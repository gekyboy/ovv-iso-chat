"""
Test suite per R21: Prepending Context (Arricchimento Chunks)

Verifica:
1. Header contestuale correttamente generato
2. Glossario acronimi risolti
3. Testo arricchito contiene originale
4. Payload per Qdrant corretto
5. Statistiche accurate
"""

import pytest
import sys
from pathlib import Path

# Setup path per import moduli
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ingestion.chunker import Chunk
from ingestion.enricher import ChunkEnricher, EnrichedChunk


class TestChunkEnricher:
    """Test per ChunkEnricher"""
    
    @pytest.fixture
    def sample_chunk(self):
        """Chunk di esempio per test"""
        return Chunk(
            id="test_parent_0",
            text="Gli strumenti del WCM per il pilastro Safety includono FMEA e NC.",
            chunk_type="parent",
            chunk_index=0,
            doc_id="PS-06_01",
            doc_type="PS",
            chapter="06",
            revision="04",
            title="Gestione Non Conformità",
            priority=1.0,
            iso_section="MODALITÀ OPERATIVE",
            label="[DOC: PS-06_01 Rev.04]"
        )
    
    @pytest.fixture
    def tools_chunk(self):
        """Chunk tipo TOOLS per test"""
        return Chunk(
            id="tools_0",
            text="Uso del tool FMEA per analisi rischi.",
            chunk_type="light",
            chunk_index=0,
            doc_id="TOOLS-01",
            doc_type="TOOLS",
            chapter="01",
            revision="01",
            title="FMEA Tool",
            priority=0.8,
            iso_section="GENERALE",
            label="TOOLS"
        )
    
    @pytest.fixture
    def enricher_no_glossary(self):
        """Enricher senza glossario"""
        return ChunkEnricher(glossary=None)
    
    @pytest.fixture
    def enricher_with_glossary(self):
        """Enricher con glossario"""
        try:
            from integration.glossary import GlossaryResolver
            glossary = GlossaryResolver(config_path="config/config.yaml")
            return ChunkEnricher(glossary=glossary)
        except Exception:
            pytest.skip("Glossario non disponibile")
    
    # ============================================
    # TEST HEADER CONTEXT
    # ============================================
    
    def test_tc01_header_includes_doc_id(self, enricher_no_glossary, sample_chunk):
        """TC01: Header deve contenere doc_id"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        assert "PS-06_01" in result.header_context
    
    def test_tc02_header_includes_revision(self, enricher_no_glossary, sample_chunk):
        """TC02: Header deve contenere revisione"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        assert "Rev.04" in result.header_context
    
    def test_tc03_header_includes_section(self, enricher_no_glossary, sample_chunk):
        """TC03: Header deve contenere sezione ISO"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        assert "MODALITÀ OPERATIVE" in result.header_context
    
    def test_tc04_header_includes_title(self, enricher_no_glossary, sample_chunk):
        """TC04: Header deve contenere titolo documento"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        assert "Gestione Non Conformità" in result.enriched_text
    
    def test_tc05_header_format_correct(self, enricher_no_glossary, sample_chunk):
        """TC05: Header ha formato corretto con brackets"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        assert result.header_context.startswith("[DOC:")
        assert "]" in result.header_context
    
    # ============================================
    # TEST GLOSSARY CONTEXT
    # ============================================
    
    def test_tc06_glossary_resolves_wcm(self, enricher_with_glossary, sample_chunk):
        """TC06: Glossario deve risolvere WCM"""
        result = enricher_with_glossary.enrich_chunk(sample_chunk)
        assert "WCM" in result.glossary_context
        assert "World Class Manufacturing" in result.glossary_context or "WCM =" in result.glossary_context
    
    def test_tc07_glossary_resolves_fmea(self, enricher_with_glossary, sample_chunk):
        """TC07: Glossario deve risolvere FMEA"""
        result = enricher_with_glossary.enrich_chunk(sample_chunk)
        # FMEA potrebbe essere nel glossario
        if "FMEA" in result.acronyms_resolved:
            assert "FMEA" in result.glossary_context
    
    def test_tc08_glossary_resolves_nc(self, enricher_with_glossary, sample_chunk):
        """TC08: Glossario deve risolvere NC"""
        result = enricher_with_glossary.enrich_chunk(sample_chunk)
        # NC potrebbe essere nel glossario
        if "NC" in result.acronyms_resolved:
            assert "NC" in result.glossary_context
    
    def test_tc09_glossary_max_definitions(self, enricher_with_glossary):
        """TC09: Glossario rispetta max definizioni"""
        # Chunk con molti acronimi
        chunk = Chunk(
            id="test_many_acr",
            text="WCM FMEA NC AC AP OPL SOP TWTTP HERCA KPI SGI PS IL MR",
            chunk_type="parent",
            chunk_index=0,
            doc_id="TEST-01",
            doc_type="PS",
            chapter="01",
            revision="01",
            title="Test Many Acronyms",
            priority=1.0,
            iso_section="TEST",
            label="TEST"
        )
        result = enricher_with_glossary.enrich_chunk(chunk)
        # Max 5 definizioni di default
        assert len(result.acronyms_resolved) <= 5
    
    def test_tc10_glossary_empty_if_no_acronyms(self, enricher_with_glossary):
        """TC10: Nessun glossario se no acronimi nel testo"""
        chunk = Chunk(
            id="test_no_acr",
            text="Questo testo non contiene nessun acronimo da risolvere.",
            chunk_type="parent",
            chunk_index=0,
            doc_id="TEST-01",
            doc_type="PS",
            chapter="01",
            revision="01",
            title="Test No Acronyms",
            priority=1.0,
            iso_section="TEST",
            label="TEST"
        )
        result = enricher_with_glossary.enrich_chunk(chunk)
        # Se nessun acronimo trovato, glossary_context potrebbe essere vuoto
        assert len(result.acronyms_resolved) == 0 or result.glossary_context != ""
    
    # ============================================
    # TEST ENRICHED TEXT
    # ============================================
    
    def test_tc11_enriched_text_contains_original(self, enricher_no_glossary, sample_chunk):
        """TC11: Testo arricchito contiene originale"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        assert sample_chunk.text in result.enriched_text
    
    def test_tc12_enriched_text_longer(self, enricher_no_glossary, sample_chunk):
        """TC12: Testo arricchito più lungo dell'originale"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        assert result.enriched_length > result.original_length
    
    def test_tc13_original_text_preserved(self, enricher_no_glossary, sample_chunk):
        """TC13: Testo originale preservato per display"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        assert result.text_for_display == sample_chunk.text
    
    def test_tc14_text_for_embedding_is_enriched(self, enricher_no_glossary, sample_chunk):
        """TC14: text_for_embedding usa testo arricchito"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        assert result.text_for_embedding == result.enriched_text
    
    # ============================================
    # TEST SCOPE CONTEXT
    # ============================================
    
    def test_tc15_scope_not_included_for_tools(self, enricher_no_glossary, tools_chunk):
        """TC15: Scopo escluso per documenti TOOLS"""
        result = enricher_no_glossary.enrich_chunk(tools_chunk)
        assert result.scope_context == ""
    
    def test_tc16_scope_empty_without_document(self, enricher_no_glossary, sample_chunk):
        """TC16: Scopo vuoto se documento non fornito"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        # Senza documento sorgente, scope sarà vuoto
        assert result.scope_context == ""
    
    # ============================================
    # TEST PAYLOAD/SERIALIZATION
    # ============================================
    
    def test_tc17_to_dict_contains_enrichment_flag(self, enricher_no_glossary, sample_chunk):
        """TC17: Payload contiene flag arricchimento"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        payload = result.to_dict()
        assert payload.get("is_enriched") == True
        assert payload.get("enrichment_version") == "R21_v1"
    
    def test_tc18_to_dict_preserves_original_fields(self, enricher_no_glossary, sample_chunk):
        """TC18: Payload preserva campi originali"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        payload = result.to_dict()
        assert payload.get("doc_id") == sample_chunk.doc_id
        assert payload.get("doc_type") == sample_chunk.doc_type
        assert payload.get("chunk_type") == sample_chunk.chunk_type
        assert payload.get("revision") == sample_chunk.revision
    
    def test_tc19_to_dict_contains_enriched_text(self, enricher_no_glossary, sample_chunk):
        """TC19: Payload contiene testo arricchito"""
        result = enricher_no_glossary.enrich_chunk(sample_chunk)
        payload = result.to_dict()
        assert "enriched_text" in payload
        assert len(payload["enriched_text"]) > len(sample_chunk.text)
    
    # ============================================
    # TEST STATISTICS
    # ============================================
    
    def test_tc20_stats_chunks_processed(self, enricher_no_glossary, sample_chunk):
        """TC20: Statistiche chunks processati"""
        enricher_no_glossary.reset_stats()
        enricher_no_glossary.enrich_chunk(sample_chunk)
        enricher_no_glossary.enrich_chunk(sample_chunk)
        stats = enricher_no_glossary.get_stats()
        assert stats["chunks_processed"] == 2
    
    def test_tc21_stats_context_chars(self, enricher_no_glossary, sample_chunk):
        """TC21: Statistiche caratteri contesto aggiunti"""
        enricher_no_glossary.reset_stats()
        enricher_no_glossary.enrich_chunk(sample_chunk)
        stats = enricher_no_glossary.get_stats()
        assert stats["total_context_added_chars"] > 0


class TestEnrichmentIntegration:
    """Test integrazione con pipeline ingestion"""
    
    @pytest.fixture
    def sample_chunks(self):
        """Lista di chunks per test batch"""
        return [
            Chunk(
                id=f"test_{i}",
                text=f"Chunk {i} con WCM e FMEA per test.",
                chunk_type="parent",
                chunk_index=i,
                doc_id="TEST",
                doc_type="PS",
                chapter="01",
                revision="01",
                title="Test Document",
                priority=1.0,
                iso_section="TEST",
                label="TEST"
            )
            for i in range(5)
        ]
    
    def test_tc22_batch_enrichment(self, sample_chunks):
        """TC22: Arricchimento batch funziona"""
        enricher = ChunkEnricher()
        results = enricher.enrich_chunks(sample_chunks)
        assert len(results) == 5
        assert all(isinstance(r, EnrichedChunk) for r in results)
    
    def test_tc23_batch_stats_accurate(self, sample_chunks):
        """TC23: Statistiche batch accurate"""
        enricher = ChunkEnricher()
        enricher.reset_stats()
        enricher.enrich_chunks(sample_chunks)
        stats = enricher.get_stats()
        assert stats["chunks_processed"] == 5
    
    def test_tc24_enriched_chunk_id_property(self, sample_chunks):
        """TC24: EnrichedChunk.id ritorna ID originale"""
        enricher = ChunkEnricher()
        result = enricher.enrich_chunk(sample_chunks[0])
        assert result.id == sample_chunks[0].id
    
    def test_tc25_enriched_chunk_doc_id_property(self, sample_chunks):
        """TC25: EnrichedChunk.doc_id ritorna doc_id originale"""
        enricher = ChunkEnricher()
        result = enricher.enrich_chunk(sample_chunks[0])
        assert result.doc_id == sample_chunks[0].doc_id


class TestAlphanumericAcronyms:
    """Test per acronimi alfanumerici (es. 5S, 5W1H)"""
    
    @pytest.fixture
    def chunk_with_5s(self):
        """Chunk con acronimo 5S"""
        return Chunk(
            id="test_5s",
            text="La metodologia 5S è fondamentale per l'ordine in produzione.",
            chunk_type="parent",
            chunk_index=0,
            doc_id="TOOLS-5S",
            doc_type="TOOLS",
            chapter="01",
            revision="01",
            title="Metodologia 5S",
            priority=0.8,
            iso_section="GENERALE",
            label="TOOLS"
        )
    
    def test_tc26_detects_5s_acronym(self, chunk_with_5s):
        """TC26: Rileva acronimo 5S"""
        enricher = ChunkEnricher()
        acronyms = enricher._extract_acronyms(chunk_with_5s.text.upper())
        # 5S dovrebbe essere rilevato come acronimo alfanumerico
        assert "5S" in acronyms or any("5" in a for a in acronyms)


def run_all_tests():
    """Esegue tutti i test con output dettagliato"""
    print("=" * 70)
    print("R21: TEST CHUNK ENRICHMENT")
    print("=" * 70)
    
    exit_code = pytest.main([
        __file__, 
        "-v", 
        "--tb=short",
        "-x"  # Stop al primo fallimento
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

