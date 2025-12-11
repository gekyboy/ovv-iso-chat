"""
Admin Dashboard View
KPI cards e grafici statistiche
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Dict, List, Any
import sys
from pathlib import Path

# Aggiungi root al path
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.store import MemoryStore, MemoryType
from src.integration.glossary import GlossaryResolver
from src.auth.store import UserStore
from src.auth.models import User


def render_dashboard(user: User):
    """Renderizza dashboard principale con KPI e grafici"""
    st.title("📊 Dashboard")
    st.markdown(f"Benvenuto, **{user.display_name}** ({user.role.value})")
    
    # Carica dati
    memory_store = _get_memory_store()
    glossary = _get_glossary()
    user_store = _get_user_store()
    
    # === KPI CARDS ===
    st.subheader("📈 Metriche Principali")
    
    col1, col2, col3, col4 = st.columns(4)
    
    # Proposte pending
    pending = memory_store.get_all(namespace=("pending_global",))
    pending_today = _count_items_today(pending)
    
    with col1:
        st.metric(
            label="📋 Proposte Pending",
            value=len(pending),
            delta=f"+{pending_today} oggi" if pending_today > 0 else None,
            delta_color="normal"
        )
    
    # Memorie totali
    stats = memory_store.get_stats()
    total_memories = stats.get("total_memories", 0)
    
    with col2:
        st.metric(
            label="🧠 Memorie Totali",
            value=total_memories
        )
    
    # Glossario
    total_acronyms = len(glossary.acronyms)
    
    with col3:
        st.metric(
            label="📚 Acronimi",
            value=total_acronyms
        )
    
    # Utenti
    users = user_store.list_users()
    
    with col4:
        st.metric(
            label="👥 Utenti",
            value=len(users)
        )
    
    st.divider()
    
    # === GRAFICI ===
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📊 Memorie per Tipo")
        by_type = stats.get("by_type", {})
        
        if by_type:
            fig = px.pie(
                names=list(by_type.keys()),
                values=list(by_type.values()),
                color_discrete_sequence=px.colors.qualitative.Set3,
                hole=0.4
            )
            fig.update_layout(
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                margin=dict(t=20, b=20, l=20, r=20),
                height=300
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📭 Nessuna memoria presente")
    
    with col_right:
        st.subheader("📈 Memorie per Namespace")
        by_namespace = stats.get("by_namespace", {})
        
        if by_namespace:
            # Abbrevia nomi namespace lunghi
            labels = [ns[:15] + "..." if len(ns) > 15 else ns for ns in by_namespace.keys()]
            
            fig = px.bar(
                x=labels,
                y=list(by_namespace.values()),
                color=list(by_namespace.values()),
                color_continuous_scale="Viridis"
            )
            fig.update_layout(
                xaxis_title="Namespace",
                yaxis_title="Memorie",
                showlegend=False,
                margin=dict(t=20, b=20, l=20, r=20),
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📭 Nessun namespace presente")
    
    st.divider()
    
    # === STATISTICHE DETTAGLIATE ===
    col_stats1, col_stats2 = st.columns(2)
    
    with col_stats1:
        st.subheader("📋 Proposte Pending")
        if pending:
            # Mostra ultime 5 proposte
            st.markdown("**Ultime proposte in attesa:**")
            for i, prop in enumerate(pending[:5]):
                metadata = prop.metadata or {}
                proposer = metadata.get("proposed_by", "unknown")
                created = prop.created_at[:10] if prop.created_at else "N/A"
                
                with st.container():
                    st.markdown(f"""
                    `{created}` **{proposer}**: {prop.content[:50]}...
                    """)
            
            if len(pending) > 5:
                st.caption(f"... e altre {len(pending) - 5} proposte")
        else:
            st.success("✅ Nessuna proposta in attesa!")
    
    with col_stats2:
        st.subheader("📚 Glossario Stats")
        
        # Conta acronimi ambigui
        ambiguous_count = sum(
            1 for data in glossary.acronyms.values() 
            if data.get("ambiguous", False)
        )
        
        st.markdown(f"""
        - **Acronimi totali:** {total_acronyms}
        - **Acronimi ambigui:** {ambiguous_count}
        - **Custom terms:** {len(glossary.custom_terms)}
        """)
        
        # Top 5 acronimi per lunghezza definizione
        if glossary.acronyms:
            st.markdown("**Ultimi aggiunti (per ordine alfabetico):**")
            sorted_acronyms = sorted(glossary.acronyms.keys())[-5:]
            for acr in sorted_acronyms:
                data = glossary.acronyms[acr]
                full = data.get("full", "N/A")[:30]
                st.caption(f"• **{acr}**: {full}...")
    
    st.divider()
    
    # === AVERAGE BOOST ===
    avg_boost = stats.get("average_boost", 1.0)
    st.subheader("🎯 Feedback Bayesian")
    
    col_boost1, col_boost2, col_boost3 = st.columns(3)
    
    with col_boost1:
        st.metric(
            label="Boost Medio",
            value=f"{avg_boost:.2f}x"
        )
    
    with col_boost2:
        # Calcola distribuzione boost
        high_boost = 0
        low_boost = 0
        for ns_items in memory_store._store.values():
            for item in ns_items.values():
                if item.boost_factor > 1.0:
                    high_boost += 1
                elif item.boost_factor < 1.0:
                    low_boost += 1
        
        st.metric(
            label="Boost > 1.0",
            value=high_boost,
            delta="positive" if high_boost > 0 else None
        )
    
    with col_boost3:
        st.metric(
            label="Boost < 1.0",
            value=low_boost,
            delta="negative" if low_boost > 0 else None,
            delta_color="inverse"
        )


def _count_items_today(items: List) -> int:
    """Conta items creati oggi"""
    today = datetime.now().date().isoformat()
    return sum(1 for i in items if hasattr(i, 'created_at') and i.created_at and i.created_at.startswith(today))


@st.cache_resource
def _get_memory_store() -> MemoryStore:
    """Cache memory store"""
    return MemoryStore(config_path="config/config.yaml")


@st.cache_resource
def _get_glossary() -> GlossaryResolver:
    """Cache glossary"""
    return GlossaryResolver(config_path="config/config.yaml")


@st.cache_resource
def _get_user_store() -> UserStore:
    """Cache user store"""
    return UserStore()

