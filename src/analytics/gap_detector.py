"""
Gap Detector per OVV ISO Chat
Rileva lacune nella knowledge base tramite segnali multipli

R19 - Segnalazione Lacune Intelligente
Created: 2025-12-08

Segnali analizzati:
1. Score retrieval basso (< threshold)
2. Pattern LLM incertezza ("non ho trovato", "non risulta")
3. Termine cercato non nel glossario
4. Termine menzionato nei doc ma mai definito
"""

import re
import logging
from typing import List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class GapSignal(Enum):
    """Tipi di segnale che indicano lacuna"""
    LOW_RETRIEVAL_SCORE = "low_score"       # Score < threshold
    NO_SOURCES = "no_sources"               # Nessun documento trovato
    LLM_UNCERTAINTY = "llm_uncertain"       # LLM ammette incertezza
    TERM_NOT_IN_GLOSSARY = "no_glossary"    # Termine non nel glossario
    TERM_NO_DEFINITION = "no_definition"    # Termine citato ma non definito


@dataclass
class GapDetection:
    """Risultato rilevamento lacuna"""
    is_gap: bool
    gap_score: float              # 0-1, >threshold = lacuna probabile
    signals: List[GapSignal]      # Quali segnali hanno triggerato
    missing_term: Optional[str]   # Termine mancante identificato
    found_in_docs: List[str]      # Documenti dove appare il termine
    suggested_action: str         # "add_glossary", "request_docs", etc.
    snippets: List[str] = field(default_factory=list)  # Snippet dove appare


class GapDetector:
    """
    Rileva lacune nella knowledge base.
    
    Multi-signal detection:
    - Score retrieval basso
    - Pattern LLM incertezza
    - Termine non nel glossario
    - Termine citato ma non definito nei doc
    
    Example:
        >>> detector = GapDetector(glossary_resolver)
        >>> gap = detector.detect_gap(query, response, sources)
        >>> if gap.is_gap:
        ...     print(f"Lacuna: {gap.missing_term}")
    """
    
    # Pattern di incertezza LLM (italiano)
    UNCERTAINTY_PATTERNS = [
        r"non\s+(ho\s+)?trovat[oa]",
        r"non\s+risulta",
        r"non\s+(è|sono)\s+present[ei]",
        r"(manca|mancano)\s+(una\s+)?(definizione|informazion)",
        r"non\s+ho\s+informazioni",
        r"non\s+(posso|sono\s+in\s+grado)",
        r"nei\s+documenti\s+non",
        r"non\s+emerge",
        r"assente\s+(nel|nei|dalla)",
        r"non\s+(dispongo|trovo)\s+di",
        r"non\s+c['']?è\s+(una\s+)?definizione",
        r"non\s+viene\s+(definit|specificat)",
        r"informazioni\s+(non\s+)?disponibil[ei]",
        r"(non\s+sono|non\s+sono)\s+disponibil[ei]",
    ]
    
    # Pattern per estrarre termini cercati
    TERM_EXTRACTION_PATTERNS = [
        r"(?:cos['']?è|cosa\s+significa|definizione\s+di)\s+[\"']?([A-Za-z0-9_\-]+)[\"']?",
        r"(?:che\s+cos['']?è)\s+(?:il\s+|la\s+|l[''])?[\"']?([A-Za-z0-9_\-]+)[\"']?",
        r"(?:spiegami)\s+(?:il\s+termine\s+)?[\"']?([A-Za-z0-9_\-]+)[\"']?",
        r"[\"']([A-Z][A-Za-z0-9_\-]+)[\"']",  # Termini tra virgolette
        r"(?:acronimo|sigla)\s+([A-Z]+)",
        r"(?:termine|parola)\s+[\"']?([A-Za-z0-9_\-]+)[\"']?",
    ]
    
    def __init__(
        self,
        glossary_resolver=None,
        retrieval_score_threshold: float = 0.4,
        gap_score_threshold: float = 0.6
    ):
        """
        Inizializza detector.
        
        Args:
            glossary_resolver: Istanza GlossaryResolver per verifica termini
            retrieval_score_threshold: Soglia sotto cui score è "basso"
            gap_score_threshold: Soglia sopra cui è "lacuna"
        """
        self.glossary = glossary_resolver
        self.retrieval_threshold = retrieval_score_threshold
        self.gap_threshold = gap_score_threshold
        
        # Compila pattern regex
        self._uncertainty_re = [
            re.compile(p, re.IGNORECASE) for p in self.UNCERTAINTY_PATTERNS
        ]
        self._term_re = [
            re.compile(p, re.IGNORECASE) for p in self.TERM_EXTRACTION_PATTERNS
        ]
        
        logger.info(
            f"GapDetector inizializzato: retrieval_threshold={retrieval_score_threshold}, "
            f"gap_threshold={gap_score_threshold}"
        )
    
    def detect_gap(
        self,
        query: str,
        response: str,
        sources: List[Any],  # RetrievedDoc
        glossary_context: Optional[str] = None
    ) -> GapDetection:
        """
        Analizza query/risposta per rilevare lacune.
        
        Args:
            query: Query utente originale
            response: Risposta LLM generata
            sources: Documenti recuperati (con .score, .text, .doc_id)
            glossary_context: Contesto glossario usato (opzionale)
            
        Returns:
            GapDetection con risultato analisi
        """
        signals = []
        gap_score = 0.0
        missing_term = None
        found_in_docs = []
        snippets = []
        
        # ═══════════════════════════════════════════════════════════════
        # SIGNAL 1: Score retrieval
        # ═══════════════════════════════════════════════════════════════
        
        if not sources:
            signals.append(GapSignal.NO_SOURCES)
            gap_score += 0.4
            logger.debug("[Gap] Signal: NO_SOURCES (+0.4)")
        else:
            scores = [getattr(s, 'score', 0) for s in sources]
            max_score = max(scores) if scores else 0
            avg_score = sum(scores) / len(scores) if scores else 0
            
            if max_score < self.retrieval_threshold:
                signals.append(GapSignal.LOW_RETRIEVAL_SCORE)
                # Score più basso = gap score più alto
                score_penalty = 0.3 * (1 - max_score / self.retrieval_threshold)
                gap_score += score_penalty
                logger.debug(f"[Gap] Signal: LOW_SCORE max={max_score:.2f} (+{score_penalty:.2f})")
        
        # ═══════════════════════════════════════════════════════════════
        # SIGNAL 2: Pattern incertezza LLM
        # ═══════════════════════════════════════════════════════════════
        
        uncertainty_match = self._detect_uncertainty(response)
        if uncertainty_match:
            signals.append(GapSignal.LLM_UNCERTAINTY)
            gap_score += 0.35
            logger.debug(f"[Gap] Signal: LLM_UNCERTAINTY pattern='{uncertainty_match}' (+0.35)")
        
        # ═══════════════════════════════════════════════════════════════
        # SIGNAL 3 & 4: Termine e glossario
        # ═══════════════════════════════════════════════════════════════
        
        missing_term = self._extract_key_term(query)
        
        if missing_term:
            logger.debug(f"[Gap] Termine estratto: '{missing_term}'")
            
            # Verifica glossario
            in_glossary = self._term_in_glossary(missing_term)
            
            if not in_glossary:
                signals.append(GapSignal.TERM_NOT_IN_GLOSSARY)
                gap_score += 0.25
                logger.debug(f"[Gap] Signal: TERM_NOT_IN_GLOSSARY (+0.25)")
                
                # Cerca dove appare il termine nei doc
                found_in_docs, snippets = self._find_term_in_docs(missing_term, sources)
                
                if found_in_docs:
                    signals.append(GapSignal.TERM_NO_DEFINITION)
                    gap_score += 0.1
                    logger.debug(f"[Gap] Signal: TERM_NO_DEFINITION in {found_in_docs} (+0.1)")
        
        # ═══════════════════════════════════════════════════════════════
        # DETERMINAZIONE FINALE
        # ═══════════════════════════════════════════════════════════════
        
        gap_score = min(1.0, gap_score)
        is_gap = gap_score >= self.gap_threshold
        suggested_action = self._suggest_action(signals, missing_term)
        
        logger.info(
            f"[Gap] Risultato: is_gap={is_gap}, score={gap_score:.2f}, "
            f"signals={[s.value for s in signals]}, term={missing_term}"
        )
        
        return GapDetection(
            is_gap=is_gap,
            gap_score=gap_score,
            signals=signals,
            missing_term=missing_term,
            found_in_docs=found_in_docs,
            suggested_action=suggested_action,
            snippets=snippets[:3]  # Max 3 snippet
        )
    
    def _detect_uncertainty(self, response: str) -> Optional[str]:
        """
        Rileva pattern di incertezza nella risposta LLM.
        
        Returns:
            Pattern matchato o None
        """
        response_lower = response.lower()
        
        for pattern_re in self._uncertainty_re:
            match = pattern_re.search(response_lower)
            if match:
                return match.group(0)
        
        return None
    
    def _extract_key_term(self, query: str) -> Optional[str]:
        """
        Estrae termine chiave dalla query.
        
        Strategie:
        1. Pattern espliciti ("cos'è X", "definizione di X")
        2. Acronimi (2-6 lettere maiuscole)
        3. Termini tra virgolette
        """
        # Prova pattern espliciti
        for pattern_re in self._term_re:
            match = pattern_re.search(query)
            if match:
                term = match.group(1)
                # Normalizza: rimuovi punteggiatura finale
                term = re.sub(r'[?!.,;:]+$', '', term).strip()
                if len(term) >= 2:
                    return term.upper()
        
        # Fallback: cerca acronimi (2-6 lettere maiuscole)
        acronyms = re.findall(r'\b([A-Z]{2,6})\b', query)
        
        # Filtra acronimi comuni non rilevanti
        exclude = {'PS', 'IL', 'MR', 'ISO', 'SGI', 'PDF', 'DOC', 'WO'}
        acronyms = [a for a in acronyms if a not in exclude]
        
        if acronyms:
            return acronyms[0]
        
        return None
    
    def _term_in_glossary(self, term: str) -> bool:
        """Verifica se termine è nel glossario"""
        if not self.glossary:
            return False
        
        try:
            result = self.glossary.resolve(term)
            return result is not None
        except Exception:
            return False
    
    def _find_term_in_docs(
        self,
        term: str,
        sources: List[Any]
    ) -> Tuple[List[str], List[str]]:
        """
        Trova documenti dove il termine appare.
        
        Returns:
            Tuple (lista doc_id, lista snippet)
        """
        found_docs = []
        snippets = []
        term_lower = term.lower()
        
        for source in sources:
            text = getattr(source, 'text', '')
            doc_id = getattr(source, 'doc_id', 'unknown')
            
            if term_lower in text.lower():
                found_docs.append(doc_id)
                
                # Estrai snippet
                snippet = self._extract_snippet(text, term)
                if snippet:
                    snippets.append(f"{doc_id}: \"{snippet}\"")
        
        return list(set(found_docs)), snippets
    
    def _extract_snippet(self, text: str, term: str, context_chars: int = 50) -> Optional[str]:
        """Estrae snippet con termine evidenziato"""
        text_lower = text.lower()
        term_lower = term.lower()
        
        pos = text_lower.find(term_lower)
        if pos == -1:
            return None
        
        start = max(0, pos - context_chars)
        end = min(len(text), pos + len(term) + context_chars)
        
        snippet = text[start:end]
        
        # Aggiungi ellipsis se troncato
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        
        return snippet.strip()
    
    def _suggest_action(
        self,
        signals: List[GapSignal],
        missing_term: Optional[str]
    ) -> str:
        """Suggerisce azione basata sui segnali"""
        
        if GapSignal.TERM_NOT_IN_GLOSSARY in signals:
            return "add_glossary"
        
        if GapSignal.NO_SOURCES in signals:
            return "request_docs"
        
        if GapSignal.LOW_RETRIEVAL_SCORE in signals:
            return "improve_indexing"
        
        if GapSignal.LLM_UNCERTAINTY in signals:
            return "review_response"
        
        return "none"


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    # Mock per test
    class MockSource:
        def __init__(self, doc_id, text, score):
            self.doc_id = doc_id
            self.text = text
            self.score = score
    
    detector = GapDetector(glossary_resolver=None)
    
    print("=== TEST GAP DETECTION ===\n")
    
    # Test 1: Query con risposta incerta
    print("Test 1: Risposta incerta")
    gap = detector.detect_gap(
        query="Cos'è WCM?",
        response="Non ho trovato una definizione specifica di WCM nei documenti.",
        sources=[MockSource("PS-06_01", "strumenti WCM per il miglioramento", 0.35)]
    )
    print(f"  is_gap: {gap.is_gap}")
    print(f"  score: {gap.gap_score:.2f}")
    print(f"  signals: {[s.value for s in gap.signals]}")
    print(f"  term: {gap.missing_term}")
    print(f"  action: {gap.suggested_action}")
    print()
    
    # Test 2: Query con risposta OK
    print("Test 2: Risposta OK")
    gap = detector.detect_gap(
        query="Come gestire le NC?",
        response="La gestione delle NC è definita nella procedura PS-08_01...",
        sources=[MockSource("PS-08_01", "gestione non conformità...", 0.85)]
    )
    print(f"  is_gap: {gap.is_gap}")
    print(f"  score: {gap.gap_score:.2f}")
    print(f"  signals: {[s.value for s in gap.signals]}")
    print()
    
    # Test 3: Nessun documento
    print("Test 3: Nessun documento")
    gap = detector.detect_gap(
        query="Cos'è XYZ123?",
        response="Non dispongo di informazioni su XYZ123.",
        sources=[]
    )
    print(f"  is_gap: {gap.is_gap}")
    print(f"  score: {gap.gap_score:.2f}")
    print(f"  signals: {[s.value for s in gap.signals]}")
    print(f"  term: {gap.missing_term}")
    print()
    
    # Test 4: Pattern incertezza
    print("Test 4: Pattern incertezza")
    test_responses = [
        "Non ho trovato informazioni specifiche",
        "Non risulta presente nei documenti",
        "Manca una definizione chiara",
        "Non sono in grado di rispondere",
        "Nei documenti non emerge questo concetto",
    ]
    
    for resp in test_responses:
        match = detector._detect_uncertainty(resp)
        status = "✅" if match else "❌"
        print(f"  {status} '{resp[:40]}...' → {match}")
    
    print("\n=== TEST TERM EXTRACTION ===\n")
    
    test_queries = [
        "Cos'è WCM?",
        "Cosa significa FMEA?",
        "Definizione di RPN",
        "Spiegami il termine Kaizen",
        'Che cos\'è "lean"?',
        "Come funziona la ISO 9001?",
        "Dimmi del modulo MR-07_05",
    ]
    
    for q in test_queries:
        term = detector._extract_key_term(q)
        print(f"  '{q}' → {term}")

