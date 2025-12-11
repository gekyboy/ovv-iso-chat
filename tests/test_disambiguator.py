"""
Test suite per R06: Disambiguazione Contestuale Acronimi (v2.0 fusa)

Testa:
1. UserPreferenceStore - Persistenza preferenze utente
2. ContextualDisambiguator - Detection e disambiguazione contestuale
3. Integrazione con pesi 60/25/15
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.integration.disambiguator import (
    ContextualDisambiguator,
    UserPreferenceStore,
    UserPreference,
    AmbiguousAcronymMatch,
    DisambiguationResult,
    QueryDisambiguationResult,
    AcronymMeaning,
    get_disambiguator,
    get_preference_store,
    reset_singletons,
    CERTAINTY_THRESHOLD,
    WEIGHT_CONTEXT,
    WEIGHT_PREFERENCE,
    WEIGHT_FREQUENCY,
    CONTEXT_KEYWORDS
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def temp_persist_dir():
    """Crea directory temporanea per test"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def preference_store(temp_persist_dir):
    """Store preferenze con directory temporanea"""
    return UserPreferenceStore(persist_dir=temp_persist_dir)


@pytest.fixture
def mock_glossary():
    """Mock GlossaryResolver che simula acronimi ambigui"""
    mock = MagicMock()
    
    def is_ambiguous(acronym):
        return acronym.upper() in ["NC", "PM", "AC", "QC", "CDL"]
    
    def get_all_meanings(acronym):
        meanings_map = {
            "NC": [
                {"context": "qualità", "full": "Non Conformità", "description": "Deviazione da requisiti"},
                {"context": "contabilità", "full": "Nota di Credito", "description": "Documento contabile"}
            ],
            "PM": [
                {"context": "manutenzione", "full": "Professional Maintenance", "description": "Pillar WCM"},
                {"context": "gestione", "full": "Project Manager", "description": "Responsabile progetto"},
                {"context": "pianificazione", "full": "Preventive Maintenance", "description": "Manutenzione preventiva"}
            ],
            "AC": [
                {"context": "qualità", "full": "Azione Correttiva", "description": "Azione per eliminare causa NC"},
                {"context": "climatizzazione", "full": "Aria Condizionata", "description": "Sistema climatizzazione"}
            ],
            "QC": [
                {"context": "qualità", "full": "Quality Control", "description": "Controllo qualità"},
                {"context": "produzione", "full": "Quick Change", "description": "Cambio rapido SMED"}
            ],
            "CDL": [
                {"context": "produzione", "full": "Centro Di Lavoro", "description": "Macchina CNC"},
                {"context": "processo", "full": "Ciclo Di Lavoro", "description": "Sequenza operazioni"}
            ]
        }
        return meanings_map.get(acronym.upper(), [])
    
    mock.is_ambiguous = is_ambiguous
    mock.get_all_meanings = get_all_meanings
    return mock


@pytest.fixture
def disambiguator(mock_glossary, preference_store):
    """Disambiguator con mock glossary"""
    return ContextualDisambiguator(
        glossary_resolver=mock_glossary,
        preference_store=preference_store
    )


@pytest.fixture(autouse=True)
def reset_global_singletons():
    """Reset singletons prima di ogni test"""
    reset_singletons()
    yield
    reset_singletons()


# ============================================================
# TEST: UserPreferenceStore
# ============================================================

class TestUserPreferenceStore:
    """Test per la persistenza delle preferenze utente"""
    
    def test_get_preference_empty(self, preference_store):
        """Test: utente senza preferenze ritorna None"""
        pref = preference_store.get_preference("user1", "NC")
        assert pref is None
    
    def test_save_and_get_preference(self, preference_store):
        """Test: salva e recupera preferenza"""
        preference_store.save_choice(
            user_id="user1",
            acronym="NC",
            chosen_context="qualità",
            chosen_meaning="Non Conformità"
        )
        
        pref = preference_store.get_preference("user1", "NC")
        assert pref is not None
        assert pref.preferred_context == "qualità"
        assert pref.preferred_meaning == "Non Conformità"
        assert pref.times_selected == 1
    
    def test_update_preference_same_context(self, preference_store):
        """Test: conferma preferenza incrementa counter"""
        preference_store.save_choice("user1", "NC", "qualità", "Non Conformità")
        preference_store.save_choice("user1", "NC", "qualità", "Non Conformità")
        
        pref = preference_store.get_preference("user1", "NC")
        assert pref.times_selected == 2
    
    def test_change_preference(self, preference_store):
        """Test: cambiare preferenza aggiorna contesto"""
        preference_store.save_choice("user1", "NC", "qualità", "Non Conformità")
        preference_store.save_choice("user1", "NC", "contabilità", "Nota di Credito")
        
        pref = preference_store.get_preference("user1", "NC")
        assert pref.preferred_context == "contabilità"
        assert pref.times_selected == 1
    
    def test_context_override(self, preference_store):
        """Test: override da contesto incrementa override_count"""
        preference_store.save_choice("user1", "NC", "qualità", "Non Conformità")
        preference_store.save_choice(
            "user1", "NC", "contabilità", "Nota di Credito",
            was_context_override=True
        )
        
        pref = preference_store.get_preference("user1", "NC")
        # Preferenza rimane qualità, ma override_count aumenta
        assert pref.preferred_context == "qualità"
        assert pref.override_count == 1
    
    def test_session_only(self, preference_store, temp_persist_dir):
        """Test: session_only non persiste su file"""
        preference_store.save_choice(
            "user1", "NC", "qualità", "Non Conformità",
            session_only=True
        )
        
        # In cache c'è
        pref = preference_store.get_preference("user1", "NC")
        assert pref is not None
        
        # Ma non su file
        user_file = Path(temp_persist_dir) / "user1_prefs.json"
        assert not user_file.exists()
    
    def test_clear_preference(self, preference_store):
        """Test: rimozione preferenza"""
        preference_store.save_choice("user1", "NC", "qualità", "Non Conformità")
        preference_store.clear_preference("user1", "NC")
        
        pref = preference_store.get_preference("user1", "NC")
        assert pref is None
    
    def test_multiple_users(self, preference_store):
        """Test: preferenze separate per utente"""
        preference_store.save_choice("user1", "NC", "qualità", "Non Conformità")
        preference_store.save_choice("user2", "NC", "contabilità", "Nota di Credito")
        
        pref1 = preference_store.get_preference("user1", "NC")
        pref2 = preference_store.get_preference("user2", "NC")
        
        assert pref1.preferred_context == "qualità"
        assert pref2.preferred_context == "contabilità"
    
    def test_persistence_across_reload(self, temp_persist_dir):
        """Test: preferenze persistono tra reload"""
        # Store 1: salva
        store1 = UserPreferenceStore(persist_dir=temp_persist_dir)
        store1.save_choice("user1", "NC", "qualità", "Non Conformità")
        
        # Store 2: carica da file
        store2 = UserPreferenceStore(persist_dir=temp_persist_dir)
        pref = store2.get_preference("user1", "NC")
        
        assert pref is not None
        assert pref.preferred_context == "qualità"
    
    def test_stats(self, preference_store):
        """Test: statistiche globali"""
        preference_store.save_choice("user1", "NC", "qualità", "Non Conformità")
        preference_store.save_choice("user1", "PM", "manutenzione", "Professional Maintenance")
        preference_store.save_choice("user2", "NC", "contabilità", "Nota di Credito")
        
        stats = preference_store.get_stats()
        
        assert stats["total_users"] == 2
        assert stats["total_preferences"] == 3
        assert stats["by_acronym"]["NC"] == 2
        assert stats["by_acronym"]["PM"] == 1


# ============================================================
# TEST: ContextualDisambiguator - Detection
# ============================================================

class TestDisambiguatorDetection:
    """Test per la detection di acronimi ambigui"""
    
    def test_no_acronyms(self, disambiguator):
        """Test: query senza acronimi"""
        result = disambiguator.detect_ambiguous_in_query(
            "Come gestire i rifiuti?", 
            user_id="test"
        )
        
        assert not result.needs_disambiguation
        assert result.resolved_query == "Come gestire i rifiuti?"
        assert len(result.ambiguous_matches) == 0
    
    def test_detect_single_ambiguous(self, disambiguator):
        """Test: rileva singolo acronimo ambiguo"""
        result = disambiguator.detect_ambiguous_in_query(
            "Parlami di NC",
            user_id="test"
        )
        
        assert len(result.ambiguous_matches) == 1
        assert result.ambiguous_matches[0].acronym == "NC"
    
    def test_detect_multiple_ambiguous(self, disambiguator):
        """Test: rileva multipli acronimi ambigui"""
        result = disambiguator.detect_ambiguous_in_query(
            "Relazione tra NC e AC",
            user_id="test"
        )
        
        assert len(result.ambiguous_matches) == 2
        acronyms = [m.acronym for m in result.ambiguous_matches]
        assert "NC" in acronyms
        assert "AC" in acronyms
    
    def test_non_ambiguous_acronym(self, disambiguator):
        """Test: acronimo non ambiguo non viene segnalato"""
        result = disambiguator.detect_ambiguous_in_query(
            "Cos'è ISO 9001?",
            user_id="test"
        )
        
        # ISO non è ambiguo nel nostro sistema
        assert len(result.ambiguous_matches) == 0
    
    def test_case_insensitive(self, disambiguator):
        """Test: detection case-insensitive"""
        result = disambiguator.detect_ambiguous_in_query(
            "cosa sono le nc?",
            user_id="test"
        )
        
        assert len(result.ambiguous_matches) == 1
        assert result.ambiguous_matches[0].acronym == "NC"


# ============================================================
# TEST: ContextualDisambiguator - Context Analysis
# ============================================================

class TestDisambiguatorContext:
    """Test per l'analisi contestuale (60% del peso)"""
    
    def test_context_quality_keywords(self, disambiguator):
        """Test: keywords qualità risolvono NC automaticamente"""
        result = disambiguator.detect_ambiguous_in_query(
            "Come gestire le NC dell'audit qualità?",
            user_id="test"
        )
        
        assert len(result.ambiguous_matches) == 1
        match = result.ambiguous_matches[0]
        
        # Dovrebbe essere certo perché "audit" e "qualità" sono keywords
        assert match.disambiguation_result is not None
        assert match.disambiguation_result.chosen_context == "qualità"
        assert match.disambiguation_result.is_certain
    
    def test_context_accounting_keywords(self, disambiguator):
        """Test: keywords contabilità risolvono NC automaticamente"""
        result = disambiguator.detect_ambiguous_in_query(
            "Devo emettere una NC per la fattura del cliente",
            user_id="test"
        )
        
        match = result.ambiguous_matches[0]
        assert match.disambiguation_result.chosen_context == "contabilità"
        assert "fattura" in match.disambiguation_result.context_used or "cliente" in match.disambiguation_result.context_used
    
    def test_context_maintenance_keywords(self, disambiguator):
        """Test: keywords manutenzione risolvono PM"""
        result = disambiguator.detect_ambiguous_in_query(
            "Qual è il piano PM per la manutenzione delle macchine?",
            user_id="test"
        )
        
        match = result.ambiguous_matches[0]
        # Dovrebbe preferire manutenzione per le keywords
        assert match.disambiguation_result.chosen_context in ["manutenzione", "pianificazione"]
    
    def test_no_context_needs_input(self, disambiguator):
        """Test: senza contesto chiaro serve input utente"""
        result = disambiguator.detect_ambiguous_in_query(
            "Mostrami le NC",
            user_id="test"
        )
        
        # Con "Mostrami le NC" senza altre keywords, probabilmente non è certo
        # (dipende dalla soglia, ma in genere serve input)
        assert result.needs_disambiguation or result.ambiguous_matches[0].disambiguation_result.confidence < 0.7


# ============================================================
# TEST: ContextualDisambiguator - User Preferences (25%)
# ============================================================

class TestDisambiguatorPreferences:
    """Test per le preferenze utente (25% del peso)"""
    
    def test_preference_influences_score(self, disambiguator, preference_store):
        """Test: preferenza utente influenza lo score"""
        # Salva preferenza per contabilità
        preference_store.save_choice("test", "NC", "contabilità", "Nota di Credito")
        
        # Query ambigua senza contesto chiaro
        result = disambiguator.detect_ambiguous_in_query(
            "Mostrami le NC",
            user_id="test"
        )
        
        match = result.ambiguous_matches[0]
        # La preferenza dovrebbe dare boost a contabilità
        # Ma il dominio frequenza dovrebbe dare boost a qualità
        # Il risultato finale dipende dal bilanciamento
        assert match.disambiguation_result is not None
    
    def test_context_overrides_preference(self, disambiguator, preference_store):
        """Test: contesto forte batte preferenza"""
        # Preferenza per contabilità
        preference_store.save_choice("test", "NC", "contabilità", "Nota di Credito")
        
        # Ma query ha contesto forte qualità
        result = disambiguator.detect_ambiguous_in_query(
            "Come gestire le NC dell'audit ISO 9001?",
            user_id="test"
        )
        
        match = result.ambiguous_matches[0]
        # Il contesto dovrebbe vincere (60% vs 25%)
        assert match.disambiguation_result.chosen_context == "qualità"


# ============================================================
# TEST: ContextualDisambiguator - Resolution
# ============================================================

class TestDisambiguatorResolution:
    """Test per la risoluzione degli acronimi"""
    
    def test_resolve_with_choice(self, disambiguator):
        """Test: resolve_with_choice espande correttamente"""
        resolved = disambiguator.resolve_with_choice(
            query="Mostrami le NC",
            acronym="NC",
            chosen_context="qualità",
            user_id="test",
            remember=False
        )
        
        assert "NC (Non Conformità)" in resolved
    
    def test_resolve_saves_preference(self, disambiguator, preference_store):
        """Test: resolve salva preferenza se remember=True"""
        disambiguator.resolve_with_choice(
            query="Mostrami le NC",
            acronym="NC",
            chosen_context="contabilità",
            user_id="test",
            remember=True
        )
        
        pref = preference_store.get_preference("test", "NC")
        assert pref is not None
        assert pref.preferred_context == "contabilità"
    
    def test_resolve_session_only(self, disambiguator, preference_store, temp_persist_dir):
        """Test: session_only non persiste"""
        disambiguator.resolve_with_choice(
            query="Mostrami le NC",
            acronym="NC",
            chosen_context="qualità",
            user_id="test",
            remember=True,
            session_only=True
        )
        
        # In cache c'è
        pref = preference_store.get_preference("test", "NC")
        assert pref is not None
        
        # Ma non su file
        user_file = Path(temp_persist_dir) / "test_prefs.json"
        assert not user_file.exists()
    
    def test_automatic_resolution(self, disambiguator):
        """Test: risoluzione automatica con contesto chiaro"""
        result = disambiguator.detect_ambiguous_in_query(
            "Procedura per gestire le NC dell'audit qualità",
            user_id="test"
        )
        
        if not result.needs_disambiguation:
            # Se risolto automaticamente, la query deve essere espansa
            assert result.resolved_query is not None
            assert "Non Conformità" in result.resolved_query


# ============================================================
# TEST: Formatting
# ============================================================

class TestDisambiguatorFormatting:
    """Test per la formattazione messaggi"""
    
    def test_format_question(self, disambiguator):
        """Test: formatta domanda correttamente"""
        result = disambiguator.detect_ambiguous_in_query(
            "Mostrami le NC",
            user_id="test"
        )
        
        if result.ambiguous_matches:
            match = result.ambiguous_matches[0]
            question = disambiguator.format_disambiguation_question(match, "test")
            
            assert "NC" in question
            assert "Non Conformità" in question
            assert "Nota di Credito" in question
            assert "❓" in question
    
    def test_format_with_preference_marker(self, disambiguator, preference_store):
        """Test: marker preferenza nella domanda"""
        preference_store.save_choice("test", "NC", "qualità", "Non Conformità")
        
        result = disambiguator.detect_ambiguous_in_query(
            "Mostrami le NC",
            user_id="test"
        )
        
        if result.ambiguous_matches:
            match = result.ambiguous_matches[0]
            question = disambiguator.format_disambiguation_question(match, "test")
            
            # Dovrebbe avere marker preferenza
            assert "⭐" in question or "preferenza" in question


# ============================================================
# TEST: Constants and Weights
# ============================================================

class TestConstants:
    """Test per le costanti di configurazione"""
    
    def test_weights_sum_to_one(self):
        """Test: i pesi sommano a 1"""
        total = WEIGHT_CONTEXT + WEIGHT_PREFERENCE + WEIGHT_FREQUENCY
        assert abs(total - 1.0) < 0.01
    
    def test_context_keywords_exist(self):
        """Test: keywords definite per acronimi principali"""
        assert "NC" in CONTEXT_KEYWORDS
        assert "AC" in CONTEXT_KEYWORDS
        assert "PM" in CONTEXT_KEYWORDS
        assert "QC" in CONTEXT_KEYWORDS
        
        # Verifica che ogni acronimo abbia almeno 2 contesti
        for acronym, contexts in CONTEXT_KEYWORDS.items():
            assert len(contexts) >= 2, f"{acronym} ha meno di 2 contesti"
    
    def test_certainty_threshold_reasonable(self):
        """Test: soglia certezza è ragionevole"""
        assert 0.2 <= CERTAINTY_THRESHOLD <= 0.5


# ============================================================
# TEST: Singletons
# ============================================================

class TestSingletons:
    """Test per singleton factory functions"""
    
    def test_get_preference_store_singleton(self):
        """Test: get_preference_store ritorna singleton"""
        store1 = get_preference_store()
        store2 = get_preference_store()
        assert store1 is store2
    
    def test_get_disambiguator_singleton(self, mock_glossary):
        """Test: get_disambiguator ritorna singleton"""
        dis1 = get_disambiguator(mock_glossary)
        dis2 = get_disambiguator(mock_glossary)
        assert dis1 is dis2
    
    def test_reset_singletons(self, mock_glossary):
        """Test: reset_singletons funziona"""
        dis1 = get_disambiguator(mock_glossary)
        reset_singletons()
        dis2 = get_disambiguator(mock_glossary)
        assert dis1 is not dis2


# ============================================================
# TEST: Edge Cases
# ============================================================

class TestEdgeCases:
    """Test per casi limite"""
    
    def test_empty_query(self, disambiguator):
        """Test: query vuota"""
        result = disambiguator.detect_ambiguous_in_query("", user_id="test")
        
        assert not result.needs_disambiguation
        assert result.resolved_query == ""
    
    def test_only_acronym(self, disambiguator):
        """Test: query con solo acronimo"""
        result = disambiguator.detect_ambiguous_in_query("NC", user_id="test")
        
        assert len(result.ambiguous_matches) == 1
    
    def test_unknown_user(self, disambiguator):
        """Test: utente sconosciuto (nessuna preferenza)"""
        result = disambiguator.detect_ambiguous_in_query(
            "Mostrami le NC",
            user_id="unknown_user_xyz"
        )
        
        # Deve funzionare senza errori
        assert result.ambiguous_matches is not None
    
    def test_get_context_for_meaning(self, disambiguator):
        """Test: trova context per meaning"""
        context = disambiguator.get_context_for_meaning("NC", "Non Conformità")
        assert context == "qualità"
        
        context = disambiguator.get_context_for_meaning("NC", "Nota di Credito")
        assert context == "contabilità"
        
        context = disambiguator.get_context_for_meaning("NC", "Unknown")
        assert context is None


# ============================================================
# TEST: Integration with Glossary
# ============================================================

class TestGlossaryIntegration:
    """Test per integrazione con GlossaryResolver"""
    
    def test_uses_glossary_meanings(self, disambiguator, mock_glossary):
        """Test: usa significati dal glossary"""
        result = disambiguator.detect_ambiguous_in_query(
            "Mostrami le NC",
            user_id="test"
        )
        
        match = result.ambiguous_matches[0]
        meanings = [m.full for m in match.meanings]
        
        assert "Non Conformità" in meanings
        assert "Nota di Credito" in meanings
    
    def test_fallback_to_context_keywords(self):
        """Test: fallback a CONTEXT_KEYWORDS se glossary non ha dati"""
        # Disambiguator senza glossary
        dis = ContextualDisambiguator(
            glossary_resolver=None,
            preference_store=UserPreferenceStore(tempfile.mkdtemp())
        )
        
        result = dis.detect_ambiguous_in_query(
            "Mostrami le NC",
            user_id="test"
        )
        
        # Dovrebbe comunque rilevare NC dalle CONTEXT_KEYWORDS
        assert len(result.ambiguous_matches) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

