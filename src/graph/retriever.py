"""
Graph Retriever per GraphRAG (R25)
Retrieval ibrido dal Knowledge Graph: local, global, hybrid

Modes:
- local: Entity matching → BFS expansion → chunk retrieval
- global: Community summary search → chunk retrieval
- hybrid: Combina local + global con RRF merge

Ottimizzato per bassa latenza
"""

import re
import logging
from typing import Dict, List, Optional, Any, Literal, Tuple, Set
from collections import defaultdict
import time

import networkx as nx

from src.graph.types import Entity, GraphResult, CommunitySummary

logger = logging.getLogger(__name__)


class GraphRetriever:
    """
    Retriever ibrido che combina graph traversal con similarity search.
    Supporta tre modalità: local (entity expansion), global (community search), hybrid.
    """
    
    def __init__(
        self,
        graph: nx.DiGraph,
        entity_to_chunks: Dict[str, List[str]],
        community_detector: Optional[Any] = None,
        summarizer: Optional[Any] = None,
        embedding_model: Optional[Any] = None,
        local_hops: int = 2,
        global_top_k: int = 3,
        rrf_k: int = 60
    ):
        """
        Inizializza il retriever
        
        Args:
            graph: Knowledge graph NetworkX
            entity_to_chunks: Mapping entity_id → [chunk_ids]
            community_detector: CommunityDetector con risultati
            summarizer: CommunitySummarizer con summary
            embedding_model: Modello per embedding query
            local_hops: Profondità BFS per local retrieval
            global_top_k: Top-k community da considerare
            rrf_k: Costante RRF per merge
        """
        self.graph = graph
        self.entity_to_chunks = entity_to_chunks
        self.community_detector = community_detector
        self.summarizer = summarizer
        self.embedding_model = embedding_model
        
        self.local_hops = local_hops
        self.global_top_k = global_top_k
        self.rrf_k = rrf_k
        
        # Build label index per fast lookup
        self.label_to_entity: Dict[str, str] = {}
        for node_id, data in self.graph.nodes(data=True):
            label = data.get("label", "").upper()
            if label:
                self.label_to_entity[label] = node_id
        
        logger.info(
            f"GraphRetriever inizializzato: "
            f"{self.graph.number_of_nodes()} entità, "
            f"{len(self.label_to_entity)} labels indicizzati"
        )
    
    def retrieve(
        self,
        query: str,
        mode: Literal["local", "global", "hybrid"] = "hybrid",
        top_k: int = 10,
        filter_types: Optional[List[str]] = None
    ) -> List[GraphResult]:
        """
        Esegue retrieval dal knowledge graph
        
        Args:
            query: Query testuale
            mode: Modalità retrieval (local, global, hybrid)
            top_k: Numero di risultati
            filter_types: Filtra per tipi entità (opzionale)
            
        Returns:
            Lista di GraphResult ordinati per score
        """
        start_time = time.time()
        results: List[GraphResult] = []
        
        if mode in ["local", "hybrid"]:
            local_results = self._retrieve_local(query, top_k, filter_types)
            results.extend(local_results)
            logger.debug(f"Local retrieval: {len(local_results)} risultati")
        
        if mode in ["global", "hybrid"]:
            global_results = self._retrieve_global(query, top_k, filter_types)
            results.extend(global_results)
            logger.debug(f"Global retrieval: {len(global_results)} risultati")
        
        # Merge e deduplica
        if mode == "hybrid" and len(results) > top_k:
            results = self._merge_results_rrf(results, top_k)
        else:
            results = self._deduplicate_results(results)[:top_k]
        
        latency_ms = (time.time() - start_time) * 1000
        logger.debug(f"Graph retrieval completato in {latency_ms:.0f}ms")
        
        return results
    
    def _retrieve_local(
        self,
        query: str,
        top_k: int,
        filter_types: Optional[List[str]]
    ) -> List[GraphResult]:
        """
        Local retrieval: trova entità nella query, espandi con BFS
        """
        results = []
        
        # 1. Estrai entità dalla query
        seed_entities = self._extract_entities_from_query(query)
        
        if not seed_entities:
            logger.debug("Nessuna entità trovata nella query per local retrieval")
            return results
        
        # 2. Espandi con BFS
        expanded = self._expand_entities_bfs(seed_entities, self.local_hops)
        
        # 3. Filtra per tipo se richiesto
        if filter_types:
            expanded = [
                e for e in expanded
                if self.graph.nodes.get(e, {}).get("type") in filter_types
            ]
        
        # 4. Score basato su distanza dal seed
        for entity_id in expanded:
            if entity_id not in self.graph:
                continue
            
            node_data = self.graph.nodes[entity_id]
            
            # Score: più vicino al seed = score più alto
            distance = self._min_distance_to_seeds(entity_id, seed_entities)
            score = 1.0 / (1.0 + distance * 0.3)
            
            # Boost per entità seed
            if entity_id in seed_entities:
                score = 1.0
            
            # Chunk associati
            chunk_ids = self.entity_to_chunks.get(entity_id, [])
            
            # Community
            community_id = None
            if self.community_detector:
                community_id = self.community_detector.get_community(entity_id)
            
            # Entità correlate (1-hop neighbors)
            neighbors = list(self.graph.neighbors(entity_id))[:5]
            predecessors = list(self.graph.predecessors(entity_id))[:5]
            related = list(set(neighbors + predecessors))[:5]
            
            result = GraphResult(
                entity_id=entity_id,
                entity_label=node_data.get("label", entity_id),
                entity_type=node_data.get("type", "UNKNOWN"),
                score=score,
                source="local",
                chunk_ids=chunk_ids,
                related_entities=related,
                community_id=community_id
            )
            results.append(result)
        
        # Sort by score
        results.sort(key=lambda x: -x.score)
        return results[:top_k]
    
    def _retrieve_global(
        self,
        query: str,
        top_k: int,
        filter_types: Optional[List[str]]
    ) -> List[GraphResult]:
        """
        Global retrieval: cerca nei community summary, ritorna entità
        """
        results = []
        
        if not self.summarizer or not self.embedding_model:
            logger.debug("Summarizer o embedding non disponibili per global retrieval")
            return results
        
        # 1. Embedding della query
        try:
            query_embedding = self.embedding_model.encode(query).tolist()
        except Exception as e:
            logger.warning(f"Errore embedding query: {e}")
            return results
        
        # 2. Cerca nei community summaries
        relevant_communities = self.summarizer.search_summaries(
            query_embedding, 
            top_k=self.global_top_k
        )
        
        if not relevant_communities:
            logger.debug("Nessuna community rilevante trovata")
            return results
        
        # 3. Per ogni community, aggiungi le entità chiave
        for comm_id, comm_score in relevant_communities:
            summary = self.summarizer.get_summary(comm_id)
            if not summary:
                continue
            
            # Aggiungi entità dalla community
            for entity_id in summary.entity_ids[:10]:  # Limita per community
                if entity_id not in self.graph:
                    continue
                
                node_data = self.graph.nodes[entity_id]
                
                # Filtra per tipo
                if filter_types and node_data.get("type") not in filter_types:
                    continue
                
                # Score basato su community similarity + entity importance
                is_key_entity = entity_id in summary.key_entities
                entity_score = comm_score * (1.2 if is_key_entity else 1.0)
                
                chunk_ids = self.entity_to_chunks.get(entity_id, [])
                
                result = GraphResult(
                    entity_id=entity_id,
                    entity_label=node_data.get("label", entity_id),
                    entity_type=node_data.get("type", "UNKNOWN"),
                    score=entity_score,
                    source="global",
                    chunk_ids=chunk_ids,
                    related_entities=summary.key_entities[:5],
                    community_id=comm_id
                )
                results.append(result)
        
        # Sort by score
        results.sort(key=lambda x: -x.score)
        return results[:top_k]
    
    def _extract_entities_from_query(self, query: str) -> Set[str]:
        """Estrae entity_ids dalla query usando label matching"""
        entities = set()
        query_upper = query.upper()
        
        # Pattern per documenti
        doc_patterns = [
            r'\b(PS-\d{2}(?:_\d{2})?)\b',
            r'\b(IL-\d{2}(?:_\d{2})?)\b',
            r'\b(MR-\d{2}(?:_\d{2})?)\b',
            r'\b(TOOLS-\d{2}(?:_\d{2})?)\b',
        ]
        
        for pattern in doc_patterns:
            for match in re.finditer(pattern, query_upper):
                label = match.group(1)
                if label in self.label_to_entity:
                    entities.add(self.label_to_entity[label])
        
        # Match diretto con labels
        words = re.findall(r'\b\w+\b', query_upper)
        for word in words:
            if len(word) >= 2 and word in self.label_to_entity:
                entities.add(self.label_to_entity[word])
        
        # Multi-word matching (es. "Responsabile Qualità")
        for label, entity_id in self.label_to_entity.items():
            if len(label) >= 5 and label in query_upper:
                entities.add(entity_id)
        
        return entities
    
    def _expand_entities_bfs(
        self,
        seed_entities: Set[str],
        max_hops: int
    ) -> List[str]:
        """Espande entità seed con BFS nel grafo"""
        expanded = set(seed_entities)
        frontier = set(seed_entities)
        
        for hop in range(max_hops):
            new_frontier = set()
            for entity_id in frontier:
                if entity_id not in self.graph:
                    continue
                
                # Neighbors (outgoing)
                for neighbor in self.graph.neighbors(entity_id):
                    if neighbor not in expanded:
                        new_frontier.add(neighbor)
                
                # Predecessors (incoming)
                for pred in self.graph.predecessors(entity_id):
                    if pred not in expanded:
                        new_frontier.add(pred)
            
            if not new_frontier:
                break
            
            frontier = new_frontier
            expanded.update(frontier)
        
        return list(expanded)
    
    def _min_distance_to_seeds(
        self,
        entity_id: str,
        seed_entities: Set[str]
    ) -> int:
        """Calcola distanza minima da entity_id a qualsiasi seed"""
        if entity_id in seed_entities:
            return 0
        
        # BFS per trovare distanza
        visited = {entity_id}
        frontier = {entity_id}
        distance = 0
        
        while frontier and distance < 10:  # Max depth
            distance += 1
            new_frontier = set()
            
            for node in frontier:
                if node not in self.graph:
                    continue
                
                neighbors = set(self.graph.neighbors(node)) | set(self.graph.predecessors(node))
                for neighbor in neighbors:
                    if neighbor in seed_entities:
                        return distance
                    if neighbor not in visited:
                        visited.add(neighbor)
                        new_frontier.add(neighbor)
            
            frontier = new_frontier
        
        return 999  # Non trovato
    
    def _merge_results_rrf(
        self,
        results: List[GraphResult],
        top_k: int
    ) -> List[GraphResult]:
        """Merge risultati con Reciprocal Rank Fusion"""
        # Raggruppa per source
        local_results = [r for r in results if r.source == "local"]
        global_results = [r for r in results if r.source == "global"]
        
        # RRF score per ogni entity
        rrf_scores: Dict[str, float] = defaultdict(float)
        entity_data: Dict[str, GraphResult] = {}
        
        for rank, result in enumerate(local_results):
            rrf_scores[result.entity_id] += 1.0 / (self.rrf_k + rank + 1)
            entity_data[result.entity_id] = result
        
        for rank, result in enumerate(global_results):
            rrf_scores[result.entity_id] += 1.0 / (self.rrf_k + rank + 1)
            if result.entity_id not in entity_data:
                entity_data[result.entity_id] = result
            else:
                # Merge data
                existing = entity_data[result.entity_id]
                existing.related_entities = list(set(
                    existing.related_entities + result.related_entities
                ))[:5]
        
        # Sort by RRF score
        sorted_entities = sorted(rrf_scores.items(), key=lambda x: -x[1])
        
        # Build final results
        final_results = []
        for entity_id, rrf_score in sorted_entities[:top_k]:
            result = entity_data[entity_id]
            result.score = rrf_score  # Aggiorna score con RRF
            result.source = "hybrid"
            final_results.append(result)
        
        return final_results
    
    def _deduplicate_results(
        self,
        results: List[GraphResult]
    ) -> List[GraphResult]:
        """Rimuove duplicati, mantiene score più alto"""
        seen: Dict[str, GraphResult] = {}
        
        for result in results:
            if result.entity_id not in seen:
                seen[result.entity_id] = result
            elif result.score > seen[result.entity_id].score:
                seen[result.entity_id] = result
        
        return list(seen.values())
    
    def get_chunks_for_results(
        self,
        results: List[GraphResult],
        max_chunks_per_entity: int = 3
    ) -> List[str]:
        """
        Raccoglie chunk IDs da risultati graph retrieval
        
        Args:
            results: Lista di GraphResult
            max_chunks_per_entity: Max chunk per entità
            
        Returns:
            Lista di chunk_ids unici
        """
        chunk_ids = []
        seen = set()
        
        for result in results:
            for chunk_id in result.chunk_ids[:max_chunks_per_entity]:
                if chunk_id not in seen:
                    seen.add(chunk_id)
                    chunk_ids.append(chunk_id)
        
        return chunk_ids
    
    def get_graph_context(
        self,
        results: List[GraphResult],
        include_relations: bool = True
    ) -> str:
        """
        Genera context string dai risultati per il prompt LLM
        
        Args:
            results: Lista di GraphResult
            include_relations: Se includere info sulle relazioni
            
        Returns:
            Context string formattato
        """
        if not results:
            return ""
        
        lines = ["## Contesto dal Knowledge Graph\n"]
        
        # Raggruppa per tipo
        by_type: Dict[str, List[GraphResult]] = defaultdict(list)
        for result in results:
            by_type[result.entity_type].append(result)
        
        for entity_type, type_results in by_type.items():
            lines.append(f"\n### {entity_type}:")
            for result in type_results[:5]:
                lines.append(f"- **{result.entity_label}**")
                
                if include_relations and result.related_entities:
                    related_labels = []
                    for rel_id in result.related_entities[:3]:
                        if rel_id in self.graph:
                            label = self.graph.nodes[rel_id].get("label", rel_id)
                            related_labels.append(label)
                    if related_labels:
                        lines.append(f"  Collegato a: {', '.join(related_labels)}")
        
        return "\n".join(lines)
    
    def get_stats(self) -> Dict[str, Any]:
        """Ritorna statistiche del retriever"""
        return {
            "total_entities": self.graph.number_of_nodes(),
            "total_relations": self.graph.number_of_edges(),
            "indexed_labels": len(self.label_to_entity),
            "chunks_indexed": sum(len(c) for c in self.entity_to_chunks.values()),
            "local_hops": self.local_hops,
            "global_top_k": self.global_top_k
        }

