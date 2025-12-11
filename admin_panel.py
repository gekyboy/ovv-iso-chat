#!/usr/bin/env python3
"""
OVV ISO Chat - Admin Panel
Pannello amministrativo Streamlit per gestione centralizzata

Avvio:
    streamlit run admin_panel.py --server.port 8501

Features:
- Dashboard KPI
- Gestione proposte pending_global (approve/reject)
- Gestione glossario (CRUD)
- Gestione memorie utenti
- Gestione utenti (solo Admin)

Accesso:
- Admin: admin/admin123
- Engineer: engineer/eng123
"""

import streamlit as st
import sys
from pathlib import Path

# Aggiungi root al path per import
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from admin.auth import authenticate_admin, logout, get_current_user
from admin.views.dashboard import render_dashboard
from admin.views.proposals import render_proposals
from admin.views.glossary import render_glossary
from admin.views.memories import render_memories
from admin.views.users import render_users
from admin.views.analytics import render_analytics_view
from admin.views.consensus import render_consensus_view
from admin.views.conversations import render_conversations_view
from src.auth.models import Role


# === PAGE CONFIG ===
st.set_page_config(
    page_title="OVV Admin Panel",
    page_icon="🎛️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': """
        ## OVV ISO Chat - Admin Panel
        
        Pannello di amministrazione per gestione:
        - Proposte utenti
        - Glossario acronimi
        - Memorie sistema
        - Utenti
        
        Versione: 1.0.0
        """
    }
)


# === CUSTOM CSS ===
st.markdown("""
<style>
    /* Header compatto */
    header[data-testid="stHeader"] {
        background-color: #1a1a2e;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #16213e 0%, #1a1a2e 100%);
    }
    
    [data-testid="stSidebar"] .stRadio > label {
        color: #e0e0e0;
        font-weight: 500;
    }
    
    /* Metric cards */
    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
        color: #4fc3f7;
    }
    
    [data-testid="stMetricDelta"] {
        font-size: 0.9rem;
    }
    
    /* Buttons */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.2s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }
    
    /* Primary buttons */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4fc3f7 0%, #29b6f6 100%);
        border: none;
    }
    
    /* Info boxes */
    .stAlert {
        border-radius: 8px;
    }
    
    /* Dividers */
    hr {
        margin: 1rem 0;
        border-color: rgba(255, 255, 255, 0.1);
    }
    
    /* Expanders */
    .streamlit-expanderHeader {
        font-weight: 600;
        color: #4fc3f7;
    }
    
    /* Forms */
    [data-testid="stForm"] {
        background-color: rgba(255, 255, 255, 0.02);
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* Tables/DataFrames */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #1a1a2e;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #4fc3f7;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #29b6f6;
    }
</style>
""", unsafe_allow_html=True)


def main():
    """Main entry point"""
    
    # === AUTENTICAZIONE ===
    user = authenticate_admin()
    if not user:
        return
    
    # === SIDEBAR ===
    with st.sidebar:
        # Logo/Header
        st.markdown("""
        <div style="text-align: center; padding: 1rem 0;">
            <h1 style="color: #4fc3f7; margin: 0;">🎛️</h1>
            <h2 style="color: #e0e0e0; margin: 0.5rem 0;">Admin Panel</h2>
            <p style="color: #888; font-size: 0.8rem;">OVV ISO Chat</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()
        
        # User info
        role_badges = {
            Role.ADMIN: ("🔴", "Admin"),
            Role.ENGINEER: ("🟡", "Engineer")
        }
        badge, role_name = role_badges.get(user.role, ("⚪", "User"))
        
        st.markdown(f"""
        <div style="text-align: center; padding: 0.5rem; background: rgba(255,255,255,0.05); border-radius: 8px;">
            <p style="margin: 0; font-weight: 600; color: #e0e0e0;">{user.display_name}</p>
            <p style="margin: 0.25rem 0 0 0; font-size: 0.85rem; color: #888;">{badge} {role_name}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()
        
        # Navigazione
        st.markdown("### 📍 Navigazione")
        
        pages = {
            "📊 Dashboard": "dashboard",
            "📈 Analytics": "analytics",
            "💬 Conversazioni": "conversations",
            "🤝 Consenso": "consensus",
            "📋 Proposte": "proposals",
            "📚 Glossario": "glossary",
            "🧠 Memorie": "memories",
            "👥 Utenti": "users"
        }
        
        # Nascondi Utenti per Engineer
        if user.role != Role.ADMIN:
            pages = {k: v for k, v in pages.items() if v != "users"}
        
        selected_page = st.radio(
            "Seleziona pagina",
            list(pages.keys()),
            label_visibility="collapsed",
            key="nav_page"
        )
        
        st.divider()
        
        # Quick stats
        st.markdown("### 📈 Quick Stats")
        _render_sidebar_stats()
        
        st.divider()
        
        # Logout
        if st.button("🚪 Logout", use_container_width=True, type="secondary"):
            logout()
        
        # Footer
        st.markdown("""
        <div style="text-align: center; padding-top: 2rem; color: #666; font-size: 0.7rem;">
            <p>OVV ISO Chat v3.2</p>
            <p>Admin Panel v1.0</p>
        </div>
        """, unsafe_allow_html=True)
    
    # === MAIN CONTENT ===
    page_key = pages.get(selected_page, "dashboard")
    
    if page_key == "dashboard":
        render_dashboard(user)
    elif page_key == "analytics":
        render_analytics_view(is_admin=(user.role == Role.ADMIN))
    elif page_key == "conversations":
        render_conversations_view("admin" if user.role == Role.ADMIN else "engineer")
    elif page_key == "consensus":
        render_consensus_view({"role": "admin" if user.role == Role.ADMIN else "engineer"})
    elif page_key == "proposals":
        render_proposals(user)
    elif page_key == "glossary":
        render_glossary(user)
    elif page_key == "memories":
        render_memories(user)
    elif page_key == "users":
        render_users(user)


def _render_sidebar_stats():
    """Render quick stats nella sidebar"""
    try:
        from src.memory.store import MemoryStore
        from src.integration.glossary import GlossaryResolver
        
        # Cache per performance
        @st.cache_resource(ttl=60)  # Refresh ogni 60 secondi
        def get_quick_stats():
            memory_store = MemoryStore(config_path="config/config.yaml")
            glossary = GlossaryResolver(config_path="config/config.yaml")
            
            pending = memory_store.get_all(namespace=("pending_global",))
            stats = memory_store.get_stats()
            
            return {
                "pending": len(pending),
                "memories": stats.get("total_memories", 0),
                "acronyms": len(glossary.acronyms)
            }
        
        quick_stats = get_quick_stats()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            pending_count = quick_stats["pending"]
            color = "#ff5722" if pending_count > 0 else "#4caf50"
            st.markdown(f"""
            <div style="text-align: center;">
                <p style="font-size: 1.5rem; font-weight: bold; color: {color}; margin: 0;">{pending_count}</p>
                <p style="font-size: 0.7rem; color: #888; margin: 0;">Pending</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div style="text-align: center;">
                <p style="font-size: 1.5rem; font-weight: bold; color: #4fc3f7; margin: 0;">{quick_stats["memories"]}</p>
                <p style="font-size: 0.7rem; color: #888; margin: 0;">Memorie</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div style="text-align: center;">
                <p style="font-size: 1.5rem; font-weight: bold; color: #ab47bc; margin: 0;">{quick_stats["acronyms"]}</p>
                <p style="font-size: 0.7rem; color: #888; margin: 0;">Acronimi</p>
            </div>
            """, unsafe_allow_html=True)
            
    except Exception as e:
        st.caption(f"Stats non disponibili")


if __name__ == "__main__":
    main()

