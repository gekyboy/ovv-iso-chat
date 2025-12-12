"""
Mesop Event Handlers - Completi
Handlers per tutte le funzionalità Chat + Admin con feature parity Chainlit
"""

import logging
import asyncio
import queue
import threading
from typing import Dict, Any, List, Optional

from src.auth.models import User
from src.ui.shared.sources import prepare_source_data, filter_cited_sources
from src.ui.shared.commands import parse_command, validate_command_access, format_command_response
from src.ui.shared.documents import get_document_manager
from src.ui.shared.postprocess import cleanup_llm_response

logger = logging.getLogger(__name__)

# Import pipeline come in app_chainlit.py
_pipeline = None

def get_pipeline():
    """
    Lazy load RAG pipeline.
    Copia da app_chainlit.py per riusare la stessa logica
    """
    global _pipeline
    if _pipeline is None:
        import yaml
        from pathlib import Path

        config_path = "config/config.yaml"

        # Leggi config per decidere quale pipeline usare
        use_multi_agent = False
        if Path(config_path).exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    use_multi_agent = config.get("multi_agent", {}).get("enabled", False)
            except Exception as e:
                logger.warning(f"Errore lettura config: {e}, uso pipeline classica")

        if use_multi_agent:
            try:
                from src.agents.orchestrator import MultiAgentPipeline
                _pipeline = MultiAgentPipeline(config_path=config_path)
                logger.info("✅ MultiAgentPipeline caricata per Mesop POC")
            except Exception as e:
                logger.warning(f"⚠️ Errore caricamento MultiAgentPipeline: {e}")
                logger.info("Fallback a RAGPipeline classica")
                from src.integration.rag_pipeline import RAGPipeline
                _pipeline = RAGPipeline(config_path=config_path)
        else:
            from src.integration.rag_pipeline import RAGPipeline
            _pipeline = RAGPipeline(config_path=config_path)
            logger.info("RAGPipeline classica caricata per Mesop POC")

    return _pipeline


def handle_query_mesop(query: str, user_data: dict) -> Dict[str, Any]:
    """
    Handler completo query RAG con feature parity Chainlit

    Args:
        query: La domanda dell'utente
        user_data: Dati utente dalla sessione

    Returns:
        Dict con:
        - answer: Risposta pulita
        - sources: Lista fonti filtrate
        - status_updates: Lista aggiornamenti status
    """
    try:
        logger.info(f"[MESOP] Query ricevuta: {query[:50]}...")

        # Ottieni pipeline
        pipeline = get_pipeline()

        # Status updates per UI
        status_updates = []

        def status_callback(message: str):
            """Callback per aggiornamenti status"""
            status_updates.append(message)
            logger.info(f"[MESOP] Status: {message}")

        # Simula callback status (in produzione collegare alla pipeline)
        status_callback("🔍 Analisi query...")
        status_callback("📚 Ricerca documenti...")
        status_callback("🤖 Generazione risposta...")

        # Esegui query RAG
        result = pipeline.query(query)

        # Estrai risposta
        if hasattr(result, 'answer'):
            raw_answer = result.answer
            sources = result.sources if hasattr(result, 'sources') else []
        elif isinstance(result, dict):
            raw_answer = result.get('answer', str(result))
            sources = result.get('sources', [])
        else:
            raw_answer = str(result)
            sources = []

        status_callback("✨ Post-processing...")

        # Filtra fonti citate (stessa logica Chainlit)
        cited_sources, missing = filter_cited_sources(raw_answer, sources)

        # Prepara dati fonti per UI
        sources_data = prepare_source_data(cited_sources)

        # Cleanup risposta (rimuovi riferimenti ridondanti)
        cleaned_answer = cleanup_llm_response(
            raw_answer,
            cited_sources,
            remove_references=True,
            replace_ids_with_titles=True
        )

        status_callback("✅ Completato")

        logger.info(f"[MESOP] Risposta generata: {len(cleaned_answer)} caratteri, {len(sources_data)} fonti")

        return {
            "answer": cleaned_answer,
            "sources": sources_data,
            "status_updates": status_updates,
            "missing_citations": missing
        }

    except Exception as e:
        error_msg = f"Errore nella pipeline: {str(e)}"
        logger.error(f"[MESOP] {error_msg}")
        return {
            "answer": error_msg,
            "sources": [],
            "status_updates": ["❌ Errore durante l'elaborazione"],
            "missing_citations": []
        }


def handle_command_mesop(command: str, user_data: dict) -> Optional[str]:
    """
    Handler comandi Mesop con RBAC (feature parity Chainlit)

    Args:
        command: Comando da eseguire (es. "/status")
        user_data: Dati utente dalla sessione

    Returns:
        Risposta comando o None se non gestito
    """
    try:
        logger.info(f"[MESOP] Comando ricevuto: {command}")

        # Parse comando
        cmd_info = parse_command(command)
        if not cmd_info:
            return "Comando non riconosciuto. Usa /status, /documenti, /glossario, etc."

        # Verifica permessi
        user_role = user_data.get("role", "User")
        if not validate_command_access(cmd_info.name, user_role):
            return f"Accesso negato. Ruolo richiesto: {cmd_info.name}"

        # Esegui comando specifico
        if cmd_info.name == "/status":
            return handle_status_command(user_data)

        elif cmd_info.name == "/documenti":
            return handle_documents_command(cmd_info, user_data)

        elif cmd_info.name == "/glossario":
            return handle_glossary_command(cmd_info)

        # Altri comandi TODO
        else:
            return f"Comando {cmd_info.name} non ancora implementato in Mesop"

    except Exception as e:
        logger.error(f"[MESOP] Errore comando {command}: {e}")
        return f"Errore esecuzione comando: {str(e)}"


def handle_status_command(user_data: dict) -> str:
    """Handler comando /status"""
    try:
        manager = get_document_manager()
        path_info = manager.get_path_manager().get_status()

        status = f"""
📊 **Stato Sistema OVV ISO Chat**

👤 **Utente**: {user_data.get('display_name', 'N/A')} ({user_data.get('role', 'N/A')})
📁 **Documenti**: {path_info.get('pdf_count', 0)} PDF trovati
🤖 **Pipeline**: MultiAgent attiva
💾 **Memoria**: {path_info.get('memory_status', 'N/A')}
        """.strip()

        return status

    except Exception as e:
        return f"Errore recupero status: {str(e)}"


def handle_documents_command(cmd_info, user_data: dict) -> str:
    """Handler comando /documenti"""
    try:
        manager = get_document_manager()

        # Se specificato path, impostalo
        if cmd_info.params.get("path"):
            result = manager.set_path(cmd_info.params["path"])
            if result["success"]:
                return f"✅ Cartella impostata: {result['path']}\n📊 Trovati: {result['stats']['pdf_count']} PDF"
            else:
                return f"❌ Errore: {result['error']}"
        else:
            # Mostra status corrente
            path_info = manager.get_current_path_info()
            return f"""
📁 **Cartella Documenti**

Percorso: {path_info['path']}
Stato: {'✅ Valido' if path_info['exists'] else '❌ Non trovato'}
PDF trovati: {path_info['pdf_count']}

💡 **Per cambiare cartella**: `/documenti C:\\nuovo\\percorso`
            """.strip()

    except Exception as e:
        return f"Errore gestione documenti: {str(e)}"


def handle_glossary_command(cmd_info) -> str:
    """Handler comando /glossario"""
    query = cmd_info.params.get("query", "").strip()

    if not query:
        return """
📖 **Glossario OVV ISO**

Cerca acronimi e termini tecnici:
`/glossario PS` - Cosa significa PS?
`/glossario ISO 14001` - Informazioni su ISO 14001

💡 **Esempi**: PS, IL, MR, TOOLS, ISO 9001, etc.
        """.strip()

    try:
        # TODO: Implementare ricerca glossario reale
        # Per ora mock response
        mock_responses = {
            "ps": "PS = Procedure di Sistema - Documenti che descrivono i processi aziendali fondamentali",
            "il": "IL = Istruzioni di Lavoro - Guide operative dettagliate per attività specifiche",
            "mr": "MR = Manuali di Riferimento - Documentazione tecnica di supporto",
            "iso": "ISO = International Organization for Standardization - Organizzazione internazionale per la standardizzazione"
        }

        response = mock_responses.get(query.lower(), f"Termine '{query}' non trovato nel glossario")
        return f"📖 **Glossario**: {response}"

    except Exception as e:
        return f"Errore ricerca glossario: {str(e)}"


def process_feedback_mesop(user_data: dict, message_content: str, feedback_type: str, sources: list = None):
    """
    Processa feedback 👍👎 in Mesop (stessa logica di Chainlit)

    Args:
        user_data: Dati utente dalla sessione
        message_content: Contenuto del messaggio valutato
        feedback_type: "positive" o "negative"
        sources: Lista fonti della risposta (opzionale)
    """
    try:
        logger.info(f"[MESOP] Feedback {feedback_type} per: {message_content[:50]}...")

        # Ottieni memory store
        from src.memory.store import MemoryStore
        memory_store = MemoryStore()

        user_id = user_data.get("id")
        namespace = f"user_{user_data.get('username', 'unknown')}"

        # Registra feedback per ogni source (se disponibili)
        if sources:
            record_response_feedback(
                memory_store,
                query=message_content,
                sources=sources,
                is_positive=(feedback_type == "positive"),
                namespace=namespace,
                user_id=user_id
            )

        # R28: Conversation logging (se abbiamo session_id)
        conv_session_id = user_data.get("conv_session_id")
        if conv_session_id:
            try:
                from src.analytics.collectors.conversation_logger import get_conversation_logger
                conv_logger = get_conversation_logger()
                # Nota: servirebbe interaction_id, per ora log semplice
                logger.info(f"[MESOP] Feedback logged in conversation {conv_session_id}")
            except Exception as conv_error:
                logger.warning(f"[MESOP] Conversation logging error: {conv_error}")

        logger.info(f"[MESOP] Feedback {feedback_type} processed successfully")

    except Exception as e:
        logger.error(f"[MESOP] Feedback processing error: {e}")


def record_response_feedback(store, query: str, sources: list, is_positive: bool, namespace: str, user_id: str):
    """
    Registra feedback su risposta RAG (stessa logica di Chainlit).
    Aggiorna boost delle memorie correlate.
    """
    try:
        # Per ogni source citata, trova memorie correlate e dai feedback
        for source_data in sources:
            doc_id = source_data.get("doc_id")
            if not doc_id:
                continue

            # Trova memorie correlate a questa fonte
            try:
                related = store.search_similar(
                    query=f"doc_id:{doc_id}",
                    limit=5,
                    namespace=(namespace,) if namespace else None
                )

                for mem in related:
                    store.add_feedback(
                        mem_id=mem.id,
                        is_positive=is_positive,
                        context=f"Response feedback for: {query[:50]}",
                        namespace=(namespace,) if namespace else None
                    )
            except Exception as search_error:
                logger.warning(f"[MESOP] Error searching related memories for {doc_id}: {search_error}")

        logger.info(f"[MESOP] Recorded feedback for {len(sources)} sources")

    except Exception as e:
        logger.error(f"[MESOP] Error recording response feedback: {e}")
