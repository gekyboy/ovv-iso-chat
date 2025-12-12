"""
UI-agnostic Documents Logic
Logica per gestire path documenti e indicizzazione PDF - estratta da Chainlit
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import logging
import time

logger = logging.getLogger(__name__)


class DocumentManager:
    """
    Gestore documenti UI-agnostic.
    Sostituisce la logica Chainlit-specific per path management.
    """

    def __init__(self):
        self._pdf_cache: Dict[str, Path] = {}
        self._cache_timestamp = 0
        self._cache_ttl = 300  # 5 minuti TTL cache

    def get_path_manager(self):
        """Ottiene istanza del path manager"""
        from src.ingestion.path_manager import get_path_manager
        return get_path_manager()

    def set_path(self, new_path: str) -> Dict[str, Any]:
        """
        Imposta nuovo path per i documenti.

        Args:
            new_path: Nuovo percorso da impostare

        Returns:
            Dict con risultato dell'operazione
        """
        try:
            manager = self.get_path_manager()
            result = manager.set_path(new_path)

            response = {
                "success": result.valid,
                "path": str(result.path) if result.valid else None,
                "error": result.error if not result.valid else None,
                "stats": None
            }

            if result.valid:
                response["stats"] = {
                    "pdf_count": result.pdf_count,
                    "ps_count": result.ps_count,
                    "il_count": result.il_count,
                    "mr_count": result.mr_count,
                    "tools_count": result.tools_count
                }
                logger.info(f"[DocumentManager] Path impostato: {result.path}")

            return response

        except Exception as e:
            logger.error(f"[DocumentManager] Errore set_path: {e}")
            return {
                "success": False,
                "path": None,
                "error": str(e),
                "stats": None
            }

    def get_current_path_info(self) -> Dict[str, Any]:
        """
        Ottiene informazioni sul path corrente.

        Returns:
            Dict con info del path corrente
        """
        try:
            manager = self.get_path_manager()
            current = manager.get_current_path()
            status = manager.get_status()

            return {
                "path": str(current),
                "exists": current.exists(),
                "pdf_count": status.get("pdf_count", 0),
                "documents": status.get("documents", [])
            }

        except Exception as e:
            logger.error(f"[DocumentManager] Errore get_current_path_info: {e}")
            return {
                "path": "data/input_docs",
                "exists": False,
                "pdf_count": 0,
                "documents": []
            }

    def get_recent_paths(self, limit: int = 10) -> List[str]:
        """
        Ottiene lista path recenti.

        Args:
            limit: Numero massimo di path da restituire

        Returns:
            Lista di path recenti come stringhe
        """
        try:
            manager = self.get_path_manager()
            recents = manager.get_recent_paths(limit=limit)
            return [str(p) for p in recents]
        except Exception as e:
            logger.error(f"[DocumentManager] Errore get_recent_paths: {e}")
            return []

    def reset_to_default(self) -> bool:
        """
        Reset al path di default.

        Returns:
            True se riuscito
        """
        try:
            manager = self.get_path_manager()
            manager.reset_to_default()
            logger.info("[DocumentManager] Reset to default path")
            return True
        except Exception as e:
            logger.error(f"[DocumentManager] Errore reset_to_default: {e}")
            return False

    def build_pdf_index(self, pdf_dir: str = "data/input_docs") -> Dict[str, Path]:
        """
        Costruisce indice PDF ottimizzato per ridurre scanning ripetuto.

        Args:
            pdf_dir: Directory dei PDF

        Returns:
            Dict doc_id -> Path al PDF
        """
        # Usa cache se valida
        current_time = time.time()
        if (current_time - self._cache_timestamp) < self._cache_ttl and self._pdf_cache:
            return self._pdf_cache.copy()

        pdf_path = Path(pdf_dir)
        if not pdf_path.exists():
            logger.warning(f"[DocumentManager] Directory PDF non esiste: {pdf_dir}")
            return {}

        index = {}

        try:
            for pdf_file in pdf_path.glob("*.pdf"):
                if pdf_file.is_file():
                    # Estrai doc_id dal nome file (es. "PS-06_01_Rev.04_..." -> "PS-06_01")
                    stem = pdf_file.stem
                    # Prendi solo la parte iniziale fino al primo "_" o "-"
                    doc_id = stem.split('_')[0].split('-')[0] + '-' + stem.split('_')[1].split('-')[1] if '_' in stem or '-' in stem else stem

                    if doc_id:
                        index[doc_id] = pdf_file

            logger.info(f"[DocumentManager] Indicizzati {len(index)} PDF")
            self._pdf_cache = index
            self._cache_timestamp = current_time

        except Exception as e:
            logger.error(f"[DocumentManager] Errore indicizzazione PDF: {e}")

        return index

    def find_pdf_by_doc_id(self, doc_id: str) -> Optional[Path]:
        """
        Trova PDF per doc_id usando indice ottimizzato.

        Args:
            doc_id: ID documento

        Returns:
            Path al PDF o None
        """
        # Costruisci indice se necessario
        if not self._pdf_cache:
            self.build_pdf_index()

        # Cerca match diretto
        pdf_path = self._pdf_cache.get(doc_id)
        if pdf_path:
            return pdf_path

        # Cerca match normalizzato
        normalized_doc_id = doc_id.replace("-", "_")
        for cached_id, path in self._pdf_cache.items():
            if cached_id.replace("-", "_") == normalized_doc_id:
                return path

        logger.debug(f"[DocumentManager] PDF non trovato: {doc_id}")
        return None


# Singleton instance
_document_manager = None

def get_document_manager() -> DocumentManager:
    """Ottiene istanza singleton del DocumentManager"""
    global _document_manager
    if _document_manager is None:
        _document_manager = DocumentManager()
    return _document_manager
