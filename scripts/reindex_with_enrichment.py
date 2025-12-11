"""
Script per re-indicizzare documenti con arricchimento R21

Uso:
    python scripts/reindex_with_enrichment.py --input data/input_docs --recreate
    python scripts/reindex_with_enrichment.py --limit 10  # Solo 10 documenti per test
"""

import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Setup path per import moduli
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

from ingestion.extractor import PDFExtractor
from ingestion.chunker import ISOChunker
from ingestion.enricher import ChunkEnricher
from ingestion.indexer import QdrantIndexer
from ingestion.synthetic_chunker import SyntheticChunker
from integration.glossary import GlossaryResolver

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def reindex_with_enrichment(
    input_dir: str = "data/input_docs",
    config_path: str = "config/config.yaml",
    recreate_collection: bool = False,
    limit: int = None,
    dry_run: bool = False
):
    """
    Re-indicizza tutti i documenti con arricchimento R21.
    
    Args:
        input_dir: Directory con PDF
        config_path: Percorso config
        recreate_collection: Se True, ricrea collection Qdrant
        limit: Numero max documenti (None = tutti)
        dry_run: Se True, non indicizza, solo mostra stats
    """
    start_time = datetime.now()
    
    print("=" * 70)
    print("R21: RE-INGESTION CON ARRICCHIMENTO")
    print("=" * 70)
    print(f"Input: {input_dir}")
    print(f"Config: {config_path}")
    print(f"Recreate: {recreate_collection}")
    print(f"Limit: {limit or 'Tutti'}")
    print(f"Dry run: {dry_run}")
    print("=" * 70)
    
    # Cambia directory al project root per path relativi
    import os
    os.chdir(project_root)
    
    # 1. Inizializza componenti
    logger.info("1. Inizializzazione componenti...")
    
    extractor = PDFExtractor(config_path=config_path)
    chunker = ISOChunker(config_path=config_path)
    
    try:
        glossary = GlossaryResolver(config_path=config_path)
        logger.info(f"   Glossario caricato: {len(glossary.acronyms)} acronimi")
    except Exception as e:
        logger.warning(f"   Glossario non disponibile: {e}")
        glossary = None
    
    enricher = ChunkEnricher(
        glossary=glossary,
        max_glossary_defs=5,
        max_scope_chars=200,
        include_scope_for=["PS", "IL"]
    )
    
    if not dry_run:
        indexer = QdrantIndexer(config_path=config_path)
    
    # 2. Estrai documenti
    logger.info(f"2. Estrazione PDF da {input_dir}...")
    documents = extractor.extract_directory(input_dir, limit=limit)
    logger.info(f"   Estratti {len(documents)} documenti")
    
    if not documents:
        logger.warning("Nessun documento trovato!")
        return None
    
    # 3. Chunk documenti
    logger.info("3. Chunking documenti...")
    all_chunks = []
    doc_map = {}
    
    for doc in documents:
        chunks = chunker.chunk_document(doc)
        all_chunks.extend(chunks)
        doc_map[doc.metadata.doc_id] = doc
    
    # Stats chunking
    parent_count = sum(1 for c in all_chunks if c.chunk_type == "parent")
    child_count = sum(1 for c in all_chunks if c.chunk_type == "child")
    light_count = sum(1 for c in all_chunks if c.chunk_type == "light")
    
    logger.info(f"   Creati {len(all_chunks)} chunks totali:")
    logger.info(f"     - Parent: {parent_count}")
    logger.info(f"     - Child: {child_count}")
    logger.info(f"     - Light: {light_count}")
    
    # 3b. Genera chunk SINTETICI per MR/TOOLS
    logger.info("3b. Generazione chunk sintetici per MR/TOOLS...")
    synthetic_chunker = SyntheticChunker()
    synthetic_enriched = synthetic_chunker.generate_enriched_chunks()
    
    logger.info(f"   Generati {len(synthetic_enriched)} chunk sintetici MR/TOOLS")
    
    # Ottieni doc_id coperti da sintetici per escluderli dall'arricchimento normale
    synthetic_doc_ids = {c.original_chunk.doc_id for c in synthetic_enriched}
    
    # Filtra chunk normali: mantieni solo PS/IL (rimuovi MR/TOOLS)
    ps_il_chunks = [
        c for c in all_chunks 
        if c.doc_id not in synthetic_doc_ids
    ]
    
    removed_count = len(all_chunks) - len(ps_il_chunks)
    logger.info(f"   Chunk PS/IL da arricchire: {len(ps_il_chunks)} (rimossi {removed_count} MR/TOOLS)")
    
    # 4. Arricchisci chunks PS/IL (normali)
    logger.info("4. Arricchimento chunks PS/IL (R21)...")
    enriched_ps_il = enricher.enrich_chunks(ps_il_chunks, documents=doc_map)
    
    stats = enricher.get_stats()
    logger.info(f"   Acronimi risolti: {stats['acronyms_resolved']}")
    logger.info(f"   Caratteri contesto: +{stats['total_context_added_chars']}")
    logger.info(f"   Media contesto/chunk: {stats['avg_context_chars']:.0f} char")
    
    # 4b. Combina chunk arricchiti: PS/IL normali + MR/TOOLS sintetici
    logger.info("4b. Combinazione chunk...")
    enriched_chunks = enriched_ps_il + synthetic_enriched
    logger.info(f"   Totale chunks da indicizzare: {len(enriched_chunks)}")
    logger.info(f"     - PS/IL arricchiti: {len(enriched_ps_il)}")
    logger.info(f"     - MR/TOOLS sintetici: {len(synthetic_enriched)}")
    
    # Mostra esempio
    if enriched_chunks:
        example = enriched_chunks[0]
        print("\n" + "-" * 70)
        print("ESEMPIO CHUNK ARRICCHITO:")
        print("-" * 70)
        print(example.enriched_text[:500])
        if len(example.enriched_text) > 500:
            print("...")
        print("-" * 70 + "\n")
    
    if dry_run:
        logger.info("Dry run completato - nessuna indicizzazione")
        
        # Mostra esempio chunk sintetico
        if synthetic_enriched:
            print("\n" + "-" * 70)
            print("ESEMPIO CHUNK SINTETICO (MR/TOOLS):")
            print("-" * 70)
            example_syn = synthetic_enriched[0]
            print(example_syn.enriched_text[:600])
            print("...")
            print("-" * 70 + "\n")
        
        return {
            "documents": len(documents),
            "chunks_ps_il": len(enriched_ps_il),
            "chunks_synthetic": len(synthetic_enriched),
            "chunks_total": len(enriched_chunks),
            "acronyms_resolved": stats['acronyms_resolved'],
            "dry_run": True
        }
    
    # 5. Crea/ricrea collection
    logger.info("5. Setup collection Qdrant...")
    indexer.create_collection(recreate=recreate_collection)
    
    # 6. Indicizza
    logger.info("6. Indicizzazione chunks arricchiti...")
    index_stats = indexer.index_chunks(enriched_chunks)
    
    # 7. Verifica
    logger.info("7. Verifica collection...")
    info = indexer.get_collection_info()
    
    # 8. Report finale
    duration = (datetime.now() - start_time).total_seconds()
    
    print("\n" + "=" * 70)
    print("REPORT FINALE")
    print("=" * 70)
    print(f"Documenti PDF:         {len(documents)}")
    print(f"Chunks PS/IL:          {len(enriched_ps_il)}")
    print(f"Chunks MR/TOOLS sint:  {len(synthetic_enriched)}")
    print(f"Chunks totali:         {len(enriched_chunks)}")
    print(f"Chunks indicizzati:    {index_stats.indexed_chunks}")
    print(f"Chunks falliti:        {index_stats.failed_chunks}")
    print(f"Acronimi risolti:      {stats['acronyms_resolved']}")
    print(f"Media contesto/chunk:  {stats['avg_context_chars']:.0f} char")
    print(f"Collection points:     {info.get('points_count', 'N/A')}")
    print(f"Collection status:     {info.get('status', 'N/A')}")
    print(f"Tempo totale:          {duration:.1f}s")
    print(f"VRAM picco:            {index_stats.vram_used_mb:.0f} MB")
    print("=" * 70)
    
    return {
        "documents": len(documents),
        "chunks_ps_il": len(enriched_ps_il),
        "chunks_synthetic": len(synthetic_enriched),
        "chunks_total": len(enriched_chunks),
        "indexed": index_stats.indexed_chunks,
        "failed": index_stats.failed_chunks,
        "acronyms_resolved": stats['acronyms_resolved'],
        "avg_context_chars": stats['avg_context_chars'],
        "duration_s": duration,
        "vram_mb": index_stats.vram_used_mb
    }


def main():
    parser = argparse.ArgumentParser(
        description="Re-indicizza documenti con arricchimento R21"
    )
    parser.add_argument(
        "--input", 
        default="data/input_docs",
        help="Directory con PDF (default: data/input_docs)"
    )
    parser.add_argument(
        "--config", 
        default="config/config.yaml",
        help="File configurazione (default: config/config.yaml)"
    )
    parser.add_argument(
        "--recreate", 
        action="store_true",
        help="Ricrea collection Qdrant (elimina esistente)"
    )
    parser.add_argument(
        "--limit", 
        type=int, 
        default=None,
        help="Numero max documenti da processare"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Solo analisi, non indicizza"
    )
    
    args = parser.parse_args()
    
    result = reindex_with_enrichment(
        input_dir=args.input,
        config_path=args.config,
        recreate_collection=args.recreate,
        limit=args.limit,
        dry_run=args.dry_run
    )
    
    if result:
        # Exit code basato su successo
        if result.get("failed", 0) > 0:
            sys.exit(1)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

