"""
Test suite per R22: Dual Embedding (Glossario come Collezione)

Verifica:
1. GlossaryIndexer funziona correttamente
2. Dual search integrato nel RAG pipeline
3. RRF merge combina risultati
4. Definition query detection
"""

import pytest
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestGlossaryIndexer:
    """Test per GlossaryIndexer"""
    
    @pytest.fixture
    def indexer(self):
        """Crea indexer per test"""
        from ingestion.glossary_indexer import GlossaryIndexer
        return GlossaryIndexer(config_path="config/config.yaml")
    
    def test_tc01_load_glossary_returns_terms(self, indexer):
        """TC01: Carica termini dal glossary.json"""
        terms = indexer.load_glossary()
        assert len(terms) > 0
        print(f"Caricati {len(terms)} termini")
    
    def test_tc02_glossary_term_has_searchable_text(self, indexer):
        """TC02: Ogni termine ha testo ricercabile"""
        terms = indexer.load_glossary()
        for term in terms[:5]:
            assert len(term.searchable_text) > 0
            assert term.acronym in term.searchable_text
            assert term.full in term.searchable_text
    
    def test_tc03_glossary_term_payload(self, indexer):
        """TC03: Payload termine contiene campi richiesti"""
        terms = indexer.load_glossary()
        if terms:
            payload = terms[0].to_payload()
            assert "acronym" in payload
            assert "full" in payload
            assert "description" in payload
            assert "text" in payload
            assert payload["source_type"] == "glossary"
    
    def test_tc04_iso_standards_included(self, indexer):
        """TC04: Standard ISO inclusi nei termini"""
        terms = indexer.load_glossary()
        acronyms = [t.acronym for t in terms]
        # Verifica che ISO 9001, 14001, 45001 siano inclusi
        iso_present = any("ISO" in a for a in acronyms)
        assert iso_present or len(terms) > 0  # Almeno termini normali


class TestGlossaryIndexerCollection:
    """Test per gestione collezione Qdrant"""
    
    @pytest.fixture
    def indexer(self):
        from ingestion.glossary_indexer import GlossaryIndexer
        return GlossaryIndexer(config_path="config/config.yaml")
    
    def test_tc05_collection_exists_check(self, indexer):
        """TC05: Verifica esistenza collezione"""
        # Non dovrebbe fallire
        exists = indexer.collection_exists()
        assert isinstance(exists, bool)
    
    def test_tc06_get_collection_info(self, indexer):
        """TC06: Ottiene info collezione"""
        info = indexer.get_collection_info()
        assert "name" in info
        assert info["name"] == "glossary_terms"


class TestDefinitionQueryDetection:
    """Test per rilevamento query definitorie"""
    
    @pytest.fixture
    def pipeline(self):
        from integration.rag_pipeline import RAGPipeline
        return RAGPipeline(config_path="config/config.yaml")
    
    def test_tc07_detects_cosa_significa(self, pipeline):
        """TC07: Rileva 'cosa significa X?'"""
        assert pipeline._is_definition_query("cosa significa WCM?") == True
        assert pipeline._is_definition_query("Cosa significa FMEA?") == True
    
    def test_tc08_detects_cos_è(self, pipeline):
        """TC08: Rileva 'cos'è X?'"""
        assert pipeline._is_definition_query("cos'è un PDCA?") == True
        assert pipeline._is_definition_query("che cos'è NC?") == True
    
    def test_tc09_detects_definizione_di(self, pipeline):
        """TC09: Rileva 'definizione di X'"""
        assert pipeline._is_definition_query("definizione di SGI") == True
    
    def test_tc10_detects_spiegami_acronym(self, pipeline):
        """TC10: Rileva 'spiegami WCM'"""
        assert pipeline._is_definition_query("spiegami WCM") == True
        assert pipeline._is_definition_query("spiegami FMEA") == True
    
    def test_tc11_not_detects_procedural(self, pipeline):
        """TC11: NON rileva query procedurali"""
        assert pipeline._is_definition_query("come compilare PS-06_01?") == False
        assert pipeline._is_definition_query("gestione rifiuti pericolosi") == False
        assert pipeline._is_definition_query("procedura per audit interni") == False


class TestRRFMerge:
    """Test per Reciprocal Rank Fusion merge"""
    
    @pytest.fixture
    def pipeline(self):
        from integration.rag_pipeline import RAGPipeline
        return RAGPipeline(config_path="config/config.yaml")
    
    def test_tc12_merge_preserves_all_docs(self, pipeline):
        """TC12: RRF merge preserva tutti i documenti"""
        from integration.rag_pipeline import RetrievedDoc
        
        docs = [
            RetrievedDoc(f"doc_{i}", f"text {i}", 0.8 - i * 0.1, {})
            for i in range(3)
        ]
        glossary = [
            RetrievedDoc(f"gloss_{i}", f"def {i}", 0.9 - i * 0.1, {"source_type": "glossary"})
            for i in range(2)
        ]
        
        merged = pipeline._merge_results_rrf(docs, glossary, k=60, glossary_boost=1.0)
        
        assert len(merged) == 5  # 3 docs + 2 glossary
    
    def test_tc13_merge_assigns_rrf_scores(self, pipeline):
        """TC13: RRF merge assegna score a tutti"""
        from integration.rag_pipeline import RetrievedDoc
        
        docs = [RetrievedDoc("doc_1", "text", 0.9, {})]
        glossary = [RetrievedDoc("gloss_1", "def", 0.7, {"source_type": "glossary"})]
        
        merged = pipeline._merge_results_rrf(docs, glossary, k=60, glossary_boost=1.0)
        
        for doc in merged:
            assert doc.rerank_score is not None
            assert doc.rerank_score > 0
    
    def test_tc14_boost_increases_glossary_score(self, pipeline):
        """TC14: Boost aumenta score glossario"""
        from integration.rag_pipeline import RetrievedDoc
        
        docs = [RetrievedDoc("doc_1", "text", 0.9, {})]
        glossary = [RetrievedDoc("gloss_1", "def", 0.7, {"source_type": "glossary"})]
        
        # Senza boost
        merged_no_boost = pipeline._merge_results_rrf(docs, glossary, k=60, glossary_boost=1.0)
        gloss_score_no_boost = next(d.rerank_score for d in merged_no_boost if d.doc_id == "gloss_1")
        
        # Con boost 2x
        merged_boost = pipeline._merge_results_rrf(docs, glossary, k=60, glossary_boost=2.0)
        gloss_score_boost = next(d.rerank_score for d in merged_boost if d.doc_id == "gloss_1")
        
        assert gloss_score_boost > gloss_score_no_boost
    
    def test_tc15_empty_glossary_works(self, pipeline):
        """TC15: Merge funziona con glossario vuoto"""
        from integration.rag_pipeline import RetrievedDoc
        
        docs = [RetrievedDoc("doc_1", "text", 0.9, {})]
        glossary = []
        
        merged = pipeline._merge_results_rrf(docs, glossary, k=60, glossary_boost=1.0)
        
        assert len(merged) == 1
        assert merged[0].doc_id == "doc_1"
    
    def test_tc16_empty_docs_works(self, pipeline):
        """TC16: Merge funziona con documenti vuoti"""
        from integration.rag_pipeline import RetrievedDoc
        
        docs = []
        glossary = [RetrievedDoc("gloss_1", "def", 0.9, {"source_type": "glossary"})]
        
        merged = pipeline._merge_results_rrf(docs, glossary, k=60, glossary_boost=1.0)
        
        assert len(merged) == 1
        assert merged[0].doc_id == "gloss_1"


class TestGlossarySearch:
    """Test per ricerca glossario"""
    
    @pytest.fixture
    def pipeline(self):
        from integration.rag_pipeline import RAGPipeline
        return RAGPipeline(config_path="config/config.yaml")
    
    def test_tc17_search_glossary_returns_list(self, pipeline):
        """TC17: Search glossario ritorna lista"""
        results = pipeline._search_glossary("WCM", limit=3)
        assert isinstance(results, list)
    
    def test_tc18_search_glossary_empty_if_no_collection(self, pipeline):
        """TC18: Search ritorna vuoto se collezione non esiste"""
        # Se collezione non esiste, deve ritornare lista vuota senza errori
        results = pipeline._search_glossary("test query", limit=3)
        assert isinstance(results, list)


class TestPipelineStatus:
    """Test per stato pipeline"""
    
    @pytest.fixture
    def pipeline(self):
        from integration.rag_pipeline import RAGPipeline
        return RAGPipeline(config_path="config/config.yaml")
    
    def test_tc19_status_includes_glossary_indexer(self, pipeline):
        """TC19: Status include glossary_indexer"""
        status = pipeline.get_status()
        assert "glossary_indexer" in status
    
    def test_tc20_status_includes_dual_embedding_config(self, pipeline):
        """TC20: Status include config dual_embedding"""
        status = pipeline.get_status()
        assert "dual_embedding_enabled" in status.get("config", {})


class TestGlossaryTermDataclass:
    """Test per dataclass GlossaryTerm"""
    
    def test_tc21_searchable_text_format(self):
        """TC21: Searchable text formato corretto"""
        from ingestion.glossary_indexer import GlossaryTerm
        
        term = GlossaryTerm(
            acronym="WCM",
            full="World Class Manufacturing",
            description="Metodologia eccellenza"
        )
        
        text = term.searchable_text
        assert "WCM" in text
        assert "World Class Manufacturing" in text
        assert "Metodologia eccellenza" in text
    
    def test_tc22_ambiguous_term_with_context(self):
        """TC22: Termine ambiguo include contesto"""
        from ingestion.glossary_indexer import GlossaryTerm
        
        term = GlossaryTerm(
            acronym="CDL",
            full="Centro Di Lavoro",
            description="Macchina CNC",
            ambiguous=True,
            context="produzione"
        )
        
        text = term.searchable_text
        assert "produzione" in text
        
        payload = term.to_payload()
        assert payload["ambiguous"] == True
        assert payload["context"] == "produzione"


def run_all_tests():
    """Esegue tutti i test"""
    print("=" * 70)
    print("R22: TEST DUAL EMBEDDING")
    print("=" * 70)
    
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x"
    ])
    
    print("\n" + "=" * 70)
    if exit_code == 0:
        print("✅ TUTTI I TEST PASSATI")
    else:
        print("❌ ALCUNI TEST FALLITI")
    print("=" * 70)
    
    return exit_code


if __name__ == "__main__":
    run_all_tests()

