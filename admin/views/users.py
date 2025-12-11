"""
Admin Users View
Gestione utenti - Solo Admin
"""

import streamlit as st
import sys
from pathlib import Path

# Aggiungi root al path
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth.store import UserStore
from src.auth.models import User, Role


def render_users(user: User):
    """Gestione utenti - Solo Admin"""
    st.title("👥 Gestione Utenti")
    
    # Verifica permessi - Solo Admin
    if user.role != Role.ADMIN:
        st.error("❌ Accesso negato")
        st.warning("Solo gli utenti con ruolo **Admin** possono accedere a questa sezione.")
        st.info("Il tuo ruolo attuale è: **" + user.role.value + "**")
        return
    
    # Carica user store
    user_store = _get_user_store()
    users = user_store.list_users()
    
    # === FORM NUOVO UTENTE ===
    with st.expander("➕ Crea Nuovo Utente", expanded=False):
        _render_create_user_form(user_store)
    
    st.divider()
    
    # === STATISTICHE ===
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    
    admin_count = len([u for u in users if u.role == Role.ADMIN])
    engineer_count = len([u for u in users if u.role == Role.ENGINEER])
    user_count = len([u for u in users if u.role == Role.USER])
    
    with col_s1:
        st.metric("Totale Utenti", len(users))
    with col_s2:
        st.metric("🔴 Admin", admin_count)
    with col_s3:
        st.metric("🟡 Engineer", engineer_count)
    with col_s4:
        st.metric("🟢 User", user_count)
    
    st.divider()
    
    # === TABELLA UTENTI ===
    st.subheader("Utenti Registrati")
    
    if not users:
        st.info("📭 Nessun utente registrato")
        return
    
    # Header
    col_user, col_name, col_role, col_id, col_actions = st.columns([2, 2, 1, 2, 1])
    with col_user:
        st.markdown("**Username**")
    with col_name:
        st.markdown("**Nome**")
    with col_role:
        st.markdown("**Ruolo**")
    with col_id:
        st.markdown("**ID**")
    with col_actions:
        st.markdown("**Azioni**")
    
    st.divider()
    
    # Render utenti
    for u in users:
        _render_user_row(u, user_store, user)


def _render_create_user_form(user_store: UserStore):
    """Form per creare nuovo utente"""
    with st.form("create_user_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            new_username = st.text_input(
                "Username *",
                placeholder="mario.rossi",
                help="Username unico per il login"
            )
            new_password = st.text_input(
                "Password *",
                type="password",
                placeholder="••••••••",
                help="Minimo 6 caratteri"
            )
        
        with col2:
            new_role = st.selectbox(
                "Ruolo *",
                [r.value for r in Role],
                index=2,  # Default: user
                help="Admin: tutto | Engineer: lettura + rifiuto | User: base"
            )
            new_display = st.text_input(
                "Nome Visualizzato",
                placeholder="Mario Rossi",
                help="Nome mostrato nell'interfaccia"
            )
        
        submitted = st.form_submit_button(
            "➕ Crea Utente",
            type="primary",
            use_container_width=True
        )
        
        if submitted:
            # Validazione
            if not new_username:
                st.error("⚠️ Username obbligatorio")
            elif not new_password:
                st.error("⚠️ Password obbligatoria")
            elif len(new_password) < 6:
                st.error("⚠️ Password troppo corta (minimo 6 caratteri)")
            elif len(new_username) < 3:
                st.error("⚠️ Username troppo corto (minimo 3 caratteri)")
            else:
                # Verifica se username esiste
                existing = user_store.get_user(new_username)
                if existing:
                    st.error(f"⚠️ Username **{new_username}** già esistente")
                else:
                    # Crea utente
                    new_user = user_store.create_user(
                        username=new_username.strip(),
                        password=new_password,
                        role=Role(new_role),
                        display_name=new_display.strip() if new_display else new_username
                    )
                    
                    if new_user:
                        st.success(f"✅ Utente **{new_username}** creato con successo!")
                        _clear_cache()
                        st.rerun()
                    else:
                        st.error("❌ Errore durante la creazione")


def _render_user_row(u: User, user_store: UserStore, current_user: User):
    """Renderizza riga utente"""
    col_user, col_name, col_role, col_id, col_actions = st.columns([2, 2, 1, 2, 1])
    
    with col_user:
        st.markdown(f"**{u.username}**")
    
    with col_name:
        st.write(u.display_name or "-")
    
    with col_role:
        role_badges = {
            Role.ADMIN: "🔴",
            Role.ENGINEER: "🟡",
            Role.USER: "🟢"
        }
        badge = role_badges.get(u.role, "⚪")
        st.markdown(f"{badge} {u.role.value}")
    
    with col_id:
        st.caption(f"`{u.id}`")
    
    with col_actions:
        col_pwd, col_del = st.columns(2)
        
        with col_pwd:
            if st.button("🔑", key=f"pwd_{u.username}", help="Cambia password"):
                st.session_state[f"change_pwd_{u.username}"] = True
        
        with col_del:
            # Non può eliminare se stesso o admin principale
            can_delete = (
                u.username != "admin" and  # Admin principale protetto
                u.username != current_user.username  # Non può eliminare se stesso
            )
            
            if can_delete:
                if st.button("🗑️", key=f"del_{u.username}", help="Elimina utente"):
                    st.session_state[f"confirm_del_{u.username}"] = True
            else:
                st.button(
                    "🗑️",
                    key=f"del_dis_{u.username}",
                    disabled=True,
                    help="Non eliminabile"
                )
    
    # Form cambio password
    if st.session_state.get(f"change_pwd_{u.username}"):
        with st.form(key=f"pwd_form_{u.username}"):
            st.markdown(f"**Cambia password per: {u.username}**")
            new_pwd = st.text_input(
                "Nuova Password",
                type="password",
                placeholder="••••••••"
            )
            confirm_pwd = st.text_input(
                "Conferma Password",
                type="password",
                placeholder="••••••••"
            )
            
            col_save, col_cancel = st.columns(2)
            with col_save:
                if st.form_submit_button("💾 Salva", type="primary"):
                    if not new_pwd:
                        st.error("⚠️ Inserisci la nuova password")
                    elif len(new_pwd) < 6:
                        st.error("⚠️ Password troppo corta")
                    elif new_pwd != confirm_pwd:
                        st.error("⚠️ Le password non coincidono")
                    else:
                        user_store.update_password(u.username, new_pwd)
                        del st.session_state[f"change_pwd_{u.username}"]
                        st.success(f"✅ Password aggiornata per {u.username}")
                        st.rerun()
            
            with col_cancel:
                if st.form_submit_button("Annulla"):
                    del st.session_state[f"change_pwd_{u.username}"]
                    st.rerun()
    
    # Conferma eliminazione
    if st.session_state.get(f"confirm_del_{u.username}"):
        st.warning(f"⚠️ Confermi l'eliminazione dell'utente **{u.username}**?")
        st.caption("Questa azione è irreversibile. Le memorie dell'utente rimarranno nel sistema.")
        
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("✅ Sì, elimina", key=f"yes_{u.username}"):
                user_store.delete_user(u.username)
                del st.session_state[f"confirm_del_{u.username}"]
                st.success(f"🗑️ Utente **{u.username}** eliminato")
                _clear_cache()
                st.rerun()
        with col_no:
            if st.button("❌ Annulla", key=f"no_{u.username}"):
                del st.session_state[f"confirm_del_{u.username}"]
                st.rerun()
    
    st.divider()


def _clear_cache():
    """Pulisce cache per refresh dati"""
    st.cache_resource.clear()


@st.cache_resource
def _get_user_store() -> UserStore:
    """Cache user store"""
    return UserStore()

