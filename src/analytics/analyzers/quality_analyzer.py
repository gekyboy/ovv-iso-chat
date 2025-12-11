"""
Quality Analyzer per R07 Analytics
Valuta qualità delle risposte RAG

R07 - Sistema Analytics
Created: 2025-12-08

Metriche:
- Hit Rate: % query con almeno 1 doc rilevante
- Feedback Score: % feedback positivi
- No-Results Rate: % query senza risultati
- Latency percentiles (P50, P95, P99)
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class QualityAnalyzer:
    """
    Analizzatore qualità risposte.
    
    Features:
    - Calcolo metriche retrieval
    - Analisi feedback utenti
    - Identificazione query problematiche
    - Benchmark latenza
    
    Example:
        >>> analyzer = QualityAnalyzer()
        >>> metrics = analyzer.calculate_metrics(query_logs)
    """
    
    # Soglie target
    HIT_RATE_TARGET = 0.90       # 90% query devono trovare doc
    FEEDBACK_TARGET = 0.80      # 80% feedback positivi
    LATENCY_P95_TARGET = 30000  # 30s P95 max
    
    def __init__(self):
        logger.info("QualityAnalyzer inizializzato")
    
    def generate_report(self, query_logs: List[Any]) -> Dict[str, Any]:
        """
        Genera report completo qualità.
        
        Args:
            query_logs: Lista QueryLog
            
        Returns:
            Dict con tutte le metriche
        """
        if not query_logs:
            return self._empty_report()
        
        return {
            "total_queries": len(query_logs),
            "hit_rate": self.calculate_hit_rate(query_logs),
            "feedback_score": self.calculate_feedback_score(query_logs),
            "no_results_rate": self.calculate_no_results_rate(query_logs),
            "latency_stats": self.calculate_latency_stats(query_logs),
            "latency_breakdown": self.calculate_latency_breakdown(query_logs),
            "quality_issues": self.identify_quality_issues(query_logs),
            "targets": self._get_targets(),
            "overall_health": self.assess_overall_health(query_logs)
        }
    
    def calculate_hit_rate(self, query_logs: List[Any]) -> float:
        """
        Calcola Hit Rate (% query con risultati).
        
        Hit = query con docs_retrieved > 0 AND has_sources = True
        
        Returns:
            Float 0-1
        """
        if not query_logs:
            return 0.0
        
        hits = 0
        for log in query_logs:
            docs = getattr(log, 'docs_retrieved', 0)
            has_sources = getattr(log, 'has_sources', True)
            
            if docs > 0 and has_sources:
                hits += 1
        
        return round(hits / len(query_logs), 3)
    
    def calculate_feedback_score(self, query_logs: List[Any]) -> Dict[str, Any]:
        """
        Calcola metriche feedback.
        
        Returns:
            Dict con positive_ratio, counts
        """
        with_feedback = []
        positive = 0
        negative = 0
        
        for log in query_logs:
            feedback = getattr(log, 'feedback', None)
            if feedback:
                with_feedback.append(log)
                if feedback == 'positive':
                    positive += 1
                elif feedback == 'negative':
                    negative += 1
        
        total_feedback = len(with_feedback)
        ratio = positive / total_feedback if total_feedback > 0 else 0
        
        return {
            "positive_count": positive,
            "negative_count": negative,
            "total_with_feedback": total_feedback,
            "feedback_coverage": round(total_feedback / len(query_logs), 3) if query_logs else 0,
            "positive_ratio": round(ratio, 3)
        }
    
    def calculate_no_results_rate(self, query_logs: List[Any]) -> float:
        """
        Calcola % query senza risultati utili.
        
        No-result = docs_retrieved == 0 OR has_sources == False
        
        Returns:
            Float 0-1
        """
        if not query_logs:
            return 0.0
        
        no_results = 0
        for log in query_logs:
            docs = getattr(log, 'docs_retrieved', 0)
            has_sources = getattr(log, 'has_sources', True)
            
            if docs == 0 or not has_sources:
                no_results += 1
        
        return round(no_results / len(query_logs), 3)
    
    def calculate_latency_stats(self, query_logs: List[Any]) -> Dict[str, int]:
        """
        Calcola statistiche latenza.
        
        Returns:
            Dict con avg, P50, P95, P99, min, max
        """
        latencies = [
            getattr(log, 'latency_total_ms', 0)
            for log in query_logs
            if getattr(log, 'latency_total_ms', 0) > 0
        ]
        
        if not latencies:
            return {
                "avg": 0, "p50": 0, "p95": 0, "p99": 0,
                "min": 0, "max": 0, "count": 0
            }
        
        latencies.sort()
        n = len(latencies)
        
        def percentile(data, p):
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data) - 1)]
        
        return {
            "avg": round(sum(latencies) / n),
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "min": min(latencies),
            "max": max(latencies),
            "count": n
        }
    
    def calculate_latency_breakdown(self, query_logs: List[Any]) -> Dict[str, int]:
        """
        Breakdown latenza per componente.
        
        Returns:
            Dict con latenze medie per fase
        """
        components = {
            "retrieval": [],
            "rerank_l1": [],
            "rerank_l2": [],
            "llm": []
        }
        
        for log in query_logs:
            if getattr(log, 'latency_retrieval_ms', 0) > 0:
                components["retrieval"].append(log.latency_retrieval_ms)
            if getattr(log, 'latency_rerank_l1_ms', 0) > 0:
                components["rerank_l1"].append(log.latency_rerank_l1_ms)
            if getattr(log, 'latency_rerank_l2_ms', 0) > 0:
                components["rerank_l2"].append(log.latency_rerank_l2_ms)
            if getattr(log, 'latency_llm_ms', 0) > 0:
                components["llm"].append(log.latency_llm_ms)
        
        return {
            comp: round(sum(vals) / len(vals)) if vals else 0
            for comp, vals in components.items()
        }
    
    def identify_quality_issues(self, query_logs: List[Any]) -> List[Dict[str, Any]]:
        """
        Identifica problemi di qualità.
        
        Returns:
            Lista issues con severity e descrizione
        """
        issues = []
        
        # Check hit rate
        hit_rate = self.calculate_hit_rate(query_logs)
        if hit_rate < self.HIT_RATE_TARGET:
            issues.append({
                "type": "low_hit_rate",
                "severity": "high" if hit_rate < 0.7 else "medium",
                "value": hit_rate,
                "target": self.HIT_RATE_TARGET,
                "description": f"Hit rate {hit_rate:.1%} sotto target {self.HIT_RATE_TARGET:.0%}"
            })
        
        # Check feedback
        feedback = self.calculate_feedback_score(query_logs)
        if feedback["positive_ratio"] < self.FEEDBACK_TARGET and feedback["total_with_feedback"] >= 10:
            issues.append({
                "type": "low_feedback_score",
                "severity": "high" if feedback["positive_ratio"] < 0.6 else "medium",
                "value": feedback["positive_ratio"],
                "target": self.FEEDBACK_TARGET,
                "description": f"Feedback positivo {feedback['positive_ratio']:.1%} sotto target {self.FEEDBACK_TARGET:.0%}"
            })
        
        # Check latency
        latency = self.calculate_latency_stats(query_logs)
        if latency["p95"] > self.LATENCY_P95_TARGET:
            issues.append({
                "type": "high_latency",
                "severity": "high" if latency["p95"] > 45000 else "medium",
                "value": latency["p95"],
                "target": self.LATENCY_P95_TARGET,
                "description": f"Latenza P95 {latency['p95']}ms sopra target {self.LATENCY_P95_TARGET}ms"
            })
        
        # Check no-results rate
        no_results = self.calculate_no_results_rate(query_logs)
        if no_results > 0.1:  # >10%
            issues.append({
                "type": "high_no_results",
                "severity": "high" if no_results > 0.2 else "medium",
                "value": no_results,
                "target": 0.1,
                "description": f"No-results rate {no_results:.1%} troppo alto"
            })
        
        return issues
    
    def assess_overall_health(self, query_logs: List[Any]) -> Dict[str, Any]:
        """
        Valutazione complessiva salute sistema.
        
        Returns:
            Dict con score e status
        """
        if not query_logs:
            return {"score": 0, "status": "no_data", "color": "gray"}
        
        # Calcola score composito (0-100)
        hit_rate = self.calculate_hit_rate(query_logs)
        feedback = self.calculate_feedback_score(query_logs)
        no_results = self.calculate_no_results_rate(query_logs)
        latency = self.calculate_latency_stats(query_logs)
        
        # Pesi
        score = 0
        
        # Hit rate (max 40 punti)
        score += min(40, hit_rate / self.HIT_RATE_TARGET * 40)
        
        # Feedback (max 30 punti)
        if feedback["total_with_feedback"] >= 5:
            score += min(30, feedback["positive_ratio"] / self.FEEDBACK_TARGET * 30)
        else:
            score += 15  # Default se pochi feedback
        
        # Latency (max 20 punti)
        if latency["p95"] > 0:
            latency_score = max(0, 1 - (latency["p95"] / self.LATENCY_P95_TARGET))
            score += latency_score * 20
        
        # No-results (max 10 punti)
        score += max(0, (1 - no_results / 0.2)) * 10
        
        score = round(min(100, max(0, score)))
        
        # Determina status
        if score >= 85:
            status, color = "excellent", "green"
        elif score >= 70:
            status, color = "good", "lime"
        elif score >= 55:
            status, color = "fair", "yellow"
        elif score >= 40:
            status, color = "needs_attention", "orange"
        else:
            status, color = "critical", "red"
        
        return {
            "score": score,
            "status": status,
            "color": color
        }
    
    def get_problematic_queries(
        self,
        query_logs: List[Any],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query più problematiche (feedback negativo o no results).
        
        Returns:
            Lista query con dettagli
        """
        problematic = []
        
        for log in query_logs:
            is_problematic = False
            reasons = []
            
            if getattr(log, 'feedback', None) == 'negative':
                is_problematic = True
                reasons.append("feedback_negativo")
            
            if getattr(log, 'docs_retrieved', 0) == 0:
                is_problematic = True
                reasons.append("no_docs")
            
            if not getattr(log, 'has_sources', True):
                is_problematic = True
                reasons.append("no_sources")
            
            if is_problematic:
                problematic.append({
                    "query": getattr(log, 'query_text', '')[:80],
                    "user_id": getattr(log, 'user_id', ''),
                    "timestamp": getattr(log, 'timestamp', ''),
                    "reasons": reasons,
                    "docs_retrieved": getattr(log, 'docs_retrieved', 0)
                })
        
        # Ordina per timestamp (più recenti prima)
        problematic.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return problematic[:limit]
    
    def _get_targets(self) -> Dict[str, float]:
        """Ritorna target configurati"""
        return {
            "hit_rate": self.HIT_RATE_TARGET,
            "feedback_score": self.FEEDBACK_TARGET,
            "latency_p95_ms": self.LATENCY_P95_TARGET
        }
    
    def _empty_report(self) -> Dict[str, Any]:
        """Report vuoto"""
        return {
            "total_queries": 0,
            "hit_rate": 0,
            "feedback_score": {"positive_ratio": 0, "total_with_feedback": 0},
            "no_results_rate": 0,
            "latency_stats": {"avg": 0, "p50": 0, "p95": 0, "p99": 0},
            "latency_breakdown": {},
            "quality_issues": [],
            "targets": self._get_targets(),
            "overall_health": {"score": 0, "status": "no_data", "color": "gray"}
        }


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    import random
    
    print("=== TEST QUALITY ANALYZER ===\n")
    
    # Mock QueryLog
    class MockLog:
        def __init__(self, docs, has_sources, feedback, latency):
            self.docs_retrieved = docs
            self.has_sources = has_sources
            self.feedback = feedback
            self.latency_total_ms = latency
            self.latency_retrieval_ms = int(latency * 0.15)
            self.latency_rerank_l1_ms = int(latency * 0.01)
            self.latency_rerank_l2_ms = int(latency * 0.06)
            self.latency_llm_ms = int(latency * 0.75)
            self.query_text = "Test query"
            self.user_id = "test_user"
            self.timestamp = "2025-12-08T10:00:00"
    
    # Genera dati di test
    logs = []
    
    # Query con risultati (maggioranza)
    for _ in range(80):
        logs.append(MockLog(
            docs=random.randint(20, 40),
            has_sources=True,
            feedback=random.choice(["positive", "positive", "positive", "negative", None]),
            latency=random.randint(2000, 5000)
        ))
    
    # Query senza risultati
    for _ in range(10):
        logs.append(MockLog(
            docs=0,
            has_sources=False,
            feedback="negative",
            latency=random.randint(1000, 2000)
        ))
    
    # Query lente
    for _ in range(10):
        logs.append(MockLog(
            docs=random.randint(30, 40),
            has_sources=True,
            feedback=random.choice(["positive", None]),
            latency=random.randint(35000, 50000)
        ))
    
    analyzer = QualityAnalyzer()
    
    # Test 1: Report completo
    print("Test 1: Report completo")
    report = analyzer.generate_report(logs)
    print(f"  Hit rate: {report['hit_rate']:.1%}")
    print(f"  Feedback positive: {report['feedback_score']['positive_ratio']:.1%}")
    print(f"  No-results rate: {report['no_results_rate']:.1%}")
    print()
    
    # Test 2: Latency stats
    print("Test 2: Latency stats")
    latency = report['latency_stats']
    print(f"  Avg: {latency['avg']}ms")
    print(f"  P50: {latency['p50']}ms")
    print(f"  P95: {latency['p95']}ms")
    print()
    
    # Test 3: Latency breakdown
    print("Test 3: Latency breakdown")
    breakdown = report['latency_breakdown']
    for comp, val in breakdown.items():
        print(f"  {comp}: {val}ms")
    print()
    
    # Test 4: Quality issues
    print("Test 4: Quality issues")
    for issue in report['quality_issues']:
        print(f"  [{issue['severity'].upper()}] {issue['description']}")
    print()
    
    # Test 5: Overall health
    print("Test 5: Overall health")
    health = report['overall_health']
    print(f"  Score: {health['score']}/100")
    print(f"  Status: {health['status']}")
    print(f"  Color: {health['color']}")
    
    print("\n✅ Test completati!")

