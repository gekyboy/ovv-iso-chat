"""
Query Collector per R07 Analytics
Registra ogni query utente con metadati per analisi successive

R07 - Sistema Analytics
Created: 2025-12-08

Metriche raccolte:
- Timestamp, user, query text
- Acronimi trovati ed espansi
- Documenti recuperati per fase
- Latenza totale e per componente
- Feedback utente (positivo/negativo)
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class QueryLog:
    """Singola entry di log query"""
    id: str
    timestamp: str                       # ISO format
    user_id: str
    user_role: str                       # admin, engineer, user
    query_text: str                      # Query originale
    query_expanded: str = ""             # Query espansa con acronimi
    
    # Acronimi
    acronyms_found: List[str] = field(default_factory=list)
    acronyms_expanded: Dict[str, str] = field(default_factory=dict)
    
    # Retrieval stats
    docs_retrieved: int = 0              # Documenti dal retrieval iniziale
    docs_after_rerank_l1: int = 0        # Dopo FlashRank
    docs_after_rerank_l2: int = 0        # Dopo Qwen3
    final_sources: List[str] = field(default_factory=list)  # doc_id citati
    
    # Performance
    latency_total_ms: int = 0
    latency_retrieval_ms: int = 0
    latency_rerank_l1_ms: int = 0
    latency_rerank_l2_ms: int = 0
    latency_llm_ms: int = 0
    
    # Response
    response_length: int = 0
    has_sources: bool = True
    
    # Feedback (popolato dopo)
    feedback: Optional[str] = None       # "positive", "negative", None
    feedback_at: Optional[str] = None
    
    # Session
    session_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializza per JSON"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueryLog":
        """Deserializza da JSON"""
        return cls(**data)


class QueryCollector:
    """
    Collector per log delle query utente.
    
    Features:
    - Persistenza JSON con rotazione giornaliera
    - Aggregazioni real-time (today, last_7_days)
    - Query per analisi (by_user, by_date, no_results)
    
    Example:
        >>> collector = QueryCollector()
        >>> log = collector.log_query(
        ...     user_id="mario",
        ...     query_text="Come gestire le NC?",
        ...     docs_retrieved=40,
        ...     final_sources=["PS-08_01"]
        ... )
        >>> stats = collector.get_daily_stats()
    """
    
    def __init__(
        self,
        persist_dir: str = "data/persist/analytics",
        max_days_retention: int = 90
    ):
        """
        Inizializza collector.
        
        Args:
            persist_dir: Directory per file JSON
            max_days_retention: Giorni di retention (default 90)
        """
        self.persist_dir = Path(persist_dir)
        self.max_days_retention = max_days_retention
        
        # Cache in memoria per giorno corrente
        self._today_logs: List[QueryLog] = []
        self._today_date: str = ""
        
        # Crea directory
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Carica log di oggi se esistono
        self._load_today()
        
        logger.info(f"QueryCollector inizializzato: {self.persist_dir}")
    
    def _get_log_path(self, date_str: str) -> Path:
        """Ottiene path file log per data"""
        return self.persist_dir / f"queries_{date_str}.json"
    
    def _get_today_str(self) -> str:
        """Ottiene data di oggi in formato YYYY-MM-DD"""
        return datetime.now().strftime("%Y-%m-%d")
    
    def _load_today(self):
        """Carica log di oggi"""
        today = self._get_today_str()
        self._today_date = today
        
        log_path = self._get_log_path(today)
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._today_logs = [QueryLog.from_dict(d) for d in data]
                logger.debug(f"Caricati {len(self._today_logs)} log di oggi")
            except Exception as e:
                logger.error(f"Errore caricamento log: {e}")
                self._today_logs = []
        else:
            self._today_logs = []
    
    def _save_today(self):
        """Salva log di oggi"""
        # Check se giorno cambiato
        today = self._get_today_str()
        if today != self._today_date:
            # Salva log vecchio prima di resettare
            if self._today_logs:
                self._persist_logs(self._today_date, self._today_logs)
            self._today_logs = []
            self._today_date = today
        
        # Salva log corrente
        log_path = self._get_log_path(today)
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump([log.to_dict() for log in self._today_logs], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Errore salvataggio log: {e}")
    
    def _persist_logs(self, date_str: str, logs: List[QueryLog]):
        """Persiste log per una data specifica"""
        log_path = self._get_log_path(date_str)
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump([log.to_dict() for log in logs], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Errore persistenza log {date_str}: {e}")
    
    def _generate_id(self) -> str:
        """Genera ID univoco per log"""
        import uuid
        return f"qlog_{uuid.uuid4().hex[:12]}"
    
    # ═══════════════════════════════════════════════════════════════
    # LOGGING
    # ═══════════════════════════════════════════════════════════════
    
    def log_query(
        self,
        user_id: str,
        user_role: str,
        query_text: str,
        query_expanded: str = "",
        acronyms_found: Optional[List[str]] = None,
        acronyms_expanded: Optional[Dict[str, str]] = None,
        docs_retrieved: int = 0,
        docs_after_rerank_l1: int = 0,
        docs_after_rerank_l2: int = 0,
        final_sources: Optional[List[str]] = None,
        latency_total_ms: int = 0,
        latency_retrieval_ms: int = 0,
        latency_rerank_l1_ms: int = 0,
        latency_rerank_l2_ms: int = 0,
        latency_llm_ms: int = 0,
        response_length: int = 0,
        has_sources: bool = True,
        session_id: str = ""
    ) -> QueryLog:
        """
        Registra una nuova query.
        
        Args:
            user_id: ID utente
            user_role: Ruolo (admin, engineer, user)
            query_text: Query originale
            query_expanded: Query espansa con acronimi
            acronyms_found: Lista acronimi trovati
            acronyms_expanded: Dict {acronimo: espansione}
            docs_retrieved: N. documenti dal retrieval
            docs_after_rerank_l1: N. dopo rerank L1
            docs_after_rerank_l2: N. dopo rerank L2
            final_sources: Lista doc_id citati
            latency_*_ms: Latenze componenti
            response_length: Lunghezza risposta
            has_sources: Se ha fonti
            session_id: ID sessione
            
        Returns:
            QueryLog creato
        """
        log = QueryLog(
            id=self._generate_id(),
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            user_role=user_role,
            query_text=query_text,
            query_expanded=query_expanded or query_text,
            acronyms_found=acronyms_found or [],
            acronyms_expanded=acronyms_expanded or {},
            docs_retrieved=docs_retrieved,
            docs_after_rerank_l1=docs_after_rerank_l1,
            docs_after_rerank_l2=docs_after_rerank_l2,
            final_sources=final_sources or [],
            latency_total_ms=latency_total_ms,
            latency_retrieval_ms=latency_retrieval_ms,
            latency_rerank_l1_ms=latency_rerank_l1_ms,
            latency_rerank_l2_ms=latency_rerank_l2_ms,
            latency_llm_ms=latency_llm_ms,
            response_length=response_length,
            has_sources=has_sources,
            session_id=session_id
        )
        
        self._today_logs.append(log)
        self._save_today()
        
        logger.debug(f"[R07] Query log: {user_id} - {query_text[:50]}...")
        
        return log
    
    def add_feedback(self, query_id: str, feedback: str) -> bool:
        """
        Aggiunge feedback a una query esistente.
        
        Args:
            query_id: ID della query
            feedback: "positive" o "negative"
            
        Returns:
            True se aggiornato
        """
        for log in self._today_logs:
            if log.id == query_id:
                log.feedback = feedback
                log.feedback_at = datetime.now().isoformat()
                self._save_today()
                logger.debug(f"[R07] Feedback aggiunto: {query_id} = {feedback}")
                return True
        
        # Cerca in log precedenti (ultimi 7 giorni)
        for days_ago in range(1, 8):
            date_str = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            log_path = self._get_log_path(date_str)
            
            if log_path.exists():
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        logs = [QueryLog.from_dict(d) for d in json.load(f)]
                    
                    for log in logs:
                        if log.id == query_id:
                            log.feedback = feedback
                            log.feedback_at = datetime.now().isoformat()
                            self._persist_logs(date_str, logs)
                            return True
                except Exception:
                    pass
        
        return False
    
    # ═══════════════════════════════════════════════════════════════
    # QUERY E AGGREGAZIONI
    # ═══════════════════════════════════════════════════════════════
    
    def get_today_logs(self) -> List[QueryLog]:
        """Ottiene tutti i log di oggi"""
        return self._today_logs.copy()
    
    def get_logs_for_date(self, date_str: str) -> List[QueryLog]:
        """Ottiene log per una data specifica"""
        if date_str == self._today_date:
            return self._today_logs.copy()
        
        log_path = self._get_log_path(date_str)
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    return [QueryLog.from_dict(d) for d in json.load(f)]
            except Exception as e:
                logger.error(f"Errore lettura log {date_str}: {e}")
        
        return []
    
    def get_logs_last_n_days(self, n_days: int = 7) -> List[QueryLog]:
        """Ottiene log degli ultimi N giorni"""
        all_logs = []
        
        for days_ago in range(n_days):
            date_str = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            all_logs.extend(self.get_logs_for_date(date_str))
        
        return all_logs
    
    def get_daily_stats(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Statistiche giornaliere.
        
        Args:
            date_str: Data (default: oggi)
            
        Returns:
            Dict con metriche aggregate
        """
        if date_str is None:
            date_str = self._today_date
            logs = self._today_logs
        else:
            logs = self.get_logs_for_date(date_str)
        
        if not logs:
            return self._empty_stats(date_str)
        
        # Aggregazioni base
        total_queries = len(logs)
        unique_users = len(set(log.user_id for log in logs))
        
        # Latenze
        latencies = [log.latency_total_ms for log in logs if log.latency_total_ms > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        # Feedback
        with_feedback = [log for log in logs if log.feedback]
        positive = len([log for log in with_feedback if log.feedback == "positive"])
        negative = len([log for log in with_feedback if log.feedback == "negative"])
        feedback_ratio = positive / len(with_feedback) if with_feedback else 0
        
        # Query senza risultati
        no_results = len([log for log in logs if not log.has_sources or log.docs_retrieved == 0])
        
        # Acronimi
        all_acronyms = []
        for log in logs:
            all_acronyms.extend(log.acronyms_found)
        acronym_freq = defaultdict(int)
        for acr in all_acronyms:
            acronym_freq[acr] += 1
        
        # Per utente
        queries_by_user = defaultdict(int)
        for log in logs:
            queries_by_user[log.user_id] += 1
        
        # Per ora
        queries_by_hour = defaultdict(int)
        for log in logs:
            hour = datetime.fromisoformat(log.timestamp).hour
            queries_by_hour[hour] += 1
        
        return {
            "date": date_str,
            "total_queries": total_queries,
            "unique_users": unique_users,
            "avg_latency_ms": round(avg_latency),
            "feedback_total": len(with_feedback),
            "feedback_positive": positive,
            "feedback_negative": negative,
            "feedback_ratio": round(feedback_ratio, 3),
            "no_results_count": no_results,
            "no_results_ratio": round(no_results / total_queries, 3) if total_queries else 0,
            "acronyms_total": len(all_acronyms),
            "acronyms_unique": len(set(all_acronyms)),
            "top_acronyms": sorted(acronym_freq.items(), key=lambda x: x[1], reverse=True)[:10],
            "queries_by_user": dict(queries_by_user),
            "queries_by_hour": dict(queries_by_hour),
            "top_users": sorted(queries_by_user.items(), key=lambda x: x[1], reverse=True)[:5]
        }
    
    def _empty_stats(self, date_str: str) -> Dict[str, Any]:
        """Statistiche vuote"""
        return {
            "date": date_str,
            "total_queries": 0,
            "unique_users": 0,
            "avg_latency_ms": 0,
            "feedback_total": 0,
            "feedback_positive": 0,
            "feedback_negative": 0,
            "feedback_ratio": 0,
            "no_results_count": 0,
            "no_results_ratio": 0,
            "acronyms_total": 0,
            "acronyms_unique": 0,
            "top_acronyms": [],
            "queries_by_user": {},
            "queries_by_hour": {},
            "top_users": []
        }
    
    def get_weekly_stats(self) -> Dict[str, Any]:
        """Statistiche settimanali con trend"""
        logs = self.get_logs_last_n_days(7)
        
        # Oggi vs ieri
        today_stats = self.get_daily_stats()
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_stats = self.get_daily_stats(yesterday)
        
        # Calcola delta
        delta_queries = today_stats["total_queries"] - yesterday_stats["total_queries"]
        delta_users = today_stats["unique_users"] - yesterday_stats["unique_users"]
        delta_latency = today_stats["avg_latency_ms"] - yesterday_stats["avg_latency_ms"]
        
        if yesterday_stats["total_queries"] > 0:
            delta_queries_pct = round(delta_queries / yesterday_stats["total_queries"] * 100, 1)
        else:
            delta_queries_pct = 100 if today_stats["total_queries"] > 0 else 0
        
        # Stats settimanali aggregate
        total_queries = len(logs)
        unique_users = len(set(log.user_id for log in logs))
        
        latencies = [log.latency_total_ms for log in logs if log.latency_total_ms > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        with_feedback = [log for log in logs if log.feedback]
        positive = len([log for log in with_feedback if log.feedback == "positive"])
        feedback_ratio = positive / len(with_feedback) if with_feedback else 0
        
        return {
            "period": "last_7_days",
            "total_queries": total_queries,
            "unique_users": unique_users,
            "avg_latency_ms": round(avg_latency),
            "feedback_ratio": round(feedback_ratio, 3),
            "today": today_stats,
            "deltas": {
                "queries": delta_queries,
                "queries_pct": delta_queries_pct,
                "users": delta_users,
                "latency_ms": delta_latency
            }
        }
    
    def get_no_results_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Query senza risultati (per gap analysis).
        
        Returns:
            Lista query con frequenza
        """
        logs = self.get_logs_last_n_days(30)
        
        # Aggrega per query (normalizzata)
        query_counts = defaultdict(lambda: {"count": 0, "users": set(), "last": ""})
        
        for log in logs:
            if not log.has_sources or log.docs_retrieved == 0:
                key = log.query_text.lower().strip()
                query_counts[key]["count"] += 1
                query_counts[key]["users"].add(log.user_id)
                query_counts[key]["last"] = log.timestamp
        
        # Converti e ordina
        results = []
        for query, data in query_counts.items():
            results.append({
                "query": query,
                "count": data["count"],
                "users": len(data["users"]),
                "last_attempt": data["last"]
            })
        
        results.sort(key=lambda x: x["count"], reverse=True)
        
        return results[:limit]
    
    def cleanup_old_logs(self):
        """Rimuove log più vecchi di max_days_retention"""
        cutoff_date = datetime.now() - timedelta(days=self.max_days_retention)
        
        removed = 0
        for log_file in self.persist_dir.glob("queries_*.json"):
            try:
                # Estrai data dal filename
                date_str = log_file.stem.replace("queries_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                
                if file_date < cutoff_date:
                    log_file.unlink()
                    removed += 1
            except Exception:
                pass
        
        if removed > 0:
            logger.info(f"[R07] Rimossi {removed} file log vecchi")


# Singleton
_collector: Optional[QueryCollector] = None


def get_query_collector() -> QueryCollector:
    """Ottiene istanza singleton QueryCollector"""
    global _collector
    if _collector is None:
        _collector = QueryCollector()
    return _collector


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    import shutil
    
    # Test in directory temporanea
    temp_dir = tempfile.mkdtemp()
    
    print("=== TEST QUERY COLLECTOR ===\n")
    
    collector = QueryCollector(persist_dir=temp_dir)
    
    # Test 1: Log query
    print("Test 1: Log query")
    log1 = collector.log_query(
        user_id="mario",
        user_role="engineer",
        query_text="Come gestire le NC?",
        query_expanded="Come gestire le NC (Non Conformità)?",
        acronyms_found=["NC"],
        acronyms_expanded={"NC": "Non Conformità"},
        docs_retrieved=40,
        docs_after_rerank_l1=15,
        docs_after_rerank_l2=5,
        final_sources=["PS-08_01", "IL-08_02"],
        latency_total_ms=2847,
        latency_retrieval_ms=450,
        latency_rerank_l1_ms=12,
        latency_rerank_l2_ms=180,
        latency_llm_ms=2200,
        response_length=1847,
        has_sources=True,
        session_id="sess_abc123"
    )
    print(f"  ID: {log1.id}")
    print(f"  Query: {log1.query_text}")
    print()
    
    # Test 2: Altre query
    print("Test 2: Altre query")
    log2 = collector.log_query(
        user_id="luigi",
        user_role="user",
        query_text="Cos'è il WCM?",
        docs_retrieved=0,
        has_sources=False
    )
    log3 = collector.log_query(
        user_id="mario",
        user_role="engineer",
        query_text="Come compilare il modulo MR-08_01?",
        docs_retrieved=35,
        final_sources=["MR-08_01"],
        latency_total_ms=3100
    )
    print(f"  Logs totali oggi: {len(collector.get_today_logs())}")
    print()
    
    # Test 3: Feedback
    print("Test 3: Feedback")
    collector.add_feedback(log1.id, "positive")
    collector.add_feedback(log3.id, "positive")
    print(f"  Log1 feedback: {collector.get_today_logs()[0].feedback}")
    print()
    
    # Test 4: Stats giornaliere
    print("Test 4: Stats giornaliere")
    stats = collector.get_daily_stats()
    print(f"  Total queries: {stats['total_queries']}")
    print(f"  Unique users: {stats['unique_users']}")
    print(f"  Avg latency: {stats['avg_latency_ms']}ms")
    print(f"  Feedback ratio: {stats['feedback_ratio']}")
    print(f"  No results: {stats['no_results_count']}")
    print()
    
    # Test 5: Query senza risultati
    print("Test 5: Query senza risultati")
    no_results = collector.get_no_results_queries()
    for q in no_results:
        print(f"  - '{q['query'][:40]}...' ({q['count']} volte)")
    print()
    
    # Cleanup
    shutil.rmtree(temp_dir)
    
    print("✅ Test completati!")

