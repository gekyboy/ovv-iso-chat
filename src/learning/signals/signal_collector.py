"""
Signal Collector per R08-R10
Raccoglie segnali impliciti dalle interazioni utente

Created: 2025-12-08

Features:
- Buffer in memoria con auto-flush
- Persistenza JSON
- Session tracking
- Aggregazione per calcolo score
"""

import logging
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

from .signal_types import (
    SignalType, 
    ImplicitSignal, 
    SIGNAL_WEIGHTS,
    SIGNAL_THRESHOLDS
)

logger = logging.getLogger(__name__)


class SignalCollector:
    """
    Raccoglie segnali impliciti dalle interazioni utente.
    
    Integrazione:
    - Chainlit: eventi UI (click, copy, scroll)
    - RAG Pipeline: eventi query
    - Session: tracking attività
    
    Example:
        >>> collector = SignalCollector()
        >>> collector.track_click_source("user_1", "sess_1", "PS-06_01", "q_123")
        >>> score = collector.calculate_implicit_score("user_1", "q_123")
    """
    
    def __init__(
        self,
        persist_path: str = "data/persist/learning/signals.json",
        buffer_size: int = 100,
        flush_interval_sec: int = 60,
        retention_days: int = 30
    ):
        """
        Inizializza collector.
        
        Args:
            persist_path: Path file persistenza
            buffer_size: Dimensione buffer prima di flush
            flush_interval_sec: Intervallo flush automatico
            retention_days: Giorni retention dati
        """
        self.persist_path = Path(persist_path)
        self.buffer_size = buffer_size
        self.flush_interval = timedelta(seconds=flush_interval_sec)
        self.retention_days = retention_days
        
        # Buffer in memoria
        self._buffer: List[ImplicitSignal] = []
        self._last_flush = datetime.now()
        
        # Session tracking
        self._sessions: Dict[str, Dict[str, Any]] = {}
        
        # Cache per query correnti
        self._query_start_times: Dict[str, datetime] = {}
        
        # Crea directory
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"SignalCollector: buffer={buffer_size}, retention={retention_days}d")
    
    # ═══════════════════════════════════════════════════════════════
    # CORE TRACKING
    # ═══════════════════════════════════════════════════════════════
    
    def track(
        self,
        signal_type: SignalType,
        user_id: str,
        session_id: str,
        value: Any = None,
        query_id: str = None,
        doc_id: str = None,
        content: str = None,
        metadata: Dict[str, Any] = None
    ) -> ImplicitSignal:
        """
        Registra un segnale implicito.
        
        Args:
            signal_type: Tipo di segnale
            user_id: ID utente
            session_id: ID sessione
            value: Valore del segnale (es: secondi, percentuale)
            query_id: ID query associata
            doc_id: ID documento associato
            content: Contenuto (es: testo copiato)
            metadata: Dati aggiuntivi
        
        Returns:
            ImplicitSignal registrato
        """
        signal = ImplicitSignal(
            id=f"sig_{uuid.uuid4().hex[:12]}",
            signal_type=signal_type,
            user_id=user_id,
            session_id=session_id,
            timestamp=datetime.now(),
            query_id=query_id,
            doc_id=doc_id,
            content=content[:500] if content else None,  # Limita lunghezza
            value=value,
            metadata=metadata or {}
        )
        
        self._buffer.append(signal)
        
        # Aggiorna session tracking
        if session_id in self._sessions:
            self._sessions[session_id]["signals"].append(signal.id)
            self._sessions[session_id]["last_activity"] = datetime.now()
        
        # Auto-flush se necessario
        if len(self._buffer) >= self.buffer_size or \
           datetime.now() - self._last_flush > self.flush_interval:
            self._flush()
        
        logger.debug(f"[Learning] Signal: {signal_type.value} user={user_id}")
        
        return signal
    
    # ═══════════════════════════════════════════════════════════════
    # SHORTCUT METHODS
    # ═══════════════════════════════════════════════════════════════
    
    def track_click_source(
        self,
        user_id: str,
        session_id: str,
        doc_id: str,
        query_id: str = None
    ) -> ImplicitSignal:
        """Utente ha cliccato su fonte citata"""
        return self.track(
            SignalType.CLICK_SOURCE,
            user_id, session_id,
            doc_id=doc_id,
            query_id=query_id
        )
    
    def track_copy_text(
        self,
        user_id: str,
        session_id: str,
        text: str,
        query_id: str = None
    ) -> Optional[ImplicitSignal]:
        """Utente ha copiato testo dalla risposta"""
        # Ignora copie troppo corte
        if len(text) < SIGNAL_THRESHOLDS["copy_min_length"]:
            return None
        
        return self.track(
            SignalType.COPY_TEXT,
            user_id, session_id,
            content=text,
            query_id=query_id,
            value=len(text)
        )
    
    def track_dwell_time(
        self,
        user_id: str,
        session_id: str,
        seconds: float,
        query_id: str = None
    ) -> ImplicitSignal:
        """Tempo di lettura risposta"""
        return self.track(
            SignalType.DWELL_TIME,
            user_id, session_id,
            value=seconds,
            query_id=query_id
        )
    
    def track_scroll_depth(
        self,
        user_id: str,
        session_id: str,
        depth: float,
        query_id: str = None
    ) -> ImplicitSignal:
        """Profondità scroll (0-1)"""
        return self.track(
            SignalType.SCROLL_DEPTH,
            user_id, session_id,
            value=depth,
            query_id=query_id
        )
    
    def track_re_ask(
        self,
        user_id: str,
        session_id: str,
        original_query: str,
        new_query: str
    ) -> ImplicitSignal:
        """Utente ha riformulato query"""
        return self.track(
            SignalType.RE_ASK_QUERY,
            user_id, session_id,
            content=f"{original_query} → {new_query}",
            metadata={"original": original_query, "new": new_query}
        )
    
    def track_follow_up(
        self,
        user_id: str,
        session_id: str,
        query_id: str,
        follow_up_query: str
    ) -> ImplicitSignal:
        """Domanda follow-up (segnale positivo)"""
        return self.track(
            SignalType.FOLLOW_UP,
            user_id, session_id,
            query_id=query_id,
            content=follow_up_query
        )
    
    def track_quick_dismiss(
        self,
        user_id: str,
        session_id: str,
        query_id: str,
        seconds: float
    ) -> Optional[ImplicitSignal]:
        """Risposta chiusa rapidamente"""
        threshold = SIGNAL_THRESHOLDS["quick_dismiss_threshold"]
        if seconds < threshold:
            return self.track(
                SignalType.QUICK_DISMISS,
                user_id, session_id,
                value=seconds,
                query_id=query_id
            )
        return None
    
    def track_teach_complete(
        self,
        user_id: str,
        session_id: str,
        doc_id: str,
        duration_sec: float = None
    ) -> ImplicitSignal:
        """Completato modalità /teach"""
        return self.track(
            SignalType.TEACH_COMPLETE,
            user_id, session_id,
            doc_id=doc_id,
            value=duration_sec
        )
    
    def track_teach_abort(
        self,
        user_id: str,
        session_id: str,
        doc_id: str,
        reason: str = None
    ) -> ImplicitSignal:
        """Abbandonato /teach"""
        return self.track(
            SignalType.TEACH_ABORT,
            user_id, session_id,
            doc_id=doc_id,
            content=reason
        )
    
    def track_memory_used(
        self,
        user_id: str,
        session_id: str,
        memory_id: str,
        query_id: str
    ) -> ImplicitSignal:
        """Memoria utente utilizzata nella risposta"""
        return self.track(
            SignalType.MEMORY_USED,
            user_id, session_id,
            query_id=query_id,
            metadata={"memory_id": memory_id}
        )
    
    # ═══════════════════════════════════════════════════════════════
    # SESSION MANAGEMENT
    # ═══════════════════════════════════════════════════════════════
    
    def start_session(self, user_id: str, session_id: str):
        """Inizia tracking sessione"""
        self._sessions[session_id] = {
            "user_id": user_id,
            "start": datetime.now(),
            "last_activity": datetime.now(),
            "queries": [],
            "signals": []
        }
        logger.debug(f"[Learning] Session started: {session_id}")
    
    def end_session(self, session_id: str, was_positive: bool = True):
        """Termina sessione"""
        if session_id not in self._sessions:
            return
        
        session = self._sessions[session_id]
        duration = (datetime.now() - session["start"]).total_seconds()
        
        signal_type = SignalType.SESSION_END_GOOD if was_positive else SignalType.QUICK_DISMISS
        
        self.track(
            signal_type,
            session["user_id"],
            session_id,
            value=duration,
            metadata={
                "query_count": len(session["queries"]),
                "signal_count": len(session["signals"])
            }
        )
        
        del self._sessions[session_id]
        logger.debug(f"[Learning] Session ended: {session_id} ({duration:.0f}s)")
    
    def start_query(self, query_id: str):
        """Registra inizio query per calcolo dwell time"""
        self._query_start_times[query_id] = datetime.now()
    
    def end_query(
        self,
        user_id: str,
        session_id: str,
        query_id: str
    ) -> Optional[float]:
        """
        Registra fine query e calcola dwell time.
        
        Returns:
            Dwell time in secondi o None
        """
        if query_id not in self._query_start_times:
            return None
        
        start = self._query_start_times.pop(query_id)
        dwell_time = (datetime.now() - start).total_seconds()
        
        self.track_dwell_time(user_id, session_id, dwell_time, query_id)
        
        # Check quick dismiss
        if dwell_time < SIGNAL_THRESHOLDS["quick_dismiss_threshold"]:
            self.track_quick_dismiss(user_id, session_id, query_id, dwell_time)
        
        return dwell_time
    
    # ═══════════════════════════════════════════════════════════════
    # QUERY & AGGREGATION
    # ═══════════════════════════════════════════════════════════════
    
    def get_user_signals(
        self,
        user_id: str,
        signal_types: List[SignalType] = None,
        days: int = None
    ) -> List[ImplicitSignal]:
        """
        Ottiene segnali per utente.
        
        Args:
            user_id: ID utente
            signal_types: Filtra per tipi (opzionale)
            days: Ultimi N giorni (default: retention_days)
        """
        days = days or self.retention_days
        
        # Combina buffer + persistiti
        all_signals = self._buffer + self._load_signals()
        
        cutoff = datetime.now() - timedelta(days=days)
        
        filtered = [
            s for s in all_signals
            if s.user_id == user_id and s.timestamp >= cutoff
        ]
        
        if signal_types:
            filtered = [s for s in filtered if s.signal_type in signal_types]
        
        return filtered
    
    def get_query_signals(
        self,
        query_id: str
    ) -> List[ImplicitSignal]:
        """Ottiene tutti i segnali per una query specifica"""
        all_signals = self._buffer + self._load_signals()
        return [s for s in all_signals if s.query_id == query_id]
    
    def calculate_implicit_score(
        self,
        user_id: str,
        query_id: str
    ) -> float:
        """
        Calcola score implicito per query basato su segnali.
        
        Returns:
            Score da -1 (molto negativo) a +1 (molto positivo)
        """
        signals = [
            s for s in self._buffer + self._load_signals()
            if s.user_id == user_id and s.query_id == query_id
        ]
        
        if not signals:
            return 0.0
        
        score = 0.0
        
        for signal in signals:
            weight = SIGNAL_WEIGHTS.get(signal.signal_type, 0)
            
            # Modulazione basata su valore
            if signal.signal_type == SignalType.DWELL_TIME and signal.value:
                # Più tempo = più positivo (fino a 60 sec)
                if signal.value >= SIGNAL_THRESHOLDS["dwell_time_positive"]:
                    weight *= min(1.0, signal.value / 60)
                elif signal.value <= SIGNAL_THRESHOLDS["dwell_time_negative"]:
                    weight = -0.3  # Negativo se troppo breve
                else:
                    weight = 0  # Neutro
            
            elif signal.signal_type == SignalType.SCROLL_DEPTH and signal.value:
                # Più scroll = più positivo
                weight *= signal.value
            
            elif signal.signal_type == SignalType.COPY_TEXT and signal.value:
                # Copia più lunga = più positivo
                weight *= min(1.0, signal.value / 200)
            
            score += weight
        
        # Normalizza a [-1, 1]
        return max(-1.0, min(1.0, score))
    
    def get_stats(self, user_id: str = None) -> Dict[str, Any]:
        """
        Statistiche sui segnali raccolti.
        
        Args:
            user_id: Filtra per utente (opzionale)
        """
        all_signals = self._buffer + self._load_signals()
        
        if user_id:
            all_signals = [s for s in all_signals if s.user_id == user_id]
        
        if not all_signals:
            return {"total": 0, "by_type": {}}
        
        # Conta per tipo
        by_type = defaultdict(int)
        for s in all_signals:
            by_type[s.signal_type.value] += 1
        
        # Utenti unici
        unique_users = len(set(s.user_id for s in all_signals))
        
        # Calcola score medio per segnali positivi/negativi
        positive = sum(1 for s in all_signals if SIGNAL_WEIGHTS.get(s.signal_type, 0) > 0)
        negative = sum(1 for s in all_signals if SIGNAL_WEIGHTS.get(s.signal_type, 0) < 0)
        
        return {
            "total": len(all_signals),
            "by_type": dict(by_type),
            "unique_users": unique_users,
            "positive_signals": positive,
            "negative_signals": negative,
            "positive_ratio": positive / len(all_signals) if all_signals else 0,
            "active_sessions": len(self._sessions)
        }
    
    # ═══════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════
    
    def _flush(self):
        """Flush buffer su disco"""
        if not self._buffer:
            return
        
        existing = self._load_signals()
        existing.extend(self._buffer)
        
        # Mantieni solo dati recenti
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        existing = [s for s in existing if s.timestamp >= cutoff]
        
        self._save_signals(existing)
        self._buffer.clear()
        self._last_flush = datetime.now()
        
        logger.debug(f"[Learning] Flushed {len(existing)} signals")
    
    def _load_signals(self) -> List[ImplicitSignal]:
        """Carica segnali da file"""
        if not self.persist_path.exists():
            return []
        
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [ImplicitSignal.from_dict(d) for d in data]
        except Exception as e:
            logger.error(f"Errore caricamento segnali: {e}")
            return []
    
    def _save_signals(self, signals: List[ImplicitSignal]):
        """Salva segnali su file"""
        try:
            data = [s.to_dict() for s in signals]
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Errore salvataggio segnali: {e}")
    
    def force_flush(self):
        """Forza flush immediato"""
        self._flush()


# Singleton
_collector: Optional[SignalCollector] = None


def get_signal_collector() -> SignalCollector:
    """Ottiene istanza singleton SignalCollector"""
    global _collector
    if _collector is None:
        _collector = SignalCollector()
    return _collector


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    
    print("=== TEST SIGNAL COLLECTOR ===\n")
    
    collector = SignalCollector(persist_path=f"{temp_dir}/signals.json")
    
    # Test 1: Session
    print("Test 1: Session tracking")
    collector.start_session("mario", "sess_1")
    print(f"  Active sessions: {len(collector._sessions)}")
    
    # Test 2: Track signals
    print("Test 2: Track signals")
    collector.start_query("q_001")
    collector.track_click_source("mario", "sess_1", "PS-06_01", "q_001")
    collector.track_copy_text("mario", "sess_1", "Questo è un testo copiato abbastanza lungo", "q_001")
    
    import time
    time.sleep(0.1)  # Simula lettura
    
    dwell = collector.end_query("mario", "sess_1", "q_001")
    print(f"  Dwell time: {dwell:.2f}s")
    print(f"  Buffer size: {len(collector._buffer)}")
    
    # Test 3: Calculate score
    print("Test 3: Calculate score")
    score = collector.calculate_implicit_score("mario", "q_001")
    print(f"  Implicit score: {score:.2f}")
    
    # Test 4: Stats
    print("Test 4: Stats")
    stats = collector.get_stats()
    print(f"  Total signals: {stats['total']}")
    print(f"  By type: {stats['by_type']}")
    
    # Test 5: End session
    print("Test 5: End session")
    collector.end_session("sess_1", was_positive=True)
    print(f"  Active sessions: {len(collector._sessions)}")
    
    # Cleanup
    shutil.rmtree(temp_dir)
    
    print("\n✅ Test completati!")

