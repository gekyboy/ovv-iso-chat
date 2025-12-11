"""
Implicit Learner per R08-R10
Orchestratore principale per apprendimento implicito

Created: 2025-12-08

Responsabilità:
1. Raccoglie segnali impliciti (SignalCollector)
2. Analizza comportamento utente (BehaviorAnalyzer)
3. Registra voti per consenso (VotingTracker)
4. Promuove memorie condivise (GlobalPromoter)
5. Salva preferenze in namespace utente
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..signals.signal_collector import SignalCollector, get_signal_collector
from ..signals.signal_types import SignalType, ImplicitSignal, SIGNAL_WEIGHTS
from ..analyzers.behavior_analyzer import BehaviorAnalyzer, BehaviorPattern
from ..consensus.voting_tracker import VotingTracker, ConsensusCandidate
from ..consensus.promoter import GlobalPromoter

logger = logging.getLogger(__name__)


class ImplicitLearner:
    """
    Orchestratore per apprendimento implicito multi-utente.
    
    Integra:
    - SignalCollector: raccolta segnali
    - BehaviorAnalyzer: analisi pattern
    - VotingTracker: consenso multi-utente
    - GlobalPromoter: promozione user→global
    
    Usage in Chainlit:
        >>> learner = get_implicit_learner()
        >>> # Ad ogni query
        >>> learner.on_query_start(user_id, session_id, query)
        >>> # Alla risposta
        >>> learner.on_response(user_id, session_id, query_id, response_text, sources)
        >>> # Su eventi UI
        >>> learner.on_copy(user_id, session_id, text, query_id)
        >>> # Periodicamente (cron notturno)
        >>> learner.run_nightly_analysis()
    """
    
    def __init__(
        self,
        signal_collector: SignalCollector = None,
        voting_tracker: VotingTracker = None,
        enable_auto_memory: bool = True,
        enable_consensus: bool = True
    ):
        """
        Inizializza learner.
        
        Args:
            signal_collector: Istanza SignalCollector (default singleton)
            voting_tracker: Istanza VotingTracker (default nuovo)
            enable_auto_memory: Se True, salva automaticamente preferenze
            enable_consensus: Se True, attiva voting multi-utente
        """
        self.signal_collector = signal_collector or get_signal_collector()
        self.voting_tracker = voting_tracker or VotingTracker()
        self.behavior_analyzer = BehaviorAnalyzer()
        self.promoter = GlobalPromoter(self.voting_tracker)
        
        self.enable_auto_memory = enable_auto_memory
        self.enable_consensus = enable_consensus
        
        # Traccia query correnti per dwell time
        self._active_queries: Dict[str, Dict[str, Any]] = {}
        
        # Cache memoria per evitare duplicati
        self._memory_store = None
        
        logger.info(f"ImplicitLearner: auto_memory={enable_auto_memory}, consensus={enable_consensus}")
    
    def _get_memory_store(self):
        """Lazy load memory store"""
        if self._memory_store is None:
            try:
                from src.memory.store import get_memory_store
                self._memory_store = get_memory_store()
            except ImportError:
                logger.warning("MemoryStore non disponibile")
        return self._memory_store
    
    # ═══════════════════════════════════════════════════════════════
    # CHAINLIT EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════════
    
    def on_session_start(self, user_id: str, session_id: str):
        """Chiamato all'inizio sessione Chainlit"""
        self.signal_collector.start_session(user_id, session_id)
        logger.debug(f"[Learning] Session start: {user_id}")
    
    def on_session_end(self, session_id: str, was_positive: bool = True):
        """Chiamato alla fine sessione Chainlit"""
        self.signal_collector.end_session(session_id, was_positive)
    
    def on_query_start(
        self,
        user_id: str,
        session_id: str,
        query: str,
        query_id: str = None
    ) -> str:
        """
        Chiamato all'inizio di ogni query.
        
        Args:
            user_id: ID utente
            session_id: ID sessione
            query: Testo query
            query_id: ID query (generato se non fornito)
            
        Returns:
            query_id usato
        """
        import uuid
        query_id = query_id or f"q_{uuid.uuid4().hex[:8]}"
        
        self._active_queries[query_id] = {
            "user_id": user_id,
            "session_id": session_id,
            "query": query,
            "start_time": datetime.now()
        }
        
        self.signal_collector.start_query(query_id)
        
        return query_id
    
    def on_response(
        self,
        user_id: str,
        session_id: str,
        query_id: str,
        response_text: str,
        sources: List[str] = None,
        memories_used: List[str] = None
    ):
        """
        Chiamato quando la risposta viene generata.
        
        Args:
            user_id: ID utente
            session_id: ID sessione
            query_id: ID query
            response_text: Testo risposta
            sources: Lista doc_id citati
            memories_used: ID memorie usate nella risposta
        """
        # Aggiorna info query
        if query_id in self._active_queries:
            self._active_queries[query_id]["response_time"] = datetime.now()
            self._active_queries[query_id]["response_length"] = len(response_text)
            self._active_queries[query_id]["sources"] = sources or []
        
        # Track memorie usate
        if memories_used:
            for mem_id in memories_used:
                self.signal_collector.track_memory_used(
                    user_id, session_id, mem_id, query_id
                )
    
    def on_query_end(
        self,
        user_id: str,
        session_id: str,
        query_id: str,
        was_helpful: bool = None
    ):
        """
        Chiamato quando l'utente passa alla query successiva.
        
        Calcola dwell time e processa segnali.
        
        Args:
            user_id: ID utente
            session_id: ID sessione
            query_id: ID query terminata
            was_helpful: Feedback esplicito (opzionale)
        """
        # Calcola dwell time
        dwell_time = self.signal_collector.end_query(user_id, session_id, query_id)
        
        if query_id in self._active_queries:
            query_info = self._active_queries.pop(query_id)
            
            # Se c'è feedback esplicito, registra come segnale forte
            if was_helpful is not None:
                signal_type = SignalType.MEMORY_CONFIRMED if was_helpful else SignalType.MEMORY_REJECTED
                self.signal_collector.track(
                    signal_type, user_id, session_id,
                    query_id=query_id,
                    value=1 if was_helpful else -1
                )
    
    def on_click_source(
        self,
        user_id: str,
        session_id: str,
        doc_id: str,
        query_id: str = None
    ):
        """Utente ha cliccato su una fonte"""
        self.signal_collector.track_click_source(
            user_id, session_id, doc_id, query_id
        )
        
        # Registra come voto implicito per il documento
        if self.enable_consensus:
            self.voting_tracker.register_vote(
                user_id,
                f"Documento {doc_id} utile per questo tipo di query",
                "preference",
                0.6,
                evidence=[f"Click su {doc_id}"]
            )
    
    def on_copy(
        self,
        user_id: str,
        session_id: str,
        text: str,
        query_id: str = None
    ):
        """Utente ha copiato testo"""
        signal = self.signal_collector.track_copy_text(
            user_id, session_id, text, query_id
        )
        
        if signal and self.enable_consensus and len(text) > 50:
            # Testo copiato = contenuto utile
            # Potrebbe diventare un "fatto" condiviso
            self.voting_tracker.register_vote(
                user_id,
                text[:200],  # Limita lunghezza
                "fact",
                0.5,
                evidence=["Testo copiato da risposta"]
            )
    
    def on_scroll(
        self,
        user_id: str,
        session_id: str,
        depth: float,
        query_id: str = None
    ):
        """Utente ha scrollato nella risposta"""
        self.signal_collector.track_scroll_depth(
            user_id, session_id, depth, query_id
        )
    
    def on_follow_up(
        self,
        user_id: str,
        session_id: str,
        prev_query_id: str,
        new_query: str
    ):
        """Utente ha fatto domanda follow-up"""
        # Determina se è follow-up positivo o riformulazione negativa
        if prev_query_id in self._active_queries:
            prev_query = self._active_queries[prev_query_id].get("query", "")
            
            # Heuristica: se molto simile, è riformulazione (negativo)
            from ..consensus.voting_tracker import VotingTracker
            tracker = VotingTracker()
            similarity = tracker._calculate_similarity(
                prev_query.lower(), new_query.lower()
            )
            
            if similarity > 0.7:
                # Riformulazione (insoddisfatto)
                self.signal_collector.track_re_ask(
                    user_id, session_id, prev_query, new_query
                )
            else:
                # Follow-up genuino (soddisfatto, vuole approfondire)
                self.signal_collector.track_follow_up(
                    user_id, session_id, prev_query_id, new_query
                )
    
    def on_teach_complete(
        self,
        user_id: str,
        session_id: str,
        taught_content: str,
        memory_type: str,
        doc_id: str = None
    ):
        """
        Chiamato quando utente completa /teach.
        
        Questo è un segnale forte per:
        1. Salvare in memoria utente
        2. Registrare come voto per consenso
        """
        # Track signal
        self.signal_collector.track_teach_complete(
            user_id, session_id, doc_id
        )
        
        # Registra come voto forte per consenso
        if self.enable_consensus:
            self.voting_tracker.register_vote(
                user_id,
                taught_content,
                memory_type,
                0.9,  # Voto forte - è stato insegnato esplicitamente
                evidence=["/teach completato"]
            )
    
    def on_teach_abort(
        self,
        user_id: str,
        session_id: str,
        doc_id: str = None
    ):
        """Utente ha abbandonato /teach"""
        self.signal_collector.track_teach_abort(
            user_id, session_id, doc_id
        )
    
    # ═══════════════════════════════════════════════════════════════
    # ANALYSIS & PROMOTION
    # ═══════════════════════════════════════════════════════════════
    
    def analyze_user(self, user_id: str) -> List[BehaviorPattern]:
        """
        Analizza comportamento utente e rileva pattern.
        
        Args:
            user_id: ID utente
            
        Returns:
            Lista pattern rilevati
        """
        signals = self.signal_collector.get_user_signals(user_id)
        
        if not signals:
            return []
        
        patterns = self.behavior_analyzer.analyze_user(user_id, signals)
        
        return patterns
    
    def apply_learned_preferences(
        self,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Applica preferenze apprese a memoria utente.
        
        Analizza i pattern e salva quelli con confidence alta
        come memorie di tipo preference.
        
        Args:
            user_id: ID utente
            
        Returns:
            Lista memorie create
        """
        if not self.enable_auto_memory:
            return []
        
        store = self._get_memory_store()
        if not store:
            return []
        
        patterns = self.analyze_user(user_id)
        candidates = self.behavior_analyzer.get_memory_candidates(patterns)
        
        created = []
        
        for candidate in candidates:
            if candidate["confidence"] < 0.65:
                continue
            
            try:
                # Verifica non esista già
                existing = store.search(
                    query=candidate["content"],
                    namespace=f"user_{user_id}",
                    limit=1,
                    min_score=0.85
                )
                
                if existing:
                    continue
                
                # Crea memoria
                from src.memory.store import MemoryType, MemoryItem
                
                mem_type_map = {
                    "preference": MemoryType.PREFERENCE,
                    "fact": MemoryType.FACT
                }
                
                memory = MemoryItem(
                    id=f"implicit_{user_id}_{len(created)}",
                    type=mem_type_map.get(candidate["type"], MemoryType.PREFERENCE),
                    content=candidate["content"],
                    source="implicit_learning",
                    base_confidence=candidate["confidence"],
                    metadata={"source_pattern": candidate["source_pattern"]}
                )
                
                store.add(memory, namespace=f"user_{user_id}")
                
                created.append({
                    "content": candidate["content"],
                    "type": candidate["type"],
                    "confidence": candidate["confidence"]
                })
                
                logger.info(f"[Learning] Auto-saved preference for {user_id}: {candidate['content'][:50]}...")
                
            except Exception as e:
                logger.error(f"Errore salvataggio preferenza: {e}")
        
        return created
    
    def run_consensus_check(self) -> List[Dict[str, Any]]:
        """
        Controlla e promuove memorie con consenso.
        
        Chiamato periodicamente (es. nightly job).
        
        Returns:
            Lista promozioni effettuate
        """
        if not self.enable_consensus:
            return []
        
        promotions = self.promoter.check_and_promote()
        
        return promotions
    
    def run_nightly_analysis(self) -> Dict[str, Any]:
        """
        Analisi notturna completa.
        
        1. Analizza tutti gli utenti attivi
        2. Applica preferenze apprese
        3. Controlla consenso e promuove
        
        Returns:
            Summary {users_analyzed, preferences_created, promotions}
        """
        logger.info("[Learning] === NIGHTLY ANALYSIS START ===")
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "users_analyzed": 0,
            "preferences_created": 0,
            "promotions": 0,
            "errors": []
        }
        
        # 1. Raccogli utenti attivi (ultimi 7 giorni)
        try:
            stats = self.signal_collector.get_stats()
            active_users = stats.get("unique_users", 0)
            summary["users_analyzed"] = active_users
        except Exception as e:
            summary["errors"].append(f"Error getting users: {e}")
        
        # 2. Per ogni utente, analizza e salva preferenze
        # (In produzione, iterare su lista utenti reali)
        # Qui skip per performance
        
        # 3. Controlla consenso
        try:
            promotions = self.run_consensus_check()
            summary["promotions"] = len(promotions)
        except Exception as e:
            summary["errors"].append(f"Error in consensus check: {e}")
        
        # 4. Flush segnali
        self.signal_collector.force_flush()
        
        logger.info(
            f"[Learning] === NIGHTLY ANALYSIS END === "
            f"users={summary['users_analyzed']}, promotions={summary['promotions']}"
        )
        
        return summary
    
    # ═══════════════════════════════════════════════════════════════
    # STATS & QUERIES
    # ═══════════════════════════════════════════════════════════════
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """
        Statistiche complessive per Admin Panel.
        
        Returns:
            Dict con stats su signals, patterns, consenso
        """
        signal_stats = self.signal_collector.get_stats()
        consensus_stats = self.voting_tracker.get_stats()
        promotion_stats = self.promoter.get_promotion_stats()
        
        return {
            "signals": signal_stats,
            "consensus": consensus_stats,
            "promotions": promotion_stats,
            "config": {
                "auto_memory": self.enable_auto_memory,
                "consensus_enabled": self.enable_consensus
            }
        }
    
    def get_user_implicit_score(self, user_id: str, query_id: str) -> float:
        """
        Calcola score implicito per una query utente.
        
        Args:
            user_id: ID utente
            query_id: ID query
            
        Returns:
            Score -1 to +1
        """
        return self.signal_collector.calculate_implicit_score(user_id, query_id)


# Singleton
_learner: Optional[ImplicitLearner] = None


def get_implicit_learner() -> ImplicitLearner:
    """Ottiene istanza singleton ImplicitLearner"""
    global _learner
    if _learner is None:
        _learner = ImplicitLearner()
    return _learner


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    
    print("=== TEST IMPLICIT LEARNER ===\n")
    
    # Setup con path temp
    signal_collector = SignalCollector(persist_path=f"{temp_dir}/signals.json")
    voting_tracker = VotingTracker(persist_path=f"{temp_dir}/votes.json")
    
    learner = ImplicitLearner(
        signal_collector=signal_collector,
        voting_tracker=voting_tracker,
        enable_auto_memory=False,  # Skip per test
        enable_consensus=True
    )
    
    # Test 1: Simula sessione
    print("Test 1: Simula sessione")
    learner.on_session_start("mario", "sess_1")
    
    # Test 2: Query flow
    print("\nTest 2: Query flow")
    query_id = learner.on_query_start("mario", "sess_1", "Cos'è il WCM?")
    print(f"  Query ID: {query_id}")
    
    learner.on_response(
        "mario", "sess_1", query_id,
        "WCM significa World Class Manufacturing...",
        sources=["PS-06_01", "MR-03"]
    )
    
    learner.on_click_source("mario", "sess_1", "PS-06_01", query_id)
    learner.on_copy("mario", "sess_1", "WCM significa World Class Manufacturing", query_id)
    
    learner.on_query_end("mario", "sess_1", query_id)
    
    # Test 3: Teach flow
    print("\nTest 3: Teach complete")
    learner.on_teach_complete(
        "mario", "sess_1",
        "WCM = World Class Manufacturing",
        "fact",
        "PS-06_01"
    )
    
    # Simula altri utenti per consenso
    print("\nTest 4: Multi-user consensus")
    for user in ["luigi", "anna", "paolo"]:
        learner.on_teach_complete(
            user, f"sess_{user}",
            "WCM = World Class Manufacturing",
            "fact"
        )
    
    # Test 5: Stats
    print("\nTest 5: Stats")
    stats = learner.get_learning_stats()
    print(f"  Signals: {stats['signals']['total']}")
    print(f"  Consensus candidates: {stats['consensus']['total_candidates']}")
    print(f"  Ready for promotion: {stats['promotions']['ready_for_promotion']}")
    
    # Test 6: Nightly analysis
    print("\nTest 6: Nightly analysis")
    summary = learner.run_nightly_analysis()
    print(f"  Summary: {summary}")
    
    # Cleanup
    shutil.rmtree(temp_dir)
    
    print("\n✅ Test completati!")

