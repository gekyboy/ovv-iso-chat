"""
Community Detection per GraphRAG (R25)
Rileva comunità di entità correlate usando algoritmo Louvain

Features:
- Louvain community detection
- Supporto per grafi diretti (conversione automatica)
- Tuning resolution parameter
- Estrazione sottografi per comunità
"""

import logging
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict

import networkx as nx

logger = logging.getLogger(__name__)

# Try to import community detection - multiple package names
try:
    import community as community_louvain
    HAS_COMMUNITY = True
except ImportError:
    try:
        from community import community_louvain
        HAS_COMMUNITY = True
    except ImportError:
        HAS_COMMUNITY = False
        logger.warning("python-louvain non installato, uso fallback NetworkX")


class CommunityDetector:
    """
    Rileva comunità di entità correlate nel knowledge graph.
    Usa algoritmo Louvain per ottimizzare la modularità.
    """
    
    def __init__(
        self,
        resolution: float = 1.0,
        min_community_size: int = 2,
        random_state: int = 42
    ):
        """
        Inizializza il detector
        
        Args:
            resolution: Parametro risoluzione Louvain (>1 = più comunità, <1 = meno)
            min_community_size: Dimensione minima comunità (quelle più piccole saranno merged)
            random_state: Seed per riproducibilità
        """
        self.resolution = resolution
        self.min_community_size = min_community_size
        self.random_state = random_state
        
        # Risultati
        self.node_to_community: Dict[str, int] = {}
        self.community_to_nodes: Dict[int, List[str]] = defaultdict(list)
        self.modularity: float = 0.0
        
        logger.info(f"CommunityDetector inizializzato (resolution={resolution})")
    
    def detect(
        self,
        graph: nx.DiGraph,
        weight: Optional[str] = "confidence"
    ) -> Dict[str, int]:
        """
        Rileva comunità nel grafo
        
        Args:
            graph: Grafo NetworkX (DiGraph)
            weight: Nome attributo per peso archi (None = non pesato)
            
        Returns:
            Dict: node_id → community_id
        """
        if graph.number_of_nodes() == 0:
            logger.warning("Grafo vuoto, nessuna comunità rilevata")
            return {}
        
        # Converti a grafo non diretto per Louvain
        undirected = graph.to_undirected()
        
        # Rileva comunità
        if HAS_COMMUNITY:
            partition = self._detect_louvain(undirected, weight)
        else:
            partition = self._detect_networkx_fallback(undirected)
        
        # Filtra comunità troppo piccole
        partition = self._filter_small_communities(partition)
        
        # Salva risultati
        self.node_to_community = partition
        self._build_reverse_mapping()
        
        # Calcola modularità
        try:
            self.modularity = nx.community.modularity(
                undirected,
                self._get_community_sets()
            )
        except Exception:
            self.modularity = 0.0
        
        n_communities = len(self.community_to_nodes)
        logger.info(
            f"Rilevate {n_communities} comunità "
            f"(modularity={self.modularity:.4f})"
        )
        
        return partition
    
    def _detect_louvain(
        self,
        graph: nx.Graph,
        weight: Optional[str]
    ) -> Dict[str, int]:
        """Usa python-louvain per community detection"""
        try:
            partition = community_louvain.best_partition(
                graph,
                weight=weight,
                resolution=self.resolution,
                random_state=self.random_state
            )
            return partition
        except Exception as e:
            logger.error(f"Errore Louvain: {e}, uso fallback")
            return self._detect_networkx_fallback(graph)
    
    def _detect_networkx_fallback(
        self,
        graph: nx.Graph
    ) -> Dict[str, int]:
        """Fallback usando NetworkX greedy modularity"""
        try:
            # NetworkX 3.x community detection
            communities = nx.community.greedy_modularity_communities(
                graph,
                resolution=self.resolution
            )
            
            # Converti in formato partition
            partition = {}
            for i, comm in enumerate(communities):
                for node in comm:
                    partition[node] = i
            
            return partition
        except Exception as e:
            logger.error(f"Errore NetworkX fallback: {e}")
            # Ultimo fallback: ogni nodo = sua comunità
            return {node: i for i, node in enumerate(graph.nodes())}
    
    def _filter_small_communities(
        self,
        partition: Dict[str, int]
    ) -> Dict[str, int]:
        """
        Filtra comunità troppo piccole, assegnandole alla comunità più vicina
        o creando una comunità "misc"
        """
        if self.min_community_size <= 1:
            return partition
        
        # Conta membri per comunità
        community_sizes: Dict[int, int] = defaultdict(int)
        for comm_id in partition.values():
            community_sizes[comm_id] += 1
        
        # Trova comunità valide e da riassegnare
        valid_communities = {
            cid for cid, size in community_sizes.items()
            if size >= self.min_community_size
        }
        
        if not valid_communities:
            # Tutte le comunità sono piccole, tieni tutto
            return partition
        
        # Riassegna nodi di comunità piccole
        new_partition = {}
        misc_community = max(partition.values()) + 1
        
        for node, comm_id in partition.items():
            if comm_id in valid_communities:
                new_partition[node] = comm_id
            else:
                # Assegna a comunità "misc"
                new_partition[node] = misc_community
        
        # Rinumera comunità
        old_to_new = {}
        counter = 0
        for node in new_partition:
            old_comm = new_partition[node]
            if old_comm not in old_to_new:
                old_to_new[old_comm] = counter
                counter += 1
            new_partition[node] = old_to_new[old_comm]
        
        return new_partition
    
    def _build_reverse_mapping(self):
        """Costruisce mapping community → nodes"""
        self.community_to_nodes.clear()
        for node, comm_id in self.node_to_community.items():
            self.community_to_nodes[comm_id].append(node)
    
    def _get_community_sets(self) -> List[Set[str]]:
        """Ritorna comunità come lista di set (per calcolo modularità)"""
        communities = defaultdict(set)
        for node, comm_id in self.node_to_community.items():
            communities[comm_id].add(node)
        return list(communities.values())
    
    def get_community(self, node_id: str) -> Optional[int]:
        """Ritorna ID comunità per un nodo"""
        return self.node_to_community.get(node_id)
    
    def get_community_members(self, community_id: int) -> List[str]:
        """Ritorna membri di una comunità"""
        return self.community_to_nodes.get(community_id, [])
    
    def get_community_subgraph(
        self,
        graph: nx.DiGraph,
        community_id: int
    ) -> nx.DiGraph:
        """
        Estrae sottografo di una comunità
        
        Args:
            graph: Grafo completo
            community_id: ID comunità
            
        Returns:
            Sottografo contenente solo nodi della comunità
        """
        nodes = self.community_to_nodes.get(community_id, [])
        return graph.subgraph(nodes).copy()
    
    def get_inter_community_edges(
        self,
        graph: nx.DiGraph
    ) -> List[Tuple[str, str, int, int]]:
        """
        Trova archi che connettono comunità diverse
        
        Returns:
            Lista di (source, target, source_community, target_community)
        """
        inter_edges = []
        
        for source, target in graph.edges():
            source_comm = self.node_to_community.get(source, -1)
            target_comm = self.node_to_community.get(target, -1)
            
            if source_comm != target_comm and source_comm >= 0 and target_comm >= 0:
                inter_edges.append((source, target, source_comm, target_comm))
        
        return inter_edges
    
    def get_community_connections(
        self,
        graph: nx.DiGraph
    ) -> Dict[Tuple[int, int], int]:
        """
        Calcola forza connessione tra comunità
        
        Returns:
            Dict: (comm1, comm2) → numero di archi tra le comunità
        """
        connections: Dict[Tuple[int, int], int] = defaultdict(int)
        
        for source, target, s_comm, t_comm in self.get_inter_community_edges(graph):
            key = (min(s_comm, t_comm), max(s_comm, t_comm))
            connections[key] += 1
        
        return dict(connections)
    
    def get_stats(self) -> Dict[str, Any]:
        """Ritorna statistiche sulle comunità"""
        sizes = [len(members) for members in self.community_to_nodes.values()]
        
        return {
            "n_communities": len(self.community_to_nodes),
            "modularity": self.modularity,
            "resolution": self.resolution,
            "community_sizes": {
                "min": min(sizes) if sizes else 0,
                "max": max(sizes) if sizes else 0,
                "avg": sum(sizes) / len(sizes) if sizes else 0,
                "distribution": dict(sorted(
                    {f"comm_{cid}": len(members) 
                     for cid, members in self.community_to_nodes.items()}.items(),
                    key=lambda x: -x[1]
                ))
            }
        }
    
    def save(self, path: str):
        """Salva risultati community detection in JSON"""
        import json
        from pathlib import Path
        
        data = {
            "node_to_community": self.node_to_community,
            "community_to_nodes": {
                str(k): v for k, v in self.community_to_nodes.items()
            },
            "modularity": self.modularity,
            "resolution": self.resolution,
            "stats": self.get_stats()
        }
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Community data salvata in {path}")
    
    def load(self, path: str):
        """Carica risultati community detection da JSON"""
        import json
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self.node_to_community = data.get("node_to_community", {})
        self.community_to_nodes = defaultdict(list, {
            int(k): v for k, v in data.get("community_to_nodes", {}).items()
        })
        self.modularity = data.get("modularity", 0.0)
        self.resolution = data.get("resolution", 1.0)
        
        logger.info(f"Community data caricata da {path}")
    
    def print_summary(self):
        """Stampa sommario delle comunità"""
        stats = self.get_stats()
        
        print("\n" + "="*50)
        print("🏘️ COMMUNITY DETECTION SUMMARY")
        print("="*50)
        print(f"📍 Comunità rilevate: {stats['n_communities']}")
        print(f"📊 Modularità: {stats['modularity']:.4f}")
        print(f"⚙️ Resolution: {stats['resolution']}")
        
        sizes = stats['community_sizes']
        print(f"\n📏 Dimensioni comunità:")
        print(f"   Min: {sizes['min']}")
        print(f"   Max: {sizes['max']}")
        print(f"   Avg: {sizes['avg']:.1f}")
        
        print(f"\n📦 Distribuzione:")
        for comm, size in list(sizes['distribution'].items())[:10]:
            print(f"   {comm}: {size} nodi")
        
        print("="*50 + "\n")

