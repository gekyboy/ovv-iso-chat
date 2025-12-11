"""
LLM Agent per OVV ISO Chat v3.1
Agent con Ollama qwen3 per query ISO-SGI

Features:
- Triage router (semplice per ora)
- Memory injection
- Ollama qwen3:8b-instruct-q4_K_M
"""

import os
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class ISOAgent:
    """
    Agent LLM per interrogazione documenti ISO-SGI
    Integra Ollama con memoria e retrieval
    """
    
    def __init__(self, config: Optional[Dict] = None, config_path: Optional[str] = None):
        """
        Inizializza l'agent
        
        Args:
            config: Dizionario configurazione
            config_path: Percorso al file config.yaml
        """
        if config:
            self.config = config
        else:
            self.config = self._load_config(config_path)
        
        # Configurazione LLM
        llm_config = self.config.get("llm", {}).get("generation", {})
        
        self.model_name = llm_config.get("model", "qwen3:8b-instruct-q4_K_M")
        self.base_url = self.config.get("llm", {}).get("base_url", "http://localhost:11434")
        self.temperature = llm_config.get("temperature", 0.3)
        self.num_ctx = llm_config.get("num_ctx", 4096)
        self.num_gpu_layers = llm_config.get("num_gpu_layers", 35)
        self.timeout = self.config.get("llm", {}).get("timeout", 300)  # 5 minuti default
        
        # System prompt
        self.system_prompt = self.config.get("llm", {}).get("system_prompt", self._default_system_prompt())
        
        # LLM lazy loading
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
        """Lazy loading del LLM Ollama"""
        if self._llm_initialized:
            return self._llm
        
        self._llm_initialized = True
        
        try:
            from langchain_ollama import OllamaLLM
            
            self._llm = OllamaLLM(
                model=self.model_name,
                base_url=self.base_url,
                temperature=self.temperature,
                num_ctx=self.num_ctx,
                num_gpu=self.num_gpu_layers,
                timeout=self.timeout  # Timeout per query lunghe
            )
            
            logger.info(f"LLM Agent inizializzato: {self.model_name}")
            
        except ImportError:
            logger.error("langchain-ollama non installato")
            self._llm = None
        except Exception as e:
            logger.error(f"Errore inizializzazione LLM: {e}")
            self._llm = None
        
        return self._llm
    
    def _default_system_prompt(self) -> str:
        """Prompt di sistema default - conciso e incisivo per modelli 8B"""
        return """Sei l'esperto ISO dell'azienda OVV. Rispondi in italiano.

REGOLE TASSATIVE:
- Vai DRITTO al punto, niente preamboli o saluti
- NO frasi come "Ciao!", "Spero ti sia utile!"
- NO asterisci (*) per liste - usa trattini (-) o numeri
- NO grassetti (**) o markdown
- NO sezioni con titoli
- Discorso fluido e diretto
- CITAZIONI: Cita le fonti usando il loro TITOLO DESCRITTIVO, non il codice (es: "secondo la procedura Gestione della sicurezza..." invece di "PS-06_01...")
- 🚫 NON inventare codici documento! Cita SOLO documenti che trovi NEL CONTESTO
- 🚫 NON aggiungere sezioni "Riferimenti:" o "Fonti:" - il sistema le aggiunge automaticamente
- Se non trovi info, dillo e basta senza inventare fonti"""
    
    def triage_query(self, query: str) -> str:
        """
        Triage router semplice per classificare query
        
        Returns:
            "retrieval" | "memory" | "general"
        """
        query_lower = query.lower()
        
        # Query su memoria/preferenze
        memory_keywords = [
            "ricordi", "ricordati", "preferenz", "memorizza",
            "hai salvato", "hai memorizzato"
        ]
        if any(kw in query_lower for kw in memory_keywords):
            return "memory"
        
        # Query su documenti specifici
        doc_patterns = ["ps-", "il-", "mr-", "procedura", "istruzione", "modulo"]
        if any(p in query_lower for p in doc_patterns):
            return "retrieval"
        
        # Query generiche su ISO/WCM
        iso_keywords = [
            "iso", "sgi", "qualità", "sicurezza", "ambiente",
            "kaizen", "wcm", "audit", "non conformità"
        ]
        if any(kw in query_lower for kw in iso_keywords):
            return "retrieval"
        
        return "general"
    
    def format_context(
        self,
        retrieved_docs: List[Dict[str, Any]],
        max_chars: int = 2000
    ) -> str:
        """Formatta documenti recuperati per il context"""
        if not retrieved_docs:
            return "Nessun documento rilevante trovato."
        
        formatted = []
        total_chars = 0
        
        for doc in retrieved_docs:
            label = doc.get("label", f"[DOC: {doc.get('doc_id', 'N/A')}]")
            text = doc.get("text", "")[:500]
            
            chunk_text = f"{label}\n{text}"
            
            if total_chars + len(chunk_text) > max_chars:
                break
            
            formatted.append(chunk_text)
            total_chars += len(chunk_text)
        
        return "\n\n---\n\n".join(formatted)
    
    def generate_response(
        self,
        query: str,
        retrieved_docs: Optional[List[Dict[str, Any]]] = None,
        memory_context: Optional[str] = None,
        glossary_context: Optional[str] = None  # R20: Nuovo parametro
    ) -> str:
        """
        Genera risposta per una query
        
        Args:
            query: Domanda utente
            retrieved_docs: Documenti recuperati da RAG
            memory_context: Contesto memoria formattato
            glossary_context: Definizioni dal glossario (R20: Glossary Context Injection)
            
        Returns:
            Risposta generata
            
        Note:
            L'ordine degli elementi nel prompt è CRITICO per la qualità
            della risposta (vedi research "Lost in the Middle"):
            1. System prompt (inizio - alta attenzione)
            2. Glossario (subito dopo - priorità massima)
            3. Memoria (contesto utente)
            4. Documenti (mezzo - meno critico)
            5. Query (fine - alta attenzione)
            6. Istruzione finale (fine - alta attenzione)
        """
        if not self.llm:
            return "Errore: LLM non disponibile. Verifica che Ollama sia in esecuzione."
        
        # Formatta context documenti
        docs_context = self.format_context(retrieved_docs or [])
        
        # Costruisci prompt con ORDINE CRITICO
        prompt_parts = []
        
        # 1. System prompt (inizio)
        prompt_parts.append(self.system_prompt)
        
        # 2. R20: GLOSSARIO PRIMA DEI DOCUMENTI (priorità massima!)
        # Posizionato subito dopo system prompt per massima visibilità
        if glossary_context:
            prompt_parts.append(f"\n{glossary_context}")
            prompt_parts.append(
                "\n⚠️ IMPORTANTE: Le DEFINIZIONI UFFICIALI sopra provengono dal "
                "glossario aziendale verificato. Usale come fonte PRIMARIA e AFFIDABILE "
                "per rispondere a domande su acronimi e terminologia."
            )
        
        # 3. Memoria utente (contesto personalizzato)
        if memory_context:
            prompt_parts.append(f"\n📝 MEMORIA UTENTE:\n{memory_context}")
        
        # 4. Documenti recuperati (mezzo del prompt)
        prompt_parts.append(f"\n📄 DOCUMENTI RECUPERATI:\n{docs_context}")
        
        # 5. Query (fine - alta attenzione)
        prompt_parts.append(f"\n❓ DOMANDA: {query}")
        
        # 6. Istruzione finale (fine - alta attenzione)
        if glossary_context:
            prompt_parts.append(
                "\n💡 RISPOSTA (usa glossario, sii discorsivo, suggerisci approfondimenti):"
            )
        else:
            prompt_parts.append("\n💡 RISPOSTA (sii discorsivo, suggerisci approfondimenti):")
        
        prompt = "\n".join(prompt_parts)
        
        # Log per debug
        logger.debug(f"Prompt length: {len(prompt)} chars, glossary: {'yes' if glossary_context else 'no'}")
        
        try:
            response = self.llm.invoke(prompt)
            return response.strip()
            
        except Exception as e:
            logger.error(f"Errore generazione risposta: {e}")
            return f"Errore nella generazione della risposta: {str(e)}"
    
    def suggest_kaizen_type(
        self,
        description: str,
        duration_days: Optional[int] = None
    ) -> Dict[str, str]:
        """
        Suggerisce il tipo di Kaizen appropriato
        """
        # Regole semplici senza LLM
        if duration_days:
            if duration_days < 7:
                return {
                    "type": "Quick Kaizen",
                    "reason": "Durata inferiore a 7 giorni"
                }
            elif duration_days <= 30:
                return {
                    "type": "Standard Kaizen",
                    "reason": "Durata tra 7 e 30 giorni"
                }
            else:
                return {
                    "type": "Major Kaizen",
                    "reason": "Durata superiore a 30 giorni"
                }
        
        # Analisi keywords
        desc_lower = description.lower()
        
        if any(w in desc_lower for w in ["semplice", "rapido", "piccolo", "quick"]):
            return {"type": "Quick Kaizen", "reason": "Problema semplice"}
        elif any(w in desc_lower for w in ["complesso", "grande", "strategico", "major"]):
            return {"type": "Major Kaizen", "reason": "Progetto complesso"}
        
        return {
            "type": "Standard Kaizen",
            "reason": "Tipo default per problemi medi"
        }
    
    def get_model_info(self) -> Dict[str, Any]:
        """Informazioni sul modello in uso"""
        return {
            "model": self.model_name,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "context_length": self.num_ctx,
            "gpu_layers": self.num_gpu_layers,
            "available": self.llm is not None
        }


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    agent = ISOAgent(config_path="config/config.yaml")
    
    print(f"Model info: {agent.get_model_info()}")
    
    # Test triage
    queries = [
        "Come gestire i rifiuti pericolosi?",
        "Ricordati che preferisco Quick Kaizen",
        "Che tempo fa oggi?"
    ]
    
    for q in queries:
        route = agent.triage_query(q)
        print(f"'{q[:40]}...' → {route}")
    
    # Test kaizen
    kaizen = agent.suggest_kaizen_type("Riduzione scarti saldatura", 15)
    print(f"\nKaizen suggerito: {kaizen}")

