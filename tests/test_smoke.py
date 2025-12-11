"""
Test Smoke - Verifica che il sistema sia pronto per l'uso.
Esegui dopo il setup per validare l'installazione.

Usage:
    pytest tests/test_smoke.py -v
    
Categorie test:
- test_imports_*: Verifica import moduli
- test_config_*: Verifica configurazione
- test_*_connection: Verifica servizi esterni
- test_*_model: Verifica modelli (slow)
"""

import pytest
import sys
from pathlib import Path


# ============================================================================
# 1. IMPORT TEST
# ============================================================================

def test_imports_core():
    """Verifica import moduli core"""
    from src.ingestion import PDFExtractor, ISOChunker, QdrantIndexer
    from src.integration import RAGPipeline, GlossaryResolver
    from src.memory import MemoryStore
    assert True


def test_imports_agents():
    """Verifica import agenti"""
    from src.agents import MultiAgentPipeline, AgentState
    assert True


def test_imports_analytics():
    """Verifica import analytics"""
    from src.analytics import GapDetector, AcronymExtractor
    assert True


def test_imports_auth():
    """Verifica import auth"""
    from src.auth import UserStore, User
    assert True


# ============================================================================
# 2. CONFIG TEST
# ============================================================================

def test_config_exists():
    """Verifica file configurazione principale"""
    config_path = Path("config/config.yaml")
    assert config_path.exists(), "config/config.yaml non trovato!"


def test_config_valid():
    """Verifica configurazione valida"""
    import yaml
    with open("config/config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # Verifica sezioni obbligatorie
    assert "embedding" in config, "Sezione 'embedding' mancante"
    assert "llm" in config, "Sezione 'llm' mancante"
    assert "qdrant" in config, "Sezione 'qdrant' mancante"
    assert "retrieval" in config, "Sezione 'retrieval' mancante"
    
    # Verifica vincoli VRAM
    assert config["vram"]["critical_mb"] == 5500, "Limite VRAM non corretto"


def test_glossary_exists():
    """Verifica glossario acronimi"""
    glossary_path = Path("config/glossary.json")
    assert glossary_path.exists(), "config/glossary.json non trovato!"
    
    import json
    with open(glossary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    acronyms = data.get("acronyms", {})
    # Rimuovi commenti
    acronyms = {k: v for k, v in acronyms.items() if not k.startswith("_")}
    assert len(acronyms) >= 100, f"Glossario troppo piccolo: {len(acronyms)} acronimi"


def test_semantic_metadata_exists():
    """Verifica metadata semantici"""
    path = Path("config/semantic_metadata.json")
    assert path.exists(), "config/semantic_metadata.json non trovato!"
    
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    documents = data.get("documents", {})
    assert len(documents) >= 50, f"Metadata troppo piccoli: {len(documents)} documenti"


def test_document_metadata_exists():
    """Verifica metadata documenti"""
    path = Path("config/document_metadata.json")
    assert path.exists(), "config/document_metadata.json non trovato!"
    
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    mr = data.get("moduli_registrazione", {})
    tools = data.get("tools", {})
    total = len(mr) + len(tools)
    assert total >= 50, f"Metadata troppo piccoli: {total} documenti"


def test_tools_mapping_exists():
    """Verifica mapping tools"""
    path = Path("config/tools_mapping.json")
    assert path.exists(), "config/tools_mapping.json non trovato!"
    
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    tools = data.get("tool_suggestions", {})
    assert len(tools) >= 5, f"Mapping tools troppo piccolo: {len(tools)}"


def test_users_exists():
    """Verifica file utenti"""
    path = Path("config/users.json")
    assert path.exists(), "config/users.json non trovato!"
    
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    users = data.get("users", {})
    assert "admin" in users, "Utente admin mancante"
    assert users["admin"]["role"] == "admin", "Ruolo admin non corretto"


# ============================================================================
# 3. SERVICES TEST
# ============================================================================

def test_qdrant_connection():
    """Verifica connessione Qdrant"""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url="http://localhost:6333", timeout=5)
        collections = client.get_collections()
        assert True
    except Exception as e:
        pytest.skip(f"Qdrant non disponibile: {e}")


def test_ollama_connection():
    """Verifica connessione Ollama"""
    import requests
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        assert response.status_code == 200, f"Ollama status: {response.status_code}"
    except Exception as e:
        pytest.skip(f"Ollama non disponibile: {e}")


# ============================================================================
# 4. GPU TEST
# ============================================================================

def test_cuda_available():
    """Verifica GPU CUDA"""
    try:
        import torch
        if not torch.cuda.is_available():
            pytest.skip("CUDA non disponibile")
        
        vram_mb = torch.cuda.get_device_properties(0).total_memory / 1024 / 1024
        assert vram_mb >= 6000, f"VRAM insufficiente: {vram_mb:.0f}MB (richiesti 6GB)"
    except ImportError:
        pytest.skip("PyTorch non installato")


def test_vram_headroom():
    """Verifica VRAM disponibile"""
    try:
        import torch
        if not torch.cuda.is_available():
            pytest.skip("CUDA non disponibile")
        
        used_mb = torch.cuda.memory_allocated() / 1024 / 1024
        assert used_mb < 5500, f"VRAM già troppo usata: {used_mb:.0f}MB"
    except ImportError:
        pytest.skip("PyTorch non installato")


# ============================================================================
# 5. SLOW TESTS - Modelli (skip by default)
# ============================================================================

@pytest.mark.slow
def test_embedding_model():
    """Verifica caricamento modello embedding"""
    try:
        from sentence_transformers import SentenceTransformer
        import torch
        
        model = SentenceTransformer("BAAI/bge-m3", device="cuda" if torch.cuda.is_available() else "cpu")
        embedding = model.encode(["Test di embedding"])
        
        assert len(embedding[0]) == 1024, f"Embedding dim errata: {len(embedding[0])}"
        
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    except Exception as e:
        pytest.fail(f"Embedding fallito: {e}")


@pytest.mark.slow
def test_glossary_resolver():
    """Verifica GlossaryResolver"""
    from src.integration import GlossaryResolver
    
    resolver = GlossaryResolver(config_path="config/config.yaml")
    
    # Test espansione
    expanded = resolver.expand_query("Cosa significa WCM?")
    assert "World Class Manufacturing" in expanded or "wcm" in expanded.lower()


@pytest.mark.slow
def test_rag_pipeline_init():
    """Verifica inizializzazione pipeline RAG"""
    try:
        from src.integration import RAGPipeline
        pipeline = RAGPipeline(config_path="config/config.yaml")
        assert pipeline is not None
    except Exception as e:
        pytest.fail(f"Pipeline init fallita: {e}")


# ============================================================================
# 6. INTEGRATION TESTS
# ============================================================================

def test_path_manager():
    """Verifica PathManager"""
    from src.ingestion import get_path_manager, reset_path_manager
    
    reset_path_manager()
    manager = get_path_manager()
    
    # Deve avere un path valido
    current = manager.get_current_path()
    assert current is not None


def test_memory_store():
    """Verifica MemoryStore"""
    from src.memory import MemoryStore
    import tempfile
    import json
    
    # Crea store temporaneo
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"memories": {}}, f)
        temp_path = f.name
    
    try:
        config = {"memory": {"persist_path": temp_path}}
        store = MemoryStore(config=config)
        assert store is not None
    finally:
        Path(temp_path).unlink(missing_ok=True)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Esegui test base (salta slow)
    pytest.main([__file__, "-v", "-m", "not slow"])


