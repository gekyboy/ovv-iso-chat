"""
Agent 3: RetrieverAgent
Responsabilità:
- Hybrid retrieval (dense + sparse) da Qdrant
- Dual search (documenti + glossario R22)
- Reranking L1 (FlashRank) + L2 (keyword overlap)
- Deduplicazione risultati
- NUOVO: Semantic filtering per incident_category (R27)

Ottimizzazione VRAM: 
- Embedding già caricato (condiviso)
- Reranker su CPU
"""

from typing import Dict, Any, List, Optional
import time
import logging

logger = logging.getLogger(__name__)

# R27: Pattern per rilevare intent incidente
INCIDENT_PATTERNS = {
    "real_injury": [
        "ho avuto un infortunio",
        "mi sono fatto male",
        "infortunio sul lavoro",
        "lesione",
        "ferito",
        "incidente con lesione",
        "sono stato ferito",
        "infortunio grave",
        "infortunio lieve",
        "medicazione",
        "ospedale"
    ],
    "near_miss": [
        "near miss",
        "mancato infortunio",
        "quasi incidente",
        "per poco",
        "poteva andare male",
        "senza lesioni",
        "condizione pericolosa",
        "unsafe condition",
        "azione pericolosa",
        "unsafe act"
    ],
    "non_conformity": [
        "non conformità",
        "NC",
        "prodotto difettoso",
        "scarto",
        "reclamo cliente",
        "problema qualità"
    ],
    "kaizen": [
        "kaizen",
        "miglioramento",
        "ottimizzazione",
        "proposta miglioramento",
        "riduzione sprechi"
    ]
}


class RetrieverAgent:
    """
    Recupera documenti rilevanti con hybrid search e reranking.
    
    Riusa la pipeline esistente per il retrieval, evitando duplicazione.
    Supporta multi-query retrieval per query complesse.
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Inizializza l'agente retriever.
        
        Args:
            config_path: Percorso configurazione
        """
        self.name = "retriever"
        self.config_path = config_path
        self._pipeline = None
        
        # Config retrieval
        self.initial_top_k = 40
        self.l1_top_k = 15
        self.final_top_k = 8
    
    @property
    def pipeline(self):
        """Lazy loading della pipeline RAG esistente"""
        if self._pipeline is None:
            from src.integration.rag_pipeline import RAGPipeline
            self._pipeline = RAGPipeline(config_path=self.config_path)
        return self._pipeline
    
    def _detect_incident_intent(self, query: str) -> Optional[str]:
        """
        R27: Rileva se query riguarda un tipo specifico di incidente.
        
        Args:
            query: Query utente
            
        Returns:
            Categoria incidente (real_injury, near_miss, etc.) o None
        """
        query_lower = query.lower()
        
        for category, patterns in INCIDENT_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in query_lower:
                    logger.info(f"[R27] Intent rilevato: {category} (pattern: '{pattern}')")
                    return category
        
        return None
    
    def _apply_category_boost(
        self, 
        docs: List[Dict[str, Any]], 
        target_category: str,
        boost_factor: float = 1.5
    ) -> List[Dict[str, Any]]:
        """
        R27: Applica boost ai documenti con categoria matching.
        
        Args:
            docs: Lista documenti recuperati
            target_category: Categoria da boostare (es. "real_injury")
            boost_factor: Fattore di moltiplicazione score
            
        Returns:
            Lista documenti con score aggiornati
        """
        boosted_count = 0
        penalized_count = 0
        
        for doc in docs:
            doc_category = doc.get("metadata", {}).get("incident_category", "")
            not_for = doc.get("metadata", {}).get("not_for", [])
            
            if doc_category == target_category:
                # Boost documenti con categoria corretta
                current_score = doc.get("rerank_score") or doc.get("score", 0)
                doc["rerank_score"] = current_score * boost_factor
                doc["category_boosted"] = True
                boosted_count += 1
                
            elif doc_category and doc_category != target_category:
                # Penalizza documenti con categoria sbagliata
                # Ma solo se hanno una categoria definita (non penalizzare PS/IL generici)
                current_score = doc.get("rerank_score") or doc.get("score", 0)
                doc["rerank_score"] = current_score * 0.7  # Penalità 30%
                doc["category_penalized"] = True
                penalized_count += 1
        
        if boosted_count > 0 or penalized_count > 0:
            logger.info(
                f"[R27] Category boost: {boosted_count} boostati, "
                f"{penalized_count} penalizzati per '{target_category}'"
            )
        
        # Riordina per nuovo score
        docs.sort(
            key=lambda x: x.get("rerank_score") or x.get("score", 0),
            reverse=True
        )
        
        return docs
    
    def _retrieve_for_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Esegue retrieval per singola query.
        
        Args:
            query: Query di ricerca
            
        Returns:
            Lista di documenti recuperati
        """
        # Usa metodi esistenti della pipeline
        docs = self.pipeline._retrieve(query, top_k=self.initial_top_k)
        
        # R22: Dual search glossario
        if self.pipeline.glossary_indexer and self.pipeline.glossary_indexer.collection_exists():
            glossary_docs = self.pipeline._search_glossary(query, limit=5)
            docs = self.pipeline._merge_results_rrf(docs, glossary_docs)
        
        # Rerank L1
        docs = self.pipeline._rerank_flashrank(query, docs, self.l1_top_k)
        
        # Rerank L2
        docs = self.pipeline._rerank_qwen(query, docs, self.final_top_k)
        
        # Deduplica
        docs = self.pipeline._deduplicate_by_doc_id(docs)
        
        # Converti in dizionari
        return [
            {
                "doc_id": d.doc_id,
                "text": d.text,
                "score": d.score,
                "rerank_score": d.rerank_score,
                "metadata": d.metadata,
                "source_type": "glossary" if "GLOSSARY" in d.doc_id else "document"
            }
            for d in docs
        ]
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Esegue retrieval per tutte le sub-query.
        Include R27: Semantic filtering per incident_category.
        
        Args:
            state: Stato corrente del grafo
            
        Returns:
            Aggiornamenti allo stato con documenti recuperati
        """
        start = time.time()
        
        # R27: Rileva intent incidente dalla query originale
        original_query = state.get("original_query", "")
        incident_intent = self._detect_incident_intent(original_query)
        
        # Ottieni sub-query o usa query espansa
        sub_queries = state.get("sub_queries", [])
        if not sub_queries:
            sub_queries = [state.get("expanded_query") or original_query]
        
        all_docs = []
        seen_texts = set()  # Dedup per TESTO, non per doc_id (permette sezioni diverse)
        
        for query in sub_queries:
            try:
                docs = self._retrieve_for_query(query)
                for doc in docs:
                    # Dedup per contenuto, non per doc_id
                    # Così sezioni diverse dello stesso doc passano (es. 5.2 e 5.3 rifiuti)
                    text_key = doc["text"][:100]  # Primi 100 char come chiave
                    if text_key not in seen_texts:
                        all_docs.append(doc)
                        seen_texts.add(text_key)
            except Exception as e:
                logger.warning(f"Errore retrieval per '{query[:30]}...': {e}")
        
        # R27: Applica category boost se intent rilevato
        if incident_intent:
            all_docs = self._apply_category_boost(all_docs, incident_intent)
        
        # Ordina per rerank_score
        all_docs.sort(
            key=lambda x: x.get("rerank_score") or x.get("score", 0), 
            reverse=True
        )
        
        # Limita a final_top_k
        all_docs = all_docs[:self.final_top_k]
        
        latency = (time.time() - start) * 1000
        
        # Statistiche per debug
        stats = {
            "total_docs": len(all_docs),
            "sub_queries": len(sub_queries),
            "glossary_docs": sum(1 for d in all_docs if d.get("source_type") == "glossary"),
            "incident_intent": incident_intent,
            "category_boosted": sum(1 for d in all_docs if d.get("category_boosted"))
        }
        
        logger.info(
            f"RetrieverAgent: {len(all_docs)} docs from {len(sub_queries)} queries, "
            f"glossary={stats['glossary_docs']}, intent={incident_intent}"
        )
        
        return {
            "retrieved_docs": all_docs,
            "retrieval_scores": stats,
            "incident_intent": incident_intent,  # R27: Passa intent allo state
            "agent_trace": state.get("agent_trace", []) + [f"retriever:{latency:.0f}ms"]
        }


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    agent = RetrieverAgent(config_path="config/config.yaml")
    
    test_state = {
        "original_query": "Come gestire i rifiuti pericolosi?",
        "expanded_query": "Come gestire i rifiuti pericolosi?",
        "sub_queries": ["Come gestire i rifiuti pericolosi?"],
        "agent_trace": []
    }
    
    result = agent(test_state)
    
    print(f"Documenti recuperati: {len(result['retrieved_docs'])}")
    for i, doc in enumerate(result['retrieved_docs'][:3], 1):
        print(f"  {i}. {doc['doc_id']} (score={doc.get('rerank_score', doc['score']):.3f})")
    print(f"Stats: {result['retrieval_scores']}")
    print(f"Trace: {result['agent_trace']}")

