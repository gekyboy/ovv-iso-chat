"""
Test suite per R23: HyDE (Hypothetical Document Embeddings)

Verifica:
1. HyDEGenerator funziona correttamente
2. Generazione documento ipotetico
3. Detection tipo documento
4. Skip per query definitorie
5. Cache funziona
6. Weighted embedding combination
7. Integrazione pipeline
"""

import pytest
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestHyDEGenerator:
    """Test per HyDEGenerator"""
    
    @pytest.fixture
    def generator(self):
        from integration.hyde import HyDEGenerator
        config = {
            "hyde": {
                "enabled": True,
                "skip_for_definition_queries": True,
                "generation": {"max_length": 150},
                "cache": {"enabled": True, "max_entries": 100}
            }
        }
        return HyDEGenerator(config)
    
    def test_tc01_detect_doc_type_ps(self, generator):
        """TC01: Rileva tipo PS per query procedurali"""
        assert generator._detect_doc_type("procedura gestione rifiuti") == "PS"
        assert generator._detect_doc_type("chi deve approvare il documento") == "PS"
        assert generator._detect_doc_type("responsabilità del RSGI") == "PS"
    
    def test_tc02_detect_doc_type_il(self, generator):
        """TC02: Rileva tipo IL per query operative"""
        assert generator._detect_doc_type("come fare la manutenzione preventiva") == "IL"
        assert generator._detect_doc_type("istruzione operativa taratura") == "IL"
        assert generator._detect_doc_type("passaggi per eseguire controllo") == "IL"
    
    def test_tc03_detect_doc_type_mr(self, generator):
        """TC03: Rileva tipo MR per query su moduli"""
        assert generator._detect_doc_type("modulo registrazione non conformità") == "MR"
        assert generator._detect_doc_type("compilare il form NC") == "MR"
        assert generator._detect_doc_type("check list controllo qualità") == "MR"
    
    def test_tc04_detect_doc_type_tool(self, generator):
        """TC04: Rileva tipo TOOL per query su strumenti"""
        assert generator._detect_doc_type("strumento 5S") == "TOOL"
        assert generator._detect_doc_type("tool FMEA") == "TOOL"
        assert generator._detect_doc_type("metodologia PDCA") == "TOOL"
    
    def test_tc05_detect_doc_type_general(self, generator):
        """TC05: Rileva tipo GENERAL per query generiche"""
        assert generator._detect_doc_type("documentazione ISO") == "GENERAL"
        assert generator._detect_doc_type("sistema gestione integrato") == "GENERAL"


class TestHyDESkipLogic:
    """Test per logica skip HyDE"""
    
    @pytest.fixture
    def generator(self):
        from integration.hyde import HyDEGenerator
        config = {"hyde": {"enabled": True, "skip_for_definition_queries": True}}
        return HyDEGenerator(config)
    
    def test_tc06_skip_cosa_significa(self, generator):
        """TC06: Skip per 'cosa significa X?'"""
        assert generator._should_skip("cosa significa WCM?") == True
        assert generator._should_skip("Cosa significa FMEA?") == True
    
    def test_tc07_skip_cos_e(self, generator):
        """TC07: Skip per 'cos'è X?'"""
        assert generator._should_skip("cos'è una NC?") == True
        assert generator._should_skip("che cos'è il PDCA?") == True
    
    def test_tc08_skip_definizione(self, generator):
        """TC08: Skip per 'definizione di X'"""
        assert generator._should_skip("definizione di SGI") == True
    
    def test_tc09_skip_short_query(self, generator):
        """TC09: Skip per query troppo corte"""
        assert generator._should_skip("rifiuti") == True
        assert generator._should_skip("NC") == True
        assert generator._should_skip("audit") == True
    
    def test_tc10_not_skip_procedural(self, generator):
        """TC10: NON skip per query procedurali"""
        assert generator._should_skip("come gestire i rifiuti pericolosi") == False
        assert generator._should_skip("procedura per audit interni annuali") == False
        assert generator._should_skip("passaggi per compilare modulo NC") == False
    
    def test_tc11_skip_when_disabled(self, generator):
        """TC11: Skip se HyDE disabilitato"""
        generator.enabled = False
        assert generator._should_skip("come gestire i rifiuti") == True


class TestHyDETemplates:
    """Test per template documento ipotetico"""
    
    def test_tc12_ps_template_has_keywords(self):
        """TC12: Template PS contiene keywords corrette"""
        from integration.hyde import HyDEGenerator
        template = HyDEGenerator.TEMPLATES["PS"]
        assert "Procedura di Sistema" in template
        assert "responsabilità" in template.lower()
        assert "ISO" in template
    
    def test_tc13_il_template_has_keywords(self):
        """TC13: Template IL contiene keywords corrette"""
        from integration.hyde import HyDEGenerator
        template = HyDEGenerator.TEMPLATES["IL"]
        assert "Istruzione di Lavoro" in template
        assert "operativ" in template.lower()
        assert "passaggi" in template.lower()
    
    def test_tc14_mr_template_has_keywords(self):
        """TC14: Template MR contiene keywords corrette"""
        from integration.hyde import HyDEGenerator
        template = HyDEGenerator.TEMPLATES["MR"]
        assert "Modulo di Registrazione" in template
        assert "compil" in template.lower()  # compilarlo o compilare
    
    def test_tc15_tool_template_has_keywords(self):
        """TC15: Template TOOL contiene keywords corrette"""
        from integration.hyde import HyDEGenerator
        template = HyDEGenerator.TEMPLATES["TOOL"]
        assert "strumento" in template.lower() or "WCM" in template
    
    def test_tc16_all_templates_have_query_placeholder(self):
        """TC16: Tutti i template hanno {query} placeholder"""
        from integration.hyde import HyDEGenerator
        for name, template in HyDEGenerator.TEMPLATES.items():
            assert "{query}" in template, f"Template {name} manca {'{query}'}"


class TestHyDEResult:
    """Test per HyDEResult dataclass"""
    
    def test_tc17_result_has_all_fields(self):
        """TC17: HyDEResult ha tutti i campi"""
        from integration.hyde import HyDEResult
        result = HyDEResult(
            query="test query",
            hypothetical_document="documento ipotetico",
            doc_type_hint="PS",
            generation_time_ms=150.5,
            from_cache=False
        )
        assert result.query == "test query"
        assert result.hypothetical_document == "documento ipotetico"
        assert result.doc_type_hint == "PS"
        assert result.generation_time_ms == 150.5
        assert result.from_cache == False
    
    def test_tc18_result_to_dict(self):
        """TC18: HyDEResult.to_dict() funziona"""
        from integration.hyde import HyDEResult
        result = HyDEResult("q", "doc", "IL", 100, True)
        d = result.to_dict()
        assert d["query"] == "q"
        assert d["hypothetical_document"] == "doc"
        assert d["doc_type_hint"] == "IL"
        assert d["from_cache"] == True


class TestHyDECache:
    """Test per cache HyDE"""
    
    @pytest.fixture
    def generator(self):
        from integration.hyde import HyDEGenerator
        config = {
            "hyde": {
                "enabled": True,
                "cache": {"enabled": True, "max_entries": 5, "ttl_seconds": 3600}
            }
        }
        return HyDEGenerator(config)
    
    def test_tc19_cache_key_generation(self, generator):
        """TC19: Cache key è deterministico"""
        key1 = generator._get_cache_key("test query")
        key2 = generator._get_cache_key("test query")
        key3 = generator._get_cache_key("TEST QUERY")  # case insensitive
        
        assert key1 == key2
        assert key1 == key3  # lowercase normalization
    
    def test_tc20_cache_stores_result(self, generator):
        """TC20: Cache salva risultato"""
        from integration.hyde import HyDEResult
        
        result = HyDEResult("test", "doc", "PS", 100, False)
        generator._cache["abc123"] = result
        
        assert "abc123" in generator._cache
        assert generator._cache["abc123"].hypothetical_document == "doc"
    
    def test_tc21_cache_clear(self, generator):
        """TC21: clear_cache() svuota cache"""
        from integration.hyde import HyDEResult
        
        generator._cache["key1"] = HyDEResult("q1", "d1", "PS", 100, False)
        generator._cache["key2"] = HyDEResult("q2", "d2", "IL", 100, False)
        
        assert len(generator._cache) == 2
        
        generator.clear_cache()
        
        assert len(generator._cache) == 0
    
    def test_tc22_cache_cleanup_max_entries(self, generator):
        """TC22: Cache cleanup rimuove eccesso"""
        from integration.hyde import HyDEResult
        from datetime import datetime, timedelta
        
        # Inserisci 10 entry (max è 5)
        for i in range(10):
            result = HyDEResult(f"q{i}", f"d{i}", "PS", 100, False)
            result.timestamp = datetime.now() - timedelta(seconds=i*10)
            generator._cache[f"key{i}"] = result
        
        generator._cleanup_cache()
        
        # Deve avere max 5 entry
        assert len(generator._cache) <= 5


class TestWeightedEmbedding:
    """Test per combinazione embedding pesata"""
    
    @pytest.fixture
    def pipeline(self):
        from integration.rag_pipeline import RAGPipeline
        return RAGPipeline(config_path="config/config.yaml")
    
    def test_tc23_combine_two_embeddings(self, pipeline):
        """TC23: Combina 2 embedding con pesi"""
        emb1 = [1.0, 0.0, 0.0]
        emb2 = [0.0, 1.0, 0.0]
        weights = [0.5, 0.5]
        
        result = pipeline._combine_embeddings_weighted([emb1, emb2], weights)
        
        # Deve essere normalizzato (unit vector)
        import math
        norm = math.sqrt(sum(x**2 for x in result))
        assert abs(norm - 1.0) < 0.01
    
    def test_tc24_combine_three_embeddings(self, pipeline):
        """TC24: Combina 3 embedding (caso R23)"""
        emb_query = [1.0, 0.0, 0.0, 0.0]
        emb_expanded = [0.0, 1.0, 0.0, 0.0]
        emb_hyde = [0.0, 0.0, 1.0, 0.0]
        weights = [0.25, 0.35, 0.40]
        
        result = pipeline._combine_embeddings_weighted(
            [emb_query, emb_expanded, emb_hyde],
            weights
        )
        
        assert len(result) == 4
        
        # Verifica normalizzazione
        import math
        norm = math.sqrt(sum(x**2 for x in result))
        assert abs(norm - 1.0) < 0.01
    
    def test_tc25_weights_normalized(self, pipeline):
        """TC25: Pesi vengono normalizzati automaticamente"""
        emb1 = [1.0, 0.0]
        emb2 = [0.0, 1.0]
        # Pesi non sommano a 1
        weights = [1.0, 3.0]
        
        # Non deve fallire
        result = pipeline._combine_embeddings_weighted([emb1, emb2], weights)
        assert len(result) == 2
    
    def test_tc26_mismatched_lengths_raises(self, pipeline):
        """TC26: Errore se embedding/weights hanno lunghezze diverse"""
        emb1 = [1.0, 0.0]
        emb2 = [0.0, 1.0]
        weights = [0.5]  # Solo 1 peso per 2 embedding
        
        with pytest.raises(ValueError):
            pipeline._combine_embeddings_weighted([emb1, emb2], weights)


class TestHyDEIntegration:
    """Test integrazione HyDE nel pipeline"""
    
    @pytest.fixture
    def pipeline(self):
        from integration.rag_pipeline import RAGPipeline
        return RAGPipeline(config_path="config/config.yaml")
    
    def test_tc27_hyde_generator_property(self, pipeline):
        """TC27: Property hyde_generator funziona"""
        gen = pipeline.hyde_generator
        # Può essere None se LLM non disponibile, ma non deve crashare
        assert gen is None or hasattr(gen, 'generate')
    
    def test_tc28_hyde_config_loaded(self, pipeline):
        """TC28: Config HyDE caricata"""
        hyde_config = pipeline.config.get("hyde", {})
        assert "enabled" in hyde_config
        assert "generation" in hyde_config
        assert "embedding" in hyde_config


class TestHyDEResponseClean:
    """Test per pulizia risposta LLM"""
    
    @pytest.fixture
    def generator(self):
        from integration.hyde import HyDEGenerator
        return HyDEGenerator({"hyde": {"enabled": True, "generation": {"max_length": 100}}})
    
    def test_tc29_removes_think_tags(self, generator):
        """TC29: Rimuove tag <think>"""
        response = "<think>thinking...</think>Il documento descrive..."
        cleaned = generator._clean_response(response)
        assert "<think>" not in cleaned
        assert "thinking" not in cleaned
        assert "Il documento descrive" in cleaned
    
    def test_tc30_removes_prefixes(self, generator):
        """TC30: Rimuove prefissi comuni"""
        response = "Ecco il documento: La procedura prevede..."
        cleaned = generator._clean_response(response)
        assert "Ecco il documento:" not in cleaned
        assert "La procedura prevede" in cleaned
    
    def test_tc31_normalizes_whitespace(self, generator):
        """TC31: Normalizza whitespace"""
        response = "La   procedura\n\nprevede   vari   passaggi."
        cleaned = generator._clean_response(response)
        assert "  " not in cleaned
        assert "\n" not in cleaned


class TestHyDEStats:
    """Test per statistiche HyDE"""
    
    def test_tc32_get_stats(self):
        """TC32: get_stats() ritorna info corrette"""
        from integration.hyde import HyDEGenerator
        config = {
            "hyde": {
                "enabled": True,
                "cache": {"enabled": True, "max_entries": 100}
            }
        }
        gen = HyDEGenerator(config)
        
        stats = gen.get_stats()
        
        assert "enabled" in stats
        assert "cache_enabled" in stats
        assert "cache_entries" in stats
        assert stats["enabled"] == True


def run_all_tests():
    """Esegue tutti i test"""
    print("=" * 70)
    print("R23: TEST HyDE (Hypothetical Document Embeddings)")
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

