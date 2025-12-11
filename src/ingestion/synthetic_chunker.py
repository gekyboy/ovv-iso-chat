"""
Synthetic Chunker per MR/TOOLS
Genera chunk ricchi di semantica da metadata invece che da PDF

Per documenti che sono principalmente form/tabelle vuote,
il contenuto estratto dal PDF non è utile per il retrieval.
Questo modulo genera chunk basati sui metadata che descrivono
lo SCOPO e l'USO del documento.

Created: 2025-12-10
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .enricher import EnrichedChunk

logger = logging.getLogger(__name__)

# Path default
DEFAULT_SEMANTIC_METADATA = "config/semantic_metadata.json"
DEFAULT_DOCUMENT_METADATA = "config/document_metadata.json"
DEFAULT_TOOLS_MAPPING = "config/tools_mapping.json"


@dataclass
class SyntheticChunk:
    """Chunk generato sinteticamente da metadata"""
    doc_id: str
    doc_type: str  # MR, TOOLS
    text: str
    chunk_type: str = "synthetic"
    chunk_id: str = ""
    
    # Metadata per Qdrant payload
    title: str = ""
    semantic_type: str = ""
    incident_category: str = ""
    applies_when: List[str] = field(default_factory=list)
    not_for: List[str] = field(default_factory=list)
    parent_ps: str = ""
    related_keywords: List[str] = field(default_factory=list)
    
    # Per compatibilità con Chunk standard
    start_idx: int = 0
    end_idx: int = 0
    section: str = ""
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = f"{self.doc_id}_synthetic_001"
        self.end_idx = len(self.text)
    
    def to_enriched_chunk(self) -> "EnrichedChunk":
        """Converte SyntheticChunk in EnrichedChunk per indicizzazione"""
        from .chunker import Chunk
        from .enricher import EnrichedChunk
        
        # Crea Chunk fittizio con tutti i campi richiesti da Chunk dataclass
        fake_chunk = Chunk(
            id=self.chunk_id,
            text=self.text,
            chunk_type=self.chunk_type,
            chunk_index=0,
            doc_id=self.doc_id,
            doc_type=self.doc_type,
            chapter=self.doc_id.split("-")[1].split("_")[0] if "-" in self.doc_id else "",
            revision="01",
            title=self.title,
            priority=0.8 if self.doc_type == "TOOLS" else 0.7,
            iso_section="",
            label=self.title,
            parent_id=None,
            child_index=None
        )
        
        # Costruisci contesto semantico
        semantic_parts = []
        if self.incident_category and self.incident_category != "general":
            semantic_parts.append(f"[CATEGORIA: {self.incident_category}]")
        if self.applies_when:
            semantic_parts.append(f"[USA QUANDO: {', '.join(self.applies_when[:3])}]")
        semantic_context = "\n".join(semantic_parts)
        
        # Crea EnrichedChunk
        return EnrichedChunk(
            original_chunk=fake_chunk,
            enriched_text=self.text,
            header_context=f"[DOC: {self.doc_id} | Tipo: {self.doc_type} | Titolo: {self.title}]",
            glossary_context="",
            scope_context="",
            semantic_context=semantic_context,
            incident_category=self.incident_category,
            semantic_type=self.semantic_type,
            applies_when=self.applies_when,
            not_for=self.not_for,
            original_length=len(self.text),
            enriched_length=len(self.text),
            acronyms_resolved=[]
        )


class SyntheticChunker:
    """
    Genera chunk sintetici per documenti MR/TOOLS.
    
    Combina dati da:
    - semantic_metadata.json (applies_when, not_for, usage_context)
    - document_metadata.json (campi_compilazione, correlazioni)
    - tools_mapping.json (fields con descrizioni, tips)
    
    Example:
        >>> chunker = SyntheticChunker()
        >>> chunks = chunker.generate_chunks(["MR-06_01", "MR-10_01"])
        >>> print(chunks[0].text[:200])
    """
    
    def __init__(
        self,
        semantic_path: str = DEFAULT_SEMANTIC_METADATA,
        document_path: str = DEFAULT_DOCUMENT_METADATA,
        tools_path: str = DEFAULT_TOOLS_MAPPING
    ):
        self.semantic_metadata: Dict = {}
        self.document_metadata: Dict = {}
        self.tools_mapping: Dict = {}
        
        self._load_metadata(semantic_path, document_path, tools_path)
        
        logger.info(
            f"SyntheticChunker: semantic={len(self.semantic_metadata)}, "
            f"documents={len(self.document_metadata)}, "
            f"tools={len(self.tools_mapping)}"
        )
    
    def _load_metadata(self, semantic_path: str, document_path: str, tools_path: str):
        """Carica tutti i metadata necessari"""
        
        # 1. Semantic metadata
        try:
            with open(semantic_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.semantic_metadata = data.get("documents", {})
            logger.info(f"Caricati {len(self.semantic_metadata)} semantic metadata")
        except Exception as e:
            logger.warning(f"Errore caricamento semantic metadata: {e}")
        
        # 2. Document metadata (MR + TOOLS)
        try:
            with open(document_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Combina moduli_registrazione e tools
            self.document_metadata = data.get("moduli_registrazione", {})
            self.document_metadata.update(data.get("tools", {}))
            logger.info(f"Caricati {len(self.document_metadata)} document metadata")
        except Exception as e:
            logger.warning(f"Errore caricamento document metadata: {e}")
        
        # 3. Tools mapping (per campi dettagliati)
        try:
            with open(tools_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.tools_mapping = data.get("tool_suggestions", {})
            logger.info(f"Caricati {len(self.tools_mapping)} tools mapping")
        except Exception as e:
            logger.warning(f"Errore caricamento tools mapping: {e}")
    
    def _find_tools_mapping(self, doc_id: str) -> Optional[Dict]:
        """Cerca mapping in tools_mapping.json per doc_id"""
        doc_id_normalized = doc_id.upper().replace("-", "_").replace(" ", "_")
        
        for key, val in self.tools_mapping.items():
            tool_doc_id = val.get("doc_id", "").upper().replace("-", "_").replace(" ", "_")
            
            if tool_doc_id == doc_id_normalized:
                return val
            if doc_id_normalized in tool_doc_id or tool_doc_id in doc_id_normalized:
                return val
        
        return None
    
    def generate_chunk_text(self, doc_id: str) -> str:
        """
        Genera testo chunk ricco di semantica per un documento.
        
        Args:
            doc_id: ID documento (es. "MR-06_01")
            
        Returns:
            Testo formattato per embedding
        """
        # Raccogli dati da tutte le fonti
        semantic = self.semantic_metadata.get(doc_id, {})
        document = self.document_metadata.get(doc_id, {})
        tools = self._find_tools_mapping(doc_id)
        
        # Estrai dati
        title = semantic.get("title") or document.get("titolo", doc_id)
        usage_context = semantic.get("usage_context", "")
        applies_when = semantic.get("applies_when", [])
        not_for = semantic.get("not_for", [])
        related_keywords = semantic.get("related_keywords", [])
        parent_ps = semantic.get("parent_ps", "") or document.get("correlazioni", {}).get("procedura_padre", "")
        semantic_type = semantic.get("semantic_type", "")
        incident_category = semantic.get("incident_category", "")
        
        # Campi da document_metadata
        campi = document.get("campi_compilazione", [])
        campi_names = [c.get("nome", "")[:50] for c in campi if c.get("nome")]
        
        # Campi dettagliati da tools_mapping
        fields_detailed = []
        if tools and "fields" in tools:
            for f in tools["fields"]:
                field_desc = f"{f['name']}: {f.get('description', '')}"
                if f.get('tips'):
                    field_desc += f" (Suggerimento: {f['tips']})"
                fields_detailed.append(field_desc)
        
        # Correlazioni
        correlazioni = document.get("correlazioni", {})
        tools_correlati = correlazioni.get("tools_correlati", [])
        moduli_correlati = correlazioni.get("moduli_correlati", [])
        
        # === COSTRUISCI TESTO CHUNK ===
        
        parts = []
        
        # Header
        parts.append(f"# {doc_id} - {title}")
        parts.append("")
        
        # Tipo documento
        doc_type = "MR" if doc_id.startswith("MR") else "TOOLS"
        parts.append(f"**Tipo documento**: {doc_type} - Modulo di Registrazione")
        
        if semantic_type:
            parts.append(f"**Tipo semantico**: {semantic_type}")
        
        if incident_category and incident_category != "general":
            parts.append(f"**Categoria incidente**: {incident_category}")
        parts.append("")
        
        # Scopo/Uso
        if usage_context:
            parts.append("## Scopo e Utilizzo")
            parts.append(usage_context)
            parts.append("")
        
        # Quando usare
        if applies_when:
            parts.append("## Quando Utilizzare Questo Modulo")
            parts.append("Usa questo documento quando l'utente chiede di:")
            for kw in applies_when[:10]:
                parts.append(f"- {kw}")
            parts.append("")
        
        # Quando NON usare
        if not_for:
            parts.append("## NON Usare Per")
            parts.append("Questo documento NON è adatto per:")
            for kw in not_for:
                parts.append(f"- {kw}")
            parts.append("")
        
        # Collegamento a PS
        if parent_ps:
            parts.append("## Procedura di Riferimento")
            parts.append(f"Questo modulo è collegato alla procedura **{parent_ps}**.")
            parts.append(f"Consultare {parent_ps} per le istruzioni complete su quando e come utilizzare questo modulo.")
            parts.append("")
        
        # Campi principali (dettagliati se disponibili)
        if fields_detailed:
            parts.append("## Campi da Compilare")
            parts.append("Questo modulo contiene i seguenti campi:")
            for field_desc in fields_detailed[:12]:
                parts.append(f"- {field_desc}")
            parts.append("")
        elif campi_names:
            parts.append("## Campi Principali")
            parts.append("Campi presenti nel modulo:")
            for nome in campi_names[:10]:
                # Pulisci nomi campi
                clean_name = nome.replace("\n", " ").strip()
                if clean_name and len(clean_name) > 3:
                    parts.append(f"- {clean_name}")
            parts.append("")
        
        # Tools correlati
        if tools_correlati:
            parts.append("## Strumenti Correlati")
            parts.append(f"Da usare insieme a: {', '.join(tools_correlati)}")
            parts.append("")
        
        # Moduli correlati
        if moduli_correlati:
            parts.append("## Moduli Correlati")
            parts.append(f"Altri moduli collegati: {', '.join(moduli_correlati)}")
            parts.append("")
        
        # Keywords per retrieval
        if related_keywords:
            parts.append("## Keywords e Termini Correlati")
            parts.append(f"{', '.join(related_keywords)}")
            parts.append("")
        
        return "\n".join(parts)
    
    def generate_chunk(self, doc_id: str) -> Optional[SyntheticChunk]:
        """
        Genera SyntheticChunk completo per un documento.
        
        Args:
            doc_id: ID documento
            
        Returns:
            SyntheticChunk o None se non trovato
        """
        # Verifica che esistano metadata
        semantic = self.semantic_metadata.get(doc_id, {})
        document = self.document_metadata.get(doc_id, {})
        
        if not semantic and not document:
            logger.debug(f"Nessun metadata trovato per {doc_id}")
            return None
        
        # Genera testo
        text = self.generate_chunk_text(doc_id)
        
        # Determina tipo documento
        if doc_id.startswith("MR"):
            doc_type = "MR"
        elif doc_id.startswith("TOOLS") or "TOOLS" in doc_id:
            doc_type = "TOOLS"
        else:
            doc_type = "MR"  # Default
        
        # Crea chunk
        chunk = SyntheticChunk(
            doc_id=doc_id,
            doc_type=doc_type,
            text=text,
            title=semantic.get("title", document.get("titolo", "")),
            semantic_type=semantic.get("semantic_type", ""),
            incident_category=semantic.get("incident_category", "general"),
            applies_when=semantic.get("applies_when", []),
            not_for=semantic.get("not_for", []),
            parent_ps=semantic.get("parent_ps", ""),
            related_keywords=semantic.get("related_keywords", [])
        )
        
        return chunk
    
    def generate_all_chunks(self) -> List[SyntheticChunk]:
        """
        Genera chunk per TUTTI i documenti MR/TOOLS con metadata.
        
        Returns:
            Lista di SyntheticChunk
        """
        chunks = []
        
        # Usa tutti i doc_id da semantic_metadata
        all_doc_ids = set(self.semantic_metadata.keys())
        
        # Aggiungi anche da document_metadata
        all_doc_ids.update(self.document_metadata.keys())
        
        # Filtra solo MR e TOOLS (escludi quelli che sembrano PS/IL)
        mr_tools_ids = [
            doc_id for doc_id in all_doc_ids
            if doc_id.startswith("MR-") or doc_id.startswith("TOOLS-") or 
               "TOOLS" in doc_id or
               (not doc_id.startswith(("PS-", "IL-")) and "-" in doc_id)
        ]
        
        logger.info(f"Generazione chunk sintetici per {len(mr_tools_ids)} documenti...")
        
        for doc_id in sorted(mr_tools_ids):
            chunk = self.generate_chunk(doc_id)
            if chunk:
                chunks.append(chunk)
        
        logger.info(f"Generati {len(chunks)} chunk sintetici")
        return chunks
    
    def generate_enriched_chunks(self) -> List["EnrichedChunk"]:
        """
        Genera EnrichedChunk pronti per indicizzazione.
        
        Returns:
            Lista di EnrichedChunk
        """
        synthetic_chunks = self.generate_all_chunks()
        return [c.to_enriched_chunk() for c in synthetic_chunks]
    
    def get_doc_ids_with_metadata(self) -> List[str]:
        """Ritorna lista doc_id che hanno metadata"""
        ids = set(self.semantic_metadata.keys())
        ids.update(self.document_metadata.keys())
        return sorted([
            doc_id for doc_id in ids
            if doc_id.startswith("MR-") or doc_id.startswith("TOOLS-") or
               "TOOLS" in doc_id or
               (not doc_id.startswith(("PS-", "IL-")) and "-" in doc_id)
        ])


# Test standalone
if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent.parent.parent)
    
    logging.basicConfig(level=logging.INFO)
    
    chunker = SyntheticChunker()
    
    print("\n=== TEST GENERAZIONE CHUNK ===\n")
    
    # Test singoli documenti
    test_docs = ["MR-06_01", "MR-06_02", "MR-10_01", "TOOLS-5_Perche"]
    
    for doc_id in test_docs:
        chunk = chunker.generate_chunk(doc_id)
        if chunk:
            print(f"✅ {doc_id}: {len(chunk.text)} chars")
            print(f"   Title: {chunk.title}")
            print(f"   Category: {chunk.incident_category}")
            print(f"   Applies when: {chunk.applies_when[:3]}")
            print()
        else:
            print(f"❌ {doc_id}: Non trovato")
    
    # Test generazione completa
    print("\n=== TEST GENERAZIONE COMPLETA ===\n")
    all_chunks = chunker.generate_all_chunks()
    print(f"Totale chunks: {len(all_chunks)}")
    
    # Conta per tipo
    mr_count = sum(1 for c in all_chunks if c.doc_type == "MR")
    tools_count = sum(1 for c in all_chunks if c.doc_type == "TOOLS")
    print(f"  MR: {mr_count}")
    print(f"  TOOLS: {tools_count}")
    
    # Mostra esempio
    if all_chunks:
        print("\n--- ESEMPIO CHUNK MR-06_01 ---")
        for c in all_chunks:
            if c.doc_id == "MR-06_01":
                print(c.text[:1000])
                print("...")
                break

