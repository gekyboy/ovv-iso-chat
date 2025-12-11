"""
Middleware autenticazione Chainlit per OVV ISO Chat v3.2
Gestisce login password e sessione utente
"""

import logging
from typing import Optional

import chainlit as cl

from .store import UserStore
from .models import User, Role

logger = logging.getLogger(__name__)

# Singleton UserStore
_user_store: Optional[UserStore] = None


def get_user_store() -> UserStore:
    """Ottiene istanza singleton UserStore"""
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store


@cl.password_auth_callback
def auth_callback(username: str, password: str) -> Optional[cl.User]:
    """
    Callback autenticazione Chainlit.
    Chiamato quando utente inserisce credenziali.
    
    Returns:
        cl.User se autenticazione ok, None altrimenti
    """
    store = get_user_store()
    user = store.authenticate(username, password)
    
    if user:
        # Crea oggetto cl.User per Chainlit
        return cl.User(
            identifier=user.id,
            metadata={
                "role": user.role.value,
                "username": user.username,
                "display_name": user.display_name
            }
        )
    
    return None


def get_current_user() -> Optional[User]:
    """
    Recupera utente corrente dalla sessione Chainlit.
    
    Returns:
        User o None se non autenticato
    """
    try:
        cl_user = cl.user_session.get("user")
        if cl_user and isinstance(cl_user, cl.User):
            store = get_user_store()
            return store.get_user_by_id(cl_user.identifier)
    except Exception as e:
        logger.debug(f"Nessun utente in sessione: {e}")
    
    return None


def get_current_namespace() -> str:
    """
    Recupera namespace corrente dalla sessione.
    
    Returns:
        Namespace stringa (user_XXX o global)
    """
    user = get_current_user()
    if user:
        return user.get_namespace()
    return "global"


def require_role(*roles: Role):
    """
    Decorator per richiedere ruoli specifici.
    
    Uso:
        @require_role(Role.ADMIN)
        async def admin_only_handler():
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user or user.role not in roles:
                await cl.Message(
                    content="Accesso negato. Non hai i permessi necessari."
                ).send()
                return
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_admin(func):
    """Shortcut per require_role(Role.ADMIN)"""
    return require_role(Role.ADMIN)(func)


def require_engineer_or_admin(func):
    """Shortcut per require_role(Role.ADMIN, Role.ENGINEER)"""
    return require_role(Role.ADMIN, Role.ENGINEER)(func)

