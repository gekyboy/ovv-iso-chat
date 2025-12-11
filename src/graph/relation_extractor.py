"""
Relation Extractor per GraphRAG (R25)
Estrae relazioni tra entità usando pattern matching e co-occorrenza

Strategie:
1. Pattern-based: "X è responsabile di Y", "vedi PS-06", "come da IL-XX"
2. Co-occurrence: Entità vicine nel testo (window-based)
3. Document reference: Citazioni tra documenti

Ottimizzato per CPU - no VRAM usage
"""

import re
import logging
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict

from src.graph.types import Entity, Relation, RelationType, EntityType

logger = logging.getLogger(__name__)


# Pattern per relazioni documento → documento
DOC_REFERENCE_PATTERNS = [
    # "vedi PS-06_01", "vedere IL-06_02"
    (r'\bved(?:i|ere|asi)\s+((?:PS|IL|MR|TOOLS|WO)-\d{2}(?:_\d{2})?)\b', "REFERENCES"),
    # "come da PS-06", "secondo PS-06_01"
    (r'\b(?:come da|secondo|ai sensi di)\s+((?:PS|IL|MR|TOOLS|WO)-\d{2}(?:_\d{2})?)\b', "REFERENCES"),
    # "rif. PS-06", "cfr. IL-06"
    (r'\b(?:rif\.?|cfr\.?)\s*((?:PS|IL|MR|TOOLS|WO)-\d{2}(?:_\d{2})?)\b', "REFERENCES"),
    # "procedura PS-06", "istruzione IL-06"
    (r'\b(?:procedura|istruzione|modulo)\s+((?:PS|IL|MR|TOOLS|WO)-\d{2}(?:_\d{2})?)\b', "REFERENCES"),
]

# Pattern per relazioni ruolo → responsabilità
RESPONSIBILITY_PATTERNS = [
    # "RSPP è responsabile di/per"
    (r'\b(\w+)\s+(?:è|sono)\s+responsabile?\s+(?:di|per|della|del)\s+(.{5,50}?)(?:\.|,|;|\n)', "RESPONSIBLE_FOR"),
    # "il Responsabile Qualità verifica"
    (r'\b(?:il|la)\s+(Responsabile\s+\w+|RSPP|RGQ)\s+(?:verifica|approva|gestisce|coordina)\s+(.{5,30})', "RESPONSIBLE_FOR"),
    # "compito di X è"
    (r'\bcompito\s+(?:di|del|della)\s+(\w+(?:\s+\w+)?)\s+è\s+(.{5,50}?)(?:\.|,)', "RESPONSIBLE_FOR"),
]

# Pattern per relazioni processo → processo
DEPENDENCY_PATTERNS = [
    # "dopo X si procede con Y"
    (r'\bdopo\s+(.{5,30}?)\s+si\s+(?:procede|passa)\s+(?:con|a)\s+(.{5,30}?)(?:\.|,)', "DEPENDS_ON"),
    # "X richiede Y"
    (r'\b(.{5,30}?)\s+richiede\s+(.{5,30}?)(?:\.|,)', "DEPENDS_ON"),
    # "prerequisito: X"
    (r'\bprerequisito:\s*(.{5,30})', "DEPENDS_ON"),
]

# Pattern per definizioni
DEFINITION_PATTERNS = [
    # "X significa Y", "X = Y"
    (r'\b(\w+)\s+(?:significa|indica|è)\s+(.{5,50}?)(?:\.|,|\n)', "DEFINES"),
    # "Per X si intende Y"
    (r'\bper\s+(\w+)\s+si\s+intende\s+(.{5,50}?)(?:\.|,)', "DEFINES"),
]

# Pattern per conformità a standard
COMPLIANCE_PATTERNS = [
    # "conforme a ISO 9001"
    (r'\bconforme?\s+(?:a|alla|al)\s+(ISO\s*\d+|IATF\s*\d+|UNI\s*EN\s*\d+)', "COMPLIES_WITH"),
    # "secondo ISO 14001"
    (r'\bsecondo\s+(?:la\s+)?(ISO\s*\d+|IATF\s*\d+)', "COMPLIES_WITH"),
    # "requisiti ISO 45001"
    (r'\brequisiti\s+(?:della?\s+)?(ISO\s*\d+|IATF\s*\d+)', "COMPLIES_WITH"),
]


class RelationExtractor:
    """
    Estrattore di relazioni tra entità.
    Combina pattern matching con co-occurrence analysis.
    """
    
    def __init__(
        self,
        cooccurrence_window: int = 100,
        min_confidence: float = 0.5
    ):
        """
        Inizializza l'estrattore
        
        Args:
            cooccurrence_window: Distanza max in caratteri per co-occurrence
            min_confidence: Confidence minima per includere relazione
        """
        self.cooccurrence_window = cooccurrence_window
        self.min_confidence = min_confidence
        
        # Compila pattern
        self.patterns = self._compile_patterns()
        
        # Cache relazioni
        self.relation_cache: Dict[str, Relation] = {}
        
        # Stats
        self.stats = defaultdict(int)
        
        logger.info(f"RelationExtractor inizializzato (window={cooccurrence_window})")
    
    def _compile_patterns(self) -> Dict[str, List[Tuple[re.Pattern, RelationType]]]:
        """Compila tutti i pattern regex"""
        all_patterns = {
            "doc_reference": DOC_REFERENCE_PATTERNS,
            "responsibility": RESPONSIBILITY_PATTERNS,
            "dependency": DEPENDENCY_PATTERNS,
            "definition": DEFINITION_PATTERNS,
            "compliance": COMPLIANCE_PATTERNS,
        }
        
        compiled = {}
        for category, patterns in all_patterns.items():
            compiled[category] = [
                (re.compile(p, re.IGNORECASE | re.MULTILINE), rel_type)
                for p, rel_type in patterns
            ]
        
        return compiled
    
    def extract(
        self,
        text: str,
        entities: List[Entity],
        chunk_id: str,
        source_doc_id: Optional[str] = None
    ) -> List[Relation]:
        """
        Estrae relazioni da un chunk di testo
        
        Args:
            text: Testo del chunk
            entities: Entità già estratte dal chunk
            chunk_id: ID del chunk
            source_doc_id: ID documento sorgente (per relazioni REFERENCES)
            
        Returns:
            Lista di Relation estratte
        """
        relations: List[Relation] = []
        
        # Mappa entity label → entity per lookup veloce
        entity_map = {e.label.upper(): e for e in entities}
        entity_by_id = {e.id: e for e in entities}
        
        # 1. Pattern-based extraction per documenti
        if source_doc_id:
            doc_relations = self._extract_doc_references(
                text, source_doc_id, chunk_id, entity_map
            )
            relations.extend(doc_relations)
        
        # 2. Pattern-based per altri tipi
        pattern_relations = self._extract_by_patterns(
            text, chunk_id, entity_map
        )
        relations.extend(pattern_relations)
        
        # 3. Co-occurrence based
        cooccurrence_relations = self._extract_cooccurrence(
            text, entities, chunk_id
        )
        relations.extend(cooccurrence_relations)
        
        self.stats["total_extractions"] += len(relations)
        
        return relations
    
    def _extract_doc_references(
        self,
        text: str,
        source_doc_id: str,
        chunk_id: str,
        entity_map: Dict[str, Entity]
    ) -> List[Relation]:
        """Estrae riferimenti tra documenti"""
        relations = []
        
        for pattern, rel_type in self.patterns.get("doc_reference", []):
            for match in pattern.finditer(text):
                target_doc = match.group(1).upper()
                
                # Skip self-reference
                if target_doc == source_doc_id.upper():
                    continue
                
                # Crea relazione source_doc → target_doc
                source_entity_id = Entity.create_id(source_doc_id, "DOCUMENT")
                target_entity_id = Entity.create_id(target_doc, "DOCUMENT")
                
                relation = self._get_or_create_relation(
                    source_id=source_entity_id,
                    target_id=target_entity_id,
                    rel_type=rel_type,
                    chunk_id=chunk_id,
                    confidence=0.95
                )
                relations.append(relation)
                self.stats["doc_references"] += 1
        
        return relations
    
    def _extract_by_patterns(
        self,
        text: str,
        chunk_id: str,
        entity_map: Dict[str, Entity]
    ) -> List[Relation]:
        """Estrae relazioni usando pattern generici"""
        relations = []
        
        # Compliance patterns
        for pattern, rel_type in self.patterns.get("compliance", []):
            for match in pattern.finditer(text):
                standard = match.group(1).upper().replace(" ", "")
                
                # Trova entità processo/documento nel contesto
                context = text[max(0, match.start()-100):match.start()]
                
                # Cerca entità DOCUMENT o PROCESS nel contesto
                for label, entity in entity_map.items():
                    if entity.type in ["DOCUMENT", "PROCESS"]:
                        if label in context.upper():
                            target_entity_id = Entity.create_id(standard, "STANDARD")
                            
                            relation = self._get_or_create_relation(
                                source_id=entity.id,
                                target_id=target_entity_id,
                                rel_type=rel_type,
                                chunk_id=chunk_id,
                                confidence=0.80
                            )
                            relations.append(relation)
                            self.stats["compliance_relations"] += 1
        
        return relations
    
    def _extract_cooccurrence(
        self,
        text: str,
        entities: List[Entity],
        chunk_id: str
    ) -> List[Relation]:
        """
        Estrae relazioni basate su co-occorrenza nel testo.
        Entità che appaiono vicine sono probabilmente correlate.
        """
        relations = []
        
        if len(entities) < 2:
            return relations
        
        # Trova posizione di ogni entità nel testo
        entity_positions: List[Tuple[Entity, int, int]] = []
        
        for entity in entities:
            pattern = re.compile(rf'\b{re.escape(entity.label)}\b', re.IGNORECASE)
            for match in pattern.finditer(text):
                entity_positions.append((entity, match.start(), match.end()))
        
        # Ordina per posizione
        entity_positions.sort(key=lambda x: x[1])
        
        # Trova coppie entro la window
        for i, (entity1, start1, end1) in enumerate(entity_positions):
            for j in range(i + 1, len(entity_positions)):
                entity2, start2, end2 = entity_positions[j]
                
                # Check distanza
                distance = start2 - end1
                if distance > self.cooccurrence_window:
                    break  # Troppo lontano, stop
                
                if distance < 0:
                    continue  # Overlap, skip
                
                # Skip self-relation
                if entity1.id == entity2.id:
                    continue
                
                # Skip relazioni tra stessi tipi (tranne DOCUMENT → DOCUMENT)
                if entity1.type == entity2.type and entity1.type != "DOCUMENT":
                    continue
                
                # Determina tipo relazione basato sui tipi di entità
                rel_type = self._infer_relation_type(entity1, entity2)
                
                # Confidence inversamente proporzionale alla distanza
                confidence = max(0.5, 1.0 - (distance / self.cooccurrence_window) * 0.5)
                
                if confidence >= self.min_confidence:
                    relation = self._get_or_create_relation(
                        source_id=entity1.id,
                        target_id=entity2.id,
                        rel_type=rel_type,
                        chunk_id=chunk_id,
                        confidence=confidence
                    )
                    relations.append(relation)
                    self.stats["cooccurrence_relations"] += 1
        
        return relations
    
    def _infer_relation_type(
        self,
        entity1: Entity,
        entity2: Entity
    ) -> RelationType:
        """Inferisce il tipo di relazione dai tipi delle entità"""
        type1, type2 = entity1.type, entity2.type
        
        # Ruolo → Processo/Documento = RESPONSIBLE_FOR
        if type1 == "ROLE" and type2 in ["PROCESS", "DOCUMENT"]:
            return "RESPONSIBLE_FOR"
        if type2 == "ROLE" and type1 in ["PROCESS", "DOCUMENT"]:
            return "RESPONSIBLE_FOR"  # Invertirà la direzione
        
        # Documento → Documento = REFERENCES
        if type1 == "DOCUMENT" and type2 == "DOCUMENT":
            return "REFERENCES"
        
        # Documento → Concetto = DEFINES
        if type1 == "DOCUMENT" and type2 in ["CONCEPT", "ACRONYM"]:
            return "DEFINES"
        
        # Processo → Standard = COMPLIES_WITH
        if type1 == "PROCESS" and type2 == "STANDARD":
            return "COMPLIES_WITH"
        
        # Processo → Equipment = USES
        if type1 == "PROCESS" and type2 == "EQUIPMENT":
            return "USES"
        
        # Equipment → Location = LOCATED_IN
        if type1 == "EQUIPMENT" and type2 == "LOCATION":
            return "LOCATED_IN"
        
        # Concetto → Concetto = PART_OF (gerarchia)
        if type1 in ["CONCEPT", "ACRONYM"] and type2 in ["CONCEPT", "ACRONYM"]:
            return "PART_OF"
        
        # Default: co-occorrenza generica
        return "COOCCURS_WITH"
    
    def _get_or_create_relation(
        self,
        source_id: str,
        target_id: str,
        rel_type: RelationType,
        chunk_id: str,
        confidence: float = 1.0,
        metadata: Optional[Dict] = None
    ) -> Relation:
        """
        Ottiene relazione dalla cache o ne crea una nuova.
        Aggiorna source_chunks se già esistente.
        """
        relation_id = Relation.create_id(source_id, target_id, rel_type)
        
        if relation_id in self.relation_cache:
            # Aggiorna chunk list e confidence
            relation = self.relation_cache[relation_id]
            if chunk_id not in relation.source_chunks:
                relation.source_chunks.append(chunk_id)
            relation.confidence = max(relation.confidence, confidence)
            return relation
        
        # Crea nuova relazione
        relation = Relation(
            id=relation_id,
            source_id=source_id,
            target_id=target_id,
            type=rel_type,
            source_chunks=[chunk_id],
            confidence=confidence,
            metadata=metadata or {}
        )
        
        self.relation_cache[relation_id] = relation
        return relation
    
    def extract_batch(
        self,
        chunks_with_entities: List[Tuple[str, List[Entity], str, Optional[str]]],
        show_progress: bool = True
    ) -> List[Relation]:
        """
        Estrae relazioni da batch di chunk
        
        Args:
            chunks_with_entities: Lista di (text, entities, chunk_id, source_doc_id)
            show_progress: Se mostrare progress bar
            
        Returns:
            Lista completa di relazioni (deduplicate)
        """
        from tqdm import tqdm
        
        iterator = tqdm(chunks_with_entities, desc="Extracting relations") if show_progress else chunks_with_entities
        
        for text, entities, chunk_id, source_doc_id in iterator:
            self.extract(text, entities, chunk_id, source_doc_id)
        
        return list(self.relation_cache.values())
    
    def get_relations_by_type(
        self,
        rel_type: RelationType
    ) -> List[Relation]:
        """Filtra relazioni per tipo"""
        return [r for r in self.relation_cache.values() if r.type == rel_type]
    
    def get_relations_for_entity(
        self,
        entity_id: str
    ) -> List[Relation]:
        """Trova tutte le relazioni che coinvolgono un'entità"""
        return [
            r for r in self.relation_cache.values()
            if r.source_id == entity_id or r.target_id == entity_id
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Ritorna statistiche di estrazione"""
        relations_by_type = defaultdict(int)
        for relation in self.relation_cache.values():
            relations_by_type[relation.type] += 1
        
        return {
            "total_relations": len(self.relation_cache),
            "relations_by_type": dict(relations_by_type),
            "extraction_stats": dict(self.stats)
        }
    
    def clear_cache(self):
        """Pulisce la cache delle relazioni"""
        self.relation_cache.clear()
        self.stats.clear()

