"""
Modelli utente e ruoli per OVV ISO Chat v3.2
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Role(str, Enum):
    """Ruoli disponibili nel sistema"""
    ADMIN = "admin"       # Gestisce memorie globali, vede tutto
    ENGINEER = "engineer" # Vede tutte le memorie utenti
    USER = "user"         # Solo proprie memorie + globali


@dataclass
class User:
    """Rappresentazione utente con permessi RBAC"""
    id: str
    username: str
    password_hash: str
    role: Role
    display_name: Optional[str] = None
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.username
        # Converte stringa a enum se necessario
        if isinstance(self.role, str):
            self.role = Role(self.role)
    
    # Permessi lettura
    def can_read_global(self) -> bool:
        """Tutti possono leggere memorie globali"""
        return True
    
    def can_read_own(self) -> bool:
        """Tutti possono leggere proprie memorie"""
        return True
    
    def can_read_all_users(self) -> bool:
        """Admin e Engineer vedono memorie di tutti gli utenti"""
        return self.role in [Role.ADMIN, Role.ENGINEER]
    
    # Permessi scrittura
    def can_write_own(self) -> bool:
        """Tutti possono scrivere proprie memorie"""
        return True
    
    def can_write_global(self) -> bool:
        """Solo Admin può scrivere memorie globali"""
        return self.role == Role.ADMIN
    
    def can_manage_users(self) -> bool:
        """Solo Admin può gestire utenti"""
        return self.role == Role.ADMIN
    
    # Namespace
    def get_namespace(self) -> str:
        """Ritorna il namespace personale dell'utente"""
        return f"user_{self.id}"
    
    def to_dict(self) -> dict:
        """Serializza utente (senza password hash per sicurezza)"""
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role.value,
            "display_name": self.display_name
        }

