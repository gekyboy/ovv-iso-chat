"""
Acronym Extractor per OVV ISO Chat
Estrae automaticamente definizioni di acronimi dai documenti

R05 - Estrazione automatica acronimi
Created: 2025-12-08

Pattern supportati:
- "ABC (Alpha Beta Gamma)" - parentesi dopo
- "(Alpha Beta Gamma) ABC" - parentesi prima
- "ABC significa Alpha Beta" - connettivo italiano
- "ABC = Alpha Beta" / "ABC: Alpha Beta" - uguale/due punti
- "ABC, ovvero Alpha Beta" - connettivo italiano
"""

import re
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Tipi di pattern riconosciuti"""
    PARENTHESIS_AFTER = "parenthesis_after"    # ABC (Alpha Beta)
    PARENTHESIS_BEFORE = "parenthesis_before"  # (Alpha Beta) ABC
    SIGNIFICA = "significa"                     # ABC significa Alpha
    EQUALS = "equals"                          # ABC = Alpha Beta
    OVVERO = "ovvero"                          # ABC, ovvero Alpha


@dataclass
class AcronymProposal:
    """Proposta di acronimo estratto"""
    id: str
    acronym: str
    expansion: str
    pattern_type: str  # PatternType.value
    confidence: float
    found_in_docs: List[str] = field(default_factory=list)
    snippets: List[str] = field(default_factory=list)
    extracted_at: str = ""
    status: str = "pending"  # pending, approved, rejected
    admin_note: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Serializza per JSON"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "AcronymProposal":
        """Deserializza da JSON"""
        return cls(**data)


class AcronymExtractor:
    """
    Estrae definizioni acronimi dal testo dei documenti.
    
    Features:
    - 5 pattern regex per italiano/inglese
    - Validazione con match iniziali
    - Blacklist falsi positivi
    - Confidence score
    - Persistenza proposte
    
    Example:
        >>> extractor = AcronymExtractor()
        >>> proposals = extractor.extract_from_text(text, doc_id="PS-06_01")
        >>> for p in proposals:
        ...     print(f"{p.acronym} = {p.expansion} ({p.confidence:.0%})")
    """
    
    # Blacklist acronimi comuni/falsi positivi
    BLACKLIST = {
        # Articoli e preposizioni italiane
        "IL", "LA", "LO", "LE", "GLI", "UN", "UNA", "UNO",
        "DEL", "DI", "DA", "IN", "PER", "CON", "SU", "TRA", "FRA",
        "SE", "NO", "SI", "MA", "ED", "OH", "AI", "AL", "ALLA",
        "CHE", "CHI", "CUI", "OVE",
        
        # Codici documento (già gestiti dal sistema)
        "PS", "MR", "WO", "REV", "CAP", "ART", "PAG", "FIG", "TAB", "ALL",
        
        # Standard/Norme (già nel glossario)
        "ISO", "UNI", "EN", "CEI", "IATF", "VDA",
        
        # File extensions
        "PDF", "DOC", "XLS", "PPT", "TXT", "CSV", "XML", "HTML",
        
        # Comuni generici
        "OK", "KO", "VS", "USA", "EU", "IT", "UK", "NR", "NS", "VS",
        "ECC", "ETC", "IVA", "SRL", "SPA", "SNC",
        
        # Troppo generici
        "TOT", "MAX", "MIN", "AVG", "QTA", "NR", "RIF", "VER",
    }
    
    # Pattern regex con gruppi nominati per chiarezza
    # Nota: [A-Z0-9] permette acronimi che iniziano con numero (es. 5S)
    PATTERNS = [
        # Pattern 1: ABC (Alpha Beta Gamma) - anche 5S (Sort Set...)
        (PatternType.PARENTHESIS_AFTER,
         r'\b([A-Z0-9][A-Z0-9]{1,7})\s*\(\s*([A-Z][a-zA-Zàèéìòùç][a-zA-Zàèéìòùç\s\-\'\.]{2,80})\s*\)'),
        
        # Pattern 2: (Alpha Beta Gamma) ABC
        (PatternType.PARENTHESIS_BEFORE,
         r'\(\s*([A-Z][a-zA-Zàèéìòùç][a-zA-Zàèéìòùç\s\-\'\.]{2,80})\s*\)\s*\(?([A-Z0-9][A-Z0-9]{1,7})\)?'),
        
        # Pattern 3: ABC significa/vuol dire/sta per Alpha Beta
        (PatternType.SIGNIFICA,
         r'\b([A-Z][A-Z0-9]{1,7})\s+(?:significa|vuol\s+dire|sta\s+per|è\s+l\'acronimo\s+di)\s+["\']?([A-Z][a-zA-Zàèéìòùç][a-zA-Zàèéìòùç\s\-\'\.]{2,80})["\']?'),
        
        # Pattern 4: ABC = Alpha Beta / ABC: Alpha Beta
        (PatternType.EQUALS,
         r'\b([A-Z][A-Z0-9]{1,7})\s*[=:]\s*["\']?([A-Z][a-zA-Zàèéìòùç][a-zA-Zàèéìòùç\s\-\'\.]{2,80})["\']?'),
        
        # Pattern 5: ABC, ovvero/cioè/ossia Alpha Beta (con o senza virgola)
        (PatternType.OVVERO,
         r'\b([A-Z][A-Z0-9]{1,7})\s*[,]?\s*(?:ovvero|cioè|ossia|vale\s+a\s+dire)\s+["\']?([A-Z][a-zA-Zàèéìòùç][a-zA-Zàèéìòùç\s\-\'\.]{2,80})["\']?'),
    ]
    
    def __init__(
        self,
        glossary_resolver=None,
        proposals_path: str = "config/acronym_proposals.json",
        min_confidence: float = 0.6
    ):
        """
        Inizializza extractor.
        
        Args:
            glossary_resolver: GlossaryResolver per check duplicati
            proposals_path: Path file JSON proposte
            min_confidence: Soglia minima confidence (0-1)
        """
        self.glossary = glossary_resolver
        self.proposals_path = Path(proposals_path)
        self.min_confidence = min_confidence
        
        # Cache proposte in memoria
        self._proposals: Dict[str, AcronymProposal] = {}
        
        # Compila pattern regex
        self._compiled_patterns = [
            (ptype, re.compile(pattern, re.UNICODE))
            for ptype, pattern in self.PATTERNS
        ]
        
        # Crea directory se non esiste
        self.proposals_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Carica proposte esistenti
        self._load_proposals()
        
        logger.info(
            f"AcronymExtractor: {len(self._proposals)} proposte, "
            f"min_confidence={min_confidence}"
        )
    
    def _generate_id(self, acronym: str) -> str:
        """Genera ID univoco per acronimo"""
        return f"acr_{hashlib.md5(acronym.lower().encode()).hexdigest()[:12]}"
    
    def _load_proposals(self):
        """Carica proposte da file"""
        if not self.proposals_path.exists():
            return
        
        try:
            with open(self.proposals_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for prop_id, prop_data in data.items():
                self._proposals[prop_id] = AcronymProposal.from_dict(prop_data)
            
            logger.debug(f"Caricate {len(self._proposals)} proposte acronimi")
            
        except Exception as e:
            logger.error(f"Errore caricamento proposte: {e}")
    
    def _save_proposals(self):
        """Salva proposte su file"""
        try:
            data = {
                prop_id: prop.to_dict()
                for prop_id, prop in self._proposals.items()
            }
            
            with open(self.proposals_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Salvate {len(self._proposals)} proposte")
            
        except Exception as e:
            logger.error(f"Errore salvataggio proposte: {e}")
    
    def extract_from_text(
        self,
        text: str,
        doc_id: str = "unknown"
    ) -> List[AcronymProposal]:
        """
        Estrae acronimi da un testo.
        
        Args:
            text: Testo da analizzare
            doc_id: ID documento sorgente
            
        Returns:
            Lista di proposte con confidence >= min_confidence
        """
        if not text or len(text) < 10:
            return []
        
        proposals = []
        seen_acronyms: Set[str] = set()
        
        for pattern_type, pattern_re in self._compiled_patterns:
            for match in pattern_re.finditer(text):
                # Estrai acronimo ed espansione in base al pattern
                if pattern_type == PatternType.PARENTHESIS_BEFORE:
                    expansion_raw = match.group(1).strip()
                    acronym_raw = match.group(2).strip()
                else:
                    acronym_raw = match.group(1).strip()
                    expansion_raw = match.group(2).strip()
                
                # Normalizza
                acronym = acronym_raw.upper()
                expansion = self._clean_expansion(expansion_raw)
                
                # Skip se già processato in questo testo
                if acronym in seen_acronyms:
                    continue
                seen_acronyms.add(acronym)
                
                # Valida e calcola confidence
                confidence = self._validate(acronym, expansion)
                
                if confidence >= self.min_confidence:
                    # Estrai snippet per contesto
                    snippet = self._extract_snippet(text, match.start(), match.end())
                    
                    # Crea o aggiorna proposta
                    proposal = self._create_or_update_proposal(
                        acronym=acronym,
                        expansion=expansion,
                        pattern_type=pattern_type,
                        confidence=confidence,
                        doc_id=doc_id,
                        snippet=snippet
                    )
                    
                    if proposal:
                        proposals.append(proposal)
        
        if proposals:
            self._save_proposals()
            logger.info(f"[R05] Estratti {len(proposals)} acronimi da {doc_id}")
        
        return proposals
    
    def _clean_expansion(self, expansion: str) -> str:
        """Pulisce espansione da caratteri extra"""
        # Rimuovi punteggiatura finale
        expansion = re.sub(r'[,;:\.\!\?]+$', '', expansion)
        
        # Rimuovi virgolette
        expansion = expansion.strip('"\'')
        
        # Normalizza spazi
        expansion = ' '.join(expansion.split())
        
        return expansion
    
    def _validate(self, acronym: str, expansion: str) -> float:
        """
        Valida estrazione e calcola confidence score.
        
        Args:
            acronym: Acronimo estratto
            expansion: Espansione estratta
            
        Returns:
            Confidence score 0-1
        """
        # ═══════════════════════════════════════════════════════════════
        # FILTRI ELIMINATORI (ritorna 0)
        # ═══════════════════════════════════════════════════════════════
        
        # Check 1: Lunghezza acronimo (2-8 caratteri)
        if not (2 <= len(acronym) <= 8):
            return 0.0
        
        # Check 2: Solo lettere maiuscole e numeri nell'acronimo
        # Può iniziare con numero (es. 5S) o lettera
        if not re.match(r'^[A-Z0-9][A-Z0-9]+$', acronym):
            return 0.0
        
        # Check 3: Acronimo in blacklist
        if acronym in self.BLACKLIST:
            return 0.0
        
        # Check 4: Già nel glossario
        if self.glossary:
            try:
                if self.glossary.resolve(acronym):
                    return 0.0  # Skip se già presente
            except Exception:
                pass
        
        # Check 5: Espansione troppo corta
        if len(expansion) < 5:
            return 0.0
        
        # Check 6: Espansione deve avere almeno 2 parole
        words = [w for w in expansion.split() if len(w) >= 2]
        if len(words) < 2:
            return 0.0
        
        # ═══════════════════════════════════════════════════════════════
        # CALCOLO SCORE (accumula punti)
        # ═══════════════════════════════════════════════════════════════
        
        score = 0.0
        
        # Punti base per aver passato i filtri
        score += 0.35
        
        # Bonus: Match iniziali
        initials = ''.join(w[0].upper() for w in words if w[0].isalpha())
        
        if acronym == initials:
            score += 0.45  # Match perfetto
        elif len(initials) >= 2:
            # Match parziale
            common = 0
            for i, char in enumerate(acronym):
                if i < len(initials) and char == initials[i]:
                    common += 1
            
            if common >= 2:
                match_ratio = common / max(len(acronym), len(initials))
                score += 0.30 * match_ratio
            else:
                score += 0.05  # Pattern valido ma iniziali non matchano
        
        # Bonus: Espansione abbastanza lunga
        if len(expansion) >= 15:
            score += 0.10
        
        # Bonus: Numero parole ragionevole (2-6)
        if 2 <= len(words) <= 6:
            score += 0.10
        
        return min(1.0, score)
    
    def _extract_snippet(
        self,
        text: str,
        start: int,
        end: int,
        context: int = 60
    ) -> str:
        """Estrae snippet con contesto"""
        snippet_start = max(0, start - context)
        snippet_end = min(len(text), end + context)
        
        snippet = text[snippet_start:snippet_end]
        
        # Aggiungi ellipsis se troncato
        if snippet_start > 0:
            snippet = "..." + snippet
        if snippet_end < len(text):
            snippet = snippet + "..."
        
        # Normalizza whitespace
        snippet = ' '.join(snippet.split())
        
        return snippet
    
    def _create_or_update_proposal(
        self,
        acronym: str,
        expansion: str,
        pattern_type: PatternType,
        confidence: float,
        doc_id: str,
        snippet: str
    ) -> Optional[AcronymProposal]:
        """Crea nuova proposta o aggiorna esistente"""
        prop_id = self._generate_id(acronym)
        
        existing = self._proposals.get(prop_id)
        
        if existing:
            # Aggiorna proposta esistente
            if doc_id not in existing.found_in_docs:
                existing.found_in_docs.append(doc_id)
            
            if snippet and snippet not in existing.snippets:
                existing.snippets.append(snippet)
                # Mantieni max 3 snippet
                existing.snippets = existing.snippets[:3]
            
            # Aggiorna confidence se migliore
            if confidence > existing.confidence:
                existing.confidence = confidence
                existing.expansion = expansion  # Usa espansione migliore
            
            return existing
        
        # Crea nuova proposta
        proposal = AcronymProposal(
            id=prop_id,
            acronym=acronym,
            expansion=expansion,
            pattern_type=pattern_type.value,
            confidence=confidence,
            found_in_docs=[doc_id],
            snippets=[snippet] if snippet else [],
            extracted_at=datetime.now().isoformat(),
            status="pending"
        )
        
        self._proposals[prop_id] = proposal
        
        logger.debug(f"[R05] Nuova proposta: {acronym} = {expansion} ({confidence:.0%})")
        
        return proposal
    
    # ═══════════════════════════════════════════════════════════════
    # GESTIONE PROPOSTE (per Admin)
    # ═══════════════════════════════════════════════════════════════
    
    def get_pending(self, limit: int = 20) -> List[AcronymProposal]:
        """
        Ottiene proposte pending ordinate per confidence.
        
        Args:
            limit: Massimo risultati
            
        Returns:
            Lista ordinata per confidence desc
        """
        pending = [
            p for p in self._proposals.values()
            if p.status == "pending"
        ]
        
        # Ordina per confidence (più alta prima)
        pending.sort(key=lambda x: x.confidence, reverse=True)
        
        return pending[:limit]
    
    def get_all(self, status: Optional[str] = None) -> List[AcronymProposal]:
        """Ottiene tutte le proposte, opzionalmente filtrate per status"""
        if status:
            return [p for p in self._proposals.values() if p.status == status]
        return list(self._proposals.values())
    
    def get(self, prop_id: str) -> Optional[AcronymProposal]:
        """Ottiene proposta per ID"""
        return self._proposals.get(prop_id)
    
    def get_by_acronym(self, acronym: str) -> Optional[AcronymProposal]:
        """Ottiene proposta per acronimo"""
        prop_id = self._generate_id(acronym)
        return self._proposals.get(prop_id)
    
    def approve(self, acronym: str, admin_note: str = "") -> Optional[AcronymProposal]:
        """
        Admin approva proposta.
        
        Args:
            acronym: Acronimo da approvare
            admin_note: Nota opzionale
            
        Returns:
            Proposta aggiornata o None
        """
        prop_id = self._generate_id(acronym)
        proposal = self._proposals.get(prop_id)
        
        if not proposal:
            logger.warning(f"[R05] Proposta non trovata: {acronym}")
            return None
        
        proposal.status = "approved"
        proposal.admin_note = admin_note
        
        self._save_proposals()
        
        logger.info(f"[R05] Approvato: {acronym} = {proposal.expansion}")
        
        return proposal
    
    def reject(self, acronym: str, reason: str) -> Optional[AcronymProposal]:
        """
        Admin rifiuta proposta.
        
        Args:
            acronym: Acronimo da rifiutare
            reason: Motivo del rifiuto
            
        Returns:
            Proposta aggiornata o None
        """
        prop_id = self._generate_id(acronym)
        proposal = self._proposals.get(prop_id)
        
        if not proposal:
            logger.warning(f"[R05] Proposta non trovata: {acronym}")
            return None
        
        proposal.status = "rejected"
        proposal.admin_note = reason
        
        self._save_proposals()
        
        logger.info(f"[R05] Rifiutato: {acronym} ({reason})")
        
        return proposal
    
    def delete(self, acronym: str) -> bool:
        """Elimina proposta"""
        prop_id = self._generate_id(acronym)
        
        if prop_id in self._proposals:
            del self._proposals[prop_id]
            self._save_proposals()
            return True
        
        return False
    
    def get_stats(self) -> Dict:
        """Statistiche per Admin"""
        proposals = list(self._proposals.values())
        
        stats = {
            "total": len(proposals),
            "pending": len([p for p in proposals if p.status == "pending"]),
            "approved": len([p for p in proposals if p.status == "approved"]),
            "rejected": len([p for p in proposals if p.status == "rejected"]),
            "by_pattern": {},
            "top_confidence": []
        }
        
        # Conta per pattern
        for p in proposals:
            ptype = p.pattern_type
            stats["by_pattern"][ptype] = stats["by_pattern"].get(ptype, 0) + 1
        
        # Top confidence pending
        pending = [p for p in proposals if p.status == "pending"]
        pending.sort(key=lambda x: x.confidence, reverse=True)
        stats["top_confidence"] = [
            {"acronym": p.acronym, "expansion": p.expansion[:40], "confidence": p.confidence}
            for p in pending[:5]
        ]
        
        return stats


# Singleton instance
_extractor: Optional[AcronymExtractor] = None


def get_acronym_extractor(glossary_resolver=None) -> AcronymExtractor:
    """Ottiene istanza singleton AcronymExtractor"""
    global _extractor
    if _extractor is None:
        _extractor = AcronymExtractor(glossary_resolver=glossary_resolver)
    return _extractor


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    extractor = AcronymExtractor(proposals_path="config/acronym_proposals_test.json")
    
    print("=== TEST ACRONYM EXTRACTOR ===\n")
    
    # Testi con vari pattern
    test_texts = [
        # Pattern 1: parentesi dopo
        "Gli strumenti del WCM (World Class Manufacturing) sono fondamentali.",
        
        # Pattern 2: parentesi prima
        "Il (Total Quality Management) TQM è un approccio sistemico.",
        
        # Pattern 3: significa
        "FMEA significa Failure Mode and Effects Analysis.",
        
        # Pattern 4: uguale
        "PDCA = Plan Do Check Act",
        
        # Pattern 5: ovvero
        "Il DMAIC, ovvero Define Measure Analyze Improve Control, è usato nel Six Sigma.",
        
        # Casi italiani
        "La NC (Non Conformità) deve essere registrata.",
        "L'OEE, cioè Overall Equipment Effectiveness, misura l'efficienza.",
        
        # Caso con due punti
        "RPN: Risk Priority Number, calcolato come prodotto di S, O, D.",
        
        # Casi che NON dovrebbero matchare
        "Il PS-06_01 definisce la procedura.",  # PS è in blacklist
        "L'ISO 9001 è lo standard.",  # ISO è in blacklist
    ]
    
    print("=== TEST ESTRAZIONE ===\n")
    
    for i, text in enumerate(test_texts, 1):
        print(f"Test {i}: \"{text[:60]}...\"")
        proposals = extractor.extract_from_text(text, doc_id=f"TEST_{i:02d}")
        
        if proposals:
            for p in proposals:
                print(f"  ✅ {p.acronym} = {p.expansion} ({p.confidence:.0%})")
        else:
            print("  ❌ Nessun acronimo estratto")
        print()
    
    # Test validazione
    print("=== TEST VALIDAZIONE ===\n")
    
    test_cases = [
        ("WCM", "World Class Manufacturing"),  # Match perfetto
        ("FMEA", "Failure Mode and Effects Analysis"),  # Match perfetto
        ("NC", "Non Conformità"),  # Match parziale
        ("ABC", "Something Completely Different"),  # No match
        ("PS", "Procedura Sistema"),  # Blacklist
        ("A", "Too Short"),  # Troppo corto
    ]
    
    for acronym, expansion in test_cases:
        confidence = extractor._validate(acronym, expansion)
        status = "✅" if confidence >= 0.6 else "❌"
        reason = "BLACKLIST" if acronym in extractor.BLACKLIST else f"{confidence:.0%}"
        print(f"  {status} {acronym} = {expansion} → {reason}")
    
    # Stats
    print("\n=== STATISTICHE ===\n")
    stats = extractor.get_stats()
    print(f"  Totale: {stats['total']}")
    print(f"  Pending: {stats['pending']}")
    print(f"  Per pattern: {stats['by_pattern']}")
    
    # Cleanup test file
    import os
    if Path("config/acronym_proposals_test.json").exists():
        os.remove("config/acronym_proposals_test.json")
    
    print("\n✅ Test completati!")

