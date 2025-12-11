"""
Memory Store per OVV ISO Chat v3.1
Gestione memoria persistente con Bayesian feedback boost

Supporta:
- JSON-based storage (default)
- PostgreSQL/pgvector (opzionale, quando disponibile)
- Namespace-based organization
- Feedback tracking con Bayesian boost (0.8x - 1.2x)
"""

import json
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple

import yaml

logger = logging.getLogger(__name__)


class MemoryType(str, Enum):
    """Tipi di memoria supportati"""
    PREFERENCE = "preference"      # Preferenze utente
    FACT = "fact"                  # Fatti appresi
    CORRECTION = "correction"      # Correzioni ricevute
    PROCEDURE = "procedure"        # Procedure specifiche
    CONTEXT = "context"            # Contesto conversazione


@dataclass
class FeedbackRecord:
    """Record di feedback singolo"""
    timestamp: str
    is_positive: bool
    context: str = ""
    user_note: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "is_positive": self.is_positive,
            "context": self.context,
            "user_note": self.user_note
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "FeedbackRecord":
        return cls(**data)


@dataclass
class MemoryItem:
    """Singolo item di memoria con Bayesian feedback"""
    id: str
    type: MemoryType
    content: str
    source: str  # user_feedback, explicit_add, llm_extraction
    
    # Confidence & Boost
    base_confidence: float = 0.7
    boost_factor: float = 1.0  # 0.8 - 1.2 range
    
    # Timestamps
    created_at: str = ""
    updated_at: str = ""
    
    # Usage tracking
    access_count: int = 0
    
    # Feedback history per Bayesian
    feedback_history: List[FeedbackRecord] = field(default_factory=list)
    
    # Relationships
    related_docs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
    
    @property
    def effective_confidence(self) -> float:
        """Confidenza effettiva con boost applicato"""
        return min(1.0, self.base_confidence * self.boost_factor)
    
    @property
    def positive_ratio(self) -> float:
        """Ratio feedback positivi"""
        if not self.feedback_history:
            return 0.5
        positive = sum(1 for f in self.feedback_history if f.is_positive)
        return positive / len(self.feedback_history)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte in dizionario per persistenza"""
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "source": self.source,
            "base_confidence": self.base_confidence,
            "boost_factor": self.boost_factor,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "access_count": self.access_count,
            "feedback_history": [f.to_dict() for f in self.feedback_history],
            "related_docs": self.related_docs,
            "metadata": self.metadata,
            # Computed fields
            "effective_confidence": self.effective_confidence,
            "positive_ratio": self.positive_ratio
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        """Crea da dizionario"""
        feedback_history = [
            FeedbackRecord.from_dict(f) 
            for f in data.get("feedback_history", [])
        ]
        return cls(
            id=data["id"],
            type=MemoryType(data["type"]),
            content=data["content"],
            source=data.get("source", "loaded"),
            base_confidence=data.get("base_confidence", 0.7),
            boost_factor=data.get("boost_factor", 1.0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            access_count=data.get("access_count", 0),
            feedback_history=feedback_history,
            related_docs=data.get("related_docs", []),
            metadata=data.get("metadata", {})
        )
    
    def update_access(self):
        """Aggiorna contatore accessi"""
        self.access_count += 1
        self.updated_at = datetime.now().isoformat()


class BayesianBooster:
    """
    Calcola Bayesian boost factor dal feedback
    
    Formula: boost = 1.0 + (positive_ratio - 0.5) * 0.4 * confidence
    Range: 0.8x to 1.2x
    """
    
    def __init__(self, config: Optional[Dict] = None):
        config = config or {}
        feedback_cfg = config.get("memory", {}).get("feedback", {})
        
        self.MIN_BOOST = feedback_cfg.get("min_boost", 0.8)
        self.MAX_BOOST = feedback_cfg.get("max_boost", 1.2)
        self.CONFIDENCE_THRESHOLD = feedback_cfg.get("confidence_threshold", 10)
        self.DEMOTE_THRESHOLD = feedback_cfg.get("demote_threshold", 0.2)
    
    def calculate_boost(self, feedback_history: List[FeedbackRecord]) -> float:
        """Calcola boost factor dal feedback"""
        if not feedback_history:
            return 1.0
        
        positive = sum(1 for f in feedback_history if f.is_positive)
        total = len(feedback_history)
        positive_ratio = positive / total
        
        # Confidence basata su numero feedback
        confidence = min(total / self.CONFIDENCE_THRESHOLD, 1.0)
        
        # Boost: neutro a ratio 0.5
        boost = 1.0 + (positive_ratio - 0.5) * 0.4 * confidence
        
        return max(self.MIN_BOOST, min(self.MAX_BOOST, boost))
    
    def should_demote(self, item: MemoryItem) -> bool:
        """Verifica se demotare item con feedback molto negativo"""
        if len(item.feedback_history) < 5:
            return False
        return item.positive_ratio < self.DEMOTE_THRESHOLD


class MemoryStore:
    """
    Store per memoria a lungo termine
    
    Supporta:
    - JSON persistence (default)
    - Namespace organization (user_id:memory_type)
    - Bayesian feedback boost
    """
    
    def __init__(self, config: Optional[Dict] = None, config_path: Optional[str] = None):
        """
        Inizializza lo store
        
        Args:
            config: Dizionario configurazione (prioritario)
            config_path: Percorso al file config.yaml (fallback)
        """
        if config:
            self.config = config
        else:
            self.config = self._load_config(config_path)
        
        memory_config = self.config.get("memory", {})
        self.default_namespace = memory_config.get("namespace", "ovv_user_v31")
        self.max_memories = memory_config.get("max_memories", 200)
        
        # Percorso persistenza
        persist_dir = self.config.get("paths", {}).get("persist_dir", "data/persist")
        self.persist_path = Path(persist_dir) / "memory_store_v31.json"
        
        # Storage in-memory
        self._store: Dict[str, Dict[str, MemoryItem]] = {}
        
        # Bayesian booster
        self.booster = BayesianBooster(self.config)
        
        # Carica dati persistenti
        self._load_from_disk()
        
        logger.info(f"MemoryStore inizializzato: namespace={self.default_namespace}")
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Carica configurazione"""
        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    def _load_from_disk(self):
        """Carica dati da file JSON"""
        if self.persist_path.exists():
            try:
                with open(self.persist_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for namespace, items in data.items():
                    self._store[namespace] = {}
                    for key, item_data in items.items():
                        self._store[namespace][key] = MemoryItem.from_dict(item_data)
                
                total = sum(len(items) for items in self._store.values())
                logger.info(f"Caricate {total} memorie da {self.persist_path}")
                
            except Exception as e:
                logger.error(f"Errore caricamento memoria: {e}")
    
    def _save_to_disk(self):
        """Salva dati su file JSON"""
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {}
            for namespace, items in self._store.items():
                data[namespace] = {
                    key: item.to_dict() for key, item in items.items()
                }
            
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Memoria salvata su {self.persist_path}")
            
        except Exception as e:
            logger.error(f"Errore salvataggio memoria: {e}")
    
    def _generate_id(self, content: str, mem_type: MemoryType) -> str:
        """Genera ID univoco per memoria"""
        hash_input = f"{mem_type.value}:{content[:100]}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:12]
        return f"{mem_type.value}_{hash_value}"
    
    def _get_namespace_key(self, namespace: Optional[Tuple[str, ...]] = None) -> str:
        """Converte namespace tuple in stringa"""
        if namespace is None:
            return self.default_namespace
        return ":".join(namespace)
    
    def put(
        self,
        content: str,
        mem_type: MemoryType,
        namespace: Optional[Tuple[str, ...]] = None,
        source: str = "explicit_add",
        confidence: float = 0.7,
        related_docs: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MemoryItem:
        """
        Salva una nuova memoria (NO overwrite, aggiorna se esiste)
        
        Args:
            content: Contenuto della memoria
            mem_type: Tipo di memoria
            namespace: Namespace (opzionale)
            source: Sorgente della memoria
            confidence: Livello di confidenza base
            related_docs: Documenti correlati
            metadata: Metadata aggiuntivi
            
        Returns:
            MemoryItem creato/aggiornato
        """
        ns_key = self._get_namespace_key(namespace)
        
        if ns_key not in self._store:
            self._store[ns_key] = {}
        
        # Genera ID basato su contenuto (dedup)
        mem_id = self._generate_id(content, mem_type)
        
        # Se esiste, AGGIORNA (no overwrite)
        if mem_id in self._store[ns_key]:
            existing = self._store[ns_key][mem_id]
            existing.base_confidence = max(existing.base_confidence, confidence)
            existing.updated_at = datetime.now().isoformat()
            existing.access_count += 1
            if related_docs:
                existing.related_docs = list(set(existing.related_docs + related_docs))
            self._save_to_disk()
            logger.debug(f"Memoria aggiornata (no overwrite): {mem_id}")
            return existing
        
        # Crea nuova memoria
        memory = MemoryItem(
            id=mem_id,
            type=mem_type,
            content=content,
            source=source,
            base_confidence=confidence,
            related_docs=related_docs or [],
            metadata=metadata or {}
        )
        
        # Verifica limite memorie
        if len(self._store[ns_key]) >= self.max_memories:
            self._evict_least_used(ns_key)
        
        self._store[ns_key][mem_id] = memory
        self._save_to_disk()
        
        logger.info(f"Memoria creata: {mem_id} ({mem_type.value})")
        return memory
    
    def _evict_least_used(self, namespace: str):
        """Rimuove la memoria meno usata/boosted"""
        if not self._store.get(namespace):
            return
        
        items = list(self._store[namespace].items())
        # Ordina per effective_confidence * access
        items.sort(key=lambda x: x[1].effective_confidence * (1 + x[1].access_count * 0.01))
        
        if items:
            to_remove = items[0][0]
            del self._store[namespace][to_remove]
            logger.debug(f"Evicted memoria: {to_remove}")
    
    def get(
        self,
        mem_id: str,
        namespace: Optional[Tuple[str, ...]] = None
    ) -> Optional[MemoryItem]:
        """Recupera una memoria per ID"""
        ns_key = self._get_namespace_key(namespace)
        
        if ns_key not in self._store:
            return None
        
        memory = self._store[ns_key].get(mem_id)
        if memory:
            memory.update_access()
            self._save_to_disk()
        
        return memory
    
    def search(
        self,
        query: str,
        namespace: Optional[Tuple[str, ...]] = None,
        mem_type: Optional[MemoryType] = None,
        limit: int = 5,
        min_confidence: float = 0.3
    ) -> List[MemoryItem]:
        """Cerca memorie per contenuto"""
        ns_key = self._get_namespace_key(namespace)
        
        if ns_key not in self._store:
            return []
        
        query_lower = query.lower()
        results = []
        
        for memory in self._store[ns_key].values():
            # Filtra per tipo
            if mem_type and memory.type != mem_type:
                continue
            
            # Filtra per confidence
            if memory.effective_confidence < min_confidence:
                continue
            
            # Match su contenuto
            if query_lower in memory.content.lower():
                results.append(memory)
        
        # Ordina per effective_confidence
        results.sort(key=lambda x: x.effective_confidence, reverse=True)
        
        return results[:limit]
    
    def add_feedback(
        self,
        mem_id: str,
        is_positive: bool,
        context: str = "",
        namespace: Optional[Tuple[str, ...]] = None
    ) -> Optional[MemoryItem]:
        """
        Aggiunge feedback e ricalcola boost
        
        Args:
            mem_id: ID memoria
            is_positive: True = 👍, False = 👎
            context: Contesto del feedback
            namespace: Namespace
            
        Returns:
            MemoryItem aggiornato o None
        """
        memory = self.get(mem_id, namespace)
        if not memory:
            logger.warning(f"Memoria non trovata per feedback: {mem_id}")
            return None
        
        # Aggiungi feedback
        feedback = FeedbackRecord(
            timestamp=datetime.now().isoformat(),
            is_positive=is_positive,
            context=context
        )
        memory.feedback_history.append(feedback)
        
        # Ricalcola boost
        memory.boost_factor = self.booster.calculate_boost(memory.feedback_history)
        memory.updated_at = datetime.now().isoformat()
        
        # Check demotion
        if self.booster.should_demote(memory):
            memory.base_confidence *= 0.5
            logger.info(f"Memoria demotata per feedback negativo: {mem_id}")
        
        self._save_to_disk()
        
        emoji = "👍" if is_positive else "👎"
        logger.info(f"Feedback {emoji} su {mem_id}: boost={memory.boost_factor:.2f}")
        
        return memory
    
    def get_all(
        self,
        namespace: Optional[Tuple[str, ...]] = None,
        mem_type: Optional[MemoryType] = None
    ) -> List[MemoryItem]:
        """Recupera tutte le memorie"""
        ns_key = self._get_namespace_key(namespace)
        
        if ns_key not in self._store:
            return []
        
        memories = list(self._store[ns_key].values())
        
        if mem_type:
            memories = [m for m in memories if m.type == mem_type]
        
        return memories
    
    def delete(
        self,
        mem_id: str,
        namespace: Optional[Tuple[str, ...]] = None
    ) -> bool:
        """Elimina una memoria"""
        ns_key = self._get_namespace_key(namespace)
        
        if ns_key not in self._store:
            return False
        
        if mem_id in self._store[ns_key]:
            del self._store[ns_key][mem_id]
            self._save_to_disk()
            logger.info(f"Memoria eliminata: {mem_id}")
            return True
        
        return False
    
    def clear(self, namespace: Optional[Tuple[str, ...]] = None):
        """Elimina tutte le memorie in un namespace"""
        ns_key = self._get_namespace_key(namespace)
        
        if ns_key in self._store:
            count = len(self._store[ns_key])
            self._store[ns_key] = {}
            self._save_to_disk()
            logger.info(f"Eliminate {count} memorie da {ns_key}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistiche dello store"""
        total = 0
        by_type: Dict[str, int] = {}
        by_namespace: Dict[str, int] = {}
        boosts = []
        
        for ns_key, items in self._store.items():
            total += len(items)
            by_namespace[ns_key] = len(items)
            
            for item in items.values():
                type_name = item.type.value
                by_type[type_name] = by_type.get(type_name, 0) + 1
                boosts.append(item.boost_factor)
        
        return {
            "total_memories": total,
            "by_type": by_type,
            "by_namespace": by_namespace,
            "average_boost": sum(boosts) / len(boosts) if boosts else 1.0
        }
    
    # === METODI MULTI-UTENTE (v3.2) ===
    
    def get_accessible_namespaces(self, user_role: str, user_id: str) -> List[str]:
        """
        Ritorna namespace accessibili per ruolo.
        
        Args:
            user_role: "admin", "engineer", "user"
            user_id: ID utente
            
        Returns:
            Lista di namespace accessibili
        """
        namespaces = ["global"]  # Tutti leggono global
        
        if user_role in ["admin", "engineer"]:
            # Admin/Engineer vedono tutti i namespace
            namespaces.extend(self._get_all_user_namespaces())
        else:
            # User vede solo proprio namespace
            namespaces.append(f"user_{user_id}")
        
        return list(set(namespaces))
    
    def _get_all_user_namespaces(self) -> List[str]:
        """Ritorna tutti i namespace utente esistenti"""
        return [ns for ns in self._store.keys() if ns.startswith("user_")]
    
    def search_multi_namespace(
        self,
        query: str,
        user_role: str,
        user_id: str,
        mem_type: Optional[MemoryType] = None,
        limit: int = 10,
        min_confidence: float = 0.3
    ) -> List[MemoryItem]:
        """
        Cerca in tutti i namespace accessibili per l'utente.
        
        Args:
            query: Query di ricerca
            user_role: Ruolo utente
            user_id: ID utente
            mem_type: Filtro tipo memoria
            limit: Max risultati
            min_confidence: Confidence minima
            
        Returns:
            Lista MemoryItem ordinata per effective_confidence
        """
        namespaces = self.get_accessible_namespaces(user_role, user_id)
        results = []
        
        for ns in namespaces:
            ns_results = self.search(
                query=query,
                namespace=(ns,),
                mem_type=mem_type,
                limit=limit,
                min_confidence=min_confidence
            )
            results.extend(ns_results)
        
        # Ordina per effective_confidence
        results.sort(key=lambda x: x.effective_confidence, reverse=True)
        return results[:limit]
    
    def record_response_feedback(
        self,
        query: str,
        sources: List[str],
        is_positive: bool,
        namespace: str
    ):
        """
        Registra feedback su risposta RAG.
        Aggiorna boost delle memorie correlate ai documenti fonte.
        
        Args:
            query: Query originale
            sources: Lista doc_id delle fonti
            is_positive: True = positivo, False = negativo
            namespace: Namespace corrente
        """
        for source_id in sources:
            try:
                related_memories = self.search(
                    query=source_id,
                    namespace=(namespace,) if namespace else None,
                    limit=5
                )
                
                for mem in related_memories:
                    self.add_feedback(
                        mem_id=mem.id,
                        is_positive=is_positive,
                        context=f"Response feedback for query: {query[:100]}",
                        namespace=(namespace,) if namespace else None
                    )
                    
            except Exception as e:
                logger.debug(f"Skip feedback per {source_id}: {e}")
    
    def format_for_prompt(
        self,
        namespace: Optional[Tuple[str, ...]] = None,
        max_items: int = 5
    ) -> str:
        """Formatta memorie per inserimento nel prompt LLM"""
        memories = self.get_all(namespace)
        
        if not memories:
            return ""
        
        # Ordina per effective_confidence
        memories.sort(key=lambda x: x.effective_confidence, reverse=True)
        
        sections = {
            MemoryType.PREFERENCE: ("📌 PREFERENZE UTENTE:", []),
            MemoryType.CORRECTION: ("⚠️ CORREZIONI:", []),
            MemoryType.FACT: ("💡 FATTI:", []),
            MemoryType.PROCEDURE: ("📋 PROCEDURE:", [])
        }
        
        for memory in memories[:max_items * 2]:
            if memory.type in sections:
                conf_pct = f"{memory.effective_confidence:.0%}"
                sections[memory.type][1].append(
                    f"  - {memory.content} (conf: {conf_pct})"
                )
        
        formatted_parts = []
        for mem_type, (header, items) in sections.items():
            if items:
                formatted_parts.append(header)
                formatted_parts.extend(items[:max_items])
        
        return "\n".join(formatted_parts) if formatted_parts else ""


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    store = MemoryStore(config_path="config/config.yaml")
    
    # Test put (no overwrite)
    m1 = store.put(
        content="Preferisco Quick Kaizen per problemi semplici",
        mem_type=MemoryType.PREFERENCE,
        source="test"
    )
    print(f"Creato: {m1.id}")
    
    # Test duplicate (should update, not overwrite)
    m2 = store.put(
        content="Preferisco Quick Kaizen per problemi semplici",
        mem_type=MemoryType.PREFERENCE,
        source="test"
    )
    print(f"Aggiornato: {m2.id} (access_count={m2.access_count})")
    
    # Test feedback
    store.add_feedback(m1.id, is_positive=True, context="Test feedback")
    
    # Stats
    print(f"\nStats: {store.get_stats()}")
    print(f"\nFormattato:\n{store.format_for_prompt()}")

