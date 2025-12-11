"""
Learning Detector per OVV ISO Chat v3.2
Rileva quando l'utente "insegna" qualcosa al sistema

Patterns supportati:
- "X significa Y"
- "X vuol dire Y"
- "X sta per Y"
- "con X intendo Y"
- "X = Y" o "X: Y"
- "no, X è Y" (correzione)
"""

import re
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class LearningType(str, Enum):
    """Tipo di apprendimento rilevato"""
    DEFINITION = "definition"      # Definizione nuova
    CORRECTION = "correction"      # Correzione di errore
    CLARIFICATION = "clarification"  # Chiarimento


@dataclass
class LearningResult:
    """Risultato del rilevamento apprendimento"""
    term: str           # Acronimo/termine (es. "CDL")
    meaning: str        # Significato (es. "Centro Di Lavoro")
    learning_type: LearningType
    confidence: float   # 0.0 - 1.0
    original_text: str  # Testo originale che ha triggerato
    
    def to_dict(self) -> Dict:
        return {
            "term": self.term,
            "meaning": self.meaning,
            "learning_type": self.learning_type.value,
            "confidence": self.confidence,
            "original_text": self.original_text
        }


class LearningDetector:
    """
    Rileva pattern di apprendimento nei messaggi utente.
    Quando l'utente "insegna" qualcosa, il sistema può salvarlo.
    """
    
    # Pattern con gruppo 1 = termine, gruppo 2 = significato
    LEARNING_PATTERNS: List[tuple] = [
        # Definizioni dirette (alta confidenza)
        (r"(\w{2,8})\s+significa\s+(.+)", LearningType.DEFINITION, 0.95),
        (r"(\w{2,8})\s+vuol\s*dire\s+(.+)", LearningType.DEFINITION, 0.95),
        (r"(\w{2,8})\s+sta\s+per\s+(.+)", LearningType.DEFINITION, 0.95),
        
        # Chiarimenti (media confidenza)
        (r"con\s+(\w{2,8})\s+intendo\s+(.+)", LearningType.CLARIFICATION, 0.85),
        (r"per\s+(\w{2,8})\s+intendo\s+(.+)", LearningType.CLARIFICATION, 0.85),
        (r"quando\s+dico\s+(\w{2,8})\s+intendo\s+(.+)", LearningType.CLARIFICATION, 0.85),
        
        # Assegnazioni (media confidenza)
        (r"(\w{2,8})\s*=\s*(.+)", LearningType.DEFINITION, 0.80),
        (r"(\w{2,8})\s*:\s+(.{5,})", LearningType.DEFINITION, 0.75),
        
        # Correzioni (alta confidenza)
        (r"no[,\s]+(\w{2,8})\s+(?:e'|è)\s+(.+)", LearningType.CORRECTION, 0.90),
        (r"non\s+(\w{2,8})[,\s]+(?:e'|è)\s+(.+)", LearningType.CORRECTION, 0.85),
        (r"(\w{2,8})\s+non\s+(?:e'|è)\s+.+[,\s]+(?:ma|bensì)\s+(.+)", LearningType.CORRECTION, 0.90),
    ]
    
    # Termini da escludere (troppo generici)
    EXCLUDED_TERMS = {
        "il", "la", "lo", "le", "un", "una", "uno",
        "che", "non", "per", "con", "questo", "quello",
        "cosa", "come", "dove", "quando", "perché",
        "si", "no", "ok", "va", "bene"
    }
    
    def __init__(self):
        """Inizializza il detector"""
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), ltype, conf)
            for pattern, ltype, conf in self.LEARNING_PATTERNS
        ]
        logger.info(f"LearningDetector: {len(self._compiled_patterns)} pattern caricati")
    
    def detect(self, text: str) -> Optional[LearningResult]:
        """
        Analizza il testo e rileva se contiene un pattern di apprendimento.
        
        Args:
            text: Testo del messaggio utente
            
        Returns:
            LearningResult se rilevato, None altrimenti
        """
        if not text or len(text) < 5:
            return None
        
        # Pulisci il testo
        text_clean = text.strip()
        
        for pattern, learning_type, base_confidence in self._compiled_patterns:
            match = pattern.search(text_clean)
            
            if match:
                term = match.group(1).strip().upper()
                meaning = match.group(2).strip()
                
                # Valida il termine
                if not self._is_valid_term(term):
                    continue
                
                # Valida il significato
                meaning = self._clean_meaning(meaning)
                if not self._is_valid_meaning(meaning):
                    continue
                
                # Calcola confidenza finale
                confidence = self._calculate_confidence(
                    term, meaning, base_confidence, text_clean
                )
                
                logger.info(f"Apprendimento rilevato: {term} = {meaning} ({learning_type.value}, conf={confidence:.2f})")
                
                return LearningResult(
                    term=term,
                    meaning=meaning,
                    learning_type=learning_type,
                    confidence=confidence,
                    original_text=text_clean
                )
        
        return None
    
    def _is_valid_term(self, term: str) -> bool:
        """Verifica se il termine è valido (acronimo plausibile)"""
        if len(term) < 2 or len(term) > 8:
            return False
        
        if term.lower() in self.EXCLUDED_TERMS:
            return False
        
        # Deve essere prevalentemente lettere/numeri
        if not term.replace("_", "").replace("-", "").isalnum():
            return False
        
        return True
    
    def _is_valid_meaning(self, meaning: str) -> bool:
        """Verifica se il significato è valido"""
        if len(meaning) < 3:
            return False
        
        # Rimuovi significati troppo corti o generici
        if meaning.lower() in self.EXCLUDED_TERMS:
            return False
        
        return True
    
    def _clean_meaning(self, meaning: str) -> str:
        """Pulisce il significato da punteggiatura finale e spazi"""
        # Rimuovi punteggiatura finale
        meaning = meaning.rstrip(".,;:!?")
        
        # Rimuovi virgolette
        meaning = meaning.strip("\"'")
        
        # Capitalizza prima lettera
        if meaning:
            meaning = meaning[0].upper() + meaning[1:]
        
        return meaning.strip()
    
    def _calculate_confidence(
        self, 
        term: str, 
        meaning: str, 
        base_confidence: float,
        full_text: str
    ) -> float:
        """
        Calcola confidenza finale basata su vari fattori.
        
        Boost:
        - Termine tutto maiuscolo: +0.05
        - Significato lungo (>20 char): +0.03
        - Testo corto e diretto: +0.02
        
        Penalità:
        - Testo con domande: -0.10
        - Termine troppo lungo: -0.05
        """
        confidence = base_confidence
        
        # Boost: termine tutto maiuscolo (tipico acronimo)
        if term.isupper() and len(term) >= 2:
            confidence += 0.05
        
        # Boost: significato dettagliato
        if len(meaning) > 20:
            confidence += 0.03
        
        # Boost: messaggio breve e diretto
        if len(full_text) < 50:
            confidence += 0.02
        
        # Penalità: presenza di domande
        if "?" in full_text:
            confidence -= 0.10
        
        # Penalità: termine lungo (meno probabile sia acronimo)
        if len(term) > 5:
            confidence -= 0.05
        
        # Clamp tra 0 e 1
        return max(0.0, min(1.0, confidence))
    
    def detect_multiple(self, text: str) -> List[LearningResult]:
        """
        Rileva tutti i pattern di apprendimento nel testo.
        Utile per messaggi che contengono più definizioni.
        
        Args:
            text: Testo del messaggio utente
            
        Returns:
            Lista di LearningResult
        """
        results = []
        seen_terms = set()
        
        for pattern, learning_type, base_confidence in self._compiled_patterns:
            for match in pattern.finditer(text):
                term = match.group(1).strip().upper()
                
                # Evita duplicati
                if term in seen_terms:
                    continue
                
                meaning = match.group(2).strip()
                
                if not self._is_valid_term(term):
                    continue
                
                meaning = self._clean_meaning(meaning)
                if not self._is_valid_meaning(meaning):
                    continue
                
                confidence = self._calculate_confidence(
                    term, meaning, base_confidence, text
                )
                
                results.append(LearningResult(
                    term=term,
                    meaning=meaning,
                    learning_type=learning_type,
                    confidence=confidence,
                    original_text=text
                ))
                
                seen_terms.add(term)
        
        # Ordina per confidenza
        results.sort(key=lambda x: x.confidence, reverse=True)
        
        return results


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    detector = LearningDetector()
    
    test_messages = [
        "CDL significa Centro Di Lavoro",
        "QK vuol dire Quick Kaizen",
        "RI sta per Richiesta di Investimento",
        "con NC intendo Non Conformità",
        "SGI = Sistema Gestione Integrato",
        "no, CDL è Centro Di Lavoro, non Ciclo",
        "Ciao, come stai?",  # Nessun pattern
        "Cosa significa PS?",  # Domanda, non definizione
    ]
    
    print("=" * 60)
    print("TEST LEARNING DETECTOR")
    print("=" * 60)
    
    for msg in test_messages:
        result = detector.detect(msg)
        if result:
            print(f"\n✅ '{msg}'")
            print(f"   → {result.term} = {result.meaning}")
            print(f"   → Tipo: {result.learning_type.value}, Confidenza: {result.confidence:.2f}")
        else:
            print(f"\n❌ '{msg}' → Nessun pattern rilevato")

