"""
Knowledge Graph Builder per GraphRAG (R25)
Costruisce e persiste il grafo NetworkX da entità e relazioni

Features:
- Costruzione grafo diretto (DiGraph)
- Serializzazione JSON compatibile
- Statistiche e validazione
- Merge incrementale
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from collections import defaultdict

import networkx as nx

from src.graph.types import Entity, Relation, GraphStats

logger = logging.getLogger(__name__)


class KnowledgeGraphBuilder:
    """
    Costruisce e gestisce il Knowledge Graph usando NetworkX.
    Il grafo è diretto (DiGraph) per rappresentare relazioni asimmetriche.
    """
    
    def __init__(self):
        """Inizializza il builder con grafo vuoto"""
        self.graph = nx.DiGraph()
        
        # Mappings ausiliari
        self.entity_to_chunks: Dict[str, List[str]] = defaultdict(list)
        self.chunk_to_entities: Dict[str, List[str]] = defaultdict(list)
        
        # Metadata
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
        self.version = "R25_v1"
        
        logger.info("KnowledgeGraphBuilder inizializzato")
    
    def add_entity(self, entity: Entity):
        """
        Aggiunge un'entità al grafo come nodo
        
        Args:
            entity: Entity da aggiungere
        """
        # Aggiungi nodo con attributi
        self.graph.add_node(
            entity.id,
            label=entity.label,
            type=entity.type,
            confidence=entity.confidence,
            metadata=entity.metadata,
            created_at=entity.created_at.isoformat()
        )
        
        # Aggiorna mappings
        for chunk_id in entity.source_chunks:
            if chunk_id not in self.entity_to_chunks[entity.id]:
                self.entity_to_chunks[entity.id].append(chunk_id)
            if entity.id not in self.chunk_to_entities[chunk_id]:
                self.chunk_to_entities[chunk_id].append(entity.id)
        
        self.last_updated = datetime.now()
    
    def add_entities(self, entities: List[Entity]):
        """Aggiunge lista di entità"""
        for entity in entities:
            self.add_entity(entity)
        
        logger.debug(f"Aggiunte {len(entities)} entità al grafo")
    
    def add_relation(self, relation: Relation):
        """
        Aggiunge una relazione al grafo come arco
        
        Args:
            relation: Relation da aggiungere
        """
        # Verifica che entrambi i nodi esistano
        if relation.source_id not in self.graph:
            logger.warning(f"Source entity {relation.source_id} non trovata, skip relazione")
            return
        
        if relation.target_id not in self.graph:
            logger.warning(f"Target entity {relation.target_id} non trovata, skip relazione")
            return
        
        # Aggiungi arco con attributi
        self.graph.add_edge(
            relation.source_id,
            relation.target_id,
            id=relation.id,
            type=relation.type,
            confidence=relation.confidence,
            source_chunks=relation.source_chunks,
            metadata=relation.metadata
        )
        
        self.last_updated = datetime.now()
    
    def add_relations(self, relations: List[Relation]):
        """Aggiunge lista di relazioni"""
        added = 0
        for relation in relations:
            if relation.source_id in self.graph and relation.target_id in self.graph:
                self.add_relation(relation)
                added += 1
        
        logger.debug(f"Aggiunte {added}/{len(relations)} relazioni al grafo")
    
    def get_entity(self, entity_id: str) -> Optional[Dict]:
        """Recupera dati di un'entità"""
        if entity_id in self.graph:
            return dict(self.graph.nodes[entity_id])
        return None
    
    def get_entity_by_label(self, label: str) -> Optional[Tuple[str, Dict]]:
        """Trova entità per label"""
        label_upper = label.upper()
        for node_id, data in self.graph.nodes(data=True):
            if data.get("label", "").upper() == label_upper:
                return node_id, data
        return None
    
    def get_neighbors(
        self,
        entity_id: str,
        direction: str = "both",
        relation_types: Optional[List[str]] = None
    ) -> List[Tuple[str, Dict]]:
        """
        Trova entità connesse a un'entità
        
        Args:
            entity_id: ID dell'entità
            direction: "in", "out", o "both"
            relation_types: Filtra per tipi di relazione
            
        Returns:
            Lista di (neighbor_id, edge_data)
        """
        neighbors = []
        
        if direction in ["out", "both"]:
            for _, target, data in self.graph.out_edges(entity_id, data=True):
                if relation_types is None or data.get("type") in relation_types:
                    neighbors.append((target, data))
        
        if direction in ["in", "both"]:
            for source, _, data in self.graph.in_edges(entity_id, data=True):
                if relation_types is None or data.get("type") in relation_types:
                    neighbors.append((source, data))
        
        return neighbors
    
    def get_subgraph(
        self,
        entity_ids: List[str],
        include_neighbors: int = 0
    ) -> nx.DiGraph:
        """
        Estrae sottografo contenente le entità specificate
        
        Args:
            entity_ids: Lista di ID entità
            include_neighbors: Livelli di neighbor da includere (0 = solo entità specificate)
            
        Returns:
            Sottografo NetworkX
        """
        nodes = set(entity_ids)
        
        # Espandi con neighbors
        for _ in range(include_neighbors):
            expansion = set()
            for node in nodes:
                if node in self.graph:
                    expansion.update(self.graph.successors(node))
                    expansion.update(self.graph.predecessors(node))
            nodes.update(expansion)
        
        # Filtra nodi esistenti
        nodes = [n for n in nodes if n in self.graph]
        
        return self.graph.subgraph(nodes).copy()
    
    def get_chunks_for_entity(self, entity_id: str) -> List[str]:
        """Ritorna chunk IDs associati a un'entità"""
        return self.entity_to_chunks.get(entity_id, [])
    
    def get_entities_in_chunk(self, chunk_id: str) -> List[str]:
        """Ritorna entity IDs presenti in un chunk"""
        return self.chunk_to_entities.get(chunk_id, [])
    
    def compute_stats(self) -> GraphStats:
        """Calcola statistiche del grafo"""
        # Conta per tipo
        entities_by_type: Dict[str, int] = defaultdict(int)
        for _, data in self.graph.nodes(data=True):
            entities_by_type[data.get("type", "UNKNOWN")] += 1
        
        relations_by_type: Dict[str, int] = defaultdict(int)
        for _, _, data in self.graph.edges(data=True):
            relations_by_type[data.get("type", "UNKNOWN")] += 1
        
        # Calcola densità
        n_nodes = self.graph.number_of_nodes()
        n_edges = self.graph.number_of_edges()
        max_edges = n_nodes * (n_nodes - 1) if n_nodes > 1 else 1
        density = n_edges / max_edges if max_edges > 0 else 0
        
        return GraphStats(
            total_entities=n_nodes,
            total_relations=n_edges,
            total_communities=0,  # Sarà calcolato dopo community detection
            entities_by_type=dict(entities_by_type),
            relations_by_type=dict(relations_by_type),
            graph_density=density,
            created_at=self.created_at
        )
    
    def save(self, path: str):
        """
        Salva il grafo in formato JSON
        
        Args:
            path: Percorso file di output
        """
        # Converti grafo in formato node_link (compatibile JSON)
        graph_data = nx.node_link_data(self.graph)
        
        # Aggiungi metadata e mappings
        data = {
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "graph": graph_data,
            "entity_to_chunks": dict(self.entity_to_chunks),
            "chunk_to_entities": dict(self.chunk_to_entities),
            "stats": self.compute_stats().to_dict()
        }
        
        # Crea directory se necessario
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        stats = self.compute_stats()
        logger.info(
            f"Grafo salvato in {path}: "
            f"{stats.total_entities} entità, {stats.total_relations} relazioni"
        )
    
    def load(self, path: str):
        """
        Carica il grafo da file JSON
        
        Args:
            path: Percorso file da caricare
        """
        if not Path(path).exists():
            raise FileNotFoundError(f"File grafo non trovato: {path}")
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Carica grafo
        self.graph = nx.node_link_graph(data["graph"])
        
        # Carica metadata
        self.version = data.get("version", "unknown")
        self.created_at = datetime.fromisoformat(data.get("created_at", datetime.now().isoformat()))
        self.last_updated = datetime.fromisoformat(data.get("last_updated", datetime.now().isoformat()))
        
        # Carica mappings
        self.entity_to_chunks = defaultdict(list, data.get("entity_to_chunks", {}))
        self.chunk_to_entities = defaultdict(list, data.get("chunk_to_entities", {}))
        
        stats = self.compute_stats()
        logger.info(
            f"Grafo caricato da {path}: "
            f"{stats.total_entities} entità, {stats.total_relations} relazioni"
        )
    
    def merge(self, other: "KnowledgeGraphBuilder"):
        """
        Merge un altro grafo in questo
        Utile per aggiornamenti incrementali
        
        Args:
            other: Altro KnowledgeGraphBuilder da mergiare
        """
        # Merge nodi
        for node_id, data in other.graph.nodes(data=True):
            if node_id in self.graph:
                # Aggiorna dati esistenti
                self.graph.nodes[node_id].update(data)
            else:
                # Aggiungi nuovo nodo
                self.graph.add_node(node_id, **data)
        
        # Merge archi
        for source, target, data in other.graph.edges(data=True):
            if self.graph.has_edge(source, target):
                # Aggiorna dati esistenti
                self.graph.edges[source, target].update(data)
            else:
                # Aggiungi nuovo arco
                self.graph.add_edge(source, target, **data)
        
        # Merge mappings
        for entity_id, chunks in other.entity_to_chunks.items():
            for chunk in chunks:
                if chunk not in self.entity_to_chunks[entity_id]:
                    self.entity_to_chunks[entity_id].append(chunk)
        
        for chunk_id, entities in other.chunk_to_entities.items():
            for entity in entities:
                if entity not in self.chunk_to_entities[chunk_id]:
                    self.chunk_to_entities[chunk_id].append(entity)
        
        self.last_updated = datetime.now()
        logger.info(f"Merged grafo: ora {self.graph.number_of_nodes()} entità")
    
    def clear(self):
        """Pulisce il grafo"""
        self.graph.clear()
        self.entity_to_chunks.clear()
        self.chunk_to_entities.clear()
        self.created_at = datetime.now()
        self.last_updated = datetime.now()
    
    def validate(self) -> List[str]:
        """
        Valida il grafo e ritorna lista di warnings
        
        Returns:
            Lista di messaggi di warning
        """
        warnings = []
        
        # Check nodi isolati
        isolated = list(nx.isolates(self.graph))
        if isolated:
            warnings.append(f"{len(isolated)} nodi isolati (senza relazioni)")
        
        # Check relazioni con nodi mancanti
        for source, target in self.graph.edges():
            if source not in self.graph.nodes:
                warnings.append(f"Relazione con source mancante: {source}")
            if target not in self.graph.nodes:
                warnings.append(f"Relazione con target mancante: {target}")
        
        # Check nodi senza tipo
        for node_id, data in self.graph.nodes(data=True):
            if "type" not in data:
                warnings.append(f"Nodo senza tipo: {node_id}")
        
        # Check grafo connesso
        if not nx.is_weakly_connected(self.graph) and self.graph.number_of_nodes() > 1:
            n_components = nx.number_weakly_connected_components(self.graph)
            warnings.append(f"Grafo non connesso: {n_components} componenti")
        
        return warnings
    
    def print_summary(self):
        """Stampa sommario del grafo"""
        stats = self.compute_stats()
        
        print("\n" + "="*50)
        print("📊 KNOWLEDGE GRAPH SUMMARY")
        print("="*50)
        print(f"📍 Entità: {stats.total_entities}")
        print(f"🔗 Relazioni: {stats.total_relations}")
        print(f"📊 Densità: {stats.graph_density:.4f}")
        print(f"📅 Creato: {stats.created_at}")
        
        print("\n📦 Entità per tipo:")
        for etype, count in sorted(stats.entities_by_type.items(), key=lambda x: -x[1]):
            print(f"   {etype}: {count}")
        
        print("\n🔗 Relazioni per tipo:")
        for rtype, count in sorted(stats.relations_by_type.items(), key=lambda x: -x[1]):
            print(f"   {rtype}: {count}")
        
        warnings = self.validate()
        if warnings:
            print("\n⚠️ Warnings:")
            for w in warnings[:5]:
                print(f"   - {w}")
        
        print("="*50 + "\n")

