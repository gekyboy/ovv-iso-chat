"""
OVV ISO Chat v3.1 - Main Entry Point

Comandi disponibili:
- ingest: Indicizza documenti PDF in Qdrant
- status: Verifica stato sistema (Qdrant, VRAM)
- memory-test: Test memoria (add/update/list)
- chat: Query RAG su documenti ISO
- teach: Spiega come compilare documenti (MR, TOOLS)
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

import yaml
import torch

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Carica configurazione YAML"""
    config_file = Path(config_path)
    if not config_file.exists():
        logger.error(f"Config non trovato: {config_path}")
        sys.exit(1)
    
    with open(config_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_vram_info() -> dict:
    """Ottiene info VRAM GPU"""
    if not torch.cuda.is_available():
        return {"available": False}
    
    return {
        "available": True,
        "device": torch.cuda.get_device_name(0),
        "total_mb": torch.cuda.get_device_properties(0).total_memory / 1024 / 1024,
        "used_mb": torch.cuda.memory_allocated() / 1024 / 1024,
        "cached_mb": torch.cuda.memory_reserved() / 1024 / 1024
    }


def cmd_ingest(args):
    """
    Comando: ingest
    Indicizza documenti PDF in Qdrant
    """
    from src.ingestion.extractor import PDFExtractor
    from src.ingestion.chunker import ISOChunker
    from src.ingestion.indexer import QdrantIndexer
    
    config = load_config(args.config)
    
    # Verifica VRAM iniziale
    vram = get_vram_info()
    if vram["available"]:
        logger.info(f"GPU: {vram['device']}, VRAM: {vram['used_mb']:.0f}/{vram['total_mb']:.0f} MB")
    
    # Inizializza componenti
    logger.info("Inizializzazione componenti...")
    extractor = PDFExtractor(config=config)
    chunker = ISOChunker(config=config)
    indexer = QdrantIndexer(config=config)
    
    # Crea collection
    if not indexer.create_collection(recreate=args.recreate):
        logger.error("Impossibile creare collection Qdrant")
        sys.exit(1)
    
    # Verifica input directory
    input_dir = Path(args.input)
    if not input_dir.exists():
        logger.error(f"Directory non trovata: {input_dir}")
        sys.exit(1)
    
    # Estrai documenti
    logger.info(f"Estrazione documenti da: {input_dir}")
    limit = args.limit if args.limit > 0 else None
    documents = extractor.extract_directory(input_dir, limit=limit)
    
    if not documents:
        logger.warning("Nessun documento estratto")
        return
    
    logger.info(f"Estratti {len(documents)} documenti")
    
    # Chunk documenti
    logger.info("Chunking documenti...")
    chunks = chunker.chunk_documents(documents)
    logger.info(f"Generati {len(chunks)} chunk")
    
    # Indicizza
    logger.info("Indicizzazione in Qdrant...")
    stats = indexer.index_chunks(chunks)
    
    # Verifica VRAM finale
    vram_final = get_vram_info()
    
    # Report
    print("\n" + "=" * 60)
    print("INDICIZZAZIONE COMPLETATA")
    print("=" * 60)
    print(f"Documenti processati: {stats.total_documents}")
    print(f"Chunk totali:        {stats.total_chunks}")
    print(f"Chunk indicizzati:   {stats.indexed_chunks}")
    print(f"Chunk falliti:       {stats.failed_chunks}")
    print(f"Collection:          {stats.collection_name}")
    
    if vram_final["available"]:
        print(f"\nVRAM utilizzata:     {vram_final['used_mb']:.0f} MB")
        if vram_final["used_mb"] > 5500:
            print("⚠️  ATTENZIONE: VRAM > 5.5GB!")
        else:
            print("✅ VRAM OK (< 5.5GB)")
    
    # Info collection
    info = indexer.get_collection_info()
    print(f"\nStato collection:    {info}")
    
    # Cleanup VRAM se richiesto
    if args.unload:
        indexer.unload_model()
        torch.cuda.empty_cache()
        logger.info("VRAM liberata")


def cmd_status(args):
    """
    Comando: status
    Verifica stato sistema
    """
    config = load_config(args.config)
    
    print("\n" + "=" * 60)
    print("OVV ISO Chat v3.1 - Status")
    print("=" * 60)
    
    # GPU/VRAM
    vram = get_vram_info()
    if vram["available"]:
        print(f"\n🖥️  GPU: {vram['device']}")
        print(f"   VRAM totale:  {vram['total_mb']:.0f} MB")
        print(f"   VRAM usata:   {vram['used_mb']:.0f} MB")
        print(f"   VRAM cached:  {vram['cached_mb']:.0f} MB")
    else:
        print("\n⚠️  GPU CUDA non disponibile")
    
    # Qdrant
    print("\n📦 Qdrant:")
    try:
        from src.ingestion.indexer import QdrantIndexer
        indexer = QdrantIndexer(config=config)
        info = indexer.get_collection_info()
        if "error" in info:
            print(f"   ❌ Errore: {info['error']}")
        else:
            print(f"   Collection: {info['name']}")
            print(f"   Punti:      {info['points_count']}")
            print(f"   Status:     {info['status']}")
    except Exception as e:
        print(f"   ❌ Connessione fallita: {e}")
    
    # Input docs
    input_dir = Path(config.get("paths", {}).get("input_docs", "data/input_docs"))
    pdf_count = len(list(input_dir.rglob("*.pdf"))) if input_dir.exists() else 0
    print(f"\n📄 Documenti:")
    print(f"   Directory: {input_dir}")
    print(f"   PDF trovati: {pdf_count}")
    
    # Memory
    print("\n🧠 Memoria:")
    try:
        from src.memory.store import MemoryStore
        store = MemoryStore(config=config)
        stats = store.get_stats()
        print(f"   Memorie totali: {stats['total_memories']}")
        print(f"   Per tipo: {stats['by_type']}")
        print(f"   Boost medio: {stats['average_boost']:.2f}")
    except Exception as e:
        print(f"   ❌ Errore: {e}")


def cmd_memory_test(args):
    """
    Comando: memory-test
    Test memoria con operazioni add/update/list/feedback
    """
    from src.memory.store import MemoryStore, MemoryType
    from src.memory.updater import MemoryUpdater
    
    config = load_config(args.config)
    store = MemoryStore(config=config)
    updater = MemoryUpdater(store, config=config)
    
    print("\n" + "=" * 60)
    print("OVV ISO Chat v3.1 - Memory Test")
    print("=" * 60)
    
    if args.add:
        # Parse: "type: content" o "content" (default preference)
        content = args.add
        mem_type = "preference"
        
        # Check per formato "type: content"
        if ":" in content and content.split(":")[0].strip().lower() in ["preference", "fact", "correction", "procedure"]:
            parts = content.split(":", 1)
            mem_type = parts[0].strip().lower()
            content = parts[1].strip()
        
        print(f"\n➕ Aggiunta memoria:")
        print(f"   Tipo: {mem_type}")
        print(f"   Contenuto: {content}")
        
        memory = updater.add_from_explicit_feedback(
            content=content,
            mem_type=mem_type
        )
        
        print(f"\n✅ Memoria creata:")
        print(f"   ID: {memory.id}")
        print(f"   Confidence: {memory.effective_confidence:.2f}")
        print(f"   Boost: {memory.boost_factor:.2f}")
    
    elif args.feedback:
        # Parse: "mem_id:+1" o "mem_id:-1"
        parts = args.feedback.split(":")
        if len(parts) == 2:
            mem_id = parts[0]
            is_positive = parts[1].strip() in ["+1", "👍", "positive", "yes"]
        else:
            print("❌ Formato feedback: mem_id:+1 o mem_id:-1")
            return
        
        print(f"\n{'👍' if is_positive else '👎'} Feedback su {mem_id}...")
        
        if is_positive:
            memory = updater.add_positive_feedback(mem_id)
        else:
            memory = updater.add_negative_feedback(mem_id)
        
        if memory:
            print(f"✅ Boost aggiornato: {memory.boost_factor:.2f}")
        else:
            print("❌ Memoria non trovata")
    
    elif args.search:
        print(f"\n🔍 Ricerca: '{args.search}'")
        
        memories = store.search(args.search, limit=5)
        
        if memories:
            print(f"\nTrovate {len(memories)} memorie:")
            for m in memories:
                conf = f"{m.effective_confidence:.0%}"
                print(f"  [{m.type.value}] {m.content[:50]}... (conf: {conf})")
        else:
            print("Nessuna memoria trovata")
    
    else:
        # List all
        print("\n📋 Memorie salvate:")
        
        memories = store.get_all()
        
        if not memories:
            print("   (nessuna memoria)")
        else:
            for m in memories[:10]:
                emoji = {"preference": "📌", "fact": "💡", "correction": "⚠️", "procedure": "📋"}.get(m.type.value, "•")
                boost = f"×{m.boost_factor:.2f}" if m.boost_factor != 1.0 else ""
                print(f"   {emoji} [{m.id}] {m.content[:40]}... {boost}")
    
    # Stats
    stats = store.get_stats()
    print(f"\n📊 Statistiche:")
    print(f"   Totale: {stats['total_memories']} memorie")
    print(f"   Boost medio: {stats['average_boost']:.2f}")


def cmd_chat(args):
    """
    Comando: chat
    Query RAG sui documenti ISO-SGI
    """
    from src.integration.rag_pipeline import RAGPipeline
    
    config = load_config(args.config)
    
    print("\n" + "=" * 60)
    print("OVV ISO Chat v3.1 - Chat")
    print("=" * 60)
    
    # Inizializza pipeline
    logger.info("Inizializzazione RAG pipeline...")
    pipeline = RAGPipeline(config=config, config_path=args.config)
    
    # Verifica VRAM
    vram = get_vram_info()
    if vram["available"]:
        logger.info(f"GPU: {vram['device']}, VRAM iniziale: {vram['used_mb']:.0f} MB")
    
    # Esegui query
    print(f"\n[?] Query: {args.query}")
    print("-" * 60)
    
    try:
        response = pipeline.query(
            question=args.query,
            use_glossary=not args.no_glossary,
            use_memory=not args.no_memory,
            use_reranking=not args.no_rerank
        )
        
        # Mostra risposta
        print(f"\n[R] Risposta:\n")
        print(response.answer)
        
        # Mostra sources
        if args.show_sources and response.sources:
            print(f"\n[S] Fonti ({len(response.sources)}):")
            for i, src in enumerate(response.sources, 1):
                score = f"{src.rerank_score:.2f}" if src.rerank_score else f"{src.score:.2f}"
                print(f"  [{i}] {src.doc_id} (score: {score})")
        
        # Metadata
        print(f"\n⏱️  Latenza: {response.latency_ms:.0f}ms")
        print(f"🤖 Modello: {response.model_used}")
        
        if response.expanded_query != args.query:
            print(f"🔄 Query espansa: {response.expanded_query[:80]}...")
        
        if response.memory_context:
            print(f"🧠 Memoria: {len(response.memory_context)} caratteri iniettati")
        
        # Verifica VRAM finale
        vram_final = get_vram_info()
        if vram_final["available"]:
            print(f"\n📊 VRAM: {vram_final['used_mb']:.0f} MB")
            if vram_final["used_mb"] > 5500:
                print("⚠️  ATTENZIONE: VRAM > 5.5GB!")
            else:
                print("✅ VRAM OK")
        
    except Exception as e:
        logger.error(f"Errore query: {e}")
        print(f"\n❌ Errore: {e}")
        
        # Suggerimenti
        print("\n💡 Suggerimenti:")
        print("  1. Verifica che Ollama sia in esecuzione: ollama serve")
        print("  2. Verifica che Qdrant sia in esecuzione: docker ps")
        print("  3. Verifica che i documenti siano indicizzati: python -m src.main status")


def cmd_teach(args):
    """
    Comando: teach
    Spiega come compilare documenti non-PS/IL (MR, TOOLS)
    """
    from src.integration.rag_pipeline import RAGPipeline
    
    config = load_config(args.config)
    
    print("\n" + "=" * 60)
    print("OVV ISO Chat v3.1 - Teach Mode")
    print("=" * 60)
    
    # Inizializza pipeline
    logger.info("Inizializzazione RAG pipeline...")
    pipeline = RAGPipeline(config=config, config_path=args.config)
    
    # Documento da spiegare
    doc_ref = args.document
    
    print(f"\n📄 Documento: {doc_ref}")
    print(f"📖 Modalità: {args.mode}")
    print("-" * 60)
    
    # Costruisci istruzione basata su modalità
    mode_instructions = {
        "compile": "Spiega passo-passo come compilare questo documento",
        "overview": "Fornisci una panoramica di questo documento e del suo scopo",
        "errors": "Elenca gli errori comuni nella compilazione di questo documento",
        "fields": "Descrivi ogni campo del documento e cosa inserire"
    }
    instruction = mode_instructions.get(args.mode, mode_instructions["compile"])
    
    try:
        response = pipeline.teach(
            doc_ref=doc_ref,
            instruction=instruction
        )
        
        # Mostra risposta
        print(f"\n📝 {instruction}:\n")
        print(response.answer)
        
        # Mostra sources se trovati
        if response.sources:
            print(f"\n📚 Documenti correlati ({len(response.sources)}):")
            for i, src in enumerate(response.sources, 1):
                filename = src.metadata.get("filename", src.doc_id)
                print(f"  [{i}] {filename}")
        else:
            print("\n⚠️  Nessun documento specifico trovato")
            print(f"    Il documento {doc_ref} potrebbe non essere indicizzato.")
            print("    Prova: python -m src.main status")
        
    except Exception as e:
        logger.error(f"Errore teach: {e}")
        print(f"\n❌ Errore: {e}")


def main():
    """Entry point principale"""
    parser = argparse.ArgumentParser(
        description="OVV ISO Chat v3.1 - Sistema RAG per documenti ISO-SGI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  # Indicizzazione
  python -m src.main ingest --input data/input_docs/ --limit 10
  python -m src.main ingest --recreate
  
  # Status
  python -m src.main status
  
  # Chat RAG
  python -m src.main chat "Come gestire rifiuti pericolosi?"
  python -m src.main chat "Cosa dice PS-06_01 sulla sicurezza?" --show-sources
  
  # Teach documenti
  python -m src.main teach MR-10_01 --mode compile
  python -m src.main teach MR-06_01 --mode fields
  
  # Memoria
  python -m src.main memory-test --add "fact: IL-06_01 gestisce rifiuti"
  python -m src.main memory-test --feedback "preference_abc123:+1"
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Comando da eseguire")
    
    # Comando: ingest
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Indicizza documenti PDF in Qdrant"
    )
    ingest_parser.add_argument(
        "--input", "-i",
        default="data/input_docs",
        help="Directory con i PDF da indicizzare"
    )
    ingest_parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="File di configurazione"
    )
    ingest_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=0,
        help="Numero massimo di file da processare (0 = tutti)"
    )
    ingest_parser.add_argument(
        "--recreate",
        action="store_true",
        help="Ricrea la collection (elimina dati esistenti)"
    )
    ingest_parser.add_argument(
        "--unload",
        action="store_true",
        help="Scarica modello dalla VRAM dopo indicizzazione"
    )
    ingest_parser.add_argument(
        "--debug",
        action="store_true",
        help="Abilita debug logging"
    )
    
    # Comando: status
    status_parser = subparsers.add_parser(
        "status",
        help="Verifica stato sistema"
    )
    status_parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="File di configurazione"
    )
    
    # Comando: memory-test
    memory_parser = subparsers.add_parser(
        "memory-test",
        help="Test memoria (add/update/list)"
    )
    memory_parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="File di configurazione"
    )
    memory_parser.add_argument(
        "--add", "-a",
        type=str,
        help="Aggiungi memoria: 'tipo: contenuto' es. 'fact: IL-06_01 rifiuti'"
    )
    memory_parser.add_argument(
        "--feedback", "-f",
        type=str,
        help="Aggiungi feedback: 'mem_id:+1' o 'mem_id:-1'"
    )
    memory_parser.add_argument(
        "--search", "-s",
        type=str,
        help="Cerca memorie per contenuto"
    )
    
    # Comando: chat
    chat_parser = subparsers.add_parser(
        "chat",
        help="Query RAG sui documenti ISO-SGI"
    )
    chat_parser.add_argument(
        "query",
        type=str,
        help="Domanda da porre sui documenti ISO"
    )
    chat_parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="File di configurazione"
    )
    chat_parser.add_argument(
        "--show-sources",
        action="store_true",
        help="Mostra documenti fonte"
    )
    chat_parser.add_argument(
        "--no-glossary",
        action="store_true",
        help="Disabilita espansione glossario"
    )
    chat_parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Disabilita iniezione memoria"
    )
    chat_parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Disabilita reranking"
    )
    
    # Comando: teach
    teach_parser = subparsers.add_parser(
        "teach",
        help="Spiega come compilare documenti (MR, TOOLS)"
    )
    teach_parser.add_argument(
        "document",
        type=str,
        help="Codice documento da spiegare (es. MR-10_01)"
    )
    teach_parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="File di configurazione"
    )
    teach_parser.add_argument(
        "--mode", "-m",
        choices=["compile", "overview", "errors", "fields"],
        default="compile",
        help="Modalità: compile, overview, errors, fields"
    )
    
    args = parser.parse_args()
    
    if args.command == "ingest":
        if getattr(args, 'debug', False):
            logging.getLogger().setLevel(logging.DEBUG)
        cmd_ingest(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "memory-test":
        cmd_memory_test(args)
    elif args.command == "chat":
        cmd_chat(args)
    elif args.command == "teach":
        cmd_teach(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

