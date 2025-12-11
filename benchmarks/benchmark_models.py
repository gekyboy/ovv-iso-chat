"""
Benchmark per OVV ISO Chat v3.1
Test faithfulness (cosine sim) e F1 su query ISO
"""

import sys
from pathlib import Path

# Aggiungi root al path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
import time
from typing import Dict, List, Tuple
from dataclasses import dataclass

import torch
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    query: str
    expected_doc: str
    retrieved_docs: List[str]
    faithfulness: float  # Cosine sim con expected
    hit: bool  # Expected in retrieved
    latency_ms: float


# Query di test ISO
TEST_QUERIES = [
    # Query su rifiuti (IL-06)
    {"query": "Come gestire i rifiuti pericolosi?", "expected": "IL-06_01"},
    {"query": "Quali sono le procedure per smaltimento rifiuti?", "expected": "IL-06_01"},
    {"query": "Gestione rifiuti non pericolosi", "expected": "IL-06_01"},
    
    # Query su qualità (PS-08)
    {"query": "Come pianificare i processi produttivi?", "expected": "PS-08_01"},
    {"query": "Requisiti cliente come si gestiscono?", "expected": "PS-08_02"},
    
    # Query su audit (PS-09)
    {"query": "Come fare audit interni?", "expected": "PS-09_02"},
    {"query": "Monitoraggio sistema di gestione", "expected": "PS-09_01"},
    
    # Query su miglioramento (PS-10)
    {"query": "Processo di miglioramento continuo", "expected": "PS-10_01"},
    
    # Query su Kaizen
    {"query": "Cos'è un Quick Kaizen?", "expected": "MR-10_03"},
    {"query": "Standard Kaizen come si compila?", "expected": "MR-10_02"},
    
    # Teach queries
    {"query": "Come compilare il modulo Major Kaizen?", "expected": "MR-10_01"},
    {"query": "Istruzioni per MR-10_01", "expected": "MR-10_01"},
]


class Benchmarker:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self._pipeline = None
        self._embedder = None
    
    @property
    def pipeline(self):
        if self._pipeline is None:
            from src.integration.rag_pipeline import RAGPipeline
            self._pipeline = RAGPipeline(config_path=self.config_path)
        return self._pipeline
    
    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = SentenceTransformer("BAAI/bge-m3")
        return self._embedder
    
    def compute_faithfulness(self, response: str, expected_doc: str) -> float:
        """
        Calcola faithfulness come cosine similarity
        tra risposta e documento atteso
        """
        try:
            embeddings = self.embedder.encode([response, expected_doc])
            sim = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
            return float(sim)
        except Exception as e:
            logger.warning(f"Errore faithfulness: {e}")
            return 0.0
    
    def run_single_query(self, query: str, expected: str) -> BenchmarkResult:
        """Esegue singola query e calcola metriche"""
        start = time.time()
        
        try:
            response = self.pipeline.query(query)
            latency = (time.time() - start) * 1000
            
            # Estrai doc_id dai risultati
            retrieved = [s.doc_id for s in response.sources[:5]]
            
            # Check hit
            hit = any(expected.lower() in doc.lower() for doc in retrieved)
            
            # Faithfulness
            faithfulness = self.compute_faithfulness(
                response.answer, 
                f"Documento {expected}"
            )
            
            return BenchmarkResult(
                query=query,
                expected_doc=expected,
                retrieved_docs=retrieved,
                faithfulness=faithfulness,
                hit=hit,
                latency_ms=latency
            )
            
        except Exception as e:
            logger.error(f"Errore query '{query}': {e}")
            return BenchmarkResult(
                query=query,
                expected_doc=expected,
                retrieved_docs=[],
                faithfulness=0.0,
                hit=False,
                latency_ms=0.0
            )
    
    def run_benchmark(
        self, 
        queries: List[Dict] = None,
        limit: int = None
    ) -> Dict:
        """
        Esegue benchmark completo
        
        Returns:
            Dict con metriche aggregate
        """
        if queries is None:
            queries = TEST_QUERIES
        
        if limit:
            queries = queries[:limit]
        
        logger.info(f"Esecuzione benchmark su {len(queries)} query...")
        
        results = []
        for i, q in enumerate(queries, 1):
            logger.info(f"[{i}/{len(queries)}] {q['query'][:50]}...")
            result = self.run_single_query(q["query"], q["expected"])
            results.append(result)
        
        # Calcola metriche aggregate
        hits = sum(1 for r in results if r.hit)
        total = len(results)
        
        precision = hits / total if total > 0 else 0
        recall = hits / total if total > 0 else 0  # Simplified
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        avg_faithfulness = np.mean([r.faithfulness for r in results])
        avg_latency = np.mean([r.latency_ms for r in results])
        
        summary = {
            "total_queries": total,
            "hits": hits,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "avg_faithfulness": float(avg_faithfulness),
            "avg_latency_ms": float(avg_latency),
            "results": [
                {
                    "query": r.query,
                    "expected": r.expected_doc,
                    "hit": r.hit,
                    "faithfulness": r.faithfulness,
                    "retrieved": r.retrieved_docs[:3]
                }
                for r in results
            ]
        }
        
        return summary
    
    def print_report(self, summary: Dict):
        """Stampa report benchmark"""
        print("\n" + "=" * 60)
        print("OVV ISO Chat v3.1 - Benchmark Report")
        print("=" * 60)
        
        print(f"\n📊 Metriche Aggregate:")
        print(f"   Query totali:    {summary['total_queries']}")
        print(f"   Hits:            {summary['hits']}")
        print(f"   Precision:       {summary['precision']:.2%}")
        print(f"   F1 Score:        {summary['f1_score']:.2%}")
        print(f"   Faithfulness:    {summary['avg_faithfulness']:.2%}")
        print(f"   Latenza media:   {summary['avg_latency_ms']:.0f}ms")
        
        # Target check
        print(f"\n🎯 Target Check:")
        f1_ok = summary['f1_score'] >= 0.85
        faith_ok = summary['avg_faithfulness'] >= 0.5
        print(f"   F1 >= 0.85:      {'✅' if f1_ok else '❌'} ({summary['f1_score']:.2%})")
        print(f"   Faith >= 0.50:   {'✅' if faith_ok else '❌'} ({summary['avg_faithfulness']:.2%})")
        
        # Dettagli query fallite
        failed = [r for r in summary['results'] if not r['hit']]
        if failed:
            print(f"\n❌ Query fallite ({len(failed)}):")
            for r in failed[:5]:
                print(f"   - {r['query'][:40]}... (expected: {r['expected']})")


def main():
    """Entry point benchmark"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Benchmark OVV ISO Chat")
    parser.add_argument("--limit", "-l", type=int, help="Limite query")
    parser.add_argument("--output", "-o", help="Salva risultati JSON")
    args = parser.parse_args()
    
    benchmarker = Benchmarker()
    summary = benchmarker.run_benchmark(limit=args.limit)
    benchmarker.print_report(summary)
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Risultati salvati in {args.output}")
    
    # Return code basato su F1
    return 0 if summary['f1_score'] >= 0.85 else 1


if __name__ == "__main__":
    exit(main())

