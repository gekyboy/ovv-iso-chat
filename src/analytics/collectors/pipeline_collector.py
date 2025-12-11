"""
Pipeline Collector per R07 Analytics
Metriche di performance della pipeline RAG

R07 - Sistema Analytics
Created: 2025-12-08

Metriche raccolte:
- Stato e statistiche collezione Qdrant
- Breakdown latenza per componente
- VRAM usage
- Hit rate e qualità retrieval
"""

import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class PipelineCollector:
    """
    Collector per metriche pipeline RAG.
    
    Features:
    - Query statistiche Qdrant
    - Breakdown latenza per componente
    - Monitoraggio VRAM (nvidia-smi)
    - Cache statistiche (se implementato)
    
    Example:
        >>> collector = PipelineCollector()
        >>> stats = collector.get_stats()
        >>> print(f"Chunks: {stats['total_chunks']}")
    """
    
    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = "iso_sgi_docs_v31"
    ):
        """
        Inizializza collector.
        
        Args:
            qdrant_host: Host Qdrant
            qdrant_port: Porta Qdrant
            collection_name: Nome collezione
        """
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.collection_name = collection_name
        
        self._qdrant_client = None
        
        logger.info(f"PipelineCollector: {collection_name}@{qdrant_host}:{qdrant_port}")
    
    def _get_qdrant_client(self):
        """Lazy load Qdrant client"""
        if self._qdrant_client is None:
            try:
                from qdrant_client import QdrantClient
                self._qdrant_client = QdrantClient(
                    host=self.qdrant_host,
                    port=self.qdrant_port
                )
            except ImportError:
                logger.warning("qdrant_client non installato")
                return None
            except Exception as e:
                logger.error(f"Errore connessione Qdrant: {e}")
                return None
        return self._qdrant_client
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Statistiche complete pipeline.
        
        Returns:
            Dict con metriche
        """
        stats = {
            "timestamp": datetime.now().isoformat(),
            "collection_name": self.collection_name,
            "collection_status": "unknown",
            "total_chunks": 0,
            "chunks_by_doc_type": {},
            "vram_usage_mb": 0,
            "vram_total_mb": 0,
            "qdrant_connected": False
        }
        
        # Qdrant stats
        qdrant_stats = self._get_qdrant_stats()
        stats.update(qdrant_stats)
        
        # VRAM stats
        vram_stats = self._get_vram_stats()
        stats.update(vram_stats)
        
        return stats
    
    def _get_qdrant_stats(self) -> Dict[str, Any]:
        """Ottiene statistiche da Qdrant"""
        client = self._get_qdrant_client()
        
        if not client:
            return {
                "qdrant_connected": False,
                "collection_status": "not_connected",
                "total_chunks": 0,
                "chunks_by_doc_type": {}
            }
        
        try:
            # Collection info
            collection_info = client.get_collection(self.collection_name)
            
            total_points = collection_info.points_count
            status = collection_info.status.value if hasattr(collection_info.status, 'value') else str(collection_info.status)
            
            # Conta per doc_type (sampling)
            chunks_by_type = self._count_by_doc_type(client)
            
            return {
                "qdrant_connected": True,
                "collection_status": status,
                "total_chunks": total_points,
                "chunks_by_doc_type": chunks_by_type,
                "vectors_count": total_points,
                "indexed_vectors": getattr(collection_info, 'indexed_vectors_count', total_points)
            }
            
        except Exception as e:
            logger.error(f"Errore query Qdrant: {e}")
            return {
                "qdrant_connected": False,
                "collection_status": f"error: {str(e)[:50]}",
                "total_chunks": 0,
                "chunks_by_doc_type": {}
            }
    
    def _count_by_doc_type(self, client, sample_size: int = 500) -> Dict[str, int]:
        """
        Conta chunks per doc_type (sampling).
        
        Args:
            client: QdrantClient
            sample_size: Dimensione sample
            
        Returns:
            Dict {doc_type: count}
        """
        try:
            # Scroll alcuni punti per conteggio
            result = client.scroll(
                collection_name=self.collection_name,
                limit=sample_size,
                with_payload=["doc_type"]
            )
            
            points = result[0]
            
            counts: Dict[str, int] = {}
            for point in points:
                doc_type = point.payload.get("doc_type", "unknown")
                counts[doc_type] = counts.get(doc_type, 0) + 1
            
            # Se abbiamo sample completo, stima totale
            if len(points) < sample_size:
                # Sample completo, conteggi esatti
                return counts
            else:
                # Stima basata su proporzioni
                # (Non precisissimo ma utile per overview)
                return counts
                
        except Exception as e:
            logger.debug(f"Errore conteggio doc_type: {e}")
            return {}
    
    def _get_vram_stats(self) -> Dict[str, Any]:
        """Ottiene statistiche VRAM da nvidia-smi"""
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                line = result.stdout.strip().split('\n')[0]
                used, total = map(int, line.split(','))
                
                return {
                    "vram_usage_mb": used,
                    "vram_total_mb": total,
                    "vram_usage_pct": round(used / total * 100, 1) if total > 0 else 0
                }
                
        except FileNotFoundError:
            logger.debug("nvidia-smi non trovato")
        except subprocess.TimeoutExpired:
            logger.debug("nvidia-smi timeout")
        except Exception as e:
            logger.debug(f"Errore nvidia-smi: {e}")
        
        return {
            "vram_usage_mb": 0,
            "vram_total_mb": 0,
            "vram_usage_pct": 0
        }
    
    def get_collection_health(self) -> Dict[str, Any]:
        """
        Health check collezione.
        
        Returns:
            Dict con stato salute
        """
        client = self._get_qdrant_client()
        
        health = {
            "healthy": False,
            "status": "unknown",
            "issues": []
        }
        
        if not client:
            health["issues"].append("Qdrant non connesso")
            return health
        
        try:
            info = client.get_collection(self.collection_name)
            
            status = info.status.value if hasattr(info.status, 'value') else str(info.status)
            
            health["status"] = status
            
            if status.lower() == "green":
                health["healthy"] = True
            elif status.lower() == "yellow":
                health["healthy"] = True
                health["issues"].append("Collection in stato yellow (ottimizzazione in corso?)")
            else:
                health["issues"].append(f"Collection status: {status}")
            
            # Check punti
            if info.points_count == 0:
                health["healthy"] = False
                health["issues"].append("Collection vuota (0 chunks)")
            
            return health
            
        except Exception as e:
            health["issues"].append(f"Errore: {str(e)}")
            return health
    
    def get_latency_breakdown(self) -> Dict[str, Any]:
        """
        Template breakdown latenza (da popolare con dati reali).
        
        I valori vengono dai QueryLog aggregati.
        Qui forniamo solo la struttura.
        """
        return {
            "note": "Usa QueryCollector.get_daily_stats() per latenze reali",
            "avg_total_ms": 0,
            "avg_retrieval_ms": 0,
            "avg_rerank_l1_ms": 0,
            "avg_rerank_l2_ms": 0,
            "avg_llm_ms": 0
        }
    
    def test_retrieval(self, test_query: str = "gestione rifiuti") -> Dict[str, Any]:
        """
        Test di retrieval per verificare funzionamento.
        
        Args:
            test_query: Query di test
            
        Returns:
            Dict con risultato test
        """
        client = self._get_qdrant_client()
        
        if not client:
            return {"success": False, "error": "Qdrant non connesso"}
        
        try:
            # Necessita embedding per query reale
            # Qui facciamo solo scroll per verificare dati
            result = client.scroll(
                collection_name=self.collection_name,
                limit=5,
                with_payload=["doc_id", "text"]
            )
            
            points = result[0]
            
            if not points:
                return {
                    "success": False,
                    "error": "Collection vuota"
                }
            
            return {
                "success": True,
                "sample_docs": [
                    {
                        "doc_id": p.payload.get("doc_id", "unknown"),
                        "text_preview": p.payload.get("text", "")[:100]
                    }
                    for p in points[:3]
                ]
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


# Singleton
_collector: Optional[PipelineCollector] = None


def get_pipeline_collector() -> PipelineCollector:
    """Ottiene istanza singleton PipelineCollector"""
    global _collector
    if _collector is None:
        _collector = PipelineCollector()
    return _collector


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("=== TEST PIPELINE COLLECTOR ===\n")
    
    collector = PipelineCollector()
    
    # Test 1: Get stats
    print("Test 1: Get stats")
    stats = collector.get_stats()
    print(f"  Collection: {stats['collection_name']}")
    print(f"  Status: {stats['collection_status']}")
    print(f"  Chunks: {stats['total_chunks']}")
    print(f"  By type: {stats['chunks_by_doc_type']}")
    print(f"  VRAM: {stats['vram_usage_mb']}MB / {stats['vram_total_mb']}MB")
    print()
    
    # Test 2: Health check
    print("Test 2: Health check")
    health = collector.get_collection_health()
    print(f"  Healthy: {health['healthy']}")
    print(f"  Status: {health['status']}")
    if health['issues']:
        print(f"  Issues: {health['issues']}")
    print()
    
    # Test 3: Test retrieval
    print("Test 3: Test retrieval")
    test_result = collector.test_retrieval()
    print(f"  Success: {test_result['success']}")
    if test_result['success']:
        for doc in test_result.get('sample_docs', []):
            print(f"    - {doc['doc_id']}: {doc['text_preview'][:50]}...")
    else:
        print(f"  Error: {test_result.get('error', 'unknown')}")
    
    print("\n✅ Test completati!")

