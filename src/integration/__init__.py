# src/integration/__init__.py
"""
Integration module per OVV ISO Chat v3.6
RAG Pipeline completa con glossary, reranking, memory injection, HyDE
R06: Disambiguazione contestuale acronimi (v2.0 fusa)
"""

from .glossary import GlossaryResolver
from .rag_pipeline import RAGPipeline, RAGResponse, RetrievedDoc
from .hyde import HyDEGenerator, HyDEResult
from .disambiguator import (
    ContextualDisambiguator,
    UserPreferenceStore,
    AmbiguousAcronymMatch,
    DisambiguationResult,
    QueryDisambiguationResult,
    AcronymMeaning,
    UserPreference,
    get_disambiguator,
    get_preference_store,
    reset_singletons,
    # Costanti
    CERTAINTY_THRESHOLD,
    WEIGHT_CONTEXT,
    WEIGHT_PREFERENCE,
    WEIGHT_FREQUENCY
)

__all__ = [
    "GlossaryResolver",
    "RAGPipeline",
    "RAGResponse",
    "RetrievedDoc",
    "HyDEGenerator",
    "HyDEResult",
    # R06 - Disambiguazione
    "ContextualDisambiguator",
    "UserPreferenceStore",
    "AmbiguousAcronymMatch",
    "DisambiguationResult",
    "QueryDisambiguationResult",
    "AcronymMeaning",
    "UserPreference",
    "get_disambiguator",
    "get_preference_store",
    "reset_singletons",
    "CERTAINTY_THRESHOLD",
    "WEIGHT_CONTEXT",
    "WEIGHT_PREFERENCE",
    "WEIGHT_FREQUENCY"
]
