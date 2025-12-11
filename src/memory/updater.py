"""
Memory Updater per OVV ISO Chat v3.1
Estrae e aggiorna memorie con feedback HITL (Human-In-The-Loop)

Features:
- Bayesian feedback boost (0.8x - 1.2x)
- Estrazione automatica da interazioni
- Feedback esplicito utente
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import yaml

from .store import MemoryStore, MemoryItem, MemoryType

logger = logging.getLogger(__name__)


class MemoryUpdater:
    """
    Gestisce estrazione e aggiornamento memorie
    con supporto feedback HITL
    """
    
    def __init__(
        self,
        memory_store: MemoryStore,
        config: Optional[Dict] = None,
        config_path: Optional[str] = None
    ):
        """
        Inizializza l'updater
        
        Args:
            memory_store: Store delle memorie
            config: Dizionario configurazione
            config_path: Percorso config.yaml
        """
        self.store = memory_store
        
        if config:
            self.config = config
        else:
            self.config = self._load_config(config_path)
        
        # LLM sarà inizializzato lazy
        self._llm = None
        self._llm_initialized = False
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Carica configurazione"""
        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    @property
    def llm(self):
        """Lazy loading LLM (opzionale, per estrazione automatica)"""
        if self._llm_initialized:
            return self._llm
        
        self._llm_initialized = True
        
        try:
            from langchain_ollama import OllamaLLM
            
            llm_config = self.config.get("llm", {}).get("memory", {})
            generation_cfg = self.config.get("llm", {}).get("generation", {})
            
            model = llm_config.get("model") or generation_cfg.get("model", "qwen3:8b-instruct-q4_K_M")
            
            self._llm = OllamaLLM(
                model=model,
                base_url=self.config.get("llm", {}).get("base_url", "http://localhost:11434"),
                temperature=llm_config.get("temperature", 0.1),
                num_ctx=llm_config.get("num_ctx", 2048),
                timeout=self.config.get("llm", {}).get("timeout", 300)  # 5 min timeout
            )
            logger.info(f"LLM per memory updater: {model}")
            
        except ImportError:
            logger.warning("langchain-ollama non disponibile per estrazione automatica")
            self._llm = None
        except Exception as e:
            logger.warning(f"LLM non disponibile: {e}")
            self._llm = None
        
        return self._llm
    
    def add_from_explicit_feedback(
        self,
        content: str,
        mem_type: str = "preference",
        related_docs: Optional[List[str]] = None,
        namespace: Optional[Tuple[str, ...]] = None
    ) -> MemoryItem:
        """
        Aggiunge memoria da feedback esplicito utente
        
        Questo è il metodo principale per HITL feedback:
        - /memoria preference "Preferisco Quick Kaizen"
        - /memoria fact "IL-06_01 gestisce rifiuti"
        - /memoria correction "Il termine corretto è..."
        
        Args:
            content: Contenuto della memoria
            mem_type: Tipo (preference, fact, correction, procedure)
            related_docs: Documenti correlati
            namespace: Namespace (opzionale)
            
        Returns:
            MemoryItem creato
        """
        # Parse tipo
        try:
            memory_type = MemoryType(mem_type.lower())
        except ValueError:
            logger.warning(f"Tipo sconosciuto '{mem_type}', uso PREFERENCE")
            memory_type = MemoryType.PREFERENCE
        
        # Confidenza alta per feedback esplicito
        confidence_map = {
            MemoryType.PREFERENCE: 0.85,
            MemoryType.FACT: 0.75,
            MemoryType.CORRECTION: 0.95,
            MemoryType.PROCEDURE: 0.80
        }
        confidence = confidence_map.get(memory_type, 0.8)
        
        # Crea memoria (no overwrite se già esiste)
        memory = self.store.put(
            content=content,
            mem_type=memory_type,
            namespace=namespace,
            source="user_feedback",
            confidence=confidence,
            related_docs=related_docs or []
        )
        
        logger.info(f"Memoria HITL aggiunta: {memory.id} ({mem_type})")
        return memory
    
    def add_positive_feedback(
        self,
        mem_id: str,
        context: str = "",
        namespace: Optional[Tuple[str, ...]] = None
    ) -> Optional[MemoryItem]:
        """
        Aggiunge feedback positivo (👍) - aumenta boost
        
        Args:
            mem_id: ID della memoria
            context: Contesto del feedback
            namespace: Namespace
            
        Returns:
            MemoryItem aggiornato
        """
        return self.store.add_feedback(
            mem_id=mem_id,
            is_positive=True,
            context=context,
            namespace=namespace
        )
    
    def add_negative_feedback(
        self,
        mem_id: str,
        context: str = "",
        namespace: Optional[Tuple[str, ...]] = None
    ) -> Optional[MemoryItem]:
        """
        Aggiunge feedback negativo (👎) - riduce boost
        
        Args:
            mem_id: ID della memoria
            context: Contesto del feedback
            namespace: Namespace
            
        Returns:
            MemoryItem aggiornato
        """
        return self.store.add_feedback(
            mem_id=mem_id,
            is_positive=False,
            context=context,
            namespace=namespace
        )
    
    def extract_from_interaction(
        self,
        user_message: str,
        assistant_response: str,
        retrieved_docs: Optional[List[Dict]] = None,
        namespace: Optional[Tuple[str, ...]] = None
    ) -> List[MemoryItem]:
        """
        Estrae memorie automaticamente da un'interazione
        (richiede LLM, opzionale)
        
        Args:
            user_message: Messaggio utente
            assistant_response: Risposta assistente
            retrieved_docs: Documenti utilizzati
            namespace: Namespace
            
        Returns:
            Lista di MemoryItem estratti
        """
        if not self.llm:
            logger.debug("LLM non disponibile per estrazione automatica")
            return []
        
        # Prima verifica se vale la pena estrarre
        if not self._should_extract(user_message, assistant_response):
            return []
        
        doc_ids = []
        if retrieved_docs:
            doc_ids = [d.get("doc_id", "N/A") for d in retrieved_docs[:5]]
        
        prompt = self._build_extraction_prompt(
            user_message,
            assistant_response[:1000],
            doc_ids
        )
        
        try:
            response = self.llm.invoke(prompt)
            memories = self._parse_extraction_response(response, doc_ids, namespace)
            
            if memories:
                logger.info(f"Estratte {len(memories)} memorie dall'interazione")
            
            return memories
            
        except Exception as e:
            logger.error(f"Errore estrazione memorie: {e}")
            return []
    
    def _should_extract(self, user_message: str, assistant_response: str) -> bool:
        """Determina se vale la pena estrarre memorie"""
        preference_keywords = [
            "preferisco", "preferire", "meglio", "vorrei",
            "mi piace", "uso sempre", "di solito"
        ]
        
        correction_keywords = [
            "correggo", "sbagliato", "errore", "invece",
            "non è così", "in realtà", "precisazione"
        ]
        
        combined = (user_message + " " + assistant_response).lower()
        
        has_preference = any(kw in combined for kw in preference_keywords)
        has_correction = any(kw in combined for kw in correction_keywords)
        
        # Lunghezza minima
        min_length = len(user_message) > 20 and len(assistant_response) > 50
        
        return (has_preference or has_correction) and min_length
    
    def _build_extraction_prompt(
        self,
        user_message: str,
        assistant_response: str,
        doc_ids: List[str]
    ) -> str:
        """Costruisce prompt per estrazione"""
        return f"""Analizza questa interazione e identifica informazioni da memorizzare.

MESSAGGIO UTENTE: {user_message}

RISPOSTA ASSISTENTE: {assistant_response}

DOCUMENTI USATI: {', '.join(doc_ids) if doc_ids else 'Nessuno'}

Identifica:
1. PREFERENZE: Scelte o preferenze espresse dall'utente
2. FATTI: Informazioni fattuali importanti discusse
3. CORREZIONI: Correzioni o chiarimenti forniti dall'utente

Rispondi SOLO in formato JSON valido:
{{
    "preferences": ["preferenza1", ...],
    "facts": ["fatto1", ...],
    "corrections": ["correzione1", ...]
}}

Se non ci sono elementi da memorizzare, rispondi con liste vuote."""
    
    def _parse_extraction_response(
        self,
        response: str,
        related_docs: List[str],
        namespace: Optional[Tuple[str, ...]]
    ) -> List[MemoryItem]:
        """Parse della risposta LLM per estrarre memorie"""
        memories = []
        
        try:
            # Cerca JSON nella risposta
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
            else:
                return []
            
            type_mapping = {
                "preferences": MemoryType.PREFERENCE,
                "facts": MemoryType.FACT,
                "corrections": MemoryType.CORRECTION
            }
            
            confidence_mapping = {
                "preferences": 0.7,
                "facts": 0.65,
                "corrections": 0.85
            }
            
            for key, mem_type in type_mapping.items():
                items = data.get(key, [])
                for content in items:
                    if content and len(content) > 5:
                        memory = self.store.put(
                            content=content,
                            mem_type=mem_type,
                            namespace=namespace,
                            source="llm_extraction",
                            confidence=confidence_mapping[key],
                            related_docs=related_docs
                        )
                        memories.append(memory)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Errore parsing JSON estrazione: {e}")
        
        return memories
    
    def get_relevant_for_query(
        self,
        query: str,
        namespace: Optional[Tuple[str, ...]] = None,
        limit: int = 5
    ) -> List[MemoryItem]:
        """
        Recupera memorie rilevanti per una query
        
        Args:
            query: Query testuale
            namespace: Namespace
            limit: Numero massimo risultati
            
        Returns:
            Lista di MemoryItem rilevanti, ordinate per boost
        """
        # Ricerca semplice + boost
        all_memories = self.store.get_all(namespace)
        
        query_lower = query.lower()
        scored = []
        
        for memory in all_memories:
            content_lower = memory.content.lower()
            query_words = query_lower.split()
            
            # Score basato su match parole
            matches = sum(1 for word in query_words if word in content_lower)
            if matches > 0:
                # Score = matches * boost * confidence
                score = matches * memory.boost_factor * memory.effective_confidence
                scored.append((memory, score))
        
        # Ordina per score
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [m for m, _ in scored[:limit]]


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    store = MemoryStore(config_path="config/config.yaml")
    updater = MemoryUpdater(store, config_path="config/config.yaml")
    
    # Test HITL feedback
    m1 = updater.add_from_explicit_feedback(
        content="Preferisco XMatrix per allineamento strategico",
        mem_type="preference"
    )
    print(f"Creato: {m1.id}")
    
    # Test positive feedback (boost up)
    updater.add_positive_feedback(m1.id, "User confirmed")
    
    # Stats
    print(f"\nStats: {store.get_stats()}")

