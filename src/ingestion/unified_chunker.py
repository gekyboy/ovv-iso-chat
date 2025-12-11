"""
Unified Chunker per OVV ISO Chat v3.9.1
Chunking unificato per tutti i tipi documento (PS, IL, MR, TOOLS)

Delega automaticamente:
- PS/IL → ISOChunker (parent + child gerarchico da PDF)
- MR/TOOLS → SyntheticChunker (da metadata JSON)

Questo modulo risolve il problema di avere logica di chunking
frammentata tra script e moduli, rendendo il progetto più
robusto e facilmente esportabile.

Usage:
    >>> from src.ingestion import UnifiedChunker
    >>> chunker = UnifiedChunker(config_path="config/config.yaml")
    >>> chunks = chunker.chunk_documents(documents)
    
    # Oppure chunk + enrich in un colpo
    >>> enriched = chunker.chunk_and_enrich(documents, glossary=glossary)

Created: 2025-12-10
Project: F06 - UnifiedChunker
"""

import logging
from typing import List, Dict, Optional, Any, Set
from pathlib import Path
from dataclasses import dataclass

import yaml

from .extractor import ExtractedDocument
from .chunker import ISOChunker, Chunk
from .synthetic_chunker import SyntheticChunker, SyntheticChunk

logger = logging.getLogger(__name__)


@dataclass
class UnifiedChunkingStats:
    """Statistiche di chunking unificato"""
    total_documents: int = 0
    total_chunks: int = 0
    hierarchical_docs: int = 0  # PS/IL
    hierarchical_chunks: int = 0
    synthetic_docs: int = 0  # MR/TOOLS con metadata
    synthetic_chunks: int = 0
    fallback_docs: int = 0  # MR/TOOLS senza metadata (fallback a light)
    fallback_chunks: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        return {
            "total_documents": self.total_documents,
            "total_chunks": self.total_chunks,
            "hierarchical_docs": self.hierarchical_docs,
            "hierarchical_chunks": self.hierarchical_chunks,
            "synthetic_docs": self.synthetic_docs,
            "synthetic_chunks": self.synthetic_chunks,
            "fallback_docs": self.fallback_docs,
            "fallback_chunks": self.fallback_chunks
        }


class UnifiedChunker:
    """
    Chunker unificato che delega al chunker appropriato per tipo documento.
    
    Config-driven:
        - synthetic_chunk_types: ["MR", "TOOLS"] → usa SyntheticChunker
        - tutti gli altri → usa ISOChunker
    
    Il vantaggio principale è che la logica di scelta è nel MODULO,
    non nello script, rendendo il progetto più robusto e esportabile.
    
    Attributes:
        iso_chunker: Chunker per documenti testuali (PS, IL)
        synthetic_chunker: Chunker per documenti template (MR, TOOLS)
        synthetic_types: Set di tipi che usano chunking sintetico
    
    Example:
        >>> chunker = UnifiedChunker()
        >>> 
        >>> # Chunk singolo documento
        >>> chunks = chunker.chunk_document(document)
        >>> 
        >>> # Chunk lista documenti
        >>> all_chunks = chunker.chunk_documents(documents)
        >>> 
        >>> # Chunk + enrich in un colpo
        >>> enriched = chunker.chunk_and_enrich(documents, glossary)
    """
    
    def __init__(
        self,
        config: Optional[Dict] = None,
        config_path: str = "config/config.yaml"
    ):
        """
        Inizializza UnifiedChunker.
        
        Args:
            config: Dizionario configurazione (prioritario)
            config_path: Percorso config.yaml (fallback)
        """
        self.config = config or self._load_config(config_path)
        self.config_path = config_path
        
        # Inizializza sub-chunkers
        self.iso_chunker = ISOChunker(config=self.config, config_path=config_path)
        self.synthetic_chunker = SyntheticChunker()
        
        # Tipi documento per chunking sintetico (da config)
        ingestion_config = self.config.get("ingestion", {})
        self.synthetic_types: Set[str] = set(
            ingestion_config.get("synthetic_chunk_types", ["MR", "TOOLS"])
        )
        
        # Doc IDs con metadata sintetico disponibile
        self._synthetic_doc_ids: Set[str] = set(
            self.synthetic_chunker.get_doc_ids_with_metadata()
        )
        
        # Stats
        self._stats = UnifiedChunkingStats()
        
        logger.info(
            f"UnifiedChunker inizializzato: "
            f"synthetic_types={self.synthetic_types}, "
            f"available_synthetic_docs={len(self._synthetic_doc_ids)}"
        )
    
    def _load_config(self, config_path: str) -> Dict:
        """Carica configurazione da YAML"""
        if Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    def _should_use_synthetic(self, doc_type: str, doc_id: str) -> bool:
        """
        Determina se usare chunking sintetico per un documento.
        
        Args:
            doc_type: Tipo documento (PS, IL, MR, TOOLS)
            doc_id: ID documento
            
        Returns:
            True se deve usare SyntheticChunker
        """
        # Il tipo deve essere nella lista synthetic
        if doc_type.upper() not in self.synthetic_types:
            return False
        
        # E deve avere metadata disponibili
        if doc_id not in self._synthetic_doc_ids:
            # Prova anche varianti del doc_id
            normalized = doc_id.upper().replace("-", "_")
            for available_id in self._synthetic_doc_ids:
                if normalized == available_id.upper().replace("-", "_"):
                    return True
            return False
        
        return True
    
    def _synthetic_to_chunk(
        self,
        synthetic: SyntheticChunk,
        document: ExtractedDocument
    ) -> Chunk:
        """
        Converte SyntheticChunk nel formato Chunk standard.
        
        Args:
            synthetic: Chunk sintetico generato
            document: Documento originale (per metadata aggiuntivi)
            
        Returns:
            Chunk in formato standard
        """
        return Chunk(
            id=f"{synthetic.doc_id}_synthetic_0",
            text=synthetic.text,
            chunk_type="synthetic",
            chunk_index=0,
            doc_id=synthetic.doc_id,
            doc_type=synthetic.doc_type,
            chapter=document.metadata.chapter if document else "",
            revision=document.metadata.revision if document else "",
            title=synthetic.title,
            priority=document.metadata.priority if document else 0.85,
            iso_section="SYNTHETIC",
            label=f"{synthetic.doc_id} | Synthetic"
        )
    
    def chunk_document(
        self,
        document: ExtractedDocument
    ) -> List[Chunk]:
        """
        Esegue chunking di un singolo documento.
        Delega automaticamente al chunker appropriato.
        
        Args:
            document: Documento estratto
            
        Returns:
            Lista di Chunk (normali o convertiti da sintetici)
        """
        doc_type = document.metadata.doc_type.upper()
        doc_id = document.metadata.doc_id
        
        if self._should_use_synthetic(doc_type, doc_id):
            # MR/TOOLS → Chunking sintetico da metadata
            logger.debug(f"Chunking SINTETICO per {doc_id} (tipo: {doc_type})")
            
            try:
                synthetic_chunk = self.synthetic_chunker.generate_chunk(doc_id)
                if synthetic_chunk:
                    # Converti SyntheticChunk → Chunk standard
                    chunk = self._synthetic_to_chunk(synthetic_chunk, document)
                    return [chunk]
                else:
                    logger.warning(
                        f"Nessun metadata per {doc_id}, fallback a chunking light"
                    )
                    return self.iso_chunker.chunk_document(document)
                    
            except Exception as e:
                logger.error(f"Errore chunking sintetico {doc_id}: {e}")
                # Fallback a chunking normale
                return self.iso_chunker.chunk_document(document)
        
        else:
            # PS/IL → Chunking gerarchico normale
            logger.debug(f"Chunking GERARCHICO per {doc_id} (tipo: {doc_type})")
            return self.iso_chunker.chunk_document(document)
    
    def chunk_documents(
        self,
        documents: List[ExtractedDocument]
    ) -> List[Chunk]:
        """
        Esegue chunking di una lista di documenti.
        
        Args:
            documents: Lista documenti estratti
            
        Returns:
            Lista di tutti i chunk
        """
        all_chunks = []
        
        # Reset stats
        self._stats = UnifiedChunkingStats()
        self._stats.total_documents = len(documents)
        
        for doc in documents:
            doc_type = doc.metadata.doc_type.upper()
            doc_id = doc.metadata.doc_id
            
            chunks = self.chunk_document(doc)
            
            # Aggiorna stats
            if self._should_use_synthetic(doc_type, doc_id):
                if chunks and chunks[0].chunk_type == "synthetic":
                    self._stats.synthetic_docs += 1
                    self._stats.synthetic_chunks += len(chunks)
                else:
                    self._stats.fallback_docs += 1
                    self._stats.fallback_chunks += len(chunks)
            else:
                self._stats.hierarchical_docs += 1
                self._stats.hierarchical_chunks += len(chunks)
            
            all_chunks.extend(chunks)
        
        self._stats.total_chunks = len(all_chunks)
        
        # Log stats
        logger.info(
            f"UnifiedChunker completato: "
            f"{self._stats.total_chunks} chunks totali "
            f"(hierarchical={self._stats.hierarchical_docs} docs/{self._stats.hierarchical_chunks} chunks, "
            f"synthetic={self._stats.synthetic_docs} docs/{self._stats.synthetic_chunks} chunks, "
            f"fallback={self._stats.fallback_docs} docs/{self._stats.fallback_chunks} chunks)"
        )
        
        return all_chunks
    
    def chunk_and_enrich(
        self,
        documents: List[ExtractedDocument],
        glossary=None
    ) -> List["EnrichedChunk"]:
        """
        Chunking + arricchimento in un solo passaggio.
        
        Args:
            documents: Lista documenti
            glossary: GlossaryResolver opzionale
            
        Returns:
            Lista EnrichedChunk pronti per indexing
        """
        from .enricher import ChunkEnricher
        
        # 1. Chunk
        chunks = self.chunk_documents(documents)
        
        # 2. Arricchisci
        enricher = ChunkEnricher(
            glossary=glossary,
            max_glossary_defs=5,
            include_scope_for=["PS", "IL"]
        )
        
        doc_map = {doc.metadata.doc_id: doc for doc in documents}
        enriched = enricher.enrich_chunks(chunks, documents=doc_map)
        
        return enriched
    
    def get_stats(self) -> UnifiedChunkingStats:
        """Ritorna statistiche ultimo chunking"""
        return self._stats
    
    def get_synthetic_doc_ids(self) -> Set[str]:
        """Ritorna set di doc_id con metadata sintetici disponibili"""
        return self._synthetic_doc_ids.copy()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PER TEST STANDALONE
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Setup path
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root / "src"))
    import os
    os.chdir(project_root)
    
    logging.basicConfig(level=logging.INFO)
    
    from ingestion.extractor import PDFExtractor
    
    print("=" * 70)
    print("TEST UNIFIED CHUNKER")
    print("=" * 70)
    
    # Inizializza
    extractor = PDFExtractor()
    chunker = UnifiedChunker()
    
    print(f"\nSynthetic types: {chunker.synthetic_types}")
    print(f"Available synthetic doc IDs: {len(chunker.get_synthetic_doc_ids())}")
    
    # Estrai alcuni documenti
    print("\nEstrazione documenti...")
    docs = extractor.extract_directory("data/input_docs", limit=10)
    print(f"Estratti {len(docs)} documenti")
    
    # Chunk
    print("\nChunking...")
    chunks = chunker.chunk_documents(docs)
    
    # Stats
    stats = chunker.get_stats()
    print(f"\n📊 STATISTICHE:")
    print(f"   Documenti totali: {stats.total_documents}")
    print(f"   Chunks totali: {stats.total_chunks}")
    print(f"   Hierarchical (PS/IL): {stats.hierarchical_docs} docs → {stats.hierarchical_chunks} chunks")
    print(f"   Synthetic (MR/TOOLS): {stats.synthetic_docs} docs → {stats.synthetic_chunks} chunks")
    print(f"   Fallback (no metadata): {stats.fallback_docs} docs → {stats.fallback_chunks} chunks")
    
    # Mostra alcuni chunks
    print(f"\n📝 PRIMI 5 CHUNKS:")
    for c in chunks[:5]:
        print(f"   {c.doc_id} [{c.chunk_type}]: {c.text[:60]}...")

