"""
Analytics View per Admin Panel
Vista dedicata alle analytics R07

R07 - Sistema Analytics
Created: 2025-12-08
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


def render_analytics_view(is_admin: bool = True):
    """
    Renderizza vista analytics nel pannello Admin.
    
    Args:
        is_admin: Se True, mostra tutte le opzioni
    """
    st.header("📊 Analytics Dashboard")
    
    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "📅 Da",
            datetime.now() - timedelta(days=7),
            key="analytics_start"
        )
    with col2:
        end_date = st.date_input(
            "📅 A",
            datetime.now(),
            key="analytics_end"
        )
    
    # Tabs
    tabs = st.tabs([
        "📈 Utilizzo",
        "✅ Qualità",
        "📚 Glossario",
        "🧠 Memoria",
        "⚙️ Pipeline",
        "📄 Report"
    ])
    
    with tabs[0]:
        _render_usage_tab(start_date, end_date)
    
    with tabs[1]:
        _render_quality_tab(start_date, end_date)
    
    with tabs[2]:
        _render_glossary_tab()
    
    with tabs[3]:
        _render_memory_tab()
    
    with tabs[4]:
        _render_pipeline_tab()
    
    with tabs[5]:
        if is_admin:
            _render_reports_tab()
        else:
            st.warning("⚠️ Solo Admin può accedere ai Report")


def _render_usage_tab(start_date, end_date):
    """Tab utilizzo sistema"""
    st.subheader("📈 Statistiche Utilizzo")
    
    try:
        from src.analytics.collectors import QueryCollector
        from src.analytics.analyzers import UsageAnalyzer
        
        collector = QueryCollector()
        analyzer = UsageAnalyzer()
        
        # Calcola giorni
        days = (end_date - start_date).days + 1
        
        # Ottieni dati
        logs = collector.get_logs_last_n_days(days)
        
        if not logs:
            st.info("📭 Nessun dato disponibile per il periodo selezionato")
            return
        
        # Genera report
        usage_report = analyzer.generate_report(logs, days=days)
        
        # KPI Cards
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "📊 Query Totali",
                usage_report.get('total_queries', 0),
                delta=None
            )
        
        with col2:
            st.metric(
                "👥 Utenti Attivi",
                usage_report.get('unique_users', 0)
            )
        
        with col3:
            trend = usage_report.get('trend', {})
            delta = trend.get('pct_change')
            st.metric(
                "📈 Trend",
                f"{delta:+.1f}%" if delta else "N/A",
                delta=trend.get('trend_direction', '')
            )
        
        with col4:
            latency = trend.get('latency_trend', 'N/A')
            st.metric("⏱️ Latenza", latency)
        
        st.divider()
        
        # Distribuzione oraria
        st.subheader("🕐 Distribuzione per Ora")
        hourly = usage_report.get('hourly_distribution', {})
        if hourly:
            import pandas as pd
            df = pd.DataFrame({
                'Ora': list(hourly.keys()),
                'Query': list(hourly.values())
            })
            st.bar_chart(df.set_index('Ora'))
        
        # Top users
        st.subheader("🏆 Top Utenti")
        top_users = usage_report.get('top_users', [])
        if top_users:
            for user in top_users[:5]:
                st.write(f"- **{user['user_id']}**: {user['query_count']} query (avg {user['avg_latency_ms']}ms)")
        
        # User segments
        st.subheader("👥 Segmentazione Utenti")
        segments = usage_report.get('user_segments', {})
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🔥 Power Users", len(segments.get('power_users', [])))
        with col2:
            st.metric("✅ Regular", len(segments.get('regular', [])))
        with col3:
            st.metric("👤 Occasional", len(segments.get('occasional', [])))
        
        # Query patterns
        st.subheader("🔍 Pattern Query")
        patterns = usage_report.get('query_patterns', {})
        if patterns.get('percentages'):
            import pandas as pd
            df = pd.DataFrame({
                'Pattern': list(patterns['percentages'].keys()),
                'Percentuale': list(patterns['percentages'].values())
            })
            st.bar_chart(df.set_index('Pattern'))
            
    except ImportError as e:
        st.error(f"❌ Modulo non disponibile: {e}")
    except Exception as e:
        st.error(f"❌ Errore: {e}")
        logger.exception("Errore in usage tab")


def _render_quality_tab(start_date, end_date):
    """Tab qualità risposte"""
    st.subheader("✅ Metriche Qualità")
    
    try:
        from src.analytics.collectors import QueryCollector
        from src.analytics.analyzers import QualityAnalyzer
        
        collector = QueryCollector()
        analyzer = QualityAnalyzer()
        
        days = (end_date - start_date).days + 1
        logs = collector.get_logs_last_n_days(days)
        
        if not logs:
            st.info("📭 Nessun dato disponibile")
            return
        
        quality_report = analyzer.generate_report(logs)
        
        # Health Score
        health = quality_report.get('overall_health', {})
        score = health.get('score', 0)
        status = health.get('status', 'unknown')
        color = health.get('color', 'gray')
        
        # Color mapping for streamlit
        status_colors = {
            'excellent': '🟢',
            'good': '🟢',
            'fair': '🟡',
            'needs_attention': '🟠',
            'critical': '🔴'
        }
        
        st.markdown(f"### Health Score: {status_colors.get(status, '⚪')} **{score}/100** ({status})")
        
        st.divider()
        
        # Metriche principali
        col1, col2, col3, col4 = st.columns(4)
        
        targets = quality_report.get('targets', {})
        
        with col1:
            hit_rate = quality_report.get('hit_rate', 0)
            target = targets.get('hit_rate', 0.9)
            delta = "✅" if hit_rate >= target else "⚠️"
            st.metric("🎯 Hit Rate", f"{hit_rate:.1%}", delta=delta)
        
        with col2:
            feedback = quality_report.get('feedback_score', {})
            ratio = feedback.get('positive_ratio', 0) if isinstance(feedback, dict) else 0
            target = targets.get('feedback_score', 0.8)
            delta = "✅" if ratio >= target else "⚠️"
            st.metric("👍 Feedback Positivo", f"{ratio:.1%}", delta=delta)
        
        with col3:
            no_results = quality_report.get('no_results_rate', 0)
            delta = "✅" if no_results <= 0.1 else "⚠️"
            st.metric("❌ No-Results", f"{no_results:.1%}", delta=delta)
        
        with col4:
            latency = quality_report.get('latency_stats', {})
            p95 = latency.get('p95', 0)
            target = targets.get('latency_p95_ms', 30000)
            delta = "✅" if p95 <= target else "⚠️"
            st.metric("⏱️ P95 Latency", f"{p95}ms", delta=delta)
        
        # Latency breakdown
        st.subheader("⏱️ Breakdown Latenza")
        breakdown = quality_report.get('latency_breakdown', {})
        if breakdown:
            import pandas as pd
            df = pd.DataFrame({
                'Componente': list(breakdown.keys()),
                'ms': list(breakdown.values())
            })
            st.bar_chart(df.set_index('Componente'))
        
        # Issues
        issues = quality_report.get('quality_issues', [])
        if issues:
            st.subheader("⚠️ Problemi Rilevati")
            for issue in issues:
                severity = issue.get('severity', 'medium')
                icon = "🔴" if severity == 'high' else "🟡"
                st.warning(f"{icon} {issue.get('description', '')}")
        else:
            st.success("✅ Nessun problema rilevato!")
            
    except Exception as e:
        st.error(f"❌ Errore: {e}")
        logger.exception("Errore in quality tab")


def _render_glossary_tab():
    """Tab statistiche glossario"""
    st.subheader("📚 Statistiche Glossario")
    
    try:
        from src.analytics.collectors import GlossaryCollector
        
        collector = GlossaryCollector()
        stats = collector.get_stats()
        
        # KPI
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📖 Termini Totali", stats.get('total_terms', 0))
        with col2:
            st.metric("✅ Usati (Ever)", stats.get('terms_used_ever', 0))
        with col3:
            coverage = stats.get('coverage_ratio', 0)
            st.metric("📊 Copertura", f"{coverage:.1%}")
        with col4:
            st.metric("❓ Non Riconosciuti", stats.get('unknown_count', 0))
        
        st.divider()
        
        # Top used
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔥 Più Usati")
            most_used = stats.get('most_used', [])
            for term, count in most_used[:10]:
                st.write(f"- `{term}`: {count}")
        
        with col2:
            st.subheader("❓ Non Riconosciuti")
            unknown = stats.get('unknown_terms', [])
            for item in unknown[:10]:
                st.write(f"- `{item.get('term', '')}`: {item.get('count', 0)} volte")
        
        # Never used
        with st.expander("📭 Termini Mai Usati"):
            never_used = stats.get('terms_never_used', [])
            if never_used:
                st.write(", ".join(f"`{t}`" for t in never_used[:30]))
            else:
                st.success("Tutti i termini sono stati usati almeno una volta!")
                
    except Exception as e:
        st.error(f"❌ Errore: {e}")


def _render_memory_tab():
    """Tab statistiche memoria"""
    st.subheader("🧠 Statistiche Sistema Memoria")
    
    try:
        from src.analytics.collectors import MemoryCollector
        
        collector = MemoryCollector()
        stats = collector.get_stats()
        
        # KPI
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("💾 Totale Memorie", stats.get('total_memories', 0))
        with col2:
            st.metric("🌍 Globali", stats.get('global_count', 0))
        with col3:
            st.metric("👥 Utenti", stats.get('user_count', 0))
        with col4:
            st.metric("⏳ Pending", stats.get('pending_count', 0))
        
        st.divider()
        
        # Per tipo
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Per Tipo")
            by_type = stats.get('by_type', {})
            if by_type:
                import pandas as pd
                df = pd.DataFrame({
                    'Tipo': list(by_type.keys()),
                    'Count': list(by_type.values())
                })
                st.bar_chart(df.set_index('Tipo'))
        
        with col2:
            st.subheader("📈 Bayesian Feedback")
            boost = stats.get('boost_stats', {})
            st.write(f"- **Media**: {boost.get('avg', 1.0):.3f}")
            st.write(f"- **Max**: {boost.get('max', 1.0):.3f}")
            st.write(f"- **Min**: {boost.get('min', 1.0):.3f}")
        
        # Top/Low boosted
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔝 Top Boosted")
            top = stats.get('top_boosted', [])
            for mem in top[:5]:
                st.write(f"- {mem['content'][:40]}... ({mem['boost']:.2f})")
        
        with col2:
            st.subheader("⬇️ Low Boosted")
            low = stats.get('low_boosted', [])
            for mem in low[:5]:
                st.write(f"- {mem['content'][:40]}... ({mem['boost']:.2f})")
                
    except Exception as e:
        st.error(f"❌ Errore: {e}")


def _render_pipeline_tab():
    """Tab pipeline RAG"""
    st.subheader("⚙️ Pipeline RAG")
    
    try:
        from src.analytics.collectors import PipelineCollector
        
        collector = PipelineCollector()
        stats = collector.get_stats()
        health = collector.get_collection_health()
        
        # Status
        status = stats.get('collection_status', 'unknown')
        connected = stats.get('qdrant_connected', False)
        
        status_icon = "🟢" if status.lower() == "green" else "🟡" if status.lower() == "yellow" else "🔴"
        
        st.markdown(f"### Status Qdrant: {status_icon} **{status}** {'✅ Connesso' if connected else '❌ Non connesso'}")
        
        st.divider()
        
        # KPI
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📦 Chunks Totali", stats.get('total_chunks', 0))
        with col2:
            vram_used = stats.get('vram_usage_mb', 0)
            vram_total = stats.get('vram_total_mb', 0)
            st.metric("💾 VRAM", f"{vram_used}MB")
        with col3:
            vram_pct = stats.get('vram_usage_pct', 0)
            st.metric("📊 VRAM %", f"{vram_pct}%")
        with col4:
            st.metric("🔗 Indexed", stats.get('indexed_vectors', 0))
        
        # Chunks per tipo
        st.subheader("📊 Chunks per Tipo Documento")
        by_type = stats.get('chunks_by_doc_type', {})
        if by_type:
            import pandas as pd
            df = pd.DataFrame({
                'Tipo': list(by_type.keys()),
                'Count': list(by_type.values())
            })
            st.bar_chart(df.set_index('Tipo'))
        
        # Health issues
        issues = health.get('issues', [])
        if issues:
            st.subheader("⚠️ Problemi")
            for issue in issues:
                st.warning(issue)
        
        # Test retrieval
        with st.expander("🧪 Test Retrieval"):
            if st.button("Esegui Test"):
                with st.spinner("Testing..."):
                    result = collector.test_retrieval()
                    if result.get('success'):
                        st.success("✅ Test OK!")
                        for doc in result.get('sample_docs', []):
                            st.write(f"- {doc['doc_id']}: {doc['text_preview'][:60]}...")
                    else:
                        st.error(f"❌ {result.get('error', 'unknown')}")
                        
    except Exception as e:
        st.error(f"❌ Errore: {e}")


def _render_reports_tab():
    """Tab report salvati"""
    st.subheader("📄 Report Salvati")
    
    try:
        from src.analytics.analyzers import ReportGenerator
        from src.analytics.scheduler import AnalyticsScheduler
        
        generator = ReportGenerator()
        
        # Lista report
        reports = generator.list_reports()
        
        if not reports:
            st.info("📭 Nessun report disponibile")
        else:
            for report in reports[:20]:
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    st.write(f"📊 **{report['name']}**")
                with col2:
                    st.write(f"_{report.get('modified', '')[:10]}_")
                with col3:
                    try:
                        with open(report['path'], 'r', encoding='utf-8') as f:
                            content = f.read()
                        st.download_button(
                            "⬇️",
                            content,
                            file_name=f"{report['name']}.{report['format']}",
                            mime="text/html" if report['format'] == 'html' else "text/markdown",
                            key=f"dl_{report['name']}"
                        )
                    except Exception:
                        st.write("N/A")
        
        st.divider()
        
        # Generate on-demand
        st.subheader("🔄 Genera Nuovo Report")
        
        if st.button("📊 Genera Report Ora", type="primary"):
            with st.spinner("Generazione in corso..."):
                scheduler = AnalyticsScheduler()
                result = scheduler.generate_nightly_report()
                
                if result.get('success'):
                    st.success(f"✅ Report generato!")
                    st.write(f"- MD: `{result.get('md_path')}`")
                    st.write(f"- HTML: `{result.get('html_path')}`")
                    st.rerun()
                else:
                    st.error(f"❌ Errore: {result.get('error')}")
                    
    except Exception as e:
        st.error(f"❌ Errore: {e}")


# Export
__all__ = ["render_analytics_view"]

