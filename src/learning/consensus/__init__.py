"""
Consensus submodule - Voting e promozione user→global
"""

from .voting_tracker import VotingTracker, ConsensusCandidate, ImplicitVote
from .promoter import GlobalPromoter

__all__ = [
    "VotingTracker",
    "ConsensusCandidate",
    "ImplicitVote",
    "GlobalPromoter"
]

