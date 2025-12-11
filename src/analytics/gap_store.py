"""
Gap Store per OVV ISO Chat
Persistenza segnalazioni lacune per review Admin

R19 - Segnalazione Lacune Intelligente
Created: 2025-12-08

Usa file JSON dedicato per persistenza indipendente.
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class GapReport:
    """Segnalazione lacuna da utente"""
    id: str
    term: str                     # Termine mancante
    query_original: str           # Query che ha generato la lacuna
    found_in_docs: List[str]      # Doc dove appare il termine
    snippets: List[str] = field(default_factory=list)  # Snippet di contesto
    reported_by: str = ""         # user_id primo utente
    reported_at: str = ""         # ISO timestamp
    report_count: int = 1         # Quanti utenti hanno segnalato
    reporters: List[str] = field(default_factory=list)  # Lista user_id
    status: str = "pending"       # pending, added, rejected
    admin_note: Optional[str] = None
    resolved_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializza per JSON"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GapReport":
        """Deserializza da JSON"""
        return cls(**data)


class GapStore:
    """
    Store per segnalazioni lacune.
    
    Features:
    - Persistenza JSON indipendente
    - Deduplicazione per termine
    - Incremento conteggio se già segnalato
    - Query per Admin (pending, stats, etc.)
    
    Example:
        >>> store = GapStore()
        >>> report = store.report_gap("WCM", "Cos'è WCM?", ["PS-06_01"], "user_1")
        >>> print(f"Segnalato: {report.term} ({report.report_count} volte)")
    """
    
    def __init__(
        self,
        persist_path: str = "data/persist/gap_reports.json",
        auto_save: bool = True
    ):
        """
        Inizializza store.
        
        Args:
            persist_path: Path file JSON persistenza
            auto_save: Salva automaticamente dopo ogni modifica
        """
        self.persist_path = Path(persist_path)
        self.auto_save = auto_save
        
        # Cache in memoria
        self._reports: Dict[str, GapReport] = {}
        
        # Crea directory se non esiste
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Carica dati esistenti
        self._load()
        
        logger.info(f"GapStore inizializzato: {len(self._reports)} report caricati")
    
    def _load(self):
        """Carica report da file"""
        if not self.persist_path.exists():
            return
        
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for gap_id, report_data in data.items():
                self._reports[gap_id] = GapReport.from_dict(report_data)
            
            logger.debug(f"Caricati {len(self._reports)} gap report")
            
        except Exception as e:
            logger.error(f"Errore caricamento gap reports: {e}")
    
    def _save(self):
        """Salva report su file"""
        try:
            data = {
                gap_id: report.to_dict()
                for gap_id, report in self._reports.items()
            }
            
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Salvati {len(self._reports)} gap report")
            
        except Exception as e:
            logger.error(f"Errore salvataggio gap reports: {e}")
    
    def _generate_id(self, term: str) -> str:
        """Genera ID univoco basato su termine (dedup)"""
        term_normalized = term.lower().strip()
        hash_value = hashlib.md5(term_normalized.encode()).hexdigest()[:12]
        return f"gap_{hash_value}"
    
    def report_gap(
        self,
        term: str,
        query: str,
        found_in_docs: List[str],
        user_id: str,
        snippets: Optional[List[str]] = None
    ) -> GapReport:
        """
        Segnala o aggiorna lacuna.
        
        Se termine già segnalato, incrementa contatore.
        Se nuovo, crea report.
        
        Args:
            term: Termine mancante
            query: Query originale
            found_in_docs: Documenti dove appare
            user_id: ID utente che segnala
            snippets: Snippet di contesto (opzionale)
            
        Returns:
            GapReport creato o aggiornato
        """
        gap_id = self._generate_id(term)
        
        existing = self._reports.get(gap_id)
        
        if existing:
            # Incrementa contatore
            existing.report_count += 1
            
            # Aggiungi user se non già presente
            if user_id not in existing.reporters:
                existing.reporters.append(user_id)
            
            # Aggiungi documenti non già presenti
            for doc in found_in_docs:
                if doc not in existing.found_in_docs:
                    existing.found_in_docs.append(doc)
            
            # Aggiungi snippet non già presenti
            if snippets:
                for snippet in snippets:
                    if snippet not in existing.snippets:
                        existing.snippets.append(snippet)
            
            logger.info(f"[Gap] Aggiornato report '{term}': {existing.report_count} segnalazioni")
            
            if self.auto_save:
                self._save()
            
            return existing
        
        # Nuovo report
        report = GapReport(
            id=gap_id,
            term=term.upper(),
            query_original=query,
            found_in_docs=found_in_docs,
            snippets=snippets or [],
            reported_by=user_id,
            reported_at=datetime.now().isoformat(),
            report_count=1,
            reporters=[user_id],
            status="pending"
        )
        
        self._reports[gap_id] = report
        
        logger.info(f"[Gap] Nuovo report: '{term}' da {user_id}")
        
        if self.auto_save:
            self._save()
        
        return report
    
    def get(self, gap_id: str) -> Optional[GapReport]:
        """Ottiene report per ID"""
        return self._reports.get(gap_id)
    
    def get_by_term(self, term: str) -> Optional[GapReport]:
        """Ottiene report per termine"""
        gap_id = self._generate_id(term)
        return self._reports.get(gap_id)
    
    def get_pending(self, limit: int = 20) -> List[GapReport]:
        """
        Ritorna segnalazioni pending ordinate per conteggio.
        
        Args:
            limit: Massimo risultati
            
        Returns:
            Lista ordinata per priorità (report_count desc)
        """
        pending = [
            r for r in self._reports.values()
            if r.status == "pending"
        ]
        
        # Ordina per conteggio (più segnalato = priorità più alta)
        pending.sort(key=lambda x: x.report_count, reverse=True)
        
        return pending[:limit]
    
    def get_all(self, status: Optional[str] = None) -> List[GapReport]:
        """
        Ritorna tutti i report, opzionalmente filtrati per status.
        
        Args:
            status: "pending", "added", "rejected" o None per tutti
        """
        if status:
            return [r for r in self._reports.values() if r.status == status]
        return list(self._reports.values())
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Statistiche per Admin dashboard.
        
        Returns:
            Dict con conteggi e top termini
        """
        reports = list(self._reports.values())
        
        stats = {
            "total": len(reports),
            "pending": len([r for r in reports if r.status == "pending"]),
            "added": len([r for r in reports if r.status == "added"]),
            "rejected": len([r for r in reports if r.status == "rejected"]),
            "total_reports": sum(r.report_count for r in reports),
            "top_pending": [],
            "recent": []
        }
        
        # Top pending per conteggio
        pending = [r for r in reports if r.status == "pending"]
        pending.sort(key=lambda x: x.report_count, reverse=True)
        stats["top_pending"] = [
            {"term": r.term, "count": r.report_count, "docs": r.found_in_docs[:3]}
            for r in pending[:10]
        ]
        
        # Più recenti
        reports.sort(key=lambda x: x.reported_at, reverse=True)
        stats["recent"] = [
            {"term": r.term, "status": r.status, "date": r.reported_at[:10]}
            for r in reports[:5]
        ]
        
        return stats
    
    def mark_added(self, gap_id: str, admin_note: str = "") -> bool:
        """
        Admin ha aggiunto termine al glossario.
        
        Args:
            gap_id: ID report
            admin_note: Nota opzionale
            
        Returns:
            True se aggiornato
        """
        report = self._reports.get(gap_id)
        if not report:
            return False
        
        report.status = "added"
        report.admin_note = admin_note
        report.resolved_at = datetime.now().isoformat()
        
        logger.info(f"[Gap] Marcato come aggiunto: {report.term}")
        
        if self.auto_save:
            self._save()
        
        return True
    
    def mark_rejected(self, gap_id: str, admin_note: str) -> bool:
        """
        Admin ha rifiutato la segnalazione.
        
        Args:
            gap_id: ID report
            admin_note: Motivazione rifiuto (obbligatoria)
            
        Returns:
            True se aggiornato
        """
        report = self._reports.get(gap_id)
        if not report:
            return False
        
        report.status = "rejected"
        report.admin_note = admin_note
        report.resolved_at = datetime.now().isoformat()
        
        logger.info(f"[Gap] Marcato come rifiutato: {report.term}")
        
        if self.auto_save:
            self._save()
        
        return True
    
    def delete(self, gap_id: str) -> bool:
        """Elimina report"""
        if gap_id in self._reports:
            del self._reports[gap_id]
            
            if self.auto_save:
                self._save()
            
            return True
        return False
    
    def clear_all(self):
        """Elimina tutti i report (per test)"""
        self._reports.clear()
        
        if self.auto_save:
            self._save()


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    # Usa path temporaneo per test
    import tempfile
    temp_dir = tempfile.mkdtemp()
    test_path = f"{temp_dir}/gap_reports_test.json"
    
    print("=== TEST GAP STORE ===\n")
    
    store = GapStore(persist_path=test_path)
    
    # Test 1: Nuovo report
    print("Test 1: Nuovo report")
    report = store.report_gap(
        term="WCM",
        query="Cos'è WCM?",
        found_in_docs=["PS-06_01", "IL-07_02"],
        user_id="user_1",
        snippets=["...strumenti WCM per..."]
    )
    print(f"  ID: {report.id}")
    print(f"  Term: {report.term}")
    print(f"  Count: {report.report_count}")
    print()
    
    # Test 2: Report duplicato (incrementa)
    print("Test 2: Report duplicato")
    report2 = store.report_gap(
        term="wcm",  # Lowercase, dovrebbe matchare
        query="Che significa WCM?",
        found_in_docs=["MR-08_01"],
        user_id="user_2"
    )
    print(f"  Count dopo duplicato: {report2.report_count}")
    print(f"  Reporters: {report2.reporters}")
    print(f"  Docs: {report2.found_in_docs}")
    print()
    
    # Test 3: Altro report
    print("Test 3: Altro report")
    report3 = store.report_gap(
        term="FMEA",
        query="Definizione di FMEA",
        found_in_docs=["MR-08_07"],
        user_id="user_1"
    )
    print(f"  Term: {report3.term}")
    print()
    
    # Test 4: Get pending
    print("Test 4: Get pending")
    pending = store.get_pending()
    for p in pending:
        print(f"  - {p.term} ({p.report_count} segnalazioni)")
    print()
    
    # Test 5: Stats
    print("Test 5: Stats")
    stats = store.get_stats()
    print(f"  Total: {stats['total']}")
    print(f"  Pending: {stats['pending']}")
    print(f"  Top pending: {stats['top_pending']}")
    print()
    
    # Test 6: Mark added
    print("Test 6: Mark added")
    store.mark_added(report.id, "Aggiunto al glossario")
    updated = store.get(report.id)
    print(f"  Status: {updated.status}")
    print(f"  Note: {updated.admin_note}")
    print()
    
    # Test 7: Persistenza
    print("Test 7: Persistenza")
    store2 = GapStore(persist_path=test_path)
    print(f"  Reports caricati: {len(store2.get_all())}")
    
    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)
    
    print("\n✅ Tutti i test completati!")

