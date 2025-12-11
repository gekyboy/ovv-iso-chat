"""
Test per SyntheticChunker

Verifica generazione chunk sintetici per MR/TOOLS
basati su metadata invece che contenuto PDF.
"""

import pytest
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ingestion.synthetic_chunker import SyntheticChunker, SyntheticChunk


class TestSyntheticChunker:
    """Test per SyntheticChunker"""
    
    @pytest.fixture
    def chunker(self):
        """Fixture per SyntheticChunker"""
        return SyntheticChunker()
    
    def test_load_metadata(self, chunker):
        """Verifica caricamento metadata da tutti i file"""
        assert len(chunker.semantic_metadata) >= 80, \
            f"Attesi >=80 semantic_metadata, trovati {len(chunker.semantic_metadata)}"
        assert len(chunker.document_metadata) >= 70, \
            f"Attesi >=70 document_metadata, trovati {len(chunker.document_metadata)}"
        assert len(chunker.tools_mapping) >= 10, \
            f"Attesi >=10 tools_mapping, trovati {len(chunker.tools_mapping)}"
    
    def test_generate_chunk_mr_infortunio(self, chunker):
        """Test generazione chunk MR-06_01 (Safety EWO - infortuni)"""
        chunk = chunker.generate_chunk("MR-06_01")
        
        assert chunk is not None, "Chunk MR-06_01 non generato"
        assert chunk.doc_id == "MR-06_01"
        assert chunk.doc_type == "MR"
        assert "Safety EWO" in chunk.text or "infortunio" in chunk.text.lower()
        assert chunk.incident_category == "real_injury"
        assert len(chunk.applies_when) > 0
        assert "infortunio" in " ".join(chunk.applies_when).lower()
    
    def test_generate_chunk_mr_near_miss(self, chunker):
        """Test generazione chunk MR-06_02 (Near Misses)"""
        chunk = chunker.generate_chunk("MR-06_02")
        
        assert chunk is not None, "Chunk MR-06_02 non generato"
        assert chunk.doc_id == "MR-06_02"
        assert chunk.incident_category == "near_miss"
        assert "near miss" in chunk.text.lower() or "mancato" in chunk.text.lower()
    
    def test_generate_chunk_tools(self, chunker):
        """Test generazione chunk TOOLS"""
        # Prova diversi formati di doc_id per TOOLS
        tools_ids = ["TOOLS-5_Perche", "TOOLS-4M_Ishikawa", "TOOLS-5W1H"]
        
        found = False
        for doc_id in tools_ids:
            chunk = chunker.generate_chunk(doc_id)
            if chunk:
                found = True
                assert "TOOLS" in chunk.doc_type or chunk.doc_type == "TOOLS"
                break
        
        assert found, "Nessun chunk TOOLS generato"
    
    def test_applies_when_in_text(self, chunker):
        """Verifica che applies_when appaia nel testo del chunk"""
        chunk = chunker.generate_chunk("MR-06_01")
        
        assert chunk is not None
        text_lower = chunk.text.lower()
        
        # Almeno una keyword di applies_when deve essere nel testo
        found = False
        for kw in chunk.applies_when[:5]:
            if kw.lower() in text_lower:
                found = True
                break
        
        assert found, f"Nessuna keyword di applies_when trovata nel testo. Keywords: {chunk.applies_when[:5]}"
    
    def test_not_for_in_text(self, chunker):
        """Verifica che not_for appaia nel testo (se presente)"""
        chunk = chunker.generate_chunk("MR-06_01")
        
        assert chunk is not None
        
        # Se c'è not_for, deve apparire nel testo
        if chunk.not_for:
            text_lower = chunk.text.lower()
            assert "non usare" in text_lower or "not_for" in str(chunk.not_for).lower()
    
    def test_parent_ps_in_text(self, chunker):
        """Verifica che parent_ps appaia nel testo"""
        chunk = chunker.generate_chunk("MR-06_01")
        
        assert chunk is not None
        
        if chunk.parent_ps:
            assert chunk.parent_ps in chunk.text, \
                f"parent_ps {chunk.parent_ps} non trovato nel testo"
    
    def test_generate_all_chunks(self, chunker):
        """Test generazione tutti i chunk"""
        chunks = chunker.generate_all_chunks()
        
        assert len(chunks) >= 80, f"Attesi >=80 chunks, generati {len(chunks)}"
        
        # Verifica mix MR e TOOLS
        mr_count = sum(1 for c in chunks if c.doc_type == "MR")
        tools_count = sum(1 for c in chunks if c.doc_type == "TOOLS")
        
        assert mr_count >= 60, f"Attesi >=60 MR chunks, trovati {mr_count}"
        assert tools_count >= 10, f"Attesi >=10 TOOLS chunks, trovati {tools_count}"
    
    def test_to_enriched_chunk(self, chunker):
        """Test conversione in EnrichedChunk"""
        synthetic = chunker.generate_chunk("MR-06_01")
        assert synthetic is not None
        
        enriched = synthetic.to_enriched_chunk()
        
        assert enriched is not None
        assert enriched.original_chunk is not None
        assert enriched.enriched_text == synthetic.text
        assert enriched.incident_category == "real_injury"
        assert len(enriched.applies_when) > 0
    
    def test_generate_enriched_chunks(self, chunker):
        """Test generazione diretta EnrichedChunk"""
        enriched_chunks = chunker.generate_enriched_chunks()
        
        assert len(enriched_chunks) >= 80
        
        # Verifica che siano tutti EnrichedChunk validi
        for ec in enriched_chunks[:10]:
            assert hasattr(ec, 'original_chunk')
            assert hasattr(ec, 'enriched_text')
            assert len(ec.enriched_text) > 100
    
    def test_chunk_text_structure(self, chunker):
        """Verifica struttura del testo chunk generato"""
        chunk = chunker.generate_chunk("MR-06_01")
        
        assert chunk is not None
        text = chunk.text
        
        # Deve avere header con doc_id
        assert "MR-06_01" in text
        
        # Deve avere sezione "Scopo" o "Utilizzo"
        assert "Scopo" in text or "Utilizzo" in text or "uso" in text.lower()
        
        # Deve avere sezione "Quando Utilizzare"
        assert "Quando" in text
    
    def test_kaizen_chunks(self, chunker):
        """Test chunk per moduli Kaizen (Cap. 10)"""
        kaizen_ids = ["MR-10_01", "MR-10_02", "MR-10_03"]
        
        for doc_id in kaizen_ids:
            chunk = chunker.generate_chunk(doc_id)
            if chunk:
                assert chunk.incident_category == "kaizen"
                assert "kaizen" in chunk.text.lower() or "miglioramento" in chunk.text.lower()
    
    def test_chunk_length_reasonable(self, chunker):
        """Verifica che i chunk abbiano lunghezza ragionevole"""
        chunks = chunker.generate_all_chunks()
        
        for chunk in chunks[:20]:
            # Non troppo corto (alcuni TOOLS hanno pochi metadata)
            assert len(chunk.text) >= 100, \
                f"Chunk {chunk.doc_id} troppo corto: {len(chunk.text)} chars"
            # Non troppo lungo
            assert len(chunk.text) <= 5000, \
                f"Chunk {chunk.doc_id} troppo lungo: {len(chunk.text)} chars"


class TestSyntheticChunkDataclass:
    """Test per SyntheticChunk dataclass"""
    
    def test_create_basic(self):
        """Test creazione SyntheticChunk base"""
        chunk = SyntheticChunk(
            doc_id="MR-TEST",
            doc_type="MR",
            text="Test content"
        )
        
        assert chunk.doc_id == "MR-TEST"
        assert chunk.chunk_id == "MR-TEST_synthetic_001"
        assert chunk.chunk_type == "synthetic"
    
    def test_end_idx_auto(self):
        """Test che end_idx venga calcolato automaticamente"""
        text = "A" * 500
        chunk = SyntheticChunk(
            doc_id="TEST",
            doc_type="MR",
            text=text
        )
        
        assert chunk.end_idx == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

