"""
Document Path Manager per OVV ISO Chat v3.9.1
Gestione centralizzata del path cartella documenti.

Supporta:
- A) Path da config.yaml (default)
- B) Override da preferenze utente
- C) Cambio runtime via comando

Feature ID: F10 - Document Watcher & Auto-Update
Created: 2025-12-10
"""

import json
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

import yaml

logger = logging.getLogger(__name__)


@dataclass
class PathValidationResult:
    """Risultato validazione path"""
    valid: bool
    path: Optional[Path] = None
    error: Optional[str] = None
    pdf_count: int = 0
    ps_count: int = 0
    il_count: int = 0
    mr_count: int = 0
    tools_count: int = 0


@dataclass
class RecentPath:
    """Path usato di recente"""
    path: str
    last_used: datetime
    pdf_count: int
    label: Optional[str] = None  # Es. "Documenti Produzione"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "last_used": self.last_used.isoformat(),
            "pdf_count": self.pdf_count,
            "label": self.label
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "RecentPath":
        return cls(
            path=data["path"],
            last_used=datetime.fromisoformat(data["last_used"]),
            pdf_count=data.get("pdf_count", 0),
            label=data.get("label")
        )


class DocumentPathManager:
    """
    Gestisce il path della cartella documenti.
    
    Gerarchia di priorità:
    1. Override runtime (set_path chiamato)
    2. Preferenza utente salvata (user_paths.json)
    3. Config.yaml (default)
    
    Usage:
        >>> manager = DocumentPathManager()
        >>> current = manager.get_current_path()
        >>> print(f"Cartella: {current}")
        
        >>> # Cambia cartella
        >>> result = manager.set_path("D:/nuova/cartella")
        >>> if result.valid:
        ...     print(f"Trovati {result.pdf_count} PDF")
        
        >>> # Path recenti
        >>> recents = manager.get_recent_paths()
    """
    
    def __init__(
        self,
        config_path: str = "config/config.yaml",
        prefs_path: str = "data/persist/user_paths.json"
    ):
        """
        Inizializza PathManager.
        
        Args:
            config_path: Path al file config.yaml
            prefs_path: Path al file preferenze utente
        """
        self.config_path = Path(config_path)
        self.prefs_path = Path(prefs_path)
        
        # Carica config
        self.config = self._load_config()
        
        # Path corrente (None = usa default da config)
        self._current_override: Optional[Path] = None
        
        # Path recenti
        self._recent_paths: List[RecentPath] = []
        
        # Carica preferenze
        self._load_preferences()
        
        logger.info(f"DocumentPathManager inizializzato: {self.get_current_path()}")
    
    def _load_config(self) -> Dict:
        """Carica config.yaml"""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    def _load_preferences(self):
        """Carica preferenze utente"""
        try:
            if self.prefs_path.exists():
                with open(self.prefs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Carica path recenti
                self._recent_paths = [
                    RecentPath.from_dict(p) for p in data.get("recent_paths", [])
                ]
                
                # Carica ultimo path usato (se esiste e valido)
                last_path = data.get("last_path")
                if last_path and Path(last_path).exists():
                    self._current_override = Path(last_path)
                    logger.info(f"Caricato ultimo path: {last_path}")
                    
        except Exception as e:
            logger.warning(f"Errore caricamento preferenze: {e}")
    
    def _save_preferences(self):
        """Salva preferenze utente"""
        try:
            self.prefs_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Max path recenti da config
            max_recent = self.config.get("document_path", {}).get("max_recent_paths", 10)
            
            data = {
                "last_path": str(self._current_override) if self._current_override else None,
                "recent_paths": [p.to_dict() for p in self._recent_paths[-max_recent:]],
                "updated_at": datetime.now().isoformat()
            }
            
            with open(self.prefs_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Errore salvataggio preferenze: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # GET/SET PATH
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_default_path(self) -> Path:
        """
        Ottiene il path di default da config.yaml.
        
        Returns:
            Path configurato (o "data/input_docs" se non configurato)
        """
        paths_config = self.config.get("paths", {})
        default = paths_config.get("input_docs", "data/input_docs")
        return Path(default)
    
    def get_current_path(self) -> Path:
        """
        Ottiene il path attualmente attivo.
        
        Priorità:
        1. Override runtime
        2. Preferenza utente salvata
        3. Default da config.yaml
        
        Returns:
            Path attivo
        """
        if self._current_override:
            return self._current_override
        return self.get_default_path()
    
    def set_path(
        self,
        path: str,
        label: Optional[str] = None,
        persist: bool = True
    ) -> PathValidationResult:
        """
        Imposta un nuovo path per i documenti.
        
        Args:
            path: Nuovo path (stringa)
            label: Etichetta opzionale (es. "Documenti Produzione")
            persist: Se salvare nelle preferenze
            
        Returns:
            PathValidationResult con esito validazione
        """
        # Valida prima
        result = self.validate_path(path)
        
        if not result.valid:
            return result
        
        # Imposta override
        self._current_override = result.path
        
        # Aggiungi ai recenti
        recent = RecentPath(
            path=str(result.path),
            last_used=datetime.now(),
            pdf_count=result.pdf_count,
            label=label
        )
        
        # Rimuovi se già presente
        self._recent_paths = [p for p in self._recent_paths if p.path != str(result.path)]
        self._recent_paths.append(recent)
        
        # Salva
        if persist:
            self._save_preferences()
        
        logger.info(f"Path documenti cambiato: {result.path} ({result.pdf_count} PDF)")
        
        return result
    
    def reset_to_default(self):
        """Resetta al path di default da config.yaml"""
        self._current_override = None
        self._save_preferences()
        logger.info(f"Path resettato a default: {self.get_default_path()}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # VALIDATION
    # ═══════════════════════════════════════════════════════════════════════
    
    def validate_path(self, path: str) -> PathValidationResult:
        """
        Valida un path per i documenti.
        
        Verifica:
        - Il path esiste
        - È una directory
        - Contiene file PDF
        - Conta i tipi di documento
        
        Args:
            path: Path da validare
            
        Returns:
            PathValidationResult
        """
        try:
            p = Path(path)
            
            # Esiste?
            if not p.exists():
                return PathValidationResult(
                    valid=False,
                    error=f"Il percorso non esiste: {path}"
                )
            
            # È directory?
            if not p.is_dir():
                return PathValidationResult(
                    valid=False,
                    error=f"Il percorso non è una cartella: {path}"
                )
            
            # Conta PDF
            pdfs = list(p.glob("*.pdf"))
            if not pdfs:
                return PathValidationResult(
                    valid=False,
                    path=p,
                    error="La cartella non contiene file PDF"
                )
            
            # Conta per tipo
            ps_count = len([f for f in pdfs if f.name.upper().startswith("PS-")])
            il_count = len([f for f in pdfs if f.name.upper().startswith("IL-")])
            mr_count = len([f for f in pdfs if f.name.upper().startswith("MR-")])
            tools_count = len([f for f in pdfs if "TOOLS" in f.name.upper()])
            
            return PathValidationResult(
                valid=True,
                path=p,
                pdf_count=len(pdfs),
                ps_count=ps_count,
                il_count=il_count,
                mr_count=mr_count,
                tools_count=tools_count
            )
            
        except Exception as e:
            return PathValidationResult(
                valid=False,
                error=f"Errore validazione: {e}"
            )
    
    # ═══════════════════════════════════════════════════════════════════════
    # RECENT PATHS
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_recent_paths(self, limit: int = 5) -> List[RecentPath]:
        """
        Ottiene i path usati di recente.
        
        Args:
            limit: Numero massimo risultati
            
        Returns:
            Lista path recenti (più recenti prima)
        """
        # Ordina per data decrescente
        sorted_paths = sorted(
            self._recent_paths,
            key=lambda p: p.last_used,
            reverse=True
        )
        return sorted_paths[:limit]
    
    def clear_recent_paths(self):
        """Pulisce la lista path recenti"""
        self._recent_paths.clear()
        self._save_preferences()
    
    # ═══════════════════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_status(self) -> Dict[str, Any]:
        """Ottiene stato corrente del path manager"""
        current = self.get_current_path()
        validation = self.validate_path(str(current))
        
        return {
            "current_path": str(current),
            "is_default": self._current_override is None,
            "is_valid": validation.valid,
            "pdf_count": validation.pdf_count if validation.valid else 0,
            "breakdown": {
                "PS": validation.ps_count,
                "IL": validation.il_count,
                "MR": validation.mr_count,
                "TOOLS": validation.tools_count
            } if validation.valid else {},
            "recent_count": len(self._recent_paths)
        }
    
    def format_status_message(self) -> str:
        """Formatta messaggio di stato per UI"""
        status = self.get_status()
        
        msg = f"📂 **Cartella documenti**\n\n"
        msg += f"📍 **Path**: `{status['current_path']}`\n"
        
        if status["is_default"]:
            msg += "ℹ️ _Usando path di default da config.yaml_\n"
        else:
            msg += "✨ _Path personalizzato_\n"
        
        if status["is_valid"]:
            msg += f"\n📊 **Documenti trovati**: {status['pdf_count']}\n"
            breakdown = status["breakdown"]
            msg += f"  - PS: {breakdown['PS']}\n"
            msg += f"  - IL: {breakdown['IL']}\n"
            msg += f"  - MR: {breakdown['MR']}\n"
            msg += f"  - TOOLS: {breakdown['TOOLS']}\n"
        else:
            msg += "\n⚠️ **Path non valido o cartella vuota**\n"
        
        return msg
    
    def is_ui_selection_allowed(self) -> bool:
        """Verifica se la selezione UI è permessa"""
        return self.config.get("document_path", {}).get("allow_ui_selection", True)
    
    def is_command_allowed(self) -> bool:
        """Verifica se il comando /documenti è permesso"""
        return self.config.get("document_path", {}).get("allow_command", True)
    
    def show_startup_selector(self) -> bool:
        """Verifica se mostrare il selettore all'avvio"""
        return self.config.get("document_path", {}).get("show_startup_selector", False)


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

_manager_instance: Optional[DocumentPathManager] = None


def get_path_manager() -> DocumentPathManager:
    """Ottiene istanza singleton del PathManager"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = DocumentPathManager()
    return _manager_instance


def reset_path_manager():
    """Resetta singleton (utile per test)"""
    global _manager_instance
    _manager_instance = None


# ═══════════════════════════════════════════════════════════════════════════
# CLI TEST
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import os
    os.chdir(Path(__file__).parent.parent.parent)
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("TEST DOCUMENT PATH MANAGER")
    print("=" * 60)
    
    manager = DocumentPathManager()
    
    print(f"\nPath corrente: {manager.get_current_path()}")
    print(f"Path default: {manager.get_default_path()}")
    
    status = manager.get_status()
    print(f"\nStatus: {status}")
    
    print(f"\n{manager.format_status_message()}")

