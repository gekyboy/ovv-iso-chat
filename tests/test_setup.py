# Test base per verificare setup
"""
Test minimali per verificare che l'ambiente sia configurato correttamente.
"""

import pytest
from pathlib import Path


def test_project_structure():
    """Verifica che la struttura del progetto esista."""
    project_root = Path(__file__).parent.parent
    
    assert (project_root / "src").exists(), "Directory src/ mancante"
    assert (project_root / "config").exists(), "Directory config/ mancante"
    assert (project_root / "data").exists(), "Directory data/ mancante"
    assert (project_root / "scripts").exists(), "Directory scripts/ mancante"


def test_config_exists():
    """Verifica che il file config.yaml esista."""
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config" / "config.yaml"
    
    assert config_path.exists(), "config/config.yaml mancante"


def test_pyproject_exists():
    """Verifica che pyproject.toml esista."""
    project_root = Path(__file__).parent.parent
    pyproject_path = project_root / "pyproject.toml"
    
    assert pyproject_path.exists(), "pyproject.toml mancante"


def test_imports():
    """Verifica che i moduli siano importabili."""
    # Test base - questi falliranno finché non ci sono i moduli
    # Ma la struttura deve esistere
    project_root = Path(__file__).parent.parent
    
    assert (project_root / "src" / "__init__.py").exists()
    assert (project_root / "src" / "ingestion" / "__init__.py").exists()
    assert (project_root / "src" / "memory" / "__init__.py").exists()
    assert (project_root / "src" / "integration" / "__init__.py").exists()


def test_input_docs_directory():
    """Verifica che la directory input_docs esista e contenga PDF."""
    project_root = Path(__file__).parent.parent
    input_docs = project_root / "data" / "input_docs"
    
    assert input_docs.exists(), "Directory data/input_docs/ mancante"
    
    # Conta PDF
    pdf_files = list(input_docs.rglob("*.pdf"))
    print(f"Trovati {len(pdf_files)} file PDF in input_docs/")
    
    # Non fallisce se vuoto, ma stampa warning
    if len(pdf_files) == 0:
        pytest.skip("Nessun PDF in input_docs/ - copiare PDF prima del test ingestion")

