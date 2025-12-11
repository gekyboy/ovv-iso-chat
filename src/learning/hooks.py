"""
Chainlit Hooks per R08-R10
Integrazione apprendimento implicito con interfaccia chat

Created: 2025-12-08

Utilizzo in app.py:
    from src.learning.hooks import LearningHooks
    
    hooks = LearningHooks()
    
    @cl.on_chat_start
    async def on_start():
        hooks.on_chat_start()
    
    @cl.on_message
    async def on_message(msg):
        query_id = hooks.on_message_start(msg.content)
        # ... process ...
        hooks.on_message_end(query_id, response)
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

try:
    import chainlit as cl
except ImportError:
    cl = None

from .learners import get_implicit_learner, ImplicitLearner

logger = logging.getLogger(__name__)


class LearningHooks:
    """
    Wrapper per integrare ImplicitLearner con Chainlit.
    
    Gestisce automaticamente:
    - Session lifecycle (start/end)
    - Query tracking (start/response/end)
    - UI events (copy, click source)
    
    Example:
        >>> hooks = LearningHooks()
        >>> 
        >>> # In @cl.on_chat_start
        >>> hooks.on_chat_start()
        >>> 
        >>> # In @cl.on_message
        >>> query_id = hooks.on_message_start(msg.content)
        >>> response = await generate_response(msg.content)
        >>> hooks.on_message_response(query_id, response, sources)
    """
    
    def __init__(self, learner: ImplicitLearner = None):
        """
        Inizializza hooks.
        
        Args:
            learner: Istanza ImplicitLearner (default singleton)
        """
        self.learner = learner or get_implicit_learner()
        self._current_query_id: Dict[str, str] = {}  # session_id -> query_id
        
        logger.info("LearningHooks inizializzato")
    
    def _get_user_session(self) -> tuple:
        """
        Ottiene user_id e session_id dalla sessione Chainlit corrente.
        
        Returns:
            (user_id, session_id)
        """
        if cl is None:
            return "unknown", f"sess_{datetime.now().timestamp()}"
        
        try:
            session = cl.user_session
            user_id = session.get("user_id", "anonymous")
            session_id = session.get("session_id", f"sess_{id(session)}")
            return user_id, session_id
        except Exception:
            return "anonymous", f"sess_{datetime.now().timestamp()}"
    
    # ═══════════════════════════════════════════════════════════════
    # LIFECYCLE HOOKS
    # ═══════════════════════════════════════════════════════════════
    
    def on_chat_start(self, user_id: str = None, session_id: str = None):
        """
        Chiamato in @cl.on_chat_start.
        
        Args:
            user_id: Override user_id (altrimenti da sessione)
            session_id: Override session_id (altrimenti da sessione)
        """
        if user_id is None or session_id is None:
            _user_id, _session_id = self._get_user_session()
            user_id = user_id or _user_id
            session_id = session_id or _session_id
        
        self.learner.on_session_start(user_id, session_id)
        
        # Salva in session per accesso futuro
        if cl:
            try:
                cl.user_session.set("learning_user_id", user_id)
                cl.user_session.set("learning_session_id", session_id)
            except Exception:
                pass
    
    def on_chat_end(self, was_positive: bool = True):
        """
        Chiamato quando la chat termina.
        
        Args:
            was_positive: Se l'esperienza è stata positiva
        """
        user_id, session_id = self._get_user_session()
        self.learner.on_session_end(session_id, was_positive)
    
    # ═══════════════════════════════════════════════════════════════
    # MESSAGE HOOKS
    # ═══════════════════════════════════════════════════════════════
    
    def on_message_start(self, content: str) -> str:
        """
        Chiamato all'inizio di @cl.on_message.
        
        Args:
            content: Testo del messaggio utente
            
        Returns:
            query_id generato (da usare in on_message_response)
        """
        user_id, session_id = self._get_user_session()
        
        # Check se è follow-up della query precedente
        prev_query_id = self._current_query_id.get(session_id)
        
        # Registra nuova query
        query_id = self.learner.on_query_start(user_id, session_id, content)
        
        # Se c'era una query precedente, registra transizione
        if prev_query_id:
            self.learner.on_follow_up(user_id, session_id, prev_query_id, content)
        
        # Aggiorna query corrente
        self._current_query_id[session_id] = query_id
        
        return query_id
    
    def on_message_response(
        self,
        query_id: str,
        response_text: str,
        sources: List[str] = None,
        memories_used: List[str] = None
    ):
        """
        Chiamato dopo che la risposta è stata generata.
        
        Args:
            query_id: ID query (da on_message_start)
            response_text: Testo della risposta
            sources: Lista doc_id citati
            memories_used: ID memorie usate
        """
        user_id, session_id = self._get_user_session()
        
        self.learner.on_response(
            user_id, session_id, query_id,
            response_text, sources, memories_used
        )
    
    def on_message_end(self, query_id: str, was_helpful: bool = None):
        """
        Chiamato quando l'utente passa alla query successiva.
        
        Nota: In Chainlit questo può essere chiamato:
        - All'inizio del messaggio successivo
        - Quando l'utente lascia la chat
        
        Args:
            query_id: ID query terminata
            was_helpful: Feedback esplicito (opzionale)
        """
        user_id, session_id = self._get_user_session()
        self.learner.on_query_end(user_id, session_id, query_id, was_helpful)
    
    # ═══════════════════════════════════════════════════════════════
    # UI EVENT HOOKS
    # ═══════════════════════════════════════════════════════════════
    
    def on_click_source(self, doc_id: str, query_id: str = None):
        """
        Chiamato quando utente clicca su una fonte.
        
        Args:
            doc_id: ID documento cliccato
            query_id: ID query corrente (opzionale, usa ultima)
        """
        user_id, session_id = self._get_user_session()
        query_id = query_id or self._current_query_id.get(session_id)
        
        self.learner.on_click_source(user_id, session_id, doc_id, query_id)
    
    def on_copy_text(self, text: str, query_id: str = None):
        """
        Chiamato quando utente copia testo dalla risposta.
        
        Args:
            text: Testo copiato
            query_id: ID query corrente (opzionale, usa ultima)
        """
        user_id, session_id = self._get_user_session()
        query_id = query_id or self._current_query_id.get(session_id)
        
        self.learner.on_copy(user_id, session_id, text, query_id)
    
    def on_scroll(self, depth: float, query_id: str = None):
        """
        Chiamato quando utente scrolla nella risposta.
        
        Args:
            depth: Profondità scroll (0-1)
            query_id: ID query corrente (opzionale, usa ultima)
        """
        user_id, session_id = self._get_user_session()
        query_id = query_id or self._current_query_id.get(session_id)
        
        self.learner.on_scroll(user_id, session_id, depth, query_id)
    
    def on_feedback(self, was_helpful: bool, query_id: str = None):
        """
        Chiamato quando utente dà feedback esplicito.
        
        Args:
            was_helpful: True se positivo, False se negativo
            query_id: ID query (opzionale, usa ultima)
        """
        user_id, session_id = self._get_user_session()
        query_id = query_id or self._current_query_id.get(session_id)
        
        if query_id:
            self.learner.on_query_end(user_id, session_id, query_id, was_helpful)
    
    # ═══════════════════════════════════════════════════════════════
    # TEACH MODE HOOKS
    # ═══════════════════════════════════════════════════════════════
    
    def on_teach_complete(
        self,
        content: str,
        memory_type: str,
        doc_id: str = None
    ):
        """
        Chiamato quando /teach viene completato.
        
        Args:
            content: Contenuto insegnato
            memory_type: Tipo memoria (fact, preference, procedure)
            doc_id: ID documento associato
        """
        user_id, session_id = self._get_user_session()
        
        self.learner.on_teach_complete(
            user_id, session_id, content, memory_type, doc_id
        )
    
    def on_teach_abort(self, doc_id: str = None):
        """
        Chiamato quando /teach viene abbandonato.
        
        Args:
            doc_id: ID documento associato
        """
        user_id, session_id = self._get_user_session()
        self.learner.on_teach_abort(user_id, session_id, doc_id)
    
    # ═══════════════════════════════════════════════════════════════
    # UTILITY
    # ═══════════════════════════════════════════════════════════════
    
    def get_current_query_id(self) -> Optional[str]:
        """Ottiene ID query corrente per la sessione"""
        _, session_id = self._get_user_session()
        return self._current_query_id.get(session_id)
    
    def get_implicit_score(self, query_id: str = None) -> float:
        """
        Calcola score implicito per query.
        
        Args:
            query_id: ID query (default: corrente)
            
        Returns:
            Score da -1 a +1
        """
        user_id, session_id = self._get_user_session()
        query_id = query_id or self._current_query_id.get(session_id)
        
        if not query_id:
            return 0.0
        
        return self.learner.get_user_implicit_score(user_id, query_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Ottiene statistiche learning"""
        return self.learner.get_learning_stats()


# Singleton
_hooks: Optional[LearningHooks] = None


def get_learning_hooks() -> LearningHooks:
    """Ottiene istanza singleton LearningHooks"""
    global _hooks
    if _hooks is None:
        _hooks = LearningHooks()
    return _hooks


# Esempio integrazione in app.py
"""
# In app.py

from src.learning.hooks import get_learning_hooks

learning_hooks = get_learning_hooks()

@cl.on_chat_start
async def on_chat_start():
    learning_hooks.on_chat_start()
    # ... altro setup ...

@cl.on_message
async def on_message(msg: cl.Message):
    # Track inizio query
    query_id = learning_hooks.on_message_start(msg.content)
    
    # Genera risposta
    response, sources = await generate_response(msg.content)
    
    # Track risposta
    learning_hooks.on_message_response(query_id, response, sources)
    
    # Invia risposta
    await cl.Message(content=response).send()

@cl.on_chat_end
def on_chat_end():
    learning_hooks.on_chat_end()

# Per eventi UI (se implementati):
@cl.action_callback("click_source")
async def on_source_click(action):
    learning_hooks.on_click_source(action.value)
"""

