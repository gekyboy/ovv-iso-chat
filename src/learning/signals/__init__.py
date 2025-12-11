"""
Signals submodule - Raccolta segnali impliciti
"""

from .signal_types import SignalType, ImplicitSignal, SIGNAL_WEIGHTS
from .signal_collector import SignalCollector, get_signal_collector

__all__ = [
    "SignalType",
    "ImplicitSignal",
    "SIGNAL_WEIGHTS",
    "SignalCollector",
    "get_signal_collector"
]

