"""
User Store per OVV ISO Chat v3.2
Storage utenti JSON-based con password bcrypt
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Optional, Dict, List

import bcrypt

from .models import User, Role

logger = logging.getLogger(__name__)


class UserStore:
    """
    Store per gestione utenti con autenticazione bcrypt.
    Persiste su file JSON.
    """
    
    def __init__(self, path: str = "config/users.json"):
        self.path = Path(path)
        self._users: Dict[str, User] = {}
        self._load()
    
    def _load(self):
        """Carica utenti da file JSON"""
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for username, user_data in data.get("users", {}).items():
                    self._users[username] = User(
                        id=user_data["id"],
                        username=user_data["username"],
                        password_hash=user_data["password_hash"],
                        role=Role(user_data["role"]),
                        display_name=user_data.get("display_name")
                    )
                
                logger.info(f"Caricati {len(self._users)} utenti da {self.path}")
                
            except Exception as e:
                logger.error(f"Errore caricamento utenti: {e}")
                self._create_default_users()
        else:
            logger.info(f"File utenti non trovato, creo utenti default")
            self._create_default_users()
    
    def _save(self):
        """Salva utenti su file JSON"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "users": {
                    user.username: {
                        "id": user.id,
                        "username": user.username,
                        "password_hash": user.password_hash,
                        "role": user.role.value,
                        "display_name": user.display_name
                    }
                    for user in self._users.values()
                }
            }
            
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Utenti salvati su {self.path}")
            
        except Exception as e:
            logger.error(f"Errore salvataggio utenti: {e}")
    
    def _create_default_users(self):
        """Crea utenti di default per primo avvio"""
        # Admin
        self.create_user("admin", "admin123", Role.ADMIN, "Amministratore")
        # Engineer
        self.create_user("engineer", "eng123", Role.ENGINEER, "Ingegnere")
        # User base
        self.create_user("user", "user123", Role.USER, "Utente")
        
        logger.info("Creati 3 utenti default (admin/engineer/user)")
    
    def _hash_password(self, password: str) -> str:
        """Hash password con bcrypt"""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verifica password contro hash"""
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False
    
    def authenticate(self, username: str, password: str) -> Optional[User]:
        """
        Autentica utente con username e password.
        
        Returns:
            User se autenticazione ok, None altrimenti
        """
        user = self._users.get(username)
        
        if user and self._verify_password(password, user.password_hash):
            logger.info(f"Login OK: {username} (ruolo: {user.role.value})")
            return user
        
        logger.warning(f"Login FALLITO: {username}")
        return None
    
    def create_user(
        self,
        username: str,
        password: str,
        role: Role,
        display_name: Optional[str] = None
    ) -> Optional[User]:
        """
        Crea nuovo utente.
        
        Returns:
            User creato o None se username esiste già
        """
        if username in self._users:
            logger.warning(f"Username già esistente: {username}")
            return None
        
        user = User(
            id=str(uuid.uuid4())[:8],
            username=username,
            password_hash=self._hash_password(password),
            role=role,
            display_name=display_name or username
        )
        
        self._users[username] = user
        self._save()
        
        logger.info(f"Utente creato: {username} (ruolo: {role.value})")
        return user
    
    def get_user(self, username: str) -> Optional[User]:
        """Recupera utente per username"""
        return self._users.get(username)
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Recupera utente per ID"""
        for user in self._users.values():
            if user.id == user_id:
                return user
        return None
    
    def list_users(self, role: Optional[Role] = None) -> List[User]:
        """Lista utenti, opzionalmente filtrati per ruolo"""
        users = list(self._users.values())
        if role:
            users = [u for u in users if u.role == role]
        return users
    
    def update_password(self, username: str, new_password: str) -> bool:
        """Aggiorna password utente"""
        user = self._users.get(username)
        if not user:
            return False
        
        user.password_hash = self._hash_password(new_password)
        self._save()
        
        logger.info(f"Password aggiornata: {username}")
        return True
    
    def delete_user(self, username: str) -> bool:
        """Elimina utente (non può eliminare admin)"""
        if username == "admin":
            logger.warning("Impossibile eliminare utente admin")
            return False
        
        if username in self._users:
            del self._users[username]
            self._save()
            logger.info(f"Utente eliminato: {username}")
            return True
        
        return False


# CLI per gestione utenti
if __name__ == "__main__":
    import sys
    
    store = UserStore()
    
    if len(sys.argv) < 2:
        print("Uso: python -m src.auth.store <comando>")
        print("Comandi: list, create, delete")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "list":
        print("\nUtenti registrati:")
        for user in store.list_users():
            print(f"  - {user.username} ({user.role.value}) [{user.id}]")
    
    elif cmd == "create" and len(sys.argv) >= 5:
        username = sys.argv[2]
        password = sys.argv[3]
        role = Role(sys.argv[4])
        user = store.create_user(username, password, role)
        if user:
            print(f"Creato: {user.username}")
    
    elif cmd == "delete" and len(sys.argv) >= 3:
        username = sys.argv[2]
        if store.delete_user(username):
            print(f"Eliminato: {username}")

