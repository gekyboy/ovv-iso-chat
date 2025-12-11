"""
Voting Tracker per R08-R10
Traccia voti impliciti degli utenti per consenso multi-utente

Created: 2025-12-08

Un "voto" è registrato quando:
- Utente usa una memoria simile (preferenza)
- Utente conferma un fatto (click source, follow-up positivo)
- Più utenti hanno la stessa correzione/preferenza
"""

import logging
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ImplicitVote:
    """Voto implicito di un utente su un fatto/preferenza"""
    user_id: str
    content_hash: str           # Hash del contenuto (per dedup)
    content_normalized: str     # Contenuto normalizzato
    vote_strength: float        # 0-1 (basato su segnali)
    timestamp: datetime
    evidence: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "content_hash": self.content_hash,
            "content_normalized": self.content_normalized,
            "vote_strength": self.vote_strength,
            "timestamp": self.timestamp.isoformat(),
            "evidence": self.evidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImplicitVote":
        return cls(
            user_id=data["user_id"],
            content_hash=data["content_hash"],
            content_normalized=data["content_normalized"],
            vote_strength=data["vote_strength"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            evidence=data.get("evidence", [])
        )


@dataclass
class ConsensusCandidate:
    """Candidato per promozione a globale"""
    content_hash: str
    content: str
    memory_type: str            # fact, preference, procedure
    
    # Voti
    votes: List[ImplicitVote] = field(default_factory=list)
    unique_voters: Set[str] = field(default_factory=set)
    
    # Score consenso
    consensus_score: float = 0.0
    
    # Timestamps
    first_seen: datetime = None
    last_vote: datetime = None
    
    # Status
    status: str = "pending"     # pending, promoted, rejected
    
    @property
    def voter_count(self) -> int:
        return len(self.unique_voters)
    
    @property
    def avg_vote_strength(self) -> float:
        if not self.votes:
            return 0.0
        return sum(v.vote_strength for v in self.votes) / len(self.votes)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "content": self.content,
            "memory_type": self.memory_type,
            "unique_voters": list(self.unique_voters),
            "consensus_score": self.consensus_score,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_vote": self.last_vote.isoformat() if self.last_vote else None,
            "status": self.status,
            "votes": [v.to_dict() for v in self.votes]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsensusCandidate":
        candidate = cls(
            content_hash=data["content_hash"],
            content=data["content"],
            memory_type=data["memory_type"],
            consensus_score=data.get("consensus_score", 0),
            first_seen=datetime.fromisoformat(data["first_seen"]) if data.get("first_seen") else None,
            last_vote=datetime.fromisoformat(data["last_vote"]) if data.get("last_vote") else None,
            status=data.get("status", "pending")
        )
        candidate.unique_voters = set(data.get("unique_voters", []))
        candidate.votes = [ImplicitVote.from_dict(v) for v in data.get("votes", [])]
        return candidate


class VotingTracker:
    """
    Traccia voti impliciti degli utenti per consenso.
    
    Features:
    - Deduplicazione per contenuto simile
    - Calcolo score consenso weighted
    - Query candidati pronti per promozione
    - Persistenza JSON
    
    Example:
        >>> tracker = VotingTracker()
        >>> tracker.register_vote("mario", "WCM = World Class Manufacturing", "fact", 0.8)
        >>> tracker.register_vote("luigi", "WCM significa World Class Manufacturing", "fact", 0.7)
        >>> candidates = tracker.get_promotion_candidates()
    """
    
    # Soglie per consenso
    MIN_UNIQUE_VOTERS = 3           # Minimo utenti diversi
    MIN_CONSENSUS_SCORE = 0.7       # Score minimo per promozione
    SIMILARITY_THRESHOLD = 0.75    # Soglia similarità contenuto
    
    def __init__(
        self,
        persist_path: str = "data/persist/learning/votes.json"
    ):
        """
        Inizializza tracker.
        
        Args:
            persist_path: Path file persistenza
        """
        self.persist_path = Path(persist_path)
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Candidati in memoria
        self._candidates: Dict[str, ConsensusCandidate] = {}
        
        self._load()
        
        logger.info(f"VotingTracker: {len(self._candidates)} candidati")
    
    def register_vote(
        self,
        user_id: str,
        content: str,
        memory_type: str,
        vote_strength: float,
        evidence: List[str] = None
    ) -> ConsensusCandidate:
        """
        Registra un voto implicito.
        
        Args:
            user_id: ID utente che vota
            content: Contenuto della memoria/fatto
            memory_type: fact, preference, procedure
            vote_strength: Forza del voto (0-1)
            evidence: Evidenze per il voto
            
        Returns:
            ConsensusCandidate aggiornato
        """
        # Normalizza e hash
        content_normalized = self._normalize_content(content)
        
        # Cerca candidato simile esistente
        existing = self._find_similar_candidate(content_normalized)
        
        if existing:
            candidate = existing
        else:
            # Crea nuovo candidato
            content_hash = self._hash_content(content_normalized)
            candidate = ConsensusCandidate(
                content_hash=content_hash,
                content=content,
                memory_type=memory_type,
                first_seen=datetime.now()
            )
            self._candidates[content_hash] = candidate
        
        # Registra voto
        vote = ImplicitVote(
            user_id=user_id,
            content_hash=candidate.content_hash,
            content_normalized=content_normalized,
            vote_strength=vote_strength,
            timestamp=datetime.now(),
            evidence=evidence or []
        )
        
        candidate.votes.append(vote)
        candidate.unique_voters.add(user_id)
        candidate.last_vote = datetime.now()
        
        # Ricalcola score consenso
        candidate.consensus_score = self._calculate_consensus_score(candidate)
        
        self._save()
        
        logger.debug(
            f"[Consensus] Voto: '{content[:30]}...' "
            f"voters={candidate.voter_count} score={candidate.consensus_score:.2f}"
        )
        
        return candidate
    
    def _find_similar_candidate(
        self,
        content_normalized: str
    ) -> Optional[ConsensusCandidate]:
        """
        Trova candidato con contenuto simile.
        
        Args:
            content_normalized: Contenuto normalizzato
            
        Returns:
            Candidato più simile o None
        """
        best_match = None
        best_score = 0.0
        
        for candidate in self._candidates.values():
            if candidate.status != "pending":
                continue
            
            similarity = self._calculate_similarity(
                content_normalized,
                self._normalize_content(candidate.content)
            )
            
            if similarity >= self.SIMILARITY_THRESHOLD and similarity > best_score:
                best_match = candidate
                best_score = similarity
        
        return best_match
    
    def find_similar(
        self,
        content: str,
        threshold: float = None
    ) -> Optional[ConsensusCandidate]:
        """
        API pubblica per trovare candidato simile.
        
        Args:
            content: Contenuto da cercare
            threshold: Soglia similarità (default SIMILARITY_THRESHOLD)
            
        Returns:
            Candidato più simile o None
        """
        threshold = threshold or self.SIMILARITY_THRESHOLD
        content_normalized = self._normalize_content(content)
        
        best_match = None
        best_score = 0.0
        
        for candidate in self._candidates.values():
            similarity = self._calculate_similarity(
                content_normalized,
                self._normalize_content(candidate.content)
            )
            
            if similarity >= threshold and similarity > best_score:
                best_match = candidate
                best_score = similarity
        
        return best_match
    
    def get_promotion_candidates(self) -> List[ConsensusCandidate]:
        """
        Ritorna candidati pronti per promozione a globale.
        
        Criteri:
        - Status == pending
        - Almeno MIN_UNIQUE_VOTERS utenti
        - Consensus score >= MIN_CONSENSUS_SCORE
        
        Returns:
            Lista ordinata per score desc
        """
        ready = []
        
        for candidate in self._candidates.values():
            if candidate.status != "pending":
                continue
            
            if candidate.voter_count >= self.MIN_UNIQUE_VOTERS and \
               candidate.consensus_score >= self.MIN_CONSENSUS_SCORE:
                ready.append(candidate)
        
        # Ordina per score desc
        ready.sort(key=lambda x: x.consensus_score, reverse=True)
        
        return ready
    
    def get_all_candidates(
        self,
        status: str = None
    ) -> List[ConsensusCandidate]:
        """
        Ottiene tutti i candidati.
        
        Args:
            status: Filtra per status (pending, promoted, rejected)
        """
        candidates = list(self._candidates.values())
        
        if status:
            candidates = [c for c in candidates if c.status == status]
        
        return candidates
    
    def get_candidate(self, content_hash: str) -> Optional[ConsensusCandidate]:
        """Ottiene candidato per hash"""
        return self._candidates.get(content_hash)
    
    def mark_promoted(self, content_hash: str):
        """Marca candidato come promosso"""
        if content_hash in self._candidates:
            self._candidates[content_hash].status = "promoted"
            self._save()
            logger.info(f"[Consensus] Marked promoted: {content_hash}")
    
    def mark_rejected(self, content_hash: str, reason: str = ""):
        """Marca candidato come rifiutato"""
        if content_hash in self._candidates:
            self._candidates[content_hash].status = "rejected"
            self._save()
            logger.info(f"[Consensus] Marked rejected: {content_hash} ({reason})")
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistiche per Admin"""
        candidates = list(self._candidates.values())
        
        if not candidates:
            return {
                "total_candidates": 0,
                "ready_for_promotion": 0,
                "by_type": {},
                "by_status": {},
                "avg_voters": 0,
                "top_candidates": []
            }
        
        pending = [c for c in candidates if c.status == "pending"]
        
        return {
            "total_candidates": len(candidates),
            "ready_for_promotion": len(self.get_promotion_candidates()),
            "by_type": {
                t: len([c for c in candidates if c.memory_type == t])
                for t in ["fact", "preference", "procedure"]
            },
            "by_status": {
                s: len([c for c in candidates if c.status == s])
                for s in ["pending", "promoted", "rejected"]
            },
            "avg_voters": sum(c.voter_count for c in pending) / len(pending) if pending else 0,
            "top_candidates": [
                {
                    "content": c.content[:50] + "..." if len(c.content) > 50 else c.content,
                    "type": c.memory_type,
                    "voters": c.voter_count,
                    "score": round(c.consensus_score, 2)
                }
                for c in sorted(pending, key=lambda x: x.consensus_score, reverse=True)[:5]
            ]
        }
    
    # ═══════════════════════════════════════════════════════════════
    # PRIVATE METHODS
    # ═══════════════════════════════════════════════════════════════
    
    def _normalize_content(self, content: str) -> str:
        """Normalizza contenuto per confronto"""
        # Lowercase, strip, normalizza spazi
        normalized = ' '.join(content.lower().strip().split())
        # Rimuovi punteggiatura comune
        for char in ".,;:!?\"'":
            normalized = normalized.replace(char, "")
        return normalized
    
    def _hash_content(self, content: str) -> str:
        """Hash contenuto normalizzato"""
        return f"cons_{hashlib.md5(content.encode()).hexdigest()[:12]}"
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calcola similarità tra due testi.
        Usa Jaccard similarity su token.
        """
        tokens1 = set(text1.split())
        tokens2 = set(text2.split())
        
        if not tokens1 or not tokens2:
            return 0.0
        
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        
        return len(intersection) / len(union)
    
    def _calculate_consensus_score(self, candidate: ConsensusCandidate) -> float:
        """
        Calcola score consenso per candidato.
        
        Formula:
        score = (voter_count_normalized * 0.5) + 
                (avg_vote_strength * 0.3) + 
                (recency_factor * 0.2)
        """
        # Normalizza voter count (1-5+ utenti → 0.2-1.0)
        voter_score = min(1.0, candidate.voter_count / 5)
        
        # Media forza voti
        strength_score = candidate.avg_vote_strength
        
        # Recency factor (voti recenti valgono di più)
        recency_score = 0.5
        if candidate.last_vote:
            days_ago = (datetime.now() - candidate.last_vote).days
            recency_score = max(0.2, 1.0 - (days_ago * 0.05))
        
        return (voter_score * 0.5) + (strength_score * 0.3) + (recency_score * 0.2)
    
    def _load(self):
        """Carica candidati da file"""
        if not self.persist_path.exists():
            return
        
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for item in data:
                candidate = ConsensusCandidate.from_dict(item)
                self._candidates[candidate.content_hash] = candidate
            
            logger.debug(f"Caricati {len(self._candidates)} candidati consenso")
            
        except Exception as e:
            logger.error(f"Errore caricamento votes: {e}")
    
    def _save(self):
        """Salva candidati su file"""
        try:
            data = [c.to_dict() for c in self._candidates.values()]
            
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Errore salvataggio votes: {e}")


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    
    print("=== TEST VOTING TRACKER ===\n")
    
    tracker = VotingTracker(persist_path=f"{temp_dir}/votes.json")
    
    # Test 1: Registra voti
    print("Test 1: Registra voti")
    tracker.register_vote("mario", "WCM significa World Class Manufacturing", "fact", 0.8)
    tracker.register_vote("luigi", "WCM = World Class Manufacturing", "fact", 0.7)
    tracker.register_vote("anna", "World Class Manufacturing è il significato di WCM", "fact", 0.9)
    print(f"  Candidati: {len(tracker._candidates)}")
    
    # Test 2: Voto su contenuto diverso
    print("\nTest 2: Nuovo contenuto")
    tracker.register_vote("mario", "L'utente preferisce risposte brevi", "preference", 0.6)
    print(f"  Candidati totali: {len(tracker._candidates)}")
    
    # Test 3: Stats
    print("\nTest 3: Stats")
    stats = tracker.get_stats()
    print(f"  Total: {stats['total_candidates']}")
    print(f"  Ready: {stats['ready_for_promotion']}")
    print(f"  By type: {stats['by_type']}")
    print(f"  Top candidates:")
    for c in stats['top_candidates']:
        print(f"    - {c['content'][:40]}... ({c['voters']} voters, {c['score']})")
    
    # Test 4: Promotion candidates
    print("\nTest 4: Promotion candidates")
    ready = tracker.get_promotion_candidates()
    print(f"  Ready for promotion: {len(ready)}")
    for c in ready:
        print(f"    - {c.content[:40]}... (score={c.consensus_score:.2f})")
    
    # Test 5: Find similar
    print("\nTest 5: Find similar")
    similar = tracker.find_similar("WCM sta per World Class Manufacturing")
    if similar:
        print(f"  Found: {similar.content[:40]}...")
    else:
        print("  Not found")
    
    # Cleanup
    shutil.rmtree(temp_dir)
    
    print("\n✅ Test completati!")

