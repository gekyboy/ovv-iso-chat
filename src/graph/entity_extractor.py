"""
Entity Extractor per GraphRAG (R25)
Estrae entità tipizzate dai chunk di testo usando pattern matching + glossario

Strategie:
1. Pattern-based: Regex per documenti (PS-XX, IL-XX), ruoli noti
2. Glossary-based: Matching con glossary.json per acronimi/concetti
3. NER leggero: Per entità non coperte (opzionale)

Ottimizzato per CPU - no VRAM usage
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict

import yaml

from src.graph.types import Entity, EntityType

logger = logging.getLogger(__name__)


# Pattern regex per tipi di documento ISO
DOCUMENT_PATTERNS = {
    "DOCUMENT": [
        r'\b(PS-\d{2}(?:_\d{2})?)\b',      # PS-06, PS-06_01
        r'\b(IL-\d{2}(?:_\d{2})?)\b',      # IL-06, IL-06_02
        r'\b(MR-\d{2}(?:_\d{2})?)\b',      # MR-10, MR-10_01
        r'\b(TOOLS-\d{2}(?:_\d{2})?)\b',   # TOOLS-01, TOOLS-01_01
        r'\b(WO-\d{2}(?:_\d{2})?)\b',      # WO-01
    ]
}

# Pattern per ruoli organizzativi
ROLE_PATTERNS = {
    "ROLE": [
        r'\b(RSPP)\b',
        r'\b(RGQ)\b',
        r'\b(RGA)\b',
        r'\b(RSGSL)\b',
        r'\b(HSE)\b',
        r'\b(Direttore(?:\s+(?:Generale|Stabilimento|Produzione|Qualità))?)\b',
        r'\b(Responsabile(?:\s+(?:Qualità|Ambiente|Sicurezza|Produzione|Manutenzione|Acquisti|Logistica))?)\b',
        r'\b(Operatore(?:\s+(?:CNC|Pressa|Linea))?)\b',
        r'\b(Auditor(?:\s+(?:Interno|Esterno))?)\b',
        r'\b(Preposto)\b',
        r'\b(Addetto(?:\s+(?:Antincendio|Primo Soccorso))?)\b',
    ]
}

# Pattern per standard ISO
STANDARD_PATTERNS = {
    "STANDARD": [
        r'\b(ISO\s*9001(?::\d{4})?)\b',
        r'\b(ISO\s*14001(?::\d{4})?)\b',
        r'\b(ISO\s*45001(?::\d{4})?)\b',
        r'\b(IATF\s*16949(?::\d{4})?)\b',
        r'\b(UNI\s*EN\s*\d+(?::\d{4})?)\b',
    ]
}

# Pattern per equipment/attrezzature
EQUIPMENT_PATTERNS = {
    "EQUIPMENT": [
        r'\b(CNC)\b',
        r'\b(PLC)\b',
        r'\b(Pressa(?:\s+\w+)?)\b',
        r'\b(Tornio(?:\s+\w+)?)\b',
        r'\b(Fresatrice)\b',
        r'\b(Robot(?:\s+\w+)?)\b',
        r'\b(AGV)\b',
        r'\b(Muletto)\b',
        r'\b(Carroponte)\b',
    ]
}

# Pattern per location
LOCATION_PATTERNS = {
    "LOCATION": [
        r'\b(Magazzino(?:\s+(?:MP|PF|Semilavorati))?)\b',
        r'\b(Reparto(?:\s+\w+)?)\b',
        r'\b(Linea(?:\s+\d+|\s+\w+)?)\b',
        r'\b(Stabilimento(?:\s+\w+)?)\b',
        r'\b(Area(?:\s+(?:Produzione|Spedizione|Collaudo))?)\b',
    ]
}


class EntityExtractor:
    """
    Estrattore di entità da chunk di testo.
    Combina pattern matching con glossario per alta precision.
    """
    
    def __init__(
        self,
        config: Optional[Dict] = None,
        config_path: str = "config/config.yaml",
        glossary_path: Optional[str] = None
    ):
        """
        Inizializza l'estrattore
        
        Args:
            config: Configurazione diretta
            config_path: Percorso config.yaml
            glossary_path: Percorso glossary.json (override)
        """
        self.config = config or self._load_config(config_path)
        
        # Carica glossario
        glossary_path = glossary_path or self.config.get("memory", {}).get(
            "glossary_path", "config/glossary.json"
        )
        self.glossary = self._load_glossary(glossary_path)
        
        # Compila pattern
        self.patterns = self._compile_patterns()
        
        # Cache entità già estratte (per deduplicazione cross-chunk)
        self.entity_cache: Dict[str, Entity] = {}
        
        # Stats
        self.stats = defaultdict(int)
        
        logger.info(f"EntityExtractor inizializzato: {len(self.glossary)} termini glossario")
    
    def _load_config(self, config_path: str) -> Dict:
        """Carica configurazione"""
        if Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    def _load_glossary(self, glossary_path: str) -> Dict[str, Dict]:
        """Carica glossario da JSON"""
        path = Path(glossary_path)
        if not path.exists():
            logger.warning(f"Glossario non trovato: {glossary_path}")
            return {}
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Normalizza acronimi (tutto uppercase come chiave)
            glossary = {}
            for acronym, info in data.get("acronyms", {}).items():
                glossary[acronym.upper()] = info
            
            return glossary
        except Exception as e:
            logger.error(f"Errore caricamento glossario: {e}")
            return {}
    
    def _compile_patterns(self) -> Dict[EntityType, List[re.Pattern]]:
        """Compila tutti i pattern regex"""
        all_patterns = {
            **DOCUMENT_PATTERNS,
            **ROLE_PATTERNS,
            **STANDARD_PATTERNS,
            **EQUIPMENT_PATTERNS,
            **LOCATION_PATTERNS
        }
        
        compiled = {}
        for entity_type, patterns in all_patterns.items():
            compiled[entity_type] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
        
        return compiled
    
    def extract(
        self,
        text: str,
        chunk_id: str,
        include_glossary: bool = True
    ) -> List[Entity]:
        """
        Estrae entità da un chunk di testo
        
        Args:
            text: Testo del chunk
            chunk_id: ID del chunk (per tracking)
            include_glossary: Se True, cerca anche nel glossario
            
        Returns:
            Lista di Entity estratte
        """
        entities: List[Entity] = []
        seen_labels: Set[str] = set()  # Per deduplicazione intra-chunk
        
        # 1. Pattern-based extraction
        for entity_type, patterns in self.patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    label = match.group(1).strip()
                    label_upper = label.upper()
                    
                    # Skip duplicati
                    if label_upper in seen_labels:
                        continue
                    seen_labels.add(label_upper)
                    
                    # Crea o aggiorna entità
                    entity = self._get_or_create_entity(
                        label=label,
                        entity_type=entity_type,
                        chunk_id=chunk_id,
                        confidence=0.95  # Alta confidence per pattern match
                    )
                    entities.append(entity)
                    self.stats[f"pattern_{entity_type}"] += 1
        
        # 2. Glossary-based extraction
        if include_glossary and self.glossary:
            glossary_entities = self._extract_from_glossary(text, chunk_id, seen_labels)
            entities.extend(glossary_entities)
        
        # 3. Processi ISO (pattern specifici per sezioni)
        process_entities = self._extract_processes(text, chunk_id, seen_labels)
        entities.extend(process_entities)
        
        self.stats["total_extractions"] += len(entities)
        
        return entities
    
    def _extract_from_glossary(
        self,
        text: str,
        chunk_id: str,
        seen_labels: Set[str]
    ) -> List[Entity]:
        """Estrae entità matching con glossario"""
        entities = []
        text_upper = text.upper()
        
        for acronym, info in self.glossary.items():
            # Cerca l'acronimo come parola intera
            pattern = rf'\b{re.escape(acronym)}\b'
            if re.search(pattern, text_upper):
                if acronym not in seen_labels:
                    seen_labels.add(acronym)
                    
                    # Determina tipo basato su info glossario
                    entity_type = self._infer_type_from_glossary(acronym, info)
                    
                    # Descrizione dal glossario
                    description = ""
                    if isinstance(info, dict):
                        description = info.get("description", info.get("full", ""))
                    elif isinstance(info, str):
                        description = info
                    
                    entity = self._get_or_create_entity(
                        label=acronym,
                        entity_type=entity_type,
                        chunk_id=chunk_id,
                        confidence=0.90,
                        metadata={"description": description, "source": "glossary"}
                    )
                    entities.append(entity)
                    self.stats["glossary_matches"] += 1
        
        return entities
    
    def _infer_type_from_glossary(
        self,
        acronym: str,
        info: Any
    ) -> EntityType:
        """Inferisce il tipo di entità dal glossario"""
        # Check per ruoli noti
        role_keywords = ["responsabile", "addetto", "operatore", "auditor", "direttore"]
        
        description = ""
        if isinstance(info, dict):
            description = str(info.get("description", info.get("full", ""))).lower()
        elif isinstance(info, str):
            description = info.lower()
        
        # Pattern matching su descrizione
        if any(kw in description for kw in role_keywords):
            return "ROLE"
        
        if "iso" in description or "norma" in description:
            return "STANDARD"
        
        if "processo" in description or "procedura" in description:
            return "PROCESS"
        
        if "macchina" in description or "attrezzatura" in description:
            return "EQUIPMENT"
        
        # Default: CONCEPT (acronimo generico)
        return "CONCEPT"
    
    def _extract_processes(
        self,
        text: str,
        chunk_id: str,
        seen_labels: Set[str]
    ) -> List[Entity]:
        """Estrae nomi di processi ISO"""
        entities = []
        
        # Pattern per processi tipici ISO
        process_patterns = [
            r'(?:processo di|procedura di|gestione)\s+([\w\s]{3,30}?)(?:\.|,|\n|$)',
            r'(?:audit|riesame|valutazione)\s+(?:di|del|della)?\s*([\w\s]{3,20})',
        ]
        
        for pattern in process_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                label = match.group(1).strip()
                
                # Filtra label troppo generiche o troppo lunghe
                if len(label) < 5 or len(label) > 30:
                    continue
                if label.lower() in ["il", "la", "di", "che", "per", "con"]:
                    continue
                
                label_norm = label.title()
                if label_norm not in seen_labels:
                    seen_labels.add(label_norm)
                    
                    entity = self._get_or_create_entity(
                        label=label_norm,
                        entity_type="PROCESS",
                        chunk_id=chunk_id,
                        confidence=0.70  # Confidence più bassa per pattern generici
                    )
                    entities.append(entity)
                    self.stats["process_extractions"] += 1
        
        return entities
    
    def _get_or_create_entity(
        self,
        label: str,
        entity_type: EntityType,
        chunk_id: str,
        confidence: float = 1.0,
        metadata: Optional[Dict] = None
    ) -> Entity:
        """
        Ottiene entità dalla cache o ne crea una nuova
        Aggiorna source_chunks se già esistente
        """
        entity_id = Entity.create_id(label, entity_type)
        
        if entity_id in self.entity_cache:
            # Aggiorna chunk list
            entity = self.entity_cache[entity_id]
            if chunk_id not in entity.source_chunks:
                entity.source_chunks.append(chunk_id)
            # Aggiorna confidence (prendi il max)
            entity.confidence = max(entity.confidence, confidence)
            return entity
        
        # Crea nuova entità
        entity = Entity(
            id=entity_id,
            label=label,
            type=entity_type,
            source_chunks=[chunk_id],
            confidence=confidence,
            metadata=metadata or {}
        )
        
        self.entity_cache[entity_id] = entity
        return entity
    
    def extract_batch(
        self,
        chunks: List[Tuple[str, str]],  # [(text, chunk_id), ...]
        show_progress: bool = True
    ) -> List[Entity]:
        """
        Estrae entità da batch di chunk
        
        Args:
            chunks: Lista di tuple (testo, chunk_id)
            show_progress: Se mostrare progress bar
            
        Returns:
            Lista completa di entità (deduplicate)
        """
        from tqdm import tqdm
        
        iterator = tqdm(chunks, desc="Extracting entities") if show_progress else chunks
        
        for text, chunk_id in iterator:
            self.extract(text, chunk_id)
        
        # Ritorna tutte le entità dalla cache
        return list(self.entity_cache.values())
    
    def get_entities_by_type(
        self,
        entity_type: EntityType
    ) -> List[Entity]:
        """Filtra entità per tipo"""
        return [e for e in self.entity_cache.values() if e.type == entity_type]
    
    def get_stats(self) -> Dict[str, Any]:
        """Ritorna statistiche di estrazione"""
        entities_by_type = defaultdict(int)
        for entity in self.entity_cache.values():
            entities_by_type[entity.type] += 1
        
        return {
            "total_entities": len(self.entity_cache),
            "entities_by_type": dict(entities_by_type),
            "extraction_stats": dict(self.stats)
        }
    
    def clear_cache(self):
        """Pulisce la cache delle entità"""
        self.entity_cache.clear()
        self.stats.clear()
    
    def save_entities(self, path: str):
        """Salva entità estratte in JSON"""
        data = {
            "entities": [e.to_dict() for e in self.entity_cache.values()],
            "stats": self.get_stats()
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Salvate {len(self.entity_cache)} entità in {path}")
    
    def load_entities(self, path: str):
        """Carica entità da JSON"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        self.entity_cache.clear()
        for entity_data in data.get("entities", []):
            entity = Entity.from_dict(entity_data)
            self.entity_cache[entity.id] = entity
        
        logger.info(f"Caricate {len(self.entity_cache)} entità da {path}")

