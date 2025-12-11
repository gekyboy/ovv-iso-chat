"""
AgentState - Stato condiviso tra tutti gli agenti
Definisce la struttura dati che fluisce attraverso il grafo LangGraph

Ogni agente legge e scrive su questo stato condiviso.
"""

from typing import TypedDict, List, Optional, Literal, Annotated, Any
from operator import add


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


def create_initial_state(
    query: str,
    user_id: str = "default"
) -> AgentState:
    """
    Crea lo stato iniziale per una nuova query.
    
    Args:
        query: Domanda utente
        user_id: ID utente per memoria
        
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
        agent_trace=[]
    )

