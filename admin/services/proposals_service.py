"""
Proposals Service Layer
Logica di business per gestione proposte pending_global - estratto da Streamlit
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from src.memory.store import MemoryType

logger = logging.getLogger(__name__)


class ProposalsService:
    """Service per gestione proposte pending_global"""

    def __init__(self):
        self._memory_store = None
        self._glossary = None

    def get_pending_proposals(self, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Ottiene proposte pending con filtri applicati

        Args:
            filters: Dict con filtri (type, search, etc.)

        Returns:
            Lista proposte formattate per UI
        """
        try:
            memory_store = self._get_memory_store()
            pending = memory_store.get_all(namespace=("pending_global",))

            if not pending:
                return []

            # Applica filtri
            filtered = self._apply_filters(pending, filters or {})

            # Formatta per UI
            proposals = []
            for mem in filtered:
                proposal = {
                    "id": mem.id,
                    "content": mem.content,
                    "type": mem.type.value if hasattr(mem, 'type') else "unknown",
                    "created_at": mem.created_at.isoformat() if hasattr(mem, 'created_at') else None,
                    "metadata": getattr(mem, 'metadata', {}),
                    "author": mem.metadata.get("author", "Unknown") if hasattr(mem, 'metadata') else "Unknown",
                    "confidence": getattr(mem, 'confidence', 0.0)
                }
                proposals.append(proposal)

            # Ordina per data discendente (più recenti prima)
            proposals.sort(key=lambda x: x.get("created_at", ""), reverse=True)

            return proposals

        except Exception as e:
            logger.error(f"Errore caricamento proposte: {e}")
            return []

    def approve_proposal(self, proposal_id: str, user_data: dict) -> Dict[str, Any]:
        """
        Approva una proposta e la sposta dal namespace pending_global

        Args:
            proposal_id: ID della proposta
            user_data: Dati utente che approva

        Returns:
            Dict con risultato dell'operazione
        """
        try:
            memory_store = self._get_memory_store()

            # Trova la proposta
            pending = memory_store.get_all(namespace=("pending_global",))
            proposal = next((p for p in pending if p.id == proposal_id), None)

            if not proposal:
                return {"success": False, "error": "Proposta non trovata"}

            # Sposta dal namespace pending_global al namespace globale
            # Rimuovi dal pending
            memory_store.delete(proposal_id, namespace=("pending_global",))

            # Aggiungi al namespace globale con metadata approvazione
            approved_metadata = dict(proposal.metadata) if hasattr(proposal, 'metadata') else {}
            approved_metadata.update({
                "approved_by": user_data.get("username", "Unknown"),
                "approved_at": datetime.now().isoformat(),
                "approved_from": "pending_global"
            })

            # Ricrea la memoria nel namespace globale
            memory_store.add(
                content=proposal.content,
                type=proposal.type,
                metadata=approved_metadata,
                namespace=("global",)
            )

            logger.info(f"Proposta {proposal_id} approvata da {user_data.get('username')}")
            return {"success": True, "message": "Proposta approvata con successo"}

        except Exception as e:
            logger.error(f"Errore approvazione proposta {proposal_id}: {e}")
            return {"success": False, "error": str(e)}

    def reject_proposal(self, proposal_id: str, user_data: dict, reason: str = "") -> Dict[str, Any]:
        """
        Rifiuta una proposta e la elimina definitivamente

        Args:
            proposal_id: ID della proposta
            user_data: Dati utente che rifiuta
            reason: Motivo del rifiuto (opzionale)

        Returns:
            Dict con risultato dell'operazione
        """
        try:
            memory_store = self._get_memory_store()

            # Trova e elimina la proposta
            pending = memory_store.get_all(namespace=("pending_global",))
            proposal = next((p for p in pending if p.id == proposal_id), None)

            if not proposal:
                return {"success": False, "error": "Proposta non trovata"}

            # Elimina definitivamente
            memory_store.delete(proposal_id, namespace=("pending_global",))

            logger.info(f"Proposta {proposal_id} rifiutata da {user_data.get('username')}: {reason}")
            return {"success": True, "message": "Proposta rifiutata"}

        except Exception as e:
            logger.error(f"Errore rifiuto proposta {proposal_id}: {e}")
            return {"success": False, "error": str(e)}

    def get_proposal_stats(self) -> Dict[str, Any]:
        """
        Statistiche sulle proposte

        Returns:
            Dict con statistiche
        """
        try:
            proposals = self.get_pending_proposals()

            stats = {
                "total": len(proposals),
                "by_type": {}
            }

            for prop in proposals:
                prop_type = prop.get("type", "unknown")
                if prop_type not in stats["by_type"]:
                    stats["by_type"][prop_type] = 0
                stats["by_type"][prop_type] += 1

            return stats

        except Exception as e:
            logger.error(f"Errore statistiche proposte: {e}")
            return {"total": 0, "by_type": {}}

    def _apply_filters(self, proposals, filters: Dict[str, Any]) -> List:
        """Applica filtri alla lista proposte"""
        filtered = proposals

        # Filtro per tipo
        if filters.get("type") and filters["type"] != "Tutti":
            target_type = MemoryType(filters["type"])
            filtered = [p for p in filtered if getattr(p, 'type', None) == target_type]

        # Filtro ricerca testuale
        if filters.get("search"):
            search_term = filters["search"].lower()
            filtered = [
                p for p in filtered
                if search_term in p.content.lower() or
                   search_term in getattr(p, 'metadata', {}).get('author', '').lower()
            ]

        return filtered

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


# Singleton instance
_proposals_service = None

def get_proposals_service() -> ProposalsService:
    """Ottiene istanza singleton del ProposalsService"""
    global _proposals_service
    if _proposals_service is None:
        _proposals_service = ProposalsService()
    return _proposals_service
