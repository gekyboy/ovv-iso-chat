"""
Learning Scheduler per R08-R10
Schedulazione analisi notturne e cleanup

Created: 2025-12-08

Jobs:
- Nightly analysis: 03:00 AM
- Consensus check: 04:00 AM
- Signal cleanup: 05:00 AM (retention 30 giorni)
"""

import logging
from datetime import datetime
from typing import Optional

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    logging.warning("APScheduler non installato, scheduler disabilitato")

logger = logging.getLogger(__name__)


class LearningScheduler:
    """
    Scheduler per job di apprendimento.
    
    Jobs schedulati:
    - Nightly analysis: analisi comportamento utenti
    - Consensus check: promozione memorie con consenso
    - Signal cleanup: pulizia dati vecchi
    
    Example:
        >>> scheduler = LearningScheduler()
        >>> scheduler.start()
        >>> # ...
        >>> scheduler.stop()
    """
    
    def __init__(
        self,
        nightly_hour: int = 3,
        consensus_hour: int = 4,
        cleanup_hour: int = 5
    ):
        """
        Inizializza scheduler.
        
        Args:
            nightly_hour: Ora per analisi notturna (default 3:00)
            consensus_hour: Ora per consensus check (default 4:00)
            cleanup_hour: Ora per cleanup (default 5:00)
        """
        self.nightly_hour = nightly_hour
        self.consensus_hour = consensus_hour
        self.cleanup_hour = cleanup_hour
        
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._running = False
        
        if SCHEDULER_AVAILABLE:
            self._scheduler = AsyncIOScheduler()
            self._setup_jobs()
            logger.info("LearningScheduler inizializzato")
        else:
            logger.warning("LearningScheduler: APScheduler non disponibile")
    
    def _setup_jobs(self):
        """Configura jobs schedulati"""
        if not self._scheduler:
            return
        
        # Job 1: Nightly Analysis
        self._scheduler.add_job(
            self._run_nightly_analysis,
            CronTrigger(hour=self.nightly_hour, minute=0),
            id="learning_nightly",
            name="Learning Nightly Analysis",
            replace_existing=True
        )
        
        # Job 2: Consensus Check
        self._scheduler.add_job(
            self._run_consensus_check,
            CronTrigger(hour=self.consensus_hour, minute=0),
            id="learning_consensus",
            name="Learning Consensus Check",
            replace_existing=True
        )
        
        # Job 3: Signal Cleanup
        self._scheduler.add_job(
            self._run_cleanup,
            CronTrigger(hour=self.cleanup_hour, minute=0),
            id="learning_cleanup",
            name="Learning Signal Cleanup",
            replace_existing=True
        )
        
        logger.info(
            f"Jobs configurati: nightly@{self.nightly_hour}:00, "
            f"consensus@{self.consensus_hour}:00, cleanup@{self.cleanup_hour}:00"
        )
    
    async def _run_nightly_analysis(self):
        """Esegue analisi notturna"""
        logger.info("[LearningScheduler] === NIGHTLY ANALYSIS START ===")
        
        try:
            from .learners import get_implicit_learner
            learner = get_implicit_learner()
            
            summary = learner.run_nightly_analysis()
            
            logger.info(
                f"[LearningScheduler] Nightly analysis completata: "
                f"users={summary.get('users_analyzed', 0)}, "
                f"promotions={summary.get('promotions', 0)}"
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"[LearningScheduler] Errore nightly analysis: {e}")
            return {"error": str(e)}
    
    async def _run_consensus_check(self):
        """Esegue check consenso e promozioni"""
        logger.info("[LearningScheduler] === CONSENSUS CHECK START ===")
        
        try:
            from .learners import get_implicit_learner
            learner = get_implicit_learner()
            
            promotions = learner.run_consensus_check()
            
            logger.info(f"[LearningScheduler] Consensus check: {len(promotions)} promozioni")
            
            return {"promotions": len(promotions)}
            
        except Exception as e:
            logger.error(f"[LearningScheduler] Errore consensus check: {e}")
            return {"error": str(e)}
    
    async def _run_cleanup(self):
        """Esegue cleanup segnali vecchi"""
        logger.info("[LearningScheduler] === CLEANUP START ===")
        
        try:
            from .signals import get_signal_collector
            collector = get_signal_collector()
            
            collector.force_flush()
            
            logger.info("[LearningScheduler] Cleanup completato")
            
            return {"status": "completed"}
            
        except Exception as e:
            logger.error(f"[LearningScheduler] Errore cleanup: {e}")
            return {"error": str(e)}
    
    def start(self):
        """Avvia scheduler"""
        if not self._scheduler:
            logger.warning("Scheduler non disponibile")
            return
        
        if not self._running:
            self._scheduler.start()
            self._running = True
            logger.info("[LearningScheduler] Avviato")
    
    def stop(self):
        """Ferma scheduler"""
        if self._scheduler and self._running:
            self._scheduler.shutdown()
            self._running = False
            logger.info("[LearningScheduler] Fermato")
    
    def is_running(self) -> bool:
        """Verifica se scheduler è attivo"""
        return self._running
    
    def get_next_runs(self) -> dict:
        """Ottiene prossime esecuzioni"""
        if not self._scheduler:
            return {}
        
        jobs = {}
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            jobs[job.name] = next_run.isoformat() if next_run else None
        
        return jobs
    
    def run_now(self, job_name: str):
        """
        Esegue job immediatamente.
        
        Args:
            job_name: "nightly", "consensus", o "cleanup"
        """
        import asyncio
        
        job_map = {
            "nightly": self._run_nightly_analysis,
            "consensus": self._run_consensus_check,
            "cleanup": self._run_cleanup
        }
        
        func = job_map.get(job_name)
        if not func:
            logger.warning(f"Job sconosciuto: {job_name}")
            return None
        
        # Esegui in modo sincrono
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Già in loop async
            return asyncio.create_task(func())
        else:
            return loop.run_until_complete(func())


# Singleton
_scheduler: Optional[LearningScheduler] = None


def get_learning_scheduler() -> LearningScheduler:
    """Ottiene istanza singleton LearningScheduler"""
    global _scheduler
    if _scheduler is None:
        _scheduler = LearningScheduler()
    return _scheduler

