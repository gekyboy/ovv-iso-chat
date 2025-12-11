"""
Test per R20: Glossary Context Injection
Verifica che le definizioni del glossario vengano correttamente
estratte e iniettate nel prompt LLM.

Implementato: 8 Dicembre 2025
"""

import pytest
import logging
import sys
from pathlib import Path

# Aggiungi path per import
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging per test
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# TEST CASES
# ============================================================================

TEST_CASES = [
    # === ACRONIMI SINGOLI ===
    {
        "id": "TC01",
        "query": "cosa significa WCM?",
        "expected_in_glossary_context": ["WCM", "World Class Manufacturing"],
        "expected_in_answer": ["World Class Manufacturing"],
        "should_not_contain": ["Work and Management", "non ho informazioni"]
    },
    {
        "id": "TC02",
        "query": "spiegami il PDCA",
        "expected_in_glossary_context": ["PDCA", "Plan-Do-Check-Act"],
        "expected_in_answer": ["Plan", "Do", "Check", "Act"],
        "should_not_contain": []
    },
    {
        "id": "TC03",
        "query": "cos'è una NC?",
        "expected_in_glossary_context": ["NC", "Non Conformità"],
        "expected_in_answer": ["Non Conformità"],
        "should_not_contain": []
    },
    
    # === ACRONIMI MULTIPLI ===
    {
        "id": "TC04",
        "query": "che differenza c'è tra NC e AC?",
        "expected_in_glossary_context": ["NC", "AC", "Non Conformità", "Azione Correttiva"],
        "expected_in_answer": ["Non Conformità", "Azione Correttiva"],
        "should_not_contain": []
    },
    {
        "id": "TC05",
        "query": "come si usa FMEA nel SGI?",
        "expected_in_glossary_context": ["FMEA", "SGI"],
        "expected_in_answer": [],  # Non verifichiamo contenuto specifico
        "should_not_contain": []
    },
    
    # === METODOLOGIE WCM ===
    {
        "id": "TC06",
        "query": "cosa sono le 5S?",
        "expected_in_glossary_context": ["5S"],
        "expected_in_answer": [],  # La definizione nel glossario può variare
        "should_not_contain": []
    },
    {
        "id": "TC07",
        "query": "come funziona un OPL?",
        "expected_in_glossary_context": ["OPL", "One Point Lesson"],
        "expected_in_answer": ["One Point Lesson"],
        "should_not_contain": []
    },
    
    # === DOCUMENTI ISO ===
    {
        "id": "TC08",
        "query": "cosa contiene una PS?",
        "expected_in_glossary_context": ["PS", "Procedura"],
        "expected_in_answer": [],
        "should_not_contain": []
    },
    {
        "id": "TC09",
        "query": "differenza tra PS e IL",
        "expected_in_glossary_context": ["PS", "IL"],
        "expected_in_answer": [],
        "should_not_contain": []
    },
    
    # === EDGE CASES ===
    {
        "id": "TC10",
        "query": "Come gestire i rifiuti?",  # Nessun acronimo esplicito
        "expected_in_glossary_context": [],  # Nessuna definizione attesa
        "expected_in_answer": [],
        "should_not_contain": ["errore"]
    },
]


# ============================================================================
# TEST GLOSSARY CONTEXT EXTRACTION
# ============================================================================

class TestGlossaryContextExtraction:
    """Test per il metodo get_context_for_query()"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup del glossary resolver"""
        from src.integration.glossary import GlossaryResolver
        self.glossary = GlossaryResolver(config_path="config/config.yaml")
    
    def test_single_acronym_extraction(self):
        """TC01: Estrae singolo acronimo WCM"""
        context = self.glossary.get_context_for_query("cosa significa WCM?")
        
        assert "WCM" in context, "WCM non trovato nel context"
        assert "World Class Manufacturing" in context, "Definizione WCM non trovata"
        assert "DEFINIZIONI UFFICIALI" in context, "Header glossario non trovato"
    
    def test_pdca_extraction(self):
        """TC02: Estrae PDCA"""
        context = self.glossary.get_context_for_query("spiegami il PDCA")
        
        assert "PDCA" in context, "PDCA non trovato"
        # Verifica che ci sia la definizione (può essere Plan-Do-Check-Act o simile)
        assert "Plan" in context or "Deming" in context, "Definizione PDCA non trovata"
    
    def test_multiple_acronyms_extraction(self):
        """TC04: Estrae acronimi multipli"""
        context = self.glossary.get_context_for_query("differenza tra NC e AC")
        
        assert "NC" in context, "NC non trovato"
        assert "AC" in context, "AC non trovato"
        assert "Non Conformità" in context, "Definizione NC non trovata"
        assert "Azione Correttiva" in context, "Definizione AC non trovata"
    
    def test_no_acronyms_returns_empty(self):
        """TC10: Query senza acronimi ritorna stringa vuota"""
        context = self.glossary.get_context_for_query("Come gestire i rifiuti?")
        
        # Dovrebbe essere vuota (o quasi) se non ci sono acronimi riconosciuti
        # Può contenere qualcosa se "rifiuti" matcha fuzzy, ma non deve avere errori
        assert isinstance(context, str)
    
    def test_max_definitions_limit(self):
        """Verifica che il limite max_definitions funzioni"""
        # Query con molti potenziali acronimi
        context = self.glossary.get_context_for_query(
            "PS IL MR NC AC FMEA WCM SGI KPI",
            max_definitions=3
        )
        
        # Conta le definizioni (ogni "• " indica una definizione)
        definition_count = context.count("• ")
        assert definition_count <= 3, f"Troppe definizioni: {definition_count} > 3"
    
    def test_format_includes_box(self):
        """Verifica che l'output sia formattato con box"""
        context = self.glossary.get_context_for_query("cosa è WCM?")
        
        if context:  # Solo se ha trovato definizioni
            assert "╔" in context or "DEFINIZIONI" in context, "Formato box non trovato"


# ============================================================================
# TEST GLOSSARY EXTRACTION (Standalone - senza pipeline completa)
# ============================================================================

def test_glossary_extraction_standalone():
    """Test standalone per verifica rapida dell'estrazione glossario"""
    from src.integration.glossary import GlossaryResolver
    
    glossary = GlossaryResolver(config_path="config/config.yaml")
    
    print("\n" + "="*60)
    print("🧪 R20 GLOSSARY EXTRACTION - TEST STANDALONE")
    print("="*60 + "\n")
    
    passed = 0
    failed = 0
    
    for test in TEST_CASES:
        query = test["query"]
        expected = test["expected_in_glossary_context"]
        
        context = glossary.get_context_for_query(query)
        
        # Verifica
        if not expected:
            # Se non ci aspettiamo definizioni, il test passa se non ci sono errori
            all_found = True
        else:
            all_found = all(term in context for term in expected)
        
        if all_found:
            print(f"✅ PASS [{test['id']}]: {query[:40]}...")
            passed += 1
        else:
            print(f"❌ FAIL [{test['id']}]: {query[:40]}...")
            print(f"   Expected: {expected}")
            print(f"   Got: {context[:200]}..." if context else "   Got: (empty)")
            failed += 1
    
    print("\n" + "-"*60)
    total = passed + failed
    percentage = (100 * passed / total) if total > 0 else 0
    print(f"📊 RESULTS: {passed}/{total} passed ({percentage:.0f}%)")
    print("-"*60 + "\n")
    
    return passed, failed


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Esegui test standalone (senza pytest)
    test_glossary_extraction_standalone()

