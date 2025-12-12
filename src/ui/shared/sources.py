"""
UI-agnostic Sources Logic
Logica per gestire fonti citate, previews e PDF - estratta da Chainlit
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

def filter_cited_sources(
    answer: str,
    sources: List
) -> Tuple[List, List[str]]:
    """
    Filtra le sources mantenendo SOLO quelle effettivamente citate nel testo.

    Args:
        answer: Testo della risposta LLM
        sources: Lista completa delle sources dal retrieval

    Returns:
        Tuple di:
        - Lista sources filtrate (solo quelle citate)
        - Lista doc_id citati nel testo ma non trovati nelle sources
    """
    from src.integration.citation_extractor import (
        extract_cited_docs,
        match_doc_ids,
        normalize_doc_id
    )

    # 1. Estrai doc_id citati nel testo
    cited_doc_ids = extract_cited_docs(answer)

    if not cited_doc_ids:
        return [], []

    # 2. Filtra sources che matchano
    cited_sources = []
    found_ids = set()

    for source in sources:
        source_id = source.doc_id

        for cited_id in cited_doc_ids:
            if match_doc_ids(cited_id, source_id):
                if source_id not in found_ids:  # Evita duplicati
                    cited_sources.append(source)
                    found_ids.add(source_id)
                break

    # 3. Identifica citazioni non trovate (possibili allucinazioni)
    normalized_found = {normalize_doc_id(s.doc_id) for s in cited_sources}
    missing = [
        cid for cid in cited_doc_ids
        if normalize_doc_id(cid) not in normalized_found
    ]

    if missing:
        logger.warning(f"[filter_cited_sources] Citazioni non trovate: {missing}")

    logger.info(f"[filter_cited_sources] {len(cited_sources)}/{len(sources)} sources filtrate")
    return cited_sources, missing


def find_pdf_by_doc_id(doc_id: str, pdf_dir: str = "data/input_docs") -> Optional[Path]:
    """
    Trova il file PDF corrispondente a un doc_id.

    Logica di matching:
    1. Cerca file che inizia con doc_id (es. "PS-06_01" -> "PS-06_01_Rev.04_...")
    2. Normalizza separatori ("-" vs "_") per match robusto

    Args:
        doc_id: ID documento (es. "PS-06_01", "IL-06_02")
        pdf_dir: Directory dove cercare i PDF

    Returns:
        Path al PDF o None se non trovato

    Examples:
        >>> find_pdf_by_doc_id("PS-06_01")
        Path("data/input_docs/PS-06_01_Rev.04_Gestione della sicurezza....pdf")
    """
    pdf_path = Path(pdf_dir)
    if not pdf_path.exists():
        logger.warning(f"[find_pdf_by_doc_id] Directory PDF non esiste: {pdf_dir}")
        return None

    # Normalizza doc_id per ricerca
    normalized_doc_id = doc_id.replace("-", "_")

    # Cerca file che inizia con il doc_id (con o senza normalizzazione)
    for pdf_file in pdf_path.glob("*.pdf"):
        pdf_name = pdf_file.stem.lower()

        # Match diretto
        if pdf_name.startswith(doc_id.lower()) or pdf_name.startswith(normalized_doc_id.lower()):
            logger.debug(f"[find_pdf_by_doc_id] Trovato: {doc_id} -> {pdf_file.name}")
            return pdf_file

    logger.warning(f"[find_pdf_by_doc_id] PDF non trovato per: {doc_id}")
    return None


def prepare_source_data(
    sources: List,
    max_preview_chars: int = 800
) -> List[Dict[str, Any]]:
    """
    Prepara dati delle fonti per l'UI (Chainlit/Mesop-agnostic).

    Args:
        sources: Lista sources filtrate (solo quelle citate)
        max_preview_chars: Massimo caratteri per anteprima

    Returns:
        Lista di dict con:
        - doc_id: ID documento
        - title: Titolo leggibile
        - preview: Anteprima testo troncata
        - score: Score di rilevanza
        - pdf_path: Path al PDF (se esiste)
        - pdf_filename: Nome del PDF
    """
    source_data = []
    seen_pdfs = set()  # Evita duplicati PDF

    for source in sources:
        # Estrai info
        doc_id = source.doc_id
        score = getattr(source, 'rerank_score', None) or getattr(source, 'score', 0)
        text = source.text or ""

        # Titolo leggibile dal metadata
        title = source.metadata.get("title", "")
        if not title or title == doc_id:
            title = doc_id  # Fallback

        # Prepara anteprima testo
        preview = text[:max_preview_chars]
        if len(text) > max_preview_chars:
            preview += "\n\n[... testo troncato ...]"

        # Trova PDF
        pdf_path = None
        pdf_filename = None
        if doc_id not in seen_pdfs:
            pdf_path_obj = find_pdf_by_doc_id(doc_id)
            if pdf_path_obj and pdf_path_obj.exists():
                pdf_path = str(pdf_path_obj)
                pdf_filename = pdf_path_obj.stem
                seen_pdfs.add(doc_id)

        # Crea dict per l'UI
        source_dict = {
            "doc_id": doc_id,
            "title": title,
            "preview": preview,
            "score": score,
            "pdf_path": pdf_path,
            "pdf_filename": pdf_filename,
        }

        source_data.append(source_dict)

    logger.info(f"[prepare_source_data] Preparati {len(source_data)} elementi fonte")
    return source_data


def format_sources_summary(cited_sources: List[Dict[str, Any]]) -> str:
    """
    Formatta un summary delle fonti citate per l'UI.

    Args:
        cited_sources: Lista di dict da prepare_source_data

    Returns:
        String formattato con summary delle fonti
    """
    if not cited_sources:
        return "Nessuna fonte citata."

    lines = ["📚 **Fonti consultate**:"]
    for i, source in enumerate(cited_sources, 1):
        title = source["title"]
        doc_id = source["doc_id"]
        score = source["score"]

        line = f"{i}. **{title}** ({doc_id}) - Rilevanza: {score:.0%}"
        lines.append(line)

    return "\n".join(lines)
