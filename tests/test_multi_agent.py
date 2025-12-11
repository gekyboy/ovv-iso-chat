"""
Test suite per Multi-Agent Pipeline (R24)
Verifica funzionamento di tutti gli agenti e dell'orchestratore
"""

import pytest
import logging
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Setup logging per test
logging.basicConfig(level=logging.INFO)

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def config_path():
    """Path configurazione test"""
    return "config/config.yaml"


@pytest.fixture
def sample_state():
    """Stato di esempio per test"""
    return {
        "original_query": "Cosa significa WCM?",
        "user_id": "test_user",
        "expanded_query": "Cosa significa WCM (World Class Manufacturing)?",
        "acronyms_found": [
            {
                "acronym": "WCM",
                "full": "World Class Manufacturing",
                "description": "Metodologia di miglioramento continuo"
            }
        ],
        "glossary_context": "📚 DEFINIZIONI:\n• WCM = World Class Manufacturing",
        "query_intent": "definitional",
        "sub_queries": ["Cosa significa WCM?"],
        "should_use_memory": False,
        "complexity": "simple",
        "retrieved_docs": [],
        "retrieval_scores": {},
        "compressed_context": "",
        "selected_sources": [],
        "memory_context": "",
        "token_count": 0,
        "answer": "",
        "cited_sources": [],
        "confidence": 0.0,
        "errors": [],
        "latency_ms": 0.0,
        "agent_trace": []
    }


# ============================================================================
# TEST STATE
# ============================================================================

class TestAgentState:
    """Test per state.py"""
    
    def test_create_initial_state(self):
        """Test creazione stato iniziale"""
        from src.agents.state import create_initial_state
        
        state = create_initial_state("Test query", "user123")
        
        assert state["original_query"] == "Test query"
        assert state["user_id"] == "user123"
        assert state["expanded_query"] == ""
        assert state["agent_trace"] == []
        assert state["confidence"] == 0.0
    
    def test_state_has_all_fields(self):
        """Verifica che lo stato abbia tutti i campi necessari"""
        from src.agents.state import create_initial_state
        
        state = create_initial_state("Test", "user")
        
        required_fields = [
            "original_query", "user_id", "expanded_query", "acronyms_found",
            "glossary_context", "query_intent", "sub_queries", "should_use_memory",
            "complexity", "retrieved_docs", "retrieval_scores", "compressed_context",
            "selected_sources", "memory_context", "token_count", "answer",
            "cited_sources", "confidence", "errors", "latency_ms", "agent_trace"
        ]
        
        for field in required_fields:
            assert field in state, f"Campo mancante: {field}"


# ============================================================================
# TEST GLOSSARY AGENT
# ============================================================================

class TestGlossaryAgent:
    """Test per GlossaryAgent"""
    
    def test_agent_initialization(self, config_path):
        """Test inizializzazione agente"""
        from src.agents.agent_glossary import GlossaryAgent
        
        agent = GlossaryAgent(config_path=config_path)
        assert agent.name == "glossary"
    
    def test_agent_call_returns_required_fields(self, config_path):
        """Test che l'agente ritorni i campi richiesti"""
        from src.agents.agent_glossary import GlossaryAgent
        
        agent = GlossaryAgent(config_path=config_path)
        
        state = {
            "original_query": "Cosa significa WCM?",
            "agent_trace": []
        }
        
        result = agent(state)
        
        assert "expanded_query" in result
        assert "acronyms_found" in result
        assert "glossary_context" in result
        assert "agent_trace" in result
        assert len(result["agent_trace"]) > 0
    
    def test_acronym_extraction(self, config_path):
        """Test estrazione acronimi da query"""
        from src.agents.agent_glossary import GlossaryAgent
        
        agent = GlossaryAgent(config_path=config_path)
        
        state = {
            "original_query": "Spiegami WCM e PDCA",
            "agent_trace": []
        }
        
        result = agent(state)
        
        # Dovrebbe trovare almeno un acronimo
        assert isinstance(result["acronyms_found"], list)


# ============================================================================
# TEST ANALYZER AGENT
# ============================================================================

class TestAnalyzerAgent:
    """Test per AnalyzerAgent"""
    
    def test_agent_initialization(self, config_path):
        """Test inizializzazione agente"""
        from src.agents.agent_analyzer import AnalyzerAgent
        
        agent = AnalyzerAgent(config_path=config_path)
        assert agent.name == "analyzer"
    
    def test_intent_classification_definitional(self, config_path):
        """Test classificazione intent definitional"""
        from src.agents.agent_analyzer import AnalyzerAgent
        
        agent = AnalyzerAgent(config_path=config_path)
        
        queries = [
            "Cosa significa WCM?",
            "Cos'è il PDCA?",
            "Definizione di NC"
        ]
        
        for query in queries:
            state = {"original_query": query, "expanded_query": query, "agent_trace": []}
            result = agent(state)
            assert result["query_intent"] == "definitional", f"Query: {query}"
    
    def test_intent_classification_procedural(self, config_path):
        """Test classificazione intent procedural"""
        from src.agents.agent_analyzer import AnalyzerAgent
        
        agent = AnalyzerAgent(config_path=config_path)
        
        queries = [
            "Come gestire i rifiuti?",
            "Come si compila il modulo MR-10_01?",
            "Procedura per la gestione NC"
        ]
        
        for query in queries:
            state = {"original_query": query, "expanded_query": query, "agent_trace": []}
            result = agent(state)
            assert result["query_intent"] == "procedural", f"Query: {query}"
    
    def test_complexity_assessment(self, config_path):
        """Test valutazione complessità"""
        from src.agents.agent_analyzer import AnalyzerAgent
        
        agent = AnalyzerAgent(config_path=config_path)
        
        # Query semplice
        state = {"original_query": "Cos'è WCM?", "expanded_query": "Cos'è WCM?", "agent_trace": []}
        result = agent(state)
        assert result["complexity"] == "simple"
        
        # Query complessa
        state = {"original_query": "Gestisci i rifiuti e anche le NC e le emergenze", 
                 "expanded_query": "Gestisci i rifiuti e anche le NC e le emergenze", "agent_trace": []}
        result = agent(state)
        assert result["complexity"] in ["medium", "complex"]
    
    def test_sub_query_decomposition(self, config_path):
        """Test decomposizione in sub-query"""
        from src.agents.agent_analyzer import AnalyzerAgent
        
        agent = AnalyzerAgent(config_path=config_path)
        
        state = {
            "original_query": "Gestisci i rifiuti e anche le NC", 
            "expanded_query": "Gestisci i rifiuti e anche le NC",
            "agent_trace": []
        }
        result = agent(state)
        
        assert len(result["sub_queries"]) >= 1


# ============================================================================
# TEST CONTEXT AGENT
# ============================================================================

class TestContextAgent:
    """Test per ContextAgent"""
    
    def test_agent_initialization(self, config_path):
        """Test inizializzazione agente"""
        from src.agents.agent_context import ContextAgent
        
        agent = ContextAgent(config_path=config_path)
        assert agent.name == "context"
    
    def test_token_estimation(self, config_path):
        """Test stima token"""
        from src.agents.agent_context import ContextAgent
        
        agent = ContextAgent(config_path=config_path)
        
        # 100 caratteri ≈ 25 token
        text = "a" * 100
        tokens = agent._estimate_tokens(text)
        assert tokens == 25
    
    def test_context_compression(self, config_path):
        """Test compressione contesto"""
        from src.agents.agent_context import ContextAgent
        
        agent = ContextAgent(config_path=config_path)
        
        docs = [
            {
                "doc_id": "PS-06_01",
                "text": "Testo documento " * 100,
                "score": 0.9,
                "metadata": {"doc_type": "PS"}
            },
            {
                "doc_id": "IL-06_02",
                "text": "Altro testo " * 50,
                "score": 0.8,
                "metadata": {"doc_type": "IL"}
            }
        ]
        
        state = {
            "retrieved_docs": docs,
            "query_intent": "procedural",
            "user_id": "test",
            "should_use_memory": False,
            "glossary_context": "",
            "agent_trace": []
        }
        
        result = agent(state)
        
        assert "compressed_context" in result
        assert "selected_sources" in result
        assert len(result["selected_sources"]) > 0
        assert result["token_count"] > 0


# ============================================================================
# TEST GENERATOR AGENT
# ============================================================================

class TestGeneratorAgent:
    """Test per GeneratorAgent"""
    
    def test_agent_initialization(self, config_path):
        """Test inizializzazione agente"""
        from src.agents.agent_generator import GeneratorAgent
        
        agent = GeneratorAgent(config_path=config_path)
        assert agent.name == "generator"
    
    def test_prompt_building(self, config_path):
        """Test costruzione prompt"""
        from src.agents.agent_generator import GeneratorAgent
        
        agent = GeneratorAgent(config_path=config_path)
        
        state = {
            "original_query": "Test query",
            "glossary_context": "📚 WCM = World Class",
            "memory_context": "📝 Preferenze utente",
            "compressed_context": "[PS: PS-06_01]\nTesto documento"
        }
        
        prompt = agent._build_prompt(state)
        
        assert "Test query" in prompt
        assert "WCM = World Class" in prompt
        assert "PS-06_01" in prompt
    
    def test_citation_extraction(self, config_path):
        """Test estrazione citazioni"""
        from src.agents.agent_generator import GeneratorAgent
        
        agent = GeneratorAgent(config_path=config_path)
        
        answer = "Secondo PS-06_01, la gestione dei rifiuti... Come indicato in IL-07_02..."
        available_sources = ["PS-06_01", "IL-07_02", "MR-10_01"]
        
        cited = agent._extract_citations(answer, available_sources)
        
        assert "PS-06_01" in cited
        assert "IL-07_02" in cited
        assert "MR-10_01" not in cited  # Non citato nella risposta
    
    def test_confidence_estimation(self, config_path):
        """Test stima confidence"""
        from src.agents.agent_generator import GeneratorAgent
        
        agent = GeneratorAgent(config_path=config_path)
        
        # Stato con molti documenti e glossario
        state = {
            "selected_sources": ["PS-06_01", "IL-07_02", "MR-10_01"],
            "glossary_context": "📚 WCM = World Class"
        }
        
        # Risposta lunga con citazioni
        answer = "Secondo PS-06_01, la procedura prevede..." + ("testo " * 100)
        
        confidence = agent._estimate_confidence(state, answer)
        
        assert confidence > 0.5
        assert confidence <= 1.0


# ============================================================================
# TEST ORCHESTRATOR
# ============================================================================

class TestOrchestrator:
    """Test per Orchestrator e MultiAgentPipeline"""
    
    def test_pipeline_initialization(self, config_path):
        """Test inizializzazione pipeline"""
        from src.agents.orchestrator import MultiAgentPipeline
        
        pipeline = MultiAgentPipeline(config_path=config_path)
        
        assert pipeline.config_path == config_path
        assert pipeline._graph is None  # Lazy loading
    
    def test_pipeline_status(self, config_path):
        """Test status pipeline"""
        from src.agents.orchestrator import MultiAgentPipeline
        
        pipeline = MultiAgentPipeline(config_path=config_path)
        status = pipeline.get_status()
        
        assert status["type"] == "multi-agent"
        assert "agents" in status
        assert len(status["agents"]) == 5


# ============================================================================
# TEST ROUTING
# ============================================================================

class TestRouting:
    """Test per routing condizionale"""
    
    def test_definitional_routes_to_direct(self, config_path):
        """Test che query definitional con acronimo vada a direct_answer"""
        from src.agents.agent_analyzer import AnalyzerAgent
        
        agent = AnalyzerAgent(config_path=config_path)
        
        state = {
            "original_query": "Cosa significa WCM?",
            "expanded_query": "Cosa significa WCM?",
            "acronyms_found": [{"acronym": "WCM", "full": "World Class Manufacturing"}],
            "agent_trace": []
        }
        
        result = agent(state)
        
        # Intent definitional + acronimo trovato + semplice = direct_answer
        assert result["query_intent"] == "definitional"
        assert result["complexity"] == "simple"
    
    def test_procedural_routes_to_retriever(self, config_path):
        """Test che query procedurale vada a retriever"""
        from src.agents.agent_analyzer import AnalyzerAgent
        
        agent = AnalyzerAgent(config_path=config_path)
        
        state = {
            "original_query": "Come gestire i rifiuti pericolosi?",
            "expanded_query": "Come gestire i rifiuti pericolosi?",
            "acronyms_found": [],
            "agent_trace": []
        }
        
        result = agent(state)
        
        # Intent procedural = sempre retriever
        assert result["query_intent"] == "procedural"


# ============================================================================
# TEST INTEGRAZIONE
# ============================================================================

class TestIntegration:
    """Test di integrazione end-to-end"""
    
    @pytest.mark.slow
    def test_full_pipeline_definitional(self, config_path):
        """Test pipeline completa per query definitional"""
        from src.agents.orchestrator import MultiAgentPipeline, MultiAgentResponse
        
        pipeline = MultiAgentPipeline(config_path=config_path)
        
        response = pipeline.query("Cosa significa WCM?", user_id="test")
        
        # Verifica che sia un MultiAgentResponse
        assert isinstance(response, MultiAgentResponse)
        
        # Verifica attributi
        assert response.answer is not None
        assert response.latency_ms > 0
        
        # Verifica che la risposta interna abbia agent_trace
        result = response.to_dict()
        trace = result.get("agent_trace", [])
        assert any("glossary" in t for t in trace)
        assert any("analyzer" in t for t in trace)
    
    @pytest.mark.slow
    def test_full_pipeline_procedural(self, config_path):
        """Test pipeline completa per query procedurale"""
        from src.agents.orchestrator import MultiAgentPipeline, MultiAgentResponse
        
        pipeline = MultiAgentPipeline(config_path=config_path)
        
        response = pipeline.query("Come gestire i rifiuti pericolosi?", user_id="test")
        
        # Verifica che sia un MultiAgentResponse
        assert isinstance(response, MultiAgentResponse)
        
        assert response.answer  # Non vuota
        
        # Query procedurale deve passare per retriever
        result = response.to_dict()
        trace = result.get("agent_trace", [])
        assert any("retriever" in t for t in trace)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

