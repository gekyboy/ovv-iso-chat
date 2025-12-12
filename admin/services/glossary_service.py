"""
Glossary Service Layer
Logica di business per gestione glossario - estratto da Streamlit
"""

from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class GlossaryService:
    """Service per gestione CRUD glossario"""

    def __init__(self):
        self._glossary = None

    def get_acronyms(self, search: str = None) -> List[Dict[str, Any]]:
        """
        Ottiene acronimi con ricerca opzionale

        Args:
            search: Termine di ricerca

        Returns:
            Lista acronimi
        """
        try:
            glossary = self._get_glossary()

            acronyms = []
            for acronym, data in glossary.acronyms.items():
                if search and search.lower() not in acronym.lower():
                    continue

                acronym_dict = {
                    "acronym": acronym,
                    "expansion": data.get("expansion", ""),
                    "description": data.get("description", ""),
                    "category": data.get("category", ""),
                    "confidence": data.get("confidence", 0.0)
                }
                acronyms.append(acronym_dict)

            return acronyms

        except Exception as e:
            logger.error(f"Errore caricamento acronimi: {e}")
            return []

    def add_acronym(self, acronym: str, expansion: str, description: str = "", category: str = "") -> Dict[str, Any]:
        """
        Aggiunge nuovo acronimo

        Args:
            acronym: Acronimo
            expansion: Espansione
            description: Descrizione
            category: Categoria

        Returns:
            Dict con risultato
        """
        try:
            glossary = self._get_glossary()

            # TODO: Implementare add_acronym se non esiste
            logger.info(f"Aggiunta acronimo {acronym}: {expansion}")
            return {"success": True, "message": "Acronimo aggiunto (TODO: implementare)"}

        except Exception as e:
            logger.error(f"Errore aggiunta acronimo {acronym}: {e}")
            return {"success": False, "error": str(e)}

    def update_acronym(self, acronym: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggiorna acronimo esistente

        Args:
            acronym: Acronimo da aggiornare
            updates: Campi da aggiornare

        Returns:
            Dict con risultato
        """
        try:
            glossary = self._get_glossary()

            # TODO: Implementare update_acronym
            logger.info(f"Aggiornamento acronimo {acronym}: {updates}")
            return {"success": True, "message": "Acronimo aggiornato (TODO: implementare)"}

        except Exception as e:
            logger.error(f"Errore aggiornamento acronimo {acronym}: {e}")
            return {"success": False, "error": str(e)}

    def delete_acronym(self, acronym: str) -> Dict[str, Any]:
        """
        Elimina acronimo

        Args:
            acronym: Acronimo da eliminare

        Returns:
            Dict con risultato
        """
        try:
            glossary = self._get_glossary()

            # TODO: Implementare delete_acronym
            logger.info(f"Eliminazione acronimo {acronym}")
            return {"success": True, "message": "Acronimo eliminato (TODO: implementare)"}

        except Exception as e:
            logger.error(f"Errore eliminazione acronimo {acronym}: {e}")
            return {"success": False, "error": str(e)}

    def _get_glossary(self):
        """Lazy load glossary"""
        if self._glossary is None:
            from src.integration.glossary import GlossaryResolver
            self._glossary = GlossaryResolver()
        return self._glossary


# Singleton instance
_glossary_service = None

def get_glossary_service() -> GlossaryService:
    """Ottiene istanza singleton del GlossaryService"""
    global _glossary_service
    if _glossary_service is None:
        _glossary_service = GlossaryService()
    return _glossary_service
