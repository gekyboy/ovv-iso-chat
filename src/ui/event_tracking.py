"""
Event Tracking for Consensus Learning
Tracking eventi DOM impliciti (click, copy, scroll, dwell) per apprendimento consenso
"""

from typing import Dict, Any, Optional
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class EventTracker:
    """
    Tracker per eventi impliciti dell'utente.
    Raccoglie segnali per consensus learning.
    """

    def __init__(self):
        self.events = []
        self.session_start = time.time()

    def track_event(self, event_type: str, event_data: Dict[str, Any], user_data: Dict[str, Any]):
        """
        Registra un evento utente

        Args:
            event_type: Tipo evento (click_source, copy_text, scroll, dwell)
            event_data: Dati specifici dell'evento
            user_data: Dati utente dalla sessione
        """
        try:
            event = {
                "type": event_type,
                "timestamp": datetime.now().isoformat(),
                "user_id": user_data.get("id"),
                "username": user_data.get("username"),
                "session_time": time.time() - self.session_start,
                "data": event_data
            }

            self.events.append(event)

            # Log per debug
            logger.info(f"Event tracked: {event_type} for user {user_data.get('username')}")

            # TODO: Integrazione con consensus learning
            # self._update_consensus_signals(event)

        except Exception as e:
            logger.error(f"Error tracking event {event_type}: {e}")

    def track_source_click(self, source_data: Dict[str, Any], user_data: Dict[str, Any]):
        """
        Track click su fonte

        Args:
            source_data: Dati della fonte cliccata
            user_data: Dati utente
        """
        event_data = {
            "source_id": source_data.get("doc_id"),
            "source_title": source_data.get("title"),
            "action": "pdf_open" if source_data.get("pdf_path") else "preview_expand"
        }
        self.track_event("click_source", event_data, user_data)

    def track_text_copy(self, text: str, context: str, user_data: Dict[str, Any]):
        """
        Track copia testo

        Args:
            text: Testo copiato
            context: Contesto (es. "response", "source")
            user_data: Dati utente
        """
        event_data = {
            "text_length": len(text),
            "context": context,
            "text_preview": text[:100] + "..." if len(text) > 100 else text
        }
        self.track_event("copy_text", event_data, user_data)

    def track_scroll(self, scroll_position: float, content_type: str, user_data: Dict[str, Any]):
        """
        Track scroll nel contenuto

        Args:
            scroll_position: Posizione scroll (0-100)
            content_type: Tipo contenuto ("chat", "source", "pdf")
            user_data: Dati utente
        """
        event_data = {
            "scroll_position": scroll_position,
            "content_type": content_type
        }
        self.track_event("scroll", event_data, user_data)

    def track_dwell_time(self, element_id: str, dwell_seconds: float, user_data: Dict[str, Any]):
        """
        Track tempo di permanenza su elemento

        Args:
            element_id: ID elemento (es. message_id, source_id)
            dwell_seconds: Tempo in secondi
            user_data: Dati utente
        """
        event_data = {
            "element_id": element_id,
            "dwell_seconds": dwell_seconds,
            "dwell_minutes": dwell_seconds / 60
        }
        self.track_event("dwell_time", event_data, user_data)

    def get_session_events(self) -> list:
        """
        Ottiene eventi della sessione corrente

        Returns:
            Lista eventi
        """
        return self.events.copy()

    def get_consensus_signals(self) -> Dict[str, Any]:
        """
        Estrae segnali consenso dalla sessione corrente

        Returns:
            Dict con pattern consenso e strength
        """
        signals = {}

        try:
            # Analizza pattern negli eventi
            source_clicks = [e for e in self.events if e["type"] == "click_source"]
            text_copies = [e for e in self.events if e["type"] == "copy_text"]
            dwells = [e for e in self.events if e["type"] == "dwell_time"]

            # Pattern: click su fonti specifiche
            if source_clicks:
                source_freq = {}
                for click in source_clicks:
                    source_id = click["data"].get("source_id")
                    if source_id:
                        source_freq[source_id] = source_freq.get(source_id, 0) + 1

                # Trova fonti cliccate frequentemente
                for source_id, count in source_freq.items():
                    if count >= 3:  # Cliccate almeno 3 volte
                        signals[f"frequent_click_{source_id}"] = {
                            "pattern": "click_su_fonte",
                            "strength": min(count / 10, 1.0),  # Max 1.0
                            "occurrences": count,
                            "source_id": source_id
                        }

            # Pattern: dwell time lungo
            if dwells:
                long_dwells = [d for d in dwells if d["data"]["dwell_seconds"] > 30]  # > 30 secondi
                if long_dwells:
                    signals["long_dwell_time"] = {
                        "pattern": "dwell_time_lungo",
                        "strength": min(len(long_dwells) / 5, 1.0),
                        "occurrences": len(long_dwells),
                        "avg_dwell": sum(d["data"]["dwell_seconds"] for d in long_dwells) / len(long_dwells)
                    }

            # Pattern: copia testo frequente
            if text_copies:
                signals["frequent_copy"] = {
                    "pattern": "copia_testo",
                    "strength": min(len(text_copies) / 5, 1.0),
                    "occurrences": len(text_copies)
                }

        except Exception as e:
            logger.error(f"Error extracting consensus signals: {e}")

        return signals

    def _update_consensus_signals(self, event: Dict[str, Any]):
        """
        Aggiorna segnali consenso con nuovo evento
        TODO: Implementare persistenza e aggregazione cross-sessione
        """
        # Per ora solo logging, poi implementare storage
        logger.debug(f"Consensus signal update: {event['type']}")


# Singleton instance per sessione
_event_tracker = None

def get_event_tracker() -> EventTracker:
    """Ottiene istanza singleton dell'EventTracker"""
    global _event_tracker
    if _event_tracker is None:
        _event_tracker = EventTracker()
    return _event_tracker

def reset_event_tracker():
    """Reset tracker per nuova sessione"""
    global _event_tracker
    _event_tracker = EventTracker()
