"""
Admin View: Consensus Management
R08-R10: Gestione consenso multi-utente e promozione memorie

Created: 2025-12-08

Features:
- Dashboard consenso con statistiche
- Lista candidati per promozione
- Approvazione/Rifiuto manuale
- Monitoraggio segnali impliciti
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def render_consensus_view(user: dict):
    """
    Renderizza vista consenso per Admin Panel.
    
    Args:
        user: Utente autenticato
    """
    st.title("🤝 Consenso Multi-Utente")
    st.caption("R08-R10: Apprendimento implicito e promozione memorie condivise")
    
    # Tab per diverse sezioni
    tabs = st.tabs([
        "📊 Dashboard",
        "📋 Candidati",
        "✅ Promozioni",
        "📡 Segnali",
        "⚙️ Config"
    ])
    
    with tabs[0]:
        _render_dashboard_tab()
    
    with tabs[1]:
        _render_candidates_tab(user)
    
    with tabs[2]:
        _render_promotions_tab()
    
    with tabs[3]:
        _render_signals_tab()
    
    with tabs[4]:
        _render_config_tab(user)


def _render_dashboard_tab():
    """Dashboard con metriche principali"""
    st.subheader("📊 Metriche Consenso")
    
    try:
        from src.learning.learners import get_implicit_learner
        learner = get_implicit_learner()
        stats = learner.get_learning_stats()
    except ImportError:
        st.warning("⚠️ Modulo Learning non disponibile")
        stats = _get_mock_stats()
    except Exception as e:
        st.error(f"Errore caricamento stats: {e}")
        stats = _get_mock_stats()
    
    # Metriche principali
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Segnali Totali",
            stats.get("signals", {}).get("total", 0),
            help="Segnali impliciti raccolti"
        )
    
    with col2:
        st.metric(
            "Candidati Pronti",
            stats.get("promotions", {}).get("ready_for_promotion", 0),
            help="Memorie pronte per promozione a globale"
        )
    
    with col3:
        st.metric(
            "Promozioni Totali",
            stats.get("promotions", {}).get("promoted_total", 0),
            help="Memorie promosse da user→global"
        )
    
    with col4:
        positive_ratio = stats.get("signals", {}).get("positive_ratio", 0)
        st.metric(
            "Ratio Positivi",
            f"{positive_ratio:.0%}",
            help="Percentuale segnali positivi"
        )
    
    st.divider()
    
    # Charts
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.markdown("#### Distribuzione Segnali per Tipo")
        by_type = stats.get("signals", {}).get("by_type", {})
        if by_type:
            df = pd.DataFrame([
                {"Tipo": k, "Count": v}
                for k, v in by_type.items()
            ])
            st.bar_chart(df.set_index("Tipo"))
        else:
            st.info("Nessun segnale registrato")
    
    with col_right:
        st.markdown("#### Candidati per Tipo Memoria")
        consensus_stats = stats.get("consensus", {}).get("by_type", {})
        if consensus_stats and any(consensus_stats.values()):
            df = pd.DataFrame([
                {"Tipo": k, "Count": v}
                for k, v in consensus_stats.items()
            ])
            st.bar_chart(df.set_index("Tipo"))
        else:
            st.info("Nessun candidato registrato")
    
    # Top candidates preview
    st.divider()
    st.markdown("#### 🔝 Top Candidati")
    
    top_candidates = stats.get("consensus", {}).get("top_candidates", [])
    
    if top_candidates:
        for i, c in enumerate(top_candidates[:5]):
            with st.container():
                col1, col2, col3 = st.columns([6, 2, 2])
                with col1:
                    st.text(f"{i+1}. {c['content']}")
                with col2:
                    st.caption(f"Voters: {c['voters']}")
                with col3:
                    st.caption(f"Score: {c['score']:.2f}")
    else:
        st.info("Nessun candidato con score significativo")


def _render_candidates_tab(user: dict):
    """Lista candidati per approvazione/rifiuto"""
    st.subheader("📋 Candidati per Promozione")
    
    try:
        from src.learning.consensus import VotingTracker, GlobalPromoter
        tracker = VotingTracker()
        promoter = GlobalPromoter(tracker)
    except ImportError:
        st.warning("⚠️ Modulo Consensus non disponibile")
        return
    
    # Filtri
    col1, col2 = st.columns(2)
    with col1:
        filter_type = st.selectbox(
            "Tipo Memoria",
            ["Tutti", "fact", "preference", "procedure"]
        )
    with col2:
        filter_status = st.selectbox(
            "Status",
            ["pending", "promoted", "rejected"]
        )
    
    # Carica candidati
    candidates = tracker.get_all_candidates(status=filter_status if filter_status != "Tutti" else None)
    
    if filter_type != "Tutti":
        candidates = [c for c in candidates if c.memory_type == filter_type]
    
    st.caption(f"Totale: {len(candidates)} candidati")
    
    if not candidates:
        st.info("Nessun candidato trovato con questi filtri")
        return
    
    # Lista candidati
    for candidate in candidates:
        with st.expander(
            f"{'🟢' if candidate.status == 'pending' else '⚪'} {candidate.content[:60]}...",
            expanded=False
        ):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"**Contenuto completo:**")
                st.text_area("", candidate.content, height=100, disabled=True, key=f"content_{candidate.content_hash}")
                
                st.markdown(f"**Tipo:** `{candidate.memory_type}`")
                st.markdown(f"**Voters:** {candidate.voter_count}")
                st.markdown(f"**Score consenso:** {candidate.consensus_score:.3f}")
                
                if candidate.first_seen:
                    st.markdown(f"**Prima vista:** {candidate.first_seen.strftime('%Y-%m-%d %H:%M')}")
            
            with col2:
                st.markdown("**Azioni:**")
                
                if candidate.status == "pending":
                    # Pulsanti azione
                    if st.button("✅ Approva", key=f"approve_{candidate.content_hash}"):
                        result = promoter.force_promote(candidate.content_hash)
                        if result:
                            st.success(f"Promosso a {result['namespace']}!")
                            st.rerun()
                        else:
                            st.error("Errore nella promozione")
                    
                    reason = st.text_input(
                        "Motivo rifiuto",
                        key=f"reason_{candidate.content_hash}",
                        placeholder="Opzionale"
                    )
                    
                    if st.button("❌ Rifiuta", key=f"reject_{candidate.content_hash}"):
                        if promoter.reject_candidate(candidate.content_hash, reason):
                            st.success("Candidato rifiutato")
                            st.rerun()
                        else:
                            st.error("Errore nel rifiuto")
                
                elif candidate.status == "promoted":
                    st.success("✅ Promosso")
                    if candidate.last_vote:
                        st.caption(f"Promosso il {candidate.last_vote.strftime('%Y-%m-%d')}")
                
                elif candidate.status == "rejected":
                    st.error("❌ Rifiutato")
            
            # Lista voters
            if candidate.unique_voters:
                st.markdown("**Utenti:**")
                st.write(", ".join(list(candidate.unique_voters)[:10]))


def _render_promotions_tab():
    """Storico promozioni"""
    st.subheader("✅ Storico Promozioni")
    
    try:
        from src.learning.consensus import VotingTracker
        tracker = VotingTracker()
    except ImportError:
        st.warning("⚠️ Modulo Consensus non disponibile")
        return
    
    promoted = tracker.get_all_candidates(status="promoted")
    
    if not promoted:
        st.info("Nessuna memoria promossa ancora")
        return
    
    # Tabella promozioni
    data = []
    for c in promoted:
        data.append({
            "Contenuto": c.content[:50] + "..." if len(c.content) > 50 else c.content,
            "Tipo": c.memory_type,
            "Voters": c.voter_count,
            "Score": f"{c.consensus_score:.2f}",
            "Data": c.last_vote.strftime("%Y-%m-%d") if c.last_vote else "N/A"
        })
    
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True)
    
    # Stats
    st.divider()
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Totale Promozioni", len(promoted))
    
    with col2:
        avg_voters = sum(c.voter_count for c in promoted) / len(promoted) if promoted else 0
        st.metric("Media Voters", f"{avg_voters:.1f}")
    
    with col3:
        avg_score = sum(c.consensus_score for c in promoted) / len(promoted) if promoted else 0
        st.metric("Score Medio", f"{avg_score:.2f}")


def _render_signals_tab():
    """Monitoraggio segnali impliciti"""
    st.subheader("📡 Segnali Impliciti")
    
    try:
        from src.learning.signals import get_signal_collector, SignalType
        collector = get_signal_collector()
    except ImportError:
        st.warning("⚠️ Modulo Signals non disponibile")
        return
    
    # Stats generali
    stats = collector.get_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Totale Segnali", stats.get("total", 0))
    
    with col2:
        st.metric("Utenti Unici", stats.get("unique_users", 0))
    
    with col3:
        st.metric("Segnali +", stats.get("positive_signals", 0))
    
    with col4:
        st.metric("Segnali -", stats.get("negative_signals", 0))
    
    st.divider()
    
    # Distribuzione per tipo
    st.markdown("#### Distribuzione per Tipo di Segnale")
    
    by_type = stats.get("by_type", {})
    
    if by_type:
        # Raggruppa per categoria
        positive_types = {
            "click_source", "copy_text", "dwell_time", "follow_up",
            "teach_complete", "acronym_click", "session_good", "memory_confirmed"
        }
        negative_types = {
            "quick_dismiss", "re_ask", "retry_different", "teach_abort", "memory_rejected"
        }
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**🟢 Segnali Positivi:**")
            for sig_type, count in sorted(by_type.items()):
                if sig_type in positive_types:
                    st.write(f"• `{sig_type}`: {count}")
        
        with col2:
            st.markdown("**🔴 Segnali Negativi:**")
            for sig_type, count in sorted(by_type.items()):
                if sig_type in negative_types:
                    st.write(f"• `{sig_type}`: {count}")
        
        # Altri
        other = {k: v for k, v in by_type.items() if k not in positive_types and k not in negative_types}
        if other:
            st.markdown("**⚪ Altri:**")
            for sig_type, count in sorted(other.items()):
                st.write(f"• `{sig_type}`: {count}")
    else:
        st.info("Nessun segnale registrato")
    
    # Session attive
    st.divider()
    st.markdown(f"**Sessioni attive:** {stats.get('active_sessions', 0)}")


def _render_config_tab(user: dict):
    """Configurazione consenso"""
    st.subheader("⚙️ Configurazione")
    
    # Solo admin può modificare
    is_admin = user.get("role") == "admin"
    
    try:
        from src.learning.learners import get_implicit_learner
        from src.learning.consensus.voting_tracker import VotingTracker
        learner = get_implicit_learner()
    except ImportError:
        st.warning("⚠️ Modulo Learning non disponibile")
        return
    
    st.markdown("#### Soglie Consenso")
    
    col1, col2 = st.columns(2)
    
    with col1:
        min_voters = st.number_input(
            "Minimo Voters per Promozione",
            min_value=2,
            max_value=10,
            value=VotingTracker.MIN_UNIQUE_VOTERS,
            disabled=not is_admin,
            help="Numero minimo di utenti unici che devono votare"
        )
        
        min_score = st.slider(
            "Score Minimo per Promozione",
            min_value=0.5,
            max_value=1.0,
            value=VotingTracker.MIN_CONSENSUS_SCORE,
            step=0.05,
            disabled=not is_admin,
            help="Score consenso minimo richiesto"
        )
    
    with col2:
        similarity_threshold = st.slider(
            "Soglia Similarità Contenuto",
            min_value=0.5,
            max_value=1.0,
            value=VotingTracker.SIMILARITY_THRESHOLD,
            step=0.05,
            disabled=not is_admin,
            help="Soglia per considerare due contenuti simili"
        )
        
        require_approval = st.checkbox(
            "Richiedi Approvazione Admin",
            value=learner.promoter.require_admin_approval,
            disabled=not is_admin,
            help="Se attivo, le promozioni vanno in pending_global"
        )
    
    st.divider()
    
    st.markdown("#### Feature Toggle")
    
    col1, col2 = st.columns(2)
    
    with col1:
        auto_memory = st.checkbox(
            "Auto-Save Preferenze",
            value=learner.enable_auto_memory,
            disabled=not is_admin,
            help="Salva automaticamente preferenze rilevate"
        )
    
    with col2:
        consensus_enabled = st.checkbox(
            "Consenso Multi-Utente",
            value=learner.enable_consensus,
            disabled=not is_admin,
            help="Attiva voting per promozione user→global"
        )
    
    if is_admin:
        st.divider()
        
        if st.button("💾 Salva Configurazione"):
            st.warning("⚠️ Salvataggio configurazione non ancora implementato")
            # TODO: Persist config changes
        
        st.divider()
        
        st.markdown("#### Azioni Admin")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Run Consensus Check"):
                promotions = learner.run_consensus_check()
                if promotions:
                    st.success(f"✅ {len(promotions)} promozioni effettuate!")
                else:
                    st.info("Nessun candidato pronto per promozione")
        
        with col2:
            if st.button("📊 Run Nightly Analysis"):
                summary = learner.run_nightly_analysis()
                st.json(summary)
    else:
        st.info("Solo gli admin possono modificare la configurazione")


def _get_mock_stats() -> dict:
    """Stats mock per testing/fallback"""
    return {
        "signals": {
            "total": 0,
            "by_type": {},
            "unique_users": 0,
            "positive_signals": 0,
            "negative_signals": 0,
            "positive_ratio": 0,
            "active_sessions": 0
        },
        "consensus": {
            "total_candidates": 0,
            "ready_for_promotion": 0,
            "by_type": {"fact": 0, "preference": 0, "procedure": 0},
            "by_status": {"pending": 0, "promoted": 0, "rejected": 0},
            "top_candidates": []
        },
        "promotions": {
            "pending_candidates": 0,
            "promoted_total": 0,
            "rejected_total": 0,
            "ready_for_promotion": 0,
            "require_admin_approval": True,
            "top_candidates": []
        },
        "config": {
            "auto_memory": True,
            "consensus_enabled": True
        }
    }

