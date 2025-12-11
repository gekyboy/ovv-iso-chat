"""
Modulo Autenticazione RBAC per OVV ISO Chat v3.2
Gestisce ruoli Admin/Engineer/User con permessi differenziati
"""

from .models import User, Role
from .store import UserStore

__all__ = ["User", "Role", "UserStore"]

