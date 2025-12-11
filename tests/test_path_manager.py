"""
Test per DocumentPathManager (F10)

Verifica:
- Validazione path
- Gestione path recenti
- Cambio path
- Reset a default
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestPathValidation:
    """Test validazione path"""
    
    @pytest.fixture
    def temp_docs_dir(self):
        """Crea directory temporanea con PDF di test"""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Crea file PDF fittizi
        (temp_dir / "PS-06_01.pdf").touch()
        (temp_dir / "PS-08_08.pdf").touch()
        (temp_dir / "IL-07_02.pdf").touch()
        (temp_dir / "MR-10_01.pdf").touch()
        (temp_dir / "TOOLS-Safety.pdf").touch()
        
        yield temp_dir
        
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def manager(self, temp_docs_dir):
        """PathManager con config mock"""
        from src.ingestion.path_manager import DocumentPathManager, reset_path_manager
        
        # Reset singleton
        reset_path_manager()
        
        # Crea manager con mock
        with patch.object(DocumentPathManager, '_load_config') as mock_config:
            mock_config.return_value = {
                "paths": {"input_docs": str(temp_docs_dir)},
                "document_path": {
                    "allow_ui_selection": True,
                    "allow_command": True,
                    "max_recent_paths": 10
                }
            }
            
            manager = DocumentPathManager(
                config_path="mock/path",
                prefs_path=str(temp_docs_dir / "prefs.json")
            )
            
            yield manager
        
        reset_path_manager()
    
    def test_validate_path_valid(self, manager, temp_docs_dir):
        """Test validazione path valido"""
        result = manager.validate_path(str(temp_docs_dir))
        
        assert result.valid is True
        assert result.pdf_count == 5
        assert result.ps_count == 2
        assert result.il_count == 1
        assert result.mr_count == 1
        assert result.tools_count == 1
    
    def test_validate_path_not_exists(self, manager):
        """Test validazione path non esistente"""
        result = manager.validate_path("/path/che/non/esiste")
        
        assert result.valid is False
        assert "non esiste" in result.error
    
    def test_validate_path_no_pdfs(self, manager):
        """Test validazione cartella senza PDF"""
        empty_dir = Path(tempfile.mkdtemp())
        
        try:
            result = manager.validate_path(str(empty_dir))
            
            assert result.valid is False
            assert "PDF" in result.error
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)


class TestPathManagement:
    """Test gestione path"""
    
    @pytest.fixture
    def temp_docs_dir(self):
        """Crea directory temporanea con PDF di test"""
        temp_dir = Path(tempfile.mkdtemp())
        (temp_dir / "PS-01_01.pdf").touch()
        (temp_dir / "IL-02_01.pdf").touch()
        
        yield temp_dir
        
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def manager(self, temp_docs_dir):
        """PathManager con config mock"""
        from src.ingestion.path_manager import DocumentPathManager, reset_path_manager
        
        reset_path_manager()
        
        with patch.object(DocumentPathManager, '_load_config') as mock_config:
            mock_config.return_value = {
                "paths": {"input_docs": str(temp_docs_dir)},
                "document_path": {"max_recent_paths": 5}
            }
            
            manager = DocumentPathManager(
                config_path="mock/path",
                prefs_path=str(temp_docs_dir / "prefs.json")
            )
            
            yield manager
        
        reset_path_manager()
    
    def test_get_default_path(self, manager, temp_docs_dir):
        """Test path di default"""
        assert manager.get_default_path() == temp_docs_dir
    
    def test_get_current_path_initial(self, manager, temp_docs_dir):
        """Test path corrente iniziale = default"""
        assert manager.get_current_path() == temp_docs_dir
    
    def test_set_path_valid(self, manager):
        """Test cambio path valido"""
        new_dir = Path(tempfile.mkdtemp())
        (new_dir / "PS-01_01.pdf").touch()
        
        try:
            result = manager.set_path(str(new_dir))
            
            assert result.valid is True
            assert manager.get_current_path() == new_dir
        finally:
            shutil.rmtree(new_dir, ignore_errors=True)
    
    def test_set_path_invalid(self, manager, temp_docs_dir):
        """Test cambio path invalido non modifica corrente"""
        original = manager.get_current_path()
        
        result = manager.set_path("/path/invalido")
        
        assert result.valid is False
        assert manager.get_current_path() == original
    
    def test_reset_to_default(self, manager, temp_docs_dir):
        """Test reset a default"""
        # Cambia path
        new_dir = Path(tempfile.mkdtemp())
        (new_dir / "PS-01_01.pdf").touch()
        
        try:
            manager.set_path(str(new_dir))
            assert manager.get_current_path() == new_dir
            
            # Reset
            manager.reset_to_default()
            assert manager.get_current_path() == temp_docs_dir
        finally:
            shutil.rmtree(new_dir, ignore_errors=True)


class TestRecentPaths:
    """Test path recenti"""
    
    @pytest.fixture
    def manager(self):
        """PathManager con config mock"""
        from src.ingestion.path_manager import DocumentPathManager, reset_path_manager
        
        reset_path_manager()
        
        temp_dir = Path(tempfile.mkdtemp())
        (temp_dir / "PS-01_01.pdf").touch()
        
        with patch.object(DocumentPathManager, '_load_config') as mock_config:
            mock_config.return_value = {
                "paths": {"input_docs": str(temp_dir)},
                "document_path": {"max_recent_paths": 3}
            }
            
            manager = DocumentPathManager(
                config_path="mock/path",
                prefs_path=str(temp_dir / "prefs.json")
            )
            
            yield manager, temp_dir
        
        shutil.rmtree(temp_dir, ignore_errors=True)
        reset_path_manager()
    
    def test_recent_paths_empty_initially(self, manager):
        """Test recenti vuoti all'inizio"""
        mgr, _ = manager
        recents = mgr.get_recent_paths()
        assert len(recents) == 0
    
    def test_recent_paths_after_set(self, manager):
        """Test recenti dopo set_path"""
        mgr, temp_dir = manager
        
        # Crea nuovo dir
        new_dir = Path(tempfile.mkdtemp())
        (new_dir / "PS-01_01.pdf").touch()
        
        try:
            mgr.set_path(str(new_dir), persist=False)
            
            recents = mgr.get_recent_paths()
            assert len(recents) == 1
            assert recents[0].path == str(new_dir)
        finally:
            shutil.rmtree(new_dir, ignore_errors=True)
    
    def test_clear_recent_paths(self, manager):
        """Test pulizia path recenti"""
        mgr, temp_dir = manager
        
        new_dir = Path(tempfile.mkdtemp())
        (new_dir / "PS-01_01.pdf").touch()
        
        try:
            mgr.set_path(str(new_dir), persist=False)
            assert len(mgr.get_recent_paths()) == 1
            
            mgr.clear_recent_paths()
            assert len(mgr.get_recent_paths()) == 0
        finally:
            shutil.rmtree(new_dir, ignore_errors=True)


class TestStatus:
    """Test status e messaggi"""
    
    @pytest.fixture
    def manager(self):
        """PathManager con config mock"""
        from src.ingestion.path_manager import DocumentPathManager, reset_path_manager
        
        reset_path_manager()
        
        temp_dir = Path(tempfile.mkdtemp())
        (temp_dir / "PS-01_01.pdf").touch()
        (temp_dir / "PS-02_01.pdf").touch()
        (temp_dir / "IL-01_01.pdf").touch()
        
        with patch.object(DocumentPathManager, '_load_config') as mock_config:
            mock_config.return_value = {
                "paths": {"input_docs": str(temp_dir)},
                "document_path": {}
            }
            
            manager = DocumentPathManager(
                config_path="mock/path",
                prefs_path=str(temp_dir / "prefs.json")
            )
            
            yield manager, temp_dir
        
        shutil.rmtree(temp_dir, ignore_errors=True)
        reset_path_manager()
    
    def test_get_status(self, manager):
        """Test get_status"""
        mgr, temp_dir = manager
        status = mgr.get_status()
        
        assert status["is_valid"] is True
        assert status["pdf_count"] == 3
        assert status["is_default"] is True
        assert status["breakdown"]["PS"] == 2
        assert status["breakdown"]["IL"] == 1
    
    def test_format_status_message(self, manager):
        """Test formato messaggio status"""
        mgr, _ = manager
        msg = mgr.format_status_message()
        
        assert "📂" in msg
        assert "Documenti trovati" in msg
        assert "PS:" in msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

