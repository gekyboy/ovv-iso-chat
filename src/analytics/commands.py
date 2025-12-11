"""
Analytics Commands per R07
Handler per comandi /analizza

R07 - Sistema Analytics
Created: 2025-12-08

Comandi:
- /analizza glossario - Statistiche glossario
- /analizza memoria - Statistiche sistema memoria
- /analizza pipeline - Statistiche pipeline RAG
- /analizza report - Genera report on-demand
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AnalyticsCommands:
    """
    Handler per comandi /analizza.
    
    Permessi:
    - /analizza glossario: admin, engineer
    - /analizza memoria: admin, engineer
    - /analizza pipeline: admin only
    - /analizza report: admin only
    
    Example:
        >>> commands = AnalyticsCommands()
        >>> result = await commands.handle("glossario", user_role="engineer")
    """
    
    ALLOWED_TARGETS = ["glossario", "memoria", "pipeline", "report"]
    
    def __init__(self):
        logger.info("AnalyticsCommands inizializzato")
    
    async def handle(
        self,
        target: str,
        user_role: str,
        user_id: str = ""
    ) -> str:
        """
        Gestisce comando /analizza.
        
        Args:
            target: glossario|memoria|pipeline|report
            user_role: admin, engineer, user
            user_id: ID utente (per logging)
            
        Returns:
            Stringa Markdown con risultati
        """
        target = target.lower().strip()
        
        if target not in self.ALLOWED_TARGETS:
            return f"❌ Target non valido. Usa: `{', '.join(self.ALLOWED_TARGETS)}`"
        
        # Check permessi
        if target == "glossario":
            if user_role not in ["admin", "engineer"]:
                return "❌ Solo Admin/Engineer possono usare `/analizza glossario`"
            return await self._analyze_glossary()
            
        elif target == "memoria":
            if user_role not in ["admin", "engineer"]:
                return "❌ Solo Admin/Engineer possono usare `/analizza memoria`"
            return await self._analyze_memory()
            
        elif target == "pipeline":
            if user_role != "admin":
                return "❌ Solo Admin può usare `/analizza pipeline`"
            return await self._analyze_pipeline()
            
        elif target == "report":
            if user_role != "admin":
                return "❌ Solo Admin può usare `/analizza report`"
            return await self._generate_report()
        
        return "❌ Comando non riconosciuto"
    
    async def _analyze_glossary(self) -> str:
        """Analisi glossario"""
        try:
            from .collectors import GlossaryCollector
            
            collector = GlossaryCollector()
            stats = collector.get_stats()
            
            # Formatta output
            lines = [
                "📚 **Analisi Glossario**",
                "",
                "**Statistiche:**",
                f"- Termini totali: **{stats['total_terms']}**",
                f"- Termini usati (ever): **{stats['terms_used_ever']}**",
                f"- Termini usati oggi: **{stats['terms_used_today']}**",
                f"- Termini mai usati: **{stats['terms_never_used_count']}**",
                f"- Copertura: **{stats['coverage_ratio']:.1%}**",
                "",
            ]
            
            # Top termini
            most_used = stats.get('most_used', [])
            if most_used:
                lines.append("**Top 5 più usati:**")
                for term, count in most_used[:5]:
                    lines.append(f"- `{term}`: {count} volte")
                lines.append("")
            
            # Unknown terms
            unknown = stats.get('unknown_terms', [])
            if unknown:
                lines.append(f"**⚠️ Acronimi non riconosciuti:** {stats['unknown_count']}")
                for item in unknown[:5]:
                    contexts = item.get('contexts', [])
                    ctx = f" _{contexts[0][:40]}..._" if contexts else ""
                    lines.append(f"- `{item['term']}` ({item['count']} volte){ctx}")
                lines.append("")
                lines.append("💡 *Considera di aggiungerli con `/glossario add`*")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Errore analisi glossario: {e}")
            return f"❌ Errore analisi glossario: {str(e)}"
    
    async def _analyze_memory(self) -> str:
        """Analisi sistema memoria"""
        try:
            from .collectors import MemoryCollector
            
            collector = MemoryCollector()
            stats = collector.get_stats()
            
            lines = [
                "🧠 **Analisi Sistema Memoria**",
                "",
                "**Distribuzione:**",
                f"- Memorie totali: **{stats['total_memories']}**",
                f"- Globali: **{stats['global_count']}**",
                f"- Utenti con memorie: **{stats['user_count']}**",
                f"- Proposte pending: **{stats['pending_count']}**",
                "",
            ]
            
            # Per tipo
            by_type = stats.get('by_type', {})
            if by_type:
                lines.append("**Per tipo:**")
                for mem_type, count in by_type.items():
                    lines.append(f"- {mem_type}: {count}")
                lines.append("")
            
            # Boost stats
            boost = stats.get('boost_stats', {})
            lines.extend([
                "**Bayesian Feedback:**",
                f"- Boost medio: **{boost.get('avg', 1.0):.3f}**",
                f"- Boost max: {boost.get('max', 1.0):.3f}",
                f"- Boost min: {boost.get('min', 1.0):.3f}",
                "",
            ])
            
            # Top boosted
            top = stats.get('top_boosted', [])
            if top:
                lines.append("**Top memorie valorizzate:**")
                for mem in top[:3]:
                    lines.append(f"- {mem['content'][:50]}... (boost: {mem['boost']:.2f})")
                lines.append("")
            
            # Low boosted
            low = stats.get('low_boosted', [])
            if low:
                lines.append("**⚠️ Memorie penalizzate:**")
                for mem in low[:3]:
                    lines.append(f"- {mem['content'][:50]}... (boost: {mem['boost']:.2f})")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Errore analisi memoria: {e}")
            return f"❌ Errore analisi memoria: {str(e)}"
    
    async def _analyze_pipeline(self) -> str:
        """Analisi pipeline RAG"""
        try:
            from .collectors import PipelineCollector, QueryCollector
            
            pipeline_collector = PipelineCollector()
            query_collector = QueryCollector()
            
            pipeline_stats = pipeline_collector.get_stats()
            health = pipeline_collector.get_collection_health()
            daily_stats = query_collector.get_daily_stats()
            
            # Status emoji
            status = pipeline_stats.get('collection_status', 'unknown')
            status_emoji = "🟢" if status.lower() == "green" else "🟡" if status.lower() == "yellow" else "🔴"
            
            lines = [
                "⚙️ **Analisi Pipeline RAG**",
                "",
                "**Collection Qdrant:**",
                f"- Status: {status_emoji} **{status}**",
                f"- Chunks totali: **{pipeline_stats.get('total_chunks', 0)}**",
                f"- Connesso: {'✅' if pipeline_stats.get('qdrant_connected') else '❌'}",
                "",
            ]
            
            # Chunks per tipo
            by_type = pipeline_stats.get('chunks_by_doc_type', {})
            if by_type:
                lines.append("**Chunks per tipo documento:**")
                for doc_type, count in sorted(by_type.items()):
                    lines.append(f"- {doc_type}: {count}")
                lines.append("")
            
            # VRAM
            vram_used = pipeline_stats.get('vram_usage_mb', 0)
            vram_total = pipeline_stats.get('vram_total_mb', 0)
            vram_pct = pipeline_stats.get('vram_usage_pct', 0)
            
            vram_emoji = "🟢" if vram_pct < 80 else "🟡" if vram_pct < 90 else "🔴"
            
            lines.extend([
                "**VRAM GPU:**",
                f"- Utilizzo: {vram_emoji} **{vram_used}MB / {vram_total}MB** ({vram_pct}%)",
                "",
            ])
            
            # Performance da query log
            if daily_stats.get('total_queries', 0) > 0:
                lines.extend([
                    "**Performance (ultime 24h):**",
                    f"- Query processate: **{daily_stats['total_queries']}**",
                    f"- Latenza media: **{daily_stats['avg_latency_ms']}ms**",
                    f"- No-results: {daily_stats.get('no_results_count', 0)} ({daily_stats.get('no_results_ratio', 0):.1%})",
                    f"- Feedback ratio: {daily_stats.get('feedback_ratio', 0):.1%}",
                ])
            
            # Health issues
            if health.get('issues'):
                lines.extend([
                    "",
                    "**⚠️ Problemi:**",
                ])
                for issue in health['issues']:
                    lines.append(f"- {issue}")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Errore analisi pipeline: {e}")
            return f"❌ Errore analisi pipeline: {str(e)}"
    
    async def _generate_report(self) -> str:
        """Genera report on-demand"""
        try:
            from .scheduler import AnalyticsScheduler
            
            scheduler = AnalyticsScheduler()
            result = scheduler.generate_nightly_report()
            
            if result.get('success'):
                return (
                    "✅ **Report generato con successo!**\n\n"
                    f"📄 Markdown: `{result.get('md_path', 'N/A')}`\n"
                    f"🌐 HTML: `{result.get('html_path', 'N/A')}`\n\n"
                    "*Puoi visualizzare i report nel pannello Admin.*"
                )
            else:
                return f"❌ Errore generazione report: {result.get('error', 'sconosciuto')}"
                
        except Exception as e:
            logger.error(f"Errore generazione report: {e}")
            return f"❌ Errore generazione report: {str(e)}"
    
    def get_help(self) -> str:
        """Ritorna help per comandi /analizza"""
        return """
📊 **Comandi Analytics**

| Comando | Descrizione | Chi può usarlo |
|---------|-------------|----------------|
| `/analizza glossario` | Statistiche glossario | Admin, Engineer |
| `/analizza memoria` | Statistiche memorie | Admin, Engineer |
| `/analizza pipeline` | Stato pipeline RAG | Solo Admin |
| `/analizza report` | Genera report | Solo Admin |

**Esempio:**
```
/analizza glossario
```
"""


# Singleton
_commands: Optional[AnalyticsCommands] = None


def get_analytics_commands() -> AnalyticsCommands:
    """Ottiene istanza singleton AnalyticsCommands"""
    global _commands
    if _commands is None:
        _commands = AnalyticsCommands()
    return _commands


# Test standalone
if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.DEBUG)
    
    async def test():
        print("=== TEST ANALYTICS COMMANDS ===\n")
        
        commands = AnalyticsCommands()
        
        # Test help
        print("Test 0: Help")
        print(commands.get_help())
        print()
        
        # Test glossario
        print("Test 1: /analizza glossario (as engineer)")
        result = await commands.handle("glossario", user_role="engineer")
        print(result[:500])
        print("...\n")
        
        # Test memoria
        print("Test 2: /analizza memoria (as engineer)")
        result = await commands.handle("memoria", user_role="engineer")
        print(result[:500])
        print("...\n")
        
        # Test pipeline
        print("Test 3: /analizza pipeline (as admin)")
        result = await commands.handle("pipeline", user_role="admin")
        print(result[:500])
        print("...\n")
        
        # Test permessi
        print("Test 4: /analizza pipeline (as user) - should fail")
        result = await commands.handle("pipeline", user_role="user")
        print(result)
        print()
        
        print("✅ Test completati!")
    
    asyncio.run(test())

