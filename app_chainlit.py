"""
OVV ISO Chat v3.9.2 - Chainlit UI
Chat interface per RAG su documenti ISO-SGI

Features:
- Autenticazione RBAC (Admin/Engineer/User)
- Feedback Bayesian integrato
- Preview documenti cliccabili
- Namespace multi-utente per memorie
- Apprendimento semi-automatico con conferma utente (R13)
- Glossario con acronimi ambigui (R01)
- Fonti intelligenti con anteprima cliccabile (R14)
- Suggerimento tool pratici (R15)
- Assistenza compilazione tool con follow-up interattivo (R16)
- Segnalazione lacune intelligente (R19)
- Semantic Chunking MR/TOOLS (R30)
- ValidatorAgent anti-hallucination (R26)
- Conversation Logger (R28)
- HyDE Query Enhancement (R23)
"""

# ═══════════════════════════════════════════════════════════════
# MONKEY PATCH: Aumenta timeout Socket.IO per query lunghe
# Default: ping_interval=25s, ping_timeout=20s
# Nuovo: ping_interval=60s, ping_timeout=120s (supporta query fino a 3 min)
# ═══════════════════════════════════════════════════════════════
try:
    from chainlit.server import sio
    # Riconfigura engineio con timeout aumentati
    sio.eio.ping_interval = 60   # 60 secondi tra ping
    sio.eio.ping_timeout = 120   # 120 secondi timeout
except Exception as e:
    pass  # Ignora errori di import al primo avvio

import logging
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

import chainlit as cl

from src.auth.models import User, Role
from src.auth.store import UserStore
from src.memory.learning_detector import LearningDetector, LearningResult
# IMPORTANTE: importa auth_callback per registrare il decorator Chainlit
from src.auth.middleware import auth_callback

# R28: Conversation Logger
from src.analytics.collectors.conversation_logger import (
    get_conversation_logger,
    InteractionStatus
)

# ═══════════════════════════════════════════════════════════════
# F10-B: DATA LAYER NATIVO PER FEEDBACK 👍👎
# Registra SQLite data layer per persistenza conversazioni e feedback
# ═══════════════════════════════════════════════════════════════
try:
    import chainlit.data as cl_data
    from src.data.chainlit_data_layer import get_data_layer
    cl_data._data_layer = get_data_layer()
    logger = logging.getLogger(__name__)
    logger.info("[F10] SQLite Data Layer registered for Chainlit")
except Exception as e:
    # Fallback: continua senza data layer (feedback manuale funziona comunque)
    import logging as _log
    _log.getLogger(__name__).warning(f"[F10] Data layer not available: {e}")

# Singleton UserStore
_user_store = None

def get_user_store() -> UserStore:
    """Ottiene istanza singleton UserStore"""
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store


@cl.password_auth_callback
def auth_callback(username: str, password: str):
    """
    Callback autenticazione Chainlit.
    DEVE essere definito nel file principale per essere riconosciuto da Chainlit.
    """
    store = get_user_store()
    user = store.authenticate(username, password)
    
    if user:
        return cl.User(
            identifier=user.id,
            metadata={
                "role": user.role.value,
                "username": user.username,
                "display_name": user.display_name
            }
        )
    return None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lazy load globals
_pipeline = None
_memory_store = None
_learning_detector = None
_tool_suggester = None
_conversation_logger = None


def get_conv_logger():
    """Lazy load conversation logger (R28)"""
    global _conversation_logger
    if _conversation_logger is None:
        _conversation_logger = get_conversation_logger()
    return _conversation_logger


def get_learning_detector() -> LearningDetector:
    """Lazy load learning detector"""
    global _learning_detector
    if _learning_detector is None:
        _learning_detector = LearningDetector()
    return _learning_detector


def get_tool_suggester():
    """Lazy load tool suggester (R15)"""
    global _tool_suggester
    if _tool_suggester is None:
        from src.integration.tool_suggester import ToolSuggester
        _tool_suggester = ToolSuggester(mapping_path="config/tools_mapping.json")
    return _tool_suggester


# R06: Disambiguazione contestuale acronimi (v2.0 fusa)
_disambiguator = None
_preference_store = None

def get_disambiguator():
    """Lazy load contextual disambiguator (R06 v2.0)"""
    global _disambiguator, _preference_store
    if _disambiguator is None:
        from src.integration.disambiguator import (
            ContextualDisambiguator,
            UserPreferenceStore
        )
        pipeline = get_pipeline()
        _preference_store = UserPreferenceStore()
        _disambiguator = ContextualDisambiguator(
            glossary_resolver=pipeline.glossary, 
            preference_store=_preference_store
        )
    return _disambiguator

def get_preference_store():
    """Lazy load preference store (R06 v2.0)"""
    global _preference_store
    if _preference_store is None:
        from src.integration.disambiguator import UserPreferenceStore
        _preference_store = UserPreferenceStore()
    return _preference_store


def get_pipeline():
    """
    Lazy load RAG pipeline.
    Usa MultiAgentPipeline (R24) se abilitata, altrimenti RAGPipeline classica.
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
                logger.info("✅ MultiAgentPipeline (R24) caricata")
            except Exception as e:
                logger.warning(f"⚠️ Errore caricamento MultiAgentPipeline: {e}")
                logger.info("Fallback a RAGPipeline classica")
                from src.integration.rag_pipeline import RAGPipeline
                _pipeline = RAGPipeline(config_path=config_path)
        else:
            from src.integration.rag_pipeline import RAGPipeline
            _pipeline = RAGPipeline(config_path=config_path)
            logger.info("RAGPipeline classica caricata")
    
    return _pipeline


def get_memory_store():
    """
    Lazy load memory store.
    Allineato con test_ui.py: usa memory_store dalla pipeline se disponibile,
    altrimenti crea istanza standalone.
    """
    global _memory_store
    if _memory_store is None:
        # Prima prova a usare memory_store dalla pipeline (come test_ui.py)
        try:
            pipeline = get_pipeline()
            if hasattr(pipeline, 'memory_store') and pipeline.memory_store is not None:
                _memory_store = pipeline.memory_store
                logger.info("Memory store: usando istanza da pipeline")
            else:
                raise AttributeError("Pipeline non ha memory_store")
        except Exception as e:
            # Fallback: crea istanza standalone
            from src.memory.store import MemoryStore
            _memory_store = MemoryStore(config_path="config/config.yaml")
            logger.info(f"Memory store: creato standalone ({e})")
    return _memory_store


# ============================================================
# R14: FONTI INTELLIGENTI (Solo se citate)
# ============================================================

def find_pdf_by_doc_id(doc_id: str, pdf_dir: str = "data/input_docs") -> Optional[Path]:
    """
    Trova il file PDF corrispondente a un doc_id.
    
    Logica di matching:
    1. Cerca file che inizia con doc_id (es. "PS-06_01" -> "PS-06_01_Rev.04_...")
    2. Normalizza separatori ("-" vs "_") per match robusto
    
    Args:
        doc_id: ID documento (es. "PS-06_01", "IL-06_02")
        pdf_dir: Directory dove cercare i PDF
        
    Returns:
        Path al PDF o None se non trovato
        
    Examples:
        >>> find_pdf_by_doc_id("PS-06_01")
        Path("data/input_docs/PS-06_01_Rev.04_Gestione della sicurezza....pdf")
    """
    pdf_path = Path(pdf_dir)
    if not pdf_path.exists():
        logger.debug(f"[PDF] Directory non trovata: {pdf_dir}")
        return None
    
    # Normalizza doc_id per confronto (rimuovi spazi, uppercase)
    doc_id_clean = doc_id.strip().upper()
    
    # Pattern di matching: doc_id all'inizio del nome file
    for pdf_file in pdf_path.glob("*.pdf"):
        filename = pdf_file.stem.upper()  # Senza estensione, uppercase
        
        # Match diretto all'inizio
        if filename.startswith(doc_id_clean):
            logger.debug(f"[PDF] Match trovato: {doc_id} -> {pdf_file.name}")
            return pdf_file
        
        # Match con normalizzazione separatori ("-" <-> "_")
        doc_id_normalized = doc_id_clean.replace("-", "_").replace("__", "_")
        filename_normalized = filename.replace("-", "_").replace("__", "_")
        
        if filename_normalized.startswith(doc_id_normalized):
            logger.debug(f"[PDF] Match normalizzato: {doc_id} -> {pdf_file.name}")
            return pdf_file
    
    logger.debug(f"[PDF] Nessun match per: {doc_id}")
    return None


def filter_cited_sources(
    answer: str,
    sources: List
) -> tuple:
    """
    Filtra le sources mantenendo SOLO quelle effettivamente citate nel testo.
    
    Args:
        answer: Testo della risposta LLM
        sources: Lista completa delle sources dal retrieval
        
    Returns:
        Tuple di:
        - Lista sources filtrate (solo quelle citate)
        - Lista doc_id citati nel testo ma non trovati nelle sources
    """
    from src.integration.citation_extractor import (
        extract_cited_docs, 
        match_doc_ids,
        normalize_doc_id
    )
    
    # 1. Estrai doc_id citati nel testo
    cited_doc_ids = extract_cited_docs(answer)
    
    if not cited_doc_ids:
        return [], []
    
    # 2. Filtra sources che matchano
    cited_sources = []
    found_ids = set()
    
    for source in sources:
        source_id = source.doc_id
        
        for cited_id in cited_doc_ids:
            if match_doc_ids(cited_id, source_id):
                if source_id not in found_ids:  # Evita duplicati
                    cited_sources.append(source)
                    found_ids.add(source_id)
                break
    
    # 3. Identifica citazioni non trovate (possibili allucinazioni)
    normalized_found = {normalize_doc_id(s.doc_id) for s in cited_sources}
    missing = [
        cid for cid in cited_doc_ids 
        if normalize_doc_id(cid) not in normalized_found
    ]
    
    if missing:
        logger.warning(f"[R14] Citazioni non trovate nelle sources: {missing}")
    
    return cited_sources, missing


# ============================================================
# POST-PROCESSING: Pulizia Risposta LLM
# ============================================================

def remove_llm_references_section(answer: str) -> str:
    """
    Rimuove la sezione "Riferimenti:" generata dall'LLM.
    
    Il sistema aggiunge le fonti automaticamente nel footer,
    quindi la sezione generata dall'LLM è ridondante.
    
    Args:
        answer: Risposta LLM originale
        
    Returns:
        Risposta senza sezione riferimenti
    """
    # Pattern per rimuovere sezione riferimenti
    patterns = [
        r'\n*\*?\*?Riferimenti:?\*?\*?\s*\n[-•*\s]*[A-Z]{2,5}-?\d{2}[_-]?\d{2}.*?(?=\n\n|\n---|\Z)',
        r'\n*\*?\*?Fonti:?\*?\*?\s*\n[-•*\s]*[A-Z]{2,5}-?\d{2}[_-]?\d{2}.*?(?=\n\n|\n---|\Z)',
        r'\n*\*?\*?Documenti citati:?\*?\*?\s*\n.*?(?=\n\n|\n---|\Z)',
        r'\n*\*?\*?Riferimenti\s+normativi:?\*?\*?\s*\n.*?(?=\n\n|\n---|\Z)',
    ]
    
    cleaned = answer
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    
    # Rimuovi anche liste di doc_id alla fine
    cleaned = re.sub(r'\n+[-•*]\s*[A-Z]{2,5}-\d{2}[_-]\d{2}\s*\n*$', '', cleaned)
    
    return cleaned.strip()


def replace_doc_ids_with_titles(
    answer: str,
    sources: List
) -> str:
    """
    Sostituisce i doc_id nel testo con i titoli leggibili tra virgolette.
    
    Es: "Secondo PS-06_01..." → "Secondo \"Gestione della sicurezza\"..."
    
    Args:
        answer: Risposta LLM
        sources: Lista sources con metadata.title
        
    Returns:
        Risposta con titoli al posto di doc_id
    """
    # Costruisci mapping doc_id -> title
    doc_id_to_title = {}
    for source in sources:
        doc_id = source.doc_id.upper()
        title = source.metadata.get("title", "")
        if title and title != doc_id:
            doc_id_to_title[doc_id] = title
            # Aggiungi anche varianti
            doc_id_to_title[doc_id.replace("_", "-")] = title
            doc_id_to_title[doc_id.replace("-", "_")] = title
    
    if not doc_id_to_title:
        logger.debug("[PP] Nessun mapping doc_id -> title disponibile")
        return answer
    
    logger.debug(f"[PP] Mapping titoli: {list(doc_id_to_title.keys())}")
    
    # Pattern per citazioni
    citation_pattern = r'\b(PS|IL|MR|TOOLS)-?\d{2}[_-]?\d{2}\b'
    
    def replace_with_title(match):
        doc_id = match.group(0).upper().replace("-", "_")
        normalized = doc_id.replace("_", "-")
        
        title = doc_id_to_title.get(doc_id) or doc_id_to_title.get(normalized)
        if title:
            # Usa virgolette italiane per citare il titolo
            return f'"{title}"'
        return match.group(0)  # Mantieni originale se non trovato
    
    result = re.sub(citation_pattern, replace_with_title, answer, flags=re.IGNORECASE)
    logger.debug(f"[PP] Sostituzione titoli completata")
    return result


def sanitize_invalid_citations(
    answer: str,
    valid_doc_ids: set,
    doc_id_to_title: Dict[str, str]
) -> str:
    """
    Rimuove citazioni invalide dalla risposta (allucinazioni).
    NON sostituisce con titoli - quello lo fa replace_doc_ids_with_titles().
    
    Args:
        answer: Risposta LLM originale
        valid_doc_ids: Set di doc_id effettivamente disponibili (uppercase)
        doc_id_to_title: Non usato, mantenuto per compatibilità
        
    Returns:
        Risposta pulita senza citazioni invalide
    """
    # Pattern per citazioni
    citation_pattern = r'\b(PS|IL|MR|TOOLS)-?\d{2}[_-]?\d{2}\b'
    
    def remove_invalid(match):
        doc_id = match.group(0).upper().replace("-", "_")
        normalized = doc_id.replace("_", "-")
        
        # Verifica se valido
        is_valid = (
            doc_id in valid_doc_ids or 
            normalized in valid_doc_ids or
            any(doc_id in v.upper() or normalized in v.upper() for v in valid_doc_ids)
        )
        
        if is_valid:
            # Valido - mantieni (verrà sostituito dopo da replace_doc_ids_with_titles)
            return match.group(0)
        else:
            # Invalido - rimuovi
            logger.debug(f"[SANITIZE] Rimossa citazione invalida: {match.group(0)}")
            return ""
    
    cleaned = re.sub(citation_pattern, remove_invalid, answer, flags=re.IGNORECASE)
    
    # Pulisci frasi rimaste incomplete
    cleaned = re.sub(r'Secondo\s*,', 'Secondo la procedura,', cleaned)
    cleaned = re.sub(r'nel documento\s*,', 'nel documento,', cleaned)
    cleaned = re.sub(r'la procedura\s*,', 'la procedura,', cleaned)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    
    return cleaned.strip()


def create_source_elements(
    sources: List,
    max_preview_chars: int = 800,
    include_pdf: bool = True
) -> List:
    """
    Crea elementi Chainlit cliccabili per le fonti.
    
    Mostra SOLO il titolo leggibile (es. "Gestione dei rifiuti")
    NON mostra: doc_type (PS/IL/MR), capitolo, revisione
    
    Args:
        sources: Lista sources filtrate (solo quelle citate)
        max_preview_chars: Massimo caratteri per anteprima
        include_pdf: Se True, include anche link al PDF
        
    Returns:
        Lista di cl.Text + cl.File elements
    """
    elements = []
    seen_pdfs = set()  # Evita duplicati PDF
    
    for i, source in enumerate(sources, 1):
        # Estrai info
        doc_id = source.doc_id
        score = getattr(source, 'rerank_score', None) or getattr(source, 'score', 0)
        text = source.text or ""
        
        # ═══════════════════════════════════════════════════════════════
        # TITOLO LEGGIBILE: usa campo "title" dal metadata
        # Es. "Gestione dei rifiuti" invece di "PS-06_01"
        # ═══════════════════════════════════════════════════════════════
        title = source.metadata.get("title", "")
        if not title or title == doc_id:
            # Fallback: usa doc_id se title vuoto
            title = doc_id
        
        # Prepara anteprima testo (limita caratteri)
        preview = text[:max_preview_chars]
        if len(text) > max_preview_chars:
            preview += "\n\n[... testo troncato ...]"
        
        # ═══════════════════════════════════════════════════════════════
        # SIDEBAR: Solo titolo leggibile, no PS/Cap/Rev
        # ═══════════════════════════════════════════════════════════════
        sidebar_content = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📄 **{title}**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{preview}

─────────────────────────────────────────────
📊 **Rilevanza:** {score:.0%}
🔗 **Riferimento:** {doc_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
        
        # Crea elemento Text con display="side"
        text_element = cl.Text(
            name=f"📄 {title}",  # Solo titolo nel nome (visibile nella UI)
            content=sidebar_content,
            display="side"
        )
        elements.append(text_element)
        
        # ═══════════════════════════════════════════════════════════════
        # PDF: Aggiungi PDF consultabile (non scaricabile)
        # Nome completo del file inclusa revisione
        # ═══════════════════════════════════════════════════════════════
        if include_pdf and doc_id not in seen_pdfs:
            pdf_path = find_pdf_by_doc_id(doc_id)
            if pdf_path and pdf_path.exists():
                try:
                    # Usa nome completo del file (es. PS-06_01_Rev.04_Gestione della sicurezza.pdf)
                    pdf_filename = pdf_path.stem  # Nome senza estensione
                    pdf_element = cl.Pdf(
                        name=f"📖 {pdf_filename}",  # Nome completo con revisione
                        path=str(pdf_path),
                        display="side",  # Sidebar per consultazione
                        page=1  # Apri alla prima pagina
                    )
                    elements.append(pdf_element)
                    seen_pdfs.add(doc_id)
                    logger.debug(f"[PDF] Aggiunto consultabile: {pdf_path.name}")
                except Exception as e:
                    logger.warning(f"[PDF] Errore creazione elemento: {e}")
    
    return elements


def format_sources_footer(
    cited_sources: List,
    missing_citations: List[str] = None
) -> str:
    """
    Formatta il footer con le fonti citate.
    Separa documenti PDF dal glossario.
    
    Args:
        cited_sources: Sources effettivamente citate
        missing_citations: Ignorato (le citazioni invalide sono già sanitizzate)
        
    Returns:
        Stringa markdown per il footer
    """
    if not cited_sources:
        return ""  # Niente footer se nessuna fonte
    
    # Separa documenti PDF dal glossario
    pdf_sources = []
    glossary_sources = []
    
    for source in cited_sources:
        doc_id = source.doc_id
        if doc_id.startswith("GLOSSARY"):
            glossary_sources.append(source)
        else:
            pdf_sources.append(source)
    
    footer = ""
    
    # Prima i documenti PDF
    if pdf_sources:
        footer += "\n\n---\n📚 **Fonti consultate:**\n"
        for source in pdf_sources:
            doc_id = source.doc_id
            title = source.metadata.get("title", "")
            revision = source.metadata.get("revision", "")
            
            # Nome COMPLETO: doc_id_Rev.XX_Titolo italiano
            if title and revision:
                full_name = f"{doc_id}_Rev.{revision}_{title}"
            elif title:
                full_name = f"{doc_id}_{title}"
            else:
                full_name = doc_id
            
            footer += f"- 📄 {full_name}\n"
    
    # Poi il glossario (separato con riga vuota)
    if glossary_sources:
        footer += "\n📖 **Termini glossario:**\n"
        for source in glossary_sources:
            # Per glossario: mostra solo il termine
            term = source.doc_id.replace("GLOSSARY_", "")
            title = source.metadata.get("title", term)
            footer += f"- 📝 {title}\n"
    
    return footer


async def warmup_models():
    """Pre-carica modelli all'avvio"""
    logger.info("Warmup modelli in corso...")
    start = datetime.now()
    
    try:
        # Warmup LLM via Ollama
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "http://localhost:11434/api/generate",
                    json={"model": "llama3.1:8b-instruct-q4_K_M", "prompt": "Ciao", "stream": False},
                    timeout=120
                )
            logger.info("LLM warmup OK")
        except Exception as e:
            logger.warning(f"LLM warmup fallito: {e}")
        
        # Warmup pipeline (compatibile con RAGPipeline e MultiAgentPipeline)
        pipeline = get_pipeline()
        
        # RAGPipeline ha indexer, flash_rank, glossary come proprietà dirette
        # MultiAgentPipeline usa lazy loading tramite gli agenti
        if hasattr(pipeline, 'indexer'):
            _ = pipeline.indexer
            _ = pipeline.flash_rank
            _ = pipeline.glossary
            logger.info("RAGPipeline warmup OK")
        else:
            # MultiAgentPipeline - carica il grafo degli agenti
            _ = pipeline.graph
            logger.info("MultiAgentPipeline warmup OK")
        
        elapsed = (datetime.now() - start).total_seconds()
        logger.info(f"Warmup completato in {elapsed:.1f}s")
        
    except Exception as e:
        logger.error(f"Errore warmup: {e}")


@cl.on_chat_start
async def on_chat_start():
    """Inizializzazione sessione chat"""
    # Recupera utente autenticato da Chainlit
    cl_user = cl.user_session.get("user")
    
    if cl_user and cl_user.metadata:
        # Usa direttamente metadata dal cl.User (già popolato dal callback auth)
        role_str = cl_user.metadata.get("role", "user")
        username = cl_user.metadata.get("username", cl_user.identifier)
        display_name = cl_user.metadata.get("display_name", username)
        
        # Crea oggetto User dal metadata
        from src.auth.models import User, Role
        user = User(
            id=cl_user.identifier,
            username=username,
            password_hash="",  # Non serve qui
            role=Role(role_str),
            display_name=display_name
        )
        
        # Salva in sessione
        cl.user_session.set("app_user", user)
        cl.user_session.set("namespace", f"user_{username}")
        cl.user_session.set("history", [])
        
        # R28: Inizia sessione per logging conversazioni
        conv_logger = get_conv_logger()
        conv_session = conv_logger.start_session(
            user_id=user.id,
            user_role=role_str,
            client_info={
                "display_name": display_name,
                "login_time": datetime.now().isoformat()
            }
        )
        cl.user_session.set("conv_session_id", conv_session.id)
        logger.info(f"[R28] Conversation session started: {conv_session.id}")
        
        # Messaggio benvenuto con pulsanti cliccabili
        role_emoji = {"admin": "👑", "engineer": "🔧", "user": "👤"}.get(role_str, "👤")
        
        # Pulsanti comandi rapidi
        quick_actions = [
            cl.Action(name="cmd_status", payload={}, label="📊 Status"),
            cl.Action(name="cmd_glossario", payload={}, label="📚 Glossario"),
            cl.Action(name="cmd_documenti", payload={}, label="📂 Documenti"),
            cl.Action(name="cmd_help", payload={}, label="❓ Aiuto"),
        ]
        
        await cl.Message(
            content=f"Benvenuto **{display_name}**! {role_emoji} Ruolo: `{role_str}`\n\n"
                    f"Chiedimi qualsiasi cosa sui documenti ISO (PS, IL, MR, TOOLS).",
            actions=quick_actions
        ).send()
        
        # F10: Path manager disponibile ma non mostriamo status all'avvio
        # (L'utente può usare /documenti per gestire la cartella)
        from src.ingestion.path_manager import get_path_manager
        try:
            manager = get_path_manager()
            if manager.show_startup_selector():
                await show_path_selector()
            # Rimossa riga "📂 Documenti: input_docs (150 file)" - non utile all'utente
        except Exception as e:
            logger.warning(f"Errore path manager all'avvio: {e}")
        
        # Warmup in background NON BLOCCANTE (prima sessione)
        # Non usiamo await per non bloccare la sessione
        global _pipeline
        if _pipeline is None:
            import asyncio
            asyncio.create_task(warmup_models())
            logger.info("Warmup avviato in background (non bloccante)")
        
        return
    
    # Fallback se non autenticato
    await cl.Message(content="Errore autenticazione. Ricarica la pagina.").send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handler principale messaggi"""
    user: User = cl.user_session.get("app_user")
    namespace = cl.user_session.get("namespace", "global")
    
    if not user:
        await cl.Message(content="Sessione scaduta. Ricarica la pagina.").send()
        return
    
    content = message.content.strip()
    
    # F10: Check se stiamo aspettando input path (da pulsante "Cambia Cartella")
    if cl.user_session.get("waiting_for_path_input"):
        cl.user_session.set("waiting_for_path_input", False)
        
        from src.ingestion.path_manager import get_path_manager
        
        new_path = content
        manager = get_path_manager()
        result = manager.set_path(new_path)
        
        if result.valid:
            msg = f"✅ **Cartella impostata!**\n\n"
            msg += f"📍 `{result.path}`\n\n"
            msg += f"📊 **Documenti trovati**: {result.pdf_count}\n"
            msg += f"  - PS: {result.ps_count}\n"
            msg += f"  - IL: {result.il_count}\n"
            msg += f"  - MR: {result.mr_count}\n"
            msg += f"  - TOOLS: {result.tools_count}\n"
            await cl.Message(content=msg, author="Sistema").send()
        else:
            await cl.Message(
                content=f"❌ **Percorso non valido**\n\n{result.error}\n\n"
                        f"Riprova con `/documenti` e poi clicca 'Cambia Cartella'.",
                author="Sistema"
            ).send()
        return
    
    # Gestisci comandi speciali
    if content.startswith("/"):
        handled = await handle_command(content, user, namespace)
        if handled:
            return
    
    # R16: Verifica follow-up teach (domanda su campo specifico)
    if await check_teach_followup(content, user):
        return  # Gestito come follow-up
    
    # Rileva pattern di apprendimento (R13)
    detector = get_learning_detector()
    learning = detector.detect(content)
    
    if learning and learning.confidence >= 0.75:
        # L'utente sta insegnando qualcosa - mostra popup conferma
        await show_learning_confirmation(learning, user, namespace)
        return  # Aspetta conferma prima di continuare
    
    # R06: Disambiguazione contestuale intelligente
    # Controlla se ci sono acronimi ambigui da chiarire
    disambiguated_query = await check_disambiguation(content, user.id)
    
    if disambiguated_query is None:
        # Serve input utente per disambiguazione, aspetta callback
        return
    
    # Query RAG normale (con query eventualmente disambiguata)
    await handle_query(disambiguated_query, user, namespace)


async def handle_command(content: str, user: User, namespace: str) -> bool:
    """Gestisce comandi speciali. Ritorna True se gestito."""
    
    # /teach
    if content.lower().startswith("/teach"):
        await handle_teach(content)
        return True
    
    # /memoria
    if content.lower().startswith("/memoria"):
        await handle_memoria(content, user, namespace)
        return True
    
    # /status
    if content.lower().startswith("/status"):
        await handle_status(user)
        return True
    
    # /glossario
    if content.lower().startswith("/glossario"):
        await handle_glossario(content)
        return True
    
    # /global (solo Admin)
    if content.lower().startswith("/global"):
        if user.can_write_global():
            await handle_global_memory(content)
        else:
            await cl.Message(content="Accesso negato. Solo Admin puo' gestire memorie globali.").send()
        return True
    
    # /memorie (Admin/Engineer)
    if content.lower().startswith("/memorie"):
        if user.can_read_all_users():
            await handle_view_memories(content, user)
        else:
            await cl.Message(content="Accesso negato. Solo Admin/Engineer possono vedere memorie utenti.").send()
        return True
    
    # /pending (Admin/Engineer) - Lista proposte in attesa
    if content.lower().startswith("/pending"):
        if user.can_read_all_users():
            await handle_pending_list(user)
        else:
            await cl.Message(content="Accesso negato. Solo Admin/Engineer possono vedere le proposte.").send()
        return True
    
    # /approve (solo Admin) - Approva proposta
    if content.lower().startswith("/approve"):
        if user.can_write_global():
            await handle_approve(content, user)
        else:
            await cl.Message(content="Accesso negato. Solo Admin puo' approvare proposte.").send()
        return True
    
    # /reject (Admin/Engineer) - Rifiuta proposta
    if content.lower().startswith("/reject"):
        if user.can_read_all_users():
            await handle_reject(content, user)
        else:
            await cl.Message(content="Accesso negato. Solo Admin/Engineer possono rifiutare proposte.").send()
        return True
    
    # /teach_stats (Admin/Engineer) - R16: Statistiche teach
    if content.lower().startswith("/teach_stats"):
        if user.can_read_all_users():
            await handle_teach_stats()
        else:
            await cl.Message(content="Accesso negato. Solo Admin/Engineer possono vedere le statistiche.").send()
        return True
    
    # /gaps (Admin/Engineer) - R19: Lacune segnalate
    if content.lower().startswith("/gaps"):
        if user.can_read_all_users():
            await handle_gaps_command()
        else:
            await cl.Message(content="Accesso negato. Solo Admin/Engineer possono vedere le lacune.").send()
        return True
    
    # /acronyms (Admin/Engineer) - R05: Gestione acronimi estratti
    if content.lower().startswith("/acronyms"):
        if user.can_read_all_users():
            await handle_acronyms_command(content, user)
        else:
            await cl.Message(content="Accesso negato. Solo Admin/Engineer possono gestire gli acronimi.").send()
        return True
    
    # /history - R28: Cronologia conversazioni
    if content.lower().startswith("/history"):
        await handle_history_command(content, user)
        return True
    
    # /clear_history - Pulisce cronologia sessione corrente
    if content.lower().startswith("/clear_history") or content.lower() == "/clear":
        await handle_clear_history()
        return True
    
    # /documenti - F10: Gestione cartella documenti
    if content.lower().startswith("/documenti"):
        await handle_documenti_command(content, user)
        return True
    
    return False


# ═══════════════════════════════════════════════════════════════════════════
# F10: DOCUMENT PATH MANAGEMENT - Selezione cartella documenti
# ═══════════════════════════════════════════════════════════════════════════

async def show_path_selector():
    """
    Opzione B: Mostra selettore cartella all'avvio.
    L'utente può confermare il path corrente o cambiarlo.
    """
    from src.ingestion.path_manager import get_path_manager
    
    manager = get_path_manager()
    current = manager.get_current_path()
    status = manager.get_status()
    recents = manager.get_recent_paths(limit=3)
    
    # Costruisci messaggio
    content = "📂 **Seleziona cartella documenti**\n\n"
    content += f"📍 **Attuale**: `{current}`\n"
    
    if status["is_valid"]:
        content += f"   _{status['pdf_count']} documenti trovati_\n"
    else:
        content += "   ⚠️ _Path non valido_\n"
    
    # Mostra recenti
    if recents:
        content += "\n📋 **Usati di recente**:\n"
        for i, r in enumerate(recents, 1):
            content += f"{i}. `{r.path}` ({r.pdf_count} PDF)\n"
    
    content += "\n_Clicca per selezionare o usa `/documenti <percorso>` per cambiare._"
    
    # Azioni
    actions = [
        cl.Action(
            name="confirm_current_path",
            payload={"path": str(current)},
            label=f"✅ Usa {current.name}"
        ),
        cl.Action(
            name="use_default_path",
            payload={},
            label="🔄 Usa default"
        )
    ]
    
    # Aggiungi azioni per recenti (max 2)
    for i, r in enumerate(recents[:2]):
        if str(r.path) != str(current):
            actions.append(cl.Action(
                name="select_recent_path",
                payload={"path": r.path, "index": i},
                label=f"📁 {Path(r.path).name}"
            ))
    
    await cl.Message(
        content=content,
        author="Sistema",
        actions=actions
    ).send()


async def show_path_status_brief():
    """Mostra status breve del path (quando non c'è selector all'avvio)"""
    from src.ingestion.path_manager import get_path_manager
    
    manager = get_path_manager()
    status = manager.get_status()
    
    if status["is_valid"]:
        content = f"📂 Documenti: `{Path(status['current_path']).name}` ({status['pdf_count']} file)"
    else:
        content = f"⚠️ Cartella documenti non valida. Usa `/documenti` per configurare."
    
    await cl.Message(content=content, author="Sistema").send()


@cl.action_callback("confirm_current_path")
async def on_confirm_current_path(action: cl.Action):
    """Conferma path corrente"""
    path = action.payload.get("path")
    await cl.Message(
        content=f"✅ Confermato: `{path}`",
        author="Sistema"
    ).send()


@cl.action_callback("use_default_path")
async def on_use_default_path(action: cl.Action):
    """Usa path di default"""
    from src.ingestion.path_manager import get_path_manager
    
    manager = get_path_manager()
    manager.reset_to_default()
    
    await cl.Message(
        content=f"✅ Path resettato a default: `{manager.get_default_path()}`",
        author="Sistema"
    ).send()


@cl.action_callback("select_recent_path")
async def on_select_recent_path(action: cl.Action):
    """Seleziona un path recente"""
    from src.ingestion.path_manager import get_path_manager
    
    path = action.payload.get("path")
    manager = get_path_manager()
    result = manager.set_path(path)
    
    if result.valid:
        await cl.Message(
            content=f"✅ Cartella cambiata: `{path}` ({result.pdf_count} PDF)",
            author="Sistema"
        ).send()
    else:
        await cl.Message(
            content=f"❌ Errore: {result.error}",
            author="Sistema"
        ).send()


@cl.action_callback("cmd_documenti_recenti")
async def on_cmd_documenti_recenti(action: cl.Action):
    """Mostra path recenti (cliccabile)"""
    from src.ingestion.path_manager import get_path_manager
    
    manager = get_path_manager()
    recents = manager.get_recent_paths(limit=10)
    
    if not recents:
        await cl.Message(
            content="📋 Nessun path recente salvato.",
            author="Sistema"
        ).send()
        return
    
    content = "📋 **Path recenti**:\n\n"
    actions = []
    
    for i, r in enumerate(recents, 1):
        date_str = r.last_used.strftime("%d/%m/%Y %H:%M")
        label = f" - {r.label}" if r.label else ""
        content += f"{i}. `{r.path}`{label}\n"
        content += f"   _{r.pdf_count} PDF, ultimo uso: {date_str}_\n\n"
        
        # Aggiungi pulsante per selezionare questo path
        actions.append(cl.Action(
            name="select_recent_path",
            payload={"path": r.path, "index": i},
            label=f"📁 Usa #{i}"
        ))
    
    await cl.Message(
        content=content,
        author="Sistema",
        actions=actions[:5]  # Max 5 pulsanti
    ).send()


@cl.action_callback("cmd_documenti_reset")
async def on_cmd_documenti_reset(action: cl.Action):
    """Reset a default (cliccabile)"""
    from src.ingestion.path_manager import get_path_manager
    
    manager = get_path_manager()
    manager.reset_to_default()
    
    await cl.Message(
        content=f"✅ Path resettato a default: `{manager.get_default_path()}`",
        author="Sistema"
    ).send()


@cl.action_callback("cmd_documenti_cambia")
async def on_cmd_documenti_cambia(action: cl.Action):
    """Richiede inserimento nuovo path"""
    await cl.Message(
        content="📝 **Inserisci il percorso della cartella documenti:**\n\n"
                "Esempio: `D:\\Documenti\\ISO` o `C:\\Users\\Mario\\Documents\\PDF`\n\n"
                "_Digita il percorso e premi Invio._",
        author="Sistema"
    ).send()
    
    # Imposta flag per intercettare prossimo messaggio come path
    cl.user_session.set("waiting_for_path_input", True)


async def handle_documenti_command(content: str, user: User):
    """
    F10: Gestisce comando /documenti per gestione cartella documenti.
    
    Comandi:
    - /documenti → status + comandi disponibili
    - /documenti scan → forza scansione
    - /documenti recenti → lista path recenti
    - /documenti reset → torna a default
    - /documenti <percorso> → cambia cartella
    """
    from src.ingestion.path_manager import get_path_manager
    
    parts = content.split(maxsplit=1)
    subcommand = parts[1].strip() if len(parts) > 1 else ""
    
    manager = get_path_manager()
    
    # Verifica permessi per modifiche
    can_modify = user.role.value in ["admin", "engineer"]
    
    # /documenti - Mostra status con pulsanti cliccabili
    if not subcommand:
        status_msg = manager.format_status_message()
        
        # Crea azioni cliccabili
        actions = [
            cl.Action(
                name="cmd_documenti_recenti",
                payload={},
                label="📋 Path Recenti"
            )
        ]
        
        if can_modify:
            actions.extend([
                cl.Action(
                    name="cmd_documenti_reset",
                    payload={},
                    label="🔄 Reset Default"
                ),
                cl.Action(
                    name="cmd_documenti_cambia",
                    payload={},
                    label="📂 Cambia Cartella"
                )
            ])
        
        await cl.Message(
            content=status_msg,
            author="Sistema",
            actions=actions
        ).send()
        return
    
    # /documenti recenti - Mostra path recenti
    if subcommand == "recenti":
        recents = manager.get_recent_paths(limit=10)
        
        if not recents:
            await cl.Message(
                content="📋 Nessun path recente salvato.",
                author="Sistema"
            ).send()
            return
        
        content = "📋 **Path recenti**:\n\n"
        for i, r in enumerate(recents, 1):
            date_str = r.last_used.strftime("%d/%m/%Y %H:%M")
            label = f" - {r.label}" if r.label else ""
            content += f"{i}. `{r.path}`{label}\n"
            content += f"   _{r.pdf_count} PDF, ultimo uso: {date_str}_\n\n"
        
        await cl.Message(content=content, author="Sistema").send()
        return
    
    # /documenti reset - Torna a default
    if subcommand == "reset":
        if not can_modify:
            await cl.Message(
                content="⛔ Permessi insufficienti. Richiesto ruolo: admin o engineer",
                author="Sistema"
            ).send()
            return
        
        manager.reset_to_default()
        await cl.Message(
            content=f"✅ Path resettato a default: `{manager.get_default_path()}`",
            author="Sistema"
        ).send()
        return
    
    # /documenti <percorso> - Cambia cartella
    if not can_modify:
        await cl.Message(
            content="⛔ Permessi insufficienti. Richiesto ruolo: admin o engineer",
            author="Sistema"
        ).send()
        return
    
    new_path = subcommand
    
    # Valida e imposta
    result = manager.set_path(new_path)
    
    if result.valid:
        content = f"✅ **Cartella cambiata!**\n\n"
        content += f"📍 **Nuovo path**: `{result.path}`\n\n"
        content += f"📊 **Documenti trovati**: {result.pdf_count}\n"
        content += f"  - PS: {result.ps_count}\n"
        content += f"  - IL: {result.il_count}\n"
        content += f"  - MR: {result.mr_count}\n"
        content += f"  - TOOLS: {result.tools_count}\n"
        
        await cl.Message(content=content, author="Sistema").send()
    else:
        await cl.Message(
            content=f"❌ **Errore**: {result.error}",
            author="Sistema"
        ).send()


async def handle_teach_stats():
    """R16: Mostra statistiche teach per Admin"""
    tracker = get_feedback_tracker()
    stats = tracker.get_stats()
    
    lines = [
        "**📊 Statistiche Teach Assistant (R16)**",
        "",
        f"**Totale domande su campi:** {stats['total_questions']}",
        ""
    ]
    
    # Top campi problematici
    if stats["top_confused_fields"]:
        lines.append("**🔴 Campi più problematici:**")
        lines.append("")
        for i, f in enumerate(stats["top_confused_fields"][:5], 1):
            lines.append(f"{i}. `{f['doc_id']}` / **{f['field']}**: {f['count']} domande")
        lines.append("")
    
    # Per documento
    if stats["by_document"]:
        lines.append("**📁 Per documento:**")
        lines.append("")
        for doc_id, doc_stats in list(stats["by_document"].items())[:5]:
            lines.append(f"- `{doc_id}`: {doc_stats['total']} domande")
        lines.append("")
    
    if stats['total_questions'] == 0:
        lines.append("_Nessuna domanda su campi registrata finora._")
    
    await cl.Message(content="\n".join(lines)).send()


# ============================================================
# R19: SEGNALAZIONE LACUNE INTELLIGENTE
# ============================================================

_gap_detector = None
_gap_store = None


def get_gap_detector():
    """Lazy load gap detector"""
    global _gap_detector
    if _gap_detector is None:
        from src.analytics.gap_detector import GapDetector
        pipeline = get_pipeline()
        _gap_detector = GapDetector(
            glossary_resolver=pipeline.glossary,
            retrieval_score_threshold=0.4,
            gap_score_threshold=0.6
        )
    return _gap_detector


def get_gap_store():
    """Lazy load gap store"""
    global _gap_store
    if _gap_store is None:
        from src.analytics.gap_store import GapStore
        _gap_store = GapStore(persist_path="data/persist/gap_reports.json")
    return _gap_store


async def check_and_show_gap_detection(
    query: str,
    response,  # RAGResponse
    user
) -> bool:
    """
    R19: Verifica lacune e mostra UI se rilevate.
    
    Args:
        query: Query originale
        response: RAGResponse dal pipeline
        user: Utente corrente
        
    Returns:
        True se lacuna rilevata e mostrata
    """
    detector = get_gap_detector()
    
    gap = detector.detect_gap(
        query=query,
        response=response.answer,
        sources=response.sources
    )
    
    if not gap.is_gap:
        return False
    
    # Costruisci messaggio
    term = gap.missing_term or "il termine cercato"
    
    lines = [
        f"📍 **Possibile lacuna rilevata**",
        "",
        f"Non ho trovato una definizione chiara per **{term}**.",
    ]
    
    if gap.found_in_docs:
        lines.append("")
        lines.append("Ho trovato il termine in questi documenti ma senza definizione:")
        for doc in gap.found_in_docs[:3]:
            lines.append(f"- `{doc}`")
    
    if gap.snippets:
        lines.append("")
        lines.append("**Contesto:**")
        for snippet in gap.snippets[:2]:
            lines.append(f"_{snippet[:100]}..._")
    
    lines.extend([
        "",
        "❓ **Vuoi segnalare questa lacuna all'Admin?**",
        "_Se segnalata, potrà aggiungere il termine al glossario._"
    ])
    
    # Crea azioni
    actions = [
        cl.Action(
            name="report_gap",
            payload={
                "term": gap.missing_term,
                "query": query,
                "found_in": gap.found_in_docs,
                "snippets": gap.snippets
            },
            label="✅ Sì, segnala"
        ),
        cl.Action(
            name="dismiss_gap",
            payload={},
            label="❌ No, non serve"
        )
    ]
    
    await cl.Message(
        content="\n".join(lines),
        actions=actions,
        author="Sistema"
    ).send()
    
    return True


@cl.action_callback("report_gap")
async def on_report_gap(action: cl.Action):
    """R19: Callback segnalazione lacuna"""
    user = cl.user_session.get("app_user")
    
    term = action.payload.get("term", "")
    query = action.payload.get("query", "")
    found_in = action.payload.get("found_in", [])
    snippets = action.payload.get("snippets", [])
    
    if not term:
        await cl.Message(
            content="⚠️ Impossibile segnalare: termine non identificato.",
            author="Sistema"
        ).send()
        return
    
    store = get_gap_store()
    report = store.report_gap(
        term=term,
        query=query,
        found_in_docs=found_in,
        user_id=user.id,
        snippets=snippets
    )
    
    if report.report_count > 1:
        msg = (
            f"✅ Grazie! La lacuna per **{term}** è già stata segnalata da "
            f"**{report.report_count} utenti**.\n\n"
            f"L'Admin la vedrà con priorità alta."
        )
    else:
        msg = f"✅ Lacuna segnalata! L'Admin potrà aggiungere **{term}** al glossario."
    
    await cl.Message(content=msg, author="Sistema").send()


@cl.action_callback("dismiss_gap")
async def on_dismiss_gap(action: cl.Action):
    """R19: Utente rifiuta segnalazione"""
    await cl.Message(
        content="👌 OK, non segnalo la lacuna.",
        author="Sistema"
    ).send()


async def handle_gaps_command():
    """R19: Mostra lacune segnalate (Admin/Engineer)"""
    store = get_gap_store()
    stats = store.get_stats()
    pending = store.get_pending(limit=10)
    
    lines = [
        "**📍 Lacune Segnalate (R19)**",
        "",
        f"📊 **Statistiche:**",
        f"- Totale: {stats['total']}",
        f"- Pending: {stats['pending']}",
        f"- Aggiunte: {stats['added']}",
        f"- Rifiutate: {stats['rejected']}",
        ""
    ]
    
    if pending:
        lines.append("**🔴 Da gestire (ordinate per priorità):**")
        lines.append("")
        for r in pending:
            lines.append(f"- **{r.term}** ({r.report_count} segnalazioni)")
            if r.found_in_docs:
                docs_str = ", ".join(r.found_in_docs[:3])
                lines.append(f"  📄 In: `{docs_str}`")
            lines.append(f"  📝 Query: _{r.query_original[:50]}..._")
            lines.append("")
    else:
        lines.append("_Nessuna lacuna pending._")
    
    lines.append("---")
    lines.append("💡 *Usa `/glossario add TERMINE = Definizione` per aggiungere al glossario*")
    
    await cl.Message(content="\n".join(lines)).send()


# ============================================================
# R05: ESTRAZIONE AUTOMATICA ACRONIMI
# ============================================================

_acronym_extractor = None


def get_acronym_extractor():
    """Lazy load acronym extractor"""
    global _acronym_extractor
    if _acronym_extractor is None:
        from src.analytics.acronym_extractor import AcronymExtractor
        pipeline = get_pipeline()
        _acronym_extractor = AcronymExtractor(
            glossary_resolver=pipeline.glossary,
            proposals_path="config/acronym_proposals.json",
            min_confidence=0.6
        )
    return _acronym_extractor


async def handle_acronyms_command(content: str, user):
    """
    R05: Gestione proposte acronimi (Admin/Engineer)
    
    Comandi:
    - /acronyms             → Lista proposte pending
    - /acronyms approve ABC → Approva e aggiunge al glossario
    - /acronyms reject ABC motivo → Rifiuta con motivo
    - /acronyms stats       → Statistiche
    """
    extractor = get_acronym_extractor()
    parts = content.split(maxsplit=3)
    
    # /acronyms (senza parametri) → lista pending
    if len(parts) == 1:
        await show_acronym_proposals(extractor)
        return
    
    subcommand = parts[1].lower()
    
    if subcommand == "stats":
        # /acronyms stats
        await show_acronym_stats(extractor)
    
    elif subcommand == "approve" and len(parts) >= 3:
        # /acronyms approve ABC
        acronym = parts[2].upper()
        await approve_acronym_proposal(extractor, acronym, user)
    
    elif subcommand == "reject" and len(parts) >= 3:
        # /acronyms reject ABC [motivo]
        acronym = parts[2].upper()
        reason = parts[3] if len(parts) > 3 else "Rifiutato da Admin"
        await reject_acronym_proposal(extractor, acronym, reason)
    
    else:
        # Help
        await cl.Message(content="""**📝 Comandi /acronyms (R05)**

- `/acronyms` - Lista proposte pending
- `/acronyms approve ABC` - Approva e aggiunge al glossario
- `/acronyms reject ABC motivo` - Rifiuta con motivo
- `/acronyms stats` - Statistiche estrazione
""").send()


async def show_acronym_proposals(extractor):
    """Mostra proposte pending"""
    pending = extractor.get_pending(limit=15)
    stats = extractor.get_stats()
    
    lines = [
        "**📝 Acronimi Proposti (R05)**",
        "",
        f"📊 **Statistiche:**",
        f"- Totale: {stats['total']}",
        f"- Pending: {stats['pending']}",
        f"- Approvati: {stats['approved']}",
        f"- Rifiutati: {stats['rejected']}",
        ""
    ]
    
    if pending:
        lines.append("**🔴 Da gestire (ordinati per confidence):**")
        lines.append("")
        
        for i, p in enumerate(pending, 1):
            lines.append(f"**{i}. {p.acronym}** = {p.expansion}")
            lines.append(f"   📊 Confidence: {p.confidence:.0%}")
            
            if p.found_in_docs:
                docs = ", ".join(p.found_in_docs[:3])
                lines.append(f"   📄 Trovato in: `{docs}`")
            
            if p.snippets:
                snippet = p.snippets[0][:80] + "..." if len(p.snippets[0]) > 80 else p.snippets[0]
                lines.append(f"   📝 _{snippet}_")
            
            lines.append("")
    else:
        lines.append("_Nessuna proposta pending._")
    
    lines.append("---")
    lines.append("💡 **Comandi:**")
    lines.append("- `/acronyms approve ABC` - Approva")
    lines.append("- `/acronyms reject ABC motivo` - Rifiuta")
    
    await cl.Message(content="\n".join(lines)).send()


async def show_acronym_stats(extractor):
    """Mostra statistiche estrazione"""
    stats = extractor.get_stats()
    
    lines = [
        "**📊 Statistiche Estrazione Acronimi (R05)**",
        "",
        f"- **Totale estratti:** {stats['total']}",
        f"- **Pending:** {stats['pending']}",
        f"- **Approvati:** {stats['approved']}",
        f"- **Rifiutati:** {stats['rejected']}",
        "",
        "**Per pattern:**"
    ]
    
    for ptype, count in stats.get("by_pattern", {}).items():
        lines.append(f"- {ptype}: {count}")
    
    if stats.get("top_confidence"):
        lines.append("")
        lines.append("**Top 5 confidence:**")
        for item in stats["top_confidence"]:
            lines.append(f"- {item['acronym']}: {item['confidence']:.0%}")
    
    await cl.Message(content="\n".join(lines)).send()


async def approve_acronym_proposal(extractor, acronym: str, user):
    """Approva proposta e aggiunge al glossario"""
    proposal = extractor.get_by_acronym(acronym)
    
    if not proposal:
        await cl.Message(content=f"❌ Proposta non trovata: **{acronym}**").send()
        return
    
    if proposal.status != "pending":
        await cl.Message(content=f"⚠️ Proposta già processata: **{acronym}** ({proposal.status})").send()
        return
    
    # Approva proposta
    extractor.approve(acronym, f"Approvato da {user.id}")
    
    # Aggiungi al glossario
    pipeline = get_pipeline()
    if pipeline.glossary:
        success = pipeline.glossary.add_acronym(
            acronym=acronym,
            full=proposal.expansion,
            description=f"Estratto automaticamente (R05) da {', '.join(proposal.found_in_docs[:2])}",
            save=True
        )
        
        if success:
            await cl.Message(
                content=f"✅ **{acronym}** = {proposal.expansion}\n\n"
                f"Aggiunto al glossario! ({proposal.confidence:.0%} confidence)"
            ).send()
        else:
            await cl.Message(content=f"⚠️ Proposta approvata ma errore salvataggio glossario").send()
    else:
        await cl.Message(content=f"✅ Proposta approvata (glossario non disponibile)").send()


async def reject_acronym_proposal(extractor, acronym: str, reason: str):
    """Rifiuta proposta con motivo"""
    proposal = extractor.get_by_acronym(acronym)
    
    if not proposal:
        await cl.Message(content=f"❌ Proposta non trovata: **{acronym}**").send()
        return
    
    if proposal.status != "pending":
        await cl.Message(content=f"⚠️ Proposta già processata: **{acronym}** ({proposal.status})").send()
        return
    
    # Rifiuta
    extractor.reject(acronym, reason)
    
    await cl.Message(content=f"🚫 **{acronym}** rifiutato.\n📝 Motivo: _{reason}_").send()


# ============================================================
# R28: CRONOLOGIA CONVERSAZIONI
# ============================================================

async def handle_clear_history():
    """
    Pulisce la cronologia della sessione corrente.
    Equivalente a /api/clear_history in test_ui.py
    """
    # Pulisci history sessione Chainlit
    cl.user_session.set("history", [])
    
    # Pulisci anche teach context se presente
    cl.user_session.set("teach_context", None)
    cl.user_session.set("pending_disambiguation", None)
    
    await cl.Message(
        content="✅ **Cronologia pulita!**\n\nLa cronologia della conversazione è stata azzerata.",
        author="Sistema"
    ).send()


async def handle_history_command(content: str, user: User):
    """
    R28: Mostra cronologia chat dell'utente.
    
    Usage:
        /history         - Ultime 10 conversazioni
        /history 20      - Ultime 20 conversazioni
        /history today   - Solo oggi
        /history all     - Tutte le sessioni (solo Admin)
    """
    conv_logger = get_conv_logger()
    parts = content.split()
    
    # Parse argomenti
    limit = 10
    days = 30
    show_all_users = False
    
    if len(parts) > 1:
        arg = parts[1].lower()
        if arg.isdigit():
            limit = int(arg)
        elif arg == "today":
            days = 1
        elif arg == "all" and user.can_read_all_users():
            show_all_users = True
            limit = 50
    
    # Ottieni sessioni
    if show_all_users:
        sessions = conv_logger.get_all_sessions(days=days, limit=limit)
        title = f"📜 **Ultime {len(sessions)} sessioni (tutti gli utenti)**"
    else:
        sessions = conv_logger.get_user_sessions(
            user_id=user.id,
            days=days,
            limit=limit
        )
        title = f"📜 **Le tue ultime {len(sessions)} sessioni:**"
    
    if not sessions:
        await cl.Message(content="📭 Nessuna conversazione trovata.").send()
        return
    
    # Formatta output
    lines = [title, ""]
    
    for session in sessions:
        try:
            start = datetime.fromisoformat(session.started_at)
            duration_min = session.duration_seconds() / 60
            
            # Header sessione
            if show_all_users:
                lines.append(f"👤 **{session.user_id}** - {start.strftime('%d/%m/%Y %H:%M')} "
                           f"({duration_min:.0f} min, {session.total_interactions} msg)")
            else:
                lines.append(f"🗓️ **{start.strftime('%d/%m/%Y %H:%M')}** "
                           f"({duration_min:.0f} min, {session.total_interactions} messaggi)")
            
            # Feedback
            if session.positive_feedback_count or session.negative_feedback_count:
                lines.append(f"   👍 {session.positive_feedback_count} / 👎 {session.negative_feedback_count}")
            
            # Mostra prime 3 query
            for i, interaction in enumerate(session.interactions[:3]):
                query_preview = interaction.query_original[:50]
                if len(interaction.query_original) > 50:
                    query_preview += "..."
                
                # Indicatori
                indicators = []
                if interaction.feedback == "positive":
                    indicators.append("👍")
                elif interaction.feedback == "negative":
                    indicators.append("👎")
                if interaction.gap_detected:
                    indicators.append("⚠️")
                
                indicator_str = " ".join(indicators)
                lines.append(f"   • {query_preview} {indicator_str}")
            
            if session.total_interactions > 3:
                lines.append(f"   _... e altri {session.total_interactions - 3} messaggi_")
            
            lines.append("")
        except Exception as e:
            logger.warning(f"[R28] Errore formattazione sessione: {e}")
            continue
    
    # Statistiche giornaliere
    stats = conv_logger.get_daily_stats()
    if stats["total_sessions"] > 0:
        lines.append("---")
        lines.append(f"📊 **Oggi:** {stats['total_sessions']} sessioni, "
                    f"{stats['total_interactions']} messaggi, "
                    f"{stats['avg_latency_ms']}ms latenza media")
    
    await cl.Message(content="\n".join(lines)).send()


# ============================================================
# APPRENDIMENTO SEMI-AUTOMATICO (R13)
# ============================================================

async def show_learning_confirmation(learning: LearningResult, user: User, namespace: str):
    """
    Mostra popup di conferma quando il sistema rileva un pattern di apprendimento.
    L'utente può scegliere se registrare o ignorare.
    """
    # Prepara dati da passare alle actions
    learning_data = json.dumps({
        "term": learning.term,
        "meaning": learning.meaning,
        "type": learning.learning_type.value,
        "confidence": learning.confidence,
        "username": user.username,
        "namespace": namespace
    })
    
    actions = [
        cl.Action(
            name="confirm_learning",
            payload={"data": learning_data},
            label="✅ Si, registra"
        ),
        cl.Action(
            name="reject_learning",
            payload={"data": learning_data},
            label="❌ No, ignora"
        )
    ]
    
    type_emoji = {
        "definition": "📝",
        "correction": "⚠️",
        "clarification": "💡"
    }.get(learning.learning_type.value, "📝")
    
    await cl.Message(
        content=f"{type_emoji} Ho capito che **{learning.term}** = {learning.meaning}\n\n"
                f"Vuoi che lo registri? *(confidenza: {learning.confidence:.0%})*",
        actions=actions
    ).send()


@cl.action_callback("confirm_learning")
async def on_confirm_learning(action: cl.Action):
    """Callback quando l'utente conferma l'apprendimento"""
    try:
        data = json.loads(action.payload.get("data", "{}"))
        term = data["term"]
        meaning = data["meaning"]
        learning_type = data["type"]
        username = data["username"]
        namespace = data["namespace"]
        
        # Salva nel namespace pending_global per approvazione Admin
        store = get_memory_store()
        from src.memory.store import MemoryType
        
        # Crea memoria in pending_global
        memory_content = f"{term} = {meaning}"
        
        from src.memory.updater import MemoryUpdater
        updater = MemoryUpdater(store, config_path="config/config.yaml")
        
        # I metadati vengono passati direttamente al contenuto per semplicità
        enriched_content = f"{term} = {meaning} | proposto_da:{username} | term:{term} | meaning:{meaning}"
        
        memory = updater.add_from_explicit_feedback(
            enriched_content,
            "fact",
            namespace=("pending_global",)
        )
        
        # Salva anche nel namespace personale dell'utente (per lui funziona subito)
        personal_memory = updater.add_from_explicit_feedback(
            memory_content,
            "fact",
            namespace=(namespace,) if namespace else None
        )
        
        # Aggiorna glossary custom per questo utente
        pipeline = get_pipeline()
        pipeline.glossary.add_custom_term(term, meaning)
        
        await cl.Message(
            content=f"✅ **Registrato!**\n\n"
                    f"- **{term}** = {meaning}\n"
                    f"- Per te: attivo subito\n"
                    f"- Per tutti: in attesa di approvazione Admin\n\n"
                    f"*Un Admin puo' approvare con `/approve`*",
            author="Sistema"
        ).send()
        
    except Exception as e:
        logger.error(f"Errore conferma apprendimento: {e}")
        await cl.Message(content=f"Errore: {str(e)}", author="Sistema").send()


@cl.action_callback("reject_learning")
async def on_reject_learning(action: cl.Action):
    """Callback quando l'utente rifiuta l'apprendimento"""
    try:
        data = json.loads(action.payload.get("data", "{}"))
        term = data["term"]
        
        await cl.Message(
            content=f"👌 OK, non registro **{term}**.",
            author="Sistema"
        ).send()
        
    except Exception as e:
        logger.error(f"Errore rifiuto apprendimento: {e}")


# ============================================================
# R15: SUGGERIMENTO TOOL PRATICI - Callback
# R16: ASSISTENZA COMPILAZIONE TOOL - Callbacks estesi
# ============================================================

def get_teach_assistant():
    """Lazy load teach assistant"""
    from src.integration.teach_assistant import get_teach_assistant as _get
    return _get()


def get_feedback_tracker():
    """Lazy load feedback tracker"""
    from src.integration.teach_assistant import get_feedback_tracker as _get
    return _get(get_memory_store())


@cl.action_callback("teach_tool")
async def on_teach_tool(action: cl.Action):
    """
    Callback quando l'utente clicca su un tool suggerito.
    R16: Aggiunge contesto sessione e azioni follow-up.
    """
    try:
        doc_id = action.payload.get("doc_id", "")
        tool_name = action.payload.get("name", doc_id)
        
        logger.info(f"[R16] Teach tool: {doc_id}")
        
        # Esegui teach
        pipeline = get_pipeline()
        response = pipeline.teach(doc_id)
        
        # R16: Salva contesto teach in sessione
        from src.integration.teach_assistant import TeachContext
        
        teach_context = TeachContext(
            doc_id=doc_id,
            doc_name=tool_name,
            started_at=datetime.now()
        )
        cl.user_session.set("teach_context", teach_context)
        
        # R16: Formatta risposta con azioni
        assistant = get_teach_assistant()
        formatted, actions_data = assistant.format_teach_response_with_actions(
            doc_id, tool_name, response.answer
        )
        
        # Converti azioni in cl.Action
        actions = [
            cl.Action(
                name=a["name"],
                payload=a["payload"],
                label=a["label"]
            )
            for a in actions_data
        ]
        
        await cl.Message(
            content=formatted,
            actions=actions,
            metadata={"type": "teach", "doc_ref": doc_id}
        ).send()
        
    except Exception as e:
        logger.error(f"[R16] Errore teach tool: {e}")
        await cl.Message(
            content=f"Errore nel recupero delle istruzioni per `{action.payload.get('doc_id', '?')}`: {str(e)}",
            author="Sistema"
        ).send()


@cl.action_callback("teach_fields_list")
async def on_teach_fields_list(action: cl.Action):
    """R16: Mostra lista campi del tool"""
    doc_id = action.payload.get("doc_id", "")
    doc_name = action.payload.get("doc_name", doc_id)
    
    logger.info(f"[R16] Lista campi: {doc_id}")
    
    assistant = get_teach_assistant()
    fields_text = assistant.format_fields_list(doc_id)
    
    await cl.Message(content=fields_text).send()


@cl.action_callback("teach_errors")
async def on_teach_errors(action: cl.Action):
    """R16: Mostra errori comuni del tool"""
    doc_id = action.payload.get("doc_id", "")
    doc_name = action.payload.get("doc_name", doc_id)
    
    logger.info(f"[R16] Errori comuni: {doc_id}")
    
    # Query RAG per errori comuni
    pipeline = get_pipeline()
    response = pipeline.query(
        f"Errori comuni da evitare nella compilazione del documento {doc_id} {doc_name}"
    )
    
    await cl.Message(
        content=f"**⚠️ Errori comuni in {doc_name}** (`{doc_id}`)\n\n---\n\n{response.answer}"
    ).send()


@cl.action_callback("teach_example")
async def on_teach_example(action: cl.Action):
    """R16: Mostra esempio compilazione"""
    doc_id = action.payload.get("doc_id", "")
    doc_name = action.payload.get("doc_name", doc_id)
    
    logger.info(f"[R16] Esempio: {doc_id}")
    
    # Query RAG per esempio
    pipeline = get_pipeline()
    response = pipeline.query(
        f"Esempio pratico di compilazione del documento {doc_id} {doc_name}"
    )
    
    await cl.Message(
        content=f"**📄 Esempio compilazione {doc_name}** (`{doc_id}`)\n\n---\n\n{response.answer}"
    ).send()


async def check_teach_followup(content: str, user) -> bool:
    """
    R16: Verifica se il messaggio è un follow-up su teach.
    Se sì, gestisce e ritorna True.
    """
    # Verifica contesto teach attivo
    teach_context = cl.user_session.get("teach_context")
    
    if not teach_context or not teach_context.is_active():
        return False
    
    # Rileva domanda su campo
    assistant = get_teach_assistant()
    is_field_question, field_name = assistant.detect_field_question(content)
    
    if not is_field_question:
        return False
    
    doc_id = teach_context.doc_id
    doc_name = teach_context.doc_name
    
    logger.info(f"[R16] Follow-up su campo '{field_name}' per {doc_id}")
    
    # R16: Traccia feedback
    tracker = get_feedback_tracker()
    tracker.track_field_question(doc_id, field_name, user.id)
    
    # Cerca info campo dal mapping
    field_info = assistant.get_field_info(doc_id, field_name)
    
    if field_info:
        # Info dal mapping
        response_text = field_info.format_explanation()
        
        # Aggiorna campi chiesti in sessione
        teach_context.add_field_asked(field_name)
        cl.user_session.set("teach_context", teach_context)
    else:
        # Fallback: query RAG sul campo
        pipeline = get_pipeline()
        response = pipeline.query(
            f"Nel documento {doc_id} {doc_name}, spiega il campo: {field_name}"
        )
        response_text = f"**📋 Campo: {field_name}**\n\n{response.answer}"
    
    # Notifica Admin se soglia raggiunta
    if tracker.should_notify_admin(doc_id, field_name):
        count = tracker.get_confusion_count(doc_id, field_name)
        logger.warning(f"[R16] ⚠️ Campo problematico: {doc_id}/{field_name} ({count} domande)")
    
    await cl.Message(
        content=response_text,
        metadata={"type": "teach_field", "doc_ref": doc_id, "field": field_name}
    ).send()
    
    return True


# ============================================================
# COMANDI ADMIN PER APPROVAZIONE (R02-R03)
# ============================================================

async def handle_pending_list(user: User):
    """Gestisce comando /pending - lista proposte in attesa"""
    store = get_memory_store()
    
    # Ottieni memorie dal namespace pending_global
    pending = store.get_all(namespace=("pending_global",))
    
    if not pending:
        await cl.Message(content="📋 Nessuna proposta in attesa di approvazione.").send()
        return
    
    lines = [f"📋 **Proposte in attesa** ({len(pending)} totali)\n"]
    
    for i, mem in enumerate(pending[:20], 1):
        # Parsa il contenuto arricchito (formato: "term = meaning | proposto_da:xxx | term:xxx | meaning:xxx")
        content_parts = mem.content.split(" | ")
        main_def = content_parts[0] if content_parts else mem.content
        
        # Estrai metadati dal contenuto
        proposed_by = "sconosciuto"
        term = ""
        meaning = main_def
        
        for part in content_parts[1:]:
            if part.startswith("proposto_da:"):
                proposed_by = part.replace("proposto_da:", "")
            elif part.startswith("term:"):
                term = part.replace("term:", "")
            elif part.startswith("meaning:"):
                meaning = part.replace("meaning:", "")
        
        # Se term è vuoto, estrai dalla definizione principale
        if not term and "=" in main_def:
            parts = main_def.split("=", 1)
            term = parts[0].strip()
            meaning = parts[1].strip() if len(parts) > 1 else meaning
        
        lines.append(f"{i}. **{term}** = {meaning}")
        lines.append(f"   └ Proposto da `{proposed_by}` - ID: `{mem.id[:8]}`")
    
    if len(pending) > 20:
        lines.append(f"\n... e altre {len(pending) - 20}")
    
    lines.append("\n\n**Comandi:**")
    lines.append("- `/approve <id>` - Approva e aggiungi al glossario")
    lines.append("- `/reject <id> [motivo]` - Rifiuta proposta")
    
    await cl.Message(content="\n".join(lines)).send()


async def handle_approve(content: str, user: User):
    """Gestisce comando /approve - approva proposta"""
    match = re.match(r'/approve\s+(\S+)', content, re.IGNORECASE)
    
    if not match:
        await cl.Message(content="Uso: `/approve <id>`\nEsempio: `/approve abc12345`").send()
        return
    
    mem_id_prefix = match.group(1).lower()
    store = get_memory_store()
    
    # Cerca memoria in pending_global che inizia con l'ID fornito
    pending = store.get_all(namespace=("pending_global",))
    target = None
    
    for mem in pending:
        if mem.id.lower().startswith(mem_id_prefix):
            target = mem
            break
    
    if not target:
        await cl.Message(content=f"❌ Proposta `{mem_id_prefix}` non trovata.").send()
        return
    
    try:
        # Parsa il contenuto arricchito
        content_parts = target.content.split(" | ")
        main_def = content_parts[0] if content_parts else target.content
        
        proposed_by = "sconosciuto"
        term = ""
        meaning = ""
        
        for part in content_parts[1:]:
            if part.startswith("proposto_da:"):
                proposed_by = part.replace("proposto_da:", "")
            elif part.startswith("term:"):
                term = part.replace("term:", "")
            elif part.startswith("meaning:"):
                meaning = part.replace("meaning:", "")
        
        # Se term/meaning vuoti, estrai dalla definizione principale
        if not term and "=" in main_def:
            parts = main_def.split("=", 1)
            term = parts[0].strip()
            meaning = parts[1].strip() if len(parts) > 1 else meaning
        
        if term and meaning:
            # Aggiungi al glossario centrale
            pipeline = get_pipeline()
            success = pipeline.glossary.add_acronym(
                acronym=term,
                full=meaning,
                description=f"Proposto da {proposed_by}, approvato da {user.username}",
                save=True
            )
            
            if success:
                # Rimuovi da pending_global
                store.delete(target.id, namespace=("pending_global",))
                
                await cl.Message(
                    content=f"✅ **Approvato!**\n\n"
                            f"**{term}** = {meaning}\n\n"
                            f"Aggiunto al glossario centrale e salvato su file."
                ).send()
            else:
                await cl.Message(content=f"⚠️ Errore aggiunta al glossario.").send()
        else:
            await cl.Message(content=f"⚠️ Dati mancanti nella proposta.").send()
            
    except Exception as e:
        logger.error(f"Errore approvazione: {e}")
        await cl.Message(content=f"Errore: {str(e)}").send()


async def handle_reject(content: str, user: User):
    """Gestisce comando /reject - rifiuta proposta"""
    match = re.match(r'/reject\s+(\S+)(?:\s+(.+))?', content, re.IGNORECASE)
    
    if not match:
        await cl.Message(content="Uso: `/reject <id> [motivo]`\nEsempio: `/reject abc12345 Non corretto`").send()
        return
    
    mem_id_prefix = match.group(1).lower()
    reason = match.group(2) or "Nessun motivo specificato"
    
    store = get_memory_store()
    
    # Cerca memoria in pending_global
    pending = store.get_all(namespace=("pending_global",))
    target = None
    
    for mem in pending:
        if mem.id.lower().startswith(mem_id_prefix):
            target = mem
            break
    
    if not target:
        await cl.Message(content=f"❌ Proposta `{mem_id_prefix}` non trovata.").send()
        return
    
    try:
        # Parsa il contenuto arricchito
        content_parts = target.content.split(" | ")
        main_def = content_parts[0] if content_parts else target.content
        
        proposed_by = "sconosciuto"
        term = ""
        
        for part in content_parts[1:]:
            if part.startswith("proposto_da:"):
                proposed_by = part.replace("proposto_da:", "")
            elif part.startswith("term:"):
                term = part.replace("term:", "")
        
        # Se term vuoto, estrai dalla definizione principale
        if not term and "=" in main_def:
            term = main_def.split("=")[0].strip()
        
        # Rimuovi da pending_global
        store.delete(target.id, namespace=("pending_global",))
        
        await cl.Message(
            content=f"❌ **Rifiutato**\n\n"
                    f"**{term}** proposto da `{proposed_by}`\n"
                    f"Motivo: {reason}\n\n"
                    f"*La memoria rimane nel namespace personale dell'utente.*"
        ).send()
        
    except Exception as e:
        logger.error(f"Errore rifiuto: {e}")
        await cl.Message(content=f"Errore: {str(e)}").send()


# ═══════════════════════════════════════════════════════════════════════════
# R06: DISAMBIGUAZIONE ACRONIMI
# ═══════════════════════════════════════════════════════════════════════════

async def check_disambiguation(
    query: str,
    user_id: str
) -> Optional[str]:
    """
    R06: Verifica se la query contiene acronimi ambigui che richiedono
    chiarimento dall'utente.
    
    Se l'utente ha già una preferenza salvata per l'acronimo, la usa.
    Altrimenti, mostra popup per chiedere all'utente quale significato intende.
    
    Args:
        query: Query dell'utente
        user_id: ID utente per preferenze salvate
        
    Returns:
        Query modificata con acronimi espansi, oppure None se serve input utente
    """
    disambiguator = get_disambiguator()
    
    # Rileva acronimi ambigui nella query (v2.0: detect_ambiguous_in_query)
    result = disambiguator.detect_ambiguous_in_query(query, user_id=user_id)
    
    if not result.ambiguous_matches:
        return query  # Nessun acronimo ambiguo
    
    if not result.needs_disambiguation:
        # Tutti gli acronimi risolti automaticamente dal contesto o preferenze
        logger.info(f"[R06] Acronimi risolti automaticamente: {[m.acronym for m in result.ambiguous_matches]}")
        return result.resolved_query
    
    # Serve input utente - mostra popup per il primo acronimo non certo
    first_unresolved = result.first_unresolved
    if first_unresolved:
        # Converti meanings (AcronymMeaning) in dizionari per compatibilità
        definitions = [
            {
                "context": m.context,
                "full": m.full,
                "description": m.description
            }
            for m in first_unresolved.meanings
        ]
        
        # Salva stato per quando l'utente risponde
        cl.user_session.set("pending_disambiguation", {
            "acronym": first_unresolved.acronym,
            "original_query": query,
            "definitions": definitions
        })
        
        # Mostra domanda disambiguazione
        await show_disambiguation_question(first_unresolved, user_id)
        return None  # Aspetta risposta utente
    
    return query


async def show_disambiguation_question(match, user_id: str):
    """
    R06 v2.0: Mostra domanda di disambiguazione con pulsanti per ogni opzione.
    Include suggerimenti da contesto e preferenza utente.
    
    Args:
        match: AmbiguousAcronymMatch con acronimo e meanings (AcronymMeaning objects)
        user_id: ID utente
    """
    acronym = match.acronym
    meanings = match.meanings  # Lista di AcronymMeaning
    disambiguation_result = match.disambiguation_result
    
    # Ottieni preferenza utente
    pref_store = get_preference_store()
    user_pref = pref_store.get_preference(user_id, acronym)
    
    # Costruisci messaggio con marker per contesto e preferenza
    lines = [
        f"🔤 **{acronym}** può significare:",
        ""
    ]
    
    actions = []
    for i, meaning in enumerate(meanings, 1):
        context = meaning.context
        full = meaning.full
        desc = meaning.description
        
        # Determina marker
        marker = ""
        if user_pref and user_pref.preferred_context == context:
            marker = " ⭐ _tua preferenza abituale_"
        elif disambiguation_result and disambiguation_result.chosen_context == context and disambiguation_result.context_used:
            marker = f" 📍 _probabile dal contesto: {disambiguation_result.context_used}_"
        
        # Aggiungi definizione al messaggio
        lines.append(f"**{i}. {full}**{marker}")
        if desc:
            desc_short = desc[:80] + "..." if len(desc) > 80 else desc
            lines.append(f"   _{desc_short}_")
        lines.append("")
        
        # Crea action button
        actions.append(
            cl.Action(
                name="disambiguate_choice",
                payload={
                    "acronym": acronym,
                    "context": context,
                    "full": full
                },
                label=f"{i}. {full}"
            )
        )
    
    # Aggiungi opzione "Non ricordare"
    actions.append(
        cl.Action(
            name="disambiguate_no_save",
            payload={
                "acronym": acronym,
                "meanings": [{"context": m.context, "full": m.full} for m in meanings]
            },
            label="🔄 Chiedimelo ogni volta"
        )
    )
    
    lines.append("❓ Quale intendi?")
    
    await cl.Message(
        content="\n".join(lines),
        actions=actions,
        author="Sistema"
    ).send()


@cl.action_callback("disambiguate_choice")
async def on_disambiguation_choice(action: cl.Action):
    """
    R06: Callback quando l'utente sceglie un significato.
    Salva la preferenza per sessioni future e riprende la query.
    """
    user: User = cl.user_session.get("app_user")
    namespace = cl.user_session.get("namespace", "global")
    
    if not user:
        return
    
    payload = action.payload
    acronym = payload.get("acronym", "")
    context = payload.get("context", "")
    full = payload.get("full", "")
    
    # Recupera stato disambiguazione
    pending = cl.user_session.get("pending_disambiguation")
    if not pending:
        await cl.Message(content="⚠️ Sessione scaduta, riprova la domanda.", author="Sistema").send()
        return
    
    original_query = pending.get("original_query", "")
    
    # Salva preferenza utente (persistente)
    store = get_preference_store()
    store.save_choice(user.id, acronym, context, full, session_only=False)
    
    logger.info(f"[R06] Preferenza salvata: {user.id}/{acronym} -> {context}")
    
    # Pulisci stato
    cl.user_session.set("pending_disambiguation", None)
    
    # Conferma scelta
    await cl.Message(
        content=f"✅ Capito! **{acronym}** = **{full}**\n\n_Ricorderò questa preferenza per le prossime volte._",
        author="Sistema"
    ).send()
    
    # Risolvi query e riprendi
    disambiguator = get_disambiguator()
    resolved_query = disambiguator.resolve_with_choice(
        original_query, acronym, context, user.id, remember=False  # già salvato sopra
    )
    
    await handle_query(resolved_query, user, namespace)


@cl.action_callback("disambiguate_no_save")
async def on_disambiguation_no_save(action: cl.Action):
    """
    R06 v2.0: Callback quando l'utente sceglie di non salvare preferenza.
    Mostra sotto-menu per scelta una tantum.
    """
    user: User = cl.user_session.get("app_user")
    
    if not user:
        return
    
    acronym = action.payload.get("acronym", "")
    meanings = action.payload.get("meanings", [])
    
    # Mostra sotto-menu per scelta senza salvataggio
    actions = []
    for i, meaning in enumerate(meanings, 1):
        context = meaning.get("context", f"opzione_{i}")
        full = meaning.get("full", "")
        
        actions.append(
            cl.Action(
                name="disambiguate_once",
                payload={
                    "acronym": acronym,
                    "context": context,
                    "full": full
                },
                label=f"{full}"
            )
        )
    
    await cl.Message(
        content=f"Quale significato di **{acronym}** intendi per questa domanda?",
        actions=actions,
        author="Sistema"
    ).send()


@cl.action_callback("disambiguate_once")
async def on_disambiguation_once(action: cl.Action):
    """
    R06: Scelta una tantum senza salvare preferenza.
    """
    user: User = cl.user_session.get("app_user")
    namespace = cl.user_session.get("namespace", "global")
    
    if not user:
        return
    
    acronym = action.payload.get("acronym", "")
    context = action.payload.get("context", "")
    full = action.payload.get("full", "")
    
    # Recupera stato
    pending = cl.user_session.get("pending_disambiguation")
    if not pending:
        await cl.Message(content="⚠️ Sessione scaduta, riprova la domanda.", author="Sistema").send()
        return
    
    original_query = pending.get("original_query", "")
    
    # Pulisci stato
    cl.user_session.set("pending_disambiguation", None)
    
    await cl.Message(
        content=f"👌 OK, uso **{acronym}** = **{full}** solo per questa domanda.",
        author="Sistema"
    ).send()
    
    # Risolvi query senza salvare preferenza
    disambiguator = get_disambiguator()
    resolved_query = disambiguator.resolve_with_choice(
        original_query, acronym, context, user.id, remember=False
    )
    
    await handle_query(resolved_query, user, namespace)


async def handle_query(query: str, user: User, namespace: str):
    """
    Gestisce query RAG con fonti intelligenti (R14).
    
    R14: Le fonti vengono mostrate SOLO se effettivamente citate nella risposta,
    e sono cliccabili con anteprima in sidebar.
    """
    try:
        logger.info(f"[handle_query] Inizio query: {query[:50]}...")
        
        # Invia messaggio di attesa per mantenere connessione WebSocket attiva
        thinking_msg = cl.Message(content="⏳ Elaborazione in corso...")
        await thinking_msg.send()
        
        pipeline = get_pipeline()
        
        # History per reformulation
        history = cl.user_session.get("history", [])
        reformulated = reformulate_query_with_history(query, history)
        
        if reformulated != query:
            logger.info(f"Query riformulata: '{query}' -> '{reformulated}'")
        
        # Esegui query RAG (glossary integrato nel pipeline)
        logger.info("[handle_query] Esecuzione pipeline.query...")
        
        # F11: Task per aggiornare messaggio con fasi RAG in tempo reale
        import asyncio
        import queue
        import functools
        
        keep_alive_task = None
        stop_keep_alive = asyncio.Event()
        status_queue = queue.Queue()  # Coda thread-safe per le fasi
        
        async def update_status_display():
            """Controlla coda fasi e aggiorna UI - gira nel loop asyncio principale"""
            last_msg = ""
            while not stop_keep_alive.is_set():
                try:
                    # Controlla coda ogni 100ms
                    await asyncio.sleep(0.1)
                    
                    # Processa tutti i messaggi in coda
                    while not status_queue.empty():
                        try:
                            msg = status_queue.get_nowait()
                            if msg != last_msg:
                                thinking_msg.content = msg
                                await thinking_msg.update()
                                last_msg = msg
                                logger.debug(f"[F11] UI aggiornata: {msg}")
                        except queue.Empty:
                            break
                except Exception as e:
                    logger.debug(f"[F11] Update error: {e}")
        
        # Avvia task per aggiornare UI
        keep_alive_task = asyncio.create_task(update_status_display())
        
        def status_callback(phase: str, message: str):
            """Callback thread-safe - mette messaggio in coda"""
            logger.info(f"[F11] {message}")
            status_queue.put(message)
        
        try:
            # Esegui pipeline in thread per non bloccare event loop
            # F11: Passa callback per aggiornamenti status
            response = await asyncio.get_event_loop().run_in_executor(
                None, 
                functools.partial(pipeline.query, reformulated, status_callback=status_callback)
            )
        finally:
            # Ferma task keep-alive
            stop_keep_alive.set()
            if keep_alive_task:
                keep_alive_task.cancel()
                try:
                    await keep_alive_task
                except asyncio.CancelledError:
                    pass
            
            # F11: Cleanup (niente da fare con approccio semplificato)
            pass
        
        logger.info(f"[handle_query] Risposta ricevuta: {len(response.answer)} chars, {len(response.sources)} sources")
        
        answer = response.answer
        
        # ═══════════════════════════════════════════════════════════════
        # POST-PROCESSING: Pulizia risposta LLM
        # ═══════════════════════════════════════════════════════════════
        
        # 1. Rimuovi sezione "Riferimenti:" generata dall'LLM (ridondante)
        answer = remove_llm_references_section(answer)
        logger.debug("[PP] Rimossa sezione Riferimenti LLM")
        
        # 2. Costruisci mapping doc_id -> title per sanitizzazione
        doc_id_to_title = {}
        valid_doc_ids = set()
        for source in response.sources:
            doc_id = source.doc_id.upper()
            title = source.metadata.get("title", "")
            valid_doc_ids.add(doc_id)
            valid_doc_ids.add(doc_id.replace("_", "-"))
            if title and title != doc_id:
                doc_id_to_title[doc_id] = title
                doc_id_to_title[doc_id.replace("_", "-")] = title
        
        # 3. Sanitizza citazioni invalide (rimuovi allucinazioni)
        answer = sanitize_invalid_citations(answer, valid_doc_ids, doc_id_to_title)
        logger.debug("[PP] Sanitizzate citazioni invalide")
        
        # 4. Sostituisci doc_id con titoli tra virgolette nel testo
        answer = replace_doc_ids_with_titles(answer, response.sources)
        logger.debug("[PP] Sostituiti doc_id con titoli")
        
        # ═══════════════════════════════════════════════════════════════
        # R14: FONTI INTELLIGENTI - Estrai e filtra citazioni
        # ═══════════════════════════════════════════════════════════════
        
        # 4. Estrai doc_id citati nel testo O titoli citati
        from src.integration.citation_extractor import extract_cited_docs
        cited_doc_ids = extract_cited_docs(answer)
        
        # 4b. Cerca anche titoli nel testo (nuova logica per LLM che usa titoli)
        cited_by_title = set()
        for source in response.sources:
            title = source.metadata.get("title", "")
            if title and title in answer:
                cited_by_title.add(source.doc_id)
        
        # Unisci citazioni per codice e per titolo
        all_cited = cited_doc_ids | cited_by_title
        logger.info(f"[R14] Citazioni: codici={cited_doc_ids}, titoli={cited_by_title}")
        
        # 5. Filtra sources: mantieni quelle citate (codice O titolo)
        if all_cited:
            cited_sources, missing = filter_cited_sources(answer, response.sources)
            # Aggiungi anche quelle citate per titolo
            cited_sources_ids = {s.doc_id for s in cited_sources}
            for source in response.sources:
                if source.doc_id in cited_by_title and source.doc_id not in cited_sources_ids:
                    cited_sources.append(source)
            logger.info(f"[R14] Sources filtrate: {len(cited_sources)} su {len(response.sources)}")
        else:
            # Nessuna citazione esplicita: includi le top-3 sources dal retrieval
            cited_sources = response.sources[:3] if response.sources else []
            missing = []
            logger.info(f"[R14] Nessuna citazione esplicita, incluse top-3: {len(cited_sources)}")
        
        # Nota: missing non dovrebbe più contenere allucinazioni dopo sanitizzazione
        if missing:
            logger.debug(f"[R14] Citazioni post-sanitizzazione non trovate: {missing}")
        
        # 6. Crea elementi cliccabili per sidebar
        elements = []
        if cited_sources:
            elements = create_source_elements(cited_sources)
            logger.info(f"[R14] Creati {len(elements)} elementi cliccabili")
        
        # 7. Formatta footer con fonti (solo titoli, niente percentuale)
        footer = format_sources_footer(cited_sources)
        answer += footer
        
        # ═══════════════════════════════════════════════════════════════
        # R15: SUGGERIMENTO TOOL PRATICI
        # NOTA: I suggerimenti MR sono ora INTEGRATI nel contesto LLM
        # tramite MRInjector (vedi agent_context.py), quindi l'LLM li cita
        # direttamente nella risposta. Il box separato è stato rimosso.
        # I bottoni /teach sono mantenuti per comodità utente.
        # ═══════════════════════════════════════════════════════════════
        
        tool_suggester = get_tool_suggester()
        suggested_tools = tool_suggester.suggest_tools(query, response.answer)
        
        tool_actions = []
        if suggested_tools:
            logger.info(f"[R15] {len(suggested_tools)} tool rilevati (integrati in risposta LLM): {[t.doc_id for t in suggested_tools]}")
            
            # RIMOSSO: Box separato - ora i moduli sono integrati nella risposta LLM
            # tool_section = tool_suggester.format_suggestions_for_ui(suggested_tools)
            # answer += tool_section
            
            # Crea action buttons per ogni tool (manteniamo per comodità)
            for tool in suggested_tools:
                tool_actions.append(
                    cl.Action(
                        name="teach_tool",
                        payload={"doc_id": tool.doc_id, "name": tool.name},
                        label=f"📝 Come compilo {tool.name}?"
                    )
                )
        
        # ═══════════════════════════════════════════════════════════════
        # F10: PULSANTI FEEDBACK 👍👎
        # Aggiungi pulsanti per valutare la risposta
        # ═══════════════════════════════════════════════════════════════
        feedback_actions = [
            cl.Action(
                name="feedback_positive",
                payload={"query": query[:200]},  # Limita lunghezza payload
                label="👍 Utile",
                tooltip="Questa risposta è stata utile"
            ),
            cl.Action(
                name="feedback_negative",
                payload={"query": query[:200]},
                label="👎 Non utile",
                tooltip="Questa risposta non è stata utile"
            )
        ]
        
        # Combina tool_actions + feedback_actions
        all_actions = tool_actions + feedback_actions
        
        # ═══════════════════════════════════════════════════════════════
        
        # 5. Aggiungi latency
        answer += f"\n\n⏱️ *{response.latency_ms:.0f}ms*"
        
        # Invia messaggio con elementi cliccabili e actions
        logger.info(f"[handle_query] Invio messaggio ({len(answer)} chars, {len(elements)} elements, {len(all_actions)} actions)...")
        
        msg = cl.Message(
            content=answer,
            elements=elements if elements else None,
            actions=all_actions if all_actions else None,
            metadata={
                "query": query,
                "sources": [s.doc_id for s in cited_sources],
                "suggested_tools": [t.doc_id for t in suggested_tools] if suggested_tools else [],
                "namespace": namespace
            }
        )
        # Rimuovi messaggio di attesa
        await thinking_msg.remove()
        
        await msg.send()
        
        logger.info("[handle_query] Messaggio inviato OK")
        
        # ═══════════════════════════════════════════════════════════════
        # R28: LOG CONVERSAZIONE COMPLETA
        # ═══════════════════════════════════════════════════════════════
        
        conv_session_id = cl.user_session.get("conv_session_id")
        interaction_id = None
        if conv_session_id:
            try:
                conv_logger = get_conv_logger()
                
                interaction = conv_logger.log_interaction(
                    session_id=conv_session_id,
                    query_original=query,
                    query_reformulated=reformulated if reformulated != query else None,
                    query_expanded=response.expanded_query if hasattr(response, 'expanded_query') else None,
                    response_text=response.answer,
                    sources_retrieved=len(response.sources) if hasattr(response, 'sources') else 0,
                    sources_cited=[s.doc_id for s in cited_sources],
                    sources_missing=missing if missing else [],
                    latency_total_ms=int(response.latency_ms) if hasattr(response, 'latency_ms') else 0,
                    status=InteractionStatus.SUCCESS.value,
                    tools_suggested=[t.doc_id for t in suggested_tools] if suggested_tools else []
                )
                
                if interaction:
                    interaction_id = interaction.id
                    # Aggiorna metadata messaggio per collegare feedback
                    msg.metadata["interaction_id"] = interaction_id
                    msg.metadata["conv_session_id"] = conv_session_id
                    await msg.update()
                    logger.debug(f"[R28] Logged interaction: {interaction_id}")
            except Exception as conv_error:
                logger.warning(f"[R28] Errore logging conversazione: {conv_error}")
        
        # ═══════════════════════════════════════════════════════════════
        # R19: VERIFICA LACUNE
        # ═══════════════════════════════════════════════════════════════
        
        gap_shown = False
        try:
            gap_shown = await check_and_show_gap_detection(query, response, user)
            if gap_shown:
                logger.info("[R19] Lacuna rilevata e mostrata all'utente")
                # R28: Aggiorna interazione con gap detected
                if conv_session_id and interaction_id:
                    conv_logger = get_conv_logger()
                    session = conv_logger.get_session(conv_session_id)
                    if session:
                        for i in session.interactions:
                            if i.id == interaction_id:
                                i.gap_detected = True
                                conv_logger._persist_session(session)
                                break
        except Exception as gap_error:
            logger.warning(f"[R19] Errore check lacune: {gap_error}")
        
        # ═══════════════════════════════════════════════════════════════
        
        # Aggiorna history
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": response.answer})
        cl.user_session.set("history", history[-10:])  # Mantieni ultimi 10
        
    except Exception as e:
        import traceback
        logger.error(f"Errore query: {e}\n{traceback.format_exc()}")
        await cl.Message(content=f"Errore: {str(e)}").send()


@cl.action_callback("feedback_positive")
async def on_feedback_positive(action: cl.Action):
    """Callback feedback positivo"""
    await process_feedback(action, is_positive=True)


@cl.action_callback("feedback_negative")
async def on_feedback_negative(action: cl.Action):
    """Callback feedback negativo"""
    await process_feedback(action, is_positive=False)


async def process_feedback(action: cl.Action, is_positive: bool):
    """Processa feedback e aggiorna Bayesian boost"""
    try:
        memory_store = get_memory_store()
        msg = action.message
        
        if msg and msg.metadata:
            query = msg.metadata.get("query", "")
            sources = msg.metadata.get("sources", [])
            namespace = msg.metadata.get("namespace", "global")
            
            # Registra feedback per ogni source
            record_response_feedback(
                memory_store,
                query=query,
                sources=sources,
                is_positive=is_positive,
                namespace=namespace
            )
            
            # R28: Aggiorna feedback nel conversation log
            conv_session_id = msg.metadata.get("conv_session_id")
            interaction_id = msg.metadata.get("interaction_id")
            
            if conv_session_id and interaction_id:
                try:
                    conv_logger = get_conv_logger()
                    conv_logger.add_feedback(
                        session_id=conv_session_id,
                        interaction_id=interaction_id,
                        feedback="positive" if is_positive else "negative"
                    )
                    logger.debug(f"[R28] Feedback logged: {interaction_id} = {'positive' if is_positive else 'negative'}")
                except Exception as conv_error:
                    logger.warning(f"[R28] Errore logging feedback: {conv_error}")
        
        emoji = "👍" if is_positive else "👎"
        feedback_type = "positivo" if is_positive else "negativo"
        
        await cl.Message(
            content=f"Grazie per il feedback {emoji}! Il sistema impara dalle tue valutazioni.",
            author="Sistema"
        ).send()
        
        # Rimuovi azioni per evitare doppi click
        action.message.actions = []
        await action.message.update()
        
    except Exception as e:
        logger.error(f"Errore feedback: {e}")


def record_response_feedback(
    store,
    query: str,
    sources: List[str],
    is_positive: bool,
    namespace: str
):
    """
    Registra feedback su risposta RAG.
    Aggiorna boost delle memorie correlate.
    """
    from src.memory.store import MemoryType
    
    # Cerca memorie correlate ai documenti fonte
    for source_id in sources:
        try:
            # Cerca per doc_id nel contenuto
            related = store.search(
                query=source_id,
                namespace=(namespace,) if namespace else None,
                limit=3
            )
            
            for mem in related:
                store.add_feedback(
                    mem_id=mem.id,
                    is_positive=is_positive,
                    context=f"Response feedback for: {query[:50]}",
                    namespace=(namespace,) if namespace else None
                )
                
        except Exception as e:
            logger.debug(f"Feedback skip per {source_id}: {e}")


async def handle_teach(content: str):
    """Gestisce comando /teach"""
    match = re.match(r'/teach\s+(\S+)', content, re.IGNORECASE)
    if not match:
        await cl.Message(content="Uso: `/teach <codice_documento>`\nEsempio: `/teach MR-10_01`").send()
        return
    
    doc_ref = match.group(1)
    
    try:
        pipeline = get_pipeline()
        response = pipeline.teach(doc_ref)
        await cl.Message(content=f"**Come compilare {doc_ref}:**\n\n{response.answer}").send()
    except Exception as e:
        await cl.Message(content=f"Errore: {str(e)}").send()


async def handle_memoria(content: str, user: User, namespace: str):
    """
    Gestisce comando /memoria.
    
    Usage:
        /memoria                              - Mostra stats memoria (come test_ui)
        /memoria stats                        - Mostra stats memoria
        /memoria <tipo> <contenuto>           - Aggiunge memoria
    """
    parts = content.strip().split(maxsplit=2)
    
    # /memoria senza argomenti o /memoria stats -> mostra stats
    if len(parts) == 1 or (len(parts) == 2 and parts[1].lower() == "stats"):
        try:
            store = get_memory_store()
            if not store:
                await cl.Message(content="⚠️ Memory store non disponibile.").send()
                return
            
            all_mems = store.get_all(namespace=(namespace,) if namespace else None)
            stats = store.get_stats()
            
            lines = [
                "**🧠 Memoria - Statistiche**",
                "",
                f"📊 **Totale memorie:** {stats.get('total_memories', len(all_mems))}",
                f"📈 **Boost medio:** {stats.get('average_boost', 1.0):.2f}x",
                ""
            ]
            
            # Per namespace
            by_ns = stats.get("by_namespace", {})
            if by_ns:
                lines.append("**Per namespace:**")
                for ns, count in list(by_ns.items())[:5]:
                    lines.append(f"- `{ns}`: {count} memorie")
                lines.append("")
            
            # Memorie recenti
            if all_mems:
                lines.append("**📝 Memorie recenti:**")
                for m in all_mems[:5]:
                    content_preview = m.content[:80] + "..." if len(m.content) > 80 else m.content
                    boost_str = f" (boost: {m.boost_factor:.2f}x)" if m.boost_factor != 1.0 else ""
                    lines.append(f"- _{content_preview}_{boost_str}")
            else:
                lines.append("_Nessuna memoria nel tuo namespace._")
            
            lines.extend([
                "",
                "---",
                "💡 **Comandi:**",
                "- `/memoria preference <testo>` - Salva preferenza",
                "- `/memoria fact <testo>` - Salva fatto",
                "- `/memoria correction <testo>` - Salva correzione"
            ])
            
            await cl.Message(content="\n".join(lines)).send()
            return
            
        except Exception as e:
            logger.error(f"Errore stats memoria: {e}")
            await cl.Message(content=f"Errore: {str(e)}").send()
            return
    
    # /memoria <tipo> <contenuto> -> aggiunge memoria
    match = re.match(
        r'/memoria\s+(preference|fact|correction)\s+(.+)',
        content,
        re.IGNORECASE
    )
    
    if not match:
        await cl.Message(
            content="Uso: `/memoria <tipo> <contenuto>`\n"
                    "Tipi: `preference`, `fact`, `correction`\n\n"
                    "Esempi:\n"
                    "- `/memoria preference Preferisco Quick Kaizen`\n"
                    "- `/memoria fact RI significa Richiesta di Investimento`\n\n"
                    "Oppure `/memoria` senza argomenti per vedere le statistiche."
        ).send()
        return
    
    mem_type = match.group(1).lower()
    mem_content = match.group(2).strip()
    
    try:
        from src.memory.updater import MemoryUpdater
        store = get_memory_store()
        updater = MemoryUpdater(store, config_path="config/config.yaml")
        
        # Usa namespace utente
        memory = updater.add_from_explicit_feedback(
            mem_content, 
            mem_type,
            namespace=(namespace,) if namespace else None
        )
        
        # Aggiorna glossario se fact su acronimi
        if mem_type == "fact":
            update_glossary_from_memory(mem_content)
        
        await cl.Message(
            content=f"✅ **Memoria aggiunta**\n\n"
                    f"- Tipo: `{mem_type}`\n"
                    f"- ID: `{memory.id}`\n"
                    f"- Namespace: `{namespace}`\n"
                    f"- Contenuto: {mem_content}"
        ).send()
        
    except Exception as e:
        await cl.Message(content=f"Errore: {str(e)}").send()


async def handle_status(user: User):
    """Gestisce comando /status"""
    import torch
    
    lines = ["**Status Sistema**\n"]
    
    # Ruolo utente
    role_emoji = {"admin": "👑", "engineer": "🔧", "user": "👤"}.get(user.role.value, "👤")
    lines.append(f"{role_emoji} **Utente:** {user.display_name} (`{user.role.value}`)")
    lines.append(f"📁 **Namespace:** `{user.get_namespace()}`\n")
    
    # GPU
    if torch.cuda.is_available():
        vram_used = torch.cuda.memory_allocated() / 1024 / 1024
        vram_total = torch.cuda.get_device_properties(0).total_memory / 1024 / 1024
        lines.append(f"🖥️ **GPU:** {torch.cuda.get_device_name(0)}")
        lines.append(f"   VRAM: {vram_used:.0f}/{vram_total:.0f} MB")
    else:
        lines.append("⚠️ GPU non disponibile")
    
    # Memory store
    try:
        store = get_memory_store()
        stats = store.get_stats()
        lines.append(f"\n🧠 **Memorie totali:** {stats['total_memories']}")
        lines.append(f"   Boost medio: {stats['average_boost']:.2f}x")
    except:
        lines.append("\n🧠 Memorie: N/A")
    
    # Glossary
    try:
        pipeline = get_pipeline()
        glossary = pipeline.glossary
        base = len(glossary.acronyms) if hasattr(glossary, 'acronyms') else 0
        custom = len(glossary.custom_terms) if hasattr(glossary, 'custom_terms') else 0
        lines.append(f"\n📚 **Glossario:** {base} base + {custom} custom")
    except:
        lines.append("\n📚 Glossario: N/A")
    
    # Pipeline
    try:
        _ = get_pipeline()
        lines.append(f"\n🔄 **Pipeline:** OK")
    except:
        lines.append(f"\n🔄 Pipeline: Non inizializzata")
    
    # Permessi
    lines.append(f"\n**Permessi:**")
    lines.append(f"- Lettura globali: {'✅' if user.can_read_global() else '❌'}")
    lines.append(f"- Scrittura globali: {'✅' if user.can_write_global() else '❌'}")
    lines.append(f"- Vede tutti utenti: {'✅' if user.can_read_all_users() else '❌'}")
    
    await cl.Message(content="\n".join(lines)).send()


async def handle_glossario(content: str):
    """Gestisce comando /glossario"""
    parts = content.split(maxsplit=2)
    
    try:
        pipeline = get_pipeline()
        glossary = pipeline.glossary
        
        if len(parts) == 1:
            # Solo /glossario -> statistiche
            total = len(glossary.acronyms) if hasattr(glossary, 'acronyms') else 0
            custom = len(glossary.custom_terms) if hasattr(glossary, 'custom_terms') else 0
            
            await cl.Message(
                content=f"**Glossario**\n\n"
                        f"- Acronimi base: {total}\n"
                        f"- Termini custom: {custom}\n\n"
                        f"Uso: `/glossario ABC` per cercare"
            ).send()
        
        elif parts[1].lower() == "add" and len(parts) > 2:
            # /glossario add ABC = Descrizione
            add_match = re.match(r'(\w{2,10})\s*[=:]\s*(.+)', parts[2])
            if add_match:
                acronym = add_match.group(1).upper()
                expansion = add_match.group(2).strip()
                glossary.add_custom_term(acronym, expansion)
                await cl.Message(content=f"✅ Aggiunto: **{acronym}** → {expansion}").send()
            else:
                await cl.Message(content="Formato: `/glossario add ABC = Descrizione`").send()
        
        else:
            # /glossario ABC -> cerca
            term = parts[1].upper()
            result = glossary.resolve_acronym(term)
            
            if result:
                full = result.get("full", term)
                desc = result.get("description", "Nessuna descrizione")
                await cl.Message(content=f"**{term}**: {full}\n\n_{desc}_").send()
            else:
                matches = glossary.fuzzy_match(term, threshold=0.5)
                if matches:
                    suggestions = "\n".join([f"- {m[0]}: {m[1]}" for m in matches[:5]])
                    await cl.Message(content=f"**{term}** non trovato. Intendevi:\n{suggestions}").send()
                else:
                    await cl.Message(content=f"**{term}** non trovato nel glossario.").send()
    
    except Exception as e:
        await cl.Message(content=f"Errore: {str(e)}").send()


async def handle_global_memory(content: str):
    """Gestisce comando /global (solo Admin)"""
    match = re.match(
        r'/global\s+add\s+(preference|fact|correction)\s+(.+)',
        content,
        re.IGNORECASE
    )
    
    if not match:
        await cl.Message(
            content="Uso: `/global add <tipo> <contenuto>`\n"
                    "Esempio: `/global add fact SGI significa Sistema Gestione Integrato`"
        ).send()
        return
    
    mem_type = match.group(1).lower()
    mem_content = match.group(2).strip()
    
    try:
        from src.memory.updater import MemoryUpdater
        store = get_memory_store()
        updater = MemoryUpdater(store, config_path="config/config.yaml")
        
        # Usa namespace globale
        memory = updater.add_from_explicit_feedback(
            mem_content,
            mem_type,
            namespace=("global",)
        )
        
        if mem_type == "fact":
            update_glossary_from_memory(mem_content)
        
        await cl.Message(
            content=f"✅ **Memoria GLOBALE aggiunta**\n\n"
                    f"- Tipo: `{mem_type}`\n"
                    f"- ID: `{memory.id}`\n"
                    f"- Contenuto: {mem_content}\n\n"
                    f"*Visibile a tutti gli utenti*"
        ).send()
        
    except Exception as e:
        await cl.Message(content=f"Errore: {str(e)}").send()


async def handle_view_memories(content: str, user: User):
    """Gestisce comando /memorie (Admin/Engineer)"""
    parts = content.split()
    
    store = get_memory_store()
    
    if len(parts) == 1:
        # /memorie -> lista namespace
        stats = store.get_stats()
        namespaces = stats.get("by_namespace", {})
        
        lines = ["**Namespace memorie:**\n"]
        for ns, count in namespaces.items():
            lines.append(f"- `{ns}`: {count} memorie")
        
        lines.append("\n\nUso: `/memorie <namespace>` per dettagli")
        await cl.Message(content="\n".join(lines)).send()
    
    else:
        # /memorie <namespace>
        target_ns = parts[1]
        memories = store.get_all(namespace=(target_ns,))
        
        if not memories:
            await cl.Message(content=f"Nessuna memoria in `{target_ns}`").send()
            return
        
        lines = [f"**Memorie in `{target_ns}`:** ({len(memories)} totali)\n"]
        for mem in memories[:10]:
            boost = f"{mem.boost_factor:.2f}x" if mem.boost_factor != 1.0 else ""
            lines.append(f"- **{mem.type.value}**: {mem.content[:50]}... {boost}")
        
        if len(memories) > 10:
            lines.append(f"\n... e altre {len(memories) - 10}")
        
        await cl.Message(content="\n".join(lines)).send()


def reformulate_query_with_history(query: str, history: List[Dict]) -> str:
    """
    Riformula query usando contesto conversazionale.
    Allineato con test_ui.py per consistenza.
    """
    if not history or not isinstance(query, str):
        return query
    
    query_lower = query.lower().strip()
    
    # Pattern follow-up (allineati con test_ui.py)
    followup_patterns = [
        (r"^(parlamene|parlami|dimmi|spiegami|continua)$", "expand_last"),
        (r"^e\s+(la|il|lo)?\s*(\w+)\?*$", "compare_with_last"),
        (r"^(quindi|allora)[\s,]*(la\s+)?differenza\??$", "compare_all"),  # Aggiunto da test_ui
    ]
    
    # Estrai termini discussi
    discussed_terms = []
    last_user_query = None
    
    for msg in history[-6:]:
        if msg.get("role") == "user":
            last_user_query = msg.get("content", "")
            terms = re.findall(r'\b([A-Z]{2,5})\b', last_user_query)
            discussed_terms.extend(terms)
    
    discussed_terms = list(dict.fromkeys(discussed_terms))
    
    # Applica pattern
    for pattern, action in followup_patterns:
        match = re.search(pattern, query_lower)
        if match:
            if action == "expand_last" and last_user_query:
                return f"Parlami di piu' su: {last_user_query}"
            elif action == "compare_with_last" and discussed_terms:
                new_term = match.group(2).upper() if match.lastindex >= 2 else ""
                return f"Cos'e' {new_term} e differenza con {discussed_terms[-1]}?"
            elif action == "compare_all" and len(discussed_terms) >= 2:
                # Allineato con test_ui.py - confronta ultimi 2 termini discussi
                return f"Qual e' la differenza tra {discussed_terms[-2]} e {discussed_terms[-1]}?"
    
    # Query corta con contesto
    if len(query) < 20 and discussed_terms:
        return f"{query} (contesto: {', '.join(discussed_terms[:3])})"
    
    return query


def update_glossary_from_memory(content: str):
    """Aggiorna glossario da memoria fact"""
    patterns = [
        r"(\w+)\s+(?:significa|vuol\s*dire|sta\s*per)\s+(.+)",
        r"(\w{2,6})\s*[=:]\s*(.+)",
    ]
    
    for pattern in patterns:
        match = re.match(pattern, content, re.IGNORECASE)
        if match:
            acronym = match.group(1).strip().upper()
            expansion = match.group(2).strip()
            
            if 2 <= len(acronym) <= 6:
                try:
                    pipeline = get_pipeline()
                    pipeline.glossary.add_custom_term(acronym, expansion)
                    logger.info(f"Glossario aggiornato: {acronym} -> {expansion}")
                except Exception as e:
                    logger.warning(f"Impossibile aggiornare glossario: {e}")
            break


# ═══════════════════════════════════════════════════════════════
# R28: CHIUSURA SESSIONE
# ═══════════════════════════════════════════════════════════════

@cl.on_chat_end
async def on_chat_end():
    """Chiude sessione conversazione (R28)"""
    conv_session_id = cl.user_session.get("conv_session_id")
    if conv_session_id:
        try:
            conv_logger = get_conv_logger()
            conv_logger.end_session(conv_session_id)
            logger.info(f"[R28] Conversation session ended: {conv_session_id}")
        except Exception as e:
            logger.warning(f"[R28] Errore chiusura sessione: {e}")


@cl.on_chat_resume
async def on_chat_resume(thread):
    """
    Gestisce la ripresa di sessioni (resilienza).
    Chiamato quando un utente riconnette dopo una disconnessione temporanea.
    
    Args:
        thread: Contesto della sessione precedente (ThreadDict)
    """
    logger.info(f"[RESUME] Sessione ripresa: {thread.get('id', 'unknown')}")
    
    # Recupera info utente dalla sessione esistente
    cl_user = cl.user_session.get("user")
    if cl_user:
        username = cl_user.metadata.get("username", cl_user.identifier) if cl_user.metadata else cl_user.identifier
        logger.info(f"[RESUME] Utente: {username}")
        
        # Inizializza history se non esiste
        if cl.user_session.get("history") is None:
            cl.user_session.set("history", [])
            logger.debug("[RESUME] History inizializzata")
        
        # Messaggio silenzioso di conferma (opzionale)
        # await cl.Message(content="✅ Sessione ripresa.", author="Sistema").send()
    else:
        # Se utente non trovato, reinizializza
        logger.warning("[RESUME] Utente non trovato, richiesta riautenticazione")
        await cl.Message(
            content="⚠️ Sessione scaduta. Per favore ricarica la pagina.",
            author="Sistema"
        ).send()

