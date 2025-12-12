"""
Memories Service Layer
Logica di business per gestione memorie - estratto da Streamlit
"""

from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class MemoriesService:
    """Service per gestione memorie utenti"""

    def __init__(self):
        self._memory_store = None

    def get_memories(self, namespace: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Ottiene memorie con filtri

        Args:
            namespace: Namespace specifico o None per tutti
            limit: Numero massimo risultati

        Returns:
            Lista memorie formattate
        """
        try:
            memory_store = self._get_memory_store()
            namespaces = (namespace,) if namespace else None
            memories = memory_store.get_all(namespace=namespaces, limit=limit)

            memory_list = []
            for mem in memories:
                memory_dict = {
                    "id": mem.id,
                    "content": mem.content,
                    "type": mem.type.value if hasattr(mem, 'type') else "unknown",
                    "namespace": getattr(mem, 'namespace', []),
                    "created_at": mem.created_at.isoformat() if hasattr(mem, 'created_at') else None,
                    "metadata": getattr(mem, 'metadata', {}),
                    "confidence": getattr(mem, 'confidence', 0.0)
                }
                memory_list.append(memory_dict)

            return memory_list

        except Exception as e:
            logger.error(f"Errore caricamento memorie: {e}")
            return []

    def promote_memory(self, memory_id: str, target_namespace: str) -> Dict[str, Any]:
        """
        Promuove memoria a namespace superiore

        Args:
            memory_id: ID memoria
            target_namespace: Namespace target (es. "global")

        Returns:
            Dict con risultato
        """
        try:
            memory_store = self._get_memory_store()

            # Trova memoria
            memories = memory_store.get_all(limit=1000)  # Ricerca ampia
            memory = next((m for m in memories if m.id == memory_id), None)

            if not memory:
                return {"success": False, "error": "Memoria non trovata"}

            # Copia nel nuovo namespace
            memory_store.add(
                content=memory.content,
                type=memory.type,
                metadata=dict(memory.metadata) if hasattr(memory, 'metadata') else {},
                namespace=(target_namespace,)
            )

            logger.info(f"Memoria {memory_id} promossa a {target_namespace}")
            return {"success": True, "message": f"Memoria promossa a {target_namespace}"}

        except Exception as e:
            logger.error(f"Errore promozione memoria {memory_id}: {e}")
            return {"success": False, "error": str(e)}

    def delete_memory(self, memory_id: str, namespace: str = None) -> Dict[str, Any]:
        """
        Elimina memoria

        Args:
            memory_id: ID memoria
            namespace: Namespace specifico

        Returns:
            Dict con risultato
        """
        try:
            memory_store = self._get_memory_store()
            namespaces = (namespace,) if namespace else None

            memory_store.delete(memory_id, namespace=namespaces)

            logger.info(f"Memoria {memory_id} eliminata")
            return {"success": True, "message": "Memoria eliminata"}

        except Exception as e:
            logger.error(f"Errore eliminazione memoria {memory_id}: {e}")
            return {"success": False, "error": str(e)}

    def _get_memory_store(self):
        """Lazy load memory store"""
        if self._memory_store is None:
            from src.memory.store import MemoryStore
            self._memory_store = MemoryStore()
        return self._memory_store


# Singleton instance
_memories_service = None

def get_memories_service() -> MemoriesService:
    """Ottiene istanza singleton del MemoriesService"""
    global _memories_service
    if _memories_service is None:
        _memories_service = MemoriesService()
    return _memories_service
