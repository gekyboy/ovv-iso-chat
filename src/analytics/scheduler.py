"""
Analytics Scheduler per R07
Task schedulati per report automatici

R07 - Sistema Analytics
Created: 2025-12-08

Jobs:
- Report notturno alle 02:00
- Cleanup dati vecchi settimanale
- Raccolta metriche ogni 5 minuti (opzionale)
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Flag per APScheduler (opzionale)
_scheduler_available = False
_scheduler_instance = None

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _scheduler_available = True
except ImportError:
    logger.warning("APScheduler non installato. Scheduler disabilitato.")
    BackgroundScheduler = None
    CronTrigger = None


class AnalyticsScheduler:
    """
    Scheduler per task analytics automatici.
    
    Features:
    - Report notturno giornaliero
    - Cleanup dati vecchi
    - Graceful degradation se APScheduler non installato
    
    Example:
        >>> scheduler = AnalyticsScheduler()
        >>> scheduler.start()
        >>> # ... app running ...
        >>> scheduler.stop()
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Inizializza scheduler.
        
        Args:
            config: Configurazione opzionale
        """
        self.config = config or {}
        self.scheduler = None
        self.is_running = False
        
        if _scheduler_available:
            self.scheduler = BackgroundScheduler()
            logger.info("AnalyticsScheduler inizializzato")
        else:
            logger.warning("AnalyticsScheduler: APScheduler non disponibile")
    
    def start(self):
        """Avvia scheduler con job configurati"""
        if not _scheduler_available or self.scheduler is None:
            logger.warning("Cannot start scheduler: APScheduler not available")
            return False
        
        if self.is_running:
            logger.warning("Scheduler già in esecuzione")
            return True
        
        try:
            # Job 1: Report notturno alle 02:00
            self.scheduler.add_job(
                self.generate_nightly_report,
                CronTrigger(hour=2, minute=0),
                id='nightly_report',
                replace_existing=True,
                name='Nightly Analytics Report'
            )
            
            # Job 2: Cleanup settimanale (domenica 03:00)
            self.scheduler.add_job(
                self.cleanup_old_data,
                CronTrigger(day_of_week='sun', hour=3, minute=0),
                id='weekly_cleanup',
                replace_existing=True,
                name='Weekly Data Cleanup'
            )
            
            self.scheduler.start()
            self.is_running = True
            
            logger.info("Analytics scheduler avviato con 2 job")
            return True
            
        except Exception as e:
            logger.error(f"Errore avvio scheduler: {e}")
            return False
    
    def stop(self):
        """Ferma scheduler"""
        if self.scheduler and self.is_running:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("Analytics scheduler fermato")
    
    def generate_nightly_report(self):
        """
        Genera report notturno completo.
        
        Eseguito automaticamente alle 02:00.
        """
        logger.info("=== Inizio generazione report notturno ===")
        
        try:
            # Import qui per evitare circular import
            from .collectors import (
                QueryCollector,
                GlossaryCollector,
                MemoryCollector,
                PipelineCollector
            )
            from .analyzers import (
                UsageAnalyzer,
                QualityAnalyzer,
                ReportGenerator
            )
            
            # 1. Raccogli dati
            logger.info("[1/4] Raccolta dati...")
            
            query_collector = QueryCollector()
            glossary_collector = GlossaryCollector()
            memory_collector = MemoryCollector()
            pipeline_collector = PipelineCollector()
            
            # Query logs degli ultimi 7 giorni
            query_logs = query_collector.get_logs_last_n_days(7)
            
            # 2. Analizza
            logger.info("[2/4] Analisi dati...")
            
            usage_analyzer = UsageAnalyzer()
            quality_analyzer = QualityAnalyzer()
            
            usage_report = usage_analyzer.generate_report(query_logs)
            quality_report = quality_analyzer.generate_report(query_logs)
            glossary_stats = glossary_collector.get_stats()
            memory_stats = memory_collector.get_stats()
            pipeline_stats = pipeline_collector.get_stats()
            
            # 3. Componi dati report
            date_str = datetime.now().strftime("%Y-%m-%d")
            
            report_data = {
                "date": date_str,
                "usage": usage_report,
                "quality": quality_report,
                "glossary": glossary_stats,
                "memory": memory_stats,
                "pipeline": pipeline_stats
            }
            
            # 4. Genera e salva report
            logger.info("[3/4] Generazione report...")
            
            generator = ReportGenerator()
            
            # Markdown
            md_content = generator.generate_daily_markdown(report_data)
            md_path = generator.save_report(md_content, f"daily_{date_str}", "md")
            
            # HTML
            html_content = generator.generate_daily_html(report_data)
            html_path = generator.save_report(html_content, f"daily_{date_str}", "html")
            
            logger.info(f"[4/4] Report salvati:")
            logger.info(f"  - Markdown: {md_path}")
            logger.info(f"  - HTML: {html_path}")
            
            logger.info("=== Report notturno completato ===")
            
            return {
                "success": True,
                "date": date_str,
                "md_path": str(md_path),
                "html_path": str(html_path)
            }
            
        except Exception as e:
            logger.error(f"Errore generazione report: {e}")
            return {"success": False, "error": str(e)}
    
    def cleanup_old_data(self, days_retention: int = 90):
        """
        Pulisce dati vecchi.
        
        Args:
            days_retention: Giorni di retention (default 90)
        """
        logger.info(f"=== Cleanup dati più vecchi di {days_retention} giorni ===")
        
        try:
            from .collectors import QueryCollector
            
            collector = QueryCollector()
            collector.cleanup_old_logs()
            
            # Cleanup vecchi report
            reports_dir = Path("data/reports")
            if reports_dir.exists():
                from datetime import timedelta
                cutoff = datetime.now() - timedelta(days=days_retention)
                
                removed = 0
                for f in reports_dir.glob("daily_*"):
                    try:
                        file_date = datetime.strptime(f.stem.replace("daily_", ""), "%Y-%m-%d")
                        if file_date < cutoff:
                            f.unlink()
                            removed += 1
                    except Exception:
                        pass
                
                if removed > 0:
                    logger.info(f"Rimossi {removed} report vecchi")
            
            logger.info("=== Cleanup completato ===")
            
        except Exception as e:
            logger.error(f"Errore cleanup: {e}")
    
    def run_now(self, job_id: str) -> Dict[str, Any]:
        """
        Esegue un job immediatamente.
        
        Args:
            job_id: "nightly_report" o "weekly_cleanup"
            
        Returns:
            Risultato esecuzione
        """
        if job_id == "nightly_report":
            return self.generate_nightly_report()
        elif job_id == "weekly_cleanup":
            self.cleanup_old_data()
            return {"success": True, "job": "cleanup"}
        else:
            return {"success": False, "error": f"Job sconosciuto: {job_id}"}
    
    def get_status(self) -> Dict[str, Any]:
        """Stato corrente scheduler"""
        if not _scheduler_available:
            return {
                "available": False,
                "running": False,
                "jobs": []
            }
        
        jobs = []
        if self.scheduler:
            for job in self.scheduler.get_jobs():
                jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None
                })
        
        return {
            "available": True,
            "running": self.is_running,
            "jobs": jobs
        }


# Singleton
def get_scheduler() -> AnalyticsScheduler:
    """Ottiene istanza singleton scheduler"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = AnalyticsScheduler()
    return _scheduler_instance


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("=== TEST ANALYTICS SCHEDULER ===\n")
    
    scheduler = AnalyticsScheduler()
    
    # Test 1: Status
    print("Test 1: Status")
    status = scheduler.get_status()
    print(f"  Available: {status['available']}")
    print(f"  Running: {status['running']}")
    print()
    
    if status['available']:
        # Test 2: Start
        print("Test 2: Start scheduler")
        started = scheduler.start()
        print(f"  Started: {started}")
        
        status = scheduler.get_status()
        print(f"  Jobs: {len(status['jobs'])}")
        for job in status['jobs']:
            print(f"    - {job['id']}: next={job['next_run']}")
        print()
        
        # Test 3: Run report manually
        print("Test 3: Generate report manually")
        result = scheduler.run_now("nightly_report")
        print(f"  Success: {result.get('success')}")
        if result.get('success'):
            print(f"  MD: {result.get('md_path')}")
            print(f"  HTML: {result.get('html_path')}")
        print()
        
        # Test 4: Stop
        print("Test 4: Stop scheduler")
        scheduler.stop()
        print(f"  Stopped: {not scheduler.is_running}")
    else:
        print("APScheduler non disponibile - installa con: pip install apscheduler")
    
    print("\n✅ Test completati!")

