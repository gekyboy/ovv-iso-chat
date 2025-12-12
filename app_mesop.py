"""
OVV ISO Chat v3.1 - Mesop UI (Completa)
App unificata Chat + Admin con feature parity Chainlit
"""

import mesop as me
import mesop.labs as mel
import logging
from typing import Optional

from src.ui.mesop_handlers import handle_query_mesop, handle_command_mesop
from src.auth.models import User, Role
from src.auth.store import UserStore
from src.ui.shared.documents import get_document_manager
from src.analytics.collectors.conversation_logger import get_conversation_logger
from src.ui.event_tracking import get_event_tracker, reset_event_tracker

logger = logging.getLogger(__name__)

# Singleton UserStore (come in Chainlit)
_user_store = None

def get_user_store() -> UserStore:
    """Ottiene istanza singleton UserStore"""
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store


@me.page(path="/")
def home_page():
    """Home page - Redirect a login se non autenticato"""
    user = me.state().get("user")
    if not user:
        me.navigate("/login")
        return

    me.text("OVV ISO Chat v3.1", style=me.Style(font_size=24, font_weight="bold"))
    me.text(f"Benvenuto, {user['display_name']}!", style=me.Style(font_size=18))

    with me.box(style=me.Style(display="flex", gap=20, margin=me.Margin(top=20))):
        me.button("💬 Chat", on_click=lambda e: me.navigate("/chat"), style=me.Style(font_size=16))
        if user["role"] in ["Admin", "Engineer"]:
            me.button("🛠️ Admin", on_click=lambda e: me.navigate("/admin"), style=me.Style(font_size=16))
        me.button("🚪 Logout", on_click=on_logout, style=me.Style(background="#ff4444", color="white"))


@me.page(path="/login")
def login_page():
    """Pagina login con RBAC"""
    me.text("🔐 Login - OVV ISO Chat", style=me.Style(font_size=24, font_weight="bold"))

    # Form login
    mel.text(
        label="Username:",
        on_input=lambda e: me.state(username=e.value),
        style=me.Style(width="100%", margin=me.Margin(bottom=10))
    )

    mel.text(
        label="Password:",
        type="password",
        on_input=lambda e: me.state(password=e.value),
        style=me.Style(width="100%", margin=me.Margin(bottom=20))
    )

    me.button("Accedi", on_click=on_login, style=me.Style(width="100%"))

    # Messaggio errore
    error = me.state().get("login_error")
    if error:
        me.text(error, style=me.Style(color="red", margin=me.Margin(top=10)))


@me.page(path="/chat")
def chat_page():
    """Chat page completa con feature parity Chainlit"""
    user = me.state().get("user")
    if not user:
        me.navigate("/login")
        return

    me.text("💬 Chat - OVV ISO Chat", style=me.Style(font_size=20, font_weight="bold"))
    me.text(f"Utente: {user['display_name']} ({user['role']})", style=me.Style(font_size=14, color="gray"))

    # Chat container
    with me.box(style=me.Style(height="70vh", border="1px solid #ddd", border_radius=8, padding=20, overflow_y="auto")):

        # Mostra messaggi precedenti
        messages = me.state().get("messages", [])
        for msg in messages[-20:]:  # Ultimi 20 messaggi
            message_bubble(msg)

        # Status/progress area
        status = me.state().get("status")
        if status:
            me.text(f"⏳ {status}", style=me.Style(color="blue", font_style="italic"))

    # Input area
    with me.box(style=me.Style(display="flex", gap=10, margin=me.Margin(top=10))):
        mel.textarea(
            label="Scrivi la tua domanda:",
            on_input=lambda e: me.state(current_message=e.value),
            value=me.state().get("current_message", ""),
            style=me.Style(flex=1, min_height=60)
        )

        me.button("📤 Invia", on_click=on_send_message)

    # Fonti area (se presenti)
    sources = me.state().get("current_sources", [])
    if sources:
        show_sources_sidebar(sources)

    # Controls
    with me.box(style=me.Style(display="flex", gap=10, margin=me.Margin(top=10))):
        me.button("📁 /documenti", on_click=lambda e: handle_command_input("/documenti"))
        me.button("📊 /status", on_click=lambda e: handle_command_input("/status"))
        me.button("📖 /glossario", on_click=lambda e: handle_command_input("/glossario"))


def message_bubble(msg: dict):
    """Mostra un messaggio nella chat"""
    with me.box(style=me.Style(
        margin=me.Margin.symmetric(vertical=5),
        padding=me.Padding.all(10),
        background="#f0f0f0" if msg.get("sender") == "user" else "#e8f5e8",
        border_radius=8,
        align_self="flex-end" if msg.get("sender") == "user" else "flex-start"
    )):
        me.text(msg.get("content", ""), style=me.Style(white_space="pre-wrap"))

        # Feedback buttons per risposte AI
        if msg.get("sender") == "ai":
            with me.box(style=me.Style(display="flex", gap=5, margin=me.Margin(top=5))):
                me.button("👍", on_click=lambda e, m=msg: on_feedback(m, "positive"), style=me.Style(font_size=12))
                me.button("👎", on_click=lambda e, m=msg: on_feedback(m, "negative"), style=me.Style(font_size=12))


def show_sources_sidebar(sources: list):
    """Mostra sidebar con fonti citate"""
    with me.box(style=me.Style(
        position="fixed", right=10, top=100, width=300, height="60vh",
        background="white", border="1px solid #ddd", border_radius=8,
        padding=10, overflow_y="auto", box_shadow="0 2px 8px rgba(0,0,0,0.1)"
    )):
        me.text("📚 Fonti Consultate", style=me.Style(font_weight="bold", margin=me.Margin(bottom=10)))

        for source in sources:
            with me.box(style=me.Style(margin=me.Margin(bottom=10), padding=me.Padding.all(5), background="#f9f9f9", border_radius=4)):
                me.text(f"📄 {source.get('title', source.get('doc_id', 'N/A'))}", style=me.Style(font_weight="bold"))
                me.text(f"ID: {source.get('doc_id', 'N/A')}", style=me.Style(font_size=12, color="gray"))

                # Preview testo
                preview = source.get('preview', '')
                if preview:
                    me.text(preview[:200] + "..." if len(preview) > 200 else preview,
                           style=me.Style(font_size=12, margin=me.Margin(top=5)))

                # PDF link
                pdf_path = source.get('pdf_path')
                if pdf_path:
                    me.button(f"📖 Apri PDF", on_click=lambda e, p=pdf_path: open_pdf(p))


@me.page(path="/admin")
def admin_page():
    """Admin page con menu laterale e RBAC"""
    user = me.state().get("user")
    if not user or user["role"] not in ["Admin", "Engineer"]:
        me.navigate("/login")
        return

    # Layout admin
    with me.box(style=me.Style(display="flex")):

        # Sidebar menu
        with me.box(style=me.Style(width=200, padding=20, background="#f5f5f5", min_height="100vh")):
            me.text("🛠️ Admin Panel", style=me.Style(font_weight="bold", margin=me.Margin(bottom=20)))

            me.button("📊 Dashboard", on_click=lambda e: me.state(admin_page="dashboard"), style=me.Style(width="100%", margin=me.Margin(bottom=5)))
            me.button("📝 Proposals", on_click=lambda e: me.state(admin_page="proposals"), style=me.Style(width="100%", margin=me.Margin(bottom=5)))
            me.button("📖 Glossary", on_click=lambda e: me.state(admin_page="glossary"), style=me.Style(width="100%", margin=me.Margin(bottom=5)))
            me.button("🧠 Memories", on_click=lambda e: me.state(admin_page="memories"), style=me.Style(width="100%", margin=me.Margin(bottom=5)))
            me.button("📈 Analytics", on_click=lambda e: me.state(admin_page="analytics"), style=me.Style(width="100%", margin=me.Margin(bottom=5)))
            me.button("🎯 Consensus", on_click=lambda e: me.state(admin_page="consensus"), style=me.Style(width="100%", margin=me.Margin(bottom=5)))
            me.button("💬 Conversations", on_click=lambda e: me.state(admin_page="conversations"), style=me.Style(width="100%", margin=me.Margin(bottom=5)))

            if user["role"] == "Admin":
                me.button("👥 Users", on_click=lambda e: me.state(admin_page="users"), style=me.Style(width="100%", margin=me.Margin(bottom=5)))

            me.button("← Torna al Chat", on_click=lambda e: me.navigate("/chat"), style=me.Style(width="100%", margin=me.Margin(top=20)))

        # Content area
        with me.box(style=me.Style(flex=1, padding=20)):
            current_page = me.state().get("admin_page", "dashboard")
            render_admin_content(current_page, user)


def on_login(e: me.ClickEvent):
    """Gestisce login con RBAC (come Chainlit)"""
    username = me.state().get("username", "").strip()
    password = me.state().get("password", "").strip()

    if not username or not password:
        me.state(login_error="Inserisci username e password")
        return

    try:
        store = get_user_store()
        user = store.authenticate(username, password)

        if user:
            # Salva sessione utente (come in Chainlit)
            user_data = {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role.value
            }
            me.state(user=user_data)

            # Inizializza conversazione
            init_conversation_session(user_data)

            # Reset event tracker per nuova sessione
            reset_event_tracker()

            # Reset form
            me.state(username="", password="", login_error="")

            # Redirect
            me.navigate("/")
        else:
            me.state(login_error="Credenziali non valide")

    except Exception as ex:
        logger.error(f"Errore login: {ex}")
        me.state(login_error="Errore interno del server")


def on_logout(e: me.ClickEvent):
    """Logout e pulizia sessione"""
    me.state(user=None, messages=[], current_sources=[], status="")
    me.navigate("/login")


def on_send_message(e: me.ClickEvent):
    """Gestisce invio messaggio chat"""
    user = me.state().get("user")
    if not user:
        me.navigate("/login")
        return

    message = me.state().get("current_message", "").strip()
    if not message:
        return

    # Aggiungi messaggio utente alla chat
    messages = me.state().get("messages", [])
    messages.append({"sender": "user", "content": message, "timestamp": get_timestamp()})
    me.state(messages=messages, current_message="", status="Elaborazione in corso...")

    try:
        # Gestisci comandi speciali
        if message.startswith("/"):
            result = handle_command_mesop(message, user)
            if result:
                messages.append({"sender": "system", "content": result, "timestamp": get_timestamp()})
                me.state(messages=messages, status="")
                return

        # Query RAG normale
        result = handle_query_mesop(message, user)

        # Aggiungi risposta AI
        messages.append({
            "sender": "ai",
            "content": result.get("answer", "Errore nella risposta"),
            "sources": result.get("sources", []),
            "timestamp": get_timestamp()
        })

        # Aggiorna fonti
        me.state(current_sources=result.get("sources", []))

        # Track query completata
        tracker = get_event_tracker()
        tracker.track_event(
            "query_completed",
            {
                "query_length": len(message),
                "response_length": len(result.get("answer", "")),
                "sources_count": len(result.get("sources", []))
            },
            user
        )

    except Exception as ex:
        logger.error(f"Errore processamento messaggio: {ex}")
        messages.append({"sender": "system", "content": f"Errore: {str(ex)}", "timestamp": get_timestamp()})

    me.state(messages=messages, status="")


def handle_command_input(command: str):
    """Gestisce input comando diretto"""
    user = me.state().get("user")
    if not user:
        return

    # Simula invio messaggio
    me.state(current_message=command)
    on_send_message(None)


def on_feedback(msg: dict, feedback_type: str):
    """Gestisce feedback 👍👎 sui messaggi (stessa logica Chainlit)"""
    user = me.state().get("user")
    if not user:
        return

    try:
        # Estrai fonti dal messaggio (se disponibili)
        sources = msg.get("sources", [])

        # Processa feedback con stessa logica di Chainlit
        from src.ui.mesop_handlers import process_feedback_mesop
        process_feedback_mesop(
            user_data=user,
            message_content=msg.get("content", ""),
            feedback_type=feedback_type,
            sources=sources
        )

        # Track feedback come evento consenso
        tracker = get_event_tracker()
        tracker.track_event(
            "feedback_given",
            {
                "feedback_type": feedback_type,
                "message_length": len(msg.get("content", "")),
                "has_sources": bool(sources)
            },
            user
        )

        # Feedback UI
        emoji = "👍" if feedback_type == "positive" else "👎"
        me.snackbar(f"Grazie per il feedback {emoji}! Il sistema impara dalle tue valutazioni.")

    except Exception as ex:
        logger.error(f"Errore feedback: {ex}")
        me.snackbar("Errore nel processamento del feedback")


def open_pdf(pdf_path: str):
    """Apre PDF viewer con tracking evento"""
    user = me.state().get("user")
    if user:
        # Track click su fonte PDF
        tracker = get_event_tracker()
        tracker.track_source_click({"pdf_path": pdf_path}, user)

    # TODO: Implementare PDF viewer integrato
    me.snackbar(f"Apertura PDF: {pdf_path}")


def init_conversation_session(user_data: dict):
    """Inizializza sessione conversazione (come Chainlit)"""
    try:
        # Crea conversation logger session
        logger = get_conversation_logger()
        session_id = logger.start_conversation(
            user_id=user_data["id"],
            username=user_data["username"],
            user_role=user_data["role"]
        )

        # Inizializza stato chat
        me.state(
            messages=[],
            current_sources=[],
            status="",
            conv_session_id=session_id
        )

        logger.info(f"[MESOP] Sessione conversazione iniziata: {session_id}")

    except Exception as ex:
        logger.error(f"Errore inizializzazione sessione: {ex}")


def get_timestamp() -> str:
    """Ottiene timestamp corrente"""
    from datetime import datetime
    return datetime.now().isoformat()


def render_admin_content(page: str, user: dict):
    """Render contenuto admin page"""
    if page == "dashboard":
        render_dashboard()
    elif page == "proposals":
        render_proposals(user)
    elif page == "glossary":
        render_glossary()
    elif page == "memories":
        render_memories(user)
    elif page == "analytics":
        render_analytics()
    elif page == "consensus":
        render_consensus()
    elif page == "conversations":
        render_conversations()
    elif page == "users" and user["role"] == "Admin":
        render_users()
    else:
        me.text("Seleziona una sezione dal menu laterale")


def render_dashboard():
    """Dashboard admin con KPI reali"""
    me.text("📊 Dashboard", style=me.Style(font_size=24, font_weight="bold"))

    try:
        from admin.services.dashboard_service import get_dashboard_service
        service = get_dashboard_service()
        kpi_data = service.get_kpi_data()

        # KPI Cards
        col1, col2, col3, col4 = me.columns(4)

        with col1:
            me.metric(
                label="📋 Proposte Pending",
                value=kpi_data["pending_proposals"]["total"],
                delta=f"+{kpi_data['pending_proposals']['today']} oggi"
            )

        with col2:
            me.metric(
                label="🧠 Memorie Totali",
                value=kpi_data["total_memories"]
            )

        with col3:
            me.metric(
                label="📚 Acronimi",
                value=kpi_data["total_acronyms"]
            )

        with col4:
            me.metric(
                label="👥 Utenti",
                value=kpi_data["total_users"]
            )

    except Exception as e:
        me.text(f"Errore caricamento dashboard: {e}")


def render_proposals(user: dict):
    """Proposals management con logica reale"""
    me.text("📝 Proposals", style=me.Style(font_size=24, font_weight="bold"))

    try:
        from admin.services.proposals_service import get_proposals_service
        service = get_proposals_service()
        proposals = service.get_pending_proposals()

        if not proposals:
            me.success("✅ Nessuna proposta in attesa!")
            return

        # Lista proposte con azioni
        for proposal in proposals:
            with me.expander(f"📋 {proposal['content'][:50]}..."):
                me.text(f"**Tipo**: {proposal['type']}")
                me.text(f"**Autore**: {proposal['author']}")
                me.text(f"**Data**: {proposal['created_at']}")

                # Azioni
                col1, col2 = me.columns(2)
                with col1:
                    if me.button(f"✅ Approva", key=f"approve_{proposal['id']}"):
                        result = service.approve_proposal(proposal['id'], user)
                        if result["success"]:
                            me.success(result["message"])
                            me.reload()  # Ricarica pagina
                        else:
                            me.error(result["error"])

                with col2:
                    if me.button(f"❌ Rifiuta", key=f"reject_{proposal['id']}"):
                        result = service.reject_proposal(proposal['id'], user)
                        if result["success"]:
                            me.success(result["message"])
                            me.reload()
                        else:
                            me.error(result["error"])

    except Exception as e:
        me.text(f"Errore caricamento proposte: {e}")


def render_glossary():
    """Glossary management"""
    me.text("📖 Glossary", style=me.Style(font_size=24, font_weight="bold"))

    try:
        from admin.services.glossary_service import get_glossary_service
        service = get_glossary_service()
        acronyms = service.get_acronyms()

        me.text(f"**Totale acronimi**: {len(acronyms)}")

        # Lista acronimi
        for acronym in acronyms[:20]:  # Max 20 per pagina
            with me.expander(f"{acronym['acronym']} → {acronym['expansion']}"):
                me.text(f"**Descrizione**: {acronym['description']}")
                me.text(f"**Categoria**: {acronym['category']}")
                me.text(f"**Confidenza**: {acronym['confidence']:.2f}")

    except Exception as e:
        me.text(f"Errore caricamento glossario: {e}")


def render_memories(user: dict):
    """Memories browser"""
    me.text("🧠 Memories", style=me.Style(font_size=24, font_weight="bold"))

    try:
        from admin.services.memories_service import get_memories_service
        service = get_memories_service()

        # Tab per namespace
        tab1, tab2 = me.tabs(["Global", "User"])

        with tab1:
            memories = service.get_memories(namespace="global", limit=20)
            render_memories_list(memories, "global", user)

        with tab2:
            user_namespace = f"user_{user['username']}"
            memories = service.get_memories(namespace=user_namespace, limit=20)
            render_memories_list(memories, user_namespace, user)

    except Exception as e:
        me.text(f"Errore caricamento memorie: {e}")


def render_memories_list(memories: list, namespace: str, user: dict):
    """Helper per render lista memorie"""
    if not memories:
        me.text(f"Nessuna memoria in {namespace}")
        return

    for memory in memories:
        with me.expander(f"{memory['type']}: {memory['content'][:50]}..."):
            me.text(f"**ID**: {memory['id']}")
            me.text(f"**Tipo**: {memory['type']}")
            me.text(f"**Data**: {memory['created_at']}")

            # Azioni
            if user['role'] == 'Admin' and namespace != 'global':
                if me.button(f"⬆️ Promuovi a Global", key=f"promote_{memory['id']}"):
                    from admin.services.memories_service import get_memories_service
                    service = get_memories_service()
                    result = service.promote_memory(memory['id'], "global")
                    if result["success"]:
                        me.success(result["message"])
                    else:
                        me.error(result["error"])


def render_analytics():
    """Analytics dashboard"""
    me.text("📈 Analytics", style=me.Style(font_size=24, font_weight="bold"))

    try:
        from admin.services.analytics_service import get_analytics_service
        service = get_analytics_service()
        data = service.get_analytics_data()

        col1, col2 = me.columns(2)

        with col1:
            me.metric("Query Totali", data.get("total_queries", 0))
            me.metric("Tempo Medio Risposta", f"{data.get('avg_response_time', 0):.1f}s")

        with col2:
            me.metric("Soddisfazione Utente", f"{data.get('user_satisfaction', 0):.1f}/5")
            me.text("**Topics Popolari**:"            for topic in data.get("popular_topics", []):
                me.text(f"• {topic}")

    except Exception as e:
        me.text(f"Errore caricamento analytics: {e}")


def render_consensus():
    """Consensus signals"""
    me.text("🎯 Consensus", style=me.Style(font_size=24, font_weight="bold"))

    try:
        from admin.services.consensus_service import get_consensus_service
        service = get_consensus_service()
        signals = service.get_consensus_signals()

        for signal in signals:
            with me.expander(f"{signal['pattern']} (Strength: {signal['strength']:.2f})"):
                me.text(f"**Occorrenze**: {signal['occurrences']}")
                me.text(f"**Ultima volta**: {signal['last_seen']}")
                me.text(f"**Descrizione**: {signal['description']}")

                if me.button(f"⬆️ Promuovi", key=f"promote_signal_{signal['id']}"):
                    result = service.promote_signal(signal['id'])
                    if result["success"]:
                        me.success(result["message"])
                    else:
                        me.error(result["error"])

    except Exception as e:
        me.text(f"Errore caricamento consensus: {e}")


def render_conversations():
    """Conversations history"""
    me.text("💬 Conversations", style=me.Style(font_size=24, font_weight="bold"))

    try:
        from admin.services.conversations_service import get_conversations_service
        service = get_conversations_service()
        conversations = service.get_conversations(limit=20)

        for conv in conversations:
            with me.expander(f"{conv['user']} - {conv['messages_count']} messaggi"):
                me.text(f"**ID**: {conv['id']}")
                me.text(f"**Iniziata**: {conv['started_at']}")
                me.text(f"**Ultima attività**: {conv['last_activity']}")
                me.text(f"**Feedback**: {conv['feedback_count']}")
                me.text(f"**Confidenza media**: {conv['avg_confidence']:.2f}")

    except Exception as e:
        me.text(f"Errore caricamento conversazioni: {e}")


def render_users():
    """Users management (solo Admin)"""
    me.text("👥 Users", style=me.Style(font_size=24, font_weight="bold"))

    try:
        from admin.services.users_service import get_users_service
        service = get_users_service()
        users = service.get_users()

        for user in users:
            with me.expander(f"{user['display_name']} ({user['username']})"):
                me.text(f"**Ruolo**: {user['role']}")
                me.text(f"**ID**: {user['id']}")
                if user.get('last_login'):
                    me.text(f"**Ultimo accesso**: {user['last_login']}")

                # Azioni CRUD (solo per Admin diverso da sé stesso)
                # TODO: Implementare azioni utente

    except Exception as e:
        me.text(f"Errore caricamento utenti: {e}")


def track_text_copy(text: str, context: str = "response"):
    """Track copia testo (da chiamare quando utente copia)"""
    user = me.state().get("user")
    if user:
        tracker = get_event_tracker()
        tracker.track_text_copy(text, context, user)


def track_scroll(position: float, content_type: str = "chat"):
    """Track scroll nel contenuto"""
    user = me.state().get("user")
    if user:
        tracker = get_event_tracker()
        tracker.track_scroll(position, content_type, user)


def track_dwell_time(element_id: str, seconds: float):
    """Track tempo di permanenza su elemento"""
    user = me.state().get("user")
    if user:
        tracker = get_event_tracker()
        tracker.track_dwell_time(element_id, seconds, user)


# Placeholder per future integrazioni DOM events
# TODO: Implementare event listener per:
# - Copy events (navigator.clipboard)
# - Scroll events
# - Focus/dwell time tracking
# - Click events su fonti
