"""
Test per R19 - Gap Detector e Gap Store
Verifica rilevamento lacune e persistenza segnalazioni

Run: pytest tests/test_gap_detector.py -v
"""

import pytest
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analytics.gap_detector import GapDetector, GapDetection, GapSignal
from src.analytics.gap_store import GapStore, GapReport


# ============================================================
# FIXTURES
# ============================================================

class MockSource:
    """Mock per RetrievedDoc"""
    def __init__(self, doc_id: str, text: str, score: float):
        self.doc_id = doc_id
        self.text = text
        self.score = score


@pytest.fixture
def detector():
    """Fixture per GapDetector senza glossario"""
    return GapDetector(glossary_resolver=None)


@pytest.fixture
def temp_store():
    """Fixture per GapStore con path temporaneo"""
    temp_dir = tempfile.mkdtemp()
    store = GapStore(persist_path=f"{temp_dir}/gap_test.json")
    yield store
    shutil.rmtree(temp_dir)


# ============================================================
# TEST GAP DETECTION
# ============================================================

class TestGapSignals:
    """Test per singoli segnali di gap"""
    
    def test_no_sources_signal(self, detector):
        """Nessun documento = segnale forte"""
        gap = detector.detect_gap(
            query="Cos'è XYZ?",
            response="Non ho informazioni su XYZ.",
            sources=[]
        )
        
        assert GapSignal.NO_SOURCES in gap.signals
        assert gap.gap_score >= 0.4
    
    def test_low_score_signal(self, detector):
        """Score basso = segnale"""
        sources = [MockSource("PS-01_01", "testo generico", 0.25)]
        
        gap = detector.detect_gap(
            query="Cos'è ABC?",
            response="Risposta generica",
            sources=sources
        )
        
        assert GapSignal.LOW_RETRIEVAL_SCORE in gap.signals
    
    def test_high_score_no_signal(self, detector):
        """Score alto = nessun segnale score"""
        sources = [MockSource("PS-01_01", "testo rilevante", 0.85)]
        
        gap = detector.detect_gap(
            query="Come gestire NC?",
            response="La procedura PS-01_01 definisce...",
            sources=sources
        )
        
        assert GapSignal.LOW_RETRIEVAL_SCORE not in gap.signals
        assert GapSignal.NO_SOURCES not in gap.signals
    
    def test_llm_uncertainty_signal(self, detector):
        """LLM incerto = segnale"""
        sources = [MockSource("PS-01_01", "testo", 0.5)]
        
        gap = detector.detect_gap(
            query="Cosa significa WCM?",
            response="Non ho trovato una definizione specifica di WCM nei documenti.",
            sources=sources
        )
        
        assert GapSignal.LLM_UNCERTAINTY in gap.signals


class TestUncertaintyPatterns:
    """Test per pattern di incertezza LLM"""
    
    @pytest.mark.parametrize("response", [
        "Non ho trovato informazioni specifiche",
        "Non risulta presente nei documenti",
        "Manca una definizione chiara",
        "Non sono in grado di rispondere",
        "Nei documenti non emerge questo concetto",
        "Non dispongo di informazioni su questo argomento",
        "Non c'è una definizione esplicita",
        "Non viene definito nei documenti",
        "Le informazioni non sono disponibili",
    ])
    def test_uncertainty_detected(self, detector, response):
        """Pattern incertezza rilevati"""
        match = detector._detect_uncertainty(response)
        assert match is not None, f"Pattern non rilevato: '{response}'"
    
    @pytest.mark.parametrize("response", [
        "La procedura PS-06_01 definisce la gestione dei rifiuti",
        "Il termine WCM significa World Class Manufacturing",
        "Secondo i documenti, il processo prevede tre fasi",
        "La risposta si trova nella sezione 4.2",
        "Confermo che la procedura è attiva dal 2020",
    ])
    def test_normal_response_no_match(self, detector, response):
        """Risposte normali non matchano"""
        match = detector._detect_uncertainty(response)
        assert match is None, f"Pattern erroneamente rilevato: '{response}'"


class TestTermExtraction:
    """Test per estrazione termine dalla query"""
    
    @pytest.mark.parametrize("query,expected", [
        ("Cos'è WCM?", "WCM"),
        ("Cosa significa FMEA?", "FMEA"),
        ("Definizione di RPN", "RPN"),
        ("Che cos'è ABC?", "ABC"),  # Acronimo diretto
        ('Spiegami "lean"', "LEAN"),
        ("Acronimo OEE", "OEE"),
    ])
    def test_term_extracted(self, detector, query, expected):
        """Termine estratto correttamente"""
        term = detector._extract_key_term(query)
        assert term == expected, f"Query: '{query}' → got {term}, expected {expected}"
    
    def test_exclude_common_acronyms(self, detector):
        """Acronimi comuni esclusi (PS, IL, MR, ISO)"""
        term = detector._extract_key_term("Cosa dice la PS-06_01?")
        # PS escluso, nessun altro termine significativo
        assert term is None or term not in ["PS", "IL", "MR", "ISO"]
    
    def test_no_term_generic_query(self, detector):
        """Query generica senza termine specifico"""
        term = detector._extract_key_term("Come funziona il sistema?")
        # Potrebbe estrarre qualcosa o None, importante non crashare
        assert term is None or isinstance(term, str)


class TestGapDetection:
    """Test per rilevamento gap complessivo"""
    
    def test_gap_detected_uncertain_response(self, detector):
        """Gap rilevato con risposta incerta"""
        gap = detector.detect_gap(
            query="Cos'è WCM?",
            response="Non ho trovato una definizione di WCM.",
            sources=[MockSource("PS-06_01", "strumenti WCM per", 0.35)]
        )
        
        assert gap.is_gap == True
        assert gap.gap_score >= 0.6
        assert gap.missing_term == "WCM"
        assert gap.suggested_action == "add_glossary"
    
    def test_no_gap_good_response(self, detector):
        """Nessun gap con risposta valida"""
        gap = detector.detect_gap(
            query="Come gestire le NC?",
            response="La gestione delle NC è definita nella procedura PS-08_01...",
            sources=[MockSource("PS-08_01", "gestione non conformità", 0.85)]
        )
        
        assert gap.is_gap == False
        assert gap.gap_score < 0.6
    
    def test_term_found_in_docs(self, detector):
        """Termine trovato nei documenti"""
        sources = [
            MockSource("PS-06_01", "Gli strumenti WCM sono fondamentali", 0.4),
            MockSource("IL-07_02", "Utilizzare WCM secondo le procedure", 0.38)
        ]
        
        gap = detector.detect_gap(
            query="Cos'è WCM?",
            response="Non ho trovato una definizione precisa di WCM.",
            sources=sources
        )
        
        assert "PS-06_01" in gap.found_in_docs
        assert "IL-07_02" in gap.found_in_docs
        assert GapSignal.TERM_NO_DEFINITION in gap.signals
    
    def test_snippets_extracted(self, detector):
        """Snippet estratti correttamente"""
        sources = [
            MockSource("PS-06_01", "Gli strumenti WCM sono utilizzati per il miglioramento continuo", 0.4)
        ]
        
        gap = detector.detect_gap(
            query="Cos'è WCM?",
            response="Non trovo definizione.",
            sources=sources
        )
        
        if gap.snippets:
            assert "WCM" in gap.snippets[0] or "wcm" in gap.snippets[0].lower()


class TestSuggestedAction:
    """Test per azioni suggerite"""
    
    def test_add_glossary_action(self, detector):
        """Suggerisce aggiunta glossario"""
        gap = detector.detect_gap(
            query="Cos'è ABC?",
            response="Non ho trovato ABC.",
            sources=[]
        )
        
        # Con termine mancante e no glossary, suggerisce add_glossary
        if gap.missing_term:
            assert gap.suggested_action == "add_glossary"
    
    def test_request_docs_action(self, detector):
        """Suggerisce richiesta documenti"""
        gap = detector.detect_gap(
            query="Come funziona il processo X?",
            response="Non ho informazioni.",
            sources=[]
        )
        
        # Senza termine specifico, potrebbe suggerire request_docs
        assert gap.suggested_action in ["add_glossary", "request_docs"]


# ============================================================
# TEST GAP STORE
# ============================================================

class TestGapStore:
    """Test per persistenza segnalazioni"""
    
    def test_report_new_gap(self, temp_store):
        """Nuova segnalazione creata"""
        report = temp_store.report_gap(
            term="WCM",
            query="Cos'è WCM?",
            found_in_docs=["PS-06_01"],
            user_id="user_1"
        )
        
        assert report.term == "WCM"
        assert report.report_count == 1
        assert report.status == "pending"
        assert "user_1" in report.reporters
    
    def test_increment_existing(self, temp_store):
        """Segnalazione duplicata incrementa contatore"""
        temp_store.report_gap("WCM", "Q1", ["PS-01"], "user_1")
        report2 = temp_store.report_gap("wcm", "Q2", ["IL-01"], "user_2")
        
        assert report2.report_count == 2
        assert "user_1" in report2.reporters
        assert "user_2" in report2.reporters
        assert "PS-01" in report2.found_in_docs
        assert "IL-01" in report2.found_in_docs
    
    def test_get_by_term(self, temp_store):
        """Recupera per termine"""
        temp_store.report_gap("FMEA", "Q1", [], "user_1")
        
        report = temp_store.get_by_term("fmea")  # Lowercase
        assert report is not None
        assert report.term == "FMEA"
    
    def test_get_pending_ordered(self, temp_store):
        """Pending ordinati per conteggio"""
        temp_store.report_gap("A", "Q", [], "u1")
        temp_store.report_gap("B", "Q", [], "u1")
        temp_store.report_gap("B", "Q", [], "u2")  # B = 2
        temp_store.report_gap("B", "Q", [], "u3")  # B = 3
        temp_store.report_gap("C", "Q", [], "u1")
        
        pending = temp_store.get_pending()
        
        assert len(pending) == 3
        assert pending[0].term == "B"  # 3 segnalazioni
        assert pending[0].report_count == 3
    
    def test_mark_added(self, temp_store):
        """Admin marca come aggiunto"""
        report = temp_store.report_gap("WCM", "Q", [], "u1")
        
        temp_store.mark_added(report.id, "Aggiunto al glossario")
        
        updated = temp_store.get(report.id)
        assert updated.status == "added"
        assert "Aggiunto" in updated.admin_note
    
    def test_mark_rejected(self, temp_store):
        """Admin rifiuta"""
        report = temp_store.report_gap("XYZ", "Q", [], "u1")
        
        temp_store.mark_rejected(report.id, "Non rilevante")
        
        updated = temp_store.get(report.id)
        assert updated.status == "rejected"
        assert "Non rilevante" in updated.admin_note
    
    def test_get_stats(self, temp_store):
        """Statistiche corrette"""
        r1 = temp_store.report_gap("A", "Q", [], "u1")
        r2 = temp_store.report_gap("B", "Q", [], "u1")
        temp_store.mark_added(r1.id, "")
        
        stats = temp_store.get_stats()
        
        assert stats["total"] == 2
        assert stats["pending"] == 1
        assert stats["added"] == 1
    
    def test_persistence(self, temp_store):
        """Dati persistiti su file"""
        temp_store.report_gap("TEST", "Query", ["DOC1"], "user_1")
        
        # Crea nuovo store stesso path
        store2 = GapStore(persist_path=temp_store.persist_path)
        
        assert len(store2.get_all()) == 1
        assert store2.get_by_term("TEST") is not None


class TestGapReport:
    """Test per dataclass GapReport"""
    
    def test_to_dict(self):
        """Serializzazione JSON"""
        report = GapReport(
            id="gap_123",
            term="WCM",
            query_original="Cos'è WCM?",
            found_in_docs=["PS-06_01"],
            reported_by="user_1",
            reported_at="2025-12-08T10:00:00"
        )
        
        data = report.to_dict()
        
        assert data["id"] == "gap_123"
        assert data["term"] == "WCM"
        assert "PS-06_01" in data["found_in_docs"]
    
    def test_from_dict(self):
        """Deserializzazione JSON"""
        data = {
            "id": "gap_456",
            "term": "FMEA",
            "query_original": "Q",
            "found_in_docs": [],
            "snippets": [],
            "reported_by": "u1",
            "reported_at": "2025-12-08",
            "report_count": 5,
            "reporters": ["u1", "u2"],
            "status": "pending",
            "admin_note": None,
            "resolved_at": None
        }
        
        report = GapReport.from_dict(data)
        
        assert report.term == "FMEA"
        assert report.report_count == 5


class TestEdgeCases:
    """Test per casi limite"""
    
    def test_empty_query(self, detector):
        """Query vuota non crashare"""
        gap = detector.detect_gap(
            query="",
            response="Risposta",
            sources=[]
        )
        
        assert gap is not None
        assert gap.missing_term is None
    
    def test_empty_response(self, detector):
        """Risposta vuota"""
        gap = detector.detect_gap(
            query="Test?",
            response="",
            sources=[]
        )
        
        assert gap is not None
    
    def test_very_long_response(self, detector):
        """Risposta molto lunga"""
        long_response = "Testo normale. " * 1000
        
        gap = detector.detect_gap(
            query="Test?",
            response=long_response,
            sources=[]
        )
        
        assert gap is not None
        assert GapSignal.LLM_UNCERTAINTY not in gap.signals


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

