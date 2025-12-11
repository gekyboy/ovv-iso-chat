"""
Script per generare/arricchire semantic_metadata.json dai PDF
Analizza i documenti MR/TOOLS e suggerisce classificazioni semantiche

Usage:
    python -m scripts.generate_semantic_metadata --analyze
    python -m scripts.generate_semantic_metadata --update
"""

import json
import re
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import pdfplumber
except ImportError:
    print("Installare pdfplumber: pip install pdfplumber")
    exit(1)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
SEMANTIC_METADATA_PATH = PROJECT_ROOT / "config" / "semantic_metadata.json"
PROCEDURE_SISTEMA_PATH = Path(r"D:\.ISO_OVV\procedure sistema")

# Classification rules
CLASSIFICATION_RULES = {
    "real_injury": {
        "patterns": [
            r"infortunio",
            r"lesion[ei]",
            r"ferit[ao]",
            r"safety ewo",
            r"analisi causa radice.*infortunio",
            r"incidente con lesion"
        ],
        "exclude": [
            r"near miss",
            r"mancato",
            r"quasi incidente",
            r"senza lesion"
        ],
        "title_patterns": ["Safety EWO", "Infortunio"]
    },
    "near_miss": {
        "patterns": [
            r"near miss",
            r"mancato infortunio",
            r"quasi incidente",
            r"unsafe condition",
            r"unsafe act",
            r"condizion[ei] pericolos[ae]",
            r"azion[ei] pericolos[ae]"
        ],
        "exclude": [
            r"lesion[ei]",
            r"ferit[ao]"
        ],
        "title_patterns": ["Near Miss", "Unsafe"]
    },
    "environmental": {
        "patterns": [
            r"ambient[ei]",
            r"environmental",
            r"sversamento",
            r"emission[ei]",
            r"rifiut[io]",
            r"inquinamento"
        ],
        "exclude": [],
        "title_patterns": ["Environmental", "Ambiente", "Emissioni", "Rifiuti"]
    },
    "non_conformity": {
        "patterns": [
            r"non conformit[àa]",
            r"\bNC\b",
            r"reclamo",
            r"difett[oi]",
            r"scarto",
            r"prodotto non conforme"
        ],
        "exclude": [],
        "title_patterns": ["Non Conformit", "Reclamo", "8D"]
    },
    "kaizen": {
        "patterns": [
            r"kaizen",
            r"miglioramento",
            r"ottimizzazione",
            r"riduzione sprechi",
            r"\bWCM\b"
        ],
        "exclude": [],
        "title_patterns": ["Kaizen", "Miglioramento"]
    },
    "quality_control": {
        "patterns": [
            r"controllo.*prodotto",
            r"qualit[àa]",
            r"ispezione",
            r"collaudo",
            r"verifica.*prodotto"
        ],
        "exclude": [],
        "title_patterns": ["Controllo", "Qualità", "Ispezione"]
    }
}

# Applies_when suggestions per categoria
APPLIES_WHEN_TEMPLATES = {
    "real_injury": [
        "ho avuto un infortunio",
        "mi sono fatto male",
        "lesione sul lavoro",
        "ferito",
        "infortunio grave",
        "infortunio lieve",
        "incidente con lesione"
    ],
    "near_miss": [
        "near miss",
        "mancato infortunio",
        "quasi incidente",
        "condizione pericolosa",
        "per poco",
        "poteva andare male"
    ],
    "environmental": [
        "incidente ambientale",
        "sversamento",
        "emissioni anomale",
        "rifiuti pericolosi"
    ],
    "non_conformity": [
        "non conformità",
        "prodotto difettoso",
        "reclamo cliente",
        "scarto"
    ],
    "kaizen": [
        "kaizen",
        "miglioramento",
        "ottimizzazione",
        "proposta miglioramento"
    ],
    "quality_control": [
        "controllo qualità",
        "ispezione",
        "collaudo"
    ]
}

# Not_for suggestions per categoria
NOT_FOR_TEMPLATES = {
    "real_injury": ["near miss", "mancato infortunio", "senza lesioni"],
    "near_miss": ["infortunio", "lesione", "ferito"],
    "environmental": ["infortunio personale"],
    "non_conformity": ["infortunio", "near miss"],
    "kaizen": [],
    "quality_control": []
}


def extract_doc_id(filename: str) -> Optional[str]:
    """Estrae doc_id dal nome file (es. MR-06_01)"""
    match = re.search(r'(MR|TOOLS|IL|PS)-?(\d{2})[-_](\d{2})', filename, re.IGNORECASE)
    if match:
        doc_type = match.group(1).upper()
        chapter = match.group(2)
        number = match.group(3)
        return f"{doc_type}-{chapter}_{number}"
    return None


def extract_title(text: str, filename: str) -> str:
    """Estrae titolo dal testo o filename"""
    # Cerca pattern titolo nel testo
    patterns = [
        r'Titolo\s*(?:procedura)?[:\s]+([^\n]+)',
        r'^([A-Z][^.:\n]{10,50})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text[:500], re.MULTILINE | re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            if len(title) > 5 and len(title) < 100:
                return title
    
    # Fallback: usa filename
    parts = filename.replace('.pdf', '').split('_')
    if len(parts) > 2:
        return ' '.join(parts[2:])
    return filename


def classify_document(text: str, title: str) -> Tuple[str, float]:
    """
    Classifica documento in una categoria semantica.
    
    Returns:
        (category, confidence)
    """
    text_lower = text.lower()
    title_lower = title.lower()
    
    scores = {}
    
    for category, rules in CLASSIFICATION_RULES.items():
        score = 0.0
        
        # Match patterns nel testo
        for pattern in rules["patterns"]:
            matches = len(re.findall(pattern, text_lower))
            score += matches * 0.1
        
        # Match patterns nel titolo (peso maggiore)
        for pattern in rules.get("title_patterns", []):
            if pattern.lower() in title_lower:
                score += 2.0
        
        # Penalizza se match exclude patterns
        for exclude in rules["exclude"]:
            if re.search(exclude, text_lower):
                score -= 1.0
        
        scores[category] = max(0, score)
    
    if not scores or max(scores.values()) == 0:
        return "general", 0.0
    
    best_category = max(scores, key=scores.get)
    confidence = min(1.0, scores[best_category] / 5.0)
    
    return best_category, confidence


def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """Estrae keywords rilevanti dal testo"""
    # Pattern per parole significative
    words = re.findall(r'\b[A-Za-zÀ-ÿ]{4,15}\b', text)
    
    # Conta frequenze
    freq = {}
    stopwords = {
        'della', 'delle', 'degli', 'dello', 'nella', 'nelle', 'negli', 'nello',
        'questo', 'questa', 'questi', 'queste', 'quello', 'quella', 'quelli',
        'sono', 'essere', 'stato', 'stata', 'stati', 'state', 'viene', 'vengono',
        'fare', 'fatto', 'fatta', 'fatti', 'fatte', 'deve', 'devono', 'possono',
        'ogni', 'altro', 'altra', 'altri', 'altre', 'dove', 'come', 'quando',
        'perché', 'quindi', 'anche', 'solo', 'dopo', 'prima', 'ancora'
    }
    
    for word in words:
        word_lower = word.lower()
        if word_lower not in stopwords:
            freq[word_lower] = freq.get(word_lower, 0) + 1
    
    # Top keywords
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_keywords]]


def analyze_pdf(pdf_path: Path) -> Optional[Dict]:
    """Analizza un singolo PDF e genera metadata"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages[:3]:  # Prime 3 pagine
                page_text = page.extract_text() or ""
                text += page_text + "\n"
        
        if len(text) < 50:
            return None
        
        doc_id = extract_doc_id(pdf_path.name)
        if not doc_id:
            return None
        
        title = extract_title(text, pdf_path.name)
        category, confidence = classify_document(text, title)
        keywords = extract_keywords(text)
        
        return {
            "doc_id": doc_id,
            "title": title,
            "filepath": str(pdf_path),
            "incident_category": category,
            "classification_confidence": confidence,
            "applies_when": APPLIES_WHEN_TEMPLATES.get(category, []),
            "not_for": NOT_FOR_TEMPLATES.get(category, []),
            "related_keywords": keywords,
            "text_preview": text[:300]
        }
        
    except Exception as e:
        logger.error(f"Errore analisi {pdf_path.name}: {e}")
        return None


def find_mr_tools_pdfs() -> List[Path]:
    """Trova tutti i PDF MR e TOOLS"""
    pdfs = []
    
    if not PROCEDURE_SISTEMA_PATH.exists():
        logger.error(f"Path non trovato: {PROCEDURE_SISTEMA_PATH}")
        return pdfs
    
    for pattern in ["**/MR-*.pdf", "**/MR_*.pdf", "**/TOOLS-*.pdf", "**/*_Rev*.pdf"]:
        for pdf_path in PROCEDURE_SISTEMA_PATH.glob(pattern):
            if "MR-" in pdf_path.name or "MR_" in pdf_path.name:
                pdfs.append(pdf_path)
            elif "TOOLS" in pdf_path.name.upper():
                pdfs.append(pdf_path)
    
    # Deduplica
    return list(set(pdfs))


def analyze_all_documents() -> Dict:
    """Analizza tutti i documenti MR/TOOLS"""
    pdfs = find_mr_tools_pdfs()
    logger.info(f"Trovati {len(pdfs)} PDF da analizzare")
    
    results = {
        "analyzed": [],
        "by_category": {},
        "failed": []
    }
    
    for pdf_path in pdfs:
        logger.info(f"Analisi: {pdf_path.name}")
        metadata = analyze_pdf(pdf_path)
        
        if metadata:
            results["analyzed"].append(metadata)
            cat = metadata["incident_category"]
            if cat not in results["by_category"]:
                results["by_category"][cat] = []
            results["by_category"][cat].append(metadata["doc_id"])
        else:
            results["failed"].append(str(pdf_path))
    
    return results


def update_semantic_metadata(analysis_results: Dict):
    """Aggiorna semantic_metadata.json con nuove analisi"""
    # Carica esistente
    existing = {}
    if SEMANTIC_METADATA_PATH.exists():
        with open(SEMANTIC_METADATA_PATH, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    
    documents = existing.get("documents", {})
    
    # Aggiorna con nuove analisi
    for doc_meta in analysis_results["analyzed"]:
        doc_id = doc_meta["doc_id"]
        
        if doc_id not in documents:
            # Nuovo documento
            documents[doc_id] = {
                "doc_id": doc_id,
                "title": doc_meta["title"],
                "semantic_type": doc_meta["incident_category"],
                "incident_category": doc_meta["incident_category"],
                "applies_when": doc_meta["applies_when"],
                "not_for": doc_meta["not_for"],
                "related_keywords": doc_meta["related_keywords"],
                "auto_classified": True,
                "classification_confidence": doc_meta["classification_confidence"]
            }
            logger.info(f"  + Aggiunto: {doc_id} ({doc_meta['incident_category']})")
        else:
            # Documento esistente - aggiorna solo se auto_classified
            if documents[doc_id].get("auto_classified", False):
                documents[doc_id]["related_keywords"] = doc_meta["related_keywords"]
                logger.info(f"  ~ Aggiornato keywords: {doc_id}")
    
    # Salva
    existing["documents"] = documents
    
    with open(SEMANTIC_METADATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Salvato: {SEMANTIC_METADATA_PATH}")


def print_analysis_report(results: Dict):
    """Stampa report analisi"""
    print("\n" + "=" * 70)
    print("REPORT ANALISI DOCUMENTI")
    print("=" * 70)
    
    print(f"\nDocumenti analizzati: {len(results['analyzed'])}")
    print(f"Documenti falliti: {len(results['failed'])}")
    
    print("\n--- PER CATEGORIA ---")
    for cat, doc_ids in sorted(results["by_category"].items()):
        print(f"\n{cat.upper()} ({len(doc_ids)} documenti):")
        for doc_id in doc_ids[:5]:
            print(f"  - {doc_id}")
        if len(doc_ids) > 5:
            print(f"  ... e altri {len(doc_ids) - 5}")
    
    print("\n--- DOCUMENTI FALLITI ---")
    for path in results["failed"][:10]:
        print(f"  - {Path(path).name}")


def main():
    parser = argparse.ArgumentParser(description="Genera/aggiorna semantic metadata")
    parser.add_argument("--analyze", action="store_true", help="Solo analisi (no update)")
    parser.add_argument("--update", action="store_true", help="Analizza e aggiorna JSON")
    
    args = parser.parse_args()
    
    if not args.analyze and not args.update:
        args.analyze = True  # Default
    
    results = analyze_all_documents()
    print_analysis_report(results)
    
    if args.update:
        update_semantic_metadata(results)


if __name__ == "__main__":
    main()


