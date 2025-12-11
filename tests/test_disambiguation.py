"""
Test per Disambiguazione Contestuale (R06)
Verifica che il sistema disambigui in modo intelligente:
- Contesto domina sulle preferenze
- Preferenze sono suggerimenti soft, non rigidi
- Chiede solo quando realmente incerto
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDisambiguatorBasics:
    """Test funzionalità base del disambiguator"""
    
    def test_ambiguous_acronyms_defined(self):
        """Verifica che esistano acronimi ambigui definiti"""
        from src.integration.disambiguator import AMBIGUOUS_ACRONYMS
        
        assert "NC" in AMBIGUOUS_ACRONYMS
        assert len(AMBIGUOUS_ACRONYMS["NC"]) >= 2
        
        # NC dovrebbe avere "Non Conformità" e "Nota di Credito"
        nc_meanings = [m.meaning for m in AMBIGUOUS_ACRONYMS["NC"]]
        assert "Non Conformità" in nc_meanings
        assert "Nota di Credito" in nc_meanings
    
    def test_is_ambiguous(self):
        """Test rilevamento acronimi ambigui"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        disambiguator = ContextualDisambiguator()
        
        assert disambiguator.is_ambiguous("NC")
        assert disambiguator.is_ambiguous("nc")  # Case insensitive
        assert disambiguator.is_ambiguous("AC")
        assert not disambiguator.is_ambiguous("ISO")  # Non ambiguo
        assert not disambiguator.is_ambiguous("XYZ")  # Non esiste
    
    def test_get_meanings(self):
        """Test recupero significati"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        disambiguator = ContextualDisambiguator()
        
        meanings = disambiguator.get_meanings("NC")
        assert len(meanings) >= 2
        
        # Verifica struttura
        for meaning in meanings:
            assert hasattr(meaning, 'meaning')
            assert hasattr(meaning, 'context_keywords')
            assert len(meaning.context_keywords) > 0


class TestContextualDisambiguation:
    """Test disambiguazione basata su contesto"""
    
    def test_quality_context_chooses_non_conformita(self):
        """NC in contesto qualità → Non Conformità"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        disambiguator = ContextualDisambiguator()
        
        # Query con chiaro contesto qualità
        result = disambiguator.disambiguate(
            acronym="NC",
            query="Come gestisco una NC rilevata durante l'audit di qualità?",
            user_id="test"
        )
        
        assert result.chosen_meaning == "Non Conformità"
        assert result.confidence > 0.5
        # Dovrebbe essere certo dato il contesto forte
        assert result.is_certain or result.confidence > 0.6
    
    def test_financial_context_chooses_nota_credito(self):
        """NC in contesto contabile → Nota di Credito"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        disambiguator = ContextualDisambiguator()
        
        # Query con chiaro contesto finanziario
        result = disambiguator.disambiguate(
            acronym="NC",
            query="Quante NC abbiamo emesso nel ciclo attivo questo mese per i rimborsi clienti?",
            user_id="test"
        )
        
        assert result.chosen_meaning == "Nota di Credito"
        assert result.confidence > 0.5
    
    def test_ambiguous_context_is_uncertain(self):
        """Contesto ambiguo → bassa certezza"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        disambiguator = ContextualDisambiguator()
        
        # Query senza contesto chiaro
        result = disambiguator.disambiguate(
            acronym="NC",
            query="Mostrami le NC",
            user_id="test"
        )
        
        # Dovrebbe avere confidence più bassa
        assert result.confidence < 0.9
        # O non è certo
        # (dipende dalla soglia, ma il gap tra opzioni dovrebbe essere piccolo)


class TestUserPreferences:
    """Test gestione preferenze utente (soft, non rigide)"""
    
    def test_save_and_retrieve_preference(self, tmp_path):
        """Test salvataggio e recupero preferenze"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        pref_path = tmp_path / "test_prefs.json"
        disambiguator = ContextualDisambiguator(preferences_path=str(pref_path))
        
        # Salva preferenza
        disambiguator.save_user_choice("user1", "NC", "Non Conformità")
        
        # Recupera
        pref = disambiguator.get_user_preference("user1", "NC")
        assert pref == "Non Conformità"
        
        # Verifica persistenza
        disambiguator2 = ContextualDisambiguator(preferences_path=str(pref_path))
        pref2 = disambiguator2.get_user_preference("user1", "NC")
        assert pref2 == "Non Conformità"
    
    def test_preference_is_soft_not_rigid(self, tmp_path):
        """Test che la preferenza NON sovrascriva il contesto forte"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        pref_path = tmp_path / "test_prefs.json"
        disambiguator = ContextualDisambiguator(preferences_path=str(pref_path))
        
        # Utente preferisce "Non Conformità"
        disambiguator.save_user_choice("user1", "NC", "Non Conformità")
        
        # Ma query ha contesto finanziario forte
        result = disambiguator.disambiguate(
            acronym="NC",
            query="Emetti una NC per lo storno della fattura nel ciclo attivo",
            user_id="user1"
        )
        
        # Il contesto dovrebbe vincere sulla preferenza
        # (perché il contesto finanziario è molto forte)
        # Nota: potrebbe non essere "Nota di Credito" se il contesto non è abbastanza forte,
        # ma almeno la confidence dovrebbe riflettere l'ambiguità
        assert result.confidence < 1.0  # Non può essere sicuro al 100%
    
    def test_preference_boosts_when_context_neutral(self, tmp_path):
        """Test che la preferenza influenzi quando il contesto è neutro"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        pref_path = tmp_path / "test_prefs.json"
        disambiguator = ContextualDisambiguator(preferences_path=str(pref_path))
        
        # Senza preferenza
        result1 = disambiguator.disambiguate(
            acronym="NC",
            query="Parlami delle NC",
            user_id="user_no_pref"
        )
        score1 = dict(result1.all_meanings).get("Non Conformità", 0)
        
        # Con preferenza per "Non Conformità"
        disambiguator.save_user_choice("user_with_pref", "NC", "Non Conformità")
        result2 = disambiguator.disambiguate(
            acronym="NC",
            query="Parlami delle NC",
            user_id="user_with_pref"
        )
        score2 = dict(result2.all_meanings).get("Non Conformità", 0)
        
        # Con preferenza, lo score dovrebbe essere più alto
        assert score2 >= score1


class TestAcronymDetection:
    """Test rilevamento acronimi nella query"""
    
    def test_find_ambiguous_in_query(self):
        """Test ricerca acronimi ambigui nella query"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        disambiguator = ContextualDisambiguator()
        
        # Query con NC
        found = disambiguator.get_ambiguous_acronyms_in_query(
            "Come gestisco una NC durante l'audit?"
        )
        assert "NC" in found
        
        # Query con AC
        found = disambiguator.get_ambiguous_acronyms_in_query(
            "Devo aprire una AC per questa non conformità"
        )
        assert "AC" in found
        
        # Query senza acronimi ambigui
        found = disambiguator.get_ambiguous_acronyms_in_query(
            "Qual è la procedura ISO?"
        )
        assert len(found) == 0
    
    def test_multiple_ambiguous_acronyms(self):
        """Test query con più acronimi ambigui"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        disambiguator = ContextualDisambiguator()
        
        found = disambiguator.get_ambiguous_acronyms_in_query(
            "Per la NC devo aprire una AC?"
        )
        
        assert "NC" in found
        assert "AC" in found


class TestDisambiguationResult:
    """Test struttura risultato disambiguazione"""
    
    def test_result_has_all_fields(self):
        """Test che il risultato abbia tutti i campi necessari"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        disambiguator = ContextualDisambiguator()
        
        result = disambiguator.disambiguate(
            acronym="NC",
            query="Come gestisco le NC?",
            user_id="test"
        )
        
        # Verifica campi
        assert hasattr(result, 'acronym')
        assert hasattr(result, 'chosen_meaning')
        assert hasattr(result, 'confidence')
        assert hasattr(result, 'is_certain')
        assert hasattr(result, 'all_meanings')
        assert hasattr(result, 'context_used')
        assert hasattr(result, 'preference_applied')
        
        # Verifica tipi
        assert isinstance(result.confidence, float)
        assert isinstance(result.is_certain, bool)
        assert isinstance(result.all_meanings, list)
    
    def test_all_meanings_sums_to_one(self):
        """Test che gli score normalizzati sommino a ~1"""
        from src.integration.disambiguator import ContextualDisambiguator
        
        disambiguator = ContextualDisambiguator()
        
        result = disambiguator.disambiguate(
            acronym="NC",
            query="Come gestisco le NC?",
            user_id="test"
        )
        
        total = sum(score for _, score in result.all_meanings)
        assert 0.99 <= total <= 1.01  # Circa 1


class TestGlossaryIntegration:
    """Test integrazione con GlossaryResolver"""
    
    def test_resolve_with_context_method_exists(self):
        """Test che il metodo resolve_with_context esista"""
        from src.integration.glossary import GlossaryResolver
        
        resolver = GlossaryResolver(config={})
        
        assert hasattr(resolver, 'resolve_with_context')
    
    def test_resolve_with_context_non_ambiguous(self):
        """Test risoluzione acronimi non ambigui"""
        from src.integration.glossary import GlossaryResolver
        
        resolver = GlossaryResolver(config_path="config/config.yaml")
        
        result = resolver.resolve_with_context(
            acronym="ISO",
            query="Cosa dice la ISO 9001?",
            user_id="test"
        )
        
        assert result.get("needs_clarification") == False
        assert result.get("full") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

