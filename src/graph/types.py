"""
Tipi base per GraphRAG (R25)
Definisce Entity, Relation, Community e strutture dati correlate
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Literal, Any
from datetime import datetime
import hashlib


# Tipi di entità domain-specific per documenti ISO
EntityType = Literal[
    "DOCUMENT",     # PS-XX, IL-XX, MR-XX, TOOLS-XX
    "ROLE",         # RSPP, RGQ, Responsabile, Operatore
    "PROCESS",      # Gestione rifiuti, Audit, Non conformità
    "CONCEPT",      # WCM, PDCA, 5S, Quick Kaizen
    "EQUIPMENT",    # Pressa, CNC, PLC
    "LOCATION",     # Magazzino, Reparto, Linea
    "STANDARD",     # ISO 9001, ISO 14001, ISO 45001
    "ACRONYM"       # Acronimi dal glossario
]

# Tipi di relazioni
RelationType = Literal[
    "REFERENCES",       # Documento → Documento (cita, vedi)
    "RESPONSIBLE_FOR",  # Ruolo → Processo/Documento
    "DEPENDS_ON",       # Processo → Processo
    "DEFINES",          # Documento → Concetto
    "USES",             # Processo → Equipment
    "LOCATED_IN",       # Equipment → Location
    "PART_OF",          # Concetto → Concetto (gerarchia)
    "COMPLIES_WITH",    # Processo → Standard
    "COOCCURS_WITH"     # Co-occorrenza generica
]


@dataclass
class Entity:
    """Entità estratta da un chunk di testo"""
    
    id: str                          # Hash unico
    label: str                       # Nome leggibile (es. "PS-06_01", "RSPP")
    type: EntityType                 # Tipo entità
    source_chunks: List[str] = field(default_factory=list)  # Chunk IDs dove appare
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extra info
    confidence: float = 1.0          # Confidence score (0-1)
    created_at: datetime = field(default_factory=datetime.now)
    
    @staticmethod
    def create_id(label: str, entity_type: EntityType) -> str:
        """Genera ID deterministico da label e tipo"""
        key = f"{entity_type}:{label.upper()}"
        return hashlib.md5(key.encode()).hexdigest()[:12]
    
    def __post_init__(self):
        """Genera ID se non fornito"""
        if not self.id:
            self.id = self.create_id(self.label, self.type)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "source_chunks": self.source_chunks,
            "metadata": self.metadata,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Entity":
        data = data.copy()
        data["created_at"] = datetime.fromisoformat(data.get("created_at", datetime.now().isoformat()))
        return cls(**data)


@dataclass
class Relation:
    """Relazione tra due entità"""
    
    id: str                          # Hash unico
    source_id: str                   # Entity ID sorgente
    target_id: str                   # Entity ID destinazione
    type: RelationType               # Tipo relazione
    source_chunks: List[str] = field(default_factory=list)  # Chunk dove trovata
    confidence: float = 1.0          # Confidence score (0-1)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def create_id(source_id: str, target_id: str, rel_type: RelationType) -> str:
        """Genera ID deterministico"""
        key = f"{source_id}:{rel_type}:{target_id}"
        return hashlib.md5(key.encode()).hexdigest()[:12]
    
    def __post_init__(self):
        """Genera ID se non fornito"""
        if not self.id:
            self.id = self.create_id(self.source_id, self.target_id, self.type)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.type,
            "source_chunks": self.source_chunks,
            "confidence": self.confidence,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Relation":
        return cls(**data)


@dataclass
class CommunitySummary:
    """Riassunto di una comunità di entità correlate"""
    
    community_id: int                # ID comunità (da Louvain)
    entity_ids: List[str]            # Entità nella comunità
    summary: str                     # Riassunto testuale generato da LLM
    key_entities: List[str]          # Top 5 entità più importanti
    key_relations: List[str]         # Top 5 relazioni più importanti
    entity_count: int = 0
    relation_count: int = 0
    embedding: Optional[List[float]] = None  # Embedding del summary
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "community_id": self.community_id,
            "entity_ids": self.entity_ids,
            "summary": self.summary,
            "key_entities": self.key_entities,
            "key_relations": self.key_relations,
            "entity_count": self.entity_count,
            "relation_count": self.relation_count,
            "embedding": self.embedding,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CommunitySummary":
        return cls(**data)


@dataclass
class GraphResult:
    """Risultato di una query al knowledge graph"""
    
    entity_id: str                   # Entità trovata
    entity_label: str                # Label leggibile
    entity_type: EntityType          # Tipo entità
    score: float                     # Relevance score
    source: Literal["local", "global", "hybrid"]  # Modalità retrieval
    chunk_ids: List[str] = field(default_factory=list)  # Chunk associati
    related_entities: List[str] = field(default_factory=list)  # Entità correlate
    community_id: Optional[int] = None  # Comunità di appartenenza
    path: Optional[List[str]] = None   # Path nel grafo (se traversal)
    
    def to_dict(self) -> Dict:
        return {
            "entity_id": self.entity_id,
            "entity_label": self.entity_label,
            "entity_type": self.entity_type,
            "score": self.score,
            "source": self.source,
            "chunk_ids": self.chunk_ids,
            "related_entities": self.related_entities,
            "community_id": self.community_id,
            "path": self.path
        }


@dataclass
class GraphStats:
    """Statistiche del knowledge graph"""
    
    total_entities: int = 0
    total_relations: int = 0
    total_communities: int = 0
    entities_by_type: Dict[str, int] = field(default_factory=dict)
    relations_by_type: Dict[str, int] = field(default_factory=dict)
    avg_community_size: float = 0.0
    graph_density: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "total_entities": self.total_entities,
            "total_relations": self.total_relations,
            "total_communities": self.total_communities,
            "entities_by_type": self.entities_by_type,
            "relations_by_type": self.relations_by_type,
            "avg_community_size": self.avg_community_size,
            "graph_density": self.graph_density,
            "created_at": self.created_at.isoformat()
        }

