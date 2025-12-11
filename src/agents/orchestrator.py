"""
Orchestrator per Multi-Agent Pipeline
Usa LangGraph StateGraph per orchestrazione con routing condizionale

Pattern: Supervisor con routing dinamico
Flow: glossary → analyzer → [retriever | direct_answer] → context → generator → END
"""

from typing import Literal, Dict, Any, Optional
from datetime import datetime
import logging

from langgraph.graph import StateGraph, END

from src.agents.state import AgentState, create_initial_state
from src.agents.agent_glossary import GlossaryAgent
from src.agents.agent_analyzer import AnalyzerAgent
from src.agents.agent_retriever import RetrieverAgent
from src.agents.agent_context import ContextAgent
from src.agents.agent_generator import GeneratorAgent
from src.agents.agent_validator import ValidatorAgent, ValidationResult

logger = logging.getLogger(__name__)


class MultiAgentResponse:
    """
    Classe wrapper per la risposta della MultiAgentPipeline.
    Compatibile con l'interfaccia di RAGResponse per facile integrazione.
    """
    
    def __init__(self, result: Dict[str, Any]):
        """
        Inizializza la risposta dal dict della pipeline.
        
        Args:
            result: Dict ritornato da MultiAgentPipeline.query()
        """
        self._data = result
        
        # Attributi compatibili con RAGResponse
        self.answer = result.get("answer", "")
        self.query = result.get("original_query", "")
        self.expanded_query = result.get("expanded_query", "")
        self.latency_ms = result.get("latency_ms", 0)
        self.model_used = "multi-agent-pipeline"
        self.memory_context = ""
        
        # Converti sources in oggetti RetrievedDoc-like
        self._sources = []
        for source_id in result.get("selected_sources", []):
            self._sources.append(_SourceWrapper(source_id, result))
    
    @property
    def sources(self):
        """Ritorna lista di source-like objects"""
        return self._sources
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte in dizionario"""
        return self._data


class _SourceWrapper:
    """Wrapper minimale per simulare un RetrievedDoc"""
    
    def __init__(self, doc_id: str, result: Dict[str, Any]):
        self.doc_id = doc_id
        self.text = ""
        self.score = 0.9
        self.rerank_score = 0.9
        
        # F01: Cerca titolo e revision nei retrieved_docs
        title = ""
        revision = ""
        retrieved_docs = result.get("retrieved_docs", [])
        for doc in retrieved_docs:
            if doc.get("doc_id") == doc_id:
                metadata = doc.get("metadata", {})
                title = metadata.get("title", "")
                revision = metadata.get("revision", "")
                break
        
        self.metadata = {
            "doc_type": self._guess_doc_type(doc_id),
            "title": title,
            "revision": revision  # Aggiunto per nome completo
        }
        
        # Cerca il testo nel compressed_context
        context = result.get("compressed_context", "")
        if doc_id in context:
            # Estrai il blocco di testo relativo a questo doc
            import re
            pattern = rf'\[.*?{re.escape(doc_id)}.*?\]\n(.*?)(?=\n\n---|\Z)'
            match = re.search(pattern, context, re.DOTALL)
            if match:
                self.text = match.group(1).strip()[:500]
    
    def _guess_doc_type(self, doc_id: str) -> str:
        """Indovina il tipo documento dal doc_id"""
        if doc_id.startswith("PS-"):
            return "PS"
        elif doc_id.startswith("IL-"):
            return "IL"
        elif doc_id.startswith("MR-"):
            return "MR"
        elif doc_id.startswith("TOOLS-"):
            return "TOOLS"
        elif "GLOSSARY" in doc_id:
            return "GLOSSARY"
        return "DOC"
    
    def to_dict(self) -> Dict:
        return {
            "doc_id": self.doc_id,
            "text": self.text,
            "score": self.score,
            "metadata": self.metadata
        }


def create_agent_pipeline(config_path: str = "config/config.yaml") -> StateGraph:
    """
    Crea il grafo degli agenti con LangGraph.
    
    Flow:
    START → glossary → analyzer → router → [retriever | direct_answer]
                                              ↓
                                  context → generator → END
    
    Router logic:
    - "definitional" + glossary_found + simple → direct_answer (skip retrieval)
    - else → retriever path
    
    Args:
        config_path: Percorso configurazione
        
    Returns:
        Grafo compilato pronto per invoke()
    """
    
    # Inizializza agenti
    glossary_agent = GlossaryAgent(config_path)
    analyzer_agent = AnalyzerAgent(config_path)
    retriever_agent = RetrieverAgent(config_path)
    context_agent = ContextAgent(config_path)
    generator_agent = GeneratorAgent(config_path)
    validator_agent = ValidatorAgent(config_path=config_path)  # R26
    
    # Crea grafo
    workflow = StateGraph(AgentState)
    
    # ==================== NODI ====================
    
    workflow.add_node("glossary", glossary_agent)
    workflow.add_node("analyzer", analyzer_agent)
    workflow.add_node("retriever", retriever_agent)
    workflow.add_node("context", context_agent)
    workflow.add_node("generator", generator_agent)
    workflow.add_node("validator", validator_agent)  # R26: ValidatorAgent
    
    # Nodo per risposta diretta da glossario CON LLM enrichment + retrieval PDF
    def direct_glossary_answer(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Genera risposta dal glossario CON enrichment LLM.
        Aggiunge anche retrieval di documenti PDF correlati per allegati.
        
        Flow:
        1. Prepara definizioni dal glossario
        2. Retrieval documenti correlati (per PDF allegati)
        3. Chiama LLM per risposta naturale e contestualizzata
        4. Fallback a risposta meccanica se LLM non disponibile
        """
        import time
        start = time.time()
        
        acronyms = state.get("acronyms_found", [])
        original_query = state.get("original_query", "")
        
        # ═══════════════════════════════════════════════════════════════
        # RETRIEVAL DOCUMENTI CORRELATI (per avere sempre i PDF allegati)
        # ═══════════════════════════════════════════════════════════════
        related_docs = []
        try:
            from src.integration.rag_pipeline import RAGPipeline
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
            
            rag = RAGPipeline(cfg)
            # Retrieval leggero: solo top-5 per non rallentare
            retrieved = rag.retrieve(original_query, top_k=5)
            related_docs = retrieved[:5]
            logger.info(f"Direct glossary + retrieval: {len(related_docs)} docs correlati")
        except Exception as e:
            logger.warning(f"Retrieval correlato fallito: {e}")
        
        if not acronyms:
            return {
                "answer": "Non ho trovato una definizione specifica. Prova a riformulare la domanda.",
                "cited_sources": [],
                "confidence": 0.3,
                "compressed_context": "",
                "selected_sources": [],
                "agent_trace": state.get("agent_trace", []) + ["direct_glossary:no_acronyms"]
            }
        
        # 1. Prepara contesto definizioni
        definitions = []
        for acr in acronyms:
            full = acr.get('full', '')
            desc = acr.get('description', '')
            line = f"• {acr['acronym']} = {full}"
            if desc:
                line += f" ({desc})"
            definitions.append(line)
        
        definitions_text = "\n".join(definitions)
        
        # 2. Chiama LLM per risposta discorsiva
        try:
            from src.memory.llm_agent import ISOAgent
            llm_agent = ISOAgent(config_path=config_path)
            
            enrichment_prompt = f"""Rispondi alla domanda usando le definizioni fornite.

📚 DEFINIZIONI DAL GLOSSARIO AZIENDALE OVV:
{definitions_text}

❓ DOMANDA: {original_query}

ISTRUZIONI:
- Rispondi in modo discorsivo e amichevole, come un collega esperto
- Spiega il significato contestualizzandolo nel mondo ISO/qualità aziendale
- Se utile, aggiungi un breve esempio pratico
- Alla fine, suggerisci se l'utente vuole approfondire
- MAX 4-5 frasi, sii conciso ma completo
- Cita "Glossario aziendale OVV" come fonte

💡 RISPOSTA:"""
            
            if llm_agent.llm:
                answer = llm_agent.llm.invoke(enrichment_prompt).strip()
                latency = (time.time() - start) * 1000
                trace_status = f"llm_enriched:{latency:.0f}ms"
                logger.info(f"Direct glossary answer con LLM: {latency:.0f}ms")
            else:
                raise RuntimeError("LLM non disponibile")
                
        except Exception as e:
            logger.warning(f"LLM enrichment fallito: {e}, uso fallback meccanico")
            
            # Fallback: risposta formattata senza LLM
            answer_parts = []
            for acr in acronyms:
                full = acr.get('full', '')
                desc = acr.get('description', '')
                part = f"**{acr['acronym']}** = {full}"
                if desc:
                    part += f"\n\n{desc}"
                answer_parts.append(part)
            
            answer = "\n\n---\n\n".join(answer_parts)
            if len(acronyms) == 1:
                answer += "\n\n*Fonte: Glossario aziendale OVV*"
            
            latency = (time.time() - start) * 1000
            trace_status = f"fallback:{latency:.0f}ms"
        
        # Costruisci sources: glossary + documenti correlati
        all_sources = []
        
        # Aggiungi voce glossario
        for acr in acronyms:
            all_sources.append({
                "doc_id": f"GLOSSARY_{acr['acronym']}",
                "text": f"{acr['acronym']} = {acr.get('full', '')}. {acr.get('description', '')}",
                "score": 1.0,
                "metadata": {
                    "title": acr.get('full', acr['acronym']),
                    "doc_type": "glossary"
                }
            })
        
        # Aggiungi documenti PDF correlati (per allegati cliccabili)
        for doc in related_docs:
            all_sources.append({
                "doc_id": doc.doc_id,
                "text": doc.text[:500] if hasattr(doc, 'text') else "",
                "score": getattr(doc, 'score', 0.5),
                "metadata": getattr(doc, 'metadata', {})
            })
        
        return {
            "answer": answer,
            "cited_sources": ["GLOSSARY"] + [d.doc_id for d in related_docs],
            "confidence": 0.95,
            "compressed_context": definitions_text,
            "selected_sources": all_sources,  # Include glossary + PDF correlati
            "agent_trace": state.get("agent_trace", []) + [f"direct_glossary:{trace_status}"]
        }
    
    workflow.add_node("direct_answer", direct_glossary_answer)
    
    # ==================== ROUTING ====================
    
    def route_after_analyzer(state: Dict[str, Any]) -> Literal["retriever", "direct_answer"]:
        """
        Decide se fare retrieval o risposta diretta.
        
        Condizioni per direct_answer:
        1. Intent = "definitional"
        2. Almeno un acronimo trovato nel glossario
        3. Query semplice (non richiede contesto documenti)
        """
        intent = state.get("query_intent", "factual")
        acronyms = state.get("acronyms_found", [])
        complexity = state.get("complexity", "simple")
        
        # Direct answer solo per definizioni semplici con acronimo trovato
        if intent == "definitional" and acronyms and complexity == "simple":
            logger.info(
                f"Routing → direct_answer (intent={intent}, "
                f"acronyms={len(acronyms)}, complexity={complexity})"
            )
            return "direct_answer"
        
        logger.info(
            f"Routing → retriever (intent={intent}, "
            f"acronyms={len(acronyms)}, complexity={complexity})"
        )
        return "retriever"
    
    # ==================== R26: ROUTING VALIDATOR ====================
    
    def route_after_validator(state: Dict[str, Any]) -> Literal["generator", "end"]:
        """
        R26: Decide se rigenerare o terminare.
        
        Logica:
        - VALID o MAX_RETRIES_EXCEEDED → END
        - INVALID_CITATIONS o LOW_GROUNDING → generator (retry)
        """
        validation_result = state.get("validation_result", "VALID")
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 2)
        
        # Se VALID o max retries raggiunto → fine
        if validation_result == "VALID" or validation_result == "MAX_RETRIES_EXCEEDED":
            logger.info(f"[R26] Validazione finale: {validation_result}")
            return "end"
        
        # Se retry disponibili → rigenera
        if retry_count < max_retries:
            logger.info(f"[R26] Retry {retry_count}/{max_retries} per: {validation_result}")
            return "generator"
        
        # Fallback → fine
        logger.info(f"[R26] Max retries raggiunto, accettando risposta")
        return "end"
    
    # ==================== EDGES ====================
    
    # Entry point
    workflow.set_entry_point("glossary")
    
    # Edges lineari
    workflow.add_edge("glossary", "analyzer")
    
    # Edge condizionale dopo analyzer
    workflow.add_conditional_edges(
        "analyzer",
        route_after_analyzer,
        {
            "retriever": "retriever",
            "direct_answer": "direct_answer"
        }
    )
    
    # Path retriever → context → generator → validator
    workflow.add_edge("retriever", "context")
    workflow.add_edge("context", "generator")
    workflow.add_edge("generator", "validator")  # R26: Passa a validator
    
    # R26: Edge condizionale dopo validator
    workflow.add_conditional_edges(
        "validator",
        route_after_validator,
        {
            "generator": "generator",  # Retry
            "end": END                  # Finito
        }
    )
    
    # Path diretto → END (salta validation)
    workflow.add_edge("direct_answer", END)
    
    return workflow.compile()


class MultiAgentPipeline:
    """
    Wrapper per pipeline multi-agent.
    Interfaccia compatibile con RAGPipeline esistente per facile migrazione.
    
    Usage:
        pipeline = MultiAgentPipeline(config_path="config/config.yaml")
        result = pipeline.query("Come gestire i rifiuti?", user_id="mario")
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Inizializza la pipeline multi-agent.
        
        Args:
            config_path: Percorso al file di configurazione
        """
        self.config_path = config_path
        self._graph = None
        self._glossary = None
        self._indexer = None
        self._flash_rank = None
        self._memory_store = None
        
        logger.info("MultiAgentPipeline inizializzata (lazy loading)")
    
    @property
    def glossary(self):
        """Lazy loading del GlossaryResolver per compatibilità con RAGPipeline"""
        if self._glossary is None:
            from src.integration.glossary import GlossaryResolver
            self._glossary = GlossaryResolver(config_path=self.config_path)
            logger.debug("GlossaryResolver caricato per MultiAgentPipeline")
        return self._glossary
    
    @property
    def indexer(self):
        """Lazy loading dell'indexer per compatibilità con RAGPipeline"""
        if self._indexer is None:
            from src.ingestion.indexer import QdrantIndexer
            import yaml
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            self._indexer = QdrantIndexer(config=config)
            logger.debug("QdrantIndexer caricato per MultiAgentPipeline")
        return self._indexer
    
    @property
    def flash_rank(self):
        """Lazy loading di FlashRank per compatibilità (ritorna None se non usato)"""
        return self._flash_rank
    
    @property
    def memory_store(self):
        """Lazy loading del MemoryStore per compatibilità con RAGPipeline"""
        if self._memory_store is None:
            from src.memory.store import MemoryStore
            self._memory_store = MemoryStore(config_path=self.config_path)
            logger.debug("MemoryStore caricato per MultiAgentPipeline")
        return self._memory_store
    
    @property
    def graph(self):
        """Lazy loading del grafo LangGraph"""
        if self._graph is None:
            logger.info("Creazione grafo agenti...")
            self._graph = create_agent_pipeline(self.config_path)
            logger.info("Grafo agenti creato")
        return self._graph
    
    def query(
        self,
        question: str,
        user_id: str = "default",
        use_glossary: bool = True,
        use_memory: bool = True,
        use_reranking: bool = True,
        inject_glossary_context: bool = True
    ) -> MultiAgentResponse:
        """
        Esegue query attraverso pipeline multi-agent.
        
        Args:
            question: Domanda utente
            user_id: ID utente per memoria
            use_glossary: Parametro legacy (sempre True per multi-agent)
            use_memory: Parametro legacy (gestito da AnalyzerAgent)
            use_reranking: Parametro legacy (sempre True per multi-agent)
            inject_glossary_context: Parametro legacy (gestito da GlossaryAgent)
            
        Returns:
            MultiAgentResponse compatibile con RAGResponse
        """
        start = datetime.now()
        
        # Crea stato iniziale
        initial_state = create_initial_state(question, user_id)
        
        try:
            # Esegui grafo
            final_state = self.graph.invoke(initial_state)
            
            latency = (datetime.now() - start).total_seconds() * 1000
            
            logger.info(
                f"Pipeline completata: {latency:.0f}ms, "
                f"trace={final_state.get('agent_trace', [])}"
            )
            
            result = {
                "original_query": question,
                "answer": final_state.get("answer", ""),
                "sources": final_state.get("cited_sources", []),
                "confidence": final_state.get("confidence", 0),
                "latency_ms": latency,
                "agent_trace": final_state.get("agent_trace", []),
                "token_count": final_state.get("token_count", 0),
                "query_intent": final_state.get("query_intent", ""),
                "expanded_query": final_state.get("expanded_query", ""),
                "selected_sources": final_state.get("selected_sources", []),
                "compressed_context": final_state.get("compressed_context", ""),
                "retrieved_docs": final_state.get("retrieved_docs", [])  # F01: Per titoli
            }
            
            return MultiAgentResponse(result)
            
        except Exception as e:
            latency = (datetime.now() - start).total_seconds() * 1000
            logger.error(f"Pipeline error: {e}")
            
            result = {
                "original_query": question,
                "answer": f"Mi dispiace, si è verificato un errore: {str(e)}",
                "sources": [],
                "confidence": 0,
                "latency_ms": latency,
                "agent_trace": initial_state.get("agent_trace", []) + [f"error:{str(e)[:50]}"],
                "token_count": 0,
                "query_intent": "",
                "expanded_query": "",
                "selected_sources": [],
                "compressed_context": "",
                "error": str(e)
            }
            
            return MultiAgentResponse(result)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Ritorna stato della pipeline.
        
        Returns:
            Dict con info sulla pipeline
        """
        return {
            "type": "multi-agent",
            "version": "1.1.0",  # R26: ValidatorAgent
            "agents": [
                "glossary",
                "analyzer", 
                "retriever",
                "context",
                "generator",
                "validator"  # R26
            ],
            "ready": self._graph is not None,
            "config_path": self.config_path,
            "features": {
                "validation_loop": True,  # R26
                "anti_hallucination": True  # R26
            }
        }
    
    # ═══════════════════════════════════════════════════════════════
    # TEACH: Delega a RAGPipeline per compatibilità R16
    # ═══════════════════════════════════════════════════════════════
    
    @property
    def _rag_pipeline(self):
        """Lazy load RAGPipeline per funzionalità teach (R16)"""
        if not hasattr(self, '__rag_pipeline'):
            self.__rag_pipeline = None
        if self.__rag_pipeline is None:
            from src.integration.rag_pipeline import RAGPipeline
            self.__rag_pipeline = RAGPipeline(config_path=self.config_path)
            logger.debug("RAGPipeline caricata per teach()")
        return self.__rag_pipeline
    
    def teach(self, doc_id: str, user_query: str = None):
        """
        Recupera informazioni su un documento per teach mode (R16).
        Delega a RAGPipeline per compatibilità.
        
        Args:
            doc_id: ID del documento (es. "MR-08_02")
            user_query: Query utente opzionale per contesto
            
        Returns:
            Dict con info documento, campi, suggerimenti
        """
        return self._rag_pipeline.teach(doc_id, user_query)


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("=" * 60)
    print("TEST MULTI-AGENT PIPELINE")
    print("=" * 60)
    
    pipeline = MultiAgentPipeline(config_path="config/config.yaml")
    
    # Test 1: Query definizionale (dovrebbe usare direct_answer)
    print("\n--- TEST 1: Query definizionale ---")
    result1 = pipeline.query("Cosa significa WCM?")
    print(f"Intent: {result1['query_intent']}")
    print(f"Trace: {result1['agent_trace']}")
    print(f"Risposta: {result1['answer'][:200]}...")
    print(f"Latenza: {result1['latency_ms']:.0f}ms")
    
    # Test 2: Query procedurale (dovrebbe usare retriever)
    print("\n--- TEST 2: Query procedurale ---")
    result2 = pipeline.query("Come gestire i rifiuti pericolosi?")
    print(f"Intent: {result2['query_intent']}")
    print(f"Trace: {result2['agent_trace']}")
    print(f"Risposta: {result2['answer'][:200]}...")
    print(f"Latenza: {result2['latency_ms']:.0f}ms")
    print(f"Fonti: {result2['sources']}")
    
    print("\n--- STATUS ---")
    print(pipeline.get_status())

