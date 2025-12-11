"""
Admin Glossary View
CRUD acronimi con paginazione
"""

import streamlit as st
from typing import List, Dict, Any
import sys
from pathlib import Path

# Aggiungi root al path
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.integration.glossary import GlossaryResolver
from src.auth.models import User, Role

ITEMS_PER_PAGE = 15


def render_glossary(user: User):
    """Gestione glossario con CRUD e paginazione"""
    st.title("📚 Gestione Glossario")
    
    # Carica glossario
    glossary = _get_glossary()
    
    # === FORM AGGIUNGI NUOVO ===
    with st.expander("➕ Aggiungi Nuovo Acronimo", expanded=False):
        _render_add_form(glossary, user)
    
    st.divider()
    
    # === RICERCA E STATS ===
    col_search, col_stats = st.columns([3, 1])
    
    with col_search:
        search = st.text_input(
            "🔍 Cerca",
            placeholder="Filtra per acronimo, significato o descrizione...",
            key="glossary_search"
        )
    
    with col_stats:
        total = len(glossary.acronyms)
        ambiguous = sum(1 for d in glossary.acronyms.values() if d.get("ambiguous", False))
        st.metric("Totale", f"{total} ({ambiguous} ambigui)")
    
    # === TABELLA GLOSSARIO ===
    # Prepara dati
    data = _prepare_glossary_data(glossary, search)
    
    if not data:
        st.info("📭 Nessun acronimo trovato" if search else "📭 Glossario vuoto")
        return
    
    # Paginazione
    total_items = len(data)
    total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    
    if "glossary_page" not in st.session_state:
        st.session_state.glossary_page = 0
    
    # Limita pagina corrente
    st.session_state.glossary_page = min(st.session_state.glossary_page, total_pages - 1)
    
    page = st.session_state.glossary_page
    start_idx = page * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
    
    page_data = data[start_idx:end_idx]
    
    st.markdown(f"Mostrando **{start_idx + 1}-{end_idx}** di **{total_items}** acronimi")
    
    # Header tabella
    col_acr, col_full, col_desc, col_actions = st.columns([1, 2, 2, 1])
    with col_acr:
        st.markdown("**Acronimo**")
    with col_full:
        st.markdown("**Significato**")
    with col_desc:
        st.markdown("**Descrizione**")
    with col_actions:
        st.markdown("**Azioni**")
    
    st.divider()
    
    # Render righe
    for item in page_data:
        _render_glossary_row(item, glossary, user)
    
    # === PAGINAZIONE ===
    st.divider()
    col_prev, col_info, col_next = st.columns([1, 2, 1])
    
    with col_prev:
        if st.button("◀ Precedente", disabled=page == 0, use_container_width=True):
            st.session_state.glossary_page -= 1
            st.rerun()
    
    with col_info:
        st.markdown(f"**Pagina {page + 1} di {total_pages}**", unsafe_allow_html=True)
    
    with col_next:
        if st.button("Successivo ▶", disabled=page >= total_pages - 1, use_container_width=True):
            st.session_state.glossary_page += 1
            st.rerun()


def _render_add_form(glossary: GlossaryResolver, user: User):
    """Form per aggiungere nuovo acronimo"""
    with st.form("add_acronym_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            new_acronym = st.text_input(
                "Acronimo *",
                max_chars=10,
                placeholder="ES: WCM",
                help="2-10 caratteri, verrà convertito in maiuscolo"
            )
        
        with col2:
            new_full = st.text_input(
                "Significato *",
                placeholder="ES: World Class Manufacturing"
            )
        
        new_desc = st.text_area(
            "Descrizione (opzionale)",
            placeholder="Descrizione estesa dell'acronimo...",
            height=80
        )
        
        submitted = st.form_submit_button(
            "➕ Aggiungi Acronimo",
            type="primary",
            use_container_width=True
        )
        
        if submitted:
            if not new_acronym or not new_full:
                st.error("⚠️ Acronimo e Significato sono obbligatori")
            elif len(new_acronym) < 2:
                st.error("⚠️ Acronimo deve avere almeno 2 caratteri")
            else:
                acronym_upper = new_acronym.upper().strip()
                
                # Verifica se esiste già
                if acronym_upper in glossary.acronyms:
                    st.warning(f"⚠️ L'acronimo **{acronym_upper}** esiste già. Usa modifica per aggiornarlo.")
                else:
                    success = glossary.add_acronym(
                        acronym=acronym_upper,
                        full=new_full.strip(),
                        description=new_desc.strip() if new_desc else "",
                        save=True
                    )
                    
                    if success:
                        st.success(f"✅ Acronimo **{acronym_upper}** aggiunto con successo!")
                        _clear_cache()
                        st.rerun()
                    else:
                        st.error("❌ Errore durante l'aggiunta")


def _prepare_glossary_data(glossary: GlossaryResolver, search: str) -> List[Dict[str, Any]]:
    """Prepara dati glossario con filtro ricerca"""
    data = []
    search_lower = search.lower() if search else ""
    
    for acr, info in sorted(glossary.acronyms.items()):
        # Gestisci acronimi ambigui
        if info.get("ambiguous", False):
            full = f"⚠️ Ambiguo ({len(info.get('definitions', []))} definizioni)"
            desc = "Clicca modifica per vedere tutte le definizioni"
            is_ambiguous = True
        else:
            full = info.get("full", "")
            desc = info.get("description", "")
            is_ambiguous = False
        
        # Applica filtro ricerca
        if search_lower:
            if not (
                search_lower in acr.lower() or
                search_lower in full.lower() or
                search_lower in desc.lower()
            ):
                continue
        
        data.append({
            "acronym": acr,
            "full": full,
            "description": desc,
            "is_ambiguous": is_ambiguous,
            "_raw": info
        })
    
    return data


def _render_glossary_row(item: Dict, glossary: GlossaryResolver, user: User):
    """Renderizza riga glossario"""
    col_acr, col_full, col_desc, col_actions = st.columns([1, 2, 2, 1])
    
    acronym = item["acronym"]
    
    with col_acr:
        if item["is_ambiguous"]:
            st.markdown(f"**{acronym}** ⚠️")
        else:
            st.markdown(f"**{acronym}**")
    
    with col_full:
        full_display = item["full"][:40] + "..." if len(item["full"]) > 40 else item["full"]
        st.write(full_display)
    
    with col_desc:
        desc_display = item["description"][:35] + "..." if len(item["description"]) > 35 else item["description"]
        st.caption(desc_display if desc_display else "-")
    
    with col_actions:
        col_edit, col_del = st.columns(2)
        
        with col_edit:
            if st.button("✏️", key=f"edit_g_{acronym}", help="Modifica"):
                st.session_state[f"editing_g_{acronym}"] = True
        
        with col_del:
            # Solo Admin può eliminare
            if user.role == Role.ADMIN:
                if st.button("🗑️", key=f"del_g_{acronym}", help="Elimina"):
                    st.session_state[f"confirm_del_g_{acronym}"] = True
            else:
                st.button("🗑️", key=f"del_g_dis_{acronym}", disabled=True, help="Solo Admin")
    
    # Form modifica inline
    if st.session_state.get(f"editing_g_{acronym}"):
        _render_edit_form(acronym, item, glossary, user)
    
    # Conferma eliminazione
    if st.session_state.get(f"confirm_del_g_{acronym}"):
        st.warning(f"⚠️ Confermi eliminazione di **{acronym}**?")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("✅ Sì, elimina", key=f"confirm_yes_{acronym}"):
                glossary.remove_acronym(acronym, save=True)
                del st.session_state[f"confirm_del_g_{acronym}"]
                st.success(f"🗑️ Acronimo **{acronym}** eliminato")
                _clear_cache()
                st.rerun()
        with col_no:
            if st.button("❌ Annulla", key=f"confirm_no_{acronym}"):
                del st.session_state[f"confirm_del_g_{acronym}"]
                st.rerun()


def _render_edit_form(acronym: str, item: Dict, glossary: GlossaryResolver, user: User):
    """Form modifica inline"""
    raw_data = item["_raw"]
    
    with st.form(key=f"edit_form_g_{acronym}"):
        st.markdown(f"**Modifica: {acronym}**")
        
        if item["is_ambiguous"]:
            # Mostra tutte le definizioni per acronimi ambigui
            st.info("⚠️ Questo acronimo ha definizioni multiple:")
            definitions = raw_data.get("definitions", [])
            for i, defn in enumerate(definitions):
                st.markdown(f"""
                - **Contesto:** {defn.get('context', 'N/A')}
                - **Significato:** {defn.get('full', '')}
                - **Descrizione:** {defn.get('description', '')}
                """)
            
            st.warning("La modifica di acronimi ambigui richiede intervento manuale su glossary.json")
            new_full = ""
            new_desc = ""
        else:
            new_full = st.text_input(
                "Significato",
                value=raw_data.get("full", "")
            )
            new_desc = st.text_area(
                "Descrizione",
                value=raw_data.get("description", ""),
                height=80
            )
        
        col_save, col_cancel = st.columns(2)
        
        with col_save:
            if st.form_submit_button("💾 Salva", type="primary"):
                if not item["is_ambiguous"] and new_full:
                    glossary.acronyms[acronym]["full"] = new_full.strip()
                    glossary.acronyms[acronym]["description"] = new_desc.strip()
                    glossary.save_to_file()
                    
                    del st.session_state[f"editing_g_{acronym}"]
                    st.success(f"✅ Acronimo **{acronym}** aggiornato")
                    _clear_cache()
                    st.rerun()
                elif item["is_ambiguous"]:
                    del st.session_state[f"editing_g_{acronym}"]
                    st.rerun()
        
        with col_cancel:
            if st.form_submit_button("Annulla"):
                del st.session_state[f"editing_g_{acronym}"]
                st.rerun()


def _clear_cache():
    """Pulisce cache per refresh dati"""
    st.cache_resource.clear()


@st.cache_resource
def _get_glossary() -> GlossaryResolver:
    """Cache glossary"""
    return GlossaryResolver(config_path="config/config.yaml")

