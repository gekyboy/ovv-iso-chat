"""
Agent 1: GlossaryAgent
Responsabilità:
- Espandere acronimi nella query
- Risolvere ambiguità (es. CDL = Centro Di Lavoro vs Ciclo Di Lavoro)
- Generare contesto glossario per LLM finale

Ottimizzazione VRAM: Nessun LLM, solo lookup e fuzzy matching
"""

from typing import Dict, Any
import time
import logging

logger = logging.getLogger(__name__)


class GlossaryAgent:
    """
    Espande acronimi e genera contesto glossario.
    
    Non usa LLM - solo lookup su glossary.json e fuzzy matching.
    Questo è il primo agente nel grafo, prepara la query per gli altri.
    """
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Inizializza l'agente glossario.
        
        Args:
            config_path: Percorso al file di configurazione
        """
        self.name = "glossary"
        self._glossary = None
        self.config_path = config_path
    
    @property
    def glossary(self):
        """Lazy loading del GlossaryResolver"""
        if self._glossary is None:
            from src.integration.glossary import GlossaryResolver
            self._glossary = GlossaryResolver(config_path=self.config_path)
        return self._glossary
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Esegue espansione acronimi.
        
        Args:
            state: Stato corrente del grafo
            
        Returns:
            Aggiornamenti allo stato (expanded_query, acronyms_found, glossary_context)
        """
        start = time.time()
        
        query = state.get("original_query", "")
        
        # 1. Espandi query con acronimi (solo se non già espansa)
        # Controlla se la query contiene già espansioni tipo "AC (Azione Correttiva)"
        import re
        already_expanded = bool(re.search(r'\b[A-Z]{2,8}\s*\([^)]+\)', query))
        
        try:
            if already_expanded:
                # Query già espansa da app_chainlit.py, non ri-espandere
                expanded = query
                logger.debug(f"Query già espansa, skip rewrite: {query[:50]}...")
            else:
                expanded = self.glossary.rewrite_query(query)
        except Exception as e:
            logger.warning(f"Errore espansione query: {e}")
            expanded = query
        
        # 2. Estrai acronimi trovati per context
        acronyms_found = []
        try:
            import re
            # Estrai potenziali acronimi dalla query (parole 2-8 char, case insensitive)
            # Pattern: parole di 2-8 lettere che potrebbero essere acronimi
            potential_acronyms = re.findall(r'\b([A-Za-z]{2,8})\b', query)
            
            # Filtra e verifica quali esistono nel glossario
            seen = set()
            for acr in potential_acronyms:
                acr_upper = acr.upper()
                if acr_upper in seen:
                    continue
                seen.add(acr_upper)
                
                info = self.glossary.resolve_acronym(acr_upper)
                if info:
                    acronyms_found.append({
                        "acronym": acr_upper,
                        "full": info.get("full", ""),
                        "description": info.get("description", "")
                    })
        except Exception as e:
            logger.warning(f"Errore estrazione acronimi: {e}")
        
        # 3. Genera context per LLM (R20 style)
        glossary_context = ""
        try:
            glossary_context = self.glossary.get_context_for_query(
                query,
                max_definitions=5,
                include_description=True
            )
        except Exception as e:
            logger.warning(f"Errore generazione glossary context: {e}")
        
        latency = (time.time() - start) * 1000
        
        logger.info(
            f"GlossaryAgent: {len(acronyms_found)} acronimi trovati, "
            f"query espansa: {expanded[:50]}..."
        )
        
        return {
            "expanded_query": expanded,
            "acronyms_found": acronyms_found,
            "glossary_context": glossary_context,
            "agent_trace": state.get("agent_trace", []) + [f"glossary:{latency:.0f}ms"]
        }


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    agent = GlossaryAgent(config_path="config/config.yaml")
    
    test_state = {
        "original_query": "Cosa significa WCM e come si usa nel SGI?",
        "agent_trace": []
    }
    
    result = agent(test_state)
    
    print(f"Query espansa: {result['expanded_query']}")
    print(f"Acronimi: {result['acronyms_found']}")
    print(f"Glossary context: {result['glossary_context'][:200]}...")
    print(f"Trace: {result['agent_trace']}")

