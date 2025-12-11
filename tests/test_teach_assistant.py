"""
Test per R16 - Teach Assistant
Verifica rilevamento domande su campi e gestione contesto

Run: pytest tests/test_teach_assistant.py -v
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.integration.teach_assistant import (
    TeachAssistant,
    TeachContext,
    TeachFeedbackTracker,
    FieldInfo,
    get_teach_assistant,
    get_feedback_tracker
)


@pytest.fixture
def assistant():
    """Fixture per TeachAssistant"""
    return TeachAssistant(mapping_path="config/tools_mapping.json")


@pytest.fixture
def tracker():
    """Fixture per TeachFeedbackTracker"""
    return TeachFeedbackTracker()


class TestTeachContext:
    """Test per TeachContext"""
    
    def test_context_active(self):
        """Contesto appena creato è attivo"""
        ctx = TeachContext(
            doc_id="MR-07_05",
            doc_name="Cartellino Anomalia",
            started_at=datetime.now()
        )
        assert ctx.is_active() == True
    
    def test_context_expired(self):
        """Contesto scaduto non è attivo"""
        ctx = TeachContext(
            doc_id="MR-07_05",
            doc_name="Cartellino Anomalia",
            started_at=datetime.now() - timedelta(minutes=15)
        )
        assert ctx.is_active(timeout_minutes=10) == False
    
    def test_context_custom_timeout(self):
        """Contesto con timeout custom"""
        ctx = TeachContext(
            doc_id="MR-07_05",
            doc_name="Cartellino Anomalia",
            started_at=datetime.now() - timedelta(minutes=5)
        )
        assert ctx.is_active(timeout_minutes=10) == True
        assert ctx.is_active(timeout_minutes=3) == False
    
    def test_add_field_asked(self):
        """Aggiunge campo alla lista"""
        ctx = TeachContext(
            doc_id="MR-07_05",
            doc_name="Test",
            started_at=datetime.now()
        )
        ctx.add_field_asked("Severity")
        ctx.add_field_asked("RPN")
        ctx.add_field_asked("Severity")  # Duplicato
        
        assert len(ctx.fields_asked) == 2
        assert "Severity" in ctx.fields_asked
        assert "RPN" in ctx.fields_asked


class TestFieldDetection:
    """Test per rilevamento domande su campi"""
    
    def test_detect_non_capisco(self, assistant):
        """Rileva 'non capisco il campo X'"""
        is_field, name = assistant.detect_field_question("Non capisco il campo Severity")
        assert is_field == True
        assert name is not None
        assert "severity" in name.lower()
    
    def test_detect_cosa_metto(self, assistant):
        """Rileva 'cosa metto nel campo X'"""
        is_field, name = assistant.detect_field_question("Cosa metto nel campo descrizione?")
        assert is_field == True
        assert name is not None
        assert "descrizione" in name.lower()
    
    def test_detect_come_compilo(self, assistant):
        """Rileva 'come compilo il campo X'"""
        is_field, name = assistant.detect_field_question("Come compilo il campo RPN?")
        assert is_field == True
        assert name is not None
        assert "rpn" in name.lower()
    
    def test_detect_cose_campo(self, assistant):
        """Rileva 'cos'è il campo X'"""
        is_field, name = assistant.detect_field_question("Cos'è il campo Occurrence?")
        assert is_field == True
        assert name is not None
    
    def test_detect_direct_field(self, assistant):
        """Rileva campo diretto (solo nome)"""
        is_field, name = assistant.detect_field_question("severity")
        assert is_field == True
    
    def test_detect_8d_discipline(self, assistant):
        """Rileva discipline 8D (D0, D1, etc.)"""
        is_field, name = assistant.detect_field_question("D3 contenimento")
        assert is_field == True
    
    def test_no_detect_long_query(self, assistant):
        """Non rileva query troppo lunghe"""
        long_query = "Come funziona la procedura di gestione delle non conformità secondo la ISO 9001 capitolo 10 nel contesto aziendale?"
        is_field, _ = assistant.detect_field_question(long_query)
        assert is_field == False
    
    def test_no_detect_unrelated(self, assistant):
        """Non rileva domande non sui campi"""
        is_field, _ = assistant.detect_field_question("Come funziona la ISO 9001?")
        assert is_field == False


class TestToolInfo:
    """Test per info tool"""
    
    def test_get_tool_by_exact_id(self, assistant):
        """Ottiene tool per ID esatto"""
        info = assistant.get_tool_info("MR-07_05")
        assert info is not None
        assert "Cartellino" in info.get("name", "") or "Anomalia" in info.get("name", "")
    
    def test_get_tool_by_partial_id(self, assistant):
        """Ottiene tool per ID parziale"""
        info = assistant.get_tool_info("MR-08_07")
        assert info is not None
        assert "FMEA" in info.get("name", "")
    
    def test_get_tool_not_found(self, assistant):
        """Tool non trovato ritorna None"""
        info = assistant.get_tool_info("XXXX-99_99")
        assert info is None


class TestFieldInfo:
    """Test per info campi"""
    
    def test_get_field_exact(self, assistant):
        """Ottiene campo con match esatto"""
        field = assistant.get_field_info("MR-08_07", "Severity (S)")
        if field:  # Se i campi sono definiti nel mapping
            assert "severity" in field.name.lower()
    
    def test_get_field_partial(self, assistant):
        """Ottiene campo con match parziale"""
        field = assistant.get_field_info("MR-08_07", "severity")
        if field:
            assert field.description  # Ha una descrizione
    
    def test_get_field_not_found(self, assistant):
        """Campo non trovato ritorna None"""
        field = assistant.get_field_info("MR-08_07", "CampoInesistente123")
        assert field is None
    
    def test_get_all_fields(self, assistant):
        """Ottiene tutti i campi di un tool"""
        fields = assistant.get_all_fields("MR-08_07")
        assert isinstance(fields, list)
        if fields:  # Se i campi sono definiti
            assert all(isinstance(f, FieldInfo) for f in fields)
    
    def test_field_format_explanation(self):
        """Formatta spiegazione campo"""
        field = FieldInfo(
            name="Test Field",
            description="Test description",
            tips="Test tips"
        )
        explanation = field.format_explanation()
        
        assert "Test Field" in explanation
        assert "Test description" in explanation
        assert "Test tips" in explanation


class TestFeedbackTracker:
    """Test per tracking feedback"""
    
    def test_track_single_question(self, tracker):
        """Traccia singola domanda"""
        tracker.track_field_question("MR-08_07", "Severity", "user_1")
        assert tracker.get_confusion_count("MR-08_07", "severity") == 1
    
    def test_track_multiple_questions(self, tracker):
        """Traccia domande multiple stesso campo"""
        tracker.track_field_question("MR-08_07", "Severity", "user_1")
        tracker.track_field_question("MR-08_07", "Severity", "user_2")
        tracker.track_field_question("MR-08_07", "Severity", "user_3")
        assert tracker.get_confusion_count("MR-08_07", "severity") == 3
    
    def test_track_different_fields(self, tracker):
        """Traccia domande su campi diversi"""
        tracker.track_field_question("MR-08_07", "Severity", "user_1")
        tracker.track_field_question("MR-08_07", "RPN", "user_2")
        tracker.track_field_question("MR-07_05", "Descrizione", "user_3")
        
        assert tracker.get_confusion_count("MR-08_07", "severity") == 1
        assert tracker.get_confusion_count("MR-08_07", "rpn") == 1
        assert tracker.get_confusion_count("MR-07_05", "descrizione") == 1
    
    def test_should_notify_below_threshold(self, tracker):
        """Non notifica sotto soglia"""
        tracker.track_field_question("MR-08_07", "RPN", "user_1")
        tracker.track_field_question("MR-08_07", "RPN", "user_2")
        assert tracker.should_notify_admin("MR-08_07", "RPN", threshold=3) == False
    
    def test_should_notify_at_threshold(self, tracker):
        """Notifica a soglia raggiunta"""
        tracker.track_field_question("MR-08_07", "RPN", "user_1")
        tracker.track_field_question("MR-08_07", "RPN", "user_2")
        tracker.track_field_question("MR-08_07", "RPN", "user_3")
        assert tracker.should_notify_admin("MR-08_07", "RPN", threshold=3) == True
    
    def test_get_stats_empty(self, tracker):
        """Statistiche vuote"""
        stats = tracker.get_stats()
        assert stats["total_questions"] == 0
        assert stats["by_document"] == {}
        assert stats["top_confused_fields"] == []
    
    def test_get_stats_with_data(self, tracker):
        """Statistiche con dati"""
        tracker.track_field_question("MR-08_07", "Severity", "user_1")
        tracker.track_field_question("MR-08_07", "Severity", "user_2")
        tracker.track_field_question("MR-08_07", "RPN", "user_3")
        tracker.track_field_question("MR-07_05", "Descrizione", "user_4")
        
        stats = tracker.get_stats()
        
        assert stats["total_questions"] == 4
        assert "MR-08_07" in stats["by_document"]
        assert stats["by_document"]["MR-08_07"]["total"] == 3
        assert len(stats["top_confused_fields"]) > 0
        assert stats["top_confused_fields"][0]["field"] == "severity"  # Most confused
    
    def test_get_recent_questions(self, tracker):
        """Ottiene domande recenti"""
        tracker.track_field_question("MR-08_07", "Severity", "user_1")
        tracker.track_field_question("MR-08_07", "RPN", "user_2")
        
        recent = tracker.get_recent_questions(limit=10)
        assert len(recent) == 2
        assert recent[0]["field"] == "Severity"


class TestFormatting:
    """Test per formattazione output"""
    
    def test_format_fields_list_with_fields(self, assistant):
        """Formatta lista campi per tool con campi"""
        result = assistant.format_fields_list("MR-08_07")
        
        assert "MR-08_07" in result or "FMEA" in result
        # Se campi definiti
        if "Dettagli campi non disponibili" not in result:
            assert "📝" in result or "Campi" in result
    
    def test_format_fields_list_no_fields(self, assistant):
        """Formatta lista per tool senza campi definiti"""
        result = assistant.format_fields_list("XXXX-99_99")
        assert "non disponibili" in result.lower() or "ℹ️" in result
    
    def test_format_teach_response_with_actions(self, assistant):
        """Formatta risposta teach con azioni"""
        response, actions = assistant.format_teach_response_with_actions(
            "MR-07_05",
            "Cartellino Anomalia",
            "Questo è il testo base della risposta."
        )
        
        assert "Cartellino Anomalia" in response
        assert "MR-07_05" in response
        assert "Come compilare" in response
        assert len(actions) >= 2  # Almeno errors e example
        
        # Verifica struttura azioni
        for action in actions:
            assert "name" in action
            assert "payload" in action
            assert "label" in action


class TestSingletons:
    """Test per funzioni singleton"""
    
    def test_get_teach_assistant_singleton(self):
        """get_teach_assistant ritorna singleton"""
        a1 = get_teach_assistant()
        a2 = get_teach_assistant()
        assert a1 is a2
    
    def test_get_feedback_tracker_singleton(self):
        """get_feedback_tracker ritorna singleton"""
        t1 = get_feedback_tracker()
        t2 = get_feedback_tracker()
        assert t1 is t2


class TestIntegration:
    """Test di integrazione end-to-end"""
    
    def test_full_flow(self, assistant, tracker):
        """Flow completo: detect → get info → track"""
        # 1. Crea contesto
        ctx = TeachContext(
            doc_id="MR-08_07",
            doc_name="FMEA",
            started_at=datetime.now()
        )
        assert ctx.is_active()
        
        # 2. Utente chiede di un campo
        question = "Non capisco il campo Severity"
        is_field, field_name = assistant.detect_field_question(question)
        assert is_field == True
        
        # 3. Cerca info campo
        field_info = assistant.get_field_info(ctx.doc_id, field_name)
        # Può essere None se campi non definiti nel mapping
        
        # 4. Traccia domanda
        tracker.track_field_question(ctx.doc_id, field_name, "test_user")
        assert tracker.get_confusion_count(ctx.doc_id, field_name.lower()) >= 1
        
        # 5. Aggiorna contesto
        ctx.add_field_asked(field_name)
        assert field_name in ctx.fields_asked


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

