"""
Behavior Analyzer per R08-R10
Analizza segnali impliciti per rilevare pattern comportamentali

Created: 2025-12-08

Pattern rilevabili:
- Preferenze (formato, stile risposta)
- Interessi (topic, documenti specifici)
- Frustrazioni (query senza risposta)
- Expertise (livello tecnico utente)
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict

from ..signals.signal_types import SignalType, ImplicitSignal, SIGNAL_WEIGHTS

logger = logging.getLogger(__name__)


@dataclass
class BehaviorPattern:
    """Pattern comportamentale rilevato"""
    pattern_type: str           # "preference", "interest", "frustration", "expertise"
    confidence: float           # 0-1
    description: str            # Descrizione human-readable
    evidence: List[str] = field(default_factory=list)  # Lista segnali di supporto
    suggested_action: str = ""  # "add_memory", "adjust_boost", "alert_admin"
    memory_content: str = ""    # Contenuto da salvare come memoria (se applicabile)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "confidence": self.confidence,
            "description": self.description,
            "evidence": self.evidence,
            "suggested_action": self.suggested_action,
            "memory_content": self.memory_content
        }


class BehaviorAnalyzer:
    """
    Analizza segnali impliciti per rilevare pattern comportamentali.
    
    Pattern rilevabili:
    - Preferenze formato risposta (brevi/dettagliate, elenchi/prose)
    - Interessi per topic/documenti specifici
    - Frustrazioni (query problematiche)
    - Livello expertise utente
    
    Example:
        >>> analyzer = BehaviorAnalyzer()
        >>> patterns = analyzer.analyze_user("mario", signals)
        >>> for p in patterns:
        ...     print(f"{p.pattern_type}: {p.description}")
    """
    
    # Soglie per pattern detection
    PREFERENCE_MIN_SIGNALS = 3      # Segnali minimi per preferenza
    INTEREST_MIN_SIGNALS = 4        # Segnali minimi per interesse
    FRUSTRATION_THRESHOLD = 0.5     # Ratio negativi per frustrazione
    EXPERTISE_MIN_QUERIES = 5       # Query minime per expertise
    
    def __init__(self):
        logger.info("BehaviorAnalyzer inizializzato")
    
    def analyze_user(
        self,
        user_id: str,
        signals: List[ImplicitSignal]
    ) -> List[BehaviorPattern]:
        """
        Analizza comportamento utente e rileva pattern.
        
        Args:
            user_id: ID utente
            signals: Lista segnali dell'utente
            
        Returns:
            Lista pattern rilevati
        """
        if not signals:
            return []
        
        patterns = []
        
        # 1. Analisi preferenze formato risposta
        pref_patterns = self._detect_response_preferences(signals)
        patterns.extend(pref_patterns)
        
        # 2. Analisi interessi topic/documenti
        interest_patterns = self._detect_interests(signals)
        patterns.extend(interest_patterns)
        
        # 3. Analisi frustrazioni
        frustration_patterns = self._detect_frustrations(signals)
        patterns.extend(frustration_patterns)
        
        # 4. Analisi expertise level
        expertise = self._infer_expertise(signals)
        if expertise:
            patterns.append(expertise)
        
        logger.info(f"[Behavior] User {user_id}: {len(patterns)} pattern rilevati")
        
        return patterns
    
    def _detect_response_preferences(
        self,
        signals: List[ImplicitSignal]
    ) -> List[BehaviorPattern]:
        """
        Rileva preferenze sul formato risposta.
        
        Analizza:
        - Dwell time medio (breve = preferisce conciso)
        - Pattern di copia (bullet points vs prose)
        - Scroll depth (legge tutto o solo inizio)
        """
        patterns = []
        
        # === Analizza dwell time ===
        dwell_signals = [s for s in signals if s.signal_type == SignalType.DWELL_TIME and s.value]
        
        if len(dwell_signals) >= self.PREFERENCE_MIN_SIGNALS:
            avg_dwell = sum(s.value for s in dwell_signals) / len(dwell_signals)
            
            if avg_dwell < 10:
                patterns.append(BehaviorPattern(
                    pattern_type="preference",
                    confidence=0.7,
                    description="Preferisce risposte concise e dirette",
                    evidence=[f"Dwell time medio: {avg_dwell:.1f}s su {len(dwell_signals)} risposte"],
                    suggested_action="add_memory",
                    memory_content="L'utente preferisce risposte brevi e dirette. Evitare prolissità."
                ))
            elif avg_dwell > 45:
                patterns.append(BehaviorPattern(
                    pattern_type="preference",
                    confidence=0.7,
                    description="Preferisce risposte dettagliate e approfondite",
                    evidence=[f"Dwell time medio: {avg_dwell:.1f}s su {len(dwell_signals)} risposte"],
                    suggested_action="add_memory",
                    memory_content="L'utente preferisce risposte dettagliate con approfondimenti."
                ))
        
        # === Analizza pattern di copia ===
        copy_signals = [s for s in signals if s.signal_type == SignalType.COPY_TEXT and s.content]
        
        if len(copy_signals) >= self.PREFERENCE_MIN_SIGNALS:
            # Cerca pattern nel contenuto copiato
            bullet_copies = sum(
                1 for s in copy_signals 
                if s.content and ('•' in s.content or '- ' in s.content[:20] or '1.' in s.content[:10])
            )
            
            bullet_ratio = bullet_copies / len(copy_signals)
            
            if bullet_ratio > 0.6:
                patterns.append(BehaviorPattern(
                    pattern_type="preference",
                    confidence=0.8,
                    description="Preferisce risposte con elenchi puntati",
                    evidence=[f"{bullet_copies}/{len(copy_signals)} copie contengono elenchi"],
                    suggested_action="add_memory",
                    memory_content="L'utente preferisce risposte formattate con elenchi puntati."
                ))
            elif bullet_ratio < 0.2 and len(copy_signals) >= 5:
                patterns.append(BehaviorPattern(
                    pattern_type="preference",
                    confidence=0.6,
                    description="Preferisce risposte in formato discorsivo",
                    evidence=[f"Solo {bullet_copies}/{len(copy_signals)} copie con elenchi"],
                    suggested_action="add_memory",
                    memory_content="L'utente preferisce risposte discorsive piuttosto che elenchi."
                ))
        
        # === Analizza scroll depth ===
        scroll_signals = [s for s in signals if s.signal_type == SignalType.SCROLL_DEPTH and s.value]
        
        if len(scroll_signals) >= self.PREFERENCE_MIN_SIGNALS:
            avg_scroll = sum(s.value for s in scroll_signals) / len(scroll_signals)
            
            if avg_scroll < 0.3:
                patterns.append(BehaviorPattern(
                    pattern_type="preference",
                    confidence=0.6,
                    description="Legge principalmente l'inizio delle risposte",
                    evidence=[f"Scroll depth medio: {avg_scroll:.0%}"],
                    suggested_action="add_memory",
                    memory_content="L'utente tende a leggere solo l'inizio. Mettere info importanti all'inizio."
                ))
        
        return patterns
    
    def _detect_interests(
        self,
        signals: List[ImplicitSignal]
    ) -> List[BehaviorPattern]:
        """
        Rileva interessi per topic/documenti specifici.
        
        Analizza:
        - Documenti cliccati frequentemente
        - Topic delle query (da metadata)
        - Acronimi cercati
        """
        patterns = []
        
        # === Conta interazioni per documento ===
        doc_interactions: Dict[str, float] = defaultdict(float)
        
        for signal in signals:
            if signal.doc_id:
                weight = abs(SIGNAL_WEIGHTS.get(signal.signal_type, 0.1))
                doc_interactions[signal.doc_id] += weight
        
        # Top documenti con score significativo
        if doc_interactions:
            top_docs = sorted(doc_interactions.items(), key=lambda x: x[1], reverse=True)
            
            for doc_id, score in top_docs[:3]:
                if score >= self.INTEREST_MIN_SIGNALS * 0.3:
                    # Estrai tipo documento da ID
                    doc_type = doc_id.split("-")[0] if "-" in doc_id else "DOC"
                    
                    patterns.append(BehaviorPattern(
                        pattern_type="interest",
                        confidence=min(0.9, score / 3),
                        description=f"Interesse elevato per documento {doc_id}",
                        evidence=[f"Interaction score: {score:.2f}"],
                        suggested_action="add_memory",
                        memory_content=f"L'utente consulta frequentemente il documento {doc_id} ({doc_type})."
                    ))
        
        # === Analizza topic da metadata query ===
        query_topics: Dict[str, int] = defaultdict(int)
        
        for signal in signals:
            if signal.metadata and "query" in signal.metadata:
                query = signal.metadata["query"].lower()
                
                # Pattern topic
                topic_patterns = {
                    "rifiuti": ["rifiuti", "smaltimento", "ambientale"],
                    "sicurezza": ["sicurezza", "infortunio", "dpi", "rischio"],
                    "qualità": ["qualità", "nc", "non conformità", "audit"],
                    "formazione": ["formazione", "corso", "addestramento"],
                    "manutenzione": ["manutenzione", "guasto", "intervento"]
                }
                
                for topic, keywords in topic_patterns.items():
                    if any(kw in query for kw in keywords):
                        query_topics[topic] += 1
        
        # Rileva topic dominanti
        for topic, count in query_topics.items():
            if count >= self.INTEREST_MIN_SIGNALS:
                patterns.append(BehaviorPattern(
                    pattern_type="interest",
                    confidence=min(0.85, count / 10),
                    description=f"Focus su tematiche di {topic}",
                    evidence=[f"{count} query relative a {topic}"],
                    suggested_action="add_memory",
                    memory_content=f"L'utente è particolarmente interessato a tematiche di {topic}."
                ))
        
        return patterns
    
    def _detect_frustrations(
        self,
        signals: List[ImplicitSignal]
    ) -> List[BehaviorPattern]:
        """
        Rileva pattern di frustrazione/insoddisfazione.
        
        Segnali:
        - Quick dismiss frequenti
        - Re-ask/retry frequenti
        - Abort teach frequenti
        """
        patterns = []
        
        # Conta segnali negativi
        negative_types = [
            SignalType.QUICK_DISMISS,
            SignalType.RE_ASK_QUERY,
            SignalType.RETRY_DIFFERENT,
            SignalType.TEACH_ABORT,
            SignalType.MEMORY_REJECTED
        ]
        
        negative_signals = [s for s in signals if s.signal_type in negative_types]
        
        if len(signals) > 5:
            frustration_ratio = len(negative_signals) / len(signals)
            
            if frustration_ratio > self.FRUSTRATION_THRESHOLD:
                # Analizza query problematiche
                problem_queries = set()
                for s in negative_signals:
                    if s.metadata and "query" in s.metadata:
                        problem_queries.add(s.metadata["query"][:50])
                    elif s.content:
                        problem_queries.add(s.content[:50])
                
                patterns.append(BehaviorPattern(
                    pattern_type="frustration",
                    confidence=frustration_ratio,
                    description=f"Alto livello di insoddisfazione ({frustration_ratio:.0%} segnali negativi)",
                    evidence=[
                        f"{len(negative_signals)}/{len(signals)} segnali negativi",
                        f"Query problematiche: {len(problem_queries)}"
                    ],
                    suggested_action="alert_admin"
                ))
        
        # Analizza specificamente re-ask (indica risposta non soddisfacente)
        reask_signals = [s for s in signals if s.signal_type == SignalType.RE_ASK_QUERY]
        
        if len(reask_signals) >= 3:
            patterns.append(BehaviorPattern(
                pattern_type="frustration",
                confidence=0.7,
                description="Riformula frequentemente le query",
                evidence=[f"{len(reask_signals)} riformulazioni rilevate"],
                suggested_action="alert_admin"
            ))
        
        return patterns
    
    def _infer_expertise(
        self,
        signals: List[ImplicitSignal]
    ) -> Optional[BehaviorPattern]:
        """
        Inferisce livello di expertise utente.
        
        Indicatori:
        - Uso termini tecnici nelle query
        - Velocità di lettura (dwell time breve + scroll completo = esperto)
        - Tipo documenti consultati (MR, PS = tecnico)
        """
        # Analizza termini tecnici nelle query
        tech_terms = 0
        total_queries = 0
        
        for signal in signals:
            if signal.metadata and "query" in signal.metadata:
                query = signal.metadata["query"].lower()
                total_queries += 1
                
                # Pattern tecnici specifici ISO/SGI
                tech_patterns = [
                    "procedura", "modulo mr-", "requisito", "norma",
                    "iso", "audit", "non conformità", "nc", "fmea",
                    "azione correttiva", "riesame", "kpi", "processo"
                ]
                if any(p in query for p in tech_patterns):
                    tech_terms += 1
        
        if total_queries < self.EXPERTISE_MIN_QUERIES:
            return None
        
        tech_ratio = tech_terms / total_queries
        
        # Analizza anche documenti consultati
        doc_types = defaultdict(int)
        for signal in signals:
            if signal.doc_id:
                doc_type = signal.doc_id.split("-")[0]
                doc_types[doc_type] += 1
        
        # PS e MR indicano utente tecnico
        technical_docs = doc_types.get("PS", 0) + doc_types.get("MR", 0)
        total_docs = sum(doc_types.values()) or 1
        doc_tech_ratio = technical_docs / total_docs
        
        # Combina indicatori
        combined_score = (tech_ratio * 0.6) + (doc_tech_ratio * 0.4)
        
        if combined_score > 0.6:
            return BehaviorPattern(
                pattern_type="expertise",
                confidence=combined_score,
                description="Utente esperto (alta frequenza termini tecnici e documenti PS/MR)",
                evidence=[
                    f"Tech ratio query: {tech_ratio:.1%}",
                    f"Doc tecnici: {technical_docs}/{total_docs}"
                ],
                suggested_action="add_memory",
                memory_content="L'utente ha competenze tecniche avanzate. Può ricevere risposte più tecniche."
            )
        elif combined_score < 0.2:
            return BehaviorPattern(
                pattern_type="expertise",
                confidence=1 - combined_score,
                description="Utente base (bassa frequenza termini tecnici)",
                evidence=[
                    f"Tech ratio query: {tech_ratio:.1%}",
                    f"Doc tecnici: {technical_docs}/{total_docs}"
                ],
                suggested_action="add_memory",
                memory_content="L'utente preferisce spiegazioni semplici. Evitare gergo troppo tecnico."
            )
        
        return None
    
    def get_actionable_patterns(
        self,
        patterns: List[BehaviorPattern]
    ) -> List[BehaviorPattern]:
        """
        Filtra pattern con azioni suggerite.
        
        Returns:
            Pattern con suggested_action != ""
        """
        return [p for p in patterns if p.suggested_action]
    
    def get_memory_candidates(
        self,
        patterns: List[BehaviorPattern]
    ) -> List[Dict[str, Any]]:
        """
        Estrae candidati per aggiunta a memoria.
        
        Returns:
            Lista {content, type, confidence}
        """
        candidates = []
        
        for pattern in patterns:
            if pattern.suggested_action == "add_memory" and pattern.memory_content:
                candidates.append({
                    "content": pattern.memory_content,
                    "type": "preference" if pattern.pattern_type == "preference" else "fact",
                    "confidence": pattern.confidence,
                    "source_pattern": pattern.pattern_type
                })
        
        return candidates


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    from ..signals.signal_types import SignalType, ImplicitSignal
    from datetime import datetime
    
    print("=== TEST BEHAVIOR ANALYZER ===\n")
    
    analyzer = BehaviorAnalyzer()
    
    # Genera segnali di test
    signals = []
    
    # Simula utente che preferisce risposte brevi
    for i in range(5):
        signals.append(ImplicitSignal(
            id=f"sig_{i}",
            signal_type=SignalType.DWELL_TIME,
            user_id="mario",
            session_id="sess_1",
            timestamp=datetime.now(),
            value=8  # Dwell time basso
        ))
    
    # Simula copie di elenchi
    for i in range(4):
        signals.append(ImplicitSignal(
            id=f"sig_copy_{i}",
            signal_type=SignalType.COPY_TEXT,
            user_id="mario",
            session_id="sess_1",
            timestamp=datetime.now(),
            content="• Punto 1\n• Punto 2\n• Punto 3"
        ))
    
    # Simula interesse per documento
    for i in range(5):
        signals.append(ImplicitSignal(
            id=f"sig_doc_{i}",
            signal_type=SignalType.CLICK_SOURCE,
            user_id="mario",
            session_id="sess_1",
            timestamp=datetime.now(),
            doc_id="PS-06_01"
        ))
    
    # Simula query tecniche
    for i in range(6):
        signals.append(ImplicitSignal(
            id=f"sig_q_{i}",
            signal_type=SignalType.DWELL_TIME,
            user_id="mario",
            session_id="sess_1",
            timestamp=datetime.now(),
            value=20,
            metadata={"query": "Come gestire le NC secondo la procedura ISO?"}
        ))
    
    # Analizza
    patterns = analyzer.analyze_user("mario", signals)
    
    print(f"Pattern rilevati: {len(patterns)}\n")
    
    for p in patterns:
        print(f"[{p.pattern_type.upper()}] {p.description}")
        print(f"  Confidence: {p.confidence:.1%}")
        print(f"  Evidence: {p.evidence}")
        if p.memory_content:
            print(f"  Memory: {p.memory_content[:60]}...")
        print()
    
    # Test memory candidates
    candidates = analyzer.get_memory_candidates(patterns)
    print(f"Memory candidates: {len(candidates)}")
    
    print("\n✅ Test completati!")

