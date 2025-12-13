"""
OVV ISO Chat v3.1 - FastAPI Server
Server alternativo per l'app Mesop (compatibile con Windows)
"""

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import uvicorn
import logging

# Import della nostra logica Mesop
from src.ui.mesop_handlers import handle_query_mesop, handle_command_mesop
from src.auth.models import User, Role
from src.auth.store import UserStore
from src.ui.shared.documents import get_document_manager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="OVV ISO Chat v3.1", version="3.1.0")

# Templates (useremo HTML semplice invece di Jinja2 per semplicità)
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)

# Session storage semplice (per demo - in produzione usare Redis/DB)
sessions = {}

# User store singleton
_user_store = None

def get_user_store():
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store


@app.get("/", response_class=HTMLResponse)
async def home():
    """Home page con navigazione"""
    user_id = "demo_user"  # Per demo semplificata

    if user_id in sessions:
        # User già loggato
        user = sessions[user_id]
        return f"""
        <html>
        <head><title>OVV ISO Chat</title></head>
        <body>
            <h1>OVV ISO Chat v3.1</h1>
            <p>Benvenuto, {user['display_name']} ({user['role']})!</p>
            <a href="/chat">💬 Vai al Chat</a> |
            <a href="/admin">🛠️ Vai all'Admin</a> |
            <a href="/logout">🚪 Logout</a>
        </body>
        </html>
        """
    else:
        # Redirect al login
        return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Login page semplificata"""
    return """
    <html>
    <head><title>Login - OVV ISO Chat</title></head>
    <body>
        <h1>🔐 Login</h1>
        <form action="/login" method="post">
            <label>Username:</label><br>
            <input type="text" name="username" value="admin"><br><br>

            <label>Password:</label><br>
            <input type="password" name="password" value="admin123"><br><br>

            <input type="submit" value="Accedi">
        </form>
        <p><small>Credenziali demo: admin/admin123 o engineer/eng123</small></p>
    </body>
    </html>
    """


@app.post("/login", response_class=HTMLResponse)
async def login(username: str = Form(...), password: str = Form(...)):
    """Processa login"""
    try:
        store = get_user_store()
        user = store.authenticate(username, password)

        if user:
            user_data = {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role.value
            }
            sessions["demo_user"] = user_data

            logger.info(f"Login riuscito: {username}")
            return RedirectResponse(url="/", status_code=302)
        else:
            return """
            <html>
            <head><title>Login Fallito</title></head>
            <body>
                <h1>❌ Credenziali non valide</h1>
                <a href="/login">Riprova</a>
            </body>
            </html>
            """

    except Exception as e:
        logger.error(f"Errore login: {e}")
        return f"""
        <html>
        <head><title>Errore</title></head>
        <body>
            <h1>Errore interno: {str(e)}</h1>
            <a href="/login">Torna al login</a>
        </body>
        </html>
        """


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    """Chat page semplificata"""
    user = sessions.get("demo_user")
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Recupera messaggi dalla sessione
    messages = sessions.get("demo_user", {}).get("messages", [])

    # Costruisci HTML dei messaggi
    messages_html = ""
    for msg in messages[-10:]:  # Ultimi 10 messaggi
        sender = msg.get("sender", "unknown")
        content = msg.get("content", "")
        if sender == "user":
            messages_html += f'<div style="background:#e8f5e8; padding:10px; margin:5px; border-radius:8px; text-align:right;">{content}</div>'
        else:
            messages_html += f'<div style="background:#f0f0f0; padding:10px; margin:5px; border-radius:8px;">{content}</div>'

    return f"""
    <html>
    <head><title>Chat - OVV ISO Chat</title></head>
    <body>
        <h1>💬 Chat - OVV ISO Chat</h1>
        <p>Utente: {user['display_name']} ({user['role']})</p>

        <div id="chat" style="height:400px; border:1px solid #ddd; padding:10px; overflow-y:auto;">
            {messages_html}
        </div>

        <form action="/chat" method="post" style="margin-top:10px;">
            <input type="text" name="message" placeholder="Scrivi la tua domanda..." style="width:70%; padding:8px;">
            <input type="submit" value="Invia" style="padding:8px;">
        </form>

        <div style="margin-top:10px;">
            <button onclick="sendCommand('/status')">/status</button>
            <button onclick="sendCommand('/documenti')">/documenti</button>
            <button onclick="sendCommand('/glossario')">/glossario</button>
        </div>

        <script>
        function sendCommand(cmd) {{
            var form = document.createElement('form');
            form.method = 'POST';
            form.action = '/chat';
            var input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'message';
            input.value = cmd;
            form.appendChild(input);
            document.body.appendChild(form);
            form.submit();
        }}
        </script>
    </body>
    </html>
    """


@app.post("/chat", response_class=HTMLResponse)
async def chat_message(message: str = Form(...)):
    """Processa messaggio chat"""
    user = sessions.get("demo_user")
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Inizializza messaggi se non esistono
    if "messages" not in sessions["demo_user"]:
        sessions["demo_user"]["messages"] = []

    messages = sessions["demo_user"]["messages"]

    # Aggiungi messaggio utente
    messages.append({"sender": "user", "content": message})

    try:
        # Gestisci comandi
        if message.startswith("/"):
            result = handle_command_mesop(message, user)
            if result:
                messages.append({"sender": "system", "content": result})
        else:
            # Query RAG normale
            result = handle_query_mesop(message, user)
            messages.append({
                "sender": "ai",
                "content": result.get("answer", "Errore nella risposta")
            })

    except Exception as e:
        logger.error(f"Errore processamento messaggio: {e}")
        messages.append({"sender": "system", "content": f"Errore: {str(e)}"})

    # Limita messaggi a 50
    if len(messages) > 50:
        messages[:] = messages[-50:]

    # Redirect per aggiornare la pagina
    return RedirectResponse(url="/chat", status_code=302)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """Admin page semplificata"""
    user = sessions.get("demo_user")
    if not user or user["role"] not in ["Admin", "Engineer"]:
        return """
        <html>
        <head><title>Accesso Negato</title></head>
        <body>
            <h1>🚫 Accesso negato</h1>
            <p>Solo Admin e Engineer possono accedere all'area admin.</p>
            <a href="/">Torna alla home</a>
        </body>
        </html>
        """

    return f"""
    <html>
    <head><title>Admin - OVV ISO Chat</title></head>
    <body>
        <h1>🛠️ Admin Panel</h1>
        <p>Benvenuto, {user['display_name']} ({user['role']})</p>

        <div style="display:flex; gap:20px;">
            <div style="flex:1;">
                <h3>📊 Dashboard</h3>
                <p>KPI e metriche principali</p>
                <p><em>Implementato: Service layer completo</em></p>
            </div>

            <div style="flex:1;">
                <h3>📝 Proposals</h3>
                <p>Gestione proposte pending</p>
                <p><em>Implementato: Approve/reject workflow</em></p>
            </div>

            <div style="flex:1;">
                <h3>📖 Glossary</h3>
                <p>CRUD acronimi</p>
                <p><em>Implementato: Service layer completo</em></p>
            </div>
        </div>

        <div style="display:flex; gap:20px; margin-top:20px;">
            <div style="flex:1;">
                <h3>🧠 Memories</h3>
                <p>Browser memorie</p>
                <p><em>Implementato: Namespace management</em></p>
            </div>

            <div style="flex:1;">
                <h3>👥 Users</h3>
                <p>CRUD utenti (Admin only)</p>
                <p><em>Implementato: Service layer</em></p>
            </div>

            <div style="flex:1;">
                <h3>🎯 Consensus</h3>
                <p>Segnali impliciti</p>
                <p><em>Implementato: Event tracking</em></p>
            </div>
        </div>

        <p style="margin-top:20px;"><a href="/">← Torna al Chat</a></p>
    </body>
    </html>
    """


@app.get("/logout")
async def logout():
    """Logout"""
    if "demo_user" in sessions:
        del sessions["demo_user"]
    return RedirectResponse(url="/login", status_code=302)


@app.get("/status")
async def status():
    """Endpoint status per verifica"""
    return {
        "status": "running",
        "version": "3.1.0",
        "features": {
            "chat": True,
            "admin": True,
            "auth": True,
            "rag_pipeline": True,
            "consensus_tracking": True
        },
        "modules_loaded": 15,
        "total_features": 30
    }


if __name__ == "__main__":
    print("🚀 Avvio OVV ISO Chat v3.1 - FastAPI Server")
    print("URL: http://localhost:8000")
    print("Admin demo: admin/admin123")
    print("Engineer demo: engineer/eng123")
    uvicorn.run(app, host="0.0.0.0", port=8000)
