"""
PDF Extractor per documenti ISO-SGI
Estrae testo e metadata da PDF con supporto per struttura ISO

Basato su: ovv-iso-chat/src/ingestion/extractor.py
Adattato per v3.1 con configurazione semplificata
"""

import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import pymupdf  # PyMuPDF
import yaml

logger = logging.getLogger(__name__)


@dataclass
class DocumentMetadata:
    """Metadata estratti da un documento ISO"""
    filepath: Path
    filename: str
    doc_type: str  # PS, IL, MR, TOOLS
    chapter: str
    doc_number: str
    revision: str
    title: str
    priority: float
    page_count: int
    sections_found: List[str] = field(default_factory=list)
    sections_content: Dict[str, str] = field(default_factory=dict)  # {SCOPO: "contenuto..."}
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte metadata in dizionario"""
        return {
            "filepath": str(self.filepath),
            "filename": self.filename,
            "doc_type": self.doc_type,
            "chapter": self.chapter,
            "doc_number": self.doc_number,
            "revision": self.revision,
            "title": self.title,
            "priority": self.priority,
            "page_count": self.page_count,
            "sections_found": self.sections_found,
            "sections_content": self.sections_content
        }
    
    @property
    def doc_id(self) -> str:
        """Genera ID documento univoco"""
        return f"{self.doc_type}-{self.chapter}_{self.doc_number}"
    
    @property
    def label(self) -> str:
        """Genera label per chunk"""
        return f"[DOC: {self.doc_id} Rev.{self.revision}]"


@dataclass
class ExtractedPage:
    """Pagina estratta con contenuto e metadata"""
    page_num: int
    text: str
    has_images: bool = False
    has_tables: bool = False


@dataclass
class ExtractedDocument:
    """Documento estratto completo"""
    metadata: DocumentMetadata
    pages: List[ExtractedPage]
    full_text: str
    
    @property
    def total_chars(self) -> int:
        return len(self.full_text)


class PDFExtractor:
    """
    Estrattore PDF specializzato per documenti ISO-SGI
    Estrae testo, rileva sezioni ISO e genera metadata
    """
    
    # Sezioni ISO standard da rilevare
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
    
    # Priorità default per tipo documento
    DEFAULT_PRIORITIES = {
        "PS": 1.0,
        "IL": 0.9,
        "MR": 0.5,
        "TOOLS": 0.8,
        "OTHER": 0.6
    }
    
    def __init__(self, config: Optional[Dict] = None, config_path: Optional[str] = None):
        """
        Inizializza l'estrattore
        
        Args:
            config: Dizionario configurazione (prioritario)
            config_path: Percorso al file config.yaml (fallback)
        """
        if config:
            self.config = config
        else:
            self.config = self._load_config(config_path)
        
        ingestion_config = self.config.get("ingestion", {})
        self.iso_sections = ingestion_config.get(
            "iso_sections", self.DEFAULT_ISO_SECTIONS
        )
        self.priorities = ingestion_config.get(
            "priorities", self.DEFAULT_PRIORITIES
        )
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Carica configurazione da YAML"""
        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    def extract_metadata_from_filename(self, filepath: Path) -> DocumentMetadata:
        """
        Estrae metadata dal nome file
        Pattern atteso: PS-06_01_Rev.04_Titolo documento.pdf
        """
        filename = filepath.stem
        
        # Pattern per tipo documento
        doc_type_match = re.match(r'^(PS|IL|MR)', filename, re.IGNORECASE)
        doc_type = doc_type_match.group(1).upper() if doc_type_match else "OTHER"
        
        # Determina se è un tool (WCM)
        tools_keywords = ["WO", "LCS", "PM", "TT", "Kaizen", "Matrix", "Ishikawa", "5W1H", "HERCA"]
        if any(kw.lower() in filename.lower() for kw in tools_keywords):
            doc_type = "TOOLS"
        
        # Pattern per capitolo (es. -06_)
        chapter_match = re.search(r'-(\d{2})_', filename)
        chapter = chapter_match.group(1) if chapter_match else "00"
        
        # Pattern per numero documento (es. _01_)
        doc_num_match = re.search(r'_(\d{2})_', filename)
        doc_number = doc_num_match.group(1) if doc_num_match else "00"
        
        # Pattern per revisione
        rev_match = re.search(r'Rev\.?(\d+)', filename, re.IGNORECASE)
        revision = rev_match.group(1) if rev_match else "00"
        
        # Estrai titolo (tutto dopo Rev.XX_)
        title_match = re.search(r'Rev\.?\d+[_\s]+(.+)$', filename, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).replace("_", " ").strip()
        else:
            # Fallback: usa filename senza estensione
            title = filename.replace("_", " ")
        
        # Priorità basata su tipo
        priority = self.priorities.get(doc_type, self.DEFAULT_PRIORITIES["OTHER"])
        
        return DocumentMetadata(
            filepath=filepath,
            filename=filename,
            doc_type=doc_type,
            chapter=chapter,
            doc_number=doc_number,
            revision=revision,
            title=title,
            priority=priority,
            page_count=0,
            sections_found=[]
        )
    
    def detect_iso_sections(self, text: str) -> List[str]:
        """
        Rileva sezioni ISO presenti nel testo
        """
        found_sections = []
        text_upper = text.upper()
        
        for section in self.iso_sections:
            patterns = [
                section,
                section.replace(" ", ""),
                f"{section}:",
                f"{section} :"
            ]
            for pattern in patterns:
                if pattern.upper() in text_upper:
                    if section not in found_sections:
                        found_sections.append(section)
                    break
        
        return found_sections
    
    def extract_section_content(self, text: str) -> Dict[str, str]:
        """
        Estrae il contenuto delle sezioni ISO dal testo usando regex
        
        Pattern supportati:
        - SCOPO: contenuto...
        - SCOPO : contenuto...
        - 1) SCOPO contenuto...
        - 1. SCOPO contenuto...
        
        Returns:
            Dict con {nome_sezione: contenuto}
        """
        sections_content = {}
        
        # Pattern regex per ogni sezione ISO
        section_patterns = {
            "SCOPO": r'(?:SCOPO|1\)\s*SCOPO|1\.\s*SCOPO)\s*:?\s*(.{20,500}?)(?=\n\s*\d+[\.\)]\s*[A-Z]|\n\s*[A-Z]{4,}|\Z)',
            "CAMPO DI APPLICAZIONE": r'(?:CAMPO\s*DI\s*APPLICAZIONE|2\)\s*CAMPO)\s*:?\s*(.{20,500}?)(?=\n\s*\d+[\.\)]\s*[A-Z]|\n\s*[A-Z]{4,}|\Z)',
            "RESPONSABILITÀ": r'(?:RESPONSABILIT[AÀ]|3\)\s*RESPONSABILIT)\s*:?\s*(.{20,500}?)(?=\n\s*\d+[\.\)]\s*[A-Z]|\n\s*[A-Z]{4,}|\Z)',
            "DEFINIZIONI": r'(?:DEFINIZIONI|4\)\s*DEFINIZIONI)\s*:?\s*(.{20,500}?)(?=\n\s*\d+[\.\)]\s*[A-Z]|\n\s*[A-Z]{4,}|\Z)',
            "MODALITÀ OPERATIVE": r'(?:MODALIT[AÀ]\s*OPERATIVE|5\)\s*MODALIT)\s*:?\s*(.{20,1000}?)(?=\n\s*\d+[\.\)]\s*[A-Z]|\n\s*[A-Z]{4,}|\Z)',
            "RIFERIMENTI": r'(?:RIFERIMENTI|RIFERIMENTI\s*NORMATIVI)\s*:?\s*(.{20,300}?)(?=\n\s*\d+[\.\)]\s*[A-Z]|\n\s*[A-Z]{4,}|\Z)',
        }
        
        for section_name, pattern in section_patterns.items():
            try:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    content = match.group(1).strip()
                    # Pulisci contenuto
                    content = re.sub(r'\s+', ' ', content)  # Normalizza spazi
                    content = content[:500]  # Limita lunghezza
                    if len(content) > 20:  # Solo se contenuto significativo
                        sections_content[section_name] = content
            except Exception as e:
                logger.debug(f"Errore parsing sezione {section_name}: {e}")
        
        return sections_content
    
    def extract_document(self, filepath: Path) -> Optional[ExtractedDocument]:
        """
        Estrae contenuto completo da un PDF
        
        Args:
            filepath: Percorso al file PDF
            
        Returns:
            ExtractedDocument o None se errore
        """
        try:
            filepath = Path(filepath)
            
            # Estrai metadata da filename
            metadata = self.extract_metadata_from_filename(filepath)
            
            # Apri PDF
            doc = pymupdf.open(filepath)
            metadata.page_count = len(doc)
            
            pages = []
            full_text_parts = []
            
            for page_num, page in enumerate(doc):
                # Estrai testo
                page_text = page.get_text("text")
                
                # Rileva presenza immagini/tabelle
                has_images = len(page.get_images()) > 0
                has_tables = "│" in page_text or "┌" in page_text or bool(
                    re.search(r'\t{2,}|\s{4,}\d', page_text)
                )
                
                pages.append(ExtractedPage(
                    page_num=page_num + 1,
                    text=page_text,
                    has_images=has_images,
                    has_tables=has_tables
                ))
                
                full_text_parts.append(f"[Pagina {page_num + 1}]\n{page_text}")
            
            doc.close()
            
            # Combina testo
            full_text = "\n\n".join(full_text_parts)
            
            # Rileva sezioni ISO
            metadata.sections_found = self.detect_iso_sections(full_text)
            
            # Estrai contenuto sezioni (per PS e IL)
            if metadata.doc_type in ["PS", "IL"]:
                metadata.sections_content = self.extract_section_content(full_text)
            
            logger.info(
                f"Estratto: {metadata.doc_id} - {metadata.title} "
                f"({metadata.page_count} pagine, {len(metadata.sections_found)} sezioni)"
            )
            
            return ExtractedDocument(
                metadata=metadata,
                pages=pages,
                full_text=full_text
            )
            
        except Exception as e:
            logger.error(f"Errore estrazione {filepath}: {e}")
            return None
    
    def extract_directory(
        self, 
        input_dir: Path, 
        limit: Optional[int] = None
    ) -> List[ExtractedDocument]:
        """
        Estrae tutti i PDF da una directory (ricorsivo)
        
        Args:
            input_dir: Directory con i PDF
            limit: Numero massimo di file da processare (opzionale)
            
        Returns:
            Lista di documenti estratti
        """
        input_path = Path(input_dir)
        pdf_files = list(input_path.rglob("*.pdf"))
        
        if limit:
            pdf_files = pdf_files[:limit]
        
        logger.info(f"Trovati {len(pdf_files)} file PDF in {input_dir}")
        
        documents = []
        for pdf_path in pdf_files:
            doc = self.extract_document(pdf_path)
            if doc:
                documents.append(doc)
        
        logger.info(f"Estratti con successo {len(documents)}/{len(pdf_files)} documenti")
        
        return documents


# Entry point per test
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        test_path = Path(sys.argv[1])
    else:
        test_path = Path("data/input_docs")
    
    extractor = PDFExtractor(config_path="config/config.yaml")
    
    if test_path.is_file():
        doc = extractor.extract_document(test_path)
        if doc:
            print(f"Documento: {doc.metadata.doc_id}")
            print(f"Titolo: {doc.metadata.title}")
            print(f"Pagine: {doc.metadata.page_count}")
            print(f"Sezioni: {doc.metadata.sections_found}")
            print(f"Caratteri: {doc.total_chars}")
    else:
        docs = extractor.extract_directory(test_path, limit=5)
        print(f"\nEstratti {len(docs)} documenti")
        for doc in docs[:5]:
            print(f"  - {doc.metadata.doc_id}: {doc.metadata.title}")

