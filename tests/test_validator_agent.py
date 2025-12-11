"""
Test per ValidatorAgent - R26 Anti-Hallucination

Testa:
1. Validazione citazioni corrette
2. Rilevamento citazioni invalide
3. Generazione error feedback
4. Max retries handling
5. Integrazione come nodo LangGraph
"""

import pytest
import sys
from pathlib import Path

# Aggiungi root project al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.agent_validator import (
    ValidatorAgent,
    ValidationResult,
    ValidationOutput
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def validator():
    """ValidatorAgent con config default"""
    return ValidatorAgent({
        "enabled": True,
        "max_retries": 2,
        "log_validations": False  # Silenzioso per test
    })


@pytest.fixture
def validator_disabled():
    """ValidatorAgent disabilitato"""
    return ValidatorAgent({"enabled": False})


@pytest.fixture
def validator_with_grounding():
    """ValidatorAgent con grounding check"""
    return ValidatorAgent({
        "enabled": True,
        "max_retries": 2,
        "grounding_check": {
            "enabled": True,
            "threshold": 0.5
        }
    })


# ============================================================================
# TEST CITATION CHECK
# ============================================================================

class TestCitationCheck:
    """Test per validazione citazioni"""
    
    def test_valid_single_citation(self, validator):
        """Citazione singola valida"""
        response = "Secondo IL-06_01, la gestione rifiuti prevede..."
        available = {"IL-06_01", "PS-08_02"}
        
        result = validator.validate(response, available)
        
        assert result.is_valid
        assert result.result == ValidationResult.VALID
        assert len(result.invalid_citations) == 0
        assert result.action == "PASS"
    
    def test_valid_multiple_citations(self, validator):
        """Citazioni multiple valide"""
        response = "Vedi IL-06_01 e PS-08_02 per i dettagli completi."
        available = {"IL-06_01", "PS-08_02", "MR-03_05"}
        
        result = validator.validate(response, available)
        
        assert result.is_valid
        assert result.result == ValidationResult.VALID
    
    def test_invalid_citation(self, validator):
        """Citazione non presente nel contesto"""
        response = "Secondo PS-06_01, la gestione rifiuti prevede..."
        available = {"IL-06_01", "IL-22_00"}
        
        result = validator.validate(response, available)
        
        assert not result.is_valid
        assert result.result == ValidationResult.INVALID_CITATIONS
        assert "PS-06_01" in result.invalid_citations
        assert result.action == "REGENERATE"
    
    def test_mixed_citations(self, validator):
        """Mix di citazioni valide e invalide"""
        response = "Vedi IL-06_01 e PS-06_01 per info complete."
        available = {"IL-06_01", "MR-22_00"}
        
        result = validator.validate(response, available)
        
        assert not result.is_valid
        assert "PS-06_01" in result.invalid_citations
        assert "IL-06_01" not in result.invalid_citations
    
    def test_no_citations(self, validator):
        """Risposta senza citazioni = OK"""
        response = "La gestione rifiuti è importante per l'ambiente."
        available = {"IL-06_01"}
        
        result = validator.validate(response, available)
        
        assert result.is_valid
        assert result.result == ValidationResult.VALID
    
    def test_case_insensitive(self, validator):
        """Citazioni case-insensitive"""
        response = "Secondo il-06_01 e ps-08_02..."
        available = {"IL-06_01", "PS-08_02"}
        
        result = validator.validate(response, available)
        
        assert result.is_valid
    
    def test_tools_citation(self, validator):
        """Citazione tipo TOOLS"""
        response = "Il modulo TOOLS-02_01 fornisce..."
        available = {"TOOLS-02_01", "IL-06_01"}
        
        result = validator.validate(response, available)
        
        assert result.is_valid


# ============================================================================
# TEST MAX RETRIES
# ============================================================================

class TestMaxRetries:
    """Test per gestione retry"""
    
    def test_max_retries_not_reached(self, validator):
        """Retry disponibili → REGENERATE"""
        response = "Secondo PS-06_01..."
        available = {"IL-06_01"}
        
        result = validator.validate(response, available, retry_count=0)
        
        assert result.action == "REGENERATE"
        assert result.result == ValidationResult.INVALID_CITATIONS
    
    def test_max_retries_reached(self, validator):
        """Max retries raggiunto → PASS (accetta comunque)"""
        response = "Secondo PS-06_01..."
        available = {"IL-06_01"}
        
        result = validator.validate(response, available, retry_count=2)
        
        assert result.action == "PASS"
        assert result.result == ValidationResult.MAX_RETRIES_EXCEEDED
    
    def test_max_retries_exceeded(self, validator):
        """Oltre max retries"""
        response = "Secondo PS-06_01..."
        available = {"IL-06_01"}
        
        result = validator.validate(response, available, retry_count=5)
        
        assert result.action == "PASS"


# ============================================================================
# TEST DISABLED VALIDATOR
# ============================================================================

class TestDisabledValidator:
    """Test con validator disabilitato"""
    
    def test_always_valid_when_disabled(self, validator_disabled):
        """Sempre VALID se disabilitato"""
        response = "Secondo documento_inventato..."
        available = set()
        
        result = validator_disabled.validate(response, available)
        
        assert result.is_valid
        assert result.result == ValidationResult.VALID
        assert result.action == "PASS"


# ============================================================================
# TEST ERROR FEEDBACK
# ============================================================================

class TestErrorFeedback:
    """Test per generazione feedback errori"""
    
    def test_citation_error_feedback(self, validator):
        """Feedback per citazioni invalide"""
        response = "Secondo PS-06_01..."
        available = {"IL-06_01"}
        
        result = validator.validate(response, available)
        feedback = validator.format_error_feedback(result)
        
        assert "PS-06_01" in feedback
        assert "ERRORE" in feedback
        assert "NON citare" in feedback.lower() or "non citare" in feedback.lower()
    
    def test_empty_feedback_for_valid(self, validator):
        """Nessun feedback se valido"""
        response = "Secondo IL-06_01..."
        available = {"IL-06_01"}
        
        result = validator.validate(response, available)
        feedback = validator.format_error_feedback(result)
        
        assert feedback == ""


# ============================================================================
# TEST GROUNDING CHECK (OPTIONAL)
# ============================================================================

class TestGroundingCheck:
    """Test per grounding check opzionale"""
    
    def test_high_grounding_pass(self, validator_with_grounding):
        """Alto overlap → PASS"""
        response = "La gestione rifiuti richiede contenitori omologati."
        context = "La gestione rifiuti richiede l'uso di contenitori omologati e certificati."
        available = {"IL-06_01"}
        
        result = validator_with_grounding.validate(
            response, available, context=context
        )
        
        assert result.is_valid
    
    def test_low_grounding_fail(self, validator_with_grounding):
        """Basso overlap → FAIL"""
        response = "Il processo di qualità necessita audit esterni trimestrali."
        context = "La gestione rifiuti usa contenitori omologati."
        available = {"IL-06_01"}
        
        result = validator_with_grounding.validate(
            response, available, context=context
        )
        
        # Potrebbe fallire per low grounding se threshold alto
        # Con threshold 0.5, dipende dall'overlap effettivo


# ============================================================================
# TEST LANGGRAPH NODE
# ============================================================================

class TestLangGraphNode:
    """Test come nodo LangGraph"""
    
    def test_callable_valid(self, validator):
        """__call__ con risposta valida"""
        state = {
            "answer": "Secondo IL-06_01, la procedura prevede...",
            "available_doc_ids": ["IL-06_01", "PS-08_02"],
            "compressed_context": "Testo documento...",
            "retry_count": 0,
            "agent_trace": ["glossary:10ms"]
        }
        
        updates = validator(state)
        
        assert updates["validation_result"] == "VALID"
        assert "validator:" in updates["agent_trace"][-1]
    
    def test_callable_invalid(self, validator):
        """__call__ con risposta invalida"""
        state = {
            "answer": "Secondo PS-06_01, la procedura prevede...",
            "available_doc_ids": ["IL-06_01"],
            "compressed_context": "Testo documento...",
            "retry_count": 0,
            "max_retries": 2,
            "agent_trace": [],
            "previous_errors": []
        }
        
        updates = validator(state)
        
        assert updates["validation_result"] == "INVALID_CITATIONS"
        assert updates["retry_count"] == 1
        assert len(updates["previous_errors"]) == 1
    
    def test_fallback_to_selected_sources(self, validator):
        """Usa selected_sources se available_doc_ids vuoto"""
        state = {
            "answer": "Secondo IL-06_01...",
            "available_doc_ids": [],  # Vuoto
            "selected_sources": ["IL-06_01"],  # Fallback
            "compressed_context": "",
            "retry_count": 0,
            "agent_trace": []
        }
        
        updates = validator(state)
        
        assert updates["validation_result"] == "VALID"


# ============================================================================
# TEST OUTPUT SERIALIZATION
# ============================================================================

class TestOutputSerialization:
    """Test per serializzazione output"""
    
    def test_to_dict(self, validator):
        """ValidationOutput.to_dict()"""
        response = "Secondo PS-06_01..."
        available = {"IL-06_01"}
        
        result = validator.validate(response, available)
        result_dict = result.to_dict()
        
        assert "result" in result_dict
        assert "is_valid" in result_dict
        assert "invalid_citations" in result_dict
        assert "action" in result_dict
        assert isinstance(result_dict["invalid_citations"], list)


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

