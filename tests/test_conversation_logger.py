"""
Test per ConversationLogger (R28)
Verifica logging conversazioni complete con sessioni e interazioni

Created: 2025-12-09
"""

import pytest
import tempfile
import shutil
import time
from pathlib import Path
from datetime import datetime

from src.analytics.collectors.conversation_logger import (
    ConversationLogger,
    Session,
    Interaction,
    InteractionStatus,
    get_conversation_logger
)


@pytest.fixture
def temp_logger():
    """Crea logger con directory temporanea"""
    temp_dir = tempfile.mkdtemp()
    logger = ConversationLogger(
        persist_dir=f"{temp_dir}/conversations",
        index_dir=f"{temp_dir}/index"
    )
    yield logger
    shutil.rmtree(temp_dir)


class TestInteraction:
    """Test per dataclass Interaction"""
    
    def test_create_interaction(self):
        """Test creazione interazione base"""
        interaction = Interaction(
            id="int_test123",
            timestamp=datetime.now().isoformat(),
            query_original="Come gestire le NC?"
        )
        
        assert interaction.id == "int_test123"
        assert interaction.query_original == "Come gestire le NC?"
        assert interaction.status == InteractionStatus.SUCCESS.value
        assert interaction.feedback is None
    
    def test_interaction_to_dict(self):
        """Test serializzazione"""
        interaction = Interaction(
            id="int_test",
            timestamp="2025-12-09T10:00:00",
            query_original="Test query",
            response_text="Test response",
            sources_cited=["PS-08_01"]
        )
        
        data = interaction.to_dict()
        
        assert data["id"] == "int_test"
        assert data["query_original"] == "Test query"
        assert data["sources_cited"] == ["PS-08_01"]
    
    def test_interaction_from_dict(self):
        """Test deserializzazione"""
        data = {
            "id": "int_test",
            "timestamp": "2025-12-09T10:00:00",
            "query_original": "Test query",
            "response_text": "Test response"
        }
        
        interaction = Interaction.from_dict(data)
        
        assert interaction.id == "int_test"
        assert interaction.query_original == "Test query"
        assert interaction.sources_cited == []  # Default


class TestSession:
    """Test per dataclass Session"""
    
    def test_create_session(self):
        """Test creazione sessione"""
        session = Session(
            id="sess_test123",
            user_id="mario",
            user_role="engineer",
            started_at=datetime.now().isoformat()
        )
        
        assert session.id == "sess_test123"
        assert session.user_id == "mario"
        assert session.total_interactions == 0
        assert session.ended_at is None
    
    def test_add_interaction(self):
        """Test aggiunta interazione"""
        session = Session(
            id="sess_test",
            user_id="mario",
            user_role="user",
            started_at=datetime.now().isoformat()
        )
        
        interaction = Interaction(
            id="int_1",
            timestamp=datetime.now().isoformat(),
            query_original="Query 1",
            latency_total_ms=2500
        )
        
        session.add_interaction(interaction)
        
        assert session.total_interactions == 1
        assert len(session.interactions) == 1
        assert session.avg_latency_ms == 2500
    
    def test_add_feedback(self):
        """Test aggiunta feedback"""
        session = Session(
            id="sess_test",
            user_id="mario",
            user_role="user",
            started_at=datetime.now().isoformat()
        )
        
        interaction = Interaction(
            id="int_1",
            timestamp=datetime.now().isoformat(),
            query_original="Query 1"
        )
        session.add_interaction(interaction)
        
        result = session.add_feedback("int_1", "positive")
        
        assert result is True
        assert session.positive_feedback_count == 1
        assert session.interactions[0].feedback == "positive"
    
    def test_close_session(self):
        """Test chiusura sessione"""
        session = Session(
            id="sess_test",
            user_id="mario",
            user_role="user",
            started_at=datetime.now().isoformat()
        )
        
        time.sleep(0.1)  # Simula durata
        session.close()
        
        assert session.ended_at is not None
        assert session.duration_seconds() > 0


class TestConversationLogger:
    """Test per ConversationLogger"""
    
    def test_start_session(self, temp_logger):
        """Test creazione sessione"""
        session = temp_logger.start_session("mario", "engineer")
        
        assert session.id.startswith("sess_")
        assert session.user_id == "mario"
        assert session.user_role == "engineer"
        assert session.total_interactions == 0
    
    def test_get_session(self, temp_logger):
        """Test recupero sessione"""
        session = temp_logger.start_session("mario", "engineer")
        
        # Da cache
        retrieved = temp_logger.get_session(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id
        
        # Non esistente
        not_found = temp_logger.get_session("sess_nonexistent")
        assert not_found is None
    
    def test_log_interaction(self, temp_logger):
        """Test log interazione"""
        session = temp_logger.start_session("mario", "engineer")
        
        interaction = temp_logger.log_interaction(
            session_id=session.id,
            query_original="Come gestire le NC?",
            response_text="La gestione delle NC prevede...",
            sources_cited=["PS-08_01"],
            latency_total_ms=2500
        )
        
        assert interaction is not None
        assert interaction.id.startswith("int_")
        assert interaction.query_original == "Come gestire le NC?"
        
        # Verifica sessione aggiornata
        updated = temp_logger.get_session(session.id)
        assert updated.total_interactions == 1
    
    def test_log_interaction_session_not_found(self, temp_logger):
        """Test log su sessione inesistente"""
        interaction = temp_logger.log_interaction(
            session_id="sess_nonexistent",
            query_original="Test",
            response_text="Test"
        )
        
        assert interaction is None
    
    def test_add_feedback(self, temp_logger):
        """Test aggiunta feedback"""
        session = temp_logger.start_session("luigi", "user")
        interaction = temp_logger.log_interaction(
            session_id=session.id,
            query_original="Test query",
            response_text="Test response"
        )
        
        result = temp_logger.add_feedback(
            session.id,
            interaction.id,
            "positive"
        )
        
        assert result is True
        
        updated = temp_logger.get_session(session.id)
        assert updated.positive_feedback_count == 1
        assert updated.interactions[0].feedback == "positive"
    
    def test_end_session(self, temp_logger):
        """Test chiusura sessione"""
        session = temp_logger.start_session("admin", "admin")
        temp_logger.log_interaction(
            session_id=session.id,
            query_original="Query 1",
            response_text="Response 1"
        )
        
        result = temp_logger.end_session(session.id)
        assert result is True
        
        closed = temp_logger.get_session(session.id)
        assert closed.ended_at is not None
    
    def test_persistence(self, temp_logger):
        """Test persistenza su disco"""
        session = temp_logger.start_session("mario", "engineer")
        temp_logger.log_interaction(
            session_id=session.id,
            query_original="Query persistita",
            response_text="Response persistita"
        )
        
        # Verifica file creato
        session_file = temp_logger.persist_dir / f"{session.id}.json"
        assert session_file.exists()
        
        # Ricarica da disco
        temp_logger._active_sessions.clear()
        reloaded = temp_logger.get_session(session.id)
        
        assert reloaded is not None
        assert reloaded.total_interactions == 1
        assert reloaded.interactions[0].query_original == "Query persistita"
    
    def test_get_daily_stats(self, temp_logger):
        """Test statistiche giornaliere"""
        # Crea alcune sessioni
        for user in ["mario", "luigi", "mario"]:
            session = temp_logger.start_session(user, "user")
            temp_logger.log_interaction(
                session_id=session.id,
                query_original=f"Query da {user}",
                response_text="Response",
                latency_total_ms=1000
            )
        
        stats = temp_logger.get_daily_stats()
        
        assert stats["total_sessions"] == 3
        assert stats["unique_users"] == 2
        assert stats["total_interactions"] == 3
        assert stats["avg_latency_ms"] == 1000
    
    def test_get_user_sessions(self, temp_logger):
        """Test recupero sessioni per utente"""
        # Mario: 2 sessioni
        for _ in range(2):
            session = temp_logger.start_session("mario", "engineer")
            temp_logger.log_interaction(
                session_id=session.id,
                query_original="Query Mario",
                response_text="Response"
            )
        
        # Luigi: 1 sessione
        session = temp_logger.start_session("luigi", "user")
        temp_logger.log_interaction(
            session_id=session.id,
            query_original="Query Luigi",
            response_text="Response"
        )
        
        mario_sessions = temp_logger.get_user_sessions("mario")
        luigi_sessions = temp_logger.get_user_sessions("luigi")
        
        assert len(mario_sessions) == 2
        assert len(luigi_sessions) == 1
    
    def test_export_csv(self, temp_logger):
        """Test export CSV"""
        session = temp_logger.start_session("test", "user")
        temp_logger.log_interaction(
            session_id=session.id,
            query_original="Export test",
            response_text="Test response",
            sources_cited=["PS-01_01"]
        )
        
        output_path = f"{temp_logger.persist_dir}/export_test.csv"
        rows = temp_logger.export_sessions_csv(output_path)
        
        assert rows == 1
        assert Path(output_path).exists()
        
        # Verifica contenuto
        with open(output_path, "r") as f:
            content = f.read()
            assert "Export test" in content
            assert "PS-01_01" in content
    
    def test_mark_gap_reported(self, temp_logger):
        """Test marcatura gap segnalato"""
        session = temp_logger.start_session("mario", "user")
        interaction = temp_logger.log_interaction(
            session_id=session.id,
            query_original="Cos'è XYZ?",
            response_text="Non ho trovato...",
            gap_detected=True
        )
        
        result = temp_logger.mark_gap_reported(session.id, interaction.id)
        
        assert result is True
        
        updated = temp_logger.get_session(session.id)
        assert updated.interactions[0].gap_reported is True


class TestInteractionStatus:
    """Test per enum InteractionStatus"""
    
    def test_status_values(self):
        """Test valori status"""
        assert InteractionStatus.SUCCESS.value == "success"
        assert InteractionStatus.NO_RESULTS.value == "no_results"
        assert InteractionStatus.ERROR.value == "error"
        assert InteractionStatus.COMMAND.value == "command"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

