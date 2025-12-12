"""
Users Service Layer
Logica di business per gestione utenti - estratto da Streamlit
"""

from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class UsersService:
    """Service per gestione CRUD utenti"""

    def __init__(self):
        self._user_store = None

    def get_users(self) -> List[Dict[str, Any]]:
        """
        Ottiene lista utenti formattata per UI

        Returns:
            Lista utenti
        """
        try:
            user_store = self._get_user_store()
            users = user_store.list_users()

            user_list = []
            for user in users:
                user_dict = {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "role": user.role.value,
                    "created_at": getattr(user, 'created_at', None),
                    "last_login": getattr(user, 'last_login', None)
                }
                user_list.append(user_dict)

            return user_list

        except Exception as e:
            logger.error(f"Errore caricamento utenti: {e}")
            return []

    def create_user(self, username: str, display_name: str, password: str, role: str) -> Dict[str, Any]:
        """
        Crea nuovo utente

        Args:
            username: Username
            display_name: Nome visualizzato
            password: Password
            role: Ruolo (Admin/Engineer/User)

        Returns:
            Dict con risultato
        """
        try:
            user_store = self._get_user_store()

            # TODO: Implementare create_user in UserStore se non esiste
            # Per ora mock
            logger.info(f"Creazione utente {username} ({role})")
            return {"success": True, "message": "Utente creato (TODO: implementare)"}

        except Exception as e:
            logger.error(f"Errore creazione utente {username}: {e}")
            return {"success": False, "error": str(e)}

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggiorna utente

        Args:
            user_id: ID utente
            updates: Campi da aggiornare

        Returns:
            Dict con risultato
        """
        try:
            user_store = self._get_user_store()

            # TODO: Implementare update_user in UserStore
            logger.info(f"Aggiornamento utente {user_id}: {updates}")
            return {"success": True, "message": "Utente aggiornato (TODO: implementare)"}

        except Exception as e:
            logger.error(f"Errore aggiornamento utente {user_id}: {e}")
            return {"success": False, "error": str(e)}

    def delete_user(self, user_id: str) -> Dict[str, Any]:
        """
        Elimina utente

        Args:
            user_id: ID utente

        Returns:
            Dict con risultato
        """
        try:
            user_store = self._get_user_store()

            # TODO: Implementare delete_user in UserStore
            logger.info(f"Eliminazione utente {user_id}")
            return {"success": True, "message": "Utente eliminato (TODO: implementare)"}

        except Exception as e:
            logger.error(f"Errore eliminazione utente {user_id}: {e}")
            return {"success": False, "error": str(e)}

    def _get_user_store(self):
        """Lazy load user store"""
        if self._user_store is None:
            from src.auth.store import UserStore
            self._user_store = UserStore()
        return self._user_store


# Singleton instance
_users_service = None

def get_users_service() -> UsersService:
    """Ottiene istanza singleton del UsersService"""
    global _users_service
    if _users_service is None:
        _users_service = UsersService()
    return _users_service
