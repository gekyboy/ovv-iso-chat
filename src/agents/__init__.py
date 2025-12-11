"""
OVV ISO Chat - Multi-Agent Pipeline (R24)
Sciame di 5 agenti specializzati orchestrati da LangGraph

Agenti:
- GlossaryAgent: Espansione acronimi e contesto glossario
- AnalyzerAgent: Classificazione intent e decomposizione query
- RetrieverAgent: Hybrid retrieval + reranking
- ContextAgent: Compressione contesto e memory injection
- GeneratorAgent: Generazione risposta con citazioni

Usage:
    from src.agents import MultiAgentPipeline
    
    pipeline = MultiAgentPipeline(config_path="config/config.yaml")
    result = pipeline.query("Come gestire i rifiuti?", user_id="mario")
"""

from src.agents.state import AgentState, RetrievedDocument
from src.agents.orchestrator import MultiAgentPipeline, MultiAgentResponse, create_agent_pipeline

__all__ = [
    "AgentState",
    "RetrievedDocument",
    "MultiAgentPipeline",
    "MultiAgentResponse",
    "create_agent_pipeline"
]

__version__ = "1.0.0"

