"""
ISO Document Chunker
Chunking gerarchico (parent/child) per documenti ISO-SGI

Parametri v3.1:
- Parent: 1200 char, overlap 200
- Child: 400 char, overlap 100
- Strategie: dense (PS, IL), light (MR, TOOLS)
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path

import yaml

from .extractor import ExtractedDocument, DocumentMetadata

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """Singolo chunk di testo con metadata"""
    id: str
    text: str
    chunk_type: str  # parent, child, light
    chunk_index: int
    doc_id: str
    doc_type: str
    chapter: str
    revision: str
    title: str
    priority: float
    iso_section: str
    label: str
    parent_id: Optional[str] = None
    child_index: Optional[int] = None
    char_count: int = 0
    
    def __post_init__(self):
        self.char_count = len(self.text)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte chunk in dizionario per indicizzazione"""
        return {
            "id": self.id,
            "text": self.text,
            "chunk_type": self.chunk_type,
            "chunk_index": self.chunk_index,
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "chapter": self.chapter,
            "revision": self.revision,
            "title": self.title,
            "priority": self.priority,
            "iso_section": self.iso_section,
            "label": self.label,
            "parent_id": self.parent_id,
            "child_index": self.child_index,
            "char_count": self.char_count
        }


class ISOChunker:
    """
    Chunker gerarchico per documenti ISO
    Crea chunk parent (contesto ampio) e child (retrieval preciso)
    
    Parametri v3.1:
    - parent_size: 1200 (come da config)
    - child_size: 400
    - parent_overlap: 200
    - child_overlap: 100
    """
    
    # Sezioni ISO per split semantico
    DEFAULT_ISO_SECTIONS = [
        "SCOPO",
        "CAMPO DI APPLICAZIONE",
        "RESPONSABILITÀ",
        "DEFINIZIONI",
        "MODALITÀ OPERATIVE",
        "DIAGRAMMA DI FLUSSO",
        "RIFERIMENTI",
        "ALLEGATI",
        "REGISTRAZIONI"
    ]
    
    def __init__(self, config: Optional[Dict] = None, config_path: Optional[str] = None):
        """
        Inizializza il chunker
        
        Args:
            config: Dizionario configurazione (prioritario)
            config_path: Percorso al file config.yaml (fallback)
        """
        if config:
            self.config = config
        else:
            self.config = self._load_config(config_path)
        
        # Configurazione chunk sizes da config v3.1
        chunk_config = self.config.get("ingestion", {}).get("chunking", {})
        self.parent_size = chunk_config.get("parent_size", 1200)
        self.child_size = chunk_config.get("child_size", 400)
        self.parent_overlap = chunk_config.get("parent_overlap", 200)
        self.child_overlap = chunk_config.get("child_overlap", 100)
        
        # Tipi documento per strategia
        strategies = self.config.get("ingestion", {}).get("strategies", {})
        self.dense_types = strategies.get("dense", ["PS", "IL"])
        self.light_types = strategies.get("light", ["MR", "TOOLS", "WO", "LCS", "PM", "TT"])
        
        # Sezioni ISO
        self.iso_sections = self.DEFAULT_ISO_SECTIONS
        
        logger.info(
            f"ISOChunker inizializzato: parent={self.parent_size}, child={self.child_size}, "
            f"dense={self.dense_types}, light={self.light_types}"
        )
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Carica configurazione"""
        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    def _detect_current_section(self, text: str) -> str:
        """
        Rileva la sezione ISO corrente nel testo
        """
        text_upper = text.upper()
        
        for section in self.iso_sections:
            if section.upper() in text_upper:
                return section
        
        return "GENERALE"
    
    def _split_text(
        self,
        text: str,
        chunk_size: int,
        overlap: int
    ) -> List[str]:
        """
        Divide testo in chunk con overlap
        """
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # Se non siamo alla fine, cerca un punto di split naturale
            if end < len(text):
                # Cerca fine paragrafo
                newline_pos = text.rfind("\n\n", start, end)
                if newline_pos > start + chunk_size // 2:
                    end = newline_pos + 2
                else:
                    # Cerca fine frase
                    sentence_end = text.rfind(". ", start, end)
                    if sentence_end > start + chunk_size // 2:
                        end = sentence_end + 2
            
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(chunk_text)
            
            # Prossimo chunk con overlap
            start = end - overlap
            if start >= len(text) - overlap:
                break
        
        return chunks
    
    def _create_parent_chunks(
        self,
        document: ExtractedDocument
    ) -> List[Chunk]:
        """
        Crea chunk parent dal documento
        """
        metadata = document.metadata
        text = document.full_text
        
        # Split in chunk parent
        parent_texts = self._split_text(
            text,
            self.parent_size,
            self.parent_overlap
        )
        
        parent_chunks = []
        for idx, parent_text in enumerate(parent_texts):
            current_section = self._detect_current_section(parent_text)
            
            chunk = Chunk(
                id=f"{metadata.filename}_parent_{idx}",
                text=parent_text,
                chunk_type="parent",
                chunk_index=idx,
                doc_id=metadata.doc_id,
                doc_type=metadata.doc_type,
                chapter=metadata.chapter,
                revision=metadata.revision,
                title=metadata.title,
                priority=metadata.priority,
                iso_section=current_section,
                label=f"{metadata.label} | {current_section}"
            )
            parent_chunks.append(chunk)
        
        return parent_chunks
    
    def _create_child_chunks(
        self,
        parent_chunks: List[Chunk]
    ) -> List[Chunk]:
        """
        Crea chunk child da chunk parent
        """
        child_chunks = []
        
        for parent in parent_chunks:
            child_texts = self._split_text(
                parent.text,
                self.child_size,
                self.child_overlap
            )
            
            for child_idx, child_text in enumerate(child_texts):
                chunk = Chunk(
                    id=f"{parent.id}_child_{child_idx}",
                    text=child_text,
                    chunk_type="child",
                    chunk_index=parent.chunk_index,
                    doc_id=parent.doc_id,
                    doc_type=parent.doc_type,
                    chapter=parent.chapter,
                    revision=parent.revision,
                    title=parent.title,
                    priority=parent.priority,
                    iso_section=parent.iso_section,
                    label=parent.label,
                    parent_id=parent.id,
                    child_index=child_idx
                )
                child_chunks.append(chunk)
        
        return child_chunks
    
    def _create_light_chunks(
        self,
        document: ExtractedDocument
    ) -> List[Chunk]:
        """
        Crea chunk leggeri per documenti MR/template
        Solo parent chunks, più grandi
        """
        metadata = document.metadata
        text = document.full_text
        
        # Per documenti light, chunk più grandi senza child
        light_texts = self._split_text(
            text,
            self.parent_size * 2,  # Chunk doppi
            self.parent_overlap
        )
        
        chunks = []
        for idx, chunk_text in enumerate(light_texts):
            current_section = self._detect_current_section(chunk_text)
            
            chunk = Chunk(
                id=f"{metadata.filename}_light_{idx}",
                text=chunk_text,
                chunk_type="light",
                chunk_index=idx,
                doc_id=metadata.doc_id,
                doc_type=metadata.doc_type,
                chapter=metadata.chapter,
                revision=metadata.revision,
                title=metadata.title,
                priority=metadata.priority,
                iso_section=current_section,
                label=f"{metadata.label} | {current_section}"
            )
            chunks.append(chunk)
        
        return chunks
    
    def chunk_document(
        self,
        document: ExtractedDocument
    ) -> List[Chunk]:
        """
        Esegue chunking completo di un documento
        """
        doc_type = document.metadata.doc_type
        
        # Strategia basata su tipo documento
        if doc_type in self.dense_types:
            # Chunking denso gerarchico
            parent_chunks = self._create_parent_chunks(document)
            child_chunks = self._create_child_chunks(parent_chunks)
            all_chunks = parent_chunks + child_chunks
            
            logger.debug(
                f"Chunking denso {document.metadata.doc_id}: "
                f"{len(parent_chunks)} parent, {len(child_chunks)} child"
            )
        else:
            # Chunking leggero
            all_chunks = self._create_light_chunks(document)
            
            logger.debug(
                f"Chunking light {document.metadata.doc_id}: "
                f"{len(all_chunks)} chunk"
            )
        
        return all_chunks
    
    def chunk_documents(
        self,
        documents: List[ExtractedDocument]
    ) -> List[Chunk]:
        """
        Esegue chunking di una lista di documenti
        """
        all_chunks = []
        
        for doc in documents:
            chunks = self.chunk_document(doc)
            all_chunks.extend(chunks)
        
        # Stats per tipo
        parent_count = sum(1 for c in all_chunks if c.chunk_type == "parent")
        child_count = sum(1 for c in all_chunks if c.chunk_type == "child")
        light_count = sum(1 for c in all_chunks if c.chunk_type == "light")
        
        logger.info(
            f"Totale chunk: {len(all_chunks)} "
            f"(parent: {parent_count}, child: {child_count}, light: {light_count})"
        )
        
        return all_chunks


    def chunk_and_enrich(
        self,
        document: ExtractedDocument,
        enricher: Optional["ChunkEnricher"] = None
    ) -> List:
        """
        Chunking + arricchimento in un'unica operazione (R21).
        
        Args:
            document: Documento da processare
            enricher: ChunkEnricher (se None, ritorna chunks normali)
            
        Returns:
            Lista di EnrichedChunk se enricher, altrimenti List[Chunk]
        """
        # Prima chunk normalmente
        chunks = self.chunk_document(document)
        
        # Poi arricchisci se enricher disponibile
        if enricher:
            return enricher.enrich_chunks(
                chunks, 
                documents={document.metadata.doc_id: document}
            )
        
        # Fallback: ritorna chunks normali
        return chunks
    
    def chunk_and_enrich_documents(
        self,
        documents: List[ExtractedDocument],
        enricher: Optional["ChunkEnricher"] = None
    ) -> List:
        """
        Chunking + arricchimento per lista di documenti (R21).
        
        Args:
            documents: Lista documenti
            enricher: ChunkEnricher (opzionale)
            
        Returns:
            Lista di chunks (arricchiti se enricher disponibile)
        """
        # Prima chunk tutti
        all_chunks = self.chunk_documents(documents)
        
        # Poi arricchisci se enricher
        if enricher:
            doc_map = {doc.metadata.doc_id: doc for doc in documents}
            return enricher.enrich_chunks(all_chunks, documents=doc_map)
        
        return all_chunks


# Import per type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .enricher import ChunkEnricher


# Entry point per test
if __name__ == "__main__":
    import sys
    from .extractor import PDFExtractor
    
    logging.basicConfig(level=logging.INFO)
    
    config_path = "config/config.yaml"
    extractor = PDFExtractor(config_path=config_path)
    chunker = ISOChunker(config_path=config_path)
    
    if len(sys.argv) > 1:
        test_path = Path(sys.argv[1])
    else:
        test_path = Path("data/input_docs")
    
    # Estrai documenti (limit 3 per test)
    docs = extractor.extract_directory(test_path, limit=3)
    
    # Chunk
    chunks = chunker.chunk_documents(docs)
    
    print(f"\nGenerati {len(chunks)} chunk totali")
    print("\nEsempio chunk:")
    for chunk in chunks[:3]:
        print(f"\n  ID: {chunk.id}")
        print(f"  Tipo: {chunk.chunk_type}")
        print(f"  Sezione: {chunk.iso_section}")
        print(f"  Caratteri: {chunk.char_count}")
        print(f"  Testo: {chunk.text[:100]}...")

