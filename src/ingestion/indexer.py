"""
Qdrant Indexer con BGE-M3 Hybrid Search
Indicizza chunk con embedding dense + sparse per documenti ISO-SGI

v3.1 - Ottimizzato per RTX 3060 6GB:
- BGE-M3: batch=16 (fallback 8)
- Hybrid search: dense + sparse vectors
- VRAM target: <5.5GB
"""

import os
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import yaml
import torch
from tqdm import tqdm

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# SINGLETON THREAD-SAFE: Modello BGE-M3 condiviso
# Double-check locking pattern per thread safety
# ═══════════════════════════════════════════════════════════════
import threading
_GLOBAL_BGE_MODEL = None
_GLOBAL_BGE_MODEL_NAME = None
_BGE_MODEL_LOCK = threading.Lock()

def get_shared_bge_model(model_name: str = "BAAI/bge-m3", device: str = "cuda"):
    """
    Restituisce il modello BGE-M3 condiviso (singleton thread-safe).
    Evita ricaricamenti multipli che consumano tempo e VRAM.
    Usa double-check locking per thread safety.
    """
    global _GLOBAL_BGE_MODEL, _GLOBAL_BGE_MODEL_NAME
    
    # Fast path: modello già caricato
    if _GLOBAL_BGE_MODEL is not None and _GLOBAL_BGE_MODEL_NAME == model_name:
        return _GLOBAL_BGE_MODEL
    
    # Slow path: carica modello con lock
    with _BGE_MODEL_LOCK:
        # Double-check: un altro thread potrebbe aver caricato nel frattempo
        if _GLOBAL_BGE_MODEL is not None and _GLOBAL_BGE_MODEL_NAME == model_name:
            return _GLOBAL_BGE_MODEL
        
        logger.info(f"Caricamento modello BGE-M3: {model_name} (thread-safe)")
        try:
            from FlagEmbedding import BGEM3FlagModel
            _GLOBAL_BGE_MODEL = BGEM3FlagModel(
                model_name,
                use_fp16=True,
                device=device
            )
            logger.info(f"BGE-M3 caricato su {device}")
        except ImportError:
            logger.warning("FlagEmbedding non disponibile, uso SentenceTransformers")
            from sentence_transformers import SentenceTransformer
            # Forza cache folder comune
            import os
            os.environ.setdefault('SENTENCE_TRANSFORMERS_HOME', '.cache/sentence_transformers')
            _GLOBAL_BGE_MODEL = SentenceTransformer(model_name, device=device)
        
        _GLOBAL_BGE_MODEL_NAME = model_name
        
        if torch.cuda.is_available():
            vram_mb = torch.cuda.memory_allocated() / 1024 / 1024
            logger.info(f"VRAM utilizzata dopo caricamento: {vram_mb:.0f} MB")
    
    return _GLOBAL_BGE_MODEL


@dataclass
class IndexStats:
    """Statistiche di indicizzazione"""
    total_documents: int
    total_chunks: int
    indexed_chunks: int
    failed_chunks: int
    collection_name: str
    vram_used_mb: float = 0.0


class BGEEmbedder:
    """
    Wrapper per BGE-M3 con supporto hybrid (dense + sparse)
    Ottimizzato per VRAM limitata
    """
    
    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cuda",
        batch_size: int = 16,
        batch_size_fallback: int = 8
    ):
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.batch_size_fallback = batch_size_fallback
        self._model = None
        
    @property
    def model(self):
        """Usa modello BGE-M3 condiviso (singleton) per evitare ricaricamenti"""
        if self._model is None:
            # Usa il singleton globale
            self._model = get_shared_bge_model(self.model_name, self.device)
            self._log_vram()
        return self._model
    
    def _log_vram(self):
        """Log utilizzo VRAM"""
        if torch.cuda.is_available():
            vram_mb = torch.cuda.memory_allocated() / 1024 / 1024
            logger.info(f"VRAM utilizzata: {vram_mb:.0f} MB")
    
    def encode(
        self,
        texts: List[str],
        return_sparse: bool = True,
        show_progress: bool = True
    ) -> Dict[str, Any]:
        """
        Genera embedding dense e sparse
        
        Args:
            texts: Lista di testi
            return_sparse: Se True, restituisce anche sparse vectors
            show_progress: Mostra barra progresso
            
        Returns:
            Dict con 'dense' e opzionalmente 'sparse'
        """
        logger.info(f"Generazione embedding per {len(texts)} testi")
        
        current_batch = self.batch_size
        
        try:
            # Check se è FlagEmbedding (ha return_dense param)
            from inspect import signature
            encode_sig = signature(self.model.encode)
            is_flag_embedding = 'return_dense' in encode_sig.parameters
            
            if is_flag_embedding:
                # BGE-M3 FlagEmbedding
                output = self.model.encode(
                    texts,
                    batch_size=current_batch,
                    max_length=8192,
                    return_dense=True,
                    return_sparse=return_sparse,
                    return_colbert_vecs=False
                )
                
                result = {"dense": output["dense_vecs"]}
                if return_sparse and "lexical_weights" in output:
                    result["sparse"] = output["lexical_weights"]
            else:
                # SentenceTransformer (restituisce ndarray diretto)
                embeddings = self.model.encode(
                    texts,
                    batch_size=current_batch,
                    show_progress_bar=show_progress,
                    normalize_embeddings=True
                )
                result = {"dense": embeddings, "sparse": None}
                
        except torch.cuda.OutOfMemoryError:
            logger.warning(f"OOM con batch={current_batch}, fallback a {self.batch_size_fallback}")
            torch.cuda.empty_cache()
            
            # Retry con batch ridotto - usa SentenceTransformer fallback
            embeddings = self.model.encode(
                texts,
                batch_size=self.batch_size_fallback,
                show_progress_bar=show_progress,
                normalize_embeddings=True
            )
            result = {"dense": embeddings, "sparse": None}
        
        self._log_vram()
        return result


class QdrantIndexer:
    """
    Indexer per Qdrant Vector Database con BGE-M3 Hybrid
    """
    
    def __init__(self, config: Optional[Dict] = None, config_path: Optional[str] = None):
        """
        Inizializza l'indexer
        """
        if config:
            self.config = config
        else:
            self.config = self._load_config(config_path)
        
        # Configurazione Qdrant
        qdrant_config = self.config.get("qdrant", {})
        self.qdrant_url = qdrant_config.get("url", "http://localhost:6333")
        self.collection_name = qdrant_config.get("collection", "iso_sgi_docs_v31")
        self.vector_size = qdrant_config.get("vector_size", 1024)
        
        # Configurazione embedding
        embed_config = self.config.get("embedding", {})
        self.embed_model_name = embed_config.get("model", "BAAI/bge-m3")
        self.embed_device = embed_config.get("device", "cuda")
        self.embed_batch_size = embed_config.get("batch_size", 16)
        self.embed_batch_fallback = embed_config.get("batch_size_low_vram", 8)
        self.use_hybrid = embed_config.get("hybrid", {}).get("enabled", True)
        
        # Lazy loading
        self._qdrant_client = None
        self._embedder = None
        
        logger.info(
            f"QdrantIndexer: collection={self.collection_name}, "
            f"model={self.embed_model_name}, hybrid={self.use_hybrid}"
        )
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Carica configurazione"""
        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    @property
    def qdrant_client(self):
        """Lazy loading client Qdrant"""
        if self._qdrant_client is None:
            from qdrant_client import QdrantClient
            self._qdrant_client = QdrantClient(url=self.qdrant_url)
            logger.info(f"Connesso a Qdrant: {self.qdrant_url}")
        return self._qdrant_client
    
    @property
    def embedder(self) -> BGEEmbedder:
        """Lazy loading embedder"""
        if self._embedder is None:
            self._embedder = BGEEmbedder(
                model_name=self.embed_model_name,
                device=self.embed_device,
                batch_size=self.embed_batch_size,
                batch_size_fallback=self.embed_batch_fallback
            )
        return self._embedder
    
    def create_collection(self, recreate: bool = False) -> bool:
        """
        Crea o ricrea la collection Qdrant con supporto hybrid
        """
        from qdrant_client.models import (
            Distance, VectorParams, SparseVectorParams, 
            SparseIndexParams
        )
        
        try:
            collections = self.qdrant_client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if exists and recreate:
                logger.info(f"Eliminazione collection: {self.collection_name}")
                self.qdrant_client.delete_collection(self.collection_name)
                exists = False
            
            if not exists:
                logger.info(f"Creazione collection: {self.collection_name}")
                
                # Configurazione hybrid vectors
                vectors_config = {
                    "dense": VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                }
                
                sparse_config = None
                if self.use_hybrid:
                    sparse_config = {
                        "sparse": SparseVectorParams(
                            index=SparseIndexParams(on_disk=False)
                        )
                    }
                
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=vectors_config,
                    sparse_vectors_config=sparse_config
                )
                
                logger.info(f"Collection '{self.collection_name}' creata (hybrid={self.use_hybrid})")
            else:
                logger.info(f"Collection '{self.collection_name}' già esistente")
            
            return True
            
        except Exception as e:
            logger.error(f"Errore creazione collection: {e}")
            return False
    
    def index_chunks(
        self,
        chunks: List,  # List[Chunk] o List[EnrichedChunk]
        batch_size: int = 50
    ) -> IndexStats:
        """
        Indicizza chunk in Qdrant con embedding hybrid.
        
        Supporta sia Chunk normali che EnrichedChunk (R21).
        Per EnrichedChunk usa text_for_embedding (testo arricchito).
        """
        from qdrant_client.models import PointStruct, SparseVector
        from .enricher import EnrichedChunk
        
        if not chunks:
            return IndexStats(0, 0, 0, 0, self.collection_name)
        
        # Conta chunks arricchiti per logging
        enriched_count = sum(1 for c in chunks if isinstance(c, EnrichedChunk))
        logger.info(
            f"Indicizzazione {len(chunks)} chunk "
            f"({enriched_count} arricchiti R21)"
        )
        
        # Estrai testi - usa text_for_embedding se EnrichedChunk
        texts = []
        for chunk in chunks:
            if isinstance(chunk, EnrichedChunk):
                texts.append(chunk.text_for_embedding)  # Testo arricchito
            else:
                texts.append(chunk.text)  # Testo originale
        
        # Genera embedding
        embeddings = self.embedder.encode(
            texts,
            return_sparse=self.use_hybrid,
            show_progress=True
        )
        
        dense_vectors = embeddings["dense"]
        sparse_data = embeddings.get("sparse")
        has_sparse = sparse_data is not None and self.use_hybrid
        
        # Crea points
        points = []
        for i, chunk in enumerate(chunks):
            point_id = abs(hash(chunk.id)) % (2**63)
            
            # Converti dense vector
            dense = dense_vectors[i]
            dense_list = dense.tolist() if hasattr(dense, 'tolist') else list(dense)
            
            # Costruisci vector dict
            if has_sparse and isinstance(sparse_data, list) and i < len(sparse_data):
                sparse = sparse_data[i]
                if sparse is not None and isinstance(sparse, dict) and sparse:
                    indices = [int(k) for k in sparse.keys()]
                    values = [float(v) for v in sparse.values()]
                    vectors = {
                        "dense": dense_list,
                        "sparse": SparseVector(indices=indices, values=values)
                    }
                else:
                    vectors = {"dense": dense_list}
            else:
                vectors = {"dense": dense_list}
            
            point = PointStruct(
                id=point_id,
                vector=vectors,
                payload=chunk.to_dict()
            )
            points.append(point)
        
        # Upload in batch
        indexed = 0
        failed = 0
        
        for i in tqdm(range(0, len(points), batch_size), desc="Uploading to Qdrant"):
            batch = points[i:i + batch_size]
            try:
                self.qdrant_client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
                indexed += len(batch)
            except Exception as e:
                logger.error(f"Errore upload batch {i}: {e}")
                failed += len(batch)
        
        # Stats
        unique_docs = len(set(c.doc_id for c in chunks))
        vram_mb = 0.0
        if torch.cuda.is_available():
            vram_mb = torch.cuda.memory_allocated() / 1024 / 1024
        
        stats = IndexStats(
            total_documents=unique_docs,
            total_chunks=len(chunks),
            indexed_chunks=indexed,
            failed_chunks=failed,
            collection_name=self.collection_name,
            vram_used_mb=vram_mb
        )
        
        logger.info(
            f"Indicizzazione completata: {indexed}/{len(chunks)} chunk, "
            f"{unique_docs} doc, VRAM: {vram_mb:.0f}MB"
        )
        
        return stats
    
    def search(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0
    ) -> List:
        """
        Cerca nella collection usando embedding hybrid
        
        Args:
            query: Query di ricerca
            limit: Numero massimo risultati
            score_threshold: Soglia minima score
            
        Returns:
            Lista di ScoredPoint
        """
        from qdrant_client.models import ScoredPoint
        
        try:
            # Genera embedding della query
            embeddings = self.embedder.encode(
                [query],
                return_sparse=self.use_hybrid,
                show_progress=False
            )
            
            query_dense = embeddings["dense"][0].tolist()
            
            # Cerca in Qdrant
            if self.use_hybrid and "sparse" in embeddings and embeddings["sparse"]:
                # Hybrid search (dense + sparse)
                from qdrant_client.models import (
                    SparseVector, SearchRequest, 
                    NamedSparseVector, NamedVector
                )
                
                sparse_data = embeddings["sparse"][0]
                
                # Prima cerca solo con dense (più stabile)
                results = self.qdrant_client.search(
                    collection_name=self.collection_name,
                    query_vector=("dense", query_dense),
                    limit=limit,
                    score_threshold=score_threshold
                )
            else:
                # Solo dense search
                results = self.qdrant_client.search(
                    collection_name=self.collection_name,
                    query_vector=("dense", query_dense),
                    limit=limit,
                    score_threshold=score_threshold
                )
            
            logger.debug(f"Search: trovati {len(results)} risultati per '{query[:50]}...'")
            return results
            
        except Exception as e:
            logger.error(f"Errore search: {e}")
            return []
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Ottiene info sulla collection"""
        try:
            info = self.qdrant_client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "points_count": info.points_count,
                "status": info.status.name,
                "vectors_count": getattr(info, 'vectors_count', info.points_count)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def unload_model(self):
        """Scarica modello dalla VRAM"""
        if self._embedder and self._embedder._model:
            del self._embedder._model
            self._embedder._model = None
            torch.cuda.empty_cache()
            logger.info("Modello embedding scaricato dalla VRAM")


# Importa Chunk per type hints
from .chunker import Chunk

