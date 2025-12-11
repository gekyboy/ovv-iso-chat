"""
Estrazione contesto MR dalle Procedure Sistema (PS)
Per suggerimenti moduli intelligenti - R15 Enhanced

Estrae:
1. Titolo e scopo di ogni PS
2. MR citati con contesto d'uso
3. Keywords dalle sezioni SCOPO e MODALITA' OPERATIVE

Output: config/ps_mr_context.json
"""

import pdfplumber
import json
import re
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict

# Directory base
BASE_DIR = Path(__file__).parent.parent.parent  # D:\.ISO_OVV
PROCEDURE_DIR = BASE_DIR / "procedure sistema"
OUTPUT_PATH = Path(__file__).parent.parent / "config" / "ps_mr_context.json"

# Stopwords italiane da escludere dalle keywords
STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
    "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
    "che", "e", "o", "ma", "se", "non", "come", "quale", "quanto",
    "questo", "quello", "suo", "loro", "ogni", "tutti", "tutto",
    "essere", "avere", "fare", "dire", "potere", "dovere", "volere",
    "del", "della", "dei", "delle", "al", "alla", "ai", "alle",
    "dal", "dalla", "nel", "nella", "sul", "sulla", "col",
    "sono", "è", "sia", "sono", "viene", "vengono", "viene",
    "deve", "devono", "può", "possono", "deve", "devono",
    "anche", "quindi", "inoltre", "pertanto", "ovvero", "oppure",
    "mediante", "attraverso", "secondo", "durante", "entro",
    "presente", "seguente", "relativo", "relativa", "relativi",
    "caso", "casi", "modo", "fine", "base", "punto", "parte",
}


def extract_keywords(text: str, min_len: int = 4, max_words: int = 15) -> List[str]:
    """Estrae parole chiave significative dal testo"""
    # Pulisci e normalizza
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Split e filtra
    words = text.split()
    keywords = []
    
    for word in words:
        if len(word) >= min_len and word not in STOPWORDS:
            # Evita numeri puri
            if not word.isdigit():
                keywords.append(word)
    
    # Rimuovi duplicati mantenendo ordine
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    
    return unique[:max_words]


def extract_section(text: str, section_name: str, max_chars: int = 1000) -> str:
    """Estrae una sezione specifica dal testo del PS"""
    # Pattern per trovare la sezione
    pattern = rf'{section_name}[:\s]*\n(.*?)(?=\n\d+\)|$)'
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    
    if match:
        content = match.group(1).strip()
        return content[:max_chars]
    
    return ""


def find_mr_mentions(text: str) -> Dict[str, Dict]:
    """Trova tutti gli MR citati nel testo con il loro contesto"""
    mr_mentions = {}
    
    # Pattern per trovare MR-XX_YY con possibile nome
    # Esempi: "MR-06_01 Safety EWO", "MR-06_01_u.r.", "MR-07_05 Cartellino anomalia"
    pattern = r'(MR[-_]?\d+[-_]?\d+)[\s_]*(?:u\.r\.|_u\.r\.)?[\s,]*([A-Za-z][A-Za-z\s\-]+)?'
    
    for match in re.finditer(pattern, text, re.IGNORECASE):
        mr_id_raw = match.group(1)
        mr_name = match.group(2)
        
        # Normalizza MR ID
        mr_id = re.sub(r'[-_]', '-', mr_id_raw).upper()
        mr_id = re.sub(r'MR(\d)', r'MR-\1', mr_id)  # MR06 -> MR-06
        
        # Pulisci nome
        if mr_name:
            mr_name = mr_name.strip().rstrip('.')
            # Evita nomi che sono solo articoli o preposizioni
            if len(mr_name) < 3 or mr_name.lower() in STOPWORDS:
                mr_name = None
        
        # Estrai contesto (100 caratteri prima e dopo)
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        context = text[start:end].strip()
        context = re.sub(r'\s+', ' ', context)  # Normalizza spazi
        
        # Estrai keywords dal contesto
        context_keywords = extract_keywords(context, min_len=4, max_words=8)
        
        # Aggiungi o aggiorna
        if mr_id not in mr_mentions:
            mr_mentions[mr_id] = {
                "nome": mr_name or "",
                "contesto": context,
                "keywords_contesto": context_keywords,
                "occorrenze": 1
            }
        else:
            mr_mentions[mr_id]["occorrenze"] += 1
            # Aggiorna nome se trovato
            if mr_name and not mr_mentions[mr_id]["nome"]:
                mr_mentions[mr_id]["nome"] = mr_name
            # Aggiungi keywords uniche
            existing = set(mr_mentions[mr_id]["keywords_contesto"])
            for kw in context_keywords:
                if kw not in existing:
                    mr_mentions[mr_id]["keywords_contesto"].append(kw)
    
    return mr_mentions


def process_ps_file(pdf_path: Path) -> Dict:
    """Processa un singolo file PS"""
    result = {
        "filepath": str(pdf_path),
        "titolo": "",
        "scopo": "",
        "keywords_scopo": [],
        "mr_citati": {}
    }
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text() or ""
                full_text += text + "\n"
            
            # Estrai titolo (prima riga dopo "Titolo procedura:")
            title_match = re.search(r'Titolo procedura[:\s]*\n?([^\n]+)', full_text, re.IGNORECASE)
            if title_match:
                result["titolo"] = title_match.group(1).strip()
            else:
                # Fallback: usa nome file
                result["titolo"] = pdf_path.stem.replace("_", " ")
            
            # Estrai sezione SCOPO
            scopo = extract_section(full_text, "SCOPO E GENERALIT[ÀA']?", max_chars=800)
            if not scopo:
                scopo = extract_section(full_text, "SCOPO", max_chars=800)
            result["scopo"] = scopo
            
            # Estrai keywords dallo scopo
            result["keywords_scopo"] = extract_keywords(scopo, min_len=4, max_words=15)
            
            # Estrai anche keywords da MODALITA' OPERATIVE
            modalita = extract_section(full_text, "MODALIT[ÀA']'? OPERATIVE", max_chars=1500)
            modalita_keywords = extract_keywords(modalita, min_len=4, max_words=10)
            
            # Merge keywords (scopo ha priorità)
            existing = set(result["keywords_scopo"])
            for kw in modalita_keywords:
                if kw not in existing:
                    result["keywords_scopo"].append(kw)
            
            # Trova MR citati
            result["mr_citati"] = find_mr_mentions(full_text)
            
    except Exception as e:
        print(f"  ERRORE: {e}")
    
    return result


def find_all_ps_files() -> List[Path]:
    """Trova tutti i file PS nelle procedure sistema"""
    ps_files = []
    
    for cap_dir in PROCEDURE_DIR.iterdir():
        if cap_dir.is_dir() and cap_dir.name.startswith("Cap"):
            # Cerca in sottodirectory "Procedure Sistema_*"
            for sub_dir in cap_dir.iterdir():
                if sub_dir.is_dir() and "Procedure" in sub_dir.name:
                    for pdf in sub_dir.glob("PS-*.pdf"):
                        ps_files.append(pdf)
    
    return sorted(ps_files)


def main():
    print("=" * 60)
    print("ESTRAZIONE CONTESTO MR DALLE PROCEDURE SISTEMA")
    print("=" * 60)
    
    # Trova tutti i PS
    ps_files = find_all_ps_files()
    print(f"\nTrovati {len(ps_files)} file PS")
    
    # Processa ogni PS
    results = {}
    total_mr = set()
    
    for ps_path in ps_files:
        # Estrai ID dal filename
        filename = ps_path.stem
        match = re.match(r'(PS-\d+_\d+)', filename)
        ps_id = match.group(1) if match else filename[:10]
        
        print(f"\n[+] {ps_id}: {ps_path.name[:50]}")
        
        ps_data = process_ps_file(ps_path)
        results[ps_id] = ps_data
        
        # Conta MR trovati
        mr_count = len(ps_data["mr_citati"])
        total_mr.update(ps_data["mr_citati"].keys())
        
        print(f"    Titolo: {ps_data['titolo'][:50]}")
        print(f"    Keywords: {len(ps_data['keywords_scopo'])}")
        print(f"    MR citati: {mr_count}")
        
        if mr_count > 0:
            for mr_id, mr_data in list(ps_data["mr_citati"].items())[:3]:
                nome = mr_data.get("nome", "")
                print(f"      - {mr_id}: {nome[:30]}")
    
    # Salva risultati
    output_data = {
        "metadata": {
            "ps_count": len(results),
            "mr_unique_count": len(total_mr),
            "source": "procedure sistema"
        },
        "procedure": results
    }
    
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print(f"✅ Salvato: {OUTPUT_PATH}")
    print(f"   PS processati: {len(results)}")
    print(f"   MR unici trovati: {len(total_mr)}")
    print("=" * 60)
    
    # Preview MR per PS
    print("\n📊 RIEPILOGO MR PER PROCEDURA:")
    for ps_id, ps_data in results.items():
        if ps_data["mr_citati"]:
            print(f"  {ps_id}: {list(ps_data['mr_citati'].keys())[:5]}")


if __name__ == "__main__":
    main()

