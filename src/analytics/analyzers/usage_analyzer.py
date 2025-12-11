"""
Usage Analyzer per R07 Analytics
Analizza pattern di utilizzo del sistema

R07 - Sistema Analytics
Created: 2025-12-08

Analisi:
- Distribuzione query per ora/giorno
- Segmentazione utenti
- Topic clustering
- Trend temporali
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class UsageAnalyzer:
    """
    Analizzatore pattern di utilizzo.
    
    Features:
    - Analisi distribuzione temporale
    - Segmentazione utenti (power, regular, occasional)
    - Identificazione topic popolari
    - Calcolo trend week-over-week
    
    Example:
        >>> analyzer = UsageAnalyzer()
        >>> report = analyzer.generate_report(query_logs)
    """
    
    # Soglie per segmentazione utenti
    POWER_USER_THRESHOLD = 20      # Query/settimana
    REGULAR_USER_THRESHOLD = 5     # Query/settimana
    
    def __init__(self):
        logger.info("UsageAnalyzer inizializzato")
    
    def generate_report(
        self,
        query_logs: List[Any],
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Genera report completo utilizzo.
        
        Args:
            query_logs: Lista QueryLog
            days: Giorni da analizzare
            
        Returns:
            Dict con tutte le analisi
        """
        if not query_logs:
            return self._empty_report()
        
        return {
            "period_days": days,
            "total_queries": len(query_logs),
            "unique_users": len(set(getattr(log, 'user_id', '') for log in query_logs)),
            "hourly_distribution": self.analyze_hourly_distribution(query_logs),
            "daily_distribution": self.analyze_daily_distribution(query_logs),
            "user_segments": self.segment_users(query_logs),
            "top_users": self.get_top_users(query_logs),
            "query_patterns": self.analyze_query_patterns(query_logs),
            "trend": self.calculate_trend(query_logs)
        }
    
    def analyze_hourly_distribution(self, query_logs: List[Any]) -> Dict[int, int]:
        """
        Distribuzione query per ora del giorno.
        
        Returns:
            Dict {hour: count}
        """
        distribution = defaultdict(int)
        
        for log in query_logs:
            timestamp = getattr(log, 'timestamp', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    distribution[dt.hour] += 1
                except Exception:
                    pass
        
        # Assicura tutte le ore presenti
        return {h: distribution.get(h, 0) for h in range(24)}
    
    def analyze_daily_distribution(self, query_logs: List[Any]) -> Dict[str, int]:
        """
        Distribuzione query per giorno della settimana.
        
        Returns:
            Dict {day_name: count}
        """
        days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
        distribution = defaultdict(int)
        
        for log in query_logs:
            timestamp = getattr(log, 'timestamp', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    distribution[days[dt.weekday()]] += 1
                except Exception:
                    pass
        
        return {day: distribution.get(day, 0) for day in days}
    
    def segment_users(self, query_logs: List[Any]) -> Dict[str, List[str]]:
        """
        Segmenta utenti per frequenza utilizzo.
        
        Categorie:
        - power_users: >= 20 query/settimana
        - regular: >= 5 query/settimana
        - occasional: < 5 query/settimana
        
        Returns:
            Dict con liste user_id per categoria
        """
        user_counts = defaultdict(int)
        
        for log in query_logs:
            user_id = getattr(log, 'user_id', 'unknown')
            user_counts[user_id] += 1
        
        # Normalizza per periodo (assumendo 7 giorni)
        segments = {
            "power_users": [],
            "regular": [],
            "occasional": []
        }
        
        for user_id, count in user_counts.items():
            if count >= self.POWER_USER_THRESHOLD:
                segments["power_users"].append(user_id)
            elif count >= self.REGULAR_USER_THRESHOLD:
                segments["regular"].append(user_id)
            else:
                segments["occasional"].append(user_id)
        
        return segments
    
    def get_top_users(self, query_logs: List[Any], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Top utenti per numero query.
        
        Returns:
            Lista {user_id, count, avg_latency}
        """
        user_stats = defaultdict(lambda: {"count": 0, "latency_sum": 0})
        
        for log in query_logs:
            user_id = getattr(log, 'user_id', 'unknown')
            user_stats[user_id]["count"] += 1
            user_stats[user_id]["latency_sum"] += getattr(log, 'latency_total_ms', 0)
        
        top_users = []
        for user_id, stats in user_stats.items():
            avg_latency = stats["latency_sum"] / stats["count"] if stats["count"] > 0 else 0
            top_users.append({
                "user_id": user_id,
                "query_count": stats["count"],
                "avg_latency_ms": round(avg_latency)
            })
        
        top_users.sort(key=lambda x: x["query_count"], reverse=True)
        
        return top_users[:limit]
    
    def analyze_query_patterns(self, query_logs: List[Any]) -> Dict[str, Any]:
        """
        Analizza pattern nelle query.
        
        Identifica:
        - Query procedurali ("come fare X")
        - Query informative ("cos'è X")
        - Query compilazione ("/teach", moduli)
        
        Returns:
            Dict con conteggi pattern
        """
        patterns = {
            "procedural": 0,     # "come", "procedura", "fare"
            "informative": 0,   # "cos'è", "definizione", "significa"
            "compilation": 0,   # "/teach", "compilare", "modulo"
            "search": 0,        # query generiche
            "commands": 0       # comandi speciali /...
        }
        
        procedural_keywords = ['come', 'procedura', 'fare', 'gestire', 'step', 'passaggi']
        informative_keywords = ["cos'è", 'cosa significa', 'definizione', 'significa', 'spiegami']
        compilation_keywords = ['compilare', 'compilazione', 'modulo', 'mr-', 'teach']
        
        for log in query_logs:
            query = getattr(log, 'query_text', '').lower()
            
            if query.startswith('/'):
                patterns["commands"] += 1
            elif any(kw in query for kw in procedural_keywords):
                patterns["procedural"] += 1
            elif any(kw in query for kw in informative_keywords):
                patterns["informative"] += 1
            elif any(kw in query for kw in compilation_keywords):
                patterns["compilation"] += 1
            else:
                patterns["search"] += 1
        
        total = sum(patterns.values())
        percentages = {
            k: round(v / total * 100, 1) if total > 0 else 0
            for k, v in patterns.items()
        }
        
        return {
            "counts": patterns,
            "percentages": percentages
        }
    
    def calculate_trend(self, query_logs: List[Any]) -> Dict[str, Any]:
        """
        Calcola trend (confronto periodi).
        
        Returns:
            Dict con delta e percentuali
        """
        if not query_logs:
            return {"status": "no_data"}
        
        # Ordina per timestamp
        sorted_logs = sorted(
            query_logs,
            key=lambda x: getattr(x, 'timestamp', ''),
            reverse=True
        )
        
        # Dividi in due metà per confronto
        midpoint = len(sorted_logs) // 2
        recent = sorted_logs[:midpoint]
        older = sorted_logs[midpoint:]
        
        recent_count = len(recent)
        older_count = len(older) if older else 1
        
        delta = recent_count - older_count
        pct_change = round((delta / older_count) * 100, 1) if older_count > 0 else 0
        
        # Calcola anche latenza trend
        recent_latencies = [getattr(log, 'latency_total_ms', 0) for log in recent]
        older_latencies = [getattr(log, 'latency_total_ms', 0) for log in older]
        
        recent_avg_latency = sum(recent_latencies) / len(recent_latencies) if recent_latencies else 0
        older_avg_latency = sum(older_latencies) / len(older_latencies) if older_latencies else 0
        
        latency_delta = round(recent_avg_latency - older_avg_latency)
        
        return {
            "recent_count": recent_count,
            "older_count": older_count,
            "delta": delta,
            "pct_change": pct_change,
            "trend_direction": "up" if delta > 0 else "down" if delta < 0 else "stable",
            "latency_delta_ms": latency_delta,
            "latency_trend": "improving" if latency_delta < 0 else "degrading" if latency_delta > 0 else "stable"
        }
    
    def get_peak_hours(self, query_logs: List[Any]) -> List[int]:
        """
        Identifica ore di picco (top 3).
        
        Returns:
            Lista ore ordinate per traffico
        """
        distribution = self.analyze_hourly_distribution(query_logs)
        sorted_hours = sorted(distribution.items(), key=lambda x: x[1], reverse=True)
        return [h for h, _ in sorted_hours[:3]]
    
    def get_quiet_hours(self, query_logs: List[Any]) -> List[int]:
        """
        Identifica ore di basso traffico (bottom 3).
        
        Returns:
            Lista ore con meno traffico
        """
        distribution = self.analyze_hourly_distribution(query_logs)
        sorted_hours = sorted(distribution.items(), key=lambda x: x[1])
        return [h for h, _ in sorted_hours[:3]]
    
    def _empty_report(self) -> Dict[str, Any]:
        """Report vuoto"""
        return {
            "period_days": 0,
            "total_queries": 0,
            "unique_users": 0,
            "hourly_distribution": {},
            "daily_distribution": {},
            "user_segments": {"power_users": [], "regular": [], "occasional": []},
            "top_users": [],
            "query_patterns": {"counts": {}, "percentages": {}},
            "trend": {"status": "no_data"}
        }


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    from datetime import datetime, timedelta
    import random
    
    print("=== TEST USAGE ANALYZER ===\n")
    
    # Mock QueryLog
    class MockLog:
        def __init__(self, user_id, query, timestamp, latency=2000):
            self.user_id = user_id
            self.query_text = query
            self.timestamp = timestamp
            self.latency_total_ms = latency
    
    # Genera dati di test
    users = ["mario", "luigi", "anna", "paolo", "guest"]
    queries = [
        "Come gestire le NC?",
        "Cos'è il WCM?",
        "/teach MR-08_01",
        "Procedura per audit",
        "Definizione di FMEA",
        "Compilare il modulo rifiuti"
    ]
    
    logs = []
    now = datetime.now()
    
    # Mario è power user
    for i in range(25):
        logs.append(MockLog(
            "mario",
            random.choice(queries),
            (now - timedelta(hours=random.randint(1, 168))).isoformat(),
            random.randint(1500, 4000)
        ))
    
    # Luigi è regular
    for i in range(8):
        logs.append(MockLog(
            "luigi",
            random.choice(queries),
            (now - timedelta(hours=random.randint(1, 168))).isoformat()
        ))
    
    # Altri occasional
    for user in ["anna", "paolo", "guest"]:
        for i in range(random.randint(1, 3)):
            logs.append(MockLog(
                user,
                random.choice(queries),
                (now - timedelta(hours=random.randint(1, 168))).isoformat()
            ))
    
    analyzer = UsageAnalyzer()
    
    # Test 1: Report completo
    print("Test 1: Report completo")
    report = analyzer.generate_report(logs)
    print(f"  Total queries: {report['total_queries']}")
    print(f"  Unique users: {report['unique_users']}")
    print()
    
    # Test 2: Segmentazione
    print("Test 2: User segments")
    segments = report['user_segments']
    print(f"  Power users: {segments['power_users']}")
    print(f"  Regular: {segments['regular']}")
    print(f"  Occasional: {segments['occasional']}")
    print()
    
    # Test 3: Pattern
    print("Test 3: Query patterns")
    patterns = report['query_patterns']
    print(f"  Counts: {patterns['counts']}")
    print(f"  Percentages: {patterns['percentages']}")
    print()
    
    # Test 4: Trend
    print("Test 4: Trend")
    trend = report['trend']
    print(f"  Direction: {trend['trend_direction']}")
    print(f"  Change: {trend['pct_change']}%")
    print(f"  Latency trend: {trend['latency_trend']}")
    print()
    
    # Test 5: Peak hours
    print("Test 5: Peak hours")
    peaks = analyzer.get_peak_hours(logs)
    print(f"  Peak hours: {peaks}")
    
    print("\n✅ Test completati!")

