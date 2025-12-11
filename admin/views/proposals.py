"""
Admin Proposals View
Gestione proposte pending_global con approve/reject workflow
"""

import streamlit as st
import re
from datetime import datetime
from typing import Optional, Tuple
import sys
from pathlib import Path

# Aggiungi root al path
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.store import MemoryStore, MemoryItem, MemoryType
from src.integration.glossary import GlossaryResolver
from src.auth.models import User, Role


def render_proposals(user: User):
    """Gestione proposte pending_global"""
    st.title("📋 Proposte in Attesa")
    
    # Refresh button
    col_title, col_refresh = st.columns([4, 1])
    with col_refresh:
        if st.button("🔄 Aggiorna", use_container_width=True):
            _clear_cache()
            st.rerun()
    
    # Carica dati
    memory_store = _get_memory_store()
    glossary = _get_glossary()
    
    # Carica proposte dal namespace pending_global
    pending = memory_store.get_all(namespace=("pending_global",))
    
    if not pending:
        st.success("✅ Nessuna proposta in attesa di approvazione!")
        st.info("Le proposte degli utenti appariranno qui quando useranno il comando `/propose` nella chat.")
        return
    
    # === FILTRI ===
    col_filter_type, col_filter_search = st.columns([1, 3])
    
    with col_filter_type:
        type_options = ["Tutti"] + [t.value for t in MemoryType]
        type_filter = st.selectbox("Tipo", type_options, key="proposal_type_filter")
    
    with col_filter_search:
        search = st.text_input(
            "🔍 Cerca",
            placeholder="Filtra per contenuto o utente...",
            key="proposal_search"
        )
    
    # Applica filtri
    filtered = pending
    if type_filter != "Tutti":
        filtered = [p for p in filtered if p.type.value == type_filter]
    if search:
        search_lower = search.lower()
        filtered = [
            p for p in filtered 
            if search_lower in p.content.lower() or 
               search_lower in (p.metadata or {}).get("proposed_by", "").lower()
        ]
    
    st.markdown(f"**{len(filtered)}** proposte trovate")
    st.divider()
    
    # === RENDER PROPOSTE ===
    for i, proposal in enumerate(filtered):
        _render_proposal_card(proposal, i, user, memory_store, glossary)


def _render_proposal_card(
    proposal: MemoryItem,
    index: int,
    user: User,
    memory_store: MemoryStore,
    glossary: GlossaryResolver
):
    """Renderizza singola card proposta"""
    metadata = proposal.metadata or {}
    proposer = metadata.get("proposed_by", "unknown")
    proposer_role = metadata.get("proposer_role", "user")
    
    # Container con bordo
    with st.container():
        # Header
        col_header, col_date = st.columns([3, 1])
        with col_header:
            type_icons = {
                MemoryType.FACT: "💡",
                MemoryType.PREFERENCE: "📌",
                MemoryType.CORRECTION: "⚠️",
                MemoryType.PROCEDURE: "📋",
                MemoryType.CONTEXT: "💬"
            }
            icon = type_icons.get(proposal.type, "📝")
            st.markdown(f"### {icon} Proposta #{index + 1}")
        with col_date:
            created = proposal.created_at[:16].replace("T", " ") if proposal.created_at else "N/A"
            st.caption(created)
        
        # Info proposta
        st.markdown(f"""
        **Da:** {proposer} (`{proposer_role}`)  
        **Tipo:** `{proposal.type.value}`
        """)
        
        # Contenuto in box evidenziato
        st.info(f"📝 {proposal.content}")
        
        # === AZIONI ===
        col_approve, col_reject, col_edit = st.columns(3)
        
        # APPROVA - Solo Admin
        with col_approve:
            if user.role == Role.ADMIN:
                if st.button(
                    "✅ Approva",
                    key=f"approve_{proposal.id}",
                    use_container_width=True,
                    type="primary"
                ):
                    _approve_proposal(proposal, memory_store, glossary)
                    st.success("✅ Proposta approvata!")
                    _clear_cache()
                    st.rerun()
            else:
                st.button(
                    "✅ Approva",
                    key=f"approve_disabled_{proposal.id}",
                    disabled=True,
                    help="Solo Admin può approvare",
                    use_container_width=True
                )
        
        # RIFIUTA - Admin e Engineer
        with col_reject:
            if st.button(
                "❌ Rifiuta",
                key=f"reject_{proposal.id}",
                use_container_width=True
            ):
                st.session_state[f"rejecting_{proposal.id}"] = True
        
        # Form rifiuto
        if st.session_state.get(f"rejecting_{proposal.id}"):
            with st.form(key=f"reject_form_{proposal.id}"):
                reason = st.text_input(
                    "Motivo del rifiuto (opzionale)",
                    placeholder="Es: Informazione non corretta..."
                )
                col_confirm, col_cancel = st.columns(2)
                with col_confirm:
                    if st.form_submit_button("Conferma Rifiuto", type="primary"):
                        _reject_proposal(proposal, reason, memory_store, proposer)
                        st.warning("❌ Proposta rifiutata")
                        del st.session_state[f"rejecting_{proposal.id}"]
                        _clear_cache()
                        st.rerun()
                with col_cancel:
                    if st.form_submit_button("Annulla"):
                        del st.session_state[f"rejecting_{proposal.id}"]
                        st.rerun()
        
        # MODIFICA E APPROVA - Solo Admin
        with col_edit:
            if user.role == Role.ADMIN:
                if st.button(
                    "✏️ Modifica",
                    key=f"edit_{proposal.id}",
                    use_container_width=True
                ):
                    st.session_state[f"editing_{proposal.id}"] = True
            else:
                st.button(
                    "✏️ Modifica",
                    key=f"edit_disabled_{proposal.id}",
                    disabled=True,
                    help="Solo Admin può modificare",
                    use_container_width=True
                )
        
        # Form modifica
        if st.session_state.get(f"editing_{proposal.id}"):
            with st.form(key=f"edit_form_{proposal.id}"):
                new_content = st.text_area(
                    "Contenuto modificato",
                    value=proposal.content,
                    height=100
                )
                col_save, col_cancel_edit = st.columns(2)
                with col_save:
                    if st.form_submit_button("💾 Salva e Approva", type="primary"):
                        proposal.content = new_content
                        _approve_proposal(proposal, memory_store, glossary)
                        st.success("✅ Modificata e Approvata!")
                        del st.session_state[f"editing_{proposal.id}"]
                        _clear_cache()
                        st.rerun()
                with col_cancel_edit:
                    if st.form_submit_button("Annulla"):
                        del st.session_state[f"editing_{proposal.id}"]
                        st.rerun()
        
        st.divider()


def _approve_proposal(
    proposal: MemoryItem,
    memory_store: MemoryStore,
    glossary: GlossaryResolver
):
    """Approva proposta e sposta in global"""
    
    # 1. Se è una definizione acronimo, aggiungila al glossario
    acronym_match = _extract_acronym_definition(proposal.content)
    if acronym_match:
        acronym, definition = acronym_match
        try:
            glossary.add_acronym(
                acronym=acronym,
                full=definition,
                description=f"Approvato da admin - {datetime.now().strftime('%Y-%m-%d')}",
                save=True
            )
        except Exception as e:
            st.warning(f"⚠️ Errore aggiunta glossario: {e}")
    
    # 2. Aggiungi memoria al namespace global
    memory_store.put(
        content=proposal.content,
        mem_type=proposal.type,
        namespace=("global",),
        source="admin_approved",
        confidence=0.9,
        metadata={
            "approved_at": datetime.now().isoformat(),
            "original_proposer": (proposal.metadata or {}).get("proposed_by", "unknown"),
            "original_id": proposal.id
        }
    )
    
    # 3. Elimina da pending_global
    memory_store.delete(proposal.id, namespace=("pending_global",))


def _reject_proposal(
    proposal: MemoryItem,
    reason: str,
    memory_store: MemoryStore,
    proposer: str
):
    """Rifiuta proposta e opzionalmente sposta nel namespace utente"""
    
    # Aggiorna metadata con info rifiuto
    metadata = proposal.metadata or {}
    metadata["rejected"] = True
    metadata["reject_reason"] = reason
    metadata["rejected_at"] = datetime.now().isoformat()
    
    # Opzionale: salva nel namespace personale dell'utente come "rifiutata"
    # (commentato per ora - la proposta viene semplicemente eliminata)
    # if proposer and proposer != "unknown":
    #     memory_store.put(
    #         content=proposal.content,
    #         mem_type=proposal.type,
    #         namespace=(f"user_{proposer}",),
    #         source="rejected_proposal",
    #         confidence=0.3,
    #         metadata=metadata
    #     )
    
    # Elimina da pending_global
    memory_store.delete(proposal.id, namespace=("pending_global",))


def _extract_acronym_definition(content: str) -> Optional[Tuple[str, str]]:
    """
    Estrae acronimo e definizione dal contenuto.
    
    Patterns supportati:
    - "ABC = Definizione"
    - "ABC significa Definizione"
    - "ABC vuol dire Definizione"
    - "ABC sta per Definizione"
    
    Returns:
        Tuple (acronimo, definizione) o None
    """
    patterns = [
        r'([A-Z]{2,6})\s*=\s*(.+)',
        r'([A-Z]{2,6})\s+significa\s+(.+)',
        r'([A-Z]{2,6})\s+vuol\s+dire\s+(.+)',
        r'([A-Z]{2,6})\s+sta\s+per\s+(.+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            acronym = match.group(1).upper()
            definition = match.group(2).strip().rstrip(".")
            return (acronym, definition)
    
    return None


def _clear_cache():
    """Pulisce cache per refresh dati"""
    st.cache_resource.clear()


@st.cache_resource
def _get_memory_store() -> MemoryStore:
    """Cache memory store"""
    return MemoryStore(config_path="config/config.yaml")


@st.cache_resource
def _get_glossary() -> GlossaryResolver:
    """Cache glossary"""
    return GlossaryResolver(config_path="config/config.yaml")

