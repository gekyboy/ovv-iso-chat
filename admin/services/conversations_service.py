"""
Conversations Service Layer
Logica di business per history conversazioni - estratto da Streamlit
"""

from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class ConversationsService:
    """Service per history conversazioni"""

    def get_conversations(self, limit: int = 50, user_filter: str = None) -> List[Dict[str, Any]]:
        """
        Ottiene conversazioni recenti

        Args:
            limit: Numero massimo conversazioni
            user_filter: Filtro per utente specifico

        Returns:
            Lista conversazioni
        """
        try:
            # TODO: Implementare caricamento conversazioni reali
            # Per ora dati mock
            conversations = [
                {
                    "id": "conv_001",
                    "user": "test_user",
                    "messages_count": 5,
                    "started_at": "2025-12-12T08:30:00",
                    "last_activity": "2025-12-12T08:45:00",
                    "feedback_count": 2,
                    "avg_confidence": 0.87
                },
                {
                    "id": "conv_002",
                    "user": "admin",
                    "messages_count": 3,
                    "started_at": "2025-12-12T09:00:00",
                    "last_activity": "2025-12-12T09:10:00",
                    "feedback_count": 1,
                    "avg_confidence": 0.92
                }
            ]

            if user_filter:
                conversations = [c for c in conversations if c["user"] == user_filter]

            return conversations[:limit]

        except Exception as e:
            logger.error(f"Errore caricamento conversazioni: {e}")
            return []

    def get_conversation_details(self, conversation_id: str) -> Dict[str, Any]:
        """
        Ottiene dettagli conversazione specifica

        Args:
            conversation_id: ID conversazione

        Returns:
            Dettagli conversazione
        """
        try:
            # TODO: Implementare caricamento dettagli reali
            logger.info(f"Caricamento dettagli conversazione {conversation_id}")
            return {
                "id": conversation_id,
                "messages": [],
                "metadata": {},
                "message": "Dettagli non ancora implementati"
            }

        except Exception as e:
            logger.error(f"Errore caricamento conversazione {conversation_id}: {e}")
            return {"error": str(e)}


# Singleton instance
_conversations_service = None

def get_conversations_service() -> ConversationsService:
    """Ottiene istanza singleton del ConversationsService"""
    global _conversations_service
    if _conversations_service is None:
        _conversations_service = ConversationsService()
    return _conversations_service
