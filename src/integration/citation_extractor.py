"""
Citation Extractor per OVV ISO Chat - R14
Estrae riferimenti documentali dal testo della risposta LLM

Pattern supportati:
- PS-06_01, IL-07_02, MR-08_03, TOOLS-10_01
- Varianti: PS06_01, PS-06-01, PS_06_01
- Menzioni testuali: "procedura PS-06_01", "documento IL-07"

Autore: OVV ISO Chat v3.2
Data: Dicembre 2025
"""

import re
import logging
from typing import Set, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CitationMatch:
    """Rappresenta una citazione trovata nel testo"""
    doc_id: str           # ID normalizzato (es. "PS-06_01")
    original_text: str    # Testo originale trovato (es. "PS06_01")
    position: int         # Posizione nel testo
    doc_type: str         # Tipo: PS, IL, MR, TOOLS, WO


def extract_cited_docs(text: str) -> Set[str]:
    """
    Estrae tutti i doc_id citati nel testo della risposta.
    
    Pattern riconosciuti:
    - PS-06_01, PS06_01, PS-06-01, PS_06_01
    - IL-07_02, IL07_02, IL-07-02
    - MR-08_03, MR08_03
    - TOOLS-10_01, TOOLS10_01
    - WO-07_01
    - LCS-07_01 (Linee Controllo Statistico)
    
    Args:
        text: Testo della risposta LLM
        
    Returns:
        Set di doc_id normalizzati (es. {"PS-06_01", "IL-07_02"})
        
    Example:
        >>> extract_cited_docs("Vedi PS-06_01 e anche IL07_02.")
        {"PS-06_01", "IL-07_02"}
    """
    # Pattern principale: TIPO-CAPITOLO_NUMERO
    # Supporta separatori: -, _, o nessuno tra capitolo e numero
    pattern = r'\b(PS|IL|MR|TOOLS|WO|LCS)[_\-]?(\d{2})[_\-]?(\d{2})\b'
    
    cited = set()
    
    for match in re.finditer(pattern, text, re.IGNORECASE):
        doc_type = match.group(1).upper()
        chapter = match.group(2)
        doc_num = match.group(3)
        
        # Normalizza formato: TIPO-CC_NN
        normalized = f"{doc_type}-{chapter}_{doc_num}"
        cited.add(normalized)
    
    return cited


def extract_cited_docs_detailed(text: str) -> List[CitationMatch]:
    """
    Versione dettagliata che ritorna anche posizione e testo originale.
    Utile per highlighting nel testo.
    
    Args:
        text: Testo della risposta LLM
        
    Returns:
        Lista di CitationMatch con dettagli
    """
    pattern = r'\b(PS|IL|MR|TOOLS|WO|LCS)[_\-]?(\d{2})[_\-]?(\d{2})\b'
    
    matches = []
    
    for match in re.finditer(pattern, text, re.IGNORECASE):
        doc_type = match.group(1).upper()
        chapter = match.group(2)
        doc_num = match.group(3)
        
        matches.append(CitationMatch(
            doc_id=f"{doc_type}-{chapter}_{doc_num}",
            original_text=match.group(0),
            position=match.start(),
            doc_type=doc_type
        ))
    
    return matches


def normalize_doc_id(doc_id: str) -> str:
    """
    Normalizza un doc_id in formato standard: TIPO-CC_NN
    
    Args:
        doc_id: ID in qualsiasi formato
        
    Returns:
        ID normalizzato
        
    Example:
        >>> normalize_doc_id("PS06_01")
        "PS-06_01"
        >>> normalize_doc_id("il-07-02")
        "IL-07_02"
    """
    # Rimuovi tutti i separatori
    clean = re.sub(r'[-_]', '', doc_id.upper())
    
    # Estrai componenti
    match = re.match(r'^(PS|IL|MR|TOOLS|WO|LCS)(\d{2})(\d{2})$', clean)
    
    if match:
        return f"{match.group(1)}-{match.group(2)}_{match.group(3)}"
    
    # Fallback: ritorna maiuscolo
    return doc_id.upper()


def match_doc_ids(
    cited_id: str, 
    source_id: str
) -> bool:
    """
    Verifica se un doc_id citato corrisponde a un doc_id delle sources.
    Gestisce variazioni nel formato.
    
    Args:
        cited_id: ID estratto dal testo
        source_id: ID dal payload delle sources
        
    Returns:
        True se corrispondono
        
    Example:
        >>> match_doc_ids("PS-06_01", "PS-06_01_Rev03")
        True
        >>> match_doc_ids("PS06_01", "PS-06_01")
        True
    """
    # Normalizza entrambi
    norm_cited = normalize_doc_id(cited_id)
    norm_source = normalize_doc_id(source_id)
    
    # Match esatto
    if norm_cited == norm_source:
        return True
    
    # Match parziale (source potrebbe avere suffisso come _Rev03)
    if norm_cited in norm_source or norm_source.startswith(norm_cited):
        return True
    
    # Match senza separatori
    cited_clean = re.sub(r'[-_]', '', norm_cited)
    source_clean = re.sub(r'[-_]', '', norm_source)
    
    if cited_clean in source_clean:
        return True
    
    return False


def detect_uncertainty_response(answer: str) -> bool:
    """
    Rileva se la risposta indica incertezza o mancanza di informazioni.
    
    Args:
        answer: Testo della risposta LLM
        
    Returns:
        True se la risposta indica incertezza
    """
    answer_lower = answer.lower()
    
    uncertainty_patterns = [
        "non ho informazioni",
        "non è presente nel contesto",
        "non ho trovato",
        "non posso rispondere",
        "non dispongo di",
        "informazioni non disponibili",
        "non sono in grado di",
        "non trovo riferimenti",
        "non è specificato",
        "non risulta"
    ]
    
    return any(pattern in answer_lower for pattern in uncertainty_patterns)


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    test_text = """
    La gestione dei rifiuti è descritta in PS-06_01 e nelle istruzioni IL06_02.
    Per la registrazione usa MR-06_01. Il tool TOOLS10_01 può aiutarti.
    Vedi anche LCS-07_01 per il controllo statistico.
    """
    
    print("Test extract_cited_docs:")
    cited = extract_cited_docs(test_text)
    print(f"  Found: {cited}")
    
    print("\nTest extract_cited_docs_detailed:")
    detailed = extract_cited_docs_detailed(test_text)
    for m in detailed:
        print(f"  {m.doc_id} at pos {m.position}: '{m.original_text}'")
    
    print("\nTest normalize_doc_id:")
    for test in ["PS06_01", "il-07-02", "MR_08_03", "TOOLS-10_01"]:
        print(f"  {test} → {normalize_doc_id(test)}")
    
    print("\nTest match_doc_ids:")
    print(f"  PS-06_01 vs PS-06_01_Rev03: {match_doc_ids('PS-06_01', 'PS-06_01_Rev03')}")
    print(f"  PS06_01 vs PS-06_01: {match_doc_ids('PS06_01', 'PS-06_01')}")
    
    print("\nTest detect_uncertainty_response:")
    print(f"  'Non ho informazioni...': {detect_uncertainty_response('Non ho informazioni su questo.')}")
    print(f"  'La procedura dice...': {detect_uncertainty_response('La procedura dice che...')}")

