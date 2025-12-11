"""
Glossary Collector per R07 Analytics
Monitora utilizzo e copertura del glossario

R07 - Sistema Analytics
Created: 2025-12-08

Metriche raccolte:
- Termini totali e loro utilizzo
- Termini mai usati
- Acronimi non riconosciuti (gap)
- Risoluzione acronimi ambigui
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class GlossaryCollector:
    """
    Collector per statistiche glossario.
    
    Features:
    - Tracking utilizzo termini
    - Identificazione termini mai usati
    - Tracking acronimi non riconosciuti
    - Statistiche risoluzione ambigui
    
    Example:
        >>> collector = GlossaryCollector()
        >>> collector.track_usage(["WCM", "NC", "PDCA"])
        >>> stats = collector.get_stats()
    """
    
    def __init__(
        self,
        glossary_path: str = "config/glossary.json",
        tracking_path: str = "data/persist/analytics/glossary_tracking.json"
    ):
        """
        Inizializza collector.
        
        Args:
            glossary_path: Path al file glossary.json
            tracking_path: Path per persistenza tracking
        """
        self.glossary_path = Path(glossary_path)
        self.tracking_path = Path(tracking_path)
        
        # Cache glossario
        self._glossary: Dict[str, Any] = {}
        
        # Tracking utilizzo (term -> {count, last_used, users})
        self._usage_tracking: Dict[str, Dict[str, Any]] = {}
        
        # Tracking termini non trovati
        self._unknown_terms: Dict[str, Dict[str, Any]] = {}
        
        # Crea directory
        self.tracking_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Carica dati
        self._load_glossary()
        self._load_tracking()
        
        logger.info(f"GlossaryCollector: {len(self._glossary)} termini nel glossario")
    
    def _load_glossary(self):
        """Carica glossario da file"""
        if not self.glossary_path.exists():
            logger.warning(f"Glossario non trovato: {self.glossary_path}")
            return
        
        try:
            with open(self.glossary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Supporta sia formato lista che dizionario
            if isinstance(data, list):
                # Formato lista [{"term": "X", "definition": "Y"}, ...]
                for item in data:
                    term = item.get("term", item.get("acronym", "")).upper()
                    if term:
                        self._glossary[term] = item
            elif isinstance(data, dict):
                # Formato dizionario {"X": "Y", ...} o {"X": {...}, ...}
                for term, value in data.items():
                    self._glossary[term.upper()] = value if isinstance(value, dict) else {"definition": value}
            
            logger.debug(f"Caricati {len(self._glossary)} termini")
            
        except Exception as e:
            logger.error(f"Errore caricamento glossario: {e}")
    
    def _load_tracking(self):
        """Carica tracking da file"""
        if not self.tracking_path.exists():
            return
        
        try:
            with open(self.tracking_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._usage_tracking = data.get("usage", {})
            self._unknown_terms = data.get("unknown", {})
            
            logger.debug(f"Caricato tracking: {len(self._usage_tracking)} tracked, {len(self._unknown_terms)} unknown")
            
        except Exception as e:
            logger.error(f"Errore caricamento tracking: {e}")
    
    def _save_tracking(self):
        """Salva tracking su file"""
        try:
            data = {
                "usage": self._usage_tracking,
                "unknown": self._unknown_terms,
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.tracking_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Errore salvataggio tracking: {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # TRACKING
    # ═══════════════════════════════════════════════════════════════
    
    def track_usage(
        self,
        terms: List[str],
        user_id: str = "unknown",
        context: str = ""
    ):
        """
        Traccia utilizzo di termini.
        
        Args:
            terms: Lista termini usati (già risolti o cercati)
            user_id: ID utente
            context: Contesto query (opzionale)
        """
        now = datetime.now().isoformat()
        
        for term in terms:
            term_upper = term.upper()
            
            if term_upper in self._glossary:
                # Termine conosciuto - aggiorna tracking
                if term_upper not in self._usage_tracking:
                    self._usage_tracking[term_upper] = {
                        "count": 0,
                        "first_used": now,
                        "last_used": now,
                        "users": []
                    }
                
                self._usage_tracking[term_upper]["count"] += 1
                self._usage_tracking[term_upper]["last_used"] = now
                
                if user_id not in self._usage_tracking[term_upper]["users"]:
                    self._usage_tracking[term_upper]["users"].append(user_id)
                    # Mantieni max 20 utenti
                    self._usage_tracking[term_upper]["users"] = self._usage_tracking[term_upper]["users"][-20:]
        
        self._save_tracking()
    
    def track_unknown(
        self,
        term: str,
        user_id: str = "unknown",
        context: str = ""
    ):
        """
        Traccia termine non trovato nel glossario.
        
        Args:
            term: Termine non trovato
            user_id: ID utente
            context: Contesto (snippet query)
        """
        term_upper = term.upper()
        now = datetime.now().isoformat()
        
        if term_upper not in self._unknown_terms:
            self._unknown_terms[term_upper] = {
                "count": 0,
                "first_seen": now,
                "last_seen": now,
                "users": [],
                "contexts": []
            }
        
        self._unknown_terms[term_upper]["count"] += 1
        self._unknown_terms[term_upper]["last_seen"] = now
        
        if user_id not in self._unknown_terms[term_upper]["users"]:
            self._unknown_terms[term_upper]["users"].append(user_id)
        
        if context and context not in self._unknown_terms[term_upper]["contexts"]:
            self._unknown_terms[term_upper]["contexts"].append(context[:100])
            # Mantieni max 5 contesti
            self._unknown_terms[term_upper]["contexts"] = self._unknown_terms[term_upper]["contexts"][-5:]
        
        self._save_tracking()
        logger.debug(f"[R07] Termine sconosciuto tracciato: {term_upper}")
    
    # ═══════════════════════════════════════════════════════════════
    # STATISTICHE
    # ═══════════════════════════════════════════════════════════════
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Statistiche complete glossario.
        
        Returns:
            Dict con metriche aggregate
        """
        # Termini nel glossario
        total_terms = len(self._glossary)
        
        # Termini usati almeno una volta
        terms_used = set(self._usage_tracking.keys())
        terms_used_count = len(terms_used)
        
        # Termini mai usati
        all_terms = set(self._glossary.keys())
        terms_never_used = list(all_terms - terms_used)
        
        # Top termini più usati
        term_counts = [
            (term, data["count"])
            for term, data in self._usage_tracking.items()
        ]
        term_counts.sort(key=lambda x: x[1], reverse=True)
        most_used = term_counts[:20]
        
        # Termini usati oggi
        today = datetime.now().strftime("%Y-%m-%d")
        terms_used_today = 0
        for term, data in self._usage_tracking.items():
            if data.get("last_used", "").startswith(today):
                terms_used_today += 1
        
        # Unknown terms (gap)
        unknown_sorted = sorted(
            self._unknown_terms.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )
        
        return {
            "total_terms": total_terms,
            "terms_used_ever": terms_used_count,
            "terms_used_today": terms_used_today,
            "terms_never_used": terms_never_used[:30],  # Max 30
            "terms_never_used_count": len(terms_never_used),
            "coverage_ratio": round(terms_used_count / total_terms, 3) if total_terms else 0,
            "most_used": most_used,
            "unknown_terms": [
                {
                    "term": term,
                    "count": data["count"],
                    "contexts": data.get("contexts", [])[:2]
                }
                for term, data in unknown_sorted[:20]
            ],
            "unknown_count": len(self._unknown_terms),
            "total_usages": sum(d["count"] for d in self._usage_tracking.values())
        }
    
    def get_term_stats(self, term: str) -> Optional[Dict[str, Any]]:
        """
        Statistiche per singolo termine.
        
        Args:
            term: Termine da cercare
            
        Returns:
            Dict con statistiche o None
        """
        term_upper = term.upper()
        
        if term_upper not in self._glossary:
            # Cerca in unknown
            if term_upper in self._unknown_terms:
                data = self._unknown_terms[term_upper]
                return {
                    "term": term_upper,
                    "in_glossary": False,
                    "usage_count": data["count"],
                    "last_seen": data.get("last_seen"),
                    "contexts": data.get("contexts", [])
                }
            return None
        
        # Termine nel glossario
        glossary_data = self._glossary[term_upper]
        usage_data = self._usage_tracking.get(term_upper, {})
        
        return {
            "term": term_upper,
            "in_glossary": True,
            "definition": glossary_data.get("definition", glossary_data) if isinstance(glossary_data, dict) else glossary_data,
            "usage_count": usage_data.get("count", 0),
            "last_used": usage_data.get("last_used"),
            "unique_users": len(usage_data.get("users", []))
        }
    
    def get_unused_terms(self, limit: int = 50) -> List[str]:
        """
        Termini mai usati.
        
        Args:
            limit: Massimo risultati
            
        Returns:
            Lista termini mai usati
        """
        all_terms = set(self._glossary.keys())
        used_terms = set(self._usage_tracking.keys())
        unused = list(all_terms - used_terms)
        
        # Ordina alfabeticamente
        unused.sort()
        
        return unused[:limit]
    
    def get_trending_terms(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Termini trending negli ultimi N giorni.
        
        Args:
            days: Giorni da considerare
            
        Returns:
            Lista termini con conteggio recente
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        trending = []
        for term, data in self._usage_tracking.items():
            if data.get("last_used", "") >= cutoff:
                trending.append({
                    "term": term,
                    "count": data["count"],
                    "last_used": data["last_used"]
                })
        
        trending.sort(key=lambda x: x["count"], reverse=True)
        
        return trending[:20]
    
    def reload_glossary(self):
        """Ricarica glossario da file"""
        self._glossary.clear()
        self._load_glossary()


# Singleton
_collector: Optional[GlossaryCollector] = None


def get_glossary_collector() -> GlossaryCollector:
    """Ottiene istanza singleton GlossaryCollector"""
    global _collector
    if _collector is None:
        _collector = GlossaryCollector()
    return _collector


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    import shutil
    
    # Setup test
    temp_dir = tempfile.mkdtemp()
    glossary_path = Path(temp_dir) / "glossary.json"
    tracking_path = Path(temp_dir) / "tracking.json"
    
    # Crea glossario di test
    test_glossary = {
        "WCM": {"definition": "World Class Manufacturing"},
        "NC": {"definition": "Non Conformità"},
        "PDCA": {"definition": "Plan Do Check Act"},
        "FMEA": {"definition": "Failure Mode and Effects Analysis"},
        "5S": {"definition": "Sort, Set, Shine, Standardize, Sustain"}
    }
    with open(glossary_path, "w") as f:
        json.dump(test_glossary, f)
    
    print("=== TEST GLOSSARY COLLECTOR ===\n")
    
    collector = GlossaryCollector(
        glossary_path=str(glossary_path),
        tracking_path=str(tracking_path)
    )
    
    # Test 1: Track usage
    print("Test 1: Track usage")
    collector.track_usage(["WCM", "NC", "NC"], user_id="mario")
    collector.track_usage(["PDCA", "WCM"], user_id="luigi")
    collector.track_usage(["NC"], user_id="anna")
    print("  Tracking completato")
    print()
    
    # Test 2: Track unknown
    print("Test 2: Track unknown terms")
    collector.track_unknown("XYZ", user_id="mario", context="cos'è XYZ?")
    collector.track_unknown("ABC", user_id="luigi", context="definizione ABC")
    collector.track_unknown("XYZ", user_id="anna")  # Duplicato
    print("  Unknown tracked")
    print()
    
    # Test 3: Get stats
    print("Test 3: Get stats")
    stats = collector.get_stats()
    print(f"  Total terms: {stats['total_terms']}")
    print(f"  Terms used: {stats['terms_used_ever']}")
    print(f"  Never used: {stats['terms_never_used_count']}")
    print(f"  Coverage: {stats['coverage_ratio']:.1%}")
    print(f"  Unknown: {stats['unknown_count']}")
    print(f"  Most used: {stats['most_used'][:3]}")
    print()
    
    # Test 4: Term stats
    print("Test 4: Term stats")
    nc_stats = collector.get_term_stats("NC")
    print(f"  NC: {nc_stats['usage_count']} uses, {nc_stats['unique_users']} users")
    
    xyz_stats = collector.get_term_stats("XYZ")
    print(f"  XYZ (unknown): {xyz_stats['usage_count']} seen")
    print()
    
    # Test 5: Unused terms
    print("Test 5: Unused terms")
    unused = collector.get_unused_terms()
    print(f"  Unused: {unused}")
    print()
    
    # Cleanup
    shutil.rmtree(temp_dir)
    
    print("✅ Test completati!")

