"""
GraphRAG Module (R25)
Knowledge Graph construction and retrieval for OVV ISO Chat

Components:
- types: Entity, Relation, CommunitySummary data classes
- entity_extractor: Extract entities from text chunks
- relation_extractor: Extract relations between entities
- builder: Build and persist NetworkX graph
- community: Community detection with Louvain algorithm
- summarizer: Generate community summaries with LLM
- retriever: Hybrid graph + vector retrieval

Usage:
    from src.graph import EntityExtractor, KnowledgeGraphBuilder, GraphRetriever
    
    # Build graph
    extractor = EntityExtractor(config_path="config/config.yaml")
    entities = extractor.extract_batch(chunks)
    
    builder = KnowledgeGraphBuilder()
    builder.add_entities(entities)
    builder.save("data/persist/knowledge_graph.json")
    
    # Retrieve
    retriever = GraphRetriever(graph=builder.graph, ...)
    results = retriever.retrieve("query", mode="hybrid")
"""

from src.graph.types import (
    Entity,
    Relation,
    CommunitySummary,
    GraphResult,
    GraphStats,
    EntityType,
    RelationType
)
from src.graph.entity_extractor import EntityExtractor
from src.graph.relation_extractor import RelationExtractor
from src.graph.builder import KnowledgeGraphBuilder
from src.graph.community import CommunityDetector
from src.graph.summarizer import CommunitySummarizer
from src.graph.retriever import GraphRetriever

__all__ = [
    # Types
    "Entity",
    "Relation", 
    "CommunitySummary",
    "GraphResult",
    "GraphStats",
    "EntityType",
    "RelationType",
    # Components
    "EntityExtractor",
    "RelationExtractor",
    "KnowledgeGraphBuilder",
    "CommunityDetector",
    "CommunitySummarizer",
    "GraphRetriever",
]

