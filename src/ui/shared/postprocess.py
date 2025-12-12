"""
UI-agnostic Post-processing Logic
Logica per cleanup risposte LLM - estratta da Chainlit
"""

import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def remove_llm_references_section(answer: str) -> str:
    """
    Rimuove la sezione "Riferimenti:" generata dall'LLM.

    Il sistema aggiunge le fonti automaticamente nel footer,
    quindi la sezione generata dall'LLM è ridondante.

    Args:
        answer: Risposta LLM originale

    Returns:
        Risposta senza sezione riferimenti
    """
    # Pattern per rimuovere sezione riferimenti
    patterns = [
        r'\n*\*?\*?Riferimenti:?\*?\*?\s*\n[-•*\s]*[A-Z]{2,5}-?\d{2}[_-]?\d{2}.*?(?=\n\n|\n---|\Z)',
        r'\n*\*?\*?Fonti:?\*?\*?\s*\n[-•*\s]*[A-Z]{2,5}-?\d{2}[_-]?\d{2}.*?(?=\n\n|\n---|\Z)',
        r'\n*\*?\*?Documenti citati:?\*?\*?\s*\n.*?(?=\n\n|\n---|\Z)',
        r'\n*\*?\*?Riferimenti\s+normativi:?\*?\*?\s*\n.*?(?=\n\n|\n---|\Z)',
    ]

    cleaned = answer
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.DOTALL)

    # Rimuovi anche liste di doc_id alla fine
    cleaned = re.sub(r'\n+[-•*]\s*[A-Z]{2,5}-\d{2}[_-]\d{2}\s*\n*$', '', cleaned)

    return cleaned.strip()


def replace_doc_ids_with_titles(
    answer: str,
    sources: List
) -> str:
    """
    Sostituisce i doc_id nel testo con i titoli leggibili tra virgolette.

    Args:
        answer: Testo della risposta
        sources: Lista delle sources disponibili

    Returns:
        Testo con titoli invece di doc_id
    """
    # Costruisci mapping doc_id -> title
    doc_mapping = {}
    for source in sources:
        doc_id = source.doc_id
        title = source.metadata.get("title", "")
        if title and title != doc_id:
            doc_mapping[doc_id] = title

    if not doc_mapping:
        return answer

    # Sostituisci nel testo (dal più lungo al più corto per evitare conflitti)
    result = answer
    for doc_id, title in sorted(doc_mapping.items(), key=lambda x: len(x[0]), reverse=True):
        # Pattern per matchare doc_id con confini di parola
        pattern = r'\b' + re.escape(doc_id) + r'\b'
        result = re.sub(pattern, f'"{title}"', result)

    logger.debug(f"[replace_doc_ids_with_titles] Sostituiti {len(doc_mapping)} doc_id con titoli")
    return result


def cleanup_llm_response(
    answer: str,
    sources: List = None,
    remove_references: bool = True,
    replace_ids_with_titles: bool = True
) -> str:
    """
    Pipeline completa di post-processing per risposte LLM.

    Args:
        answer: Risposta LLM originale
        sources: Lista sources per sostituzione titoli (opzionale)
        remove_references: Se rimuovere sezione riferimenti
        replace_ids_with_titles: Se sostituire doc_id con titoli

    Returns:
        Risposta pulita e formattata
    """
    cleaned = answer

    # 1. Rimuovi sezione riferimenti se richiesta
    if remove_references:
        cleaned = remove_llm_references_section(cleaned)

    # 2. Sostituisci doc_id con titoli se sources disponibili
    if replace_ids_with_titles and sources:
        cleaned = replace_doc_ids_with_titles(cleaned, sources)

    # 3. Cleanup finale: rimuovi spazi extra
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)  # Max 2 newline
    cleaned = cleaned.strip()

    if cleaned != answer:
        logger.debug(f"[cleanup_llm_response] Risposta pulita: {len(answer)} -> {len(cleaned)} caratteri")

    return cleaned


def extract_response_quality_metrics(answer: str) -> Dict[str, Any]:
    """
    Estrae metriche di qualità dalla risposta per analytics.

    Args:
        answer: Risposta LLM

    Returns:
        Dict con metriche: length, has_sources, has_structure, etc.
    """
    metrics = {
        "length": len(answer),
        "word_count": len(answer.split()),
        "has_sources": bool(re.search(r'[A-Z]{2,5}-\d{2}[_-]\d{2}', answer)),
        "has_bullet_points": bool(re.search(r'[-•*]\s+', answer)),
        "has_numbering": bool(re.search(r'\d+\.\s+', answer)),
        "has_headers": bool(re.search(r'#{1,6}\s+', answer)),
        "has_tables": bool(re.search(r'\|.*\|.*\|', answer)),
    }

    return metrics
