"""
Admin Panel Authentication
Autenticazione per pannello admin Streamlit

Solo Admin e Engineer possono accedere.
"""

import streamlit as st
from typing import Optional
import sys
from pathlib import Path

# Aggiungi root al path per import src
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth.store import UserStore
from src.auth.models import User, Role


def get_user_store() -> UserStore:
    """Ottiene istanza UserStore (cached)"""
    if "user_store" not in st.session_state:
        st.session_state.user_store = UserStore()
    return st.session_state.user_store


def authenticate_admin() -> Optional[User]:
    """
    Autentica admin via Streamlit session_state.
    Solo Admin e Engineer possono accedere.
    
    Returns:
        User autenticato o None se non autenticato
    """
    # Se già autenticato, ritorna utente
    if "admin_user" in st.session_state and st.session_state.admin_user:
        return st.session_state.admin_user
    
    # Form login centrato
    st.markdown("""
    <style>
    .login-container {
        max-width: 400px;
        margin: 100px auto;
        padding: 2rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("## 🔐 Admin Panel")
        st.markdown("Accesso riservato ad Admin e Engineer")
        st.divider()
        
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input(
                "Username",
                placeholder="admin",
                key="login_username"
            )
            password = st.text_input(
                "Password",
                type="password",
                placeholder="••••••••",
                key="login_password"
            )
            
            submitted = st.form_submit_button(
                "🚀 Accedi",
                use_container_width=True
            )
            
            if submitted:
                if not username or not password:
                    st.error("⚠️ Inserisci username e password")
                    return None
                
                store = get_user_store()
                user = store.authenticate(username, password)
                
                if user:
                    # Verifica ruolo
                    if user.role in [Role.ADMIN, Role.ENGINEER]:
                        st.session_state.admin_user = user
                        st.success(f"✅ Benvenuto, {user.display_name}!")
                        st.rerun()
                    else:
                        st.error("❌ Accesso negato: solo Admin/Engineer possono accedere")
                else:
                    st.error("❌ Credenziali non valide")
        
        st.caption("Credenziali default: admin/admin123 o engineer/eng123")
    
    return None


def logout():
    """Effettua logout e pulisce sessione"""
    keys_to_clear = ["admin_user", "user_store"]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


def require_role(allowed_roles: list):
    """
    Decorator factory per richiedere ruoli specifici.
    
    Usage:
        @require_role([Role.ADMIN])
        def admin_only_view(user):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            user = st.session_state.get("admin_user")
            if not user:
                st.error("❌ Non autenticato")
                st.stop()
            if user.role not in allowed_roles:
                st.error(f"❌ Accesso negato: richiesto ruolo {[r.value for r in allowed_roles]}")
                st.stop()
            return func(user, *args, **kwargs)
        return wrapper
    return decorator


def get_current_user() -> Optional[User]:
    """Ritorna utente corrente o None"""
    return st.session_state.get("admin_user")


def is_admin() -> bool:
    """Verifica se utente corrente è Admin"""
    user = get_current_user()
    return user is not None and user.role == Role.ADMIN


def is_engineer() -> bool:
    """Verifica se utente corrente è Engineer"""
    user = get_current_user()
    return user is not None and user.role == Role.ENGINEER

