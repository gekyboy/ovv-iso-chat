"""
Learning Module per OVV ISO Chat

R08-R10: Apprendimento Implicito + Consenso Multi-Utente
Created: 2025-12-08

Moduli:
- signals: Raccolta segnali impliciti dalle interazioni
- analyzers: Analisi comportamento e pattern detection
- consensus: Voting tracker e promozione user→global
- learners: Orchestrazione apprendimento
- hooks: Integrazione Chainlit

Utilizzo:
    from src.learning import get_implicit_learner, LearningHooks
    
    learner = get_implicit_learner()
    hooks = LearningHooks()  # per Chainlit
"""

from .signals import SignalCollector, SignalType, ImplicitSignal, SIGNAL_WEIGHTS, get_signal_collector
from .analyzers import BehaviorAnalyzer, BehaviorPattern
from .consensus import VotingTracker, ConsensusCandidate, GlobalPromoter
from .learners import ImplicitLearner, get_implicit_learner
from .hooks import LearningHooks, get_learning_hooks

__all__ = [
    # Signals
    "SignalCollector",
    "SignalType",
    "ImplicitSignal",
    "SIGNAL_WEIGHTS",
    "get_signal_collector",
    # Analyzers
    "BehaviorAnalyzer",
    "BehaviorPattern",
    # Consensus
    "VotingTracker",
    "ConsensusCandidate",
    "GlobalPromoter",
    # Learners
    "ImplicitLearner",
    "get_implicit_learner",
    # Hooks
    "LearningHooks",
    "get_learning_hooks"
]

