"""
Agent 3: RetrieverAgent
Responsabilità:
- Hybrid retrieval (dense + sparse) da Qdrant
- Dual search (documenti + glossario R22)
- Reranking L1 (FlashRank) + L2 (keyword overlap)
- Deduplicazione risultati

Ottimizzazione VRAM: 
- Embedding già caricato (condiviso)
- Reranker su CPU
"""

from typing import Dict, Any, List
import time
import logging

from src.agents.state import emit_status

logger = logging.getLogger(__name__)


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
        
        Args:
            state: Stato corrente del grafo
            
        Returns:
            Aggiornamenti allo stato con documenti recuperati
        """
        # F11: Emetti stato
        emit_status(state, "retriever")
        
        start = time.time()
        
        # Ottieni sub-query o usa query espansa
        sub_queries = state.get("sub_queries", [])
        if not sub_queries:
            sub_queries = [state.get("expanded_query") or state.get("original_query", "")]
        
        all_docs = []
        seen_ids = set()
        
        for query in sub_queries:
            try:
                docs = self._retrieve_for_query(query)
                for doc in docs:
                    if doc["doc_id"] not in seen_ids:
                        all_docs.append(doc)
                        seen_ids.add(doc["doc_id"])
            except Exception as e:
                logger.warning(f"Errore retrieval per '{query[:30]}...': {e}")
        
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
            "glossary_docs": sum(1 for d in all_docs if d.get("source_type") == "glossary")
        }
        
        logger.info(
            f"RetrieverAgent: {len(all_docs)} docs from {len(sub_queries)} queries, "
            f"glossary={stats['glossary_docs']}"
        )
        
        return {
            "retrieved_docs": all_docs,
            "retrieval_scores": stats,
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

