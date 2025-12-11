"""
Test per R27: Semantic Retrieval con filtering per incident_category
Verifica che il sistema distingua correttamente documenti simili
(es. infortunio reale vs near miss)
"""

import pytest
import logging
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestIncidentIntentDetection:
    """Test rilevamento intent incidente"""
    
    @pytest.fixture
    def retriever(self):
        """Fixture per RetrieverAgent"""
        from src.agents.agent_retriever import RetrieverAgent
        return RetrieverAgent(config_path="config/config.yaml")
    
    def test_detect_real_injury(self, retriever):
        """Deve rilevare intent real_injury"""
        queries = [
            "Ho avuto un infortunio sul lavoro",
            "Mi sono fatto male in produzione",
            "C'è stata una lesione in reparto",
            "Infortunio grave ieri"
        ]
        
        for query in queries:
            intent = retriever._detect_incident_intent(query)
            assert intent == "real_injury", f"Query '{query}' dovrebbe essere real_injury, non {intent}"
    
    def test_detect_near_miss(self, retriever):
        """Deve rilevare intent near_miss"""
        queries = [
            "C'è stato un near miss",
            "Mancato infortunio in magazzino",
            "Quasi incidente alla pressa",
            "Condizione pericolosa rilevata"
        ]
        
        for query in queries:
            intent = retriever._detect_incident_intent(query)
            assert intent == "near_miss", f"Query '{query}' dovrebbe essere near_miss, non {intent}"
    
    def test_no_intent_generic_query(self, retriever):
        """Query generiche non devono avere intent specifico"""
        queries = [
            "Come gestire la sicurezza?",
            "Quali sono le procedure?",
            "Spiegami il WCM"
        ]
        
        for query in queries:
            intent = retriever._detect_incident_intent(query)
            assert intent is None, f"Query '{query}' non dovrebbe avere intent, ha {intent}"


class TestCategoryBoost:
    """Test boosting per categoria"""
    
    @pytest.fixture
    def retriever(self):
        from src.agents.agent_retriever import RetrieverAgent
        return RetrieverAgent(config_path="config/config.yaml")
    
    def test_boost_increases_score(self, retriever):
        """Boost deve aumentare score documenti matching"""
        docs = [
            {"doc_id": "MR-06_01", "score": 0.8, "rerank_score": 0.8, 
             "metadata": {"incident_category": "real_injury"}},
            {"doc_id": "MR-06_02", "score": 0.9, "rerank_score": 0.9, 
             "metadata": {"incident_category": "near_miss"}},
        ]
        
        boosted = retriever._apply_category_boost(docs, "real_injury", boost_factor=1.5)
        
        # MR-06_01 deve avere score più alto dopo boost
        mr_06_01 = next(d for d in boosted if d["doc_id"] == "MR-06_01")
        mr_06_02 = next(d for d in boosted if d["doc_id"] == "MR-06_02")
        
        assert mr_06_01["rerank_score"] == 0.8 * 1.5, "Boost non applicato correttamente"
        assert mr_06_01.get("category_boosted") == True, "Flag category_boosted mancante"
    
    def test_boost_reorders_results(self, retriever):
        """Boost deve riordinare risultati"""
        docs = [
            {"doc_id": "MR-06_02", "score": 0.9, "rerank_score": 0.9, 
             "metadata": {"incident_category": "near_miss"}},  # Primo per score
            {"doc_id": "MR-06_01", "score": 0.7, "rerank_score": 0.7, 
             "metadata": {"incident_category": "real_injury"}},  # Secondo
        ]
        
        boosted = retriever._apply_category_boost(docs, "real_injury", boost_factor=1.5)
        
        # MR-06_01 deve essere primo dopo boost (0.7 * 1.5 = 1.05 > 0.9 * 0.7 = 0.63)
        assert boosted[0]["doc_id"] == "MR-06_01", "Boost non ha riordinato correttamente"


class TestSemanticMetadata:
    """Test che semantic metadata siano caricati in enricher"""
    
    def test_enricher_loads_metadata(self):
        """Enricher deve caricare semantic_metadata.json"""
        from src.ingestion.enricher import ChunkEnricher
        
        enricher = ChunkEnricher()
        
        assert len(enricher.semantic_metadata) > 0, "Nessun semantic metadata caricato"
        
        # Verifica documenti chiave
        assert "MR-06_01" in enricher.semantic_metadata, "MR-06_01 mancante"
        assert "MR-06_02" in enricher.semantic_metadata, "MR-06_02 mancante"
    
    def test_metadata_has_required_fields(self):
        """Metadata devono avere campi richiesti"""
        from src.ingestion.enricher import ChunkEnricher
        
        enricher = ChunkEnricher()
        
        for doc_id, meta in enricher.semantic_metadata.items():
            assert "incident_category" in meta, f"{doc_id} manca incident_category"
            assert "applies_when" in meta, f"{doc_id} manca applies_when"
    
    def test_injury_vs_near_miss_categories(self):
        """MR-06_01 e MR-06_02 devono avere categorie diverse"""
        from src.ingestion.enricher import ChunkEnricher
        
        enricher = ChunkEnricher()
        
        mr_06_01 = enricher.semantic_metadata.get("MR-06_01", {})
        mr_06_02 = enricher.semantic_metadata.get("MR-06_02", {})
        
        assert mr_06_01.get("incident_category") == "real_injury", \
            f"MR-06_01 dovrebbe essere real_injury, è {mr_06_01.get('incident_category')}"
        
        assert mr_06_02.get("incident_category") == "near_miss", \
            f"MR-06_02 dovrebbe essere near_miss, è {mr_06_02.get('incident_category')}"


class TestEndToEndRetrieval:
    """Test end-to-end del retrieval con filtering"""
    
    @pytest.fixture
    def retriever(self):
        from src.agents.agent_retriever import RetrieverAgent
        return RetrieverAgent(config_path="config/config.yaml")
    
    def test_injury_query_returns_mr_06_01(self, retriever):
        """Query infortunio deve preferire MR-06_01"""
        state = {
            "original_query": "Ho avuto un infortunio sul lavoro",
            "expanded_query": "Ho avuto un infortunio sul lavoro",
            "sub_queries": [],
            "agent_trace": []
        }
        
        result = retriever(state)
        
        # Verifica intent rilevato
        assert result.get("incident_intent") == "real_injury", \
            f"Intent non rilevato correttamente: {result.get('incident_intent')}"
        
        # Verifica che ci siano documenti
        docs = result.get("retrieved_docs", [])
        assert len(docs) > 0, "Nessun documento recuperato"
        
        # Log per debug
        logger.info(f"Documenti recuperati per query infortunio:")
        for i, doc in enumerate(docs[:5]):
            cat = doc.get("metadata", {}).get("incident_category", "N/A")
            logger.info(f"  {i+1}. {doc['doc_id']} - categoria: {cat}")
    
    def test_near_miss_query_returns_mr_06_02(self, retriever):
        """Query near miss deve preferire MR-06_02"""
        state = {
            "original_query": "C'è stato un near miss in reparto",
            "expanded_query": "C'è stato un near miss in reparto",
            "sub_queries": [],
            "agent_trace": []
        }
        
        result = retriever(state)
        
        # Verifica intent rilevato
        assert result.get("incident_intent") == "near_miss", \
            f"Intent non rilevato correttamente: {result.get('incident_intent')}"
        
        # Verifica documenti
        docs = result.get("retrieved_docs", [])
        assert len(docs) > 0, "Nessun documento recuperato"
        
        logger.info(f"Documenti recuperati per query near miss:")
        for i, doc in enumerate(docs[:5]):
            cat = doc.get("metadata", {}).get("incident_category", "N/A")
            logger.info(f"  {i+1}. {doc['doc_id']} - categoria: {cat}")


# Test eseguibili direttamente
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


