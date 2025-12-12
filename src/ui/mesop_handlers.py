"""
Mesop Event Handlers - POC
Handler per singola chiamata alla pipeline RAG esistente
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Import pipeline come in app_chainlit.py
_pipeline = None

def get_pipeline():
    """
    Lazy load RAG pipeline.
    Copia da app_chainlit.py per riusare la stessa logica
    """
    global _pipeline
    if _pipeline is None:
        import yaml
        from pathlib import Path

        config_path = "config/config.yaml"

        # Leggi config per decidere quale pipeline usare
        use_multi_agent = False
        if Path(config_path).exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    use_multi_agent = config.get("multi_agent", {}).get("enabled", False)
            except Exception as e:
                logger.warning(f"Errore lettura config: {e}, uso pipeline classica")

        if use_multi_agent:
            try:
                from src.agents.orchestrator import MultiAgentPipeline
                _pipeline = MultiAgentPipeline(config_path=config_path)
                logger.info("✅ MultiAgentPipeline caricata per Mesop POC")
            except Exception as e:
                logger.warning(f"⚠️ Errore caricamento MultiAgentPipeline: {e}")
                logger.info("Fallback a RAGPipeline classica")
                from src.integration.rag_pipeline import RAGPipeline
                _pipeline = RAGPipeline(config_path=config_path)
        else:
            from src.integration.rag_pipeline import RAGPipeline
            _pipeline = RAGPipeline(config_path=config_path)
            logger.info("RAGPipeline classica caricata per Mesop POC")

    return _pipeline


def handle_query_poc(query: str) -> str:
    """
    POC: Single call alla pipeline RAG esistente

    Args:
        query: La domanda dell'utente

    Returns:
        Risposta dalla pipeline (semplificata per POC)
    """
    try:
        logger.info(f"[POC] Query ricevuta: {query[:50]}...")

        # Ottieni pipeline (stessa logica di Chainlit)
        pipeline = get_pipeline()

        # Per POC semplice, chiamiamo direttamente senza async/status
        # Nota: nella versione completa dovremo gestire async e status callbacks
        result = pipeline.query(query)

        # Estrai solo il testo della risposta (semplificato per POC)
        if hasattr(result, 'answer'):
            answer = result.answer
        elif isinstance(result, dict) and 'answer' in result:
            answer = result['answer']
        elif isinstance(result, str):
            answer = result
        else:
            answer = str(result)

        logger.info(f"[POC] Risposta generata: {len(answer)} caratteri")

        # Per POC, restituiamo solo la risposta senza fonti/metadata
        return answer

    except Exception as e:
        error_msg = f"Errore nella pipeline: {str(e)}"
        logger.error(f"[POC] {error_msg}")
        return error_msg
