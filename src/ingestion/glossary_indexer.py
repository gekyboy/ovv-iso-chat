"""
Glossary Indexer per OVV ISO Chat v3.3
Indicizza definizioni glossario come collezione Qdrant separata (R22)

Features:
- Collezione `glossary_terms` con embedding BGE-M3
- Testo ricercabile: "ACRONIMO = significato completo. descrizione"
- Metadata: acronym, full, description, ambiguous
- Ricerca semantica su definizioni glossario

Architettura:
- Riusa BGEEmbedder da indexer.py (stesso modello)
- Collezione separata per retrieval parallelo
- Merge con RRF nel rag_pipeline
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import yaml
import json

logger = logging.getLogger(__name__)


@dataclass
class GlossaryTerm:
    """Singolo termine del glossario indicizzabile"""
    acronym: str
    full: str
    description: str
    ambiguous: bool = False
    context: Optional[str] = None
    
    @property
    def searchable_text(self) -> str:
        """
        Testo usato per embedding e ricerca.
        Include acronimo, significato completo e descrizione.
        """
        parts = [f"{self.acronym} = {self.full}"]
        if self.description:
            parts.append(self.description)
        if self.context:
            parts.append(f"Contesto: {self.context}")
        return ". ".join(parts)
    
    def to_payload(self) -> Dict[str, Any]:
        """Payload per Qdrant point"""
        return {
            "acronym": self.acronym,
            "full": self.full,
            "description": self.description,
            "ambiguous": self.ambiguous,
            "context": self.context,
            "text": self.searchable_text,
            "source_type": "glossary"
        }


@dataclass
class GlossaryIndexStats:
    """Statistiche indicizzazione glossario"""
    total_terms: int = 0
    indexed_terms: int = 0
    failed_terms: int = 0
    ambiguous_terms: int = 0
    collection_name: str = ""


class GlossaryIndexer:
    """
    Indicizza il glossario come collezione Qdrant separata.
    
    Collection: glossary_terms
    Vector: BGE-M3 1024 dim (stesso modello dei documenti)
    
    Uso:
        indexer = GlossaryIndexer()
        indexer.index_glossary(recreate=True)
        results = indexer.search("World Class Manufacturing")
    """
    
    COLLECTION_NAME = "glossary_terms"
    
    def __init__(
        self,
        config: Optional[Dict] = None,
        config_path: str = "config/config.yaml",
        glossary_path: Optional[str] = None
    ):
        """
        Inizializza l'indexer glossario.
        
        Args:
            config: Configurazione opzionale (priorità)
            config_path: Percorso config.yaml
            glossary_path: Percorso glossary.json (override)
        """
        self.config = config or self._load_config(config_path)
        self.config_path = config_path
        
        # Percorso glossario
        if glossary_path:
            self.glossary_path = Path(glossary_path)
        else:
            memory_config = self.config.get("memory", {})
            self.glossary_path = Path(
                memory_config.get("glossary_path", "config/glossary.json")
            )
        
        # Config Qdrant (stessa del docs indexer)
        qdrant_config = self.config.get("qdrant", {})
        self.qdrant_url = qdrant_config.get("url", "http://localhost:6333")
        self.vector_size = qdrant_config.get("vector_size", 1024)
        
        # Config dual embedding (R22)
        dual_config = self.config.get("dual_embedding", {})
        self.glossary_top_k = dual_config.get("glossary_top_k", 5)
        self.score_threshold = dual_config.get("glossary_score_threshold", 0.5)
        
        # Lazy loading
        self._qdrant_client = None
        self._embedder = None
        
        logger.info(
            f"GlossaryIndexer: collection={self.COLLECTION_NAME}, "
            f"glossary={self.glossary_path}"
        )
    
    def _load_config(self, config_path: str) -> Dict:
        """Carica configurazione da YAML"""
        path = Path(config_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    @property
    def qdrant_client(self):
        """Lazy loading Qdrant client"""
        if self._qdrant_client is None:
            from qdrant_client import QdrantClient
            self._qdrant_client = QdrantClient(url=self.qdrant_url)
            logger.debug(f"Connesso a Qdrant: {self.qdrant_url}")
        return self._qdrant_client
    
    @property
    def embedder(self):
        """Lazy loading embedder (riusa BGEEmbedder da indexer)"""
        if self._embedder is None:
            from .indexer import BGEEmbedder
            embed_config = self.config.get("embedding", {})
            self._embedder = BGEEmbedder(
                model_name=embed_config.get("model", "BAAI/bge-m3"),
                device=embed_config.get("device", "cuda"),
                batch_size=embed_config.get("batch_size", 16),
                batch_size_fallback=embed_config.get("batch_size_low_vram", 8)
            )
        return self._embedder
    
    def load_glossary(self) -> List[GlossaryTerm]:
        """
        Carica termini dal glossary.json.
        Gestisce acronimi normali e ambigui (con definitions[]).
        
        Returns:
            Lista di GlossaryTerm
        """
        if not self.glossary_path.exists():
            logger.error(f"Glossario non trovato: {self.glossary_path}")
            return []
        
        try:
            with open(self.glossary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Errore lettura glossario: {e}")
            return []
        
        terms = []
        acronyms = data.get("acronyms", {})
        
        for acronym, info in acronyms.items():
            # Salta commenti/metadata (chiavi che iniziano con _)
            if acronym.startswith("_"):
                continue
            
            # Gestisci acronimi ambigui (hanno "definitions" array)
            if info.get("ambiguous", False) and "definitions" in info:
                for defn in info["definitions"]:
                    terms.append(GlossaryTerm(
                        acronym=acronym,
                        full=defn.get("full", ""),
                        description=defn.get("description", ""),
                        ambiguous=True,
                        context=defn.get("context", "")
                    ))
            else:
                # Acronimo normale
                terms.append(GlossaryTerm(
                    acronym=acronym,
                    full=info.get("full", ""),
                    description=info.get("description", ""),
                    ambiguous=False
                ))
        
        # Aggiungi anche ISO standards se presenti
        iso_standards = data.get("iso_standards", {})
        for code, description in iso_standards.items():
            terms.append(GlossaryTerm(
                acronym=f"ISO {code}",
                full=f"ISO {code}",
                description=description,
                ambiguous=False
            ))
        
        logger.info(f"Caricati {len(terms)} termini dal glossario")
        return terms
    
    def create_collection(self, recreate: bool = False) -> bool:
        """
        Crea collezione glossary_terms in Qdrant.
        
        Args:
            recreate: Se True, elimina e ricrea collezione esistente
            
        Returns:
            True se successo
        """
        from qdrant_client.models import Distance, VectorParams
        
        try:
            # Check se esiste
            collections = self.qdrant_client.get_collections().collections
            exists = any(c.name == self.COLLECTION_NAME for c in collections)
            
            if exists and recreate:
                logger.info(f"Eliminazione collezione: {self.COLLECTION_NAME}")
                self.qdrant_client.delete_collection(self.COLLECTION_NAME)
                exists = False
            
            if not exists:
                logger.info(f"Creazione collezione: {self.COLLECTION_NAME}")
                
                self.qdrant_client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Collezione '{self.COLLECTION_NAME}' creata")
            else:
                logger.info(f"Collezione '{self.COLLECTION_NAME}' già esistente")
            
            return True
            
        except Exception as e:
            logger.error(f"Errore creazione collezione: {e}")
            return False
    
    def index_glossary(self, recreate: bool = False) -> GlossaryIndexStats:
        """
        Indicizza tutti i termini del glossario in Qdrant.
        
        Args:
            recreate: Se True, ricrea collezione (elimina esistente)
            
        Returns:
            GlossaryIndexStats con statistiche
        """
        from qdrant_client.models import PointStruct
        
        stats = GlossaryIndexStats(collection_name=self.COLLECTION_NAME)
        
        # 1. Carica termini
        terms = self.load_glossary()
        if not terms:
            logger.warning("Nessun termine da indicizzare")
            return stats
        
        stats.total_terms = len(terms)
        stats.ambiguous_terms = sum(1 for t in terms if t.ambiguous)
        
        # 2. Crea/ricrea collezione
        if not self.create_collection(recreate=recreate):
            stats.failed_terms = len(terms)
            return stats
        
        # 3. Genera embedding per tutti i termini
        texts = [t.searchable_text for t in terms]
        logger.info(f"Generazione embedding per {len(texts)} termini glossario...")
        
        try:
            embeddings = self.embedder.encode(
                texts,
                return_sparse=False,  # Solo dense per glossario
                show_progress=True
            )
            dense_vectors = embeddings["dense"]
        except Exception as e:
            logger.error(f"Errore generazione embedding: {e}")
            stats.failed_terms = len(terms)
            return stats
        
        # 4. Crea points per Qdrant
        points = []
        for i, term in enumerate(terms):
            # ID univoco basato su acronimo + context
            point_id = abs(hash(f"{term.acronym}_{term.context or 'default'}_{i}")) % (2**63)
            
            # Converti vector
            vector = dense_vectors[i]
            vector_list = vector.tolist() if hasattr(vector, 'tolist') else list(vector)
            
            points.append(PointStruct(
                id=point_id,
                vector=vector_list,
                payload=term.to_payload()
            ))
        
        # 5. Upload in Qdrant
        try:
            self.qdrant_client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points
            )
            stats.indexed_terms = len(points)
            logger.info(f"Indicizzati {len(points)} termini glossario")
            
        except Exception as e:
            logger.error(f"Errore upload Qdrant: {e}")
            stats.failed_terms = len(points)
        
        return stats
    
    def search(
        self,
        query: str,
        limit: int = 5,
        score_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Cerca nel glossario.
        
        Args:
            query: Query di ricerca
            limit: Max risultati
            score_threshold: Soglia minima score (0-1)
            
        Returns:
            Lista di risultati con score e campi glossario
        """
        try:
            # Genera embedding query
            embeddings = self.embedder.encode(
                [query],
                return_sparse=False,
                show_progress=False
            )
            query_vector = embeddings["dense"][0]
            query_vector_list = query_vector.tolist() if hasattr(query_vector, 'tolist') else list(query_vector)
            
            # Cerca in Qdrant
            results = self.qdrant_client.search(
                collection_name=self.COLLECTION_NAME,
                query_vector=query_vector_list,
                limit=limit,
                score_threshold=score_threshold
            )
            
            # Formatta risultati
            formatted = []
            for hit in results:
                payload = hit.payload or {}
                formatted.append({
                    "score": float(hit.score),
                    "acronym": payload.get("acronym", ""),
                    "full": payload.get("full", ""),
                    "description": payload.get("description", ""),
                    "text": payload.get("text", ""),
                    "ambiguous": payload.get("ambiguous", False),
                    "context": payload.get("context", ""),
                    "source_type": "glossary"
                })
            
            logger.debug(f"Glossary search '{query[:30]}...': {len(formatted)} risultati")
            return formatted
            
        except Exception as e:
            logger.error(f"Errore ricerca glossario: {e}")
            return []
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Ottiene informazioni sulla collezione glossario"""
        try:
            info = self.qdrant_client.get_collection(self.COLLECTION_NAME)
            return {
                "name": self.COLLECTION_NAME,
                "points_count": info.points_count,
                "status": info.status.name,
                "vector_size": self.vector_size
            }
        except Exception as e:
            return {"error": str(e), "name": self.COLLECTION_NAME}
    
    def collection_exists(self) -> bool:
        """Verifica se la collezione esiste"""
        try:
            collections = self.qdrant_client.get_collections().collections
            return any(c.name == self.COLLECTION_NAME for c in collections)
        except Exception:
            return False


# CLI per indicizzazione standalone
if __name__ == "__main__":
    import sys
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    parser = argparse.ArgumentParser(description="Indicizza glossario in Qdrant")
    parser.add_argument("--recreate", action="store_true", help="Ricrea collezione")
    parser.add_argument("--config", default="config/config.yaml", help="Config path")
    parser.add_argument("--search", type=str, help="Test ricerca")
    
    args = parser.parse_args()
    
    indexer = GlossaryIndexer(config_path=args.config)
    
    if args.search:
        # Modalità ricerca
        print(f"\nRicerca: '{args.search}'")
        results = indexer.search(args.search, limit=5)
        for i, r in enumerate(results, 1):
            print(f"\n{i}. {r['acronym']} (score: {r['score']:.3f})")
            print(f"   {r['full']}")
            if r['description']:
                print(f"   {r['description'][:100]}...")
    else:
        # Modalità indicizzazione
        print("\n" + "=" * 60)
        print("R22: INDICIZZAZIONE GLOSSARIO")
        print("=" * 60)
        
        stats = indexer.index_glossary(recreate=args.recreate)
        
        print(f"\nRisultato:")
        print(f"  Termini totali: {stats.total_terms}")
        print(f"  Indicizzati: {stats.indexed_terms}")
        print(f"  Falliti: {stats.failed_terms}")
        print(f"  Ambigui: {stats.ambiguous_terms}")
        
        info = indexer.get_collection_info()
        print(f"\nCollezione: {info}")

