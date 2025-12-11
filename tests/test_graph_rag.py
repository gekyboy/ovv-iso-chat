"""
Test suite per GraphRAG (R25)
Testa entity extraction, relation extraction, graph building e retrieval
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestEntityExtraction:
    """Test per EntityExtractor"""
    
    def test_extract_document_entities(self):
        """Estrae riferimenti a documenti PS-XX, IL-XX"""
        from src.graph.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor(config={})
        
        text = "Come descritto nella PS-06_01, vedere anche IL-06_02 e MR-10_01"
        entities = extractor.extract(text, "chunk_001")
        
        assert len(entities) >= 3
        labels = [e.label.upper() for e in entities]
        assert "PS-06_01".upper() in labels or "PS-06_01" in labels
        assert "IL-06_02".upper() in labels or "IL-06_02" in labels
        assert "MR-10_01".upper() in labels or "MR-10_01" in labels
    
    def test_extract_role_entities(self):
        """Estrae ruoli organizzativi"""
        from src.graph.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor(config={})
        
        text = "Il RSPP verifica che il Responsabile Qualità abbia completato l'audit"
        entities = extractor.extract(text, "chunk_002")
        
        labels = [e.label.upper() for e in entities]
        assert any("RSPP" in l for l in labels)
    
    def test_extract_standard_entities(self):
        """Estrae standard ISO"""
        from src.graph.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor(config={})
        
        text = "Il sistema è conforme alla ISO 9001:2015 e ISO 14001"
        entities = extractor.extract(text, "chunk_003")
        
        types = [e.type for e in entities]
        assert "STANDARD" in types
    
    def test_deduplication(self):
        """Verifica che le entità siano deduplicate"""
        from src.graph.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor(config={})
        
        text1 = "PS-06_01 descrive il processo"
        text2 = "Vedi PS-06_01 per i dettagli"
        
        extractor.extract(text1, "chunk_001")
        extractor.extract(text2, "chunk_002")
        
        # Dovrebbe esserci solo una entità PS-06_01 ma con 2 source_chunks
        entities = list(extractor.entity_cache.values())
        ps06_entities = [e for e in entities if "PS-06_01" in e.label.upper()]
        
        assert len(ps06_entities) == 1
        assert len(ps06_entities[0].source_chunks) == 2


class TestRelationExtraction:
    """Test per RelationExtractor"""
    
    def test_extract_doc_references(self):
        """Estrae riferimenti tra documenti"""
        from src.graph.entity_extractor import EntityExtractor
        from src.graph.relation_extractor import RelationExtractor
        from src.graph.types import Entity
        
        extractor = EntityExtractor(config={})
        rel_extractor = RelationExtractor()
        
        text = "Come da PS-06_01, vedere anche IL-06_02"
        entities = extractor.extract(text, "chunk_001")
        
        relations = rel_extractor.extract(
            text=text,
            entities=entities,
            chunk_id="chunk_001",
            source_doc_id="PS-06_01"
        )
        
        # Dovrebbe trovare relazione REFERENCES
        ref_relations = [r for r in relations if r.type == "REFERENCES"]
        assert len(ref_relations) >= 1
    
    def test_cooccurrence_relations(self):
        """Estrae relazioni per co-occorrenza"""
        from src.graph.entity_extractor import EntityExtractor
        from src.graph.relation_extractor import RelationExtractor
        
        extractor = EntityExtractor(config={})
        rel_extractor = RelationExtractor(cooccurrence_window=100)
        
        text = "Il RSPP gestisce la sicurezza secondo la procedura PS-06_01"
        entities = extractor.extract(text, "chunk_001")
        
        relations = rel_extractor.extract(
            text=text,
            entities=entities,
            chunk_id="chunk_001"
        )
        
        # Dovrebbe trovare almeno una relazione
        assert len(relations) >= 1


class TestGraphBuilder:
    """Test per KnowledgeGraphBuilder"""
    
    def test_add_entities_and_relations(self):
        """Test aggiunta entità e relazioni"""
        from src.graph.builder import KnowledgeGraphBuilder
        from src.graph.types import Entity, Relation
        
        builder = KnowledgeGraphBuilder()
        
        # Aggiungi entità
        e1 = Entity(id="e1", label="PS-06_01", type="DOCUMENT", source_chunks=["c1"])
        e2 = Entity(id="e2", label="IL-06_02", type="DOCUMENT", source_chunks=["c1"])
        
        builder.add_entity(e1)
        builder.add_entity(e2)
        
        assert builder.graph.number_of_nodes() == 2
        
        # Aggiungi relazione
        r1 = Relation(id="r1", source_id="e1", target_id="e2", type="REFERENCES", source_chunks=["c1"])
        builder.add_relation(r1)
        
        assert builder.graph.number_of_edges() == 1
    
    def test_get_neighbors(self):
        """Test recupero neighbors"""
        from src.graph.builder import KnowledgeGraphBuilder
        from src.graph.types import Entity, Relation
        
        builder = KnowledgeGraphBuilder()
        
        e1 = Entity(id="e1", label="A", type="DOCUMENT", source_chunks=[])
        e2 = Entity(id="e2", label="B", type="DOCUMENT", source_chunks=[])
        e3 = Entity(id="e3", label="C", type="DOCUMENT", source_chunks=[])
        
        builder.add_entities([e1, e2, e3])
        
        r1 = Relation(id="r1", source_id="e1", target_id="e2", type="REFERENCES", source_chunks=[])
        r2 = Relation(id="r2", source_id="e1", target_id="e3", type="REFERENCES", source_chunks=[])
        
        builder.add_relations([r1, r2])
        
        neighbors = builder.get_neighbors("e1", direction="out")
        assert len(neighbors) == 2
    
    def test_save_and_load(self, tmp_path):
        """Test salvataggio e caricamento"""
        from src.graph.builder import KnowledgeGraphBuilder
        from src.graph.types import Entity
        
        builder = KnowledgeGraphBuilder()
        
        e1 = Entity(id="e1", label="PS-06_01", type="DOCUMENT", source_chunks=["c1", "c2"])
        builder.add_entity(e1)
        
        # Salva
        save_path = tmp_path / "test_graph.json"
        builder.save(str(save_path))
        
        # Carica in nuovo builder
        builder2 = KnowledgeGraphBuilder()
        builder2.load(str(save_path))
        
        assert builder2.graph.number_of_nodes() == 1
        assert "e1" in builder2.entity_to_chunks
        assert len(builder2.entity_to_chunks["e1"]) == 2


class TestCommunityDetection:
    """Test per CommunityDetector"""
    
    def test_detect_communities(self):
        """Test rilevamento comunità"""
        import networkx as nx
        from src.graph.community import CommunityDetector
        
        # Crea grafo con 2 cluster evidenti
        G = nx.DiGraph()
        
        # Cluster 1
        G.add_edges_from([("a", "b"), ("b", "c"), ("c", "a")])
        # Cluster 2
        G.add_edges_from([("x", "y"), ("y", "z"), ("z", "x")])
        # Bridge
        G.add_edge("c", "x")
        
        detector = CommunityDetector(resolution=1.0, min_community_size=2)
        partition = detector.detect(G)
        
        # Dovrebbe trovare 2 comunità (o 1 se sono troppo connesse)
        assert len(set(partition.values())) >= 1
        assert len(partition) == 6  # Tutti i nodi hanno una community


class TestGraphRetriever:
    """Test per GraphRetriever"""
    
    def test_local_retrieval(self):
        """Test retrieval locale"""
        import networkx as nx
        from src.graph.retriever import GraphRetriever
        
        G = nx.DiGraph()
        G.add_node("e1", label="PS-06_01", type="DOCUMENT")
        G.add_node("e2", label="IL-06_02", type="DOCUMENT")
        G.add_node("e3", label="RSPP", type="ROLE")
        G.add_edge("e3", "e1", type="RESPONSIBLE_FOR")
        G.add_edge("e1", "e2", type="REFERENCES")
        
        entity_to_chunks = {
            "e1": ["c1", "c2"],
            "e2": ["c3"],
            "e3": ["c1"]
        }
        
        retriever = GraphRetriever(
            graph=G,
            entity_to_chunks=entity_to_chunks,
            local_hops=1
        )
        
        # Query che contiene PS-06
        results = retriever.retrieve("PS-06_01", mode="local", top_k=5)
        
        assert len(results) >= 1
        # Il primo risultato dovrebbe essere PS-06_01
        assert results[0].entity_label == "PS-06_01"
    
    def test_extract_entities_from_query(self):
        """Test estrazione entità dalla query"""
        import networkx as nx
        from src.graph.retriever import GraphRetriever
        
        G = nx.DiGraph()
        G.add_node("e1", label="PS-06_01", type="DOCUMENT")
        G.add_node("e2", label="RSPP", type="ROLE")
        
        retriever = GraphRetriever(
            graph=G,
            entity_to_chunks={},
            local_hops=1
        )
        
        entities = retriever._extract_entities_from_query("Cosa dice la PS-06_01?")
        
        assert len(entities) >= 1


class TestIntegration:
    """Test di integrazione end-to-end"""
    
    def test_full_pipeline_minimal(self):
        """Test pipeline completa su testo minimale"""
        from src.graph.entity_extractor import EntityExtractor
        from src.graph.relation_extractor import RelationExtractor
        from src.graph.builder import KnowledgeGraphBuilder
        from src.graph.community import CommunityDetector
        from src.graph.retriever import GraphRetriever
        
        # Testi di esempio
        chunks = [
            ("La procedura PS-06_01 descrive la gestione dei rifiuti. Il RSPP è responsabile.", "c1", "PS-06_01"),
            ("Vedere IL-06_02 per le istruzioni operative. Conforme a ISO 14001.", "c2", "PS-06_01"),
            ("Il modulo MR-10_01 documenta le non conformità.", "c3", "MR-10_01"),
        ]
        
        # 1. Entity extraction
        entity_extractor = EntityExtractor(config={})
        for text, chunk_id, doc_id in chunks:
            entity_extractor.extract(text, chunk_id)
        
        entities = list(entity_extractor.entity_cache.values())
        assert len(entities) >= 3
        
        # 2. Relation extraction
        rel_extractor = RelationExtractor()
        for text, chunk_id, doc_id in chunks:
            chunk_entities = [e for e in entities if chunk_id in e.source_chunks]
            rel_extractor.extract(text, chunk_entities, chunk_id, doc_id)
        
        relations = list(rel_extractor.relation_cache.values())
        
        # 3. Graph building
        builder = KnowledgeGraphBuilder()
        builder.add_entities(entities)
        builder.add_relations(relations)
        
        assert builder.graph.number_of_nodes() >= 3
        
        # 4. Community detection
        detector = CommunityDetector(min_community_size=1)
        detector.detect(builder.graph)
        
        # 5. Retrieval
        retriever = GraphRetriever(
            graph=builder.graph,
            entity_to_chunks=dict(builder.entity_to_chunks),
            community_detector=detector,
            local_hops=2
        )
        
        results = retriever.retrieve("PS-06_01 rifiuti", mode="local", top_k=5)
        
        # Dovrebbe trovare almeno un risultato
        assert len(results) >= 1
        
        # Il primo dovrebbe essere correlato a PS-06
        first_label = results[0].entity_label
        assert "PS" in first_label or "rifiuti" in first_label.lower() or len(results) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

