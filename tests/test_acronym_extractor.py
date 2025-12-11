"""
Test suite per AcronymExtractor (R05)
Estrazione automatica acronimi dai documenti

Created: 2025-12-08
"""

import pytest
import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Aggiungi percorso root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analytics.acronym_extractor import (
    AcronymExtractor, 
    AcronymProposal, 
    PatternType
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def temp_proposals_file():
    """File temporaneo per proposte"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write('{}')
        temp_path = f.name
    yield temp_path
    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def extractor(temp_proposals_file):
    """Extractor senza glossario"""
    return AcronymExtractor(
        glossary_resolver=None,
        proposals_path=temp_proposals_file,
        min_confidence=0.6
    )


@pytest.fixture
def mock_glossary():
    """Glossario mock"""
    glossary = Mock()
    glossary.resolve = Mock(return_value=None)  # Nessun acronimo presente
    return glossary


@pytest.fixture
def extractor_with_glossary(temp_proposals_file, mock_glossary):
    """Extractor con glossario mock"""
    return AcronymExtractor(
        glossary_resolver=mock_glossary,
        proposals_path=temp_proposals_file,
        min_confidence=0.6
    )


# ============================================================
# TEST PATTERN EXTRACTION
# ============================================================

class TestPatternParenthesisAfter:
    """Pattern 1: ABC (Alpha Beta Gamma)"""
    
    def test_basic_match(self, extractor):
        text = "Gli strumenti del WCM (World Class Manufacturing) sono fondamentali."
        proposals = extractor.extract_from_text(text, doc_id="TEST_01")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "WCM"
        assert proposals[0].expansion == "World Class Manufacturing"
        assert proposals[0].pattern_type == PatternType.PARENTHESIS_AFTER.value
    
    def test_multiple_words(self, extractor):
        text = "La FMEA (Failure Mode and Effects Analysis) è importante."
        proposals = extractor.extract_from_text(text, doc_id="TEST_02")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "FMEA"
        assert "Failure Mode" in proposals[0].expansion
    
    def test_italian_accents(self, extractor):
        text = "La NC (Non Conformità) deve essere registrata."
        proposals = extractor.extract_from_text(text, doc_id="TEST_03")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "NC"
        assert "Conformità" in proposals[0].expansion
    
    def test_numbers_in_acronym(self, extractor):
        text = "Il 5S (Sort Set Shine Standardize Sustain) migliora l'ordine."
        proposals = extractor.extract_from_text(text, doc_id="TEST_04")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "5S"


class TestPatternParenthesisBefore:
    """Pattern 2: (Alpha Beta Gamma) ABC"""
    
    def test_basic_match(self, extractor):
        text = "Il (Total Quality Management) TQM è un approccio sistemico."
        proposals = extractor.extract_from_text(text, doc_id="TEST_05")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "TQM"
        assert proposals[0].expansion == "Total Quality Management"


class TestPatternSignifica:
    """Pattern 3: ABC significa Alpha Beta"""
    
    def test_significa(self, extractor):
        text = "DMAIC significa Define Measure Analyze Improve Control."
        proposals = extractor.extract_from_text(text, doc_id="TEST_06")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "DMAIC"
        assert proposals[0].pattern_type == PatternType.SIGNIFICA.value
    
    def test_vuol_dire(self, extractor):
        text = "OEE vuol dire Overall Equipment Effectiveness."
        proposals = extractor.extract_from_text(text, doc_id="TEST_07")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "OEE"
    
    def test_sta_per(self, extractor):
        text = "TPM sta per Total Productive Maintenance."
        proposals = extractor.extract_from_text(text, doc_id="TEST_08")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "TPM"


class TestPatternEquals:
    """Pattern 4: ABC = Alpha Beta"""
    
    def test_equals_sign(self, extractor):
        text = "PDCA = Plan Do Check Act"
        proposals = extractor.extract_from_text(text, doc_id="TEST_09")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "PDCA"
        assert proposals[0].pattern_type == PatternType.EQUALS.value
    
    def test_colon(self, extractor):
        text = "RPN: Risk Priority Number"
        proposals = extractor.extract_from_text(text, doc_id="TEST_10")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "RPN"


class TestPatternOvvero:
    """Pattern 5: ABC, ovvero Alpha Beta"""
    
    def test_ovvero(self, extractor):
        text = "Il KAIZEN, ovvero Miglioramento Continuo Giapponese."
        proposals = extractor.extract_from_text(text, doc_id="TEST_11")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "KAIZEN"
    
    def test_cioe(self, extractor):
        text = "L'OEE, cioè Overall Equipment Effectiveness, misura l'efficienza."
        proposals = extractor.extract_from_text(text, doc_id="TEST_12")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "OEE"
    
    def test_ossia(self, extractor):
        # Nota: Il pattern cattura fino al prossimo terminatore
        text = "Il JIT, ossia Just In Time."
        proposals = extractor.extract_from_text(text, doc_id="TEST_13")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "JIT"
        assert "Just In Time" in proposals[0].expansion


# ============================================================
# TEST VALIDATION
# ============================================================

class TestValidation:
    """Test validazione e confidence"""
    
    def test_blacklist_filtered(self, extractor):
        """Acronimi in blacklist devono essere filtrati"""
        text = "Il PS (Procedura Sistema) descrive il processo."
        proposals = extractor.extract_from_text(text, doc_id="TEST_14")
        
        # PS è in blacklist
        assert len(proposals) == 0
    
    def test_iso_blacklist(self, extractor):
        """ISO deve essere filtrato"""
        text = "L'ISO (International Organization) è uno standard."
        proposals = extractor.extract_from_text(text, doc_id="TEST_15")
        
        assert len(proposals) == 0
    
    def test_article_blacklist(self, extractor):
        """Articoli italiani devono essere filtrati"""
        text = "IL (Istruzione Lavoro) definisce le operazioni."
        proposals = extractor.extract_from_text(text, doc_id="TEST_16")
        
        # IL è in blacklist
        assert len(proposals) == 0
    
    def test_too_short_acronym(self, extractor):
        """Acronimo troppo corto (1 char)"""
        confidence = extractor._validate("A", "Something Long")
        assert confidence == 0.0
    
    def test_too_long_acronym(self, extractor):
        """Acronimo troppo lungo (>8 char)"""
        confidence = extractor._validate("VERYLONGG", "Something Long Here")
        assert confidence == 0.0
    
    def test_initials_match_perfect(self, extractor):
        """Match perfetto delle iniziali = alto confidence"""
        confidence = extractor._validate("WCM", "World Class Manufacturing")
        assert confidence >= 0.8
    
    def test_initials_match_partial(self, extractor):
        """Match parziale delle iniziali"""
        confidence = extractor._validate("NC", "Non Conformità")
        assert 0.5 <= confidence <= 0.9
    
    def test_no_initials_match(self, extractor):
        """Nessun match delle iniziali"""
        confidence = extractor._validate("XYZ", "Alpha Beta Gamma")
        # Le iniziali ABG non matchano XYZ, quindi confidence basso
        assert confidence <= 0.6
    
    def test_expansion_too_short(self, extractor):
        """Espansione troppo corta"""
        confidence = extractor._validate("AB", "Hi")
        assert confidence == 0.0
    
    def test_single_word_expansion(self, extractor):
        """Espansione con una sola parola"""
        confidence = extractor._validate("ABC", "SingleWord")
        assert confidence == 0.0


class TestAlreadyInGlossary:
    """Test skip se già nel glossario"""
    
    def test_skip_existing(self, temp_proposals_file, mock_glossary):
        """Se già nel glossario, skip"""
        # Configura glossario per ritornare definizione per WCM
        mock_glossary.resolve = Mock(return_value="World Class Manufacturing")
        
        extractor = AcronymExtractor(
            glossary_resolver=mock_glossary,
            proposals_path=temp_proposals_file
        )
        
        text = "Il WCM (World Class Manufacturing) è fondamentale."
        proposals = extractor.extract_from_text(text, doc_id="TEST_17")
        
        # Dovrebbe essere saltato perché già nel glossario
        assert len(proposals) == 0


# ============================================================
# TEST PROPOSAL MANAGEMENT
# ============================================================

class TestProposalManagement:
    """Test gestione proposte"""
    
    def test_create_proposal(self, extractor):
        """Crea nuova proposta"""
        text = "Il WCM (World Class Manufacturing) è fondamentale."
        proposals = extractor.extract_from_text(text, doc_id="TEST_18")
        
        assert len(proposals) == 1
        assert proposals[0].status == "pending"
        assert proposals[0].id.startswith("acr_")
    
    def test_update_existing_adds_doc(self, extractor):
        """Aggiorna proposta esistente aggiungendo doc"""
        text1 = "Il WCM (World Class Manufacturing) è fondamentale."
        text2 = "Gli strumenti WCM (World Class Manufacturing) includono."
        
        extractor.extract_from_text(text1, doc_id="DOC_01")
        extractor.extract_from_text(text2, doc_id="DOC_02")
        
        proposal = extractor.get_by_acronym("WCM")
        
        assert len(proposal.found_in_docs) == 2
        assert "DOC_01" in proposal.found_in_docs
        assert "DOC_02" in proposal.found_in_docs
    
    def test_get_pending(self, extractor):
        """Ottiene proposte pending"""
        texts = [
            "Il WCM (World Class Manufacturing) è fondamentale.",
            "La FMEA (Failure Mode and Effects Analysis) è importante.",
            "Il TPM (Total Productive Maintenance) migliora."
        ]
        
        for i, text in enumerate(texts):
            extractor.extract_from_text(text, doc_id=f"TEST_{i}")
        
        pending = extractor.get_pending(limit=10)
        
        assert len(pending) == 3
        # Ordinate per confidence
        assert pending[0].confidence >= pending[1].confidence
    
    def test_approve(self, extractor):
        """Approva proposta"""
        text = "Il WCM (World Class Manufacturing) è fondamentale."
        extractor.extract_from_text(text, doc_id="TEST_19")
        
        result = extractor.approve("WCM", "Test approval")
        
        assert result is not None
        assert result.status == "approved"
        assert result.admin_note == "Test approval"
    
    def test_reject(self, extractor):
        """Rifiuta proposta"""
        text = "Il WCM (World Class Manufacturing) è fondamentale."
        extractor.extract_from_text(text, doc_id="TEST_20")
        
        result = extractor.reject("WCM", "Non pertinente")
        
        assert result is not None
        assert result.status == "rejected"
        assert result.admin_note == "Non pertinente"
    
    def test_approve_nonexistent(self, extractor):
        """Approva proposta non esistente"""
        result = extractor.approve("NONEXISTENT")
        assert result is None
    
    def test_delete(self, extractor):
        """Elimina proposta"""
        text = "Il WCM (World Class Manufacturing) è fondamentale."
        extractor.extract_from_text(text, doc_id="TEST_21")
        
        assert extractor.get_by_acronym("WCM") is not None
        
        result = extractor.delete("WCM")
        
        assert result is True
        assert extractor.get_by_acronym("WCM") is None


# ============================================================
# TEST PERSISTENCE
# ============================================================

class TestPersistence:
    """Test persistenza proposte"""
    
    def test_save_and_load(self, temp_proposals_file):
        """Salva e ricarica proposte"""
        # Prima istanza - crea proposta
        ext1 = AcronymExtractor(proposals_path=temp_proposals_file)
        ext1.extract_from_text(
            "Il WCM (World Class Manufacturing) è fondamentale.",
            doc_id="TEST_22"
        )
        
        # Verifica salvataggio
        assert Path(temp_proposals_file).exists()
        
        # Seconda istanza - ricarica
        ext2 = AcronymExtractor(proposals_path=temp_proposals_file)
        
        proposal = ext2.get_by_acronym("WCM")
        assert proposal is not None
        assert proposal.acronym == "WCM"


# ============================================================
# TEST STATS
# ============================================================

class TestStats:
    """Test statistiche"""
    
    def test_stats_empty(self, extractor):
        """Stats con nessuna proposta"""
        stats = extractor.get_stats()
        
        assert stats["total"] == 0
        assert stats["pending"] == 0
    
    def test_stats_with_proposals(self, extractor):
        """Stats con proposte"""
        texts = [
            "Il WCM (World Class Manufacturing) è fondamentale.",
            "La FMEA (Failure Mode and Effects Analysis) è importante."
        ]
        
        for i, text in enumerate(texts):
            extractor.extract_from_text(text, doc_id=f"TEST_{i}")
        
        extractor.approve("WCM")
        
        stats = extractor.get_stats()
        
        assert stats["total"] == 2
        assert stats["pending"] == 1
        assert stats["approved"] == 1


# ============================================================
# TEST REAL EXAMPLES
# ============================================================

class TestRealExamples:
    """Test con esempi reali da documenti ISO"""
    
    def test_multiple_in_same_text(self, extractor):
        """Estrae multipli acronimi dallo stesso testo"""
        text = """
        Gli strumenti del WCM (World Class Manufacturing) includono:
        - PDCA (Plan Do Check Act) per il miglioramento continuo
        - FMEA (Failure Mode and Effects Analysis) per l'analisi rischi
        - OEE (Overall Equipment Effectiveness) per l'efficienza
        """
        
        proposals = extractor.extract_from_text(text, doc_id="TEST_23")
        
        acronyms = {p.acronym for p in proposals}
        
        assert "WCM" in acronyms
        assert "PDCA" in acronyms
        assert "FMEA" in acronyms
        assert "OEE" in acronyms
    
    def test_italian_iso_text(self, extractor):
        """Testo tipico ISO italiano"""
        text = """
        La NC (Non Conformità) rilevata durante l'audit deve essere
        registrata nel modulo MR. L'AC (Azione Correttiva) conseguente
        viene gestita secondo la procedura PS.
        """
        
        proposals = extractor.extract_from_text(text, doc_id="TEST_24")
        
        # NC e AC dovrebbero essere estratti (non sono in blacklist)
        # MR e PS sono in blacklist
        acronyms = {p.acronym for p in proposals}
        
        assert "NC" in acronyms
        assert "AC" in acronyms
        assert "MR" not in acronyms  # blacklist
        assert "PS" not in acronyms  # blacklist


# ============================================================
# TEST EDGE CASES
# ============================================================

class TestEdgeCases:
    """Test casi limite"""
    
    def test_empty_text(self, extractor):
        """Testo vuoto"""
        proposals = extractor.extract_from_text("", doc_id="TEST_25")
        assert len(proposals) == 0
    
    def test_no_acronyms(self, extractor):
        """Testo senza acronimi"""
        text = "Questo è un testo normale senza acronimi definiti."
        proposals = extractor.extract_from_text(text, doc_id="TEST_26")
        assert len(proposals) == 0
    
    def test_same_acronym_twice(self, extractor):
        """Stesso acronimo ripetuto nel testo"""
        text = """
        Il WCM (World Class Manufacturing) è importante.
        Il WCM (World Class Manufacturing) richiede impegno.
        """
        
        proposals = extractor.extract_from_text(text, doc_id="TEST_27")
        
        # Dovrebbe estrarre solo una volta
        assert len(proposals) == 1
    
    def test_special_characters_in_expansion(self, extractor):
        """Caratteri speciali nell'espansione"""
        text = "L'OJT (On-the-Job Training) è formazione sul campo."
        proposals = extractor.extract_from_text(text, doc_id="TEST_28")
        
        assert len(proposals) == 1
        assert proposals[0].acronym == "OJT"


# ============================================================
# RUN TESTS
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

