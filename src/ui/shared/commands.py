"""
UI-agnostic Commands Logic
Logica per parsing e dispatch comandi - estratta da Chainlit
"""

from typing import Dict, Any, Optional, Tuple
import logging
import re

logger = logging.getLogger(__name__)


class CommandInfo:
    """Informazioni su un comando riconosciuto"""

    def __init__(self, name: str, args: str = "", params: Dict[str, Any] = None):
        self.name = name
        self.args = args
        self.params = params or {}


def parse_command(content: str) -> Optional[CommandInfo]:
    """
    Parsea un comando dal contenuto del messaggio.

    Args:
        content: Contenuto del messaggio (deve iniziare con /)

    Returns:
        CommandInfo se comando riconosciuto, None altrimenti
    """
    if not content.startswith("/"):
        return None

    content = content.strip()
    parts = content.split()
    command = parts[0].lower()

    # Estrai argomenti (tutto dopo il comando)
    args = " ".join(parts[1:]) if len(parts) > 1 else ""

    # Parse parametri specifici per comando
    params = {}

    # /teach [testo]
    if command == "/teach":
        params["text"] = args

    # /memoria [testo]
    elif command == "/memoria":
        params["text"] = args

    # /status
    elif command == "/status":
        pass  # Nessun parametro

    # /glossario [query]
    elif command == "/glossario":
        params["query"] = args

    # /global [testo]
    elif command == "/global":
        params["text"] = args

    # /memorie [filtri]
    elif command == "/memorie":
        params["filters"] = args

    # /pending
    elif command == "/pending":
        pass

    # /approve [id]
    elif command == "/approve":
        params["proposal_id"] = args.strip()

    # /reject [id]
    elif command == "/reject":
        params["proposal_id"] = args.strip()

    # /documenti [path]
    elif command == "/documenti":
        params["path"] = args

    else:
        logger.warning(f"[parse_command] Comando non riconosciuto: {command}")
        return None

    logger.info(f"[parse_command] Riconosciuto: {command}, args: '{args}'")
    return CommandInfo(command, args, params)


def validate_command_access(command: str, user_role: str) -> bool:
    """
    Valida se l'utente può eseguire un certo comando basato sul suo ruolo.

    Args:
        command: Nome del comando (es. "/global")
        user_role: Ruolo dell'utente (Admin/Engineer/User)

    Returns:
        True se accesso consentito, False altrimenti
    """
    role_hierarchy = {
        "Admin": ["Admin", "Engineer", "User"],
        "Engineer": ["Engineer", "User"],
        "User": ["User"]
    }

    allowed_roles = {
        "/global": ["Admin"],  # Solo Admin
        "/memorie": ["Admin", "Engineer"],  # Admin + Engineer
        "/pending": ["Admin", "Engineer"],  # Admin + Engineer
        "/approve": ["Admin"],  # Solo Admin
        "/reject": ["Admin"],  # Solo Admin
        "/teach": ["Admin", "Engineer", "User"],  # Tutti
        "/memoria": ["Admin", "Engineer", "User"],  # Tutti
        "/status": ["Admin", "Engineer", "User"],  # Tutti
        "/glossario": ["Admin", "Engineer", "User"],  # Tutti
        "/documenti": ["Admin", "Engineer", "User"],  # Tutti
    }

    required_roles = allowed_roles.get(command, ["Admin", "Engineer", "User"])

    if user_role not in role_hierarchy:
        logger.warning(f"[validate_command_access] Ruolo sconosciuto: {user_role}")
        return False

    # L'utente può accedere se il suo ruolo è nella lista dei ruoli consentiti
    # oppure se uno dei ruoli che può impersonare è nella lista
    user_allowed_roles = role_hierarchy[user_role]

    for required_role in required_roles:
        if required_role in user_allowed_roles:
            return True

    logger.warning(f"[validate_command_access] Accesso negato: {user_role} -> {command}")
    return False


def get_command_help() -> Dict[str, str]:
    """
    Restituisce la documentazione dei comandi disponibili.

    Returns:
        Dict comando -> descrizione
    """
    return {
        "/teach": "Insegna qualcosa al sistema (es. /teach La gestione dei rifiuti segue le norme ISO 14001)",
        "/memoria": "Ricorda qualcosa per il tuo namespace (es. /memoria Questo progetto usa Python 3.11)",
        "/status": "Mostra stato del sistema e configurazione corrente",
        "/glossario": "Cerca nel glossario (es. /glossario cosa significa PS)",
        "/global": "Aggiungi memoria globale (solo Admin)",
        "/memorie": "Visualizza memorie (Admin/Engineer)",
        "/pending": "Lista proposte in attesa (Admin/Engineer)",
        "/approve": "Approva proposta (solo Admin) (es. /approve 123)",
        "/reject": "Rifiuta proposta (solo Admin) (es. /reject 123)",
        "/documenti": "Gestisci cartella documenti (es. /documenti o /documenti C:\\percorso)",
    }


def format_command_response(command: str, result: Any, success: bool = True) -> str:
    """
    Formatta la risposta di un comando per l'UI.

    Args:
        command: Nome del comando eseguito
        result: Risultato dell'operazione
        success: True se comando riuscito

    Returns:
        String formattata per l'UI
    """
    if success:
        status = "✅"
        if isinstance(result, str):
            return f"{status} {result}"
        elif isinstance(result, dict):
            lines = [f"{status} Comando {command} eseguito:"]
            for key, value in result.items():
                lines.append(f"  • {key}: {value}")
            return "\n".join(lines)
        else:
            return f"{status} Comando {command} completato"
    else:
        error_msg = result if isinstance(result, str) else "Errore sconosciuto"
        return f"❌ Errore {command}: {error_msg}"
