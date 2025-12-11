"""
Test per R15 - Tool Suggester
Verifica intent detection, mapping match e suggerimenti

Run: pytest tests/test_tool_suggester.py -v
"""

import pytest
import sys
from pathlib import Path

# Aggiungi src al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.integration.tool_suggester import ToolSuggester, ToolSuggestion


@pytest.fixture
def suggester():
    """Fixture per ToolSuggester con mapping di test"""
    return ToolSuggester(mapping_path="config/tools_mapping.json")


class TestIntentDetection:
    """Test per is_actionable_query()"""
    
    def test_actionable_nc(self, suggester):
        """NC è azionabile"""
        assert suggester.is_actionable_query("Ho una non conformità") == True
    
    def test_actionable_come_gestisco(self, suggester):
        """'Come gestisco' è azionabile"""
        assert suggester.is_actionable_query("Come gestisco un reclamo?") == True
    
    def test_actionable_problema(self, suggester):
        """'Ho un problema' è azionabile"""
        assert suggester.is_actionable_query("Ho un problema di qualità") == True
    
    def test_actionable_guasto(self, suggester):
        """Guasto è azionabile"""
        assert suggester.is_actionable_query("La macchina si è guastata") == True
    
    def test_actionable_devo_registrare(self, suggester):
        """'Devo registrare' è azionabile"""
        assert suggester.is_actionable_query("Devo registrare un'anomalia") == True
    
    def test_actionable_cliente_reclama(self, suggester):
        """'Cliente reclama' è azionabile"""
        assert suggester.is_actionable_query("Il cliente reclama per un difetto") == True
    
    def test_informational_cose(self, suggester):
        """'Cos'è' è informativo"""
        assert suggester.is_actionable_query("Cos'è una NC?") == False
    
    def test_informational_spiegami(self, suggester):
        """'Spiegami' è informativo"""
        assert suggester.is_actionable_query("Spiegami la ISO 9001") == False
    
    def test_informational_definizione(self, suggester):
        """Richiesta definizione è informativa"""
        assert suggester.is_actionable_query("Definizione di WCM") == False
    
    def test_informational_quanti(self, suggester):
        """'Quanti' è informativo"""
        assert suggester.is_actionable_query("Quanti capitoli ha la norma?") == False
    
    def test_informational_differenza(self, suggester):
        """'Differenza tra' è informativo"""
        assert suggester.is_actionable_query("Differenza tra PS e IL?") == False
    
    def test_informational_che_cose(self, suggester):
        """'Che cos'è' è informativo"""
        assert suggester.is_actionable_query("Che cos'è una procedura?") == False


class TestMappingMatch:
    """Test per match_from_mapping()"""
    
    def test_match_nc_keywords(self, suggester):
        """Match su keywords NC"""
        results = suggester.match_from_mapping("Ho una non conformità")
        assert len(results) > 0
        doc_ids = [r.doc_id for r in results]
        assert "MR-07_05" in doc_ids  # Cartellino anomalia
    
    def test_match_anomalia(self, suggester):
        """Match su anomalia"""
        results = suggester.match_from_mapping("Devo segnalare un'anomalia")
        assert len(results) > 0
        doc_ids = [r.doc_id for r in results]
        assert "MR-07_05" in doc_ids
    
    def test_match_ishikawa_concepts(self, suggester):
        """Match su concepts Ishikawa"""
        results = suggester.match_from_mapping("Devo analizzare le cause radice")
        assert len(results) > 0
        doc_ids = [r.doc_id for r in results]
        # Dovrebbe includere 4M o 5 Perché
        assert any("TOOLS-10" in d for d in doc_ids) or any("ishikawa" in str(r.name).lower() for r in results)
    
    def test_match_kaizen(self, suggester):
        """Match su Kaizen"""
        results = suggester.match_from_mapping("Voglio fare un quick kaizen")
        assert len(results) > 0
        doc_ids = [r.doc_id for r in results]
        assert "MR-10_03" in doc_ids  # Quick Kaizen
    
    def test_match_8d_reclamo(self, suggester):
        """Match su 8D per reclamo cliente"""
        results = suggester.match_from_mapping("Ho un reclamo cliente")
        assert len(results) > 0
        doc_ids = [r.doc_id for r in results]
        assert "MR-08_14" in doc_ids  # 8D Report
    
    def test_match_fmea(self, suggester):
        """Match su FMEA"""
        results = suggester.match_from_mapping("Devo fare analisi rischi failure mode")
        assert len(results) > 0
        doc_ids = [r.doc_id for r in results]
        assert "MR-08_07" in doc_ids  # FMEA
    
    def test_no_match_unrelated(self, suggester):
        """Nessun match per query non correlata"""
        results = suggester.match_from_mapping("Il tempo oggi è bello")
        assert len(results) == 0


class TestSuggestTools:
    """Test per suggest_tools() (metodo principale)"""
    
    def test_suggest_for_nc(self, suggester):
        """Suggerisce tool per NC"""
        suggestions = suggester.suggest_tools("Ho una NC su un pezzo lavorato")
        assert len(suggestions) > 0
        assert len(suggestions) <= 2  # Max 2
    
    def test_no_suggest_for_informational(self, suggester):
        """Nessun suggerimento per query informativa"""
        suggestions = suggester.suggest_tools("Cos'è una procedura di sistema?")
        assert len(suggestions) == 0
    
    def test_no_suggest_for_spiegami(self, suggester):
        """Nessun suggerimento per 'spiegami'"""
        suggestions = suggester.suggest_tools("Spiegami come funziona il WCM")
        assert len(suggestions) == 0
    
    def test_suggest_deduplication(self, suggester):
        """Suggerimenti sono deduplicati"""
        suggestions = suggester.suggest_tools(
            "Non conformità anomalia difetto NC problema"  # Molte keywords
        )
        doc_ids = [s.doc_id for s in suggestions]
        assert len(doc_ids) == len(set(doc_ids))  # No duplicati
    
    def test_suggest_max_two(self, suggester):
        """Massimo 2 suggerimenti"""
        suggestions = suggester.suggest_tools(
            "Ho una NC, devo fare root cause analysis con ishikawa e kaizen"
        )
        assert len(suggestions) <= 2
    
    def test_suggest_for_reclamo(self, suggester):
        """Suggerisce tool per reclamo"""
        suggestions = suggester.suggest_tools("Il cliente reclama per difetto prodotto")
        assert len(suggestions) > 0
        doc_ids = [s.doc_id for s in suggestions]
        # Dovrebbe suggerire 8D o cartellino
        assert "MR-08_14" in doc_ids or "MR-07_05" in doc_ids
    
    def test_suggest_for_miglioramento(self, suggester):
        """Suggerisce tool per miglioramento"""
        suggestions = suggester.suggest_tools("Voglio fare un miglioramento rapido")
        # Potrebbe o meno suggerire, dipende se azionabile
        # Ma se suggerisce, deve essere kaizen
        if suggestions:
            doc_ids = [s.doc_id for s in suggestions]
            assert any("MR-10" in d for d in doc_ids)


class TestFormatting:
    """Test per formattazione UI"""
    
    def test_format_empty(self, suggester):
        """Formatta lista vuota"""
        result = suggester.format_suggestions_for_ui([])
        assert result == ""
    
    def test_format_with_suggestions(self, suggester):
        """Formatta con suggerimenti"""
        suggestions = [
            ToolSuggestion(
                doc_id="MR-07_05",
                name="Cartellino Anomalia",
                reason="Test",
                source="mapping",
                score=1.0,
                suggest_when="Per registrare anomalie"
            )
        ]
        result = suggester.format_suggestions_for_ui(suggestions)
        
        assert "🛠️ Tool consigliati" in result
        assert "Cartellino Anomalia" in result
        assert "MR-07_05" in result
        assert "admin mapping" in result
    
    def test_format_semantic_source(self, suggester):
        """Formatta con source semantico"""
        suggestions = [
            ToolSuggestion(
                doc_id="TOOLS-10_01",
                name="5W1H",
                reason="Test",
                source="semantic",
                score=0.85,
                suggest_when="Analisi strutturata"
            )
        ]
        result = suggester.format_suggestions_for_ui(suggestions)
        
        assert "5W1H" in result
        assert "semantico" in result
        assert "85%" in result


class TestToolSuggestion:
    """Test per dataclass ToolSuggestion"""
    
    def test_create_suggestion(self):
        """Crea ToolSuggestion"""
        s = ToolSuggestion(
            doc_id="MR-07_05",
            name="Test Tool",
            reason="Test reason",
            source="mapping",
            score=0.9,
            suggest_when="Test condition"
        )
        
        assert s.doc_id == "MR-07_05"
        assert s.name == "Test Tool"
        assert s.score == 0.9
        assert s.source == "mapping"


class TestIntegration:
    """Test di integrazione end-to-end"""
    
    def test_full_flow_actionable(self, suggester):
        """Flow completo per query azionabile"""
        query = "Ho una non conformità su un pezzo lavorato"
        
        # Step 1: Intent detection
        assert suggester.is_actionable_query(query) == True
        
        # Step 2: Mapping match
        mapping_results = suggester.match_from_mapping(query)
        assert len(mapping_results) > 0
        
        # Step 3: Suggest tools
        suggestions = suggester.suggest_tools(query)
        assert len(suggestions) > 0
        assert len(suggestions) <= 2
        
        # Step 4: Format
        formatted = suggester.format_suggestions_for_ui(suggestions)
        assert len(formatted) > 0
        assert "🛠️" in formatted
    
    def test_full_flow_informational(self, suggester):
        """Flow completo per query informativa"""
        query = "Cos'è una procedura di sistema?"
        
        # Step 1: Intent detection
        assert suggester.is_actionable_query(query) == False
        
        # Step 2: Suggest tools (should be empty)
        suggestions = suggester.suggest_tools(query)
        assert len(suggestions) == 0
        
        # Step 3: Format (should be empty)
        formatted = suggester.format_suggestions_for_ui(suggestions)
        assert formatted == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

