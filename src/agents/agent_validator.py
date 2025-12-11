"""
Agent 6: ValidatorAgent - R26 Anti-Hallucination
Responsabilità:
- Validare risposte RAG per prevenire allucinazioni nelle citazioni
- Attivare retry se citazioni non valide
- Fornire feedback specifico per rigenerazione

Validazioni:
1. CITATION_CHECK: Citazioni presenti nel contesto?
2. GROUNDING_CHECK: Risposta supportata dai documenti? (opzionale)

Flow:
- Se VALID → END
- Se INVALID → REGENERATE (max 2 retry)
- Se MAX_RETRIES → accetta comunque con warning
"""

import logging
import time
from typing import Dict, Any, Set, Tuple, List
from dataclasses import dataclass
from enum import Enum

from src.agents.state import emit_status
from src.integration.citation_extractor import extract_cited_docs, normalize_doc_id

logger = logging.getLogger(__name__)


class ValidationResult(Enum):
    """Risultati possibili della validazione"""
    VALID = "VALID"
    INVALID_CITATIONS = "INVALID_CITATIONS"
    LOW_GROUNDING = "LOW_GROUNDING"
    MAX_RETRIES_EXCEEDED = "MAX_RETRIES_EXCEEDED"


@dataclass
class ValidationOutput:
    """Output strutturato della validazione"""
    result: ValidationResult
    is_valid: bool
    invalid_citations: Set[str]
    details: str
    action: str  # "PASS" | "REGENERATE" | "FAIL"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result.value,
            "is_valid": self.is_valid,
            "invalid_citations": list(self.invalid_citations),
            "details": self.details,
            "action": self.action
        }


class ValidatorAgent:
    """
    Agente di validazione per risposte RAG - R26.
    
    Validazioni implementate:
    1. Citation Check (regex-based, veloce)
       - Estrae citazioni dalla risposta
       - Verifica che siano nel set di documenti disponibili
    
    2. Grounding Check (opzionale, basato su overlap parole)
       - Verifica che le affermazioni siano supportate dai documenti
    
    Uso:
        validator = ValidatorAgent(config)
        result = validator.validate(response, available_docs, context)
        if not result.is_valid:
            # Rigenera con feedback
    """
    
    def __init__(self, config: Dict[str, Any] = None, config_path: str = None):
        """
        Inizializza il ValidatorAgent.
        
        Args:
            config: Configurazione diretta con chiavi:
                - enabled: bool (default True)
                - max_retries: int (default 2)
                - grounding_check_enabled: bool (default False)
                - grounding_threshold: float (default 0.7)
            config_path: Percorso al file config.yaml
        """
        # Carica config da file se non fornita
        if config is None and config_path:
            config = self._load_config(config_path)
        
        self.config = config or {}
        
        # Estrai parametri da config.validator
        validator_config = self.config.get("validator", self.config)
        
        self.enabled = validator_config.get("enabled", True)
        self.max_retries = validator_config.get("max_retries", 2)
        self.grounding_check_enabled = validator_config.get("grounding_check", {}).get("enabled", False)
        self.grounding_threshold = validator_config.get("grounding_check", {}).get("threshold", 0.7)
        self.log_validations = validator_config.get("log_validations", True)
        
        self.name = "validator"
        
        logger.info(
            f"ValidatorAgent (R26) inizializzato: enabled={self.enabled}, "
            f"max_retries={self.max_retries}, grounding={self.grounding_check_enabled}"
        )
    
    def _load_config(self, config_path: str) -> Dict:
        """Carica configurazione da file YAML."""
        try:
            import yaml
            from pathlib import Path
            if Path(config_path).exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Errore caricamento config: {e}")
        return {}
    
    def validate(
        self,
        response: str,
        available_doc_ids: Set[str],
        context: str = "",
        retry_count: int = 0
    ) -> ValidationOutput:
        """
        Valida una risposta RAG.
        
        Args:
            response: Testo della risposta LLM
            available_doc_ids: Set di doc_id disponibili nel contesto
            context: Testo completo del contesto (per grounding check)
            retry_count: Numero di retry già effettuati
            
        Returns:
            ValidationOutput con risultato e azione consigliata
        """
        if not self.enabled:
            return ValidationOutput(
                result=ValidationResult.VALID,
                is_valid=True,
                invalid_citations=set(),
                details="Validation disabled",
                action="PASS"
            )
        
        # Check max retries
        if retry_count >= self.max_retries:
            logger.warning(f"[R26] Max retries ({self.max_retries}) exceeded, accepting response")
            return ValidationOutput(
                result=ValidationResult.MAX_RETRIES_EXCEEDED,
                is_valid=False,
                invalid_citations=set(),
                details=f"Max retries ({self.max_retries}) exceeded, accepting response with warning",
                action="PASS"  # Accetta comunque dopo max retry
            )
        
        # 1. Citation Check (veloce, regex-based)
        is_valid, invalid_cits = self._check_citations(response, available_doc_ids)
        
        if not is_valid:
            if self.log_validations:
                logger.warning(f"[R26] Citazioni invalide trovate: {invalid_cits}")
            return ValidationOutput(
                result=ValidationResult.INVALID_CITATIONS,
                is_valid=False,
                invalid_citations=invalid_cits,
                details=f"Citazioni non nel contesto: {', '.join(invalid_cits)}",
                action="REGENERATE"
            )
        
        # 2. Grounding Check (opzionale)
        if self.grounding_check_enabled and context:
            grounding_score = self._check_grounding(response, context)
            if grounding_score < self.grounding_threshold:
                if self.log_validations:
                    logger.warning(f"[R26] Low grounding score: {grounding_score:.2f}")
                return ValidationOutput(
                    result=ValidationResult.LOW_GROUNDING,
                    is_valid=False,
                    invalid_citations=set(),
                    details=f"Grounding score ({grounding_score:.2f}) sotto soglia ({self.grounding_threshold})",
                    action="REGENERATE"
                )
        
        # Tutto OK
        if self.log_validations:
            logger.info("[R26] Validazione OK")
        return ValidationOutput(
            result=ValidationResult.VALID,
            is_valid=True,
            invalid_citations=set(),
            details="All checks passed",
            action="PASS"
        )
    
    def _check_citations(
        self,
        response: str,
        available_doc_ids: Set[str]
    ) -> Tuple[bool, Set[str]]:
        """
        Verifica che le citazioni siano nel set disponibile.
        
        Returns:
            Tuple (is_valid, invalid_citations)
        """
        # Estrai citazioni dalla risposta
        cited_docs = extract_cited_docs(response)
        
        if not cited_docs:
            # Nessuna citazione = OK (non è un errore)
            return True, set()
        
        # Normalizza doc_id disponibili
        normalized_available = {normalize_doc_id(d) for d in available_doc_ids}
        normalized_cited = {normalize_doc_id(d) for d in cited_docs}
        
        # Trova citazioni non disponibili
        invalid = normalized_cited - normalized_available
        
        return len(invalid) == 0, invalid
    
    def _check_grounding(self, response: str, context: str) -> float:
        """
        Verifica che la risposta sia supportata dal contesto.
        
        Metodo semplice basato su overlap parole significative.
        Non richiede LLM.
        
        Returns:
            Score 0-1 di grounding
        """
        # Estrai parole significative dalla risposta (>4 caratteri, solo lettere)
        response_words = set(
            word.lower() for word in response.split()
            if len(word) > 4 and word.isalpha()
        )
        
        if not response_words:
            return 1.0
        
        context_lower = context.lower()
        
        # Conta quante parole della risposta sono nel contesto
        found = sum(1 for word in response_words if word in context_lower)
        
        return found / len(response_words)
    
    def format_error_feedback(self, validation_output: ValidationOutput) -> str:
        """
        Formatta feedback di errore per il prompt di retry.
        
        Args:
            validation_output: Risultato della validazione fallita
            
        Returns:
            Stringa di feedback da aggiungere al prompt
        """
        if validation_output.result == ValidationResult.INVALID_CITATIONS:
            invalid = ", ".join(validation_output.invalid_citations)
            return (
                f"⚠️ ERRORE PRECEDENTE: Hai citato documenti non presenti nel contesto: {invalid}\n"
                f"🚫 NON citare questi documenti. Usa SOLO quelli elencati in 'DOCUMENTI DISPONIBILI'.\n"
                f"📌 Riformula la risposta citando SOLO i documenti che ti ho fornito."
            )
        
        elif validation_output.result == ValidationResult.LOW_GROUNDING:
            return (
                "⚠️ ERRORE PRECEDENTE: La risposta non è sufficientemente supportata dai documenti.\n"
                "📌 Basa la risposta SOLO sulle informazioni presenti nei documenti forniti.\n"
                "🚫 NON aggiungere informazioni non presenti nel contesto."
            )
        
        return ""
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Callable per integrazione come nodo LangGraph.
        
        Args:
            state: Stato corrente del grafo
            
        Returns:
            Aggiornamenti allo stato con risultato validazione
        """
        # F11: Emetti stato iniziale
        emit_status(state, "validator")
        
        start = time.time()
        
        response = state.get("answer", "")
        available_docs = set(state.get("available_doc_ids", []))
        context = state.get("compressed_context", "")
        retry_count = state.get("retry_count", 0)
        
        # Se non ci sono doc disponibili, usa selected_sources come fallback
        if not available_docs:
            available_docs = set(state.get("selected_sources", []))
        
        # Valida
        validation = self.validate(
            response=response,
            available_doc_ids=available_docs,
            context=context,
            retry_count=retry_count
        )
        
        latency = (time.time() - start) * 1000
        
        # Prepara aggiornamenti stato
        updates = {
            "validation_result": validation.result.value,
            "validation_details": validation.details,
            "agent_trace": state.get("agent_trace", []) + [f"validator:{latency:.0f}ms:{validation.result.value}"]
        }
        
        # F11: Aggiorna stato con esito validazione
        if validation.is_valid:
            cited_count = len(validation.invalid_citations) if hasattr(validation, 'invalid_citations') else 0
            emit_status(state, "validator", f"✓")
        else:
            # F11: Mostra messaggio retry per 5 secondi per farlo vedere all'utente
            emit_status(state, "retry", "", delay_seconds=5)
        
        # Se richiede rigenerazione, prepara feedback
        if not validation.is_valid and validation.action == "REGENERATE":
            updates["retry_count"] = retry_count + 1
            
            # Aggiungi feedback errore per prossimo tentativo
            error_feedback = self.format_error_feedback(validation)
            previous_errors = state.get("previous_errors", [])
            previous_errors.append(error_feedback)
            updates["previous_errors"] = previous_errors
            
            logger.info(f"[R26] Richiesta rigenerazione (retry {retry_count + 1}/{self.max_retries})")
        
        return updates


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("TEST VALIDATOR AGENT - R26")
    print("=" * 60)
    
    validator = ValidatorAgent({"enabled": True, "max_retries": 2})
    
    # Test 1: Citazione valida
    print("\n--- Test 1: Citazione valida ---")
    response1 = "Secondo IL-06_01, la gestione rifiuti prevede..."
    available1 = {"IL-06_01", "IL-22_00"}
    result1 = validator.validate(response1, available1)
    print(f"Risultato: {result1.to_dict()}")
    
    # Test 2: Citazione invalida
    print("\n--- Test 2: Citazione invalida ---")
    response2 = "Secondo PS-06_01, la gestione rifiuti prevede..."
    available2 = {"IL-06_01", "IL-22_00"}
    result2 = validator.validate(response2, available2)
    print(f"Risultato: {result2.to_dict()}")
    print(f"Feedback: {validator.format_error_feedback(result2)}")
    
    # Test 3: Mix citazioni
    print("\n--- Test 3: Mix citazioni valide/invalide ---")
    response3 = "Vedi IL-06_01 e PS-06_01 per dettagli su MR-08_01."
    available3 = {"IL-06_01", "IL-22_00"}
    result3 = validator.validate(response3, available3)
    print(f"Risultato: {result3.to_dict()}")
    
    # Test 4: Max retries
    print("\n--- Test 4: Max retries exceeded ---")
    result4 = validator.validate(response2, available2, retry_count=2)
    print(f"Risultato: {result4.to_dict()}")
    
    # Test 5: Nessuna citazione
    print("\n--- Test 5: Nessuna citazione ---")
    response5 = "La gestione rifiuti è importante per l'ambiente."
    result5 = validator.validate(response5, available2)
    print(f"Risultato: {result5.to_dict()}")
    
    # Test 6: Come nodo LangGraph
    print("\n--- Test 6: Come nodo LangGraph ---")
    test_state = {
        "answer": "Secondo PS-06_01 e IL-06_01, i rifiuti vanno gestiti...",
        "available_doc_ids": ["IL-06_01", "IL-22_00"],
        "compressed_context": "Testo documento...",
        "retry_count": 0,
        "agent_trace": ["glossary:10ms", "retriever:200ms"]
    }
    result6 = validator(test_state)
    print(f"State updates: {result6}")

