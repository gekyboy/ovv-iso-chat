"""
Generazione entries tools_mapping.json
Combina dati da:
1. ps_mr_context.json (contesto MR dai PS)
2. document_metadata.json (campi MR estratti con pdfplumber)

Output: config/tools_mapping_extended.json (da mergiare manualmente)
"""

import json
from pathlib import Path
from typing import Dict, List, Set

# Directory
CONFIG_DIR = Path(__file__).parent.parent / "config"
PS_CONTEXT_PATH = CONFIG_DIR / "ps_mr_context.json"
DOC_METADATA_PATH = CONFIG_DIR / "document_metadata.json"
OUTPUT_PATH = CONFIG_DIR / "tools_mapping_extended.json"
EXISTING_MAPPING_PATH = CONFIG_DIR / "tools_mapping.json"

# Mappatura capitoli a temi (fallback se PS non ha keywords)
CHAPTER_THEMES = {
    "04": {
        "concepts": ["politica", "gestione", "sistema", "organizzazione", "direzione"],
        "keywords": ["politica aziendale", "sistema gestione", "organizzazione"]
    },
    "06": {
        "concepts": ["sicurezza", "ambiente", "infortunio", "rifiuti", "emissioni", "safety"],
        "keywords": ["infortunio", "near miss", "sicurezza", "rifiuti", "ambiente", "EWO"]
    },
    "07": {
        "concepts": ["risorse", "manutenzione", "taratura", "documenti", "formazione", "addestramento"],
        "keywords": ["manutenzione", "taratura", "strumenti", "formazione", "5S", "guasto"]
    },
    "08": {
        "concepts": ["qualità", "prodotto", "processo", "controllo", "fornitore", "conformità"],
        "keywords": ["qualità", "prodotto", "processo", "controllo", "fornitore", "NC", "FMEA"]
    },
    "09": {
        "concepts": ["audit", "verifica", "monitoraggio", "obiettivi", "performance"],
        "keywords": ["audit", "verifica", "ispezione", "obiettivi", "KPI", "riesame"]
    },
    "10": {
        "concepts": ["miglioramento", "kaizen", "problem solving", "azione correttiva"],
        "keywords": ["kaizen", "miglioramento", "problem solving", "5 perché", "Ishikawa"]
    }
}

# Priorità per capitolo
CHAPTER_PRIORITY = {
    "06": 1,  # Sicurezza = critico
    "10": 1,  # Kaizen = frequente
    "08": 2,  # Qualità = importante
    "07": 2,  # Manutenzione = importante  
    "09": 3,  # Audit = periodico
    "04": 4,  # Governance = raro
}


def normalize_mr_id(mr_id: str) -> str:
    """Normalizza ID MR al formato MR-XX_YY"""
    # Rimuovi spazi
    mr_id = mr_id.strip().upper()
    # Sostituisci -- con -
    mr_id = mr_id.replace("--", "-")
    # Pattern: MR-XX-YY o MR-XX_YY
    import re
    match = re.match(r'MR[-_]?(\d+)[-_](\d+)', mr_id)
    if match:
        return f"MR-{match.group(1).zfill(2)}_{match.group(2).zfill(2)}"
    return mr_id


def load_existing_mapping() -> Set[str]:
    """Carica doc_id già presenti in tools_mapping.json"""
    existing = set()
    if EXISTING_MAPPING_PATH.exists():
        with open(EXISTING_MAPPING_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for tool_data in data.get("tool_suggestions", {}).values():
                doc_id = tool_data.get("doc_id", "")
                existing.add(doc_id)
    return existing


def generate_tool_key(doc_id: str, name: str) -> str:
    """Genera chiave per tools_mapping"""
    # MR-06_01 + "Safety EWO" → "MR_06_01_Safety_EWO"
    key = doc_id.replace("-", "_")
    if name:
        name_clean = name.replace(" ", "_").replace("-", "_")[:25]
        key = f"{key}_{name_clean}"
    return key


def generate_suggest_when(mr_name: str, contesto: str, ps_titolo: str) -> str:
    """Genera la descrizione di quando usare il modulo"""
    if contesto and len(contesto) > 20:
        # Usa prima frase significativa del contesto
        # Pulisci contesto
        contesto_clean = contesto.replace("\n", " ").strip()
        # Trova una frase completa
        if "." in contesto_clean:
            frasi = contesto_clean.split(".")
            for frase in frasi:
                if len(frase) > 20:
                    return frase.strip()[:100]
    
    # Fallback basato su nome
    if mr_name:
        return f"Tabella per {mr_name} - Riferimento: {ps_titolo}"
    
    return f"Modulo di registrazione per {ps_titolo}"


def main():
    print("=" * 60)
    print("GENERAZIONE ENTRIES TOOLS_MAPPING")
    print("=" * 60)
    
    # Carica dati
    print("\n📂 Caricamento dati...")
    
    # 1. Contesto PS
    if not PS_CONTEXT_PATH.exists():
        print(f"❌ File non trovato: {PS_CONTEXT_PATH}")
        print("   Esegui prima: python scripts/extract_ps_context.py")
        return
    
    with open(PS_CONTEXT_PATH, 'r', encoding='utf-8') as f:
        ps_context = json.load(f)
    print(f"   PS context: {ps_context['metadata']['ps_count']} procedure")
    
    # 2. Document metadata
    if not DOC_METADATA_PATH.exists():
        print(f"❌ File non trovato: {DOC_METADATA_PATH}")
        return
    
    with open(DOC_METADATA_PATH, 'r', encoding='utf-8') as f:
        doc_metadata = json.load(f)
    mr_count = len(doc_metadata.get("moduli_registrazione", {}))
    tools_count = len(doc_metadata.get("tools", {}))
    print(f"   Document metadata: {mr_count} MR, {tools_count} TOOLS")
    
    # 3. Existing mapping
    existing_ids = load_existing_mapping()
    print(f"   Già mappati: {len(existing_ids)} tool")
    
    # Costruisci indice PS -> MR
    ps_to_mr = {}
    for ps_id, ps_data in ps_context.get("procedure", {}).items():
        for mr_id_raw in ps_data.get("mr_citati", {}).keys():
            mr_id = normalize_mr_id(mr_id_raw)
            if mr_id not in ps_to_mr:
                ps_to_mr[mr_id] = {
                    "ps_id": ps_id,
                    "ps_titolo": ps_data.get("titolo", ""),
                    "ps_keywords": ps_data.get("keywords_scopo", []),
                    "mr_data": ps_data["mr_citati"][mr_id_raw]
                }
    
    print(f"   MR con contesto PS: {len(ps_to_mr)}")
    
    # Genera entries
    print("\n🔧 Generazione entries...")
    new_entries = {}
    skipped = 0
    
    # Processa MR da document_metadata
    for mr_id, mr_meta in doc_metadata.get("moduli_registrazione", {}).items():
        mr_id_norm = normalize_mr_id(mr_id)
        
        # Skip se già mappato
        if mr_id_norm in existing_ids:
            skipped += 1
            continue
        
        # Estrai capitolo
        import re
        chap_match = re.search(r'MR-(\d+)', mr_id_norm)
        chapter = chap_match.group(1) if chap_match else "08"
        
        # Dati dal metadata
        mr_name = mr_meta.get("titolo", "")
        correlazioni = mr_meta.get("correlazioni", {})
        ps_padre = correlazioni.get("procedura_padre", "")
        
        # Dati dal contesto PS
        ps_info = ps_to_mr.get(mr_id_norm, {})
        contesto = ps_info.get("mr_data", {}).get("contesto", "")
        keywords_contesto = ps_info.get("mr_data", {}).get("keywords_contesto", [])
        ps_keywords = ps_info.get("ps_keywords", [])
        ps_titolo = ps_info.get("ps_titolo", "")
        
        # Se non c'è contesto PS, usa fallback da capitolo
        if not ps_keywords:
            ps_keywords = CHAPTER_THEMES.get(chapter, {}).get("concepts", [])
        if not keywords_contesto:
            keywords_contesto = CHAPTER_THEMES.get(chapter, {}).get("keywords", [])
        
        # Aggiungi keywords dal titolo MR
        if mr_name:
            title_words = mr_name.lower().replace("-", " ").replace("_", " ").split()
            for word in title_words:
                if len(word) > 3 and word not in keywords_contesto:
                    keywords_contesto.append(word)
        
        # Genera entry
        tool_key = generate_tool_key(mr_id_norm, mr_name)
        suggest_when = generate_suggest_when(mr_name, contesto, ps_titolo or ps_padre)
        
        entry = {
            "doc_id": mr_id_norm,
            "name": mr_name or mr_id_norm,
            "concepts": list(set(ps_keywords))[:10],
            "keywords": list(set(keywords_contesto))[:12],
            "suggest_when": suggest_when,
            "priority": CHAPTER_PRIORITY.get(chapter, 3),
            "related_ps": ps_padre or ps_info.get("ps_id", "")
        }
        
        new_entries[tool_key] = entry
    
    # Processa anche TOOLS
    for tool_id, tool_meta in doc_metadata.get("tools", {}).items():
        # Skip se già mappato (normalizza ID)
        tool_id_norm = tool_id.replace("-", "_").upper()
        if any(tool_id_norm in existing for existing in existing_ids):
            skipped += 1
            continue
        
        tool_name = tool_meta.get("titolo", tool_id)
        
        # Keywords dai tools correlati + nome
        keywords = []
        if tool_name:
            keywords = tool_name.lower().replace("-", " ").replace("_", " ").split()
        
        tool_key = f"TOOLS_{tool_id_norm}_{tool_name[:20].replace(' ', '_')}"
        
        entry = {
            "doc_id": tool_id,
            "name": tool_name,
            "concepts": ["strumento", "tool", "analisi"],
            "keywords": [kw for kw in keywords if len(kw) > 3][:10],
            "suggest_when": f"Tool: {tool_name}",
            "priority": 2
        }
        
        new_entries[tool_key] = entry
    
    print(f"   Nuove entries generate: {len(new_entries)}")
    print(f"   Skippate (già esistenti): {skipped}")
    
    # Salva output
    output_data = {
        "metadata": {
            "note": "Merge manualmente in tools_mapping.json nella sezione tool_suggestions",
            "entries_count": len(new_entries),
            "source": "generate_tools_mapping.py"
        },
        "tool_suggestions": new_entries
    }
    
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Salvato: {OUTPUT_PATH}")
    
    # Preview
    print("\n📋 PREVIEW (prime 5 entries):")
    for key, entry in list(new_entries.items())[:5]:
        print(f"\n  {key}:")
        print(f"    doc_id: {entry['doc_id']}")
        print(f"    name: {entry['name']}")
        print(f"    concepts: {entry['concepts'][:5]}")
        print(f"    keywords: {entry['keywords'][:5]}")
        print(f"    related_ps: {entry.get('related_ps', '')}")


if __name__ == "__main__":
    main()

