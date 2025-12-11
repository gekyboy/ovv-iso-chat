"""
AgentState - Stato condiviso tra tutti gli agenti
Definisce la struttura dati che fluisce attraverso il grafo LangGraph

Ogni agente legge e scrive su questo stato condiviso.
"""

from typing import TypedDict, List, Optional, Literal, Annotated, Any, Callable
from operator import add
import logging
import time

logger = logging.getLogger(__name__)


# ==================== F11: Status Phases ====================
RAG_PHASES = {
    "glossary": ("🤔", "Leggo la domanda..."),
    "analyzer": ("🧠", "Capisco cosa cerchi..."),
    "retriever": ("📚", "Cerco nei documenti..."),
    "context": ("📄", "Preparo il contesto..."),
    "generator": ("✍️", "Scrivo la risposta..."),
    "validator": ("🔍", "Verifico le fonti..."),
    "retry": ("🤨", "Non mi convince... riscrivo!"),
    "direct": ("📖", "Conosco già la risposta!"),
}


def emit_status(state: dict, phase: str, extra_info: str = "", delay_seconds: float = 0) -> None:
    """
    Emette un aggiornamento di stato se il callback è presente.
    
    Args:
        state: AgentState corrente
        phase: Nome della fase ("glossary", "analyzer", etc.)
        extra_info: Info aggiuntiva opzionale (es. "8 trovati")
        delay_seconds: Delay in secondi DOPO aver emesso (per far vedere il messaggio)
                       Se 0, usa delay minimo di 0.8s per dare tempo all'utente di leggere
    """
    # Delay minimo per dare tempo all'utente di vedere ogni fase
    MIN_DISPLAY_TIME = 0.8  # secondi
    
    callback = state.get("status_callback")
    if callback:
        emoji, message = RAG_PHASES.get(phase, ("⏳", "Elaborazione..."))
        if extra_info:
            message = f"{message} ({extra_info})"
        full_message = f"{emoji} {message}"
        try:
            callback(phase, full_message)
        except Exception as e:
            logger.debug(f"Status callback error: {e}")
    
    # Delay per far vedere il messaggio (usa delay_seconds se specificato, altrimenti minimo)
    actual_delay = delay_seconds if delay_seconds > 0 else MIN_DISPLAY_TIME
    time.sleep(actual_delay)


class RetrievedDocument(TypedDict):
    """
    Documento recuperato dal retrieval.
    Può provenire da Qdrant (documenti) o dalla collezione glossario.
    """
    doc_id: str
    text: str
    score: float
    rerank_score: Optional[float]
    metadata: dict
    source_type: Literal["document", "glossary"]


class AgentState(TypedDict):
    """
    Stato condiviso tra tutti gli agenti nel grafo LangGraph.
    
    Struttura:
    - Input: query originale e user_id
    - Agent 1 (Glossary): espansione acronimi
    - Agent 2 (Analyzer): classificazione intent
    - Agent 3 (Retriever): documenti recuperati
    - Agent 4 (Context): contesto compresso
    - Agent 5 (Generator): risposta finale
    - Metadata: errori, latenza, trace
    """
    
    # ==================== INPUT ====================
    original_query: str
    user_id: str
    
    # ==================== AGENT 1: GLOSSARY ====================
    expanded_query: str
    acronyms_found: List[dict]  # [{acronym: str, full: str, description: str}]
    glossary_context: str
    
    # ==================== AGENT 2: ANALYZER ====================
    query_intent: Literal["factual", "procedural", "definitional", "comparison", "teach"]
    sub_queries: List[str]
    should_use_memory: bool
    complexity: Literal["simple", "medium", "complex"]
    
    # ==================== AGENT 3: RETRIEVER ====================
    # Annotated con add permette append invece di replace
    retrieved_docs: Annotated[List[RetrievedDocument], add]
    retrieval_scores: dict  # Stats per debug
    
    # ==================== AGENT 3.5: GRAPH (R25) ====================
    graph_context: str              # Contesto dal Knowledge Graph
    graph_entities: List[str]       # Entity IDs trovati nel grafo
    graph_chunks: List[str]         # Chunk IDs suggeriti dal grafo
    
    # ==================== AGENT 4: CONTEXT ====================
    compressed_context: str
    selected_sources: List[str]  # doc_ids selezionati
    memory_context: str
    token_count: int
    
    # ==================== AGENT 5: GENERATOR ====================
    answer: str
    cited_sources: List[str]
    confidence: float
    
    # ==================== AGENT 6: VALIDATOR (R26) ====================
    available_doc_ids: List[str]           # Doc disponibili nel contesto (per validazione)
    validation_result: str                 # "VALID" | "INVALID_CITATIONS" | "LOW_GROUNDING" | "MAX_RETRIES_EXCEEDED"
    validation_details: str                # Dettagli errore validazione
    retry_count: int                       # Contatore retry generazione
    max_retries: int                       # Max tentativi (default 2)
    previous_errors: List[str]             # Feedback errori precedenti per retry
    
    # ==================== METADATA ====================
    errors: List[str]
    latency_ms: float
    agent_trace: List[str]  # Per debug: ["glossary:45ms", "analyzer:12ms", ...]
    
    # ==================== F11: STATUS CALLBACK ====================
    status_callback: Optional[Callable[[str, str], None]]  # (phase, message) -> None


def create_initial_state(
    query: str,
    user_id: str = "default",
    status_callback: Optional[Callable[[str, str], None]] = None
) -> AgentState:
    """
    Crea lo stato iniziale per una nuova query.
    
    Args:
        query: Domanda utente
        user_id: ID utente per memoria
        status_callback: Callback (phase, message) per aggiornare UI (F11)
        
    Returns:
        AgentState inizializzato con valori default
    """
    return AgentState(
        # Input
        original_query=query,
        user_id=user_id,
        
        # Agent 1: Glossary
        expanded_query="",
        acronyms_found=[],
        glossary_context="",
        
        # Agent 2: Analyzer
        query_intent="factual",
        sub_queries=[],
        should_use_memory=False,
        complexity="simple",
        
        # Agent 3: Retriever
        retrieved_docs=[],
        retrieval_scores={},
        
        # Agent 3.5: Graph (R25)
        graph_context="",
        graph_entities=[],
        graph_chunks=[],
        
        # Agent 4: Context
        compressed_context="",
        selected_sources=[],
        memory_context="",
        token_count=0,
        
        # Agent 5: Generator
        answer="",
        cited_sources=[],
        confidence=0.0,
        
        # Agent 6: Validator (R26)
        available_doc_ids=[],
        validation_result="",
        validation_details="",
        retry_count=0,
        max_retries=2,
        previous_errors=[],
        
        # Metadata
        errors=[],
        latency_ms=0.0,
        agent_trace=[],
        
        # F11: Status callback
        status_callback=status_callback
    )

