"""
Global Promoter per R08-R10
Promuove memorie da namespace utente a globale quando raggiungono consenso

Created: 2025-12-08

Flow:
1. VotingTracker identifica candidati pronti
2. Promoter verifica qualità
3. Se OK, aggiunge a namespace global (o pending_global)
4. Notifica Admin per revisione (opzionale)
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .voting_tracker import VotingTracker, ConsensusCandidate

logger = logging.getLogger(__name__)


class GlobalPromoter:
    """
    Promuove memorie da namespace utente a globale.
    
    Features:
    - Validazione qualità contenuto
    - Opzione approvazione Admin
    - Prevenzione duplicati
    - Logging promozioni
    
    Example:
        >>> promoter = GlobalPromoter(voting_tracker)
        >>> promotions = promoter.check_and_promote()
        >>> print(f"Promossi: {len(promotions)}")
    """
    
    def __init__(
        self,
        voting_tracker: VotingTracker,
        memory_store=None,  # Lazy load
        require_admin_approval: bool = True
    ):
        """
        Inizializza promoter.
        
        Args:
            voting_tracker: Istanza VotingTracker
            memory_store: Istanza MemoryStore (o lazy load)
            require_admin_approval: Se True, mette in pending_global invece di global
        """
        self.voting_tracker = voting_tracker
        self._memory_store = memory_store
        self.require_admin_approval = require_admin_approval
        
        logger.info(f"GlobalPromoter: admin_approval={require_admin_approval}")
    
    def _get_memory_store(self):
        """Lazy load memory store"""
        if self._memory_store is None:
            try:
                from src.memory.store import get_memory_store
                self._memory_store = get_memory_store()
            except ImportError:
                logger.warning("MemoryStore non disponibile")
                return None
        return self._memory_store
    
    def check_and_promote(self) -> List[Dict[str, Any]]:
        """
        Controlla candidati e promuove quelli pronti.
        
        Returns:
            Lista promozioni effettuate [{content, type, namespace, voters, score, timestamp}]
        """
        candidates = self.voting_tracker.get_promotion_candidates()
        
        if not candidates:
            logger.debug("[Promoter] Nessun candidato pronto")
            return []
        
        promotions = []
        
        for candidate in candidates:
            result = self._process_candidate(candidate)
            if result:
                promotions.append(result)
        
        if promotions:
            logger.info(f"[Promoter] {len(promotions)} promozioni processate")
        
        return promotions
    
    def _process_candidate(
        self,
        candidate: ConsensusCandidate
    ) -> Optional[Dict[str, Any]]:
        """
        Processa singolo candidato per promozione.
        
        Args:
            candidate: Candidato da processare
            
        Returns:
            Dict con dettagli promozione o None se fallita
        """
        store = self._get_memory_store()
        
        if not store:
            logger.warning("[Promoter] MemoryStore non disponibile")
            return None
        
        # 1. Verifica non esista già in global
        try:
            existing = store.search(
                query=candidate.content,
                namespace="global",
                limit=1,
                min_score=0.85
            )
            
            if existing:
                logger.debug(f"[Promoter] Skip '{candidate.content[:30]}...' - già in global")
                self.voting_tracker.mark_promoted(candidate.content_hash)
                return None
        except Exception as e:
            logger.warning(f"[Promoter] Errore ricerca global: {e}")
        
        # 2. Verifica qualità contenuto
        if not self._validate_content(candidate):
            logger.debug(f"[Promoter] Skip '{candidate.content[:30]}...' - validazione fallita")
            return None
        
        # 3. Determina namespace target
        if self.require_admin_approval:
            target_namespace = "pending_global"
        else:
            target_namespace = "global"
        
        # 4. Crea memoria
        try:
            from src.memory.store import MemoryType, MemoryItem
            
            memory_type_map = {
                "fact": MemoryType.FACT,
                "preference": MemoryType.PREFERENCE,
                "procedure": MemoryType.PROCEDURE
            }
            
            mem_type = memory_type_map.get(candidate.memory_type, MemoryType.FACT)
            
            memory = MemoryItem(
                id=f"consensus_{candidate.content_hash}",
                type=mem_type,
                content=candidate.content,
                source="consensus_promotion",
                base_confidence=min(0.9, candidate.consensus_score),
                metadata={
                    "voters": list(candidate.unique_voters),
                    "voter_count": candidate.voter_count,
                    "consensus_score": candidate.consensus_score,
                    "promoted_at": datetime.now().isoformat(),
                    "original_hash": candidate.content_hash
                }
            )
            
            # 5. Salva
            store.add(memory, namespace=target_namespace)
            
        except ImportError:
            logger.warning("[Promoter] Memory module non disponibile")
            return None
        except Exception as e:
            logger.error(f"[Promoter] Errore creazione memoria: {e}")
            return None
        
        # 6. Marca come promosso
        self.voting_tracker.mark_promoted(candidate.content_hash)
        
        result = {
            "content": candidate.content,
            "type": candidate.memory_type,
            "namespace": target_namespace,
            "voters": candidate.voter_count,
            "score": round(candidate.consensus_score, 3),
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(
            f"[Promoter] Promosso a {target_namespace}: "
            f"'{candidate.content[:40]}...' ({candidate.voter_count} voters)"
        )
        
        return result
    
    def _validate_content(self, candidate: ConsensusCandidate) -> bool:
        """
        Valida qualità contenuto prima di promozione.
        
        Criteri:
        - Lunghezza minima/massima
        - Non troppo generico
        - Non spam/placeholder
        """
        content = candidate.content.strip()
        
        # Lunghezza minima
        if len(content) < 15:
            return False
        
        # Lunghezza massima
        if len(content) > 1000:
            return False
        
        # Non troppo generico
        generic_patterns = [
            "ok", "grazie", "capito", "bene", "perfetto", "va bene",
            "sì", "no", "forse", "non so"
        ]
        if content.lower() in generic_patterns:
            return False
        
        # Deve contenere almeno qualche parola significativa
        words = content.split()
        if len(words) < 3:
            return False
        
        # Non deve essere solo punteggiatura
        alpha_chars = sum(1 for c in content if c.isalpha())
        if alpha_chars / len(content) < 0.5:
            return False
        
        return True
    
    def get_pending_promotions(self) -> List[ConsensusCandidate]:
        """
        Candidati che stanno per essere promossi.
        
        Utile per preview nell'Admin Panel.
        
        Returns:
            Lista candidati pronti
        """
        return self.voting_tracker.get_promotion_candidates()
    
    def force_promote(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """
        Admin forza promozione di un candidato.
        
        Args:
            content_hash: Hash del candidato
            
        Returns:
            Dettagli promozione o None
        """
        candidate = self.voting_tracker.get_candidate(content_hash)
        
        if not candidate:
            logger.warning(f"[Promoter] Candidato non trovato: {content_hash}")
            return None
        
        if candidate.status != "pending":
            logger.warning(f"[Promoter] Candidato non pending: {content_hash}")
            return None
        
        # Override require_admin_approval
        old_setting = self.require_admin_approval
        self.require_admin_approval = False
        
        result = self._process_candidate(candidate)
        
        self.require_admin_approval = old_setting
        
        return result
    
    def reject_candidate(self, content_hash: str, reason: str = "") -> bool:
        """
        Admin rifiuta candidato (rimuove da tracking).
        
        Args:
            content_hash: Hash del candidato
            reason: Motivo del rifiuto
            
        Returns:
            True se rifiutato
        """
        candidate = self.voting_tracker.get_candidate(content_hash)
        
        if not candidate:
            return False
        
        self.voting_tracker.mark_rejected(content_hash, reason)
        logger.info(f"[Promoter] Candidato rifiutato: {content_hash} ({reason})")
        
        return True
    
    def get_promotion_stats(self) -> Dict[str, Any]:
        """
        Statistiche promozioni.
        
        Returns:
            Dict con conteggi e top candidati
        """
        voting_stats = self.voting_tracker.get_stats()
        
        return {
            "pending_candidates": voting_stats["by_status"].get("pending", 0),
            "promoted_total": voting_stats["by_status"].get("promoted", 0),
            "rejected_total": voting_stats["by_status"].get("rejected", 0),
            "ready_for_promotion": voting_stats["ready_for_promotion"],
            "require_admin_approval": self.require_admin_approval,
            "top_candidates": voting_stats["top_candidates"]
        }


# Singleton instance holder
_promoter: Optional[GlobalPromoter] = None


def get_global_promoter(voting_tracker: VotingTracker = None) -> GlobalPromoter:
    """
    Ottiene istanza singleton GlobalPromoter.
    
    Args:
        voting_tracker: VotingTracker da usare (richiesto alla prima chiamata)
    """
    global _promoter
    if _promoter is None:
        if voting_tracker is None:
            voting_tracker = VotingTracker()
        _promoter = GlobalPromoter(voting_tracker)
    return _promoter


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    
    print("=== TEST GLOBAL PROMOTER ===\n")
    
    # Setup
    tracker = VotingTracker(persist_path=f"{temp_dir}/votes.json")
    promoter = GlobalPromoter(tracker, require_admin_approval=False)
    
    # Simula voti con consenso
    print("Test 1: Simula consenso")
    for user in ["mario", "luigi", "anna", "paolo"]:
        tracker.register_vote(
            user,
            "WCM significa World Class Manufacturing",
            "fact",
            0.8,
            evidence=[f"Query utente {user}"]
        )
    
    candidates = tracker.get_promotion_candidates()
    print(f"  Candidati pronti: {len(candidates)}")
    
    # Test promozione (senza MemoryStore reale)
    print("\nTest 2: Check and promote (mock)")
    promotions = promoter.check_and_promote()
    print(f"  Promozioni: {len(promotions)}")
    # Nota: fallirà senza MemoryStore reale
    
    # Test stats
    print("\nTest 3: Stats")
    stats = promoter.get_promotion_stats()
    print(f"  Pending: {stats['pending_candidates']}")
    print(f"  Ready: {stats['ready_for_promotion']}")
    
    # Test force reject
    print("\nTest 4: Force reject")
    if candidates:
        rejected = promoter.reject_candidate(candidates[0].content_hash, "Test rejection")
        print(f"  Rejected: {rejected}")
    
    # Cleanup
    shutil.rmtree(temp_dir)
    
    print("\n✅ Test completati!")

