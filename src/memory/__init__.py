# Modulo Memory
"""
Gestione memoria persistente con Bayesian feedback.

Componenti:
- store: Memory store con namespace e Bayesian boost (0.8x-1.2x)
- updater: HITL feedback per aggiornamento memorie
- llm_agent: Agent ISO con Ollama qwen3
"""

from .store import MemoryStore, MemoryItem, MemoryType, BayesianBooster
from .updater import MemoryUpdater
from .llm_agent import ISOAgent

__all__ = [
    "MemoryStore",
    "MemoryItem",
    "MemoryType",
    "BayesianBooster",
    "MemoryUpdater",
    "ISOAgent"
]

