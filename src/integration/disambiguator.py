"""
R06: Disambiguatore Contestuale per OVV ISO Chat v2.0
=====================================================

Disambigua acronimi in modo intelligente usando:
- CONTESTO della query (60%) - Keywords che indicano il significato
- PREFERENZE utente soft (25%) - Suggerimenti basati su scelte passate  
- FREQUENZA nel dominio (15%) - Quanto è comune in ambito ISO

Principi:
- NON è un sistema rigido: si comporta come una persona normale
- Se l'incertezza è alta, CHIEDE all'utente (con suggerimento)
- Le preferenze sono suggerimenti, il contesto domina

Features fuse da entrambe le implementazioni:
- Analisi contestuale con keywords (da v1)
- Integrazione con GlossaryResolver (da v2)
- Persistenza preferenze per utente separati (da v2)
- Override tracking (da v1)
- Opzione "solo questa sessione" (da v2)
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURAZIONE
# ============================================================

# Soglia di certezza: se la differenza tra i top 2 score è >= questa soglia,
# usa il significato migliore senza chiedere
# Abbassato da 0.35 a 0.20 per rispettare meglio le preferenze utente salvate
CERTAINTY_THRESHOLD = 0.20

# Pesi per il calcolo dello score finale
WEIGHT_CONTEXT = 0.60      # Il contesto domina
WEIGHT_PREFERENCE = 0.25   # Preferenze sono suggerimenti
WEIGHT_FREQUENCY = 0.15    # Frequenza nel dominio

# Keywords per ogni significato degli acronimi ambigui
# Queste integrano le definizioni dal glossary.json
CONTEXT_KEYWORDS = {
    "NC": {
        "qualità": [
            "qualità", "audit", "procedura", "difetto", "reclamo", "ispezione",
            "requisito", "ISO", "certificazione", "verifica", "controllo",
            "prodotto", "processo", "sistema", "gestione", "PS-08", "IL-08",
            "CAPA", "azione correttiva", "registrazione", "segnalazione",
            "conformità", "non conformità", "NC tipo"
        ],
        "contabilità": [
            "fattura", "contabilità", "ciclo attivo", "cliente", "rimborso",
            "storno", "credito", "pagamento", "amministrazione", "finanza",
            "commerciale", "vendita", "emesso", "importo", "euro", "contabile"
        ]
    },
    "AC": {
        "qualità": [
            "NC", "non conformità", "causa", "correzione", "CAPA", "audit",
            "qualità", "miglioramento", "procedura", "registrazione",
            "azione", "correttiva", "preventiva", "root cause"
        ],
        "climatizzazione": [
            "temperatura", "clima", "impianto", "manutenzione", "HVAC",
            "raffreddamento", "comfort", "ambiente", "condizionatore", "aria"
        ]
    },
    "PM": {
        "manutenzione": [
            "manutenzione", "pillar", "WCM", "guasto", "macchina",
            "attrezzatura", "intervento", "TPM", "fermi", "professional",
            "tecnico", "riparazione", "asset"
        ],
        "pianificazione": [
            "preventiva", "piano", "programmata", "schedule", "calendario",
            "periodicità", "ispezione", "check"
        ],
        "gestione": [
            "progetto", "project", "responsabile", "team", "milestone", 
            "pianificazione", "risorse", "budget", "deliverable", "manager"
        ]
    },
    "QC": {
        "qualità": [
            "controllo", "qualità", "ispezione", "collaudo", "test",
            "verifica", "prodotto", "campione", "specifica", "pillar",
            "WCM", "zero difetti"
        ],
        "produzione": [
            "setup", "cambio", "attrezzaggio", "SMED", "lean",
            "tempo", "riduzione", "produzione", "quick", "change"
        ]
    },
    "CDL": {
        "produzione": [
            "macchina", "CNC", "centro", "fresatura", "lavorazione",
            "utensile", "tornio", "multiasse", "meccanica"
        ],
        "processo": [
            "ciclo", "sequenza", "operazioni", "fasi", "lavorazione",
            "routing", "tempi", "metodo"
        ]
    }
}

# Frequenza base nel dominio ISO (quanto è comune ogni significato)
DOMAIN_FREQUENCY = {
    "NC": {"qualità": 0.85, "contabilità": 0.15},
    "AC": {"qualità": 0.90, "climatizzazione": 0.10},
    "PM": {"manutenzione": 0.50, "pianificazione": 0.35, "gestione": 0.15},
    "QC": {"qualità": 0.85, "produzione": 0.15},
    "CDL": {"produzione": 0.70, "processo": 0.30}
}


# ============================================================
# DATACLASSES
# ============================================================

@dataclass
class AcronymMeaning:
    """Un possibile significato di un acronimo"""
    acronym: str
    context: str                      # Es. "qualità"
    full: str                         # Es. "Non Conformità"
    description: str                  # Descrizione estesa
    context_keywords: List[str] = field(default_factory=list)
    related_docs: List[str] = field(default_factory=list)
    domain_frequency: float = 0.5     # Frequenza base nel dominio (0-1)


@dataclass
class UserPreference:
    """Preferenza utente per un acronimo (soft, non rigida)"""
    acronym: str
    preferred_context: str            # Es. "qualità"
    preferred_meaning: str            # Es. "Non Conformità"
    times_selected: int = 1
    last_selected: datetime = field(default_factory=datetime.now)
    override_count: int = 0           # Volte che il contesto ha vinto sulla preferenza
    
    def to_dict(self) -> Dict:
        return {
            "acronym": self.acronym,
            "preferred_context": self.preferred_context,
            "preferred_meaning": self.preferred_meaning,
            "times_selected": self.times_selected,
            "last_selected": self.last_selected.isoformat(),
            "override_count": self.override_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "UserPreference":
        data = data.copy()
        if "last_selected" in data:
            data["last_selected"] = datetime.fromisoformat(data["last_selected"])
        # Retrocompatibilità: se manca preferred_context, usa preferred_meaning come fallback
        if "preferred_context" not in data and "preferred_meaning" in data:
            data["preferred_context"] = data["preferred_meaning"].lower()
        return cls(**data)


@dataclass
class DisambiguationResult:
    """Risultato della disambiguazione"""
    acronym: str
    chosen_meaning: str               # Significato scelto
    chosen_context: str               # Contesto scelto (es. "qualità")
    confidence: float                 # 0-1
    is_certain: bool                  # True se confidence > threshold
    all_meanings: List[Tuple[str, str, float]]  # [(context, meaning, score), ...]
    context_used: str                 # Keywords che hanno influenzato la decisione
    preference_applied: bool          # Se la preferenza utente ha influito


@dataclass
class AmbiguousAcronymMatch:
    """Risultato detection di un acronimo ambiguo nella query"""
    acronym: str                      # Es. "NC"
    position: int                     # Posizione nella query
    meanings: List[AcronymMeaning]    # Lista significati possibili
    disambiguation_result: Optional[DisambiguationResult] = None
    
    @property
    def needs_user_input(self) -> bool:
        """True se serve input utente per disambiguare"""
        if self.disambiguation_result is None:
            return True
        return not self.disambiguation_result.is_certain


@dataclass
class QueryDisambiguationResult:
    """Risultato completo della disambiguazione di una query"""
    original_query: str
    needs_disambiguation: bool        # Se serve interazione utente
    ambiguous_matches: List[AmbiguousAcronymMatch]
    resolved_query: Optional[str]     # Query con acronimi risolti (se tutti certi)
    
    @property
    def first_unresolved(self) -> Optional[AmbiguousAcronymMatch]:
        """Ritorna il primo acronimo che necessita input utente"""
        for match in self.ambiguous_matches:
            if match.needs_user_input:
                return match
        return None


# ============================================================
# PREFERENCE STORE
# ============================================================

class UserPreferenceStore:
    """
    Gestisce preferenze utente per acronimi ambigui.
    Ogni utente ha il proprio file JSON in data/persist/acronym_preferences/
    """
    
    def __init__(self, persist_dir: str = "data/persist/acronym_preferences"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache in memoria: user_id -> {acronym -> UserPreference}
        self._cache: Dict[str, Dict[str, UserPreference]] = {}
        
        logger.info(f"UserPreferenceStore: persist_dir={self.persist_dir}")
    
    def _get_user_file(self, user_id: str) -> Path:
        """Genera path file preferenze per utente"""
        safe_id = re.sub(r'[^\w\-]', '_', user_id)
        return self.persist_dir / f"{safe_id}_prefs.json"
    
    def _load_user_prefs(self, user_id: str) -> Dict[str, UserPreference]:
        """Carica preferenze utente da file (con cache)"""
        if user_id in self._cache:
            return self._cache[user_id]
        
        file_path = self._get_user_file(user_id)
        
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    prefs = {}
                    for acronym, pref_data in data.get("preferences", {}).items():
                        prefs[acronym.upper()] = UserPreference.from_dict(pref_data)
                    self._cache[user_id] = prefs
                    return prefs
            except Exception as e:
                logger.warning(f"Errore lettura preferenze {user_id}: {e}")
        
        self._cache[user_id] = {}
        return self._cache[user_id]
    
    def _save_user_prefs(self, user_id: str) -> bool:
        """Salva preferenze utente su file"""
        if user_id not in self._cache:
            return False
        
        file_path = self._get_user_file(user_id)
        try:
            data = {
                "user_id": user_id,
                "updated_at": datetime.now().isoformat(),
                "preferences": {
                    acronym: pref.to_dict()
                    for acronym, pref in self._cache[user_id].items()
                }
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Errore salvataggio preferenze {user_id}: {e}")
            return False
    
    def get_preference(self, user_id: str, acronym: str) -> Optional[UserPreference]:
        """Ottiene preferenza utente per un acronimo"""
        prefs = self._load_user_prefs(user_id)
        return prefs.get(acronym.upper())
    
    def save_choice(
        self,
        user_id: str,
        acronym: str,
        chosen_context: str,
        chosen_meaning: str,
        was_context_override: bool = False,
        session_only: bool = False
    ) -> bool:
        """
        Salva la scelta dell'utente.
        
        Args:
            user_id: ID utente
            acronym: Acronimo (es. "NC")
            chosen_context: Contesto scelto (es. "qualità")
            chosen_meaning: Significato scelto (es. "Non Conformità")
            was_context_override: True se il contesto ha prevalso sulla preferenza
            session_only: Se True, salva solo in cache (non su file)
        """
        acronym = acronym.upper()
        prefs = self._load_user_prefs(user_id)
        
        if acronym in prefs:
            pref = prefs[acronym]
            if pref.preferred_context == chosen_context:
                # Conferma preferenza esistente
                pref.times_selected += 1
                pref.last_selected = datetime.now()
            else:
                if was_context_override:
                    # Il contesto ha vinto, incrementa override_count
                    pref.override_count += 1
                else:
                    # L'utente ha cambiato idea
                    pref.preferred_context = chosen_context
                    pref.preferred_meaning = chosen_meaning
                    pref.times_selected = 1
                    pref.last_selected = datetime.now()
        else:
            # Nuova preferenza
            prefs[acronym] = UserPreference(
                acronym=acronym,
                preferred_context=chosen_context,
                preferred_meaning=chosen_meaning
            )
        
        logger.info(f"[R06] Preferenza: {user_id}/{acronym} -> {chosen_context} (persist={not session_only})")
        
        if not session_only:
            return self._save_user_prefs(user_id)
        return True
    
    def clear_preference(self, user_id: str, acronym: str) -> bool:
        """Rimuove preferenza per un acronimo"""
        prefs = self._load_user_prefs(user_id)
        if acronym.upper() in prefs:
            del prefs[acronym.upper()]
            return self._save_user_prefs(user_id)
        return True
    
    def get_stats(self) -> Dict:
        """Statistiche globali preferenze"""
        stats = {"total_users": 0, "total_preferences": 0, "by_acronym": {}}
        
        for file_path in self.persist_dir.glob("*_prefs.json"):
            stats["total_users"] += 1
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    prefs = data.get("preferences", {})
                    stats["total_preferences"] += len(prefs)
                    for acronym in prefs:
                        acr = acronym.upper()
                        stats["by_acronym"][acr] = stats["by_acronym"].get(acr, 0) + 1
            except:
                pass
        
        return stats


# ============================================================
# CONTEXTUAL DISAMBIGUATOR
# ============================================================

class ContextualDisambiguator:
    """
    Disambigua acronimi in modo contestuale e intelligente.
    
    Workflow:
    1. detect_ambiguous_in_query() trova acronimi ambigui
    2. Per ogni acronimo, calcola score per ogni significato
    3. Se certezza alta → risolve automaticamente
    4. Se certezza bassa → chiede all'utente con suggerimento
    5. resolve_with_choice() applica scelta utente
    """
    
    def __init__(
        self,
        glossary_resolver=None,
        preference_store: Optional[UserPreferenceStore] = None,
        certainty_threshold: float = CERTAINTY_THRESHOLD
    ):
        """
        Args:
            glossary_resolver: GlossaryResolver per leggere acronimi da glossary.json
            preference_store: Store preferenze (default: crea nuovo)
            certainty_threshold: Soglia per decisione automatica (0-1)
        """
        self.glossary = glossary_resolver
        self.preference_store = preference_store or UserPreferenceStore()
        self.certainty_threshold = certainty_threshold
        
        # Pattern per estrarre acronimi (2-6 caratteri maiuscoli)
        self.acronym_pattern = re.compile(r'\b([A-Z][A-Z0-9]{1,5})\b')
        
        logger.info(f"ContextualDisambiguator inizializzato (threshold={certainty_threshold})")
    
    def _get_meanings_for_acronym(self, acronym: str) -> List[AcronymMeaning]:
        """
        Ottiene tutti i significati per un acronimo ambiguo.
        Prima prova dal glossary.json, poi usa CONTEXT_KEYWORDS come fallback.
        """
        acronym = acronym.upper()
        meanings = []
        
        # Prova dal glossary (integrazione con GlossaryResolver)
        if self.glossary and hasattr(self.glossary, 'get_all_meanings'):
            try:
                glossary_meanings = self.glossary.get_all_meanings(acronym)
                if glossary_meanings:
                    for m in glossary_meanings:
                        context = m.get("context", "default")
                        meanings.append(AcronymMeaning(
                            acronym=acronym,
                            context=context,
                            full=m.get("full", ""),
                            description=m.get("description", ""),
                            context_keywords=CONTEXT_KEYWORDS.get(acronym, {}).get(context, []),
                            domain_frequency=DOMAIN_FREQUENCY.get(acronym, {}).get(context, 0.5)
                        ))
                    return meanings
            except Exception as e:
                logger.debug(f"Glossary lookup fallito per {acronym}: {e}")
        
        # Fallback: usa CONTEXT_KEYWORDS
        if acronym in CONTEXT_KEYWORDS:
            for context, keywords in CONTEXT_KEYWORDS[acronym].items():
                freq = DOMAIN_FREQUENCY.get(acronym, {}).get(context, 0.5)
                meanings.append(AcronymMeaning(
                    acronym=acronym,
                    context=context,
                    full=f"{acronym} ({context})",
                    description=f"Significato in ambito {context}",
                    context_keywords=keywords,
                    domain_frequency=freq
                ))
        
        return meanings
    
    def is_ambiguous(self, acronym: str) -> bool:
        """Verifica se un acronimo è ambiguo"""
        # Check glossary
        if self.glossary and hasattr(self.glossary, 'is_ambiguous'):
            try:
                if self.glossary.is_ambiguous(acronym):
                    return True
            except:
                pass
        
        # Check CONTEXT_KEYWORDS
        return acronym.upper() in CONTEXT_KEYWORDS
    
    def disambiguate(
        self,
        acronym: str,
        query: str,
        user_id: str = "default"
    ) -> DisambiguationResult:
        """
        Disambigua un singolo acronimo usando contesto + preferenze soft.
        
        Args:
            acronym: L'acronimo da disambiguare (es. "NC")
            query: La query completa dell'utente (per contesto)
            user_id: ID utente per preferenze
            
        Returns:
            DisambiguationResult con la scelta e la confidence
        """
        acronym = acronym.upper()
        meanings = self._get_meanings_for_acronym(acronym)
        
        if not meanings:
            return DisambiguationResult(
                acronym=acronym,
                chosen_meaning="",
                chosen_context="",
                confidence=1.0,
                is_certain=True,
                all_meanings=[],
                context_used="",
                preference_applied=False
            )
        
        if len(meanings) == 1:
            return DisambiguationResult(
                acronym=acronym,
                chosen_meaning=meanings[0].full,
                chosen_context=meanings[0].context,
                confidence=1.0,
                is_certain=True,
                all_meanings=[(meanings[0].context, meanings[0].full, 1.0)],
                context_used="",
                preference_applied=False
            )
        
        # Calcola score per ogni significato
        scores = []
        query_lower = query.lower()
        context_matches = []
        
        # Ottieni preferenza utente
        user_pref = self.preference_store.get_preference(user_id, acronym)
        
        for meaning in meanings:
            # 1. Context score (60%)
            context_score, matched_kw = self._calculate_context_score(query_lower, meaning)
            context_matches.extend(matched_kw)
            
            # 2. Preference score (25%)
            preference_score, pref_applied = self._calculate_preference_score(
                user_pref, meaning.context
            )
            
            # 3. Frequency score (15%)
            frequency_score = meaning.domain_frequency
            
            # Score finale pesato
            final_score = (
                context_score * WEIGHT_CONTEXT +
                preference_score * WEIGHT_PREFERENCE +
                frequency_score * WEIGHT_FREQUENCY
            )
            
            scores.append((meaning.context, meaning.full, final_score, pref_applied))
        
        # Ordina per score decrescente
        scores.sort(key=lambda x: -x[2])
        
        # Calcola gap tra top 2
        top_score = scores[0][2]
        second_score = scores[1][2] if len(scores) > 1 else 0
        gap = top_score - second_score
        
        # Determina se siamo certi
        is_certain = gap >= self.certainty_threshold
        
        # Normalizza scores
        total = sum(s[2] for s in scores)
        if total > 0:
            normalized = [(c, m, s/total) for c, m, s, _ in scores]
        else:
            normalized = [(c, m, 1/len(scores)) for c, m, _, _ in scores]
        
        return DisambiguationResult(
            acronym=acronym,
            chosen_meaning=scores[0][1],
            chosen_context=scores[0][0],
            confidence=normalized[0][2],
            is_certain=is_certain,
            all_meanings=normalized,
            context_used=", ".join(list(set(context_matches))[:5]),
            preference_applied=scores[0][3]
        )
    
    def _calculate_context_score(
        self,
        query_lower: str,
        meaning: AcronymMeaning
    ) -> Tuple[float, List[str]]:
        """
        Calcola score basato sul contesto della query.
        Ritorna (score, matched_keywords)
        """
        if not meaning.context_keywords:
            return (0.5, [])  # Neutro se nessuna keyword definita
        
        matched = []
        for keyword in meaning.context_keywords:
            if keyword.lower() in query_lower:
                matched.append(keyword)
        
        if not matched:
            return (0.1, [])  # Score minimo se nessun match
        
        # Formula: più match = score più alto, con plateau
        score = min(1.0, 0.3 + (len(matched) / min(len(meaning.context_keywords), 5)) * 0.7)
        
        return (score, matched)
    
    def _calculate_preference_score(
        self,
        user_pref: Optional[UserPreference],
        context: str
    ) -> Tuple[float, bool]:
        """
        Calcola score basato su preferenza utente.
        Ritorna (score, preference_was_applied)
        """
        if user_pref is None:
            return (0.5, False)  # Neutro
        
        if user_pref.preferred_context == context:
            # Boost per preferenza, ma NON dominante
            # Boost diminuisce se spesso il contesto ha vinto
            override_ratio = user_pref.override_count / max(user_pref.times_selected, 1)
            boost = max(0.6, 1.0 - override_ratio * 0.3)
            return (boost, True)
        else:
            return (0.4, False)  # Leggera penalità
    
    def detect_ambiguous_in_query(
        self,
        query: str,
        user_id: str = "default"
    ) -> QueryDisambiguationResult:
        """
        Trova acronimi ambigui nella query e tenta di disambiguarli.
        
        Args:
            query: Query utente
            user_id: ID utente per check preferenze
            
        Returns:
            QueryDisambiguationResult con info su acronimi trovati
        """
        if not query:
            return QueryDisambiguationResult(
                original_query=query,
                needs_disambiguation=False,
                ambiguous_matches=[],
                resolved_query=query
            )
        
        # Estrai potenziali acronimi
        potential_acronyms = self.acronym_pattern.findall(query.upper())
        
        # Deduplica mantenendo ordine
        seen: Set[str] = set()
        unique_acronyms = []
        for a in potential_acronyms:
            if a not in seen:
                seen.add(a)
                unique_acronyms.append(a)
        
        ambiguous_matches: List[AmbiguousAcronymMatch] = []
        
        for acronym in unique_acronyms:
            if not self.is_ambiguous(acronym):
                continue
            
            meanings = self._get_meanings_for_acronym(acronym)
            if not meanings:
                continue
            
            # Trova posizione nella query originale
            position = -1
            match_obj = re.search(rf'\b{re.escape(acronym)}\b', query, re.IGNORECASE)
            if match_obj:
                position = match_obj.start()
            
            # Disambigua
            result = self.disambiguate(acronym, query, user_id)
            
            ambiguous_matches.append(AmbiguousAcronymMatch(
                acronym=acronym,
                position=position,
                meanings=meanings,
                disambiguation_result=result
            ))
        
        # Determina se serve input utente
        needs_disambiguation = any(m.needs_user_input for m in ambiguous_matches)
        
        # Se tutti sono certi, genera query risolta
        resolved_query = None
        if ambiguous_matches and not needs_disambiguation:
            resolved_query = self._resolve_query(query, ambiguous_matches)
        elif not ambiguous_matches:
            resolved_query = query
        
        logger.debug(
            f"[R06] detect_ambiguous: query='{query[:30]}...', "
            f"found={[m.acronym for m in ambiguous_matches]}, "
            f"needs_user={needs_disambiguation}"
        )
        
        return QueryDisambiguationResult(
            original_query=query,
            needs_disambiguation=needs_disambiguation,
            ambiguous_matches=ambiguous_matches,
            resolved_query=resolved_query
        )
    
    def _resolve_query(
        self,
        query: str,
        matches: List[AmbiguousAcronymMatch]
    ) -> str:
        """Espande acronimi nella query con i significati disambiguati"""
        resolved = query
        
        for match in matches:
            if match.disambiguation_result and match.disambiguation_result.chosen_meaning:
                # Espandi: "NC" -> "NC (Non Conformità)"
                pattern = rf'\b{re.escape(match.acronym)}\b'
                replacement = f"{match.acronym} ({match.disambiguation_result.chosen_meaning})"
                resolved = re.sub(pattern, replacement, resolved, count=1, flags=re.IGNORECASE)
        
        return resolved
    
    def resolve_with_choice(
        self,
        query: str,
        acronym: str,
        chosen_context: str,
        user_id: str = "default",
        remember: bool = True,
        session_only: bool = False
    ) -> str:
        """
        Risolve query con scelta utente e opzionalmente salva preferenza.
        
        Args:
            query: Query originale
            acronym: Acronimo disambiguato
            chosen_context: Contesto scelto (es. "qualità")
            user_id: ID utente
            remember: Se salvare preferenza
            session_only: Se True, salva solo per questa sessione
            
        Returns:
            Query con acronimo espanso
        """
        acronym = acronym.upper()
        meanings = self._get_meanings_for_acronym(acronym)
        
        # Trova il significato corrispondente al contesto
        chosen_meaning = ""
        for m in meanings:
            if m.context.lower() == chosen_context.lower():
                chosen_meaning = m.full
                break
        
        if not chosen_meaning:
            logger.warning(f"[R06] Contesto '{chosen_context}' non trovato per {acronym}")
            return query
        
        # Salva preferenza se richiesto
        if remember:
            self.preference_store.save_choice(
                user_id=user_id,
                acronym=acronym,
                chosen_context=chosen_context,
                chosen_meaning=chosen_meaning,
                was_context_override=False,
                session_only=session_only
            )
        
        logger.info(f"[R06] resolve_with_choice: {acronym} -> {chosen_context}/{chosen_meaning}")
        
        # Espandi nella query
        pattern = rf'\b{re.escape(acronym)}\b'
        return re.sub(
            pattern,
            f"{acronym} ({chosen_meaning})",
            query,
            count=1,
            flags=re.IGNORECASE
        )
    
    def format_disambiguation_question(
        self,
        match: AmbiguousAcronymMatch,
        user_id: str = "default"
    ) -> str:
        """
        Formatta la domanda di disambiguazione per l'utente.
        Include suggerimento basato su contesto e/o preferenza.
        """
        result = match.disambiguation_result
        user_pref = self.preference_store.get_preference(user_id, match.acronym)
        
        lines = [f"🔤 **{match.acronym}** può significare:\n"]
        
        for i, meaning in enumerate(match.meanings, 1):
            marker = ""
            
            # Marker per preferenza utente
            if user_pref and user_pref.preferred_context == meaning.context:
                marker = " ⭐ _tua preferenza abituale_"
            # Marker per suggerimento contestuale
            elif result and result.chosen_context == meaning.context and result.context_used:
                marker = f" 📍 _probabile dal contesto: {result.context_used}_"
            
            lines.append(f"**{i}. {meaning.full}**{marker}")
            
            if meaning.description:
                desc = meaning.description[:80] + "..." if len(meaning.description) > 80 else meaning.description
                lines.append(f"   _{desc}_")
            
            lines.append("")
        
        lines.append("❓ Quale intendi?")
        
        return "\n".join(lines)
    
    def get_context_for_meaning(
        self,
        acronym: str,
        full_name: str
    ) -> Optional[str]:
        """
        Trova il context corrispondente a un nome completo.
        """
        meanings = self._get_meanings_for_acronym(acronym)
        for m in meanings:
            if m.full.lower() == full_name.lower():
                return m.context
        return None


# ============================================================
# SINGLETON INSTANCES
# ============================================================

_disambiguator: Optional[ContextualDisambiguator] = None
_preference_store: Optional[UserPreferenceStore] = None


def get_preference_store() -> UserPreferenceStore:
    """Ottiene istanza singleton PreferenceStore"""
    global _preference_store
    if _preference_store is None:
        _preference_store = UserPreferenceStore()
    return _preference_store


def get_disambiguator(glossary_resolver=None) -> ContextualDisambiguator:
    """
    Ottiene istanza singleton ContextualDisambiguator.
    
    Args:
        glossary_resolver: GlossaryResolver da usare (opzionale)
        
    Returns:
        ContextualDisambiguator configurato
    """
    global _disambiguator, _preference_store
    
    if _disambiguator is None:
        _preference_store = get_preference_store()
        _disambiguator = ContextualDisambiguator(
            glossary_resolver=glossary_resolver,
            preference_store=_preference_store
        )
    
    return _disambiguator


def reset_singletons():
    """Reset singleton per test"""
    global _disambiguator, _preference_store
    _disambiguator = None
    _preference_store = None


# ============================================================
# CLI TEST
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    disambiguator = ContextualDisambiguator()
    
    print("=" * 60)
    print("Test 1: Query con NC e contesto qualità")
    result = disambiguator.detect_ambiguous_in_query(
        "Come gestire le NC dell'audit qualità?",
        user_id="test_user"
    )
    print(f"  needs_disambiguation: {result.needs_disambiguation}")
    if result.ambiguous_matches:
        match = result.ambiguous_matches[0]
        print(f"  {match.acronym}: {match.disambiguation_result.chosen_meaning}")
        print(f"  confidence: {match.disambiguation_result.confidence:.2f}")
        print(f"  context_used: {match.disambiguation_result.context_used}")
    print(f"  resolved_query: {result.resolved_query}")
    
    print("\n" + "=" * 60)
    print("Test 2: Query con NC senza contesto chiaro")
    result2 = disambiguator.detect_ambiguous_in_query(
        "Mostrami le NC",
        user_id="test_user"
    )
    print(f"  needs_disambiguation: {result2.needs_disambiguation}")
    if result2.first_unresolved:
        print(f"\n  Domanda disambiguazione:")
        print(disambiguator.format_disambiguation_question(result2.first_unresolved))
    
    print("\n" + "=" * 60)
    print("Test 3: Query con NC e contesto contabilità")
    result3 = disambiguator.detect_ambiguous_in_query(
        "Devo emettere una NC per la fattura del cliente",
        user_id="test_user"
    )
    print(f"  needs_disambiguation: {result3.needs_disambiguation}")
    if result3.ambiguous_matches:
        match = result3.ambiguous_matches[0]
        print(f"  {match.acronym}: {match.disambiguation_result.chosen_meaning}")
        print(f"  context_used: {match.disambiguation_result.context_used}")
    
    print("\n✅ Test completati!")
