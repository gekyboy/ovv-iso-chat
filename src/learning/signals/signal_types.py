"""
Signal Types per R08-R10
Definizione tipi di segnali impliciti tracciabili

Created: 2025-12-08
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List


class SignalType(Enum):
    """Tipi di segnali impliciti tracciabili"""
    
    # === INTERACTION SIGNALS ===
    CLICK_SOURCE = "click_source"           # Click su fonte citata
    COPY_TEXT = "copy_text"                 # Copia porzione risposta
    SCROLL_DEPTH = "scroll_depth"           # Quanto ha scrollato
    DWELL_TIME = "dwell_time"               # Tempo lettura risposta
    RE_ASK_QUERY = "re_ask"                 # Ripete query simile
    FOLLOW_UP = "follow_up"                 # Domanda follow-up
    
    # === TEACH MODE SIGNALS ===
    TEACH_COMPLETE = "teach_complete"       # Completato /teach
    TEACH_ABORT = "teach_abort"             # Abbandonato /teach
    FIELD_FOCUS_TIME = "field_focus"        # Tempo su campo specifico
    
    # === FEEDBACK IMPLICIT SIGNALS ===
    QUICK_DISMISS = "quick_dismiss"         # Chiuso subito (negativo)
    SESSION_END_GOOD = "session_good"       # Sessione terminata bene
    RETRY_DIFFERENT = "retry_different"     # Riformula query (insoddisfatto)
    
    # === GLOSSARY SIGNALS ===
    ACRONYM_EXPAND_CLICK = "acronym_click"  # Click su espansione acronimo
    DEFINITION_HOVER = "def_hover"          # Hover su definizione
    
    # === MEMORY SIGNALS ===
    MEMORY_USED = "memory_used"             # Memoria utente usata nella risposta
    MEMORY_CONFIRMED = "memory_confirmed"   # Utente conferma memoria corretta
    MEMORY_REJECTED = "memory_rejected"     # Utente rifiuta memoria


@dataclass
class ImplicitSignal:
    """Singolo segnale implicito"""
    id: str
    signal_type: SignalType
    user_id: str
    session_id: str
    timestamp: datetime
    
    # Contesto
    query_id: Optional[str] = None
    doc_id: Optional[str] = None
    content: Optional[str] = None
    
    # Valore del segnale (dipende dal tipo)
    value: Any = None  # es: dwell_time=15s, scroll_depth=0.8
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializza per JSON"""
        return {
            "id": self.id,
            "signal_type": self.signal_type.value,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "query_id": self.query_id,
            "doc_id": self.doc_id,
            "content": self.content,
            "value": self.value,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImplicitSignal":
        """Deserializza da JSON"""
        return cls(
            id=data["id"],
            signal_type=SignalType(data["signal_type"]),
            user_id=data["user_id"],
            session_id=data["session_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            query_id=data.get("query_id"),
            doc_id=data.get("doc_id"),
            content=data.get("content"),
            value=data.get("value"),
            metadata=data.get("metadata", {})
        )


# Pesi per segnali (positivi/negativi)
SIGNAL_WEIGHTS: Dict[SignalType, float] = {
    # Segnali positivi (utente soddisfatto)
    SignalType.CLICK_SOURCE: +0.3,
    SignalType.COPY_TEXT: +0.4,
    SignalType.DWELL_TIME: +0.2,  # Se > soglia
    SignalType.FOLLOW_UP: +0.2,
    SignalType.TEACH_COMPLETE: +0.5,
    SignalType.ACRONYM_EXPAND_CLICK: +0.2,
    SignalType.SESSION_END_GOOD: +0.3,
    SignalType.MEMORY_CONFIRMED: +0.5,
    SignalType.MEMORY_USED: +0.1,
    
    # Segnali negativi (insoddisfazione)
    SignalType.QUICK_DISMISS: -0.4,
    SignalType.RE_ASK_QUERY: -0.3,
    SignalType.RETRY_DIFFERENT: -0.3,
    SignalType.TEACH_ABORT: -0.4,
    SignalType.MEMORY_REJECTED: -0.5,
}


# Soglie per interpretazione segnali
SIGNAL_THRESHOLDS = {
    "dwell_time_positive": 15,      # Secondi minimo per positivo
    "dwell_time_negative": 3,       # Secondi massimo per negativo
    "scroll_depth_positive": 0.7,   # % scroll per positivo
    "quick_dismiss_threshold": 5,   # Secondi per quick dismiss
    "copy_min_length": 20,          # Caratteri minimo per copy positivo
}

