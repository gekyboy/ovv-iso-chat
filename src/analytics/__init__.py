"""
Analytics module per OVV ISO Chat

Moduli:
- R05: Estrazione automatica acronimi
- R07: Sistema Analytics e Report
- R19: Gap detection e segnalazione lacune
"""

# R19 - Gap Detection
from .gap_detector import GapDetector, GapDetection, GapSignal
from .gap_store import GapStore, GapReport

# R05 - Acronym Extraction
from .acronym_extractor import AcronymExtractor, AcronymProposal, PatternType

# R07 - Analytics Collectors
from .collectors import (
    QueryCollector,
    QueryLog,
    GlossaryCollector,
    MemoryCollector,
    PipelineCollector
)

# R07 - Analytics Analyzers
from .analyzers import (
    UsageAnalyzer,
    QualityAnalyzer,
    ReportGenerator
)

# R07 - Scheduler & Commands
from .scheduler import AnalyticsScheduler, get_scheduler
from .commands import AnalyticsCommands, get_analytics_commands

__all__ = [
    # R19
    "GapDetector",
    "GapDetection", 
    "GapSignal",
    "GapStore",
    "GapReport",
    # R05
    "AcronymExtractor",
    "AcronymProposal",
    "PatternType",
    # R07 Collectors
    "QueryCollector",
    "QueryLog",
    "GlossaryCollector",
    "MemoryCollector",
    "PipelineCollector",
    # R07 Analyzers
    "UsageAnalyzer",
    "QualityAnalyzer",
    "ReportGenerator",
    # R07 Scheduler & Commands
    "AnalyticsScheduler",
    "get_scheduler",
    "AnalyticsCommands",
    "get_analytics_commands"
]

