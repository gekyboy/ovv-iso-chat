"""
Dashboard Service Layer
Logica di business per KPI e statistiche dashboard - estratto da Streamlit
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class DashboardService:
    """Service per dashboard KPI e statistiche"""

    def __init__(self):
        self._memory_store = None
        self._glossary = None
        self._user_store = None

    def get_kpi_data(self) -> Dict[str, Any]:
        """
        Ottiene dati KPI principali per dashboard

        Returns:
            Dict con metriche principali
        """
        try:
            # Inizializza stores
            memory_store = self._get_memory_store()
            glossary = self._get_glossary()
            user_store = self._get_user_store()

            # Proposte pending
            pending = memory_store.get_all(namespace=("pending_global",))
            pending_today = self._count_items_today(pending)

            # Memorie totali
            stats = memory_store.get_stats()
            total_memories = stats.get("total_memories", 0)

            # Glossario
            total_acronyms = len(glossary.acronyms) if glossary else 0

            # Utenti
            users = user_store.list_users()

            return {
                "pending_proposals": {
                    "total": len(pending),
                    "today": pending_today
                },
                "total_memories": total_memories,
                "total_acronyms": total_acronyms,
                "total_users": len(users),
                "memory_stats": stats
            }

        except Exception as e:
            logger.error(f"Errore caricamento KPI: {e}")
            return {
                "pending_proposals": {"total": 0, "today": 0},
                "total_memories": 0,
                "total_acronyms": 0,
                "total_users": 0,
                "memory_stats": {}
            }

    def get_memory_distribution(self) -> Dict[str, int]:
        """
        Ottiene distribuzione memorie per tipo

        Returns:
            Dict tipo -> count
        """
        try:
            memory_store = self._get_memory_store()
            stats = memory_store.get_stats()
            return stats.get("by_type", {})
        except Exception as e:
            logger.error(f"Errore distribuzione memorie: {e}")
            return {}

    def get_recent_activity(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Ottiene attività recente degli ultimi N giorni

        Args:
            days: Numero di giorni da considerare

        Returns:
            Lista attività recenti
        """
        try:
            memory_store = self._get_memory_store()
            cutoff = datetime.now() - timedelta(days=days)

            # Trova memorie recenti
            recent = []
            all_memories = memory_store.get_all(limit=100)

            for mem in all_memories:
                if hasattr(mem, 'created_at') and mem.created_at >= cutoff:
                    recent.append({
                        "id": mem.id,
                        "content": mem.content[:100] + "..." if len(mem.content) > 100 else mem.content,
                        "type": mem.type.value if hasattr(mem, 'type') else "unknown",
                        "created_at": mem.created_at.isoformat() if hasattr(mem, 'created_at') else None
                    })

            # Ordina per data discendente
            recent.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return recent[:20]  # Max 20 elementi

        except Exception as e:
            logger.error(f"Errore attività recente: {e}")
            return []

    def get_user_activity_stats(self) -> Dict[str, Any]:
        """
        Statistiche attività utenti

        Returns:
            Dict con statistiche utenti
        """
        try:
            user_store = self._get_user_store()
            users = user_store.list_users()

            # Raggruppa per ruolo
            by_role = {}
            active_today = 0

            for user in users:
                role = user.role.value
                if role not in by_role:
                    by_role[role] = 0
                by_role[role] += 1

                # TODO: Implementare tracking last activity
                # if user.last_activity >= datetime.now() - timedelta(days=1):
                #     active_today += 1

            return {
                "by_role": by_role,
                "total": len(users),
                "active_today": active_today
            }

        except Exception as e:
            logger.error(f"Errore statistiche utenti: {e}")
            return {"by_role": {}, "total": 0, "active_today": 0}

    def _get_memory_store(self):
        """Lazy load memory store"""
        if self._memory_store is None:
            from src.memory.store import MemoryStore
            self._memory_store = MemoryStore()
        return self._memory_store

    def _get_glossary(self):
        """Lazy load glossary"""
        if self._glossary is None:
            from src.integration.glossary import GlossaryResolver
            self._glossary = GlossaryResolver()
        return self._glossary

    def _get_user_store(self):
        """Lazy load user store"""
        if self._user_store is None:
            from src.auth.store import UserStore
            self._user_store = UserStore()
        return self._user_store

    def _count_items_today(self, items) -> int:
        """Conta elementi creati oggi"""
        today = datetime.now().date()
        count = 0

        for item in items:
            if hasattr(item, 'created_at'):
                if isinstance(item.created_at, datetime):
                    if item.created_at.date() == today:
                        count += 1
                elif isinstance(item.created_at, str):
                    try:
                        item_date = datetime.fromisoformat(item.created_at).date()
                        if item_date == today:
                            count += 1
                    except:
                        pass

        return count


# Singleton instance
_dashboard_service = None

def get_dashboard_service() -> DashboardService:
    """Ottiene istanza singleton del DashboardService"""
    global _dashboard_service
    if _dashboard_service is None:
        _dashboard_service = DashboardService()
    return _dashboard_service
