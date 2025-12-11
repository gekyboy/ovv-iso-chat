"""
Build Knowledge Graph - Script per costruire il grafo R25
Esegue l'intera pipeline: extraction → graph → communities → summaries

Usage:
    python scripts/build_knowledge_graph.py
    python scripts/build_knowledge_graph.py --no-summaries  # Skip summary generation
    python scripts/build_knowledge_graph.py --stats-only    # Solo statistiche
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from tqdm import tqdm
from rich.console import Console
from rich.table import Table

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
console = Console()


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Carica configurazione"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_chunks_from_qdrant(config: dict) -> list:
    """
    Carica chunk da Qdrant collection
    
    Returns:
        Lista di tuple (chunk_text, chunk_id, doc_id)
    """
    from qdrant_client import QdrantClient
    
    qdrant_config = config.get("qdrant", {})
    collection_name = qdrant_config.get("collection_name", "iso_sgi_docs_v31")
    
    console.print(f"[cyan]Connessione a Qdrant collection: {collection_name}[/cyan]")
    
    client = QdrantClient(
        host=qdrant_config.get("host", "localhost"),
        port=qdrant_config.get("port", 6333)
    )
    
    # Scroll all points
    chunks = []
    offset = None
    batch_size = 100
    
    while True:
        results, offset = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False
        )
        
        if not results:
            break
        
        for point in results:
            payload = point.payload or {}
            chunk_text = payload.get("text", "")
            chunk_id = str(point.id)
            doc_id = payload.get("doc_id", payload.get("parent_doc_id", "unknown"))
            
            if chunk_text:
                chunks.append((chunk_text, chunk_id, doc_id))
        
        console.print(f"  Caricati {len(chunks)} chunk...")
        
        if offset is None:
            break
    
    console.print(f"[green]✓ Totale: {len(chunks)} chunk caricati[/green]")
    return chunks


def build_knowledge_graph(
    config: dict,
    chunks: list,
    generate_summaries: bool = True
) -> dict:
    """
    Costruisce il knowledge graph completo
    
    Args:
        config: Configurazione
        chunks: Lista di (text, chunk_id, doc_id)
        generate_summaries: Se generare i summary delle community
        
    Returns:
        Dict con statistiche
    """
    from src.graph.entity_extractor import EntityExtractor
    from src.graph.relation_extractor import RelationExtractor
    from src.graph.builder import KnowledgeGraphBuilder
    from src.graph.community import CommunityDetector
    
    graphrag_config = config.get("graphrag", {})
    storage_config = graphrag_config.get("storage", {})
    
    stats = {
        "chunks_processed": 0,
        "entities_extracted": 0,
        "relations_extracted": 0,
        "communities_detected": 0,
        "summaries_generated": 0,
        "start_time": datetime.now().isoformat()
    }
    
    # ========== 1. ENTITY EXTRACTION ==========
    console.print("\n[bold blue]📦 FASE 1: Entity Extraction[/bold blue]")
    
    entity_extractor = EntityExtractor(config=config)
    
    for chunk_text, chunk_id, doc_id in tqdm(chunks, desc="Extracting entities"):
        entity_extractor.extract(chunk_text, chunk_id)
        stats["chunks_processed"] += 1
    
    entities = list(entity_extractor.entity_cache.values())
    stats["entities_extracted"] = len(entities)
    
    console.print(f"[green]✓ Estratte {len(entities)} entità[/green]")
    
    # Mostra distribuzione per tipo
    entity_stats = entity_extractor.get_stats()
    table = Table(title="Entità per Tipo")
    table.add_column("Tipo", style="cyan")
    table.add_column("Count", style="green")
    for etype, count in sorted(entity_stats["entities_by_type"].items(), key=lambda x: -x[1]):
        table.add_row(etype, str(count))
    console.print(table)
    
    # ========== 2. RELATION EXTRACTION ==========
    console.print("\n[bold blue]🔗 FASE 2: Relation Extraction[/bold blue]")
    
    rel_config = graphrag_config.get("relation_extraction", {})
    relation_extractor = RelationExtractor(
        cooccurrence_window=rel_config.get("cooccurrence_window", 100),
        min_confidence=rel_config.get("min_confidence", 0.5)
    )
    
    # Prepara dati per relation extraction
    chunk_entities = {}
    for chunk_text, chunk_id, doc_id in chunks:
        chunk_entities[chunk_id] = [
            e for e in entities if chunk_id in e.source_chunks
        ]
    
    for chunk_text, chunk_id, doc_id in tqdm(chunks, desc="Extracting relations"):
        entities_in_chunk = chunk_entities.get(chunk_id, [])
        relation_extractor.extract(
            text=chunk_text,
            entities=entities_in_chunk,
            chunk_id=chunk_id,
            source_doc_id=doc_id
        )
    
    relations = list(relation_extractor.relation_cache.values())
    stats["relations_extracted"] = len(relations)
    
    console.print(f"[green]✓ Estratte {len(relations)} relazioni[/green]")
    
    # Mostra distribuzione per tipo
    rel_stats = relation_extractor.get_stats()
    table = Table(title="Relazioni per Tipo")
    table.add_column("Tipo", style="cyan")
    table.add_column("Count", style="green")
    for rtype, count in sorted(rel_stats["relations_by_type"].items(), key=lambda x: -x[1]):
        table.add_row(rtype, str(count))
    console.print(table)
    
    # ========== 3. GRAPH BUILDING ==========
    console.print("\n[bold blue]🏗️ FASE 3: Graph Building[/bold blue]")
    
    graph_builder = KnowledgeGraphBuilder()
    graph_builder.add_entities(entities)
    graph_builder.add_relations(relations)
    
    # Salva grafo
    graph_path = storage_config.get("graph_path", "data/persist/knowledge_graph.json")
    graph_builder.save(graph_path)
    
    console.print(f"[green]✓ Grafo salvato in {graph_path}[/green]")
    graph_builder.print_summary()
    
    # ========== 4. COMMUNITY DETECTION ==========
    console.print("\n[bold blue]🏘️ FASE 4: Community Detection[/bold blue]")
    
    comm_config = graphrag_config.get("community", {})
    community_detector = CommunityDetector(
        resolution=comm_config.get("resolution", 1.0),
        min_community_size=comm_config.get("min_community_size", 2)
    )
    
    community_detector.detect(graph_builder.graph)
    stats["communities_detected"] = len(community_detector.community_to_nodes)
    
    # Salva communities
    community_path = storage_config.get("community_path", "data/persist/communities.json")
    community_detector.save(community_path)
    
    console.print(f"[green]✓ {stats['communities_detected']} comunità rilevate[/green]")
    community_detector.print_summary()
    
    # ========== 5. COMMUNITY SUMMARIZATION ==========
    if generate_summaries:
        console.print("\n[bold blue]📝 FASE 5: Community Summarization[/bold blue]")
        
        from src.graph.summarizer import CommunitySummarizer
        
        # Prepara chunk texts per summarizer
        chunk_texts = {chunk_id: text for text, chunk_id, _ in chunks}
        
        summarizer = CommunitySummarizer(
            llm_agent=None,  # Senza LLM usa fallback
            max_entities_per_summary=graphrag_config.get("summarization", {}).get("max_entities_per_summary", 20)
        )
        
        summaries = summarizer.summarize_all(
            graph=graph_builder.graph,
            community_to_nodes=dict(community_detector.community_to_nodes),
            chunk_texts=chunk_texts,
            entity_to_chunks=dict(graph_builder.entity_to_chunks),
            show_progress=True
        )
        
        stats["summaries_generated"] = len(summaries)
        
        # Salva summaries
        summaries_path = storage_config.get("summaries_path", "data/persist/community_summaries.json")
        summarizer.save(summaries_path)
        
        console.print(f"[green]✓ {len(summaries)} summary generati[/green]")
    
    # ========== FINE ==========
    stats["end_time"] = datetime.now().isoformat()
    
    # Salva entity index
    entity_index = {
        "entities": [e.to_dict() for e in entities],
        "entity_to_chunks": dict(graph_builder.entity_to_chunks)
    }
    entity_index_path = storage_config.get("entity_index_path", "data/persist/entity_index.json")
    Path(entity_index_path).parent.mkdir(parents=True, exist_ok=True)
    with open(entity_index_path, "w", encoding="utf-8") as f:
        json.dump(entity_index, f, indent=2, ensure_ascii=False)
    
    console.print(f"\n[bold green]✅ Knowledge Graph completato![/bold green]")
    
    return stats


def print_stats(config: dict):
    """Stampa statistiche del grafo esistente"""
    from src.graph.builder import KnowledgeGraphBuilder
    from src.graph.community import CommunityDetector
    
    storage = config.get("graphrag", {}).get("storage", {})
    
    graph_path = storage.get("graph_path", "data/persist/knowledge_graph.json")
    if not Path(graph_path).exists():
        console.print(f"[red]Grafo non trovato: {graph_path}[/red]")
        return
    
    builder = KnowledgeGraphBuilder()
    builder.load(graph_path)
    builder.print_summary()
    
    community_path = storage.get("community_path", "data/persist/communities.json")
    if Path(community_path).exists():
        detector = CommunityDetector()
        detector.load(community_path)
        detector.print_summary()


def main():
    parser = argparse.ArgumentParser(description="Build Knowledge Graph for GraphRAG")
    parser.add_argument("--config", default="config/config.yaml", help="Config file path")
    parser.add_argument("--no-summaries", action="store_true", help="Skip summary generation")
    parser.add_argument("--stats-only", action="store_true", help="Show stats only")
    args = parser.parse_args()
    
    console.print("[bold]🧠 OVV ISO Chat - Knowledge Graph Builder (R25)[/bold]")
    console.print("="*50)
    
    config = load_config(args.config)
    
    if args.stats_only:
        print_stats(config)
        return
    
    # Carica chunk da Qdrant
    try:
        chunks = load_chunks_from_qdrant(config)
    except Exception as e:
        console.print(f"[red]Errore connessione Qdrant: {e}[/red]")
        console.print("[yellow]Assicurati che Qdrant sia in esecuzione e la collection esista[/yellow]")
        return
    
    if not chunks:
        console.print("[red]Nessun chunk trovato![/red]")
        return
    
    # Build graph
    stats = build_knowledge_graph(
        config=config,
        chunks=chunks,
        generate_summaries=not args.no_summaries
    )
    
    # Stampa statistiche finali
    console.print("\n[bold]📊 Statistiche Finali:[/bold]")
    for key, value in stats.items():
        console.print(f"  {key}: {value}")


if __name__ == "__main__":
    main()

