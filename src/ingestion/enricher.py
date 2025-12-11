"""
Chunk Enricher per OVV ISO Chat v3.3
Arricchisce chunks con contesto glossario e metadata (R21)

Strategia "Prepending Context":
1. Header contestuale: [DOC: id | Sezione: x | Titolo: y]
2. Glossario: [Glossario: ACR1 = def1, ACR2 = def2]
3. Scopo documento (opzionale, per PS/IL)

Basato su ricerca:
- Contextual Retrieval (Anthropic): -49% retrieval failures
- Summary-Augmented Chunking (SAC): +15-25% precision
- RAG Techniques (NirDiamant): Contextual Chunk Headers
"""

import re
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .chunker import Chunk
    from .extractor import ExtractedDocument
    from ..integration.glossary import GlossaryResolver

logger = logging.getLogger(__name__)

# Path default per semantic metadata
DEFAULT_SEMANTIC_METADATA_PATH = "config/semantic_metadata.json"


@dataclass
class EnrichedChunk:
    """
    Chunk arricchito con contesto preposto.
    
    Contiene sia il testo originale (per display) che il testo
    arricchito (per embedding), permettendo retrieval migliorato
    mantenendo output pulito per l'utente.
    """
    # Dati originali
    original_chunk: "Chunk"
    
    # Testo arricchito (usato per embedding)
    enriched_text: str
    
    # Componenti contesto
    header_context: str = ""
    glossary_context: str = ""
    scope_context: str = ""
    semantic_context: str = ""  # NUOVO: Contesto semantico per filtering
    
    # Metadata semantici per Qdrant payload (filtering)
    incident_category: str = ""
    semantic_type: str = ""
    applies_when: List[str] = field(default_factory=list)
    not_for: List[str] = field(default_factory=list)
    
    # Metriche
    original_length: int = 0
    enriched_length: int = 0
    acronyms_resolved: List[str] = field(default_factory=list)
    
    @property
    def text_for_embedding(self) -> str:
        """Testo da usare per generare embedding (arricchito)"""
        return self.enriched_text
    
    @property
    def text_for_display(self) -> str:
        """Testo originale per display all'utente"""
        return self.original_chunk.text
    
    @property
    def text(self) -> str:
        """Alias per compatibilità con Chunk.text"""
        return self.original_chunk.text
    
    @property
    def id(self) -> str:
        """ID del chunk originale"""
        return self.original_chunk.id
    
    @property
    def doc_id(self) -> str:
        """Doc ID del chunk originale"""
        return self.original_chunk.doc_id
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Converte in dizionario per Qdrant payload.
        Preserva tutti i campi originali + aggiunge campi arricchimento.
        Include metadata semantici per filtering nel retriever.
        """
        base = self.original_chunk.to_dict()
        base.update({
            # Testo arricchito per riferimento
            "enriched_text": self.enriched_text,
            # Componenti contesto separati
            "header_context": self.header_context,
            "glossary_context": self.glossary_context,
            "scope_context": self.scope_context,
            "semantic_context": self.semantic_context,
            # NUOVO: Metadata semantici per filtering Qdrant
            "incident_category": self.incident_category,
            "semantic_type": self.semantic_type,
            "applies_when": self.applies_when,
            "not_for": self.not_for,
            # Metriche
            "original_length": self.original_length,
            "enriched_length": self.enriched_length,
            "acronyms_resolved": self.acronyms_resolved,
            # Flag per identificare chunk arricchiti
            "is_enriched": True,
            "enrichment_version": "R21_v1"
        })
        return base


class ChunkEnricher:
    """
    Arricchisce chunks con contesto per migliorare retrieval.
    
    Livelli di arricchimento:
    1. Header contestuale (sempre) - ID doc, sezione, titolo
    2. Glossario acronimi (sempre) - Definizioni dal glossary.json
    3. Scopo documento (solo PS/IL) - Prima frase sezione SCOPO
    
    Esempio output:
    ```
    [DOC: PS-06_01 Rev.04 | Sezione: MODALITÀ OPERATIVE]
    [Titolo: Gestione delle Non Conformità]
    [Glossario: NC = Non Conformità, AC = Azione Correttiva, WCM = World Class Manufacturing]
    
    Gli strumenti del WCM relativi al pilastro Safety...
    ```
    """
    
    # Pattern per trovare acronimi nel testo
    # Supporta: WCM, FMEA, 5S, NC, AC, etc.
    ACRONYM_PATTERN = re.compile(r'\b[A-Z][A-Z0-9]{1,5}\b')
    
    # Pattern per acronimi alfanumerici (es. 5S, 5W1H)
    ALPHANUMERIC_PATTERN = re.compile(r'\b\d+[A-Z]+\b|\b[A-Z]+\d+[A-Z]*\b')
    
    # Parole comuni da escludere (sembrano acronimi ma non lo sono)
    COMMON_WORDS = {
        "IL", "LA", "UN", "IN", "SE", "NO", "SI", "CI", "NE", "DA",
        "DI", "DEL", "AL", "LE", "LO", "GLI", "UNA", "CON", "PER",
        "TRA", "SU", "ED", "AD", "MA", "CHE", "NON"
    }
    
    def __init__(
        self,
        glossary: Optional["GlossaryResolver"] = None,
        config: Optional[Dict] = None,
        max_glossary_defs: int = 5,
        max_scope_chars: int = 200,
        include_scope_for: Optional[List[str]] = None,
        semantic_metadata_path: Optional[str] = None
    ):
        """
        Inizializza l'enricher.
        
        Args:
            glossary: GlossaryResolver per risolvere acronimi
            config: Configurazione opzionale (override parametri)
            max_glossary_defs: Max definizioni glossario per chunk
            max_scope_chars: Max caratteri per scopo documento
            include_scope_for: Tipi documento per cui includere scopo
            semantic_metadata_path: Path a semantic_metadata.json
        """
        self.glossary = glossary
        self.config = config or {}
        
        # Parametri da config o default
        enrichment_config = self.config.get("enrichment", {})
        self.max_glossary_defs = enrichment_config.get(
            "max_glossary_definitions", max_glossary_defs
        )
        self.max_scope_chars = enrichment_config.get(
            "max_scope_chars", max_scope_chars
        )
        self.include_scope_for = enrichment_config.get(
            "scope_for_doc_types", include_scope_for or ["PS", "IL"]
        )
        
        # Flags da config
        self.include_header = enrichment_config.get("include_header", True)
        self.include_glossary_flag = enrichment_config.get("include_glossary", True)
        self.include_scope_flag = enrichment_config.get("include_scope", True)
        self.include_semantic_flag = enrichment_config.get("include_semantic", True)
        
        # Cache per scopi documento (evita parsing ripetuto)
        self._scope_cache: Dict[str, str] = {}
        
        # NUOVO: Carica semantic metadata per filtering
        self.semantic_metadata: Dict[str, Dict] = {}
        self._load_semantic_metadata(semantic_metadata_path)
        
        # Statistiche
        self.stats = {
            "chunks_processed": 0,
            "acronyms_resolved": 0,
            "total_context_added_chars": 0,
            "semantic_enriched": 0
        }
        
        logger.info(
            f"ChunkEnricher inizializzato: "
            f"max_defs={self.max_glossary_defs}, "
            f"max_scope={self.max_scope_chars}, "
            f"scope_for={self.include_scope_for}, "
            f"semantic_docs={len(self.semantic_metadata)}"
        )
    
    def _load_semantic_metadata(self, path: Optional[str] = None):
        """
        Carica semantic_metadata.json per arricchimento chunk.
        I metadata permettono filtering nel retriever (es. incident_category).
        """
        metadata_path = Path(path or DEFAULT_SEMANTIC_METADATA_PATH)
        
        if not metadata_path.exists():
            logger.warning(f"Semantic metadata non trovato: {metadata_path}")
            return
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Estrai documenti
            self.semantic_metadata = data.get("documents", {})
            
            # Carica anche intent patterns per eventuale uso futuro
            self.intent_patterns = data.get("intent_patterns", {})
            
            logger.info(f"Caricati {len(self.semantic_metadata)} semantic metadata")
            
        except Exception as e:
            logger.warning(f"Errore caricamento semantic metadata: {e}")
    
    def _build_semantic_context(self, chunk: "Chunk") -> tuple:
        """
        Costruisce contesto semantico e estrae metadata per il chunk.
        
        Args:
            chunk: Chunk da arricchire
            
        Returns:
            Tuple (semantic_context_str, incident_category, semantic_type, applies_when, not_for)
        """
        doc_id = chunk.doc_id
        meta = self.semantic_metadata.get(doc_id, {})
        
        if not meta:
            return "", "", "", [], []
        
        # Estrai metadata
        incident_category = meta.get("incident_category", "")
        semantic_type = meta.get("semantic_type", "")
        applies_when = meta.get("applies_when", [])
        not_for = meta.get("not_for", [])
        
        # Costruisci contesto testuale per embedding
        parts = []
        
        if incident_category:
            parts.append(f"[CATEGORIA: {incident_category}]")
        
        if meta.get("usage_context"):
            # Aggiungi breve descrizione d'uso
            usage = meta["usage_context"][:100]
            parts.append(f"[USO: {usage}]")
        
        if applies_when:
            # Prime 3 keywords per quando usare
            when_str = ", ".join(applies_when[:3])
            parts.append(f"[USA QUANDO: {when_str}]")
        
        semantic_context = "\n".join(parts)
        
        return semantic_context, incident_category, semantic_type, applies_when, not_for
    
    def _extract_acronyms(self, text: str) -> Set[str]:
        """
        Estrae potenziali acronimi dal testo.
        
        Supporta:
        - Acronimi standard: WCM, FMEA, NC, AC
        - Acronimi alfanumerici: 5S, 5W1H, PDCA
        """
        # Trova acronimi standard
        matches = set(self.ACRONYM_PATTERN.findall(text))
        
        # Trova acronimi alfanumerici (es. 5S)
        alphanumeric = self.ALPHANUMERIC_PATTERN.findall(text.upper())
        matches.update(alphanumeric)
        
        # Filtra parole comuni
        return {m for m in matches if m not in self.COMMON_WORDS and len(m) >= 2}
    
    def _build_header_context(self, chunk: "Chunk") -> str:
        """
        Costruisce header contestuale.
        
        Formato:
        [DOC: PS-06_01 Rev.04 | Sezione: MODALITÀ OPERATIVE]
        [Titolo: Gestione delle Non Conformità]
        """
        parts = []
        
        # Linea 1: ID documento e sezione
        doc_info = f"DOC: {chunk.doc_id}"
        if chunk.revision:
            doc_info += f" Rev.{chunk.revision}"
        if chunk.iso_section and chunk.iso_section != "GENERALE":
            doc_info += f" | Sezione: {chunk.iso_section}"
        parts.append(f"[{doc_info}]")
        
        # Linea 2: Titolo (se disponibile e non troppo lungo)
        if chunk.title:
            title_clean = chunk.title[:100]  # Limita lunghezza
            if len(chunk.title) > 100:
                title_clean = title_clean.rsplit(" ", 1)[0] + "..."
            parts.append(f"[Titolo: {title_clean}]")
        
        return "\n".join(parts)
    
    def _build_glossary_context(
        self, 
        text: str,
        existing_acronyms: Optional[Set[str]] = None
    ) -> tuple[str, List[str]]:
        """
        Costruisce contesto glossario.
        
        Args:
            text: Testo da analizzare
            existing_acronyms: Set di acronimi già noti (opzionale)
            
        Returns:
            (stringa_contesto, lista_acronimi_risolti)
        """
        if not self.glossary:
            return "", []
        
        # Estrai acronimi dal testo
        acronyms = self._extract_acronyms(text)
        
        # Aggiungi eventuali acronimi già noti
        if existing_acronyms:
            acronyms.update(existing_acronyms)
        
        # Risolvi acronimi
        definitions = []
        resolved = []
        
        for acr in sorted(acronyms):
            result = self.glossary.resolve_acronym(acr)
            if result:
                full = result.get("full", "")
                if full:
                    definitions.append(f"{acr} = {full}")
                    resolved.append(acr)
                    
                    if len(definitions) >= self.max_glossary_defs:
                        break
        
        if definitions:
            context = f"[Glossario: {', '.join(definitions)}]"
            return context, resolved
        
        return "", []
    
    def _build_scope_context(
        self, 
        chunk: "Chunk",
        document: Optional["ExtractedDocument"] = None
    ) -> str:
        """
        Costruisce contesto scopo documento.
        Solo per tipi specificati (default: PS, IL).
        
        Estrae prima frase/paragrafo dalla sezione SCOPO.
        """
        if chunk.doc_type not in self.include_scope_for:
            return ""
        
        # Cerca in cache
        cache_key = chunk.doc_id
        if cache_key in self._scope_cache:
            return self._scope_cache[cache_key]
        
        # Estrai da documento se disponibile
        scope = ""
        if document and document.metadata.sections_content:
            scope = document.metadata.sections_content.get("SCOPO", "")
        
        if scope:
            # Trunca e pulisci
            scope = scope.strip()
            if len(scope) > self.max_scope_chars:
                # Tronca alla parola più vicina
                scope = scope[:self.max_scope_chars]
                scope = scope.rsplit(" ", 1)[0] + "..."
            
            scope = f"[Scopo: {scope}]"
            self._scope_cache[cache_key] = scope
        
        return scope
    
    def enrich_chunk(
        self,
        chunk: "Chunk",
        document: Optional["ExtractedDocument"] = None,
        include_header: Optional[bool] = None,
        include_glossary: Optional[bool] = None,
        include_scope: Optional[bool] = None,
        include_semantic: Optional[bool] = None
    ) -> EnrichedChunk:
        """
        Arricchisce un singolo chunk.
        
        Args:
            chunk: Chunk originale
            document: Documento sorgente (per scopo)
            include_header: Override flag header (None = usa config)
            include_glossary: Override flag glossario (None = usa config)
            include_scope: Override flag scopo (None = usa config)
            include_semantic: Override flag semantic (None = usa config)
            
        Returns:
            EnrichedChunk con contesto preposto e metadata semantici
        """
        # Usa parametri passati o default da config
        do_header = include_header if include_header is not None else self.include_header
        do_glossary = include_glossary if include_glossary is not None else self.include_glossary_flag
        do_scope = include_scope if include_scope is not None else self.include_scope_flag
        do_semantic = include_semantic if include_semantic is not None else self.include_semantic_flag
        
        context_parts = []
        
        # 1. Header contestuale
        header = ""
        if do_header:
            header = self._build_header_context(chunk)
            if header:
                context_parts.append(header)
        
        # 2. Glossario
        glossary = ""
        acronyms_resolved = []
        if do_glossary:
            glossary, acronyms_resolved = self._build_glossary_context(chunk.text)
            if glossary:
                context_parts.append(glossary)
        
        # 3. Scopo documento
        scope = ""
        if do_scope:
            scope = self._build_scope_context(chunk, document)
            if scope:
                context_parts.append(scope)
        
        # 4. NUOVO: Contesto semantico per filtering
        semantic_context = ""
        incident_category = ""
        semantic_type = ""
        applies_when: List[str] = []
        not_for: List[str] = []
        
        if do_semantic:
            (
                semantic_context, 
                incident_category, 
                semantic_type, 
                applies_when, 
                not_for
            ) = self._build_semantic_context(chunk)
            
            if semantic_context:
                context_parts.append(semantic_context)
                self.stats["semantic_enriched"] += 1
        
        # Combina contesto + testo originale
        if context_parts:
            context_block = "\n".join(context_parts)
            enriched_text = f"{context_block}\n\n{chunk.text}"
        else:
            enriched_text = chunk.text
        
        # Aggiorna statistiche
        self.stats["chunks_processed"] += 1
        self.stats["acronyms_resolved"] += len(acronyms_resolved)
        self.stats["total_context_added_chars"] += len(enriched_text) - len(chunk.text)
        
        return EnrichedChunk(
            original_chunk=chunk,
            enriched_text=enriched_text,
            header_context=header,
            glossary_context=glossary,
            semantic_context=semantic_context,
            incident_category=incident_category,
            semantic_type=semantic_type,
            applies_when=applies_when,
            not_for=not_for,
            scope_context=scope,
            original_length=len(chunk.text),
            enriched_length=len(enriched_text),
            acronyms_resolved=acronyms_resolved
        )
    
    def enrich_chunks(
        self,
        chunks: List["Chunk"],
        documents: Optional[Dict[str, "ExtractedDocument"]] = None,
        **kwargs
    ) -> List[EnrichedChunk]:
        """
        Arricchisce una lista di chunks.
        
        Args:
            chunks: Lista chunks da arricchire
            documents: Dict[doc_id, ExtractedDocument] per scopi
            **kwargs: Parametri per enrich_chunk()
            
        Returns:
            Lista di EnrichedChunk
        """
        documents = documents or {}
        enriched = []
        
        for chunk in chunks:
            doc = documents.get(chunk.doc_id)
            enriched_chunk = self.enrich_chunk(chunk, document=doc, **kwargs)
            enriched.append(enriched_chunk)
        
        logger.info(
            f"Arricchiti {len(enriched)} chunks: "
            f"{self.stats['acronyms_resolved']} acronimi risolti, "
            f"+{self.stats['total_context_added_chars']} caratteri contesto"
        )
        
        return enriched
    
    def get_stats(self) -> Dict[str, Any]:
        """Ritorna statistiche di arricchimento"""
        return {
            **self.stats,
            "avg_context_chars": (
                self.stats["total_context_added_chars"] / 
                max(self.stats["chunks_processed"], 1)
            )
        }
    
    def reset_stats(self):
        """Reset statistiche per nuova sessione"""
        self.stats = {
            "chunks_processed": 0,
            "acronyms_resolved": 0,
            "total_context_added_chars": 0
        }
        self._scope_cache.clear()


# Test standalone
if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    logging.basicConfig(level=logging.INFO)
    
    # Import necessari per test
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from src.ingestion.chunker import Chunk
    
    # Crea chunk di test
    test_chunk = Chunk(
        id="test_parent_0",
        text="Gli strumenti del WCM relativi al pilastro Safety includono "
             "la matrice FMEA per l'analisi dei rischi e le NC per tracciare "
             "le non conformità rilevate durante gli audit SGI.",
        chunk_type="parent",
        chunk_index=0,
        doc_id="PS-06_01",
        doc_type="PS",
        chapter="06",
        revision="04",
        title="Gestione delle Non Conformità",
        priority=1.0,
        iso_section="MODALITÀ OPERATIVE",
        label="[DOC: PS-06_01 Rev.04]"
    )
    
    print("=" * 70)
    print("TEST CHUNK ENRICHER (senza glossario)")
    print("=" * 70)
    
    # Test senza glossario (solo header)
    enricher = ChunkEnricher()
    result = enricher.enrich_chunk(test_chunk)
    
    print("\nTESTO ORIGINALE:")
    print("-" * 40)
    print(test_chunk.text)
    
    print("\n\nTESTO ARRICCHITO:")
    print("-" * 40)
    print(result.enriched_text)
    
    print("\n\nMETRICHE:")
    print("-" * 40)
    print(f"Lunghezza: {result.original_length} → {result.enriched_length} (+{result.enriched_length - result.original_length})")
    print(f"Header: {len(result.header_context)} char")
    print(f"Glossario: {len(result.glossary_context)} char")
    print(f"Acronimi risolti: {result.acronyms_resolved}")
    
    # Test con glossario
    print("\n" + "=" * 70)
    print("TEST CON GLOSSARIO")
    print("=" * 70)
    
    try:
        from src.integration.glossary import GlossaryResolver
        glossary = GlossaryResolver(config_path="config/config.yaml")
        
        enricher_with_glossary = ChunkEnricher(glossary=glossary)
        result_with_glossary = enricher_with_glossary.enrich_chunk(test_chunk)
        
        print("\nTESTO ARRICCHITO CON GLOSSARIO:")
        print("-" * 40)
        print(result_with_glossary.enriched_text)
        
        print("\n\nACRONIMI RISOLTI:")
        print(result_with_glossary.acronyms_resolved)
        
    except Exception as e:
        print(f"Glossario non disponibile per test: {e}")
    
    print("\n" + "=" * 70)
    print("TEST COMPLETATO")
    print("=" * 70)

