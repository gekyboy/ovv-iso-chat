"""
Vista Admin Panel per cronologia conversazioni
R28 - Conversation History Viewer

Created: 2025-12-09
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import Optional
import os

from src.analytics.collectors.conversation_logger import get_conversation_logger


def render_conversations_view(user_role: str):
    """
    Renderizza vista cronologia conversazioni.
    
    Args:
        user_role: Ruolo utente ("admin" o "engineer")
    """
    st.header("💬 Cronologia Conversazioni")
    
    conv_logger = get_conversation_logger()
    
    # ═══════════════════════════════════════════════════════════════
    # FILTRI
    # ═══════════════════════════════════════════════════════════════
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        date_range = st.selectbox(
            "Periodo",
            ["Oggi", "Ultimi 7 giorni", "Ultimi 30 giorni", "Personalizzato"],
            index=1
        )
    
    with col2:
        if date_range == "Personalizzato":
            date_from = st.date_input("Da", value=datetime.now() - timedelta(days=7))
            date_to = st.date_input("A", value=datetime.now())
        else:
            if date_range == "Oggi":
                date_from = date_to = datetime.now().date()
            elif date_range == "Ultimi 7 giorni":
                date_from = datetime.now().date() - timedelta(days=7)
                date_to = datetime.now().date()
            else:  # 30 giorni
                date_from = datetime.now().date() - timedelta(days=30)
                date_to = datetime.now().date()
    
    with col3:
        user_filter = st.text_input("Filtra per utente", placeholder="es: mario")
    
    # ═══════════════════════════════════════════════════════════════
    # STATISTICHE
    # ═══════════════════════════════════════════════════════════════
    
    st.subheader("📊 Statistiche Periodo")
    
    # Raccogli sessioni per ogni giorno
    all_sessions = []
    current = date_from
    while current <= date_to:
        all_sessions.extend(
            conv_logger.get_sessions_for_date(current.strftime("%Y-%m-%d"))
        )
        current += timedelta(days=1)
    
    # Filtra per utente
    if user_filter:
        all_sessions = [s for s in all_sessions if user_filter.lower() in s.user_id.lower()]
    
    if not all_sessions:
        st.info("Nessuna sessione trovata per i filtri selezionati.")
        return
    
    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    
    total_interactions = sum(s.total_interactions for s in all_sessions)
    unique_users = len(set(s.user_id for s in all_sessions))
    positive = sum(s.positive_feedback_count for s in all_sessions)
    negative = sum(s.negative_feedback_count for s in all_sessions)
    total_fb = positive + negative
    
    with col1:
        st.metric("Sessioni", len(all_sessions))
    with col2:
        st.metric("Messaggi", total_interactions)
    with col3:
        st.metric("Utenti Unici", unique_users)
    with col4:
        ratio = f"{positive/total_fb*100:.0f}%" if total_fb else "N/A"
        st.metric("Feedback Positivo", ratio)
    
    # Stats aggiuntive
    col1, col2, col3, col4 = st.columns(4)
    
    all_latencies = []
    gaps_detected = 0
    gaps_reported = 0
    
    for s in all_sessions:
        for i in s.interactions:
            if i.latency_total_ms > 0:
                all_latencies.append(i.latency_total_ms)
            if i.gap_detected:
                gaps_detected += 1
            if i.gap_reported:
                gaps_reported += 1
    
    avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0
    
    with col1:
        st.metric("Latenza Media", f"{avg_latency:.0f}ms")
    with col2:
        avg_int = total_interactions / len(all_sessions) if all_sessions else 0
        st.metric("Msg/Sessione", f"{avg_int:.1f}")
    with col3:
        st.metric("Lacune Rilevate", gaps_detected)
    with col4:
        st.metric("Lacune Segnalate", gaps_reported)
    
    st.divider()
    
    # ═══════════════════════════════════════════════════════════════
    # LISTA SESSIONI
    # ═══════════════════════════════════════════════════════════════
    
    st.subheader("📋 Sessioni")
    
    # Ordina per data (più recenti prima)
    all_sessions.sort(key=lambda s: s.started_at, reverse=True)
    
    # Paginazione
    sessions_per_page = 10
    total_pages = (len(all_sessions) + sessions_per_page - 1) // sessions_per_page
    
    if total_pages > 1:
        page = st.number_input("Pagina", min_value=1, max_value=total_pages, value=1)
    else:
        page = 1
    
    start_idx = (page - 1) * sessions_per_page
    end_idx = start_idx + sessions_per_page
    page_sessions = all_sessions[start_idx:end_idx]
    
    st.caption(f"Mostrando {start_idx + 1}-{min(end_idx, len(all_sessions))} di {len(all_sessions)} sessioni")
    
    for session in page_sessions:
        try:
            start_dt = datetime.fromisoformat(session.started_at)
            duration = session.duration_seconds()
            
            # Titolo expander
            title = (
                f"🗣️ **{session.user_id}** - {start_dt.strftime('%d/%m %H:%M')} "
                f"| {session.total_interactions} msg | {duration/60:.0f} min"
            )
            
            if session.positive_feedback_count or session.negative_feedback_count:
                title += f" | 👍{session.positive_feedback_count} 👎{session.negative_feedback_count}"
            
            with st.expander(title):
                # Info sessione
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Ruolo:** {session.user_role}")
                with col2:
                    st.write(f"**Durata:** {duration/60:.1f} min")
                with col3:
                    st.write(f"**Latenza media:** {session.avg_latency_ms:.0f}ms")
                
                st.divider()
                
                # Lista interazioni
                for i, interaction in enumerate(session.interactions):
                    # Query
                    st.markdown(f"**👤 Domanda {i+1}:**")
                    st.text(interaction.query_original)
                    
                    # Response (collapsible se lunga)
                    st.markdown("**🤖 Risposta:**")
                    if len(interaction.response_text) > 500:
                        with st.expander("Mostra risposta completa"):
                            st.text(interaction.response_text)
                    else:
                        st.text(interaction.response_text[:500] if interaction.response_text else "(vuota)")
                    
                    # Metadata inline
                    meta_parts = []
                    if interaction.sources_cited:
                        meta_parts.append(f"📚 {', '.join(interaction.sources_cited)}")
                    if interaction.latency_total_ms:
                        meta_parts.append(f"⏱️ {interaction.latency_total_ms}ms")
                    if interaction.feedback:
                        emoji = "👍" if interaction.feedback == "positive" else "👎"
                        meta_parts.append(emoji)
                    if interaction.gap_detected:
                        meta_parts.append("⚠️ Lacuna")
                    if interaction.tools_suggested:
                        meta_parts.append(f"🛠️ {', '.join(interaction.tools_suggested)}")
                    
                    if meta_parts:
                        st.caption(" | ".join(meta_parts))
                    
                    st.divider()
                    
        except Exception as e:
            st.warning(f"Errore visualizzazione sessione: {e}")
            continue
    
    # ═══════════════════════════════════════════════════════════════
    # EXPORT
    # ═══════════════════════════════════════════════════════════════
    
    st.subheader("📤 Export")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 Genera CSV", type="primary"):
            export_dir = "data/exports"
            os.makedirs(export_dir, exist_ok=True)
            
            output_path = f"{export_dir}/conversations_{date_from}_{date_to}.csv"
            
            rows = conv_logger.export_sessions_csv(
                output_path=output_path,
                date_from=date_from.strftime("%Y-%m-%d"),
                date_to=date_to.strftime("%Y-%m-%d"),
                user_id=user_filter if user_filter else None
            )
            
            st.success(f"✅ Esportate {rows} righe in `{output_path}`")
            
            # Download button
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    csv_content = f.read()
                
                st.download_button(
                    label="⬇️ Scarica CSV",
                    data=csv_content,
                    file_name=f"conversations_{date_from}_{date_to}.csv",
                    mime="text/csv"
                )
            except Exception as e:
                st.error(f"Errore lettura file: {e}")
    
    with col2:
        # Cleanup button (solo admin)
        if user_role == "admin":
            if st.button("🗑️ Pulisci sessioni vecchie"):
                removed = conv_logger.cleanup_old_sessions()
                if removed > 0:
                    st.success(f"✅ Rimosse {removed} sessioni più vecchie di {conv_logger.retention_days} giorni")
                else:
                    st.info("Nessuna sessione da rimuovere")
    
    # ═══════════════════════════════════════════════════════════════
    # STATISTICHE PER UTENTE
    # ═══════════════════════════════════════════════════════════════
    
    st.subheader("👥 Statistiche per Utente")
    
    # Aggrega per utente
    user_stats = {}
    for session in all_sessions:
        uid = session.user_id
        if uid not in user_stats:
            user_stats[uid] = {
                "sessions": 0,
                "interactions": 0,
                "positive": 0,
                "negative": 0,
                "gaps": 0
            }
        user_stats[uid]["sessions"] += 1
        user_stats[uid]["interactions"] += session.total_interactions
        user_stats[uid]["positive"] += session.positive_feedback_count
        user_stats[uid]["negative"] += session.negative_feedback_count
        for i in session.interactions:
            if i.gap_detected:
                user_stats[uid]["gaps"] += 1
    
    # Ordina per interazioni
    sorted_users = sorted(user_stats.items(), key=lambda x: x[1]["interactions"], reverse=True)
    
    # Mostra tabella
    if sorted_users:
        import pandas as pd
        
        df_data = []
        for uid, stats in sorted_users[:20]:  # Top 20
            total_fb = stats["positive"] + stats["negative"]
            ratio = f"{stats['positive']/total_fb*100:.0f}%" if total_fb else "-"
            df_data.append({
                "Utente": uid,
                "Sessioni": stats["sessions"],
                "Messaggi": stats["interactions"],
                "👍": stats["positive"],
                "👎": stats["negative"],
                "Ratio": ratio,
                "Lacune": stats["gaps"]
            })
        
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

