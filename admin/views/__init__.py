"""
Admin Panel Views
"""

from .dashboard import render_dashboard
from .proposals import render_proposals
from .glossary import render_glossary
from .memories import render_memories
from .users import render_users
from .analytics import render_analytics_view
from .consensus import render_consensus_view

__all__ = [
    "render_dashboard",
    "render_proposals", 
    "render_glossary",
    "render_memories",
    "render_users",
    "render_analytics_view",
    "render_consensus_view"
]

