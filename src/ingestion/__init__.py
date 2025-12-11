# Modulo Ingestion
"""
Gestione estrazione e chunking documenti PDF ISO.

Componenti:
- extractor: Estrazione testo da PDF (PyMuPDF)
- chunker: Chunking gerarchico parent-child (PS/IL)
- synthetic_chunker: Chunking da metadata (MR/TOOLS)
- unified_chunker: API unificata per tutti i tipi (F06)
- enricher: Arricchimento chunks con contesto (R21)
- indexer: Indicizzazione in Qdrant (BGE-M3 hybrid)

Usage:
    # API unificata (raccomandata)
    >>> from src.ingestion import UnifiedChunker
    >>> chunker = UnifiedChunker()
    >>> chunks = chunker.chunk_documents(documents)
    
    # Chunkers specifici (per casi particolari)
    >>> from src.ingestion import ISOChunker, SyntheticChunker
"""

from .extractor import PDFExtractor, ExtractedDocument, DocumentMetadata
from .chunker import ISOChunker, Chunk
from .synthetic_chunker import SyntheticChunker, SyntheticChunk
from .unified_chunker import UnifiedChunker, UnifiedChunkingStats
from .enricher import ChunkEnricher, EnrichedChunk
from .indexer import QdrantIndexer, IndexStats
from .glossary_indexer import GlossaryIndexer, GlossaryTerm, GlossaryIndexStats
from .path_manager import (
    DocumentPathManager, 
    PathValidationResult, 
    RecentPath,
    get_path_manager,
    reset_path_manager
)

__all__ = [
    # Extractor
    "PDFExtractor",
    "ExtractedDocument", 
    "DocumentMetadata",
    # Chunkers
    "ISOChunker",
    "Chunk",
    "SyntheticChunker",
    "SyntheticChunk",
    "UnifiedChunker",
    "UnifiedChunkingStats",
    # Enricher
    "ChunkEnricher",
    "EnrichedChunk",
    # Indexer
    "QdrantIndexer",
    "IndexStats",
    # Glossary Indexer
    "GlossaryIndexer",
    "GlossaryTerm",
    "GlossaryIndexStats",
    # Path Manager (F10)
    "DocumentPathManager",
    "PathValidationResult",
    "RecentPath",
    "get_path_manager",
    "reset_path_manager"
]

