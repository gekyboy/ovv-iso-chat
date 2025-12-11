"""
Unified Conversation Logger per OVV ISO Chat
Registra ogni conversazione completa con metadati per analisi

R28 - Conversation Logging
Created: 2025-12-09

Registra:
- Sessione completa (inizio/fine, durata)
- Ogni interazione Q&A (query, risposta, fonti, latenza)
- Feedback associato
- Segnali impliciti collegati
"""

import json
import uuid
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class InteractionStatus(str, Enum):
    """Stato di un'interazione"""
    SUCCESS = "success"           # Risposta con fonti
    NO_RESULTS = "no_results"     # Nessun documento trovato
    ERROR = "error"               # Errore pipeline
    COMMAND = "command"           # Comando slash (/teach, /status, etc.)
    DISAMBIGUATION = "disambiguation"  # Richiesta disambiguazione


@dataclass
class Interaction:
    """Singola interazione Q&A"""
    id: str                                # UUID interazione
    timestamp: str                         # ISO format
    
    # Query
    query_original: str                    # Query utente originale
    query_reformulated: str = ""           # Dopo reformulation con history
    query_expanded: str = ""               # Dopo espansione acronimi
    
    # Response
    response_text: str = ""                # Risposta LLM completa
    response_length: int = 0               # Lunghezza caratteri
    
    # Sources
    sources_retrieved: int = 0             # N. documenti retrieval iniziale
    sources_after_rerank_l1: int = 0       # Dopo FlashRank
    sources_after_rerank_l2: int = 0       # Dopo Qwen3
    sources_cited: List[str] = field(default_factory=list)  # doc_id citati
    sources_missing: List[str] = field(default_factory=list)  # Citazioni fantasma
    
    # Glossary & Memory
    acronyms_found: List[str] = field(default_factory=list)
    acronyms_expanded: Dict[str, str] = field(default_factory=dict)
    memory_context_used: bool = False
    
    # Performance
    latency_total_ms: int = 0
    latency_retrieval_ms: int = 0
    latency_rerank_l1_ms: int = 0
    latency_rerank_l2_ms: int = 0
    latency_llm_ms: int = 0
    
    # Status & Feedback
    status: str = InteractionStatus.SUCCESS.value
    feedback: Optional[str] = None         # "positive", "negative", None
    feedback_at: Optional[str] = None
    
    # R15/R16 Tool suggestions
    tools_suggested: List[str] = field(default_factory=list)
    teach_doc_id: Optional[str] = None     # Se era /teach
    
    # R19 Gap detection
    gap_detected: bool = False
    gap_reported: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Interaction":
        # Gestisci campi mancanti per retrocompatibilità
        defaults = {
            "query_reformulated": "",
            "query_expanded": "",
            "response_text": "",
            "response_length": 0,
            "sources_retrieved": 0,
            "sources_after_rerank_l1": 0,
            "sources_after_rerank_l2": 0,
            "sources_cited": [],
            "sources_missing": [],
            "acronyms_found": [],
            "acronyms_expanded": {},
            "memory_context_used": False,
            "latency_total_ms": 0,
            "latency_retrieval_ms": 0,
            "latency_rerank_l1_ms": 0,
            "latency_rerank_l2_ms": 0,
            "latency_llm_ms": 0,
            "status": InteractionStatus.SUCCESS.value,
            "feedback": None,
            "feedback_at": None,
            "tools_suggested": [],
            "teach_doc_id": None,
            "gap_detected": False,
            "gap_reported": False
        }
        for key, default in defaults.items():
            if key not in data:
                data[key] = default
        return cls(**data)


@dataclass
class Session:
    """Sessione utente completa"""
    id: str                                # UUID sessione
    user_id: str
    user_role: str                         # admin, engineer, user
    
    started_at: str                        # ISO format
    ended_at: Optional[str] = None         # ISO format (None = attiva)
    
    # Interazioni
    interactions: List[Interaction] = field(default_factory=list)
    
    # Statistiche sessione
    total_interactions: int = 0
    positive_feedback_count: int = 0
    negative_feedback_count: int = 0
    avg_latency_ms: float = 0
    
    # Metadata sessione
    client_info: Dict[str, Any] = field(default_factory=dict)  # browser, etc.
    
    def add_interaction(self, interaction: Interaction):
        """Aggiunge interazione e aggiorna stats"""
        self.interactions.append(interaction)
        self.total_interactions = len(self.interactions)
        
        # Aggiorna latenza media
        latencies = [i.latency_total_ms for i in self.interactions if i.latency_total_ms > 0]
        self.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0
    
    def add_feedback(self, interaction_id: str, feedback: str) -> bool:
        """Aggiunge feedback a un'interazione"""
        for i in self.interactions:
            if i.id == interaction_id:
                i.feedback = feedback
                i.feedback_at = datetime.now().isoformat()
                
                if feedback == "positive":
                    self.positive_feedback_count += 1
                else:
                    self.negative_feedback_count += 1
                return True
        return False
    
    def close(self):
        """Chiude la sessione"""
        self.ended_at = datetime.now().isoformat()
    
    def duration_seconds(self) -> float:
        """Durata sessione in secondi"""
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.ended_at) if self.ended_at else datetime.now()
        return (end - start).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "interactions": [i.to_dict() for i in self.interactions],
            "total_interactions": self.total_interactions,
            "positive_feedback_count": self.positive_feedback_count,
            "negative_feedback_count": self.negative_feedback_count,
            "avg_latency_ms": self.avg_latency_ms,
            "client_info": self.client_info
        }
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        interactions_data = data.pop("interactions", [])
        interactions = [Interaction.from_dict(i) for i in interactions_data]
        
        # Gestisci campi mancanti
        defaults = {
            "ended_at": None,
            "total_interactions": 0,
            "positive_feedback_count": 0,
            "negative_feedback_count": 0,
            "avg_latency_ms": 0,
            "client_info": {}
        }
        for key, default in defaults.items():
            if key not in data:
                data[key] = default
        
        session = cls(**data)
        session.interactions = interactions
        return session


class ConversationLogger:
    """
    Logger unificato per conversazioni.
    
    Features:
    - Persistenza per sessione (un file JSON per sessione)
    - Indice giornaliero per query rapide
    - Auto-close sessioni inattive
    - Export CSV/JSON
    
    Usage:
        >>> logger = ConversationLogger()
        >>> session = logger.start_session("mario", "engineer")
        >>> interaction = logger.log_interaction(
        ...     session_id=session.id,
        ...     query_original="Come gestire le NC?",
        ...     response_text="La gestione delle NC...",
        ...     sources_cited=["PS-08_01"]
        ... )
        >>> logger.add_feedback(session.id, interaction.id, "positive")
        >>> logger.end_session(session.id)
    """
    
    def __init__(
        self,
        persist_dir: str = "data/persist/conversations",
        index_dir: str = "data/persist/conversations/index",
        inactive_timeout_min: int = 60,
        retention_days: int = 90
    ):
        self.persist_dir = Path(persist_dir)
        self.index_dir = Path(index_dir)
        self.inactive_timeout = timedelta(minutes=inactive_timeout_min)
        self.retention_days = retention_days
        
        # Cache sessioni attive (in memoria per performance)
        self._active_sessions: Dict[str, Session] = {}
        
        # Crea directory
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ConversationLogger inizializzato: {self.persist_dir}")
    
    # ═══════════════════════════════════════════════════════════════
    # SESSION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    
    def start_session(
        self,
        user_id: str,
        user_role: str,
        client_info: Dict[str, Any] = None
    ) -> Session:
        """Inizia nuova sessione"""
        session = Session(
            id=f"sess_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            user_role=user_role,
            started_at=datetime.now().isoformat(),
            client_info=client_info or {}
        )
        
        self._active_sessions[session.id] = session
        self._persist_session(session)
        self._update_index(session)
        
        logger.info(f"[ConvLog] Session started: {session.id} user={user_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Ottiene sessione (da cache o disco)"""
        # Prima cerca in cache
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]
        
        # Poi cerca su disco
        return self._load_session(session_id)
    
    def end_session(self, session_id: str) -> bool:
        """Chiude sessione"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.close()
        self._persist_session(session)
        
        # Rimuovi da cache
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
        
        logger.info(f"[ConvLog] Session ended: {session_id} ({session.duration_seconds():.0f}s)")
        return True
    
    # ═══════════════════════════════════════════════════════════════
    # INTERACTION LOGGING
    # ═══════════════════════════════════════════════════════════════
    
    def log_interaction(
        self,
        session_id: str,
        query_original: str,
        response_text: str,
        query_reformulated: str = None,
        query_expanded: str = None,
        sources_retrieved: int = 0,
        sources_after_rerank_l1: int = 0,
        sources_after_rerank_l2: int = 0,
        sources_cited: List[str] = None,
        sources_missing: List[str] = None,
        acronyms_found: List[str] = None,
        acronyms_expanded: Dict[str, str] = None,
        memory_context_used: bool = False,
        latency_total_ms: int = 0,
        latency_retrieval_ms: int = 0,
        latency_rerank_l1_ms: int = 0,
        latency_rerank_l2_ms: int = 0,
        latency_llm_ms: int = 0,
        status: str = InteractionStatus.SUCCESS.value,
        tools_suggested: List[str] = None,
        teach_doc_id: str = None,
        gap_detected: bool = False
    ) -> Optional[Interaction]:
        """
        Registra un'interazione completa.
        
        Args:
            session_id: ID sessione
            query_original: Query utente originale
            response_text: Risposta LLM completa
            ... (altri parametri opzionali)
        
        Returns:
            Interaction creata o None se sessione non trovata
        """
        session = self.get_session(session_id)
        if not session:
            logger.warning(f"[ConvLog] Session not found: {session_id}")
            return None
        
        interaction = Interaction(
            id=f"int_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now().isoformat(),
            query_original=query_original,
            query_reformulated=query_reformulated or query_original,
            query_expanded=query_expanded or "",
            response_text=response_text,
            response_length=len(response_text),
            sources_retrieved=sources_retrieved,
            sources_after_rerank_l1=sources_after_rerank_l1,
            sources_after_rerank_l2=sources_after_rerank_l2,
            sources_cited=sources_cited or [],
            sources_missing=sources_missing or [],
            acronyms_found=acronyms_found or [],
            acronyms_expanded=acronyms_expanded or {},
            memory_context_used=memory_context_used,
            latency_total_ms=latency_total_ms,
            latency_retrieval_ms=latency_retrieval_ms,
            latency_rerank_l1_ms=latency_rerank_l1_ms,
            latency_rerank_l2_ms=latency_rerank_l2_ms,
            latency_llm_ms=latency_llm_ms,
            status=status,
            tools_suggested=tools_suggested or [],
            teach_doc_id=teach_doc_id,
            gap_detected=gap_detected
        )
        
        session.add_interaction(interaction)
        self._persist_session(session)
        self._update_index(session)
        
        logger.debug(f"[ConvLog] Interaction: {interaction.id} query='{query_original[:40]}...'")
        
        return interaction
    
    def add_feedback(
        self,
        session_id: str,
        interaction_id: str,
        feedback: str  # "positive" | "negative"
    ) -> bool:
        """Aggiunge feedback a un'interazione"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        if session.add_feedback(interaction_id, feedback):
            self._persist_session(session)
            logger.debug(f"[ConvLog] Feedback: {interaction_id} = {feedback}")
            return True
        return False
    
    def mark_gap_reported(self, session_id: str, interaction_id: str) -> bool:
        """Marca che l'utente ha segnalato la lacuna"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        for i in session.interactions:
            if i.id == interaction_id:
                i.gap_reported = True
                self._persist_session(session)
                return True
        return False
    
    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════
    
    def _get_session_path(self, session_id: str) -> Path:
        """Path file sessione"""
        return self.persist_dir / f"{session_id}.json"
    
    def _persist_session(self, session: Session):
        """Salva sessione su disco"""
        path = self._get_session_path(session.id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[ConvLog] Persist error: {e}")
    
    def _load_session(self, session_id: str) -> Optional[Session]:
        """Carica sessione da disco"""
        path = self._get_session_path(session_id)
        if not path.exists():
            return None
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                return Session.from_dict(json.load(f))
        except Exception as e:
            logger.error(f"[ConvLog] Load error: {e}")
            return None
    
    def _update_index(self, session: Session):
        """Aggiorna indice giornaliero"""
        today = datetime.now().strftime("%Y-%m-%d")
        index_path = self.index_dir / f"index_{today}.json"
        
        # Carica indice esistente
        index = []
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except:
                pass
        
        # Aggiungi/aggiorna entry
        entry = {
            "session_id": session.id,
            "user_id": session.user_id,
            "user_role": session.user_role,
            "started_at": session.started_at,
            "interactions": session.total_interactions
        }
        
        # Aggiorna se esiste, altrimenti aggiungi
        found = False
        for i, e in enumerate(index):
            if e["session_id"] == session.id:
                index[i] = entry
                found = True
                break
        if not found:
            index.append(entry)
        
        # Salva
        try:
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[ConvLog] Index update error: {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # QUERY & ANALYTICS
    # ═══════════════════════════════════════════════════════════════
    
    def get_user_sessions(
        self,
        user_id: str,
        days: int = 30,
        limit: int = 50
    ) -> List[Session]:
        """Ottiene sessioni di un utente"""
        sessions = []
        cutoff = datetime.now() - timedelta(days=days)
        
        for session_file in sorted(self.persist_dir.glob("sess_*.json"), reverse=True):
            if len(sessions) >= limit:
                break
            
            try:
                session = self._load_session(session_file.stem)
                if session and session.user_id == user_id:
                    start = datetime.fromisoformat(session.started_at)
                    if start >= cutoff:
                        sessions.append(session)
            except:
                continue
        
        return sessions
    
    def get_all_sessions(
        self,
        days: int = 30,
        limit: int = 100
    ) -> List[Session]:
        """Ottiene tutte le sessioni (per admin)"""
        sessions = []
        cutoff = datetime.now() - timedelta(days=days)
        
        for session_file in sorted(self.persist_dir.glob("sess_*.json"), reverse=True):
            if len(sessions) >= limit:
                break
            
            try:
                session = self._load_session(session_file.stem)
                if session:
                    start = datetime.fromisoformat(session.started_at)
                    if start >= cutoff:
                        sessions.append(session)
            except:
                continue
        
        return sessions
    
    def get_sessions_for_date(self, date_str: str) -> List[Session]:
        """Ottiene sessioni per data (YYYY-MM-DD)"""
        index_path = self.index_dir / f"index_{date_str}.json"
        if not index_path.exists():
            return []
        
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
            
            sessions = []
            for entry in index:
                session = self._load_session(entry["session_id"])
                if session:
                    sessions.append(session)
            return sessions
        except:
            return []
    
    def get_daily_stats(self, date_str: str = None) -> Dict[str, Any]:
        """Statistiche giornaliere"""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        sessions = self.get_sessions_for_date(date_str)
        
        if not sessions:
            return {
                "date": date_str,
                "total_sessions": 0,
                "total_interactions": 0,
                "unique_users": 0,
                "avg_interactions_per_session": 0,
                "avg_latency_ms": 0,
                "positive_feedback": 0,
                "negative_feedback": 0,
                "feedback_ratio": 0,
                "gaps_detected": 0,
                "gaps_reported": 0
            }
        
        total_interactions = sum(s.total_interactions for s in sessions)
        unique_users = len(set(s.user_id for s in sessions))
        
        all_latencies = []
        positive = 0
        negative = 0
        gaps_detected = 0
        gaps_reported = 0
        
        for s in sessions:
            positive += s.positive_feedback_count
            negative += s.negative_feedback_count
            for i in s.interactions:
                if i.latency_total_ms > 0:
                    all_latencies.append(i.latency_total_ms)
                if i.gap_detected:
                    gaps_detected += 1
                if i.gap_reported:
                    gaps_reported += 1
        
        avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0
        total_feedback = positive + negative
        
        return {
            "date": date_str,
            "total_sessions": len(sessions),
            "total_interactions": total_interactions,
            "unique_users": unique_users,
            "avg_interactions_per_session": round(total_interactions / len(sessions), 1) if sessions else 0,
            "avg_latency_ms": round(avg_latency),
            "positive_feedback": positive,
            "negative_feedback": negative,
            "feedback_ratio": round(positive / total_feedback, 3) if total_feedback else 0,
            "gaps_detected": gaps_detected,
            "gaps_reported": gaps_reported
        }
    
    def export_sessions_csv(
        self,
        output_path: str,
        date_from: str = None,
        date_to: str = None,
        user_id: str = None
    ) -> int:
        """
        Esporta sessioni in CSV.
        
        Returns:
            Numero di righe esportate
        """
        import csv
        
        # Assicura directory esista
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Raccogli sessioni
        sessions = []
        
        if date_from and date_to:
            current = datetime.strptime(date_from, "%Y-%m-%d")
            end = datetime.strptime(date_to, "%Y-%m-%d")
            while current <= end:
                sessions.extend(self.get_sessions_for_date(current.strftime("%Y-%m-%d")))
                current += timedelta(days=1)
        else:
            # Ultimi 30 giorni
            for days_ago in range(30):
                date_str = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
                sessions.extend(self.get_sessions_for_date(date_str))
        
        # Filtra per utente
        if user_id:
            sessions = [s for s in sessions if user_id.lower() in s.user_id.lower()]
        
        # Scrivi CSV
        rows = 0
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                "session_id", "user_id", "user_role", "started_at",
                "interaction_id", "timestamp", "query", "response_preview",
                "sources_cited", "latency_ms", "feedback", "status"
            ])
            
            for session in sessions:
                for interaction in session.interactions:
                    response_preview = interaction.response_text[:200]
                    if len(interaction.response_text) > 200:
                        response_preview += "..."
                    
                    writer.writerow([
                        session.id,
                        session.user_id,
                        session.user_role,
                        session.started_at,
                        interaction.id,
                        interaction.timestamp,
                        interaction.query_original,
                        response_preview,
                        ", ".join(interaction.sources_cited),
                        interaction.latency_total_ms,
                        interaction.feedback or "",
                        interaction.status
                    ])
                    rows += 1
        
        logger.info(f"[ConvLog] Exported {rows} rows to {output_path}")
        return rows
    
    def cleanup_old_sessions(self) -> int:
        """Rimuove sessioni più vecchie di retention_days"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        removed = 0
        
        for session_file in self.persist_dir.glob("sess_*.json"):
            try:
                session = self._load_session(session_file.stem)
                if session:
                    start = datetime.fromisoformat(session.started_at)
                    if start < cutoff:
                        session_file.unlink()
                        removed += 1
            except:
                continue
        
        # Pulisci anche indici vecchi
        for index_file in self.index_dir.glob("index_*.json"):
            try:
                date_str = index_file.stem.replace("index_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    index_file.unlink()
            except:
                continue
        
        if removed > 0:
            logger.info(f"[ConvLog] Cleaned up {removed} old sessions")
        
        return removed


# ═══════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════

_logger: Optional[ConversationLogger] = None


def get_conversation_logger() -> ConversationLogger:
    """Ottiene istanza singleton ConversationLogger"""
    global _logger
    if _logger is None:
        _logger = ConversationLogger()
    return _logger


# ═══════════════════════════════════════════════════════════════
# TEST STANDALONE
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile
    import shutil
    
    logging.basicConfig(level=logging.DEBUG)
    
    temp_dir = tempfile.mkdtemp()
    
    print("=== TEST CONVERSATION LOGGER ===\n")
    
    conv_logger = ConversationLogger(
        persist_dir=f"{temp_dir}/conversations",
        index_dir=f"{temp_dir}/index"
    )
    
    # Test 1: Crea sessione
    print("Test 1: Crea sessione")
    session = conv_logger.start_session("mario", "engineer", {"browser": "Chrome"})
    print(f"  Session ID: {session.id}")
    print(f"  User: {session.user_id}")
    print()
    
    # Test 2: Log interazioni
    print("Test 2: Log interazioni")
    int1 = conv_logger.log_interaction(
        session_id=session.id,
        query_original="Come gestire le NC?",
        response_text="La gestione delle NC prevede diversi passaggi...",
        sources_cited=["PS-08_01", "IL-08_02"],
        latency_total_ms=2500,
        status=InteractionStatus.SUCCESS.value
    )
    print(f"  Interaction 1: {int1.id}")
    
    int2 = conv_logger.log_interaction(
        session_id=session.id,
        query_original="E per le AC?",
        response_text="Le Azioni Correttive sono...",
        sources_cited=["PS-08_03"],
        latency_total_ms=1800
    )
    print(f"  Interaction 2: {int2.id}")
    print()
    
    # Test 3: Feedback
    print("Test 3: Feedback")
    conv_logger.add_feedback(session.id, int1.id, "positive")
    conv_logger.add_feedback(session.id, int2.id, "negative")
    
    updated = conv_logger.get_session(session.id)
    print(f"  Positive: {updated.positive_feedback_count}")
    print(f"  Negative: {updated.negative_feedback_count}")
    print()
    
    # Test 4: Stats
    print("Test 4: Daily stats")
    stats = conv_logger.get_daily_stats()
    print(f"  Sessions: {stats['total_sessions']}")
    print(f"  Interactions: {stats['total_interactions']}")
    print(f"  Avg latency: {stats['avg_latency_ms']}ms")
    print()
    
    # Test 5: Close session
    print("Test 5: Close session")
    conv_logger.end_session(session.id)
    closed = conv_logger.get_session(session.id)
    print(f"  Duration: {closed.duration_seconds():.1f}s")
    print()
    
    # Test 6: Export CSV
    print("Test 6: Export CSV")
    csv_path = f"{temp_dir}/export.csv"
    rows = conv_logger.export_sessions_csv(csv_path)
    print(f"  Exported {rows} rows")
    print()
    
    # Cleanup
    shutil.rmtree(temp_dir)
    
    print("✅ Test completati!")

