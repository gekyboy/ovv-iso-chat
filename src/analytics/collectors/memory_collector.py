"""
Memory Collector per R07 Analytics
Statistiche sul sistema di memoria utente

R07 - Sistema Analytics
Created: 2025-12-08

Metriche raccolte:
- Distribuzione memorie per namespace e tipo
- Boost factor medio e distribuzione
- Proposte pending e approvate/rifiutate
- Top memorie (più usate/valorizzate)
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class MemoryCollector:
    """
    Collector per statistiche sistema memoria.
    
    Features:
    - Legge direttamente dal MemoryStore
    - Aggregazioni per namespace e tipo
    - Analisi boost factor (Bayesian feedback)
    - Tracking proposte pending_global
    
    Example:
        >>> collector = MemoryCollector()
        >>> stats = collector.get_stats()
        >>> print(f"Totale memorie: {stats['total_memories']}")
    """
    
    def __init__(self, memory_store=None):
        """
        Inizializza collector.
        
        Args:
            memory_store: Istanza MemoryStore (o lazy load)
        """
        self._memory_store = memory_store
        logger.info("MemoryCollector inizializzato")
    
    def _get_store(self):
        """Lazy load del MemoryStore"""
        if self._memory_store is None:
            try:
                from src.memory.store import get_memory_store
                self._memory_store = get_memory_store()
            except ImportError:
                logger.warning("MemoryStore non disponibile")
                return None
        return self._memory_store
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Statistiche complete sistema memoria.
        
        Returns:
            Dict con metriche aggregate
        """
        store = self._get_store()
        if not store:
            return self._empty_stats()
        
        try:
            # Ottieni tutte le memorie
            all_memories = store.get_all()
            
            if not all_memories:
                return self._empty_stats()
            
            # Conteggi per namespace
            by_namespace: Dict[str, int] = {}
            by_type: Dict[str, int] = {}
            boost_factors: List[float] = []
            
            for mem in all_memories:
                ns = getattr(mem, 'namespace', 'unknown')
                mem_type = getattr(mem, 'memory_type', getattr(mem, 'type', 'unknown'))
                boost = getattr(mem, 'boost_factor', 1.0)
                
                by_namespace[ns] = by_namespace.get(ns, 0) + 1
                
                # Normalizza tipo
                if isinstance(mem_type, str):
                    type_str = mem_type
                else:
                    type_str = getattr(mem_type, 'value', str(mem_type))
                by_type[type_str] = by_type.get(type_str, 0) + 1
                
                boost_factors.append(boost)
            
            # Calcola statistiche boost
            avg_boost = sum(boost_factors) / len(boost_factors) if boost_factors else 1.0
            max_boost = max(boost_factors) if boost_factors else 1.0
            min_boost = min(boost_factors) if boost_factors else 1.0
            
            # Top boosted (memorie più valorizzate)
            memories_with_boost = [
                (mem, getattr(mem, 'boost_factor', 1.0))
                for mem in all_memories
            ]
            memories_with_boost.sort(key=lambda x: x[1], reverse=True)
            
            top_boosted = [
                {
                    "content": getattr(m, 'content', str(m))[:80],
                    "boost": round(b, 3),
                    "namespace": getattr(m, 'namespace', 'unknown')
                }
                for m, b in memories_with_boost[:5]
                if b > 1.0
            ]
            
            # Low boosted (memorie penalizzate)
            low_boosted = [
                {
                    "content": getattr(m, 'content', str(m))[:80],
                    "boost": round(b, 3),
                    "namespace": getattr(m, 'namespace', 'unknown')
                }
                for m, b in reversed(memories_with_boost[-5:])
                if b < 1.0
            ]
            
            # Pending proposals
            pending_count = by_namespace.get('pending_global', 0)
            
            # Conta utenti con memorie personali
            user_namespaces = [ns for ns in by_namespace.keys() if ns.startswith('user_')]
            
            return {
                "total_memories": len(all_memories),
                "by_namespace": by_namespace,
                "by_type": by_type,
                "user_count": len(user_namespaces),
                "global_count": by_namespace.get('global', 0),
                "pending_count": pending_count,
                "boost_stats": {
                    "avg": round(avg_boost, 3),
                    "max": round(max_boost, 3),
                    "min": round(min_boost, 3)
                },
                "top_boosted": top_boosted,
                "low_boosted": low_boosted
            }
            
        except Exception as e:
            logger.error(f"Errore raccolta stats memoria: {e}")
            return self._empty_stats()
    
    def _empty_stats(self) -> Dict[str, Any]:
        """Statistiche vuote"""
        return {
            "total_memories": 0,
            "by_namespace": {},
            "by_type": {},
            "user_count": 0,
            "global_count": 0,
            "pending_count": 0,
            "boost_stats": {"avg": 1.0, "max": 1.0, "min": 1.0},
            "top_boosted": [],
            "low_boosted": []
        }
    
    def get_namespace_stats(self, namespace: str) -> Dict[str, Any]:
        """
        Statistiche per singolo namespace.
        
        Args:
            namespace: Nome namespace (es. "user_mario", "global")
            
        Returns:
            Dict con statistiche namespace
        """
        store = self._get_store()
        if not store:
            return {"error": "Store non disponibile"}
        
        try:
            memories = store.get_by_namespace(namespace)
            
            if not memories:
                return {
                    "namespace": namespace,
                    "count": 0,
                    "by_type": {},
                    "avg_boost": 1.0
                }
            
            by_type: Dict[str, int] = {}
            boost_sum = 0.0
            
            for mem in memories:
                mem_type = getattr(mem, 'memory_type', getattr(mem, 'type', 'unknown'))
                if isinstance(mem_type, str):
                    type_str = mem_type
                else:
                    type_str = getattr(mem_type, 'value', str(mem_type))
                
                by_type[type_str] = by_type.get(type_str, 0) + 1
                boost_sum += getattr(mem, 'boost_factor', 1.0)
            
            return {
                "namespace": namespace,
                "count": len(memories),
                "by_type": by_type,
                "avg_boost": round(boost_sum / len(memories), 3)
            }
            
        except Exception as e:
            logger.error(f"Errore stats namespace {namespace}: {e}")
            return {"error": str(e)}
    
    def get_pending_proposals(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Ottiene proposte pending per Admin.
        
        Args:
            limit: Massimo risultati
            
        Returns:
            Lista proposte con dettagli
        """
        store = self._get_store()
        if not store:
            return []
        
        try:
            pending = store.get_by_namespace('pending_global')
            
            if not pending:
                return []
            
            # Ordina per timestamp (più recenti prima)
            pending_list = []
            for mem in pending:
                pending_list.append({
                    "id": getattr(mem, 'id', ''),
                    "content": getattr(mem, 'content', ''),
                    "type": str(getattr(mem, 'memory_type', getattr(mem, 'type', ''))),
                    "proposed_by": getattr(mem, 'user_id', getattr(mem, 'proposed_by', '')),
                    "timestamp": getattr(mem, 'timestamp', getattr(mem, 'created_at', ''))
                })
            
            # Ordina per timestamp desc
            pending_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return pending_list[:limit]
            
        except Exception as e:
            logger.error(f"Errore proposte pending: {e}")
            return []
    
    def get_feedback_distribution(self) -> Dict[str, int]:
        """
        Distribuzione feedback (basata su boost factor).
        
        Boost > 1.0 indica feedback positivi prevalenti
        Boost < 1.0 indica feedback negativi prevalenti
        
        Returns:
            Dict con conteggi
        """
        store = self._get_store()
        if not store:
            return {"positive": 0, "negative": 0, "neutral": 0}
        
        try:
            all_memories = store.get_all()
            
            positive = 0
            negative = 0
            neutral = 0
            
            for mem in all_memories:
                boost = getattr(mem, 'boost_factor', 1.0)
                
                if boost > 1.02:  # Soglia positivo
                    positive += 1
                elif boost < 0.98:  # Soglia negativo
                    negative += 1
                else:
                    neutral += 1
            
            return {
                "positive": positive,
                "negative": negative,
                "neutral": neutral
            }
            
        except Exception as e:
            logger.error(f"Errore distribuzione feedback: {e}")
            return {"positive": 0, "negative": 0, "neutral": 0}


# Singleton
_collector: Optional[MemoryCollector] = None


def get_memory_collector() -> MemoryCollector:
    """Ottiene istanza singleton MemoryCollector"""
    global _collector
    if _collector is None:
        _collector = MemoryCollector()
    return _collector


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("=== TEST MEMORY COLLECTOR ===\n")
    
    # Mock MemoryStore per test
    class MockMemory:
        def __init__(self, ns, mtype, content, boost=1.0):
            self.namespace = ns
            self.memory_type = mtype
            self.content = content
            self.boost_factor = boost
            self.id = f"mem_{hash(content)}"
    
    class MockStore:
        def __init__(self):
            self.memories = [
                MockMemory("global", "fact", "WCM significa World Class Manufacturing", 1.15),
                MockMemory("global", "fact", "NC = Non Conformità", 1.08),
                MockMemory("user_mario", "preference", "Preferisco risposte brevi", 1.05),
                MockMemory("user_mario", "fact", "Quick Kaizen dura 5 giorni", 0.95),
                MockMemory("user_luigi", "preference", "Mi piacciono gli elenchi", 1.0),
                MockMemory("pending_global", "fact", "FMEA sta per Failure Mode...", 1.0),
            ]
        
        def get_all(self):
            return self.memories
        
        def get_by_namespace(self, ns):
            return [m for m in self.memories if m.namespace == ns]
    
    collector = MemoryCollector(memory_store=MockStore())
    
    # Test 1: Get stats
    print("Test 1: Get stats")
    stats = collector.get_stats()
    print(f"  Total: {stats['total_memories']}")
    print(f"  By namespace: {stats['by_namespace']}")
    print(f"  By type: {stats['by_type']}")
    print(f"  Boost avg: {stats['boost_stats']['avg']}")
    print(f"  Top boosted: {len(stats['top_boosted'])}")
    print()
    
    # Test 2: Namespace stats
    print("Test 2: Namespace stats")
    mario_stats = collector.get_namespace_stats("user_mario")
    print(f"  user_mario: {mario_stats['count']} memorie")
    print(f"  Types: {mario_stats['by_type']}")
    print()
    
    # Test 3: Pending proposals
    print("Test 3: Pending proposals")
    pending = collector.get_pending_proposals()
    print(f"  Pending: {len(pending)}")
    for p in pending:
        print(f"    - {p['content'][:40]}...")
    print()
    
    # Test 4: Feedback distribution
    print("Test 4: Feedback distribution")
    feedback = collector.get_feedback_distribution()
    print(f"  Positive: {feedback['positive']}")
    print(f"  Negative: {feedback['negative']}")
    print(f"  Neutral: {feedback['neutral']}")
    
    print("\n✅ Test completati!")

