"""
Admin Memories View
Browser memorie per namespace con visualizzazione e promozione
"""

import streamlit as st
from typing import List
import sys
from pathlib import Path

# Aggiungi root al path
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.store import MemoryStore, MemoryItem, MemoryType
from src.auth.models import User, Role


def render_memories(user: User):
    """Browser memorie per namespace"""
    st.title("🧠 Gestione Memorie")
    
    # Carica memory store
    memory_store = _get_memory_store()
    stats = memory_store.get_stats()
    
    # === SELETTORI ===
    col_ns, col_type, col_search = st.columns([2, 2, 3])
    
    # Lista namespace disponibili
    namespaces = list(stats.get("by_namespace", {}).keys())
    if not namespaces:
        namespaces = ["global"]
    
    with col_ns:
        selected_ns = st.selectbox(
            "📁 Namespace",
            namespaces,
            index=0,
            key="mem_namespace"
        )
    
    with col_type:
        type_options = ["Tutti"] + [t.value for t in MemoryType]
        selected_type = st.selectbox(
            "🏷️ Tipo",
            type_options,
            key="mem_type"
        )
    
    with col_search:
        search = st.text_input(
            "🔍 Cerca",
            placeholder="Filtra per contenuto...",
            key="mem_search"
        )
    
    st.divider()
    
    # === STATISTICHE NAMESPACE ===
    ns_count = stats.get("by_namespace", {}).get(selected_ns, 0)
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    
    with col_stat1:
        st.metric("Memorie nel namespace", ns_count)
    
    with col_stat2:
        avg_boost = _calculate_namespace_avg_boost(memory_store, selected_ns)
        st.metric("Boost medio", f"{avg_boost:.2f}x")
    
    with col_stat3:
        st.metric("Namespace", selected_ns[:20] + "..." if len(selected_ns) > 20 else selected_ns)
    
    st.divider()
    
    # === CARICA MEMORIE ===
    mem_type = None if selected_type == "Tutti" else MemoryType(selected_type)
    memories = memory_store.get_all(namespace=(selected_ns,), mem_type=mem_type)
    
    # Applica filtro ricerca
    if search:
        search_lower = search.lower()
        memories = [m for m in memories if search_lower in m.content.lower()]
    
    # Ordina per effective_confidence decrescente
    memories.sort(key=lambda x: x.effective_confidence, reverse=True)
    
    if not memories:
        st.info("📭 Nessuna memoria trovata con i filtri selezionati")
        return
    
    st.markdown(f"**{len(memories)}** memorie trovate")
    
    # === RENDER MEMORIE ===
    for memory in memories:
        _render_memory_card(memory, selected_ns, memory_store, user)


def _render_memory_card(
    memory: MemoryItem,
    namespace: str,
    memory_store: MemoryStore,
    user: User
):
    """Renderizza card memoria"""
    
    # Icon per tipo
    type_icons = {
        MemoryType.PREFERENCE: "📌",
        MemoryType.FACT: "💡",
        MemoryType.CORRECTION: "⚠️",
        MemoryType.PROCEDURE: "📋",
        MemoryType.CONTEXT: "💬"
    }
    icon = type_icons.get(memory.type, "📝")
    
    with st.container():
        # Header
        col_header, col_boost = st.columns([3, 1])
        
        with col_header:
            # ID troncato
            short_id = memory.id[:20] + "..." if len(memory.id) > 20 else memory.id
            st.markdown(f"### {icon} `{short_id}`")
        
        with col_boost:
            # Colore boost
            if memory.boost_factor > 1.0:
                boost_color = "green"
            elif memory.boost_factor < 1.0:
                boost_color = "red"
            else:
                boost_color = "gray"
            
            st.markdown(f"**Boost:** :{boost_color}[{memory.boost_factor:.2f}x]")
        
        # Contenuto
        st.info(memory.content)
        
        # Stats inline
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        
        with col_s1:
            st.caption(f"**Tipo:** `{memory.type.value}`")
        
        with col_s2:
            st.caption(f"**Source:** `{memory.source}`")
        
        with col_s3:
            st.caption(f"**Accessi:** {memory.access_count}")
        
        with col_s4:
            conf_pct = f"{memory.effective_confidence:.0%}"
            st.caption(f"**Conf:** {conf_pct}")
        
        # Feedback history
        if memory.feedback_history:
            positive = sum(1 for f in memory.feedback_history if f.is_positive)
            negative = len(memory.feedback_history) - positive
            ratio_pct = f"{memory.positive_ratio:.0%}"
            st.caption(f"**Feedback:** 👍 {positive} | 👎 {negative} | Ratio: {ratio_pct}")
        
        # Metadata
        if memory.metadata:
            with st.expander("📋 Metadata", expanded=False):
                st.json(memory.metadata)
        
        # === AZIONI ===
        col_del, col_promote, col_details = st.columns(3)
        
        with col_del:
            if st.button(
                "🗑️ Elimina",
                key=f"del_mem_{memory.id}",
                use_container_width=True
            ):
                st.session_state[f"confirm_del_mem_{memory.id}"] = True
        
        with col_promote:
            # Promuovi a global (solo se non è già in global e user è admin)
            if namespace != "global" and user.role == Role.ADMIN:
                if st.button(
                    "📤 Promuovi",
                    key=f"promote_mem_{memory.id}",
                    use_container_width=True,
                    help="Copia questa memoria nel namespace global"
                ):
                    _promote_to_global(memory, memory_store)
                    st.success("✅ Promossa a Global!")
                    _clear_cache()
                    st.rerun()
            else:
                st.button(
                    "📤 Promuovi",
                    key=f"promote_dis_{memory.id}",
                    disabled=True,
                    use_container_width=True,
                    help="Non disponibile per questo namespace/ruolo"
                )
        
        with col_details:
            # Mostra dettagli
            if st.button(
                "🔍 Dettagli",
                key=f"details_mem_{memory.id}",
                use_container_width=True
            ):
                st.session_state[f"show_details_{memory.id}"] = not st.session_state.get(f"show_details_{memory.id}", False)
        
        # Conferma eliminazione
        if st.session_state.get(f"confirm_del_mem_{memory.id}"):
            st.warning("⚠️ Confermi l'eliminazione di questa memoria?")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("✅ Sì, elimina", key=f"yes_del_{memory.id}"):
                    memory_store.delete(memory.id, namespace=(namespace,))
                    del st.session_state[f"confirm_del_mem_{memory.id}"]
                    st.success("🗑️ Memoria eliminata")
                    _clear_cache()
                    st.rerun()
            with col_no:
                if st.button("❌ Annulla", key=f"no_del_{memory.id}"):
                    del st.session_state[f"confirm_del_mem_{memory.id}"]
                    st.rerun()
        
        # Dettagli espansi
        if st.session_state.get(f"show_details_{memory.id}"):
            with st.expander("📊 Dettagli Completi", expanded=True):
                st.markdown(f"""
                **ID Completo:** `{memory.id}`
                
                **Timestamps:**
                - Creato: `{memory.created_at}`
                - Aggiornato: `{memory.updated_at}`
                
                **Confidence:**
                - Base: {memory.base_confidence:.2f}
                - Boost: {memory.boost_factor:.2f}x
                - Effettiva: {memory.effective_confidence:.2%}
                
                **Documenti correlati:** {memory.related_docs or "Nessuno"}
                """)
                
                if memory.feedback_history:
                    st.markdown("**Storico Feedback:**")
                    for i, fb in enumerate(memory.feedback_history[-5:]):  # Ultimi 5
                        emoji = "👍" if fb.is_positive else "👎"
                        st.caption(f"{emoji} `{fb.timestamp[:16]}` - {fb.context[:50] if fb.context else 'N/A'}")
        
        st.divider()


def _promote_to_global(memory: MemoryItem, memory_store: MemoryStore):
    """Promuove memoria al namespace global"""
    from datetime import datetime
    
    memory_store.put(
        content=memory.content,
        mem_type=memory.type,
        namespace=("global",),
        source="promoted_from_admin",
        confidence=memory.effective_confidence,
        metadata={
            "promoted_at": datetime.now().isoformat(),
            "original_id": memory.id,
            "original_source": memory.source
        }
    )


def _calculate_namespace_avg_boost(memory_store: MemoryStore, namespace: str) -> float:
    """Calcola boost medio per namespace"""
    memories = memory_store.get_all(namespace=(namespace,))
    if not memories:
        return 1.0
    
    total_boost = sum(m.boost_factor for m in memories)
    return total_boost / len(memories)


def _clear_cache():
    """Pulisce cache per refresh dati"""
    st.cache_resource.clear()


@st.cache_resource
def _get_memory_store() -> MemoryStore:
    """Cache memory store"""
    return MemoryStore(config_path="config/config.yaml")

