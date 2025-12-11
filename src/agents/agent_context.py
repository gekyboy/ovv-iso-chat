"""
Agent 4: ContextAgent
Responsabilità:
- Comprimere e selezionare context più rilevante
- Iniettare memoria utente
- Gestire token budget (max ~1500 token per context)

Ottimizzazione VRAM: No LLM, solo selezione rule-based
"""

from typing import Dict, Any, List, Tuple, Set
import time
import logging

logger = logging.getLogger(__name__)

# Lazy import per evitare circular imports
_mr_injector_instance = None

def get_mr_injector():
    """Lazy load MRInjector singleton"""
    global _mr_injector_instance
    if _mr_injector_instance is None:
        try:
            from src.agents.mr_injector import MRInjector
            _mr_injector_instance = MRInjector()
        except Exception as e:
            logger.warning(f"MRInjector non disponibile: {e}")
    return _mr_injector_instance


class ContextAgent:
    """
    Comprime e ottimizza il contesto per l'LLM.
    
    Strategie:
    - Prioritizza documenti per intent (definitional → glossary, procedural → PS/IL)
    - Tronca testi lunghi preservando inizio e fine
    - Inietta memoria utente se rilevante
    - Rispetta token budget
    """
    
    # Token budget per sezione (OTTIMIZZATO per velocità)
    # Con 8B model, meno token = più veloce senza perdere troppa qualità
    MAX_TOTAL_TOKENS = 1200  # Ridotto da 2000
    GLOSSARY_BUDGET = 150
    MEMORY_BUDGET = 200
    DOCS_BUDGET = 850  # Ridotto da 1500
    
    # Priorità per tipo documento per intent
    PRIORITY_MAP = {
        "definitional": {"GLOSSARY": 3, "PS": 2, "IL": 1, "MR": 0, "TOOLS": 0},
        "procedural": {"PS": 3, "IL": 3, "MR": 1, "GLOSSARY": 2, "TOOLS": 1},
        "teach": {"MR": 3, "TOOLS": 3, "PS": 2, "IL": 1, "GLOSSARY": 1},
        "factual": {"PS": 2, "IL": 2, "MR": 1, "GLOSSARY": 2, "TOOLS": 1},
        "comparison": {"PS": 2, "IL": 2, "MR": 1, "GLOSSARY": 2, "TOOLS": 1}
    }
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """Inizializza l'agente context."""
        self.name = "context"
        self.config_path = config_path
        self._memory_store = None
    
    @property
    def memory_store(self):
        """Lazy loading del MemoryStore"""
        if self._memory_store is None:
            try:
                from src.memory.store import MemoryStore
                self._memory_store = MemoryStore(config_path=self.config_path)
            except Exception as e:
                logger.warning(f"MemoryStore non disponibile: {e}")
        return self._memory_store
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Stima approssimativa token (4 char ≈ 1 token).
        
        Args:
            text: Testo da stimare
            
        Returns:
            Numero approssimativo di token
        """
        return len(text) // 4
    
    def _get_doc_priority(
        self, 
        doc: Dict[str, Any], 
        intent: str
    ) -> float:
        """
        Calcola priorità di un documento basata su intent.
        
        Args:
            doc: Documento da valutare
            intent: Intent della query
            
        Returns:
            Score di priorità (più alto = più prioritario)
        """
        priorities = self.PRIORITY_MAP.get(intent, self.PRIORITY_MAP["factual"])
        
        # Determina tipo documento
        doc_type = doc.get("metadata", {}).get("doc_type", "")
        if "GLOSSARY" in doc.get("doc_id", ""):
            doc_type = "GLOSSARY"
        
        base_priority = priorities.get(doc_type, 0)
        score = doc.get("rerank_score") or doc.get("score", 0)
        
        return base_priority + score
    
    def _compress_docs(
        self, 
        docs: List[Dict[str, Any]],
        intent: str,
        max_chars: int = 3500  # RIDOTTO da 6000 per velocità
    ) -> Tuple[str, List[str]]:
        """
        Comprime documenti per token budget OTTIMIZZATO.
        
        Strategia: TOP 5 chunk più rilevanti con max 600 char ciascuno.
        Questo bilancia qualità (trova info diverse) con velocità (meno token).
        
        Args:
            docs: Lista documenti da comprimere
            intent: Intent per prioritizzazione
            max_chars: Max caratteri totali
            
        Returns:
            Tuple (testo compresso, lista doc_id selezionati)
        """
        # Ordina per priorità
        sorted_docs = sorted(
            docs, 
            key=lambda d: self._get_doc_priority(d, intent), 
            reverse=True
        )
        
        compressed = []
        selected_ids = []
        total_chars = 0
        max_docs = 6  # Aumentato a 6 per includere sezioni diverse (es. 5.2 e 5.3)
        
        # Diversità: assicura chunk con contenuti diversi
        seen_content_keys = set()
        
        for doc in sorted_docs[:max_docs * 3]:  # Esamina più chunk per diversità
            if len(compressed) >= max_docs:
                break
            
            text = doc.get("text", "")
            doc_id = doc.get("doc_id", "unknown")
            
            # Diversità: evita chunk troppo simili
            content_key = text[:80].lower().strip()  # Primi 80 char come chiave
            if content_key in seen_content_keys:
                continue  # Skip chunk simile
            seen_content_keys.add(content_key)
            
            # Calcola spazio disponibile per questo doc
            max_doc_chars = min(600, max_chars - total_chars)  # RIDOTTO da 800
            if max_doc_chars <= 100:
                break
            
            # Tronca testo intelligente: inizio + fine se lungo
            if len(text) > max_doc_chars:
                half = max_doc_chars // 2
                truncated = text[:half] + "..." + text[-half:]
            else:
                truncated = text
            
            # Formatta con header compatto
            doc_type = doc.get("metadata", {}).get("doc_type", "DOC")
            if "GLOSSARY" in doc_id:
                doc_type = "📖"
            
            chunk = f"[{doc_type}:{doc_id}]\n{truncated}"
            
            compressed.append(chunk)
            selected_ids.append(doc_id)
            total_chars += len(chunk)
        
        return "\n\n---\n\n".join(compressed), selected_ids
    
    def _build_doc_id_header(self, selected_ids: List[str]) -> str:
        """
        R26: Costruisce header con lista doc_id disponibili.
        Questo aiuta il LLM a sapere quali documenti può citare.
        
        Args:
            selected_ids: Lista doc_id selezionati
            
        Returns:
            Header formattato per il prompt
        """
        if not selected_ids:
            return ""
        
        # Filtra solo doc_id validi (non GLOSSARY generico)
        valid_ids = [did for did in selected_ids if did and did != "unknown"]
        
        if not valid_ids:
            return ""
        
        doc_list = ", ".join(sorted(set(valid_ids)))
        
        return (
            f"📋 DOCUMENTI DISPONIBILI: {doc_list}\n"
            f"⚠️ CITA SOLO questi documenti. Non inventare altri riferimenti.\n\n"
        )
    
    def _get_memory_context(
        self, 
        user_id: str, 
        should_use: bool
    ) -> str:
        """
        Ottiene contesto memoria se necessario.
        
        Args:
            user_id: ID utente
            should_use: Se la memoria è richiesta
            
        Returns:
            Stringa formattata con memoria (vuota se non usata)
        """
        if not should_use or not self.memory_store:
            return ""
        
        try:
            namespace = f"user_{user_id}"
            memories = self.memory_store.format_for_prompt(
                namespace=namespace,
                max_items=5
            )
            return memories
        except Exception as e:
            logger.warning(f"Errore recupero memoria: {e}")
            return ""
    
    def _extract_ps_doc_ids(self, selected_ids: List[str]) -> List[str]:
        """
        Estrae PS doc_id dalla lista di documenti selezionati.
        
        Args:
            selected_ids: Lista doc_id selezionati
            
        Returns:
            Lista di PS doc_id (es. ["PS-06_01", "PS-10_01"])
        """
        ps_ids: List[str] = []
        seen: Set[str] = set()
        
        for doc_id in selected_ids:
            if doc_id and doc_id.upper().startswith("PS-"):
                # Normalizza
                ps_id = doc_id.upper()
                if ps_id not in seen:
                    ps_ids.append(doc_id)  # Mantieni formato originale
                    seen.add(ps_id)
        
        return ps_ids
    
    def _get_modules_section(self, selected_ids: List[str]) -> str:
        """
        Genera sezione moduli correlati per il prompt LLM.
        
        Usa MRInjector per trovare MR correlati ai PS selezionati
        e formattarli per il prompt.
        
        Args:
            selected_ids: Lista doc_id selezionati
            
        Returns:
            Stringa formattata con moduli correlati (vuota se nessuno)
        """
        mr_injector = get_mr_injector()
        if not mr_injector:
            return ""
        
        ps_ids = self._extract_ps_doc_ids(selected_ids)
        if not ps_ids:
            return ""
        
        try:
            modules_section = mr_injector.format_modules_for_prompt(ps_ids, max_total=5)
            if modules_section:
                logger.info(f"ContextAgent: iniettati moduli MR per {ps_ids}")
            return modules_section
        except Exception as e:
            logger.warning(f"Errore generazione moduli: {e}")
            return ""
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Costruisce contesto ottimizzato.
        
        R26: Aggiunge header con doc_id disponibili per prevenire allucinazioni.
        
        Args:
            state: Stato corrente del grafo
            
        Returns:
            Aggiornamenti allo stato con contesto compresso
        """
        start = time.time()
        
        docs = state.get("retrieved_docs", [])
        intent = state.get("query_intent", "factual")
        user_id = state.get("user_id", "default")
        should_use_memory = state.get("should_use_memory", False)
        glossary_context = state.get("glossary_context", "")
        
        # Comprime documenti
        compressed_docs, selected_ids = self._compress_docs(docs, intent)
        
        # R26: Costruisci header con doc_id disponibili
        doc_id_header = self._build_doc_id_header(selected_ids)
        
        # R26: Prependi header al contesto compresso
        if doc_id_header:
            compressed_docs = doc_id_header + compressed_docs
        
        # Ottieni memoria
        memory_context = self._get_memory_context(user_id, should_use_memory)
        
        # NUOVO: Genera sezione moduli MR correlati
        modules_section = self._get_modules_section(selected_ids)
        
        # Stima token totali
        total_tokens = (
            self._estimate_tokens(glossary_context) +
            self._estimate_tokens(memory_context) +
            self._estimate_tokens(compressed_docs) +
            self._estimate_tokens(modules_section)  # Include moduli
        )
        
        latency = (time.time() - start) * 1000
        
        logger.info(
            f"ContextAgent: {len(selected_ids)} docs selezionati, "
            f"~{total_tokens} token, memory={'sì' if memory_context else 'no'}, "
            f"moduli={'sì' if modules_section else 'no'}"
        )
        
        return {
            "compressed_context": compressed_docs,
            "selected_sources": selected_ids,
            "available_doc_ids": selected_ids,  # R26: Per ValidatorAgent
            "memory_context": memory_context,
            "modules_section": modules_section,  # NUOVO: Moduli MR correlati
            "token_count": total_tokens,
            "agent_trace": state.get("agent_trace", []) + [f"context:{latency:.0f}ms"]
        }


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    agent = ContextAgent(config_path="config/config.yaml")
    
    test_docs = [
        {
            "doc_id": "PS-06_01",
            "text": "La gestione dei rifiuti pericolosi deve seguire..." * 50,
            "score": 0.85,
            "rerank_score": 0.9,
            "metadata": {"doc_type": "PS"}
        },
        {
            "doc_id": "GLOSSARY_WCM",
            "text": "WCM = World Class Manufacturing: metodologia di miglioramento continuo",
            "score": 0.95,
            "rerank_score": 0.95,
            "metadata": {"doc_type": "GLOSSARY"}
        }
    ]
    
    test_state = {
        "retrieved_docs": test_docs,
        "query_intent": "procedural",
        "user_id": "test_user",
        "should_use_memory": False,
        "glossary_context": "",
        "agent_trace": []
    }
    
    result = agent(test_state)
    
    print(f"Documenti selezionati: {result['selected_sources']}")
    print(f"Token stimati: {result['token_count']}")
    print(f"Context preview: {result['compressed_context'][:300]}...")
    print(f"Trace: {result['agent_trace']}")

