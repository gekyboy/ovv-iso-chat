"""
Community Summarizer per GraphRAG (R25)
Genera riassunti gerarchici per ogni comunità usando LLM

Features:
- Generazione summary con LLM (Ollama)
- Batch processing per VRAM optimization
- Embedding dei summary per retrieval
- Cache per evitare rigenerazione
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from collections import defaultdict

import networkx as nx

from src.graph.types import CommunitySummary

logger = logging.getLogger(__name__)


# Prompt template per generazione summary
SUMMARY_PROMPT_TEMPLATE = """Analizza questo gruppo di concetti e relazioni estratti da documenti ISO aziendali.

## Entità nel gruppo:
{entities_text}

## Relazioni tra le entità:
{relations_text}

## Esempio di contenuto dai documenti:
{sample_text}

---

Genera un riassunto conciso (max 150 parole) che:
1. Descriva il TEMA PRINCIPALE di questo gruppo
2. Identifichi le entità più importanti e il loro ruolo
3. Spieghi come le entità sono collegate tra loro
4. Sia utile per capire rapidamente di cosa tratta questo gruppo

Rispondi SOLO con il riassunto, senza preamboli."""


class CommunitySummarizer:
    """
    Genera riassunti per comunità di entità correlate.
    Usa LLM per comprensione semantica profonda.
    """
    
    def __init__(
        self,
        llm_agent: Optional[Any] = None,
        embedding_model: Optional[Any] = None,
        max_entities_per_summary: int = 20,
        max_tokens_per_summary: int = 300,
        batch_size: int = 5
    ):
        """
        Inizializza il summarizer
        
        Args:
            llm_agent: Agente LLM (ISOAgent o compatibile)
            embedding_model: Modello per embedding dei summary
            max_entities_per_summary: Max entità da includere nel prompt
            max_tokens_per_summary: Max token per summary generato
            batch_size: Comunità da processare in batch (per VRAM)
        """
        self.llm_agent = llm_agent
        self.embedding_model = embedding_model
        self.max_entities_per_summary = max_entities_per_summary
        self.max_tokens_per_summary = max_tokens_per_summary
        self.batch_size = batch_size
        
        # Cache summaries
        self.summaries: Dict[int, CommunitySummary] = {}
        
        # Stats
        self.stats = {
            "total_generated": 0,
            "total_tokens": 0,
            "avg_generation_time": 0.0
        }
        
        logger.info(f"CommunitySummarizer inizializzato (batch_size={batch_size})")
    
    def set_llm_agent(self, llm_agent: Any):
        """Imposta l'agente LLM (lazy loading)"""
        self.llm_agent = llm_agent
    
    def set_embedding_model(self, embedding_model: Any):
        """Imposta il modello di embedding (lazy loading)"""
        self.embedding_model = embedding_model
    
    def summarize_community(
        self,
        graph: nx.DiGraph,
        community_id: int,
        community_nodes: List[str],
        chunk_texts: Optional[Dict[str, str]] = None,
        entity_to_chunks: Optional[Dict[str, List[str]]] = None
    ) -> CommunitySummary:
        """
        Genera summary per una singola comunità
        
        Args:
            graph: Grafo completo
            community_id: ID comunità
            community_nodes: Nodi nella comunità
            chunk_texts: Mapping chunk_id → text (opzionale)
            entity_to_chunks: Mapping entity_id → [chunk_ids] (opzionale)
            
        Returns:
            CommunitySummary generato
        """
        import time
        start_time = time.time()
        
        # Estrai sottografo
        subgraph = graph.subgraph(community_nodes).copy()
        
        # Prepara testo entità
        entities_text = self._format_entities(subgraph)
        
        # Prepara testo relazioni
        relations_text = self._format_relations(subgraph)
        
        # Prepara sample text dai chunk
        sample_text = self._get_sample_text(
            community_nodes, chunk_texts, entity_to_chunks
        )
        
        # Genera summary
        if self.llm_agent:
            summary_text = self._generate_with_llm(
                entities_text, relations_text, sample_text
            )
        else:
            # Fallback senza LLM
            summary_text = self._generate_fallback_summary(
                subgraph, community_nodes
            )
        
        # Identifica entità e relazioni chiave
        key_entities = self._get_key_entities(subgraph, limit=5)
        key_relations = self._get_key_relations(subgraph, limit=5)
        
        # Crea summary object
        summary = CommunitySummary(
            community_id=community_id,
            entity_ids=community_nodes,
            summary=summary_text,
            key_entities=key_entities,
            key_relations=key_relations,
            entity_count=len(community_nodes),
            relation_count=subgraph.number_of_edges(),
            metadata={
                "generated_at": datetime.now().isoformat(),
                "generation_time_ms": (time.time() - start_time) * 1000
            }
        )
        
        # Genera embedding del summary (se disponibile)
        if self.embedding_model and summary_text:
            try:
                embedding = self.embedding_model.encode(summary_text).tolist()
                summary.embedding = embedding
            except Exception as e:
                logger.warning(f"Errore generazione embedding: {e}")
        
        # Cache
        self.summaries[community_id] = summary
        self.stats["total_generated"] += 1
        
        return summary
    
    def _format_entities(self, subgraph: nx.DiGraph) -> str:
        """Formatta entità per il prompt"""
        lines = []
        
        # Raggruppa per tipo
        by_type: Dict[str, List[Tuple[str, Dict]]] = defaultdict(list)
        for node_id, data in subgraph.nodes(data=True):
            entity_type = data.get("type", "UNKNOWN")
            by_type[entity_type].append((node_id, data))
        
        for entity_type, entities in sorted(by_type.items()):
            lines.append(f"\n### {entity_type}:")
            for node_id, data in entities[:self.max_entities_per_summary // len(by_type)]:
                label = data.get("label", node_id)
                desc = data.get("metadata", {}).get("description", "")
                if desc:
                    lines.append(f"- {label}: {desc[:100]}")
                else:
                    lines.append(f"- {label}")
        
        return "\n".join(lines)
    
    def _format_relations(self, subgraph: nx.DiGraph) -> str:
        """Formatta relazioni per il prompt"""
        lines = []
        
        # Raggruppa per tipo
        by_type: Dict[str, List] = defaultdict(list)
        for source, target, data in subgraph.edges(data=True):
            rel_type = data.get("type", "RELATED_TO")
            by_type[rel_type].append((source, target, data))
        
        for rel_type, relations in sorted(by_type.items()):
            lines.append(f"\n### {rel_type}:")
            for source, target, data in relations[:5]:
                source_label = subgraph.nodes[source].get("label", source)
                target_label = subgraph.nodes[target].get("label", target)
                lines.append(f"- {source_label} → {target_label}")
        
        return "\n".join(lines) if lines else "Nessuna relazione esplicita trovata."
    
    def _get_sample_text(
        self,
        community_nodes: List[str],
        chunk_texts: Optional[Dict[str, str]],
        entity_to_chunks: Optional[Dict[str, List[str]]]
    ) -> str:
        """Recupera sample text dai chunk associati alle entità"""
        if not chunk_texts or not entity_to_chunks:
            return "Nessun testo di esempio disponibile."
        
        # Raccogli chunk unici
        chunks_seen = set()
        sample_chunks = []
        
        for entity_id in community_nodes[:10]:  # Limita entità
            for chunk_id in entity_to_chunks.get(entity_id, [])[:2]:  # Max 2 chunk per entità
                if chunk_id not in chunks_seen and chunk_id in chunk_texts:
                    chunks_seen.add(chunk_id)
                    text = chunk_texts[chunk_id][:300]  # Tronca
                    sample_chunks.append(f"[{chunk_id}]: {text}...")
                    
                    if len(sample_chunks) >= 3:  # Max 3 sample
                        break
            if len(sample_chunks) >= 3:
                break
        
        return "\n\n".join(sample_chunks) if sample_chunks else "Nessun testo di esempio disponibile."
    
    def _generate_with_llm(
        self,
        entities_text: str,
        relations_text: str,
        sample_text: str
    ) -> str:
        """Genera summary usando LLM"""
        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            entities_text=entities_text,
            relations_text=relations_text,
            sample_text=sample_text
        )
        
        try:
            # Usa il metodo generate dell'agent
            if hasattr(self.llm_agent, 'generate'):
                response = self.llm_agent.generate(
                    prompt,
                    max_tokens=self.max_tokens_per_summary,
                    temperature=0.3
                )
            elif hasattr(self.llm_agent, 'invoke'):
                # LangChain style
                response = self.llm_agent.invoke(prompt)
                if hasattr(response, 'content'):
                    response = response.content
            else:
                # Fallback: prova come callable
                response = self.llm_agent(prompt)
            
            return response.strip() if response else ""
            
        except Exception as e:
            logger.error(f"Errore generazione LLM: {e}")
            return self._generate_fallback_summary_text(entities_text, relations_text)
    
    def _generate_fallback_summary(
        self,
        subgraph: nx.DiGraph,
        community_nodes: List[str]
    ) -> str:
        """Genera summary senza LLM (template-based)"""
        # Conta tipi
        type_counts: Dict[str, int] = defaultdict(int)
        labels_by_type: Dict[str, List[str]] = defaultdict(list)
        
        for node_id, data in subgraph.nodes(data=True):
            entity_type = data.get("type", "UNKNOWN")
            type_counts[entity_type] += 1
            labels_by_type[entity_type].append(data.get("label", node_id))
        
        # Costruisci summary
        parts = []
        parts.append(f"Comunità con {len(community_nodes)} entità e {subgraph.number_of_edges()} relazioni.")
        
        # Descrivi composizione
        composition = ", ".join([
            f"{count} {etype}" 
            for etype, count in sorted(type_counts.items(), key=lambda x: -x[1])
        ])
        parts.append(f"Composizione: {composition}.")
        
        # Entità principali per tipo
        for etype, labels in list(labels_by_type.items())[:3]:
            top_labels = ", ".join(labels[:3])
            parts.append(f"{etype}: {top_labels}.")
        
        return " ".join(parts)
    
    def _generate_fallback_summary_text(
        self,
        entities_text: str,
        relations_text: str
    ) -> str:
        """Fallback quando LLM fallisce"""
        # Estrai primi label da entities_text
        import re
        labels = re.findall(r'- ([^:\n]+)', entities_text)[:5]
        
        return f"Gruppo contenente: {', '.join(labels)}. Relazioni: {relations_text[:100]}..."
    
    def _get_key_entities(
        self,
        subgraph: nx.DiGraph,
        limit: int = 5
    ) -> List[str]:
        """Identifica entità più importanti (per degree)"""
        # Usa degree come proxy per importanza
        degrees = dict(subgraph.degree())
        sorted_nodes = sorted(degrees.items(), key=lambda x: -x[1])
        
        return [node_id for node_id, _ in sorted_nodes[:limit]]
    
    def _get_key_relations(
        self,
        subgraph: nx.DiGraph,
        limit: int = 5
    ) -> List[str]:
        """Identifica relazioni più importanti (per confidence)"""
        edges_with_conf = []
        for source, target, data in subgraph.edges(data=True):
            conf = data.get("confidence", 0.5)
            rel_type = data.get("type", "RELATED_TO")
            edges_with_conf.append((f"{source}→{target}:{rel_type}", conf))
        
        sorted_edges = sorted(edges_with_conf, key=lambda x: -x[1])
        return [edge_str for edge_str, _ in sorted_edges[:limit]]
    
    def summarize_all(
        self,
        graph: nx.DiGraph,
        community_to_nodes: Dict[int, List[str]],
        chunk_texts: Optional[Dict[str, str]] = None,
        entity_to_chunks: Optional[Dict[str, List[str]]] = None,
        show_progress: bool = True
    ) -> Dict[int, CommunitySummary]:
        """
        Genera summary per tutte le comunità
        
        Args:
            graph: Grafo completo
            community_to_nodes: Mapping community_id → [node_ids]
            chunk_texts: Mapping chunk_id → text
            entity_to_chunks: Mapping entity_id → [chunk_ids]
            show_progress: Se mostrare progress bar
            
        Returns:
            Dict: community_id → CommunitySummary
        """
        from tqdm import tqdm
        
        community_ids = list(community_to_nodes.keys())
        iterator = tqdm(community_ids, desc="Generating summaries") if show_progress else community_ids
        
        for comm_id in iterator:
            nodes = community_to_nodes[comm_id]
            self.summarize_community(
                graph=graph,
                community_id=comm_id,
                community_nodes=nodes,
                chunk_texts=chunk_texts,
                entity_to_chunks=entity_to_chunks
            )
        
        logger.info(f"Generati {len(self.summaries)} summary")
        return self.summaries
    
    def get_summary(self, community_id: int) -> Optional[CommunitySummary]:
        """Recupera summary per community_id"""
        return self.summaries.get(community_id)
    
    def search_summaries(
        self,
        query_embedding: List[float],
        top_k: int = 3
    ) -> List[Tuple[int, float]]:
        """
        Cerca nei summary per embedding similarity
        
        Args:
            query_embedding: Embedding della query
            top_k: Numero di risultati
            
        Returns:
            Lista di (community_id, similarity_score)
        """
        import numpy as np
        
        results = []
        query_vec = np.array(query_embedding)
        
        for comm_id, summary in self.summaries.items():
            if summary.embedding:
                summary_vec = np.array(summary.embedding)
                # Cosine similarity
                similarity = np.dot(query_vec, summary_vec) / (
                    np.linalg.norm(query_vec) * np.linalg.norm(summary_vec) + 1e-8
                )
                results.append((comm_id, float(similarity)))
        
        # Sort by similarity
        results.sort(key=lambda x: -x[1])
        return results[:top_k]
    
    def save(self, path: str):
        """Salva tutti i summary in JSON"""
        data = {
            "summaries": {
                str(k): v.to_dict() for k, v in self.summaries.items()
            },
            "stats": self.stats,
            "saved_at": datetime.now().isoformat()
        }
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Summary salvati in {path}")
    
    def load(self, path: str):
        """Carica summary da JSON"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self.summaries = {
            int(k): CommunitySummary.from_dict(v)
            for k, v in data.get("summaries", {}).items()
        }
        self.stats = data.get("stats", self.stats)
        
        logger.info(f"Caricati {len(self.summaries)} summary da {path}")
    
    def print_summary(self, community_id: int):
        """Stampa summary di una comunità"""
        summary = self.summaries.get(community_id)
        if not summary:
            print(f"Summary non trovato per community {community_id}")
            return
        
        print("\n" + "="*50)
        print(f"📝 COMMUNITY {community_id} SUMMARY")
        print("="*50)
        print(f"📍 Entità: {summary.entity_count}")
        print(f"🔗 Relazioni: {summary.relation_count}")
        print(f"\n📖 Summary:\n{summary.summary}")
        print(f"\n⭐ Key entities: {', '.join(summary.key_entities)}")
        print(f"🔑 Key relations: {', '.join(summary.key_relations[:3])}")
        print("="*50 + "\n")

