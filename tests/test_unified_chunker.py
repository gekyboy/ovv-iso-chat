"""
Test per UnifiedChunker (F06)
Verifica che il chunker unificato deleghi correttamente ai sub-chunkers.

Created: 2025-12-10
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path


class TestUnifiedChunker:
    """Test per UnifiedChunker"""
    
    @pytest.fixture
    def mock_config(self):
        """Config mock per test"""
        return {
            "ingestion": {
                "synthetic_chunk_types": ["MR", "TOOLS"],
                "chunking": {
                    "parent_size": 1200,
                    "child_size": 400,
                    "parent_overlap": 200,
                    "child_overlap": 100
                },
                "strategies": {
                    "dense": ["PS", "IL"],
                    "light": ["MR", "TOOLS"]
                }
            }
        }
    
    @pytest.fixture
    def chunker(self, mock_config):
        """Fixture per UnifiedChunker con config mock"""
        with patch('src.ingestion.unified_chunker.UnifiedChunker._load_config') as mock_load:
            mock_load.return_value = mock_config
            
            # Mock SyntheticChunker per evitare caricamento file
            with patch('src.ingestion.unified_chunker.SyntheticChunker') as MockSynthetic:
                mock_synthetic = MagicMock()
                mock_synthetic.get_doc_ids_with_metadata.return_value = [
                    "MR-06_01", "MR-06_02", "MR-10_01", "TOOLS-5_Perche"
                ]
                MockSynthetic.return_value = mock_synthetic
                
                # Mock ISOChunker
                with patch('src.ingestion.unified_chunker.ISOChunker') as MockISO:
                    mock_iso = MagicMock()
                    MockISO.return_value = mock_iso
                    
                    from src.ingestion.unified_chunker import UnifiedChunker
                    chunker = UnifiedChunker(config=mock_config)
                    chunker.iso_chunker = mock_iso
                    chunker.synthetic_chunker = mock_synthetic
                    
                    return chunker
    
    def _create_mock_document(self, doc_id: str, doc_type: str):
        """Helper per creare documento mock"""
        metadata = MagicMock()
        metadata.doc_id = doc_id
        metadata.doc_type = doc_type
        metadata.chapter = doc_id.split("-")[1].split("_")[0] if "-" in doc_id else "00"
        metadata.revision = "01"
        metadata.priority = 0.85 if doc_type in ["MR", "TOOLS"] else 1.0
        metadata.filename = f"{doc_id}.pdf"
        metadata.title = f"Test {doc_type} Document"
        metadata.label = doc_id
        
        doc = MagicMock()
        doc.metadata = metadata
        doc.full_text = f"Test content for {doc_id}"
        
        return doc
    
    def test_init_loads_synthetic_types(self, chunker):
        """Verifica che synthetic_types sia caricato da config"""
        assert chunker.synthetic_types == {"MR", "TOOLS"}
    
    def test_init_loads_available_synthetic_docs(self, chunker):
        """Verifica che i doc_id con metadata siano caricati"""
        assert "MR-06_01" in chunker._synthetic_doc_ids
        assert "TOOLS-5_Perche" in chunker._synthetic_doc_ids
    
    def test_should_use_synthetic_for_mr_with_metadata(self, chunker):
        """MR con metadata deve usare synthetic"""
        assert chunker._should_use_synthetic("MR", "MR-06_01") is True
    
    def test_should_use_synthetic_for_tools_with_metadata(self, chunker):
        """TOOLS con metadata deve usare synthetic"""
        assert chunker._should_use_synthetic("TOOLS", "TOOLS-5_Perche") is True
    
    def test_should_not_use_synthetic_for_ps(self, chunker):
        """PS non deve usare synthetic"""
        assert chunker._should_use_synthetic("PS", "PS-06_01") is False
    
    def test_should_not_use_synthetic_for_il(self, chunker):
        """IL non deve usare synthetic"""
        assert chunker._should_use_synthetic("IL", "IL-07_02") is False
    
    def test_should_not_use_synthetic_for_mr_without_metadata(self, chunker):
        """MR senza metadata non deve usare synthetic"""
        assert chunker._should_use_synthetic("MR", "MR-99_99") is False
    
    def test_ps_document_uses_iso_chunker(self, chunker):
        """PS deve usare ISOChunker (gerarchico)"""
        doc = self._create_mock_document("PS-06_01", "PS")
        
        # Setup mock return
        mock_chunk = MagicMock()
        mock_chunk.chunk_type = "parent"
        chunker.iso_chunker.chunk_document.return_value = [mock_chunk]
        
        chunks = chunker.chunk_document(doc)
        
        chunker.iso_chunker.chunk_document.assert_called_once_with(doc)
        assert len(chunks) == 1
    
    def test_il_document_uses_iso_chunker(self, chunker):
        """IL deve usare ISOChunker (gerarchico)"""
        doc = self._create_mock_document("IL-07_02", "IL")
        
        mock_chunk = MagicMock()
        mock_chunk.chunk_type = "parent"
        chunker.iso_chunker.chunk_document.return_value = [mock_chunk]
        
        chunks = chunker.chunk_document(doc)
        
        chunker.iso_chunker.chunk_document.assert_called_once_with(doc)
    
    def test_mr_document_uses_synthetic_chunker(self, chunker):
        """MR con metadata deve usare SyntheticChunker"""
        doc = self._create_mock_document("MR-06_01", "MR")
        
        # Setup mock synthetic chunk
        mock_synthetic = MagicMock()
        mock_synthetic.doc_id = "MR-06_01"
        mock_synthetic.doc_type = "MR"
        mock_synthetic.text = "Test synthetic chunk text"
        mock_synthetic.title = "Safety EWO"
        chunker.synthetic_chunker.generate_chunk.return_value = mock_synthetic
        
        chunks = chunker.chunk_document(doc)
        
        chunker.synthetic_chunker.generate_chunk.assert_called_once_with("MR-06_01")
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "synthetic"
    
    def test_mr_fallback_when_no_metadata(self, chunker):
        """MR senza metadata deve fallback a ISOChunker"""
        doc = self._create_mock_document("MR-99_99", "MR")
        
        # Mock light chunk
        mock_chunk = MagicMock()
        mock_chunk.chunk_type = "light"
        chunker.iso_chunker.chunk_document.return_value = [mock_chunk]
        
        chunks = chunker.chunk_document(doc)
        
        # Non deve chiamare synthetic_chunker perché doc_id non è nei metadata
        chunker.iso_chunker.chunk_document.assert_called_once_with(doc)
        assert len(chunks) == 1
    
    def test_chunk_documents_stats(self, chunker):
        """Verifica statistiche dopo chunk multipli"""
        docs = [
            self._create_mock_document("PS-06_01", "PS"),
            self._create_mock_document("IL-07_02", "IL"),
            self._create_mock_document("MR-06_01", "MR"),
        ]
        
        # Setup mocks
        mock_parent = MagicMock()
        mock_parent.chunk_type = "parent"
        chunker.iso_chunker.chunk_document.return_value = [mock_parent, mock_parent]
        
        mock_synthetic = MagicMock()
        mock_synthetic.doc_id = "MR-06_01"
        mock_synthetic.doc_type = "MR"
        mock_synthetic.text = "Synthetic"
        mock_synthetic.title = "Test"
        chunker.synthetic_chunker.generate_chunk.return_value = mock_synthetic
        
        chunks = chunker.chunk_documents(docs)
        
        stats = chunker.get_stats()
        assert stats.total_documents == 3
        assert stats.hierarchical_docs == 2  # PS + IL
        assert stats.synthetic_docs == 1  # MR
    
    def test_get_synthetic_doc_ids_returns_copy(self, chunker):
        """get_synthetic_doc_ids deve ritornare una copia"""
        ids1 = chunker.get_synthetic_doc_ids()
        ids2 = chunker.get_synthetic_doc_ids()
        
        assert ids1 == ids2
        assert ids1 is not ids2  # Devono essere oggetti diversi


class TestUnifiedChunkingStats:
    """Test per UnifiedChunkingStats dataclass"""
    
    def test_to_dict(self):
        """Verifica conversione a dizionario"""
        from src.ingestion.unified_chunker import UnifiedChunkingStats
        
        stats = UnifiedChunkingStats(
            total_documents=10,
            total_chunks=50,
            hierarchical_docs=6,
            hierarchical_chunks=40,
            synthetic_docs=4,
            synthetic_chunks=10
        )
        
        d = stats.to_dict()
        
        assert d["total_documents"] == 10
        assert d["total_chunks"] == 50
        assert d["hierarchical_docs"] == 6
        assert d["synthetic_docs"] == 4


# Test di integrazione (richiede file reali)
@pytest.mark.integration
class TestUnifiedChunkerIntegration:
    """Test di integrazione con file reali (skip se mancano)"""
    
    @pytest.fixture
    def real_chunker(self):
        """Chunker reale con config dal progetto"""
        import os
        os.chdir(Path(__file__).parent.parent)
        
        from src.ingestion.unified_chunker import UnifiedChunker
        return UnifiedChunker()
    
    def test_real_synthetic_doc_ids_loaded(self, real_chunker):
        """Verifica che i doc_id sintetici siano caricati"""
        ids = real_chunker.get_synthetic_doc_ids()
        
        # Dovrebbero esserci almeno alcuni MR
        mr_count = sum(1 for id in ids if id.startswith("MR"))
        assert mr_count > 0, "Nessun MR trovato nei metadata sintetici"

