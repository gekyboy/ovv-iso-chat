"""
RAG Pipeline per OVV ISO Chat v3.9.1
Pipeline completa: Query → Glossary → Retrieve → Rerank → Memory → Generate

Flow:
1. Query rewriting con glossary
2. HyDE document generation (R23)
3. Hybrid retrieval Qdrant (dense + sparse) top_k=40
4. Rerank L1: FlashRank CPU (top=15)
5. Rerank L2: Qwen3 GGUF CPU (top=8)
6. Memory injection pre-generation
7. Generate con Ollama llama3.1

Ottimizzato per RTX 3060 6GB VRAM (rerankers CPU)
"""

import gc
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

import yaml
import torch

logger = logging.getLogger(__name__)


def cleanup_vram():
    """Libera VRAM non utilizzata"""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        logger.debug("VRAM cleanup eseguito")


def get_vram_mb() -> float:
    """Ritorna VRAM utilizzata in MB"""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / 1024 / 1024
    return 0.0


@dataclass
class RetrievedDoc:
    """Documento recuperato"""
    doc_id: str
    text: str
    score: float
    metadata: Dict[str, Any]
    rerank_score: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return {
            "doc_id": self.doc_id,
            "text": self.text,
            "score": self.score,
            "rerank_score": self.rerank_score,
            "metadata": self.metadata
        }


@dataclass
class RAGResponse:
    """Risposta RAG completa"""
    query: str
    expanded_query: str
    answer: str
    sources: List[RetrievedDoc]
    memory_context: str
    latency_ms: float
    model_used: str


class RAGPipeline:
    """
    Pipeline RAG completa per documenti ISO-SGI
    """
    
    def __init__(
        self,
        config: Optional[Dict] = None,
        config_path: str = "config/config.yaml"
    ):
        """
        Inizializza pipeline
        
        Args:
            config: Dizionario configurazione
            config_path: Percorso config.yaml
        """
        self.config = config or self._load_config(config_path)
        self.config_path = config_path
        
        # Componenti (lazy loading)
        self._indexer = None
        self._glossary = None
        self._memory_store = None
        self._llm_agent = None
        self._flash_rank = None
        self._qwen_reranker = None
        
        # Config retrieval
        ret_config = self.config.get("retrieval", {})
        self.initial_top_k = 40  # Retrieve iniziale
        self.flash_rank_top_k = ret_config.get("reranking", {}).get("flash_rank", {}).get("top_k", 15)
        self.final_top_k = ret_config.get("reranking", {}).get("qwen_reranker", {}).get("top_k", 8)
        self.score_threshold = ret_config.get("score_threshold", 0.3)
        
        logger.info(f"RAGPipeline: retrieve={self.initial_top_k} → L1={self.flash_rank_top_k} → L2={self.final_top_k}")
    
    def _load_config(self, config_path: str) -> Dict:
        """Carica configurazione"""
        if Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    @property
    def indexer(self):
        """Lazy load indexer (per retrieval)"""
        if self._indexer is None:
            from src.ingestion.indexer import QdrantIndexer
            self._indexer = QdrantIndexer(config=self.config)
        return self._indexer
    
    @property
    def glossary(self):
        """Lazy load glossary resolver"""
        if self._glossary is None:
            from src.integration.glossary import GlossaryResolver
            self._glossary = GlossaryResolver(
                config=self.config,
                config_path=self.config_path
            )
        return self._glossary
    
    @property
    def memory_store(self):
        """Lazy load memory store"""
        if self._memory_store is None:
            from src.memory.store import MemoryStore
            self._memory_store = MemoryStore(config_path=self.config_path)
        return self._memory_store
    
    @property
    def llm_agent(self):
        """Lazy load LLM agent"""
        if self._llm_agent is None:
            from src.memory.llm_agent import ISOAgent
            self._llm_agent = ISOAgent(config_path=self.config_path)
        return self._llm_agent
    
    @property
    def flash_rank(self):
        """Lazy load FlashRank reranker (CPU)"""
        if self._flash_rank is None:
            try:
                from flashrank import Ranker, RerankRequest
                
                model = self.config.get("retrieval", {}).get(
                    "reranking", {}
                ).get("flash_rank", {}).get("model", "ms-marco-MiniLM-L-12-v2")
                
                self._flash_rank = Ranker(model_name=model)
                logger.info(f"FlashRank caricato: {model}")
                
            except ImportError:
                logger.warning("FlashRank non disponibile, skip L1 reranking")
                self._flash_rank = None
            except Exception as e:
                logger.warning(f"Errore caricamento FlashRank: {e}")
                self._flash_rank = None
        
        return self._flash_rank
    
    @property
    def glossary_indexer(self):
        """Lazy load glossary indexer per dual search (R22)"""
        if not hasattr(self, '_glossary_indexer'):
            self._glossary_indexer = None
        if self._glossary_indexer is None:
            try:
                from src.ingestion.glossary_indexer import GlossaryIndexer
                self._glossary_indexer = GlossaryIndexer(
                    config=self.config,
                    config_path=self.config_path
                )
                # Verifica se collezione esiste
                if self._glossary_indexer.collection_exists():
                    logger.info("GlossaryIndexer (R22) caricato - collezione esistente")
                else:
                    logger.info("GlossaryIndexer (R22) caricato - collezione NON esistente")
            except Exception as e:
                logger.warning(f"GlossaryIndexer non disponibile: {e}")
                self._glossary_indexer = None
        return self._glossary_indexer
    
    def _is_definition_query(self, query: str) -> bool:
        """
        Rileva se la query è una richiesta di definizione (R22).
        
        Args:
            query: Query utente
            
        Returns:
            True se query definitoria (es. "cosa significa WCM?")
        """
        import re
        
        # Pattern per query lowercase
        patterns_lower = [
            r"cosa significa",
            r"cos'è",
            r"che cos'è",
            r"definizione di",
            r"cosa vuol dire",
            r"cosa indica",
            r"acronimo",
            r"spiegami\s+\w{2,6}\b",  # "spiegami WCM" (case insensitive)
        ]
        
        query_lower = query.lower()
        if any(re.search(p, query_lower) for p in patterns_lower):
            return True
        
        # Pattern per query originale (con acronimi maiuscoli)
        # Query solo acronimo: "WCM?", "FMEA", "NC?"
        if re.match(r"^\s*[A-Z][A-Z0-9]{1,5}\s*\??\s*$", query):
            return True
        
        return False
    
    def _search_glossary(
        self,
        query: str,
        limit: int = 5
    ) -> List[RetrievedDoc]:
        """
        Cerca nella collezione glossario (R22).
        
        Args:
            query: Query di ricerca
            limit: Max risultati
            
        Returns:
            Lista RetrievedDoc da glossario (con source_type="glossary")
        """
        if not self.glossary_indexer:
            return []
        
        # Verifica se collezione esiste
        if not self.glossary_indexer.collection_exists():
            logger.debug("Collezione glossary_terms non esiste, skip search")
            return []
        
        try:
            # Config
            dual_config = self.config.get("dual_embedding", {})
            threshold = dual_config.get("glossary_score_threshold", 0.5)
            
            results = self.glossary_indexer.search(
                query=query,
                limit=limit,
                score_threshold=threshold
            )
            
            docs = []
            for r in results:
                docs.append(RetrievedDoc(
                    doc_id=f"GLOSSARY_{r['acronym']}",
                    text=f"📖 DEFINIZIONE: {r['text']}",
                    score=r['score'],
                    metadata={
                        "doc_type": "GLOSSARY",
                        "acronym": r['acronym'],
                        "full": r['full'],
                        "description": r.get('description', ''),
                        "source_type": "glossary"
                    }
                ))
            
            logger.debug(f"Glossary search: {len(docs)} risultati")
            return docs
            
        except Exception as e:
            logger.warning(f"Errore glossary search: {e}")
            return []
    
    def _merge_results_rrf(
        self,
        docs_results: List[RetrievedDoc],
        glossary_results: List[RetrievedDoc],
        k: int = 60,
        glossary_boost: float = 1.0
    ) -> List[RetrievedDoc]:
        """
        Merge risultati con Reciprocal Rank Fusion (R22).
        
        RRF Score = Σ 1/(k + rank) per ogni lista dove appare il doc.
        
        Args:
            docs_results: Risultati da iso_sgi_docs
            glossary_results: Risultati da glossary_terms
            k: Costante RRF (default 60, standard)
            glossary_boost: Moltiplicatore per score glossario
            
        Returns:
            Lista merged e ordinata per RRF score
        """
        # Dict per accumulare RRF scores e oggetti
        rrf_scores: Dict[str, float] = {}
        doc_objects: Dict[str, RetrievedDoc] = {}
        
        # Processa risultati documenti
        for rank, doc in enumerate(docs_results):
            key = doc.doc_id
            rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (k + rank + 1)
            if key not in doc_objects:
                doc_objects[key] = doc
        
        # Processa risultati glossario (con boost opzionale)
        for rank, doc in enumerate(glossary_results):
            key = doc.doc_id
            score = (1.0 / (k + rank + 1)) * glossary_boost
            rrf_scores[key] = rrf_scores.get(key, 0) + score
            if key not in doc_objects:
                doc_objects[key] = doc
        
        # Costruisci lista merged con RRF scores
        merged = []
        for doc_id, rrf_score in rrf_scores.items():
            doc = doc_objects.get(doc_id)
            if doc:
                # Usa rerank_score per RRF (sarà usato per ordinamento)
                doc.rerank_score = rrf_score
                merged.append(doc)
        
        # Ordina per RRF score decrescente
        merged.sort(key=lambda x: x.rerank_score or 0, reverse=True)
        
        logger.debug(
            f"RRF merge: {len(docs_results)} docs + {len(glossary_results)} glossary "
            f"→ {len(merged)} merged"
        )
        return merged
    
    @property
    def hyde_generator(self):
        """Lazy load HyDE generator (R23)"""
        if not hasattr(self, '_hyde_generator'):
            self._hyde_generator = None
        if self._hyde_generator is None:
            try:
                from src.integration.hyde import HyDEGenerator
                
                # Passa LLM e embedder
                llm = self.llm_agent.llm if self._llm_agent else None
                embedder = self.indexer.embedder if self._indexer else None
                
                self._hyde_generator = HyDEGenerator(
                    config=self.config,
                    llm=llm,
                    embedder=embedder
                )
                logger.info("HyDEGenerator (R23) inizializzato")
            except Exception as e:
                logger.warning(f"HyDE non disponibile: {e}")
                self._hyde_generator = None
        return self._hyde_generator
    
    def _combine_embeddings_weighted(
        self,
        embeddings: List[List[float]],
        weights: List[float]
    ) -> List[float]:
        """
        Combina embedding con media pesata (R23).
        
        Args:
            embeddings: Lista di vettori embedding
            weights: Pesi per ogni embedding
            
        Returns:
            Embedding combinato normalizzato
        """
        import numpy as np
        
        if not embeddings:
            return []
        
        if len(embeddings) != len(weights):
            raise ValueError(f"embeddings ({len(embeddings)}) e weights ({len(weights)}) devono avere stessa lunghezza")
        
        # Normalizza pesi
        weights_arr = np.array(weights, dtype=np.float32)
        weights_arr = weights_arr / weights_arr.sum()
        
        # Media pesata
        result = np.zeros(len(embeddings[0]), dtype=np.float32)
        for emb, w in zip(embeddings, weights_arr):
            result += np.array(emb, dtype=np.float32) * w
        
        # Normalizza a unit vector
        norm = np.linalg.norm(result)
        if norm > 0:
            result = result / norm
        
        return result.tolist()
    
    def _retrieve_with_hyde(
        self,
        original_query: str,
        expanded_query: str,
        hyde_document: str,
        top_k: int = 40
    ) -> List[RetrievedDoc]:
        """
        Retrieval con HyDE (R23).
        
        Genera embedding combinato da:
        - Query originale (peso 0.25)
        - Query espansa con glossario (peso 0.35)
        - Documento ipotetico HyDE (peso 0.40)
        
        Args:
            original_query: Query utente originale
            expanded_query: Query espansa con glossario
            hyde_document: Documento ipotetico generato da HyDE
            top_k: Numero risultati
            
        Returns:
            Lista documenti ordinati per score
        """
        try:
            # Genera embedding per tutti i componenti
            texts = [original_query]
            
            # Aggiungi expanded solo se diversa
            if expanded_query and expanded_query != original_query:
                texts.append(expanded_query)
            
            texts.append(hyde_document)
            
            # Genera embeddings
            embeddings_result = self.indexer.embedder.encode(
                texts,
                return_sparse=False,
                show_progress=False
            )
            dense_vectors = embeddings_result["dense"]
            
            # Ottieni pesi da config
            hyde_config = self.config.get("hyde", {}).get("embedding", {}).get("weights", {})
            
            if len(texts) == 3:
                weights = [
                    hyde_config.get("query_original", 0.25),
                    hyde_config.get("query_expanded", 0.35),
                    hyde_config.get("hyde_document", 0.40)
                ]
            else:
                # Solo query + hyde
                weights = [0.35, 0.65]
            
            # Combina embeddings
            combined_embedding = self._combine_embeddings_weighted(
                [v.tolist() if hasattr(v, 'tolist') else list(v) for v in dense_vectors],
                weights
            )
            
            logger.debug(f"HyDE combined embedding: {len(texts)} components, weights={weights}")
            
            # Cerca con embedding combinato (specificando "dense" per named vectors)
            from qdrant_client.models import NamedVector
            
            qdrant_config = self.config.get("qdrant", {})
            collection = qdrant_config.get("collection_name", "iso_sgi_docs_v31")
            
            results = self.indexer.qdrant_client.search(
                collection_name=collection,
                query_vector=NamedVector(name="dense", vector=combined_embedding),
                limit=top_k
            )
            
            # Converti risultati
            docs = []
            for hit in results:
                payload = hit.payload or {}
                docs.append(RetrievedDoc(
                    doc_id=payload.get("doc_id", "unknown"),
                    text=payload.get("text", ""),
                    score=float(hit.score),
                    metadata={
                        "doc_type": payload.get("doc_type", ""),
                        "filename": payload.get("filename", ""),
                        "title": payload.get("title", ""),  # F01: Titolo descrittivo
                        "revision": payload.get("revision", ""),  # Aggiunto per nome completo
                        "section": payload.get("section", ""),
                        "chunk_index": payload.get("chunk_index", 0)
                    }
                ))
            
            logger.info(f"HyDE retrieve: {len(docs)} documenti (top_k={top_k})")
            return docs
            
        except Exception as e:
            logger.error(f"HyDE retrieve failed: {e}")
            # Fallback a retrieve normale
            logger.info("Fallback a retrieve senza HyDE")
            return self._retrieve(expanded_query, top_k)
    
    def _retrieve(
        self,
        query: str,
        top_k: int = 40
    ) -> List[RetrievedDoc]:
        """
        Retrieval ibrido da Qdrant
        
        Args:
            query: Query da cercare
            top_k: Numero risultati
            
        Returns:
            Lista documenti ordinati per score
        """
        try:
            results = self.indexer.search(
                query=query,
                limit=top_k
            )
            
            docs = []
            for hit in results:
                payload = hit.payload or {}
                docs.append(RetrievedDoc(
                    doc_id=payload.get("doc_id", "unknown"),
                    text=payload.get("text", ""),
                    score=float(hit.score),
                    metadata={
                        "doc_type": payload.get("doc_type", ""),
                        "chapter": payload.get("chapter", ""),
                        "revision": payload.get("revision", ""),
                        "title": payload.get("title", ""),  # F01: Titolo descrittivo
                        "chunk_type": payload.get("chunk_type", ""),
                        "filename": payload.get("filename", "")
                    }
                ))
            
            logger.debug(f"Retrieved {len(docs)} documenti")
            return docs
            
        except Exception as e:
            logger.error(f"Errore retrieval: {e}")
            return []
    
    def _rerank_flashrank(
        self,
        query: str,
        docs: List[RetrievedDoc],
        top_k: int = 15
    ) -> List[RetrievedDoc]:
        """
        Reranking L1 con FlashRank (CPU)
        
        Args:
            query: Query originale
            docs: Documenti da rerancare
            top_k: Numero risultati dopo rerank
            
        Returns:
            Documenti reranked
        """
        if not self.flash_rank or not docs:
            return docs[:top_k]
        
        try:
            from flashrank import RerankRequest
            
            # Prepara passaggi per FlashRank
            passages = [
                {"id": i, "text": doc.text}
                for i, doc in enumerate(docs)
            ]
            
            # Rerank
            request = RerankRequest(query=query, passages=passages)
            results = self.flash_rank.rerank(request)
            
            # Riordina documenti
            reranked = []
            for result in results[:top_k]:
                idx = result.get("id", 0)
                if idx < len(docs):
                    doc = docs[idx]
                    doc.rerank_score = result.get("score", doc.score)
                    reranked.append(doc)
            
            logger.debug(f"FlashRank: {len(docs)} → {len(reranked)} documenti")
            return reranked
            
        except Exception as e:
            logger.warning(f"Errore FlashRank: {e}, skip reranking")
            return docs[:top_k]
    
    def _rerank_qwen(
        self,
        query: str,
        docs: List[RetrievedDoc],
        top_k: int = 8
    ) -> List[RetrievedDoc]:
        """
        Reranking L2 con Qwen3 GGUF (CPU) - semplificato
        Per ora usa scoring basato su overlap semantico
        
        Args:
            query: Query originale
            docs: Documenti da rerancare
            top_k: Numero risultati finali
            
        Returns:
            Documenti reranked
        """
        if not docs:
            return []
        
        # Per MVP: scoring semplice basato su keyword overlap
        # TODO: Integrare llama.cpp per vero Qwen3 reranking
        
        query_words = set(query.lower().split())
        
        for doc in docs:
            doc_words = set(doc.text.lower().split())
            overlap = len(query_words & doc_words) / max(len(query_words), 1)
            
            # Combina con score esistente
            if doc.rerank_score:
                doc.rerank_score = doc.rerank_score * 0.7 + overlap * 0.3
            else:
                doc.rerank_score = doc.score * 0.7 + overlap * 0.3
        
        # Ordina per rerank score
        docs.sort(key=lambda x: x.rerank_score or 0, reverse=True)
        
        logger.debug(f"L2 Rerank: {len(docs)} → {top_k} documenti")
        return docs[:top_k]
    
    def _deduplicate_by_doc_id(
        self,
        docs: List[RetrievedDoc],
        max_per_doc: int = 999  # DISABILITATO: passa TUTTO al LLM (Chain of Thought decide)
    ) -> List[RetrievedDoc]:
        """
        Deduplicazione DISABILITATA - il LLM vede tutti i chunk e decide cosa usare.
        Questo permette risposte più complete su documenti con più sezioni rilevanti.
        
        Args:
            docs: Lista documenti (già ordinati per score)
            max_per_doc: Massimo chunk per doc_id (999 = nessun limite)
            
        Returns:
            Lista dedupplicata
        """
        seen_docs = {}
        deduplicated = []
        
        for doc in docs:
            doc_id = doc.doc_id
            if doc_id not in seen_docs:
                seen_docs[doc_id] = 0
            
            if seen_docs[doc_id] < max_per_doc:
                deduplicated.append(doc)
                seen_docs[doc_id] += 1
        
        if len(deduplicated) < len(docs):
            logger.info(f"Dedup: {len(docs)} → {len(deduplicated)} documenti (rimossi {len(docs) - len(deduplicated)} duplicati)")
        
        return deduplicated
    
    def _get_memory_context(
        self,
        query: str,
        max_memories: int = 5
    ) -> str:
        """
        Ottiene contesto da memoria utente
        
        Args:
            query: Query corrente
            max_memories: Max memorie da includere
            
        Returns:
            Stringa contesto formattata
        """
        try:
            context = self.memory_store.format_for_prompt(max_items=max_memories)
            return context
        except Exception as e:
            logger.warning(f"Errore recupero memoria: {e}")
            return ""
    
    def _format_sources(
        self,
        docs: List[RetrievedDoc],
        max_chars: int = 3000
    ) -> str:
        """
        Formatta documenti per prompt LLM
        
        Args:
            docs: Documenti da formattare
            max_chars: Max caratteri totali
            
        Returns:
            Stringa formattata
        """
        if not docs:
            return "Nessun documento trovato."
        
        formatted = []
        total_chars = 0
        
        for i, doc in enumerate(docs, 1):
            # Header documento
            doc_type = doc.metadata.get("doc_type", "DOC")
            filename = doc.metadata.get("filename", doc.doc_id)
            
            header = f"[{i}] {doc_type}: {filename}"
            text = doc.text[:600]  # Limita testo
            
            chunk = f"{header}\n{text}\n"
            
            if total_chars + len(chunk) > max_chars:
                break
            
            formatted.append(chunk)
            total_chars += len(chunk)
        
        return "\n---\n".join(formatted)
    
    def _generate(
        self,
        query: str,
        sources: str,
        memory_context: str,
        glossary_context: str = ""  # R20: Nuovo parametro
    ) -> str:
        """
        Genera risposta con LLM
        
        Args:
            query: Query utente
            sources: Documenti formattati
            memory_context: Contesto memoria
            glossary_context: Contesto glossario (R20: Glossary Context Injection)
            
        Returns:
            Risposta generata
        """
        try:
            docs_list = [{"text": sources, "doc_id": "combined"}]
            response = self.llm_agent.generate_response(
                query=query,
                retrieved_docs=docs_list,
                memory_context=memory_context if memory_context else None,
                glossary_context=glossary_context if glossary_context else None  # R20
            )
            return response
            
        except Exception as e:
            logger.error(f"Errore generazione: {e}")
            return f"Errore nella generazione della risposta: {str(e)}"
    
    def query(
        self,
        question: str,
        use_glossary: bool = True,
        use_memory: bool = True,
        use_reranking: bool = True,
        inject_glossary_context: bool = True,  # R20
        use_hyde: bool = True  # R23: HyDE
    ) -> RAGResponse:
        """
        Esegue query RAG completa
        
        Args:
            question: Domanda utente
            use_glossary: Se usare glossary per espansione query
            use_memory: Se iniettare memoria utente
            use_reranking: Se usare reranking
            use_hyde: Se usare HyDE per retrieval (R23)
            inject_glossary_context: Se iniettare definizioni glossario nel prompt (R20)
            
        Returns:
            RAGResponse con risposta e metadati
        """
        start_time = datetime.now()
        
        # 1. Query expansion con glossary (già esistente)
        if use_glossary:
            expanded_query = self.glossary.rewrite_query(question)
            logger.info(f"Query espansa: {expanded_query[:100]}...")
        else:
            expanded_query = question
        
        # 2. R20: Estrai contesto glossario per injection nel prompt
        glossary_context = ""
        if use_glossary and inject_glossary_context:
            glossary_context = self.glossary.get_context_for_query(
                question,
                max_definitions=3,  # Limita per token budget
                include_description=True
            )
            if glossary_context:
                logger.info(f"R20 Glossary context: {len(glossary_context)} chars estratti")
        
        # 2.5 R23: Genera documento ipotetico HyDE
        hyde_document = None
        hyde_time_ms = 0
        if use_hyde:
            hyde_config = self.config.get("hyde", {})
            if hyde_config.get("enabled", True):
                try:
                    hyde_gen = self.hyde_generator
                    if hyde_gen:
                        # Imposta LLM se non già impostato
                        if hyde_gen._llm is None and self._llm_agent:
                            hyde_gen.set_llm(self.llm_agent.llm)
                        if hyde_gen._embedder is None and self._indexer:
                            hyde_gen.set_embedder(self.indexer.embedder)
                        
                        hyde_result = hyde_gen.generate(question)
                        if hyde_result:
                            hyde_document = hyde_result.hypothetical_document
                            hyde_time_ms = hyde_result.generation_time_ms
                            logger.info(
                                f"R23 HyDE: type={hyde_result.doc_type_hint}, "
                                f"len={len(hyde_document)}, time={hyde_time_ms:.0f}ms, "
                                f"cached={hyde_result.from_cache}"
                            )
                except Exception as e:
                    logger.warning(f"HyDE generation skipped: {e}")
        
        # 3. R22+R23: Dual retrieve (documenti + glossario)
        # 3a. Retrieve documenti principali (con HyDE se disponibile)
        if hyde_document:
            retrieved_docs = self._retrieve_with_hyde(
                original_query=question,
                expanded_query=expanded_query,
                hyde_document=hyde_document,
                top_k=self.initial_top_k
            )
            logger.info(f"Retrieved docs (HyDE): {len(retrieved_docs)}")
        else:
            retrieved_docs = self._retrieve(expanded_query, top_k=self.initial_top_k)
            logger.info(f"Retrieved docs: {len(retrieved_docs)}")
        
        # 3b. Retrieve glossario (R22)
        dual_config = self.config.get("dual_embedding", {})
        use_dual_search = dual_config.get("enabled", True) and use_glossary
        
        if use_dual_search:
            # Boost glossario se query definitoria
            is_def_query = self._is_definition_query(question)
            glossary_boost = dual_config.get("definition_query_boost", 1.5) if is_def_query else 1.0
            glossary_limit = dual_config.get("glossary_top_k", 5)
            
            retrieved_glossary = self._search_glossary(
                question,  # Usa query originale per glossario
                limit=glossary_limit
            )
            logger.info(f"Retrieved glossary: {len(retrieved_glossary)} (boost={glossary_boost:.1f}, def_query={is_def_query})")
            
            # 3c. Merge con RRF
            rrf_k = dual_config.get("rrf_k", 60)
            retrieved = self._merge_results_rrf(
                retrieved_docs,
                retrieved_glossary,
                k=rrf_k,
                glossary_boost=glossary_boost
            )
            logger.info(f"Merged results (RRF): {len(retrieved)}")
        else:
            retrieved = retrieved_docs
            logger.info(f"Dual search disabled, using docs only: {len(retrieved)}")
        
        # 4. Reranking L1 (FlashRank)
        if use_reranking and retrieved:
            reranked = self._rerank_flashrank(expanded_query, retrieved, self.flash_rank_top_k)
        else:
            reranked = retrieved[:self.flash_rank_top_k]
        
        # 5. Reranking L2 (Qwen3 o fallback)
        if use_reranking and reranked:
            final_docs = self._rerank_qwen(expanded_query, reranked, self.final_top_k)
        else:
            final_docs = reranked[:self.final_top_k]
        
        # 5.5 Deduplicazione per doc_id (evita stesso documento N volte)
        final_docs = self._deduplicate_by_doc_id(final_docs)
        
        # 6. Memory injection
        if use_memory:
            memory_context = self._get_memory_context(question)
        else:
            memory_context = ""
        
        # 7. Format sources
        sources_text = self._format_sources(final_docs)
        
        # 8. Generate response - R20: passa glossary_context
        answer = self._generate(
            question, 
            sources_text, 
            memory_context,
            glossary_context  # R20: Nuovo parametro
        )
        
        # Calcola latenza
        latency = (datetime.now() - start_time).total_seconds() * 1000
        
        # Cleanup VRAM se sopra soglia
        if get_vram_mb() > 5000:
            cleanup_vram()
            logger.info(f"VRAM cleanup: {get_vram_mb():.0f}MB")
        
        return RAGResponse(
            query=question,
            expanded_query=expanded_query,
            answer=answer,
            sources=final_docs,
            memory_context=memory_context,
            latency_ms=latency,
            model_used=self.llm_agent.model_name if self.llm_agent else "unknown"
        )
    
    def teach(
        self,
        doc_ref: str,
        instruction: str = "Spiega come compilare questo documento"
    ) -> RAGResponse:
        """
        Modalità teach: spiega documento non-PS/IL (MR, TOOLS)
        
        Args:
            doc_ref: Riferimento documento (es. "MR-10_01")
            instruction: Istruzione per LLM
            
        Returns:
            RAGResponse con spiegazione
        """
        # Costruisci query per trovare il documento
        query = f"documento {doc_ref} come compilare utilizzare"
        
        # Retrieve specifico
        retrieved = self._retrieve(query, top_k=10)
        
        # Filtra per doc_ref
        filtered = [
            doc for doc in retrieved
            if doc_ref.lower() in doc.doc_id.lower() or 
               doc_ref.lower() in doc.metadata.get("filename", "").lower()
        ]
        
        if not filtered:
            # Fallback: usa tutti i risultati
            filtered = retrieved[:5]
            logger.warning(f"Documento {doc_ref} non trovato specificamente, uso risultati generici")
        
        # Format prompt per teach
        teach_prompt = f"""
{instruction}

DOCUMENTO RICHIESTO: {doc_ref}

Fornisci:
1. Scopo del documento
2. Campi principali da compilare
3. Esempio di compilazione (se possibile)
4. Errori comuni da evitare
"""
        
        # Format sources
        sources_text = self._format_sources(filtered)
        
        # Generate
        answer = self._generate(teach_prompt, sources_text, "")
        
        return RAGResponse(
            query=f"Teach: {doc_ref}",
            expanded_query=query,
            answer=answer,
            sources=filtered,
            memory_context="",
            latency_ms=0,
            model_used=self.llm_agent.model_name if self.llm_agent else "unknown"
        )
    
    def get_status(self) -> Dict[str, Any]:
        """Ottiene stato pipeline"""
        # R22: Check glossary indexer status
        glossary_indexer_status = "not_loaded"
        if hasattr(self, '_glossary_indexer') and self._glossary_indexer:
            if self._glossary_indexer.collection_exists():
                glossary_indexer_status = "loaded_with_collection"
            else:
                glossary_indexer_status = "loaded_no_collection"
        
        return {
            "indexer": "loaded" if self._indexer else "not_loaded",
            "glossary": "loaded" if self._glossary else "not_loaded",
            "glossary_indexer": glossary_indexer_status,  # R22
            "memory": "loaded" if self._memory_store else "not_loaded",
            "llm": "loaded" if self._llm_agent else "not_loaded",
            "flash_rank": "available" if self._flash_rank else "not_available",
            "config": {
                "initial_top_k": self.initial_top_k,
                "flash_rank_top_k": self.flash_rank_top_k,
                "final_top_k": self.final_top_k,
                "dual_embedding_enabled": self.config.get("dual_embedding", {}).get("enabled", True)  # R22
            }
        }


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    pipeline = RAGPipeline(config_path="config/config.yaml")
    
    print("Status pipeline:")
    print(pipeline.get_status())
    
    # Test query
    response = pipeline.query("Come gestire i rifiuti pericolosi?")
    
    print(f"\nQuery: {response.query}")
    print(f"Expanded: {response.expanded_query}")
    print(f"Answer: {response.answer[:500]}...")
    print(f"Sources: {len(response.sources)}")
    print(f"Latency: {response.latency_ms:.0f}ms")

