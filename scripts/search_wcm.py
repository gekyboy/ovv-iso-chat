"""
Script per cercare WCM nei PDF e confrontare con chunks indicizzati
"""
import pdfplumber
from pathlib import Path
import re
from qdrant_client import QdrantClient

def search_pdf():
    """Cerca WCM nei PDF originali"""
    input_dir = Path('data/input_docs')
    print('=' * 60)
    print('RICERCA WCM NEI PDF ORIGINALI (PS/IL)')
    print('=' * 60)
    print()
    
    results = []
    
    for pdf_file in sorted(input_dir.glob('*.pdf')):
        fn = pdf_file.name
        if not (fn.startswith('PS-') or fn.startswith('IL-')):
            continue
        try:
            with pdfplumber.open(pdf_file) as pdf:
                text = ''
                for p in pdf.pages:
                    text += (p.extract_text() or '') + ' '
                if 'wcm' in text.lower():
                    count = text.lower().count('wcm')
                    matches = re.findall(r'.{0,50}wcm.{0,50}', text, re.IGNORECASE)[:3]
                    results.append({
                        'file': fn,
                        'count': count,
                        'samples': matches
                    })
        except Exception as e:
            print(f'Errore {fn}: {e}')
    
    print(f'Trovato WCM in {len(results)} documenti PS/IL:')
    print()
    
    for r in results:
        print(f"[{r['file']}] {r['count']} occorrenze")
        for m in r['samples']:
            clean = ' '.join(m.split())[:100]
            print(f"  -> {clean}")
        print()
    
    return results


def search_qdrant():
    """Cerca WCM nei chunks indicizzati"""
    print()
    print('=' * 60)
    print('RICERCA WCM NEI CHUNKS INDICIZZATI (Qdrant)')
    print('=' * 60)
    print()
    
    c = QdrantClient('http://localhost:6333')
    
    # Scroll tutti i chunks e cerca WCM
    results = c.scroll('iso_sgi_docs_v31', limit=2000, with_payload=True)
    
    wcm_chunks = []
    for point in results[0]:
        text = point.payload.get('text', '')
        doc_id = point.payload.get('doc_id', 'N/A')
        if 'wcm' in text.lower():
            wcm_chunks.append({
                'doc_id': doc_id,
                'text': text[:200]
            })
    
    print(f'Trovato WCM in {len(wcm_chunks)} chunks indicizzati:')
    print()
    
    # Raggruppa per doc_id
    by_doc = {}
    for ch in wcm_chunks:
        doc_id = ch['doc_id']
        if doc_id not in by_doc:
            by_doc[doc_id] = []
        by_doc[doc_id].append(ch['text'])
    
    for doc_id, texts in sorted(by_doc.items()):
        print(f"[{doc_id}] {len(texts)} chunks con WCM")
        for t in texts[:2]:
            clean = ' '.join(t.split())[:100]
            print(f"  -> {clean}...")
        print()
    
    return wcm_chunks


if __name__ == '__main__':
    pdf_results = search_pdf()
    qdrant_results = search_qdrant()
    
    # Confronto
    print()
    print('=' * 60)
    print('CONFRONTO PDF vs QDRANT')
    print('=' * 60)
    print()
    
    pdf_docs = set(r['file'].split('_')[0] + '-' + r['file'].split('_')[1].split('_')[0] 
                   for r in pdf_results)
    qdrant_docs = set(ch['doc_id'] for ch in qdrant_results)
    
    # Normalizza nomi
    pdf_normalized = set()
    for r in pdf_results:
        # Estrai doc_id dal nome file (es. PS-06_01_Rev.04_xxx.pdf -> PS-06_01)
        parts = r['file'].replace('.pdf', '').split('_')
        if len(parts) >= 2:
            doc_id = parts[0] + '_' + parts[1]
            pdf_normalized.add(doc_id)
    
    print(f"PDF con WCM: {sorted(pdf_normalized)}")
    print(f"Qdrant con WCM: {sorted(qdrant_docs)}")
    print()
    
    missing = pdf_normalized - qdrant_docs
    if missing:
        print(f"MANCANTI in Qdrant: {missing}")
    else:
        print("Tutti i documenti con WCM sono indicizzati!")

