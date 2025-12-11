"""
Graph Agent per Multi-Agent Pipeline (R25)
Usa il Knowledge Graph per arricchire il retrieval con contesto strutturato

Features:
- Integrazione con pipeline R24
- Lazy loading dei componenti graph
- Routing intelligente basato su query intent
- Merge graph context con vector context
"""

import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Literal

import yaml

from src.agents.state import AgentState

logger = logging.getLogger(__name__)


class GraphAgent:
    """
    Agente che usa il Knowledge Graph per arricchire il contesto.
    Si inserisce nella pipeline multi-agent tra Analyzer e Retriever.
    
    Flusso:
    1. Riceve stato con query e intent
    2. Decide se usare graph (basato su intent e complexity)
    3. Esegue graph retrieval
    4. Aggiunge graph_context e graph_entities allo stato
    """
    
    def __init__(
        self,
        config: Optional[Dict] = None,
        config_path: str = "config/config.yaml"
    ):
        """
        Inizializza l'agente
        
        Args:
            config: Configurazione diretta
            config_path: Percorso config.yaml
        """
        self.config = config or self._load_config(config_path)
        self.config_path = config_path
        
        # Configurazione graphrag
        self.graph_config = self.config.get("graphrag", {})
        self.enabled = self.graph_config.get("enabled", False)
        
        # Componenti (lazy loading)
        self._graph_builder = None
        self._community_detector = None
        self._summarizer = None
        self._retriever = None
        
        # Paths
        self.graph_path = self.graph_config.get("storage", {}).get(
            "graph_path", "data/persist/knowledge_graph.json"
        )
        self.summaries_path = self.graph_config.get("storage", {}).get(
            "summaries_path", "data/persist/community_summaries.json"
        )
        self.community_path = self.graph_config.get("storage", {}).get(
            "community_path", "data/persist/communities.json"
        )
        
        # Retrieval config
        self.retrieval_config = self.graph_config.get("retrieval", {})
        self.default_mode = self.retrieval_config.get("default_mode", "hybrid")
        self.local_hops = self.retrieval_config.get("local_hops", 2)
        self.global_top_k = self.retrieval_config.get("global_top_k", 3)
        
        logger.info(f"GraphAgent inizializzato (enabled={self.enabled})")
    
    def _load_config(self, config_path: str) -> Dict:
        """Carica configurazione"""
        if Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    def _load_graph(self):
        """Carica il knowledge graph (lazy)"""
        if self._graph_builder is not None:
            return
        
        if not Path(self.graph_path).exists():
            logger.warning(f"Knowledge graph non trovato: {self.graph_path}")
            return
        
        try:
            from src.graph.builder import KnowledgeGraphBuilder
            
            self._graph_builder = KnowledgeGraphBuilder()
            self._graph_builder.load(self.graph_path)
            
            logger.info(
                f"Knowledge graph caricato: "
                f"{self._graph_builder.graph.number_of_nodes()} entità"
            )
        except Exception as e:
            logger.error(f"Errore caricamento graph: {e}")
            self._graph_builder = None
    
    def _load_communities(self):
        """Carica community detection results (lazy)"""
        if self._community_detector is not None:
            return
        
        if not Path(self.community_path).exists():
            logger.debug(f"Community data non trovata: {self.community_path}")
            return
        
        try:
            from src.graph.community import CommunityDetector
            
            self._community_detector = CommunityDetector()
            self._community_detector.load(self.community_path)
            
            logger.info(
                f"Communities caricate: "
                f"{len(self._community_detector.community_to_nodes)} comunità"
            )
        except Exception as e:
            logger.error(f"Errore caricamento communities: {e}")
            self._community_detector = None
    
    def _load_summaries(self):
        """Carica community summaries (lazy)"""
        if self._summarizer is not None:
            return
        
        if not Path(self.summaries_path).exists():
            logger.debug(f"Summaries non trovati: {self.summaries_path}")
            return
        
        try:
            from src.graph.summarizer import CommunitySummarizer
            
            self._summarizer = CommunitySummarizer()
            self._summarizer.load(self.summaries_path)
            
            logger.info(f"Summaries caricati: {len(self._summarizer.summaries)}")
        except Exception as e:
            logger.error(f"Errore caricamento summaries: {e}")
            self._summarizer = None
    
    def _get_retriever(self):
        """Ottiene o crea il retriever (lazy)"""
        if self._retriever is not None:
            return self._retriever
        
        # Carica componenti necessari
        self._load_graph()
        self._load_communities()
        self._load_summaries()
        
        if not self._graph_builder:
            return None
        
        try:
            from src.graph.retriever import GraphRetriever
            
            # Crea retriever
            self._retriever = GraphRetriever(
                graph=self._graph_builder.graph,
                entity_to_chunks=dict(self._graph_builder.entity_to_chunks),
                community_detector=self._community_detector,
                summarizer=self._summarizer,
                embedding_model=None,  # TODO: condividi con pipeline
                local_hops=self.local_hops,
                global_top_k=self.global_top_k
            )
            
            return self._retriever
        except Exception as e:
            logger.error(f"Errore creazione retriever: {e}")
            return None
    
    def process(self, state: AgentState) -> AgentState:
        """
        Processa lo stato e arricchisce con graph context
        
        Args:
            state: Stato corrente della pipeline
            
        Returns:
            Stato aggiornato con graph_context
        """
        start_time = time.time()
        
        # Inizializza campi graph nello stato
        if "graph_context" not in state:
            state["graph_context"] = ""
        if "graph_entities" not in state:
            state["graph_entities"] = []
        if "graph_chunks" not in state:
            state["graph_chunks"] = []
        
        # Skip se disabilitato
        if not self.enabled:
            state["agent_trace"].append("graph:disabled")
            return state
        
        # Skip per query semplici definitorie (già gestite da glossario)
        if (state.get("complexity") == "simple" and 
            state.get("query_intent") == "definitional"):
            state["agent_trace"].append("graph:skipped_simple")
            return state
        
        # Determina mode basato su intent
        mode = self._intent_to_mode(state.get("query_intent", "factual"))
        
        # Ottieni retriever
        retriever = self._get_retriever()
        if not retriever:
            state["errors"].append("GraphAgent: retriever non disponibile")
            state["agent_trace"].append("graph:no_retriever")
            return state
        
        try:
            # Query da usare (preferisci expanded se disponibile)
            query = state.get("expanded_query") or state.get("original_query", "")
            
            # Esegui retrieval
            results = retriever.retrieve(
                query=query,
                mode=mode,
                top_k=10
            )
            
            if results:
                # Costruisci contesto
                graph_context = retriever.get_graph_context(
                    results,
                    include_relations=True
                )
                
                # Raccogli chunk IDs
                graph_chunks = retriever.get_chunks_for_results(results)
                
                # Aggiorna stato
                state["graph_context"] = graph_context
                state["graph_entities"] = [r.entity_id for r in results]
                state["graph_chunks"] = graph_chunks
                
                logger.debug(
                    f"GraphAgent: {len(results)} entità, "
                    f"{len(graph_chunks)} chunks trovati"
                )
            
        except Exception as e:
            logger.error(f"Errore GraphAgent: {e}")
            state["errors"].append(f"GraphAgent error: {str(e)}")
        
        # Registra timing
        latency = (time.time() - start_time) * 1000
        state["agent_trace"].append(f"graph:{latency:.0f}ms")
        
        return state
    
    def _intent_to_mode(
        self,
        intent: str
    ) -> Literal["local", "global", "hybrid"]:
        """
        Mappa query intent → graph retrieval mode
        
        - factual/procedural → local (trova fatto specifico)
        - comparison → global (confronta concetti)
        - teach → hybrid (spiegazione completa)
        """
        intent_mode_map = {
            "factual": "local",
            "procedural": "local",
            "definitional": "local",
            "comparison": "global",
            "teach": "hybrid",
        }
        return intent_mode_map.get(intent, self.default_mode)
    
    def is_available(self) -> bool:
        """Verifica se il graph agent è utilizzabile"""
        return (
            self.enabled and 
            Path(self.graph_path).exists()
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Ritorna statistiche sull'agente"""
        stats = {
            "enabled": self.enabled,
            "graph_available": Path(self.graph_path).exists(),
            "communities_available": Path(self.community_path).exists(),
            "summaries_available": Path(self.summaries_path).exists()
        }
        
        if self._retriever:
            stats.update(self._retriever.get_stats())
        
        return stats
    
    def cleanup(self):
        """Libera risorse"""
        self._graph_builder = None
        self._community_detector = None
        self._summarizer = None
        self._retriever = None
        logger.debug("GraphAgent cleanup completato")

