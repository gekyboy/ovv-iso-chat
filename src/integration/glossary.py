"""
Glossary Resolver per OVV ISO Chat v3.2
Risolve acronimi e termini ISO/WCM con fuzzy match

Features:
- Caricamento statico da config/glossary.json
- Fuzzy match CPU-based (difflib)
- Query rewriting con espansione acronimi
- Dynamic update via memory
- Supporto acronimi ambigui con definizioni multiple
- Salvataggio modifiche nel glossario centrale
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from difflib import SequenceMatcher, get_close_matches
from datetime import datetime

import yaml

logger = logging.getLogger(__name__)


class GlossaryResolver:
    """
    Risolve acronimi e termini ISO/WCM
    """
    
    def __init__(
        self, 
        config: Optional[Dict] = None,
        config_path: Optional[str] = None,
        glossary_path: Optional[str] = None
    ):
        """
        Inizializza il resolver
        
        Args:
            config: Dizionario configurazione
            config_path: Percorso config.yaml
            glossary_path: Percorso glossary.json (override)
        """
        if config:
            self.config = config
        else:
            self.config = self._load_config(config_path)
        
        # Percorso glossary
        if glossary_path:
            self.glossary_path = Path(glossary_path)
        else:
            self.glossary_path = Path(
                self.config.get("memory", {}).get("glossary_path", "config/glossary.json")
            )
        
        # Dati glossario
        self.acronyms: Dict[str, Dict] = {}
        self.iso_standards: Dict[str, str] = {}
        self.chapters: Dict[str, str] = {}
        
        # Termini custom (da memory)
        self.custom_terms: Dict[str, str] = {}
        
        # Carica glossario
        self._load_glossary()
        
        logger.info(f"GlossaryResolver: {len(self.acronyms)} acronimi caricati")
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Carica configurazione"""
        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    
    def _load_glossary(self):
        """Carica glossario da JSON"""
        if not self.glossary_path.exists():
            logger.warning(f"Glossario non trovato: {self.glossary_path}")
            self._create_default_glossary()
            return
        
        try:
            with open(self.glossary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.acronyms = data.get("acronyms", {})
            self.iso_standards = data.get("iso_standards", {})
            self.chapters = data.get("chapters", {})
            
        except Exception as e:
            logger.error(f"Errore caricamento glossario: {e}")
            self._create_default_glossary()
    
    def _create_default_glossary(self):
        """Crea glossario default minimo"""
        self.acronyms = {
            "PS": {"full": "Procedura di Sistema", "description": "Documenti strategici"},
            "IL": {"full": "Istruzione di Lavoro", "description": "Procedure operative"},
            "MR": {"full": "Modulo di Registrazione", "description": "Template e form"},
            "SGI": {"full": "Sistema di Gestione Integrato", "description": "ISO 9001+14001+45001"},
            "WCM": {"full": "World Class Manufacturing", "description": "Metodologia eccellenza"},
            "EWO": {"full": "Emergency Work Order", "description": "Ordine emergenza"},
            "NC": {"full": "Non Conformità", "description": "Deviazione da standard"},
            "AC": {"full": "Azione Correttiva", "description": "Correzione non conformità"},
            "AP": {"full": "Azione Preventiva", "description": "Prevenzione problemi"},
            "OPL": {"full": "One Point Lesson", "description": "Formazione rapida"},
            "SOP": {"full": "Standard Operating Procedure", "description": "Procedura standard"},
            "TWTTP": {"full": "The Way To Teach People", "description": "Metodo formazione WCM"},
            "HERCA": {"full": "Human Error Root Cause Analysis", "description": "Analisi errore umano"},
            "5S": {"full": "Sort, Set, Shine, Standardize, Sustain", "description": "Metodologia ordine"},
            "FMEA": {"full": "Failure Mode and Effects Analysis", "description": "Analisi guasti"},
            "KPI": {"full": "Key Performance Indicator", "description": "Indicatore prestazione"}
        }
        
        self.iso_standards = {
            "9001": "Sistema di Gestione Qualità",
            "14001": "Sistema di Gestione Ambientale",
            "45001": "Sistema di Gestione Salute e Sicurezza"
        }
        
        self.chapters = {
            "4": "Contesto dell'organizzazione",
            "5": "Leadership",
            "6": "Pianificazione",
            "7": "Supporto",
            "8": "Attività operative",
            "9": "Valutazione delle prestazioni",
            "10": "Miglioramento"
        }
    
    def resolve_acronym(
        self, 
        acronym: str,
        context: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Risolve un acronimo, gestendo anche quelli ambigui.
        
        Args:
            acronym: Acronimo da risolvere (es. "PS", "WCM")
            context: Contesto per disambiguazione (es. "produzione", "processo")
            
        Returns:
            Dict con full, description o None.
            Per acronimi ambigui senza context, ritorna il default.
        """
        key = acronym.upper()
        
        if key in self.acronyms:
            data = self.acronyms[key]
            
            # Gestisci acronimi ambigui
            if data.get("ambiguous", False) and "definitions" in data:
                return self._resolve_ambiguous(data, context)
            
            return data
        
        # Cerca custom
        if key in self.custom_terms:
            return {"full": self.custom_terms[key], "description": "Custom term"}
        
        return None
    
    def _resolve_ambiguous(
        self, 
        data: Dict, 
        context: Optional[str] = None
    ) -> Dict:
        """
        Risolve un acronimo ambiguo usando il contesto.
        
        Args:
            data: Dati acronimo con definitions[]
            context: Contesto preferito
            
        Returns:
            Dict con full, description della definizione scelta
        """
        definitions = data.get("definitions", [])
        default_context = data.get("default_context")
        
        if not definitions:
            return {"full": "Sconosciuto", "description": "Nessuna definizione"}
        
        # Se c'è contesto, cerca match
        if context:
            for defn in definitions:
                if defn.get("context", "").lower() == context.lower():
                    return {
                        "full": defn.get("full", ""),
                        "description": defn.get("description", ""),
                        "context": defn.get("context", ""),
                        "ambiguous": True
                    }
        
        # Usa default context
        if default_context:
            for defn in definitions:
                if defn.get("context", "").lower() == default_context.lower():
                    return {
                        "full": defn.get("full", ""),
                        "description": defn.get("description", ""),
                        "context": defn.get("context", ""),
                        "ambiguous": True
                    }
        
        # Fallback: prima definizione
        first = definitions[0]
        return {
            "full": first.get("full", ""),
            "description": first.get("description", ""),
            "context": first.get("context", ""),
            "ambiguous": True
        }
    
    def is_ambiguous(self, acronym: str) -> bool:
        """
        Verifica se un acronimo ha significati multipli.
        
        Args:
            acronym: Acronimo da verificare
            
        Returns:
            True se ambiguo, False altrimenti
        """
        key = acronym.upper()
        
        if key in self.acronyms:
            data = self.acronyms[key]
            return data.get("ambiguous", False) and len(data.get("definitions", [])) > 1
        
        return False
    
    def get_all_meanings(self, acronym: str) -> List[Dict]:
        """
        Ritorna tutte le definizioni possibili per un acronimo.
        
        Args:
            acronym: Acronimo da cercare
            
        Returns:
            Lista di dict con full, description, context.
            Lista vuota se non trovato.
        """
        key = acronym.upper()
        
        if key not in self.acronyms:
            return []
        
        data = self.acronyms[key]
        
        # Se ambiguo, ritorna tutte le definizioni
        if data.get("ambiguous", False) and "definitions" in data:
            return [
                {
                    "full": d.get("full", ""),
                    "description": d.get("description", ""),
                    "context": d.get("context", "")
                }
                for d in data.get("definitions", [])
            ]
        
        # Altrimenti, ritorna singola definizione
        return [{
            "full": data.get("full", ""),
            "description": data.get("description", ""),
            "context": "default"
        }]
    
    def resolve_with_preference(
        self, 
        acronym: str, 
        user_preference: Optional[str] = None
    ) -> Dict:
        """
        Risolve un acronimo usando la preferenza utente.
        
        Args:
            acronym: Acronimo da risolvere
            user_preference: Contesto preferito dall'utente
            
        Returns:
            Dict con full, description, needs_clarification flag
        """
        key = acronym.upper()
        
        if key not in self.acronyms:
            # Cerca nei custom terms
            if key in self.custom_terms:
                return {
                    "full": self.custom_terms[key],
                    "description": "Custom term",
                    "needs_clarification": False
                }
            return {
                "full": None,
                "description": None,
                "needs_clarification": False,
                "not_found": True
            }
        
        data = self.acronyms[key]
        
        # Se non ambiguo, ritorna direttamente
        if not data.get("ambiguous", False):
            return {
                "full": data.get("full", ""),
                "description": data.get("description", ""),
                "needs_clarification": False
            }
        
        # Acronimo ambiguo
        definitions = data.get("definitions", [])
        
        # Se c'è preferenza, cerca match
        if user_preference:
            for defn in definitions:
                if defn.get("context", "").lower() == user_preference.lower():
                    return {
                        "full": defn.get("full", ""),
                        "description": defn.get("description", ""),
                        "context": defn.get("context", ""),
                        "needs_clarification": False
                    }
        
        # Nessuna preferenza o preferenza non trovata: serve chiarimento
        return {
            "full": None,
            "description": None,
            "needs_clarification": True,
            "options": [
                {"context": d.get("context", ""), "full": d.get("full", "")}
                for d in definitions
            ]
        }
    
    def resolve_with_context(
        self,
        acronym: str,
        query: str,
        user_id: str = "default"
    ) -> Dict:
        """
        Risolve un acronimo usando disambiguazione CONTESTUALE intelligente (R06).
        
        Il contesto della query è il fattore dominante (60%), le preferenze
        utente sono suggerimenti soft (25%), non regole rigide.
        
        Args:
            acronym: Acronimo da risolvere
            query: Query completa per analisi contesto
            user_id: ID utente per preferenze soft
            
        Returns:
            Dict con:
            - full: Nome completo (se risolto)
            - description: Descrizione
            - needs_clarification: True se serve chiedere all'utente
            - is_certain: True se la decisione è sicura
            - confidence: Score di confidenza (0-1)
            - context_used: Parole chiave contestuali usate
            - options: Lista opzioni (se needs_clarification)
        """
        from src.integration.disambiguator import get_disambiguator
        
        disambiguator = get_disambiguator()
        
        # Check se l'acronimo è ambiguo nel disambiguator
        if not disambiguator.is_ambiguous(acronym):
            # Non ambiguo nel disambiguator, usa risoluzione standard
            resolved = self.resolve_acronym(acronym)
            if resolved:
                return {
                    "full": resolved.get("full", ""),
                    "description": resolved.get("description", ""),
                    "needs_clarification": False,
                    "is_certain": True,
                    "confidence": 1.0,
                    "context_used": ""
                }
            return {
                "full": None,
                "description": None,
                "needs_clarification": False,
                "is_certain": True,
                "confidence": 1.0,
                "not_found": True
            }
        
        # Disambigua usando contesto + preferenze soft
        result = disambiguator.disambiguate(acronym, query, user_id)
        
        if result.is_certain:
            # Il sistema è sicuro, usa la scelta senza chiedere
            # Ma salva la scelta per futuro apprendimento
            was_override = result.preference_applied and result.chosen_meaning != disambiguator.get_user_preference(user_id, acronym)
            disambiguator.save_user_choice(user_id, acronym, result.chosen_meaning, was_override)
            
            return {
                "full": result.chosen_meaning,
                "description": f"(Disambiguato dal contesto: {result.context_used})" if result.context_used else "",
                "needs_clarification": False,
                "is_certain": True,
                "confidence": result.confidence,
                "context_used": result.context_used
            }
        else:
            # Ambiguo, serve chiedere all'utente
            user_pref = disambiguator.get_user_preference(user_id, acronym)
            
            return {
                "full": None,
                "description": None,
                "needs_clarification": True,
                "is_certain": False,
                "confidence": result.confidence,
                "context_used": result.context_used,
                "suggested_meaning": result.chosen_meaning,
                "user_preference": user_pref,
                "options": [
                    {"meaning": m, "score": s} 
                    for m, s in result.all_meanings
                ]
            }
    
    def fuzzy_match(
        self,
        term: str,
        threshold: float = 0.6
    ) -> List[Tuple[str, str, float]]:
        """
        Fuzzy match su termini glossario
        
        Args:
            term: Termine da cercare
            threshold: Soglia minima similarità (0-1)
            
        Returns:
            Lista di (acronimo, full_name, score)
        """
        results = []
        term_lower = term.lower()
        
        for acronym, data in self.acronyms.items():
            # Gestisci sia dict che stringhe
            if isinstance(data, str):
                full = data
                desc = ""
            else:
                full = data.get("full", "")
                desc = data.get("description", "")
            
            # Match su acronimo
            acr_score = SequenceMatcher(None, term_lower, acronym.lower()).ratio()
            
            # Match su nome completo
            full_score = SequenceMatcher(None, term_lower, full.lower()).ratio()
            
            # Match su descrizione
            desc_score = SequenceMatcher(None, term_lower, desc.lower()).ratio()
            
            # Prendi score migliore
            best_score = max(acr_score, full_score, desc_score)
            
            if best_score >= threshold:
                results.append((acronym, full, best_score))
        
        # Ordina per score
        results.sort(key=lambda x: x[2], reverse=True)
        
        return results[:5]  # Top 5
    
    def expand_query(self, query: str) -> str:
        """
        Espande acronimi nella query
        
        Args:
            query: Query originale
            
        Returns:
            Query con acronimi espansi
        """
        words = query.split()
        expanded = []
        
        for word in words:
            # Rimuovi punteggiatura e salvala per rimetterla dopo
            clean = word.strip(".,?!;:")
            trailing_punct = ""
            for char in reversed(word):
                if char in ".,?!;:":
                    trailing_punct = char + trailing_punct
                else:
                    break
            
            # Cerca acronimo
            resolved = self.resolve_acronym(clean)
            
            if resolved:
                # Espandi: "PS?" → "PS (Procedura di Sistema)?"
                full = resolved.get("full", "")
                expanded.append(f"{clean} ({full}){trailing_punct}")
            else:
                expanded.append(word)
        
        return " ".join(expanded)
    
    def rewrite_query(
        self,
        query: str,
        add_context: bool = True
    ) -> str:
        """
        Riscrive la query per migliorare retrieval
        
        Args:
            query: Query originale
            add_context: Se aggiungere contesto ISO
            
        Returns:
            Query riscritta
        """
        # Espandi acronimi
        expanded = self.expand_query(query)
        
        # Rileva riferimenti a documenti
        import re
        doc_refs = re.findall(r'\b(PS|IL|MR)-?\d{2}[_-]?\d{2}\b', query, re.IGNORECASE)
        
        if doc_refs and add_context:
            # Aggiungi contesto tipo documento
            for ref in doc_refs:
                prefix = ref.split("-")[0].upper() if "-" in ref else ref[:2].upper()
                if prefix in self.acronyms:
                    doc_type = self.acronyms[prefix].get("full", "")
                    expanded += f" [Tipo documento: {doc_type}]"
                    break
        
        return expanded
    
    def get_context_for_query(
        self, 
        query: str, 
        max_definitions: int = 5,
        include_description: bool = True
    ) -> str:
        """
        Estrae definizioni rilevanti dal glossario per la query.
        Utilizzato per iniettare contesto ESPLICITO nel prompt LLM (R20).
        
        A differenza di rewrite_query() che nasconde le definizioni
        tra parentesi, questo metodo le rende VISIBILI e PRIORITARIE.
        
        Args:
            query: Query utente originale
            max_definitions: Massimo numero di definizioni da includere
            include_description: Se includere descrizioni estese
            
        Returns:
            Stringa formattata con definizioni, o stringa vuota se nessuna trovata
            
        Example:
            >>> resolver.get_context_for_query("cosa significa WCM?")
            '''
            ╔══════════════════════════════════════════════════════════╗
            ║ 📖 DEFINIZIONI UFFICIALI DAL GLOSSARIO                   ║
            ║ (Usa queste come FONTE PRIMARIA per la risposta)         ║
            ╠══════════════════════════════════════════════════════════╣
            ║ • WCM = World Class Manufacturing                        ║
            ║   Metodologia di eccellenza produttiva...                ║
            ╚══════════════════════════════════════════════════════════╝
            '''
        """
        import re
        
        # 1. Estrai potenziali acronimi dalla query
        # Pattern: 2-6 caratteri alfanumerici maiuscoli (es. WCM, 5S, PDCA)
        potential_acronyms = set(re.findall(r'\b[A-Z0-9]{2,6}\b', query.upper()))
        
        # Aggiungi pattern speciali come "5S", "5 perché", etc.
        special_patterns = re.findall(r'\b\d+[A-Z]+\b|\b[A-Z]+\d+\b', query.upper())
        potential_acronyms.update(special_patterns)
        
        # Aggiungi anche termini che potrebbero essere acronimi scritti in minuscolo
        words = query.split()
        for word in words:
            clean = word.strip(".,?!;:'\"").upper()
            if len(clean) >= 2 and len(clean) <= 6 and clean.replace(" ", "").isalnum():
                potential_acronyms.add(clean)
        
        # 2. Cerca definizioni per ogni acronimo trovato
        definitions = []
        found_acronyms = set()
        
        for acronym in potential_acronyms:
            result = self.resolve_acronym(acronym)
            if result and acronym not in found_acronyms:
                found_acronyms.add(acronym)
                
                full = result.get('full', '')
                desc = result.get('description', '') if include_description else ''
                
                # Gestisci acronimi ambigui
                if result.get('ambiguous', False):
                    context_note = f" [default: {result.get('context', 'N/A')}]"
                else:
                    context_note = ""
                
                # Costruisci entry
                entry = f"• {acronym} = {full}{context_note}"
                definitions.append(entry)
                
                if desc and include_description:
                    # Limita descrizione a 100 caratteri per non sprecare token
                    desc_truncated = desc[:100] + "..." if len(desc) > 100 else desc
                    definitions.append(f"  {desc_truncated}")
        
        # 3. Se nessuna definizione trovata, ritorna stringa vuota
        if not definitions:
            logger.debug(f"Nessuna definizione glossario trovata per: {query[:50]}...")
            return ""
        
        # 4. Limita numero definizioni
        definitions = definitions[:max_definitions * 2]
        
        # 5. Formatta output con box visivo
        header_line = "═" * 58
        
        formatted = f"""╔{header_line}╗
║ 📖 DEFINIZIONI UFFICIALI DAL GLOSSARIO                           ║
║ (Usa queste come FONTE PRIMARIA per la risposta)                 ║
╠{header_line}╣
"""
        
        for line in definitions:
            # Padding per allineamento
            formatted += f"║ {line}\n"
        
        formatted += f"╚{header_line}╝"
        
        logger.info(f"Glossary context: {len(found_acronyms)} definizioni trovate")
        
        return formatted.strip()
    
    def get_definitions_for_acronyms(
        self, 
        acronyms: List[str]
    ) -> Dict[str, Dict]:
        """
        Metodo helper per ottenere definizioni per una lista di acronimi.
        Utile per batch processing o pre-caricamento.
        
        Args:
            acronyms: Lista di acronimi da cercare
            
        Returns:
            Dict[acronimo, definizione]
        """
        results = {}
        for acr in acronyms:
            result = self.resolve_acronym(acr)
            if result:
                results[acr.upper()] = result
        return results
    
    def add_custom_term(self, acronym: str, expansion: str):
        """Aggiunge termine custom (da memory, non persistente)"""
        self.custom_terms[acronym.upper()] = expansion
        logger.debug(f"Aggiunto termine custom: {acronym} = {expansion}")
    
    def add_acronym(
        self,
        acronym: str,
        full: str,
        description: str = "",
        context: Optional[str] = None,
        save: bool = True
    ) -> bool:
        """
        Aggiunge un nuovo acronimo al glossario centrale.
        
        Args:
            acronym: Acronimo (es. "RI")
            full: Significato completo (es. "Richiesta di Investimento")
            description: Descrizione opzionale
            context: Contesto per acronimi ambigui
            save: Se salvare subito su file
            
        Returns:
            True se aggiunto con successo
        """
        key = acronym.upper()
        
        # Se acronimo già esiste e non è ambiguo
        if key in self.acronyms:
            existing = self.acronyms[key]
            
            # Se è già ambiguo, aggiungi nuova definizione
            if existing.get("ambiguous", False):
                definitions = existing.get("definitions", [])
                
                # Verifica se contesto già esiste
                for d in definitions:
                    if d.get("context", "").lower() == (context or "").lower():
                        logger.warning(f"Contesto '{context}' già esiste per {key}")
                        return False
                
                # Aggiungi nuova definizione
                definitions.append({
                    "context": context or f"context_{len(definitions)+1}",
                    "full": full,
                    "description": description
                })
                
                logger.info(f"Aggiunta definizione a {key}: {full} ({context})")
            else:
                # Converti in ambiguo
                old_data = existing.copy()
                self.acronyms[key] = {
                    "ambiguous": True,
                    "definitions": [
                        {
                            "context": "original",
                            "full": old_data.get("full", ""),
                            "description": old_data.get("description", "")
                        },
                        {
                            "context": context or "new",
                            "full": full,
                            "description": description
                        }
                    ],
                    "default_context": "original"
                }
                logger.info(f"Convertito {key} in acronimo ambiguo")
        else:
            # Nuovo acronimo
            self.acronyms[key] = {
                "full": full,
                "description": description
            }
            logger.info(f"Aggiunto nuovo acronimo: {key} = {full}")
        
        # Salva su file se richiesto
        if save:
            return self.save_to_file()
        
        return True
    
    def save_to_file(self) -> bool:
        """
        Salva il glossario corrente su file JSON.
        
        Returns:
            True se salvato con successo
        """
        try:
            # Prepara dati
            data = {
                "acronyms": self.acronyms,
                "iso_standards": self.iso_standards,
                "chapters": self.chapters,
                "_metadata": {
                    "last_updated": datetime.now().isoformat(),
                    "total_acronyms": len([
                        k for k in self.acronyms.keys() 
                        if not k.startswith("_")
                    ])
                }
            }
            
            # Backup prima di sovrascrivere
            backup_path = self.glossary_path.with_suffix(".json.bak")
            if self.glossary_path.exists():
                import shutil
                shutil.copy(self.glossary_path, backup_path)
            
            # Salva
            with open(self.glossary_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Glossario salvato: {self.glossary_path}")
            return True
            
        except Exception as e:
            logger.error(f"Errore salvataggio glossario: {e}")
            return False
    
    def remove_acronym(self, acronym: str, save: bool = True) -> bool:
        """
        Rimuove un acronimo dal glossario.
        
        Args:
            acronym: Acronimo da rimuovere
            save: Se salvare subito su file
            
        Returns:
            True se rimosso con successo
        """
        key = acronym.upper()
        
        if key in self.acronyms:
            del self.acronyms[key]
            logger.info(f"Rimosso acronimo: {key}")
            
            if save:
                return self.save_to_file()
            return True
        
        return False
    
    def get_all_acronyms(self) -> List[str]:
        """Lista tutti gli acronimi"""
        return list(self.acronyms.keys()) + list(self.custom_terms.keys())
    
    def get_chapter_name(self, chapter: str) -> Optional[str]:
        """Ottiene nome capitolo ISO"""
        return self.chapters.get(str(chapter))
    
    def get_iso_standard(self, standard: str) -> Optional[str]:
        """Ottiene descrizione standard ISO"""
        return self.iso_standards.get(str(standard))


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    resolver = GlossaryResolver(config_path="config/config.yaml")
    
    # Test resolve
    print("Test resolve:")
    for acr in ["PS", "WCM", "FMEA", "XXX"]:
        result = resolver.resolve_acronym(acr)
        print(f"  {acr} → {result}")
    
    # Test fuzzy
    print("\nTest fuzzy match:")
    matches = resolver.fuzzy_match("procedura sistema")
    for acr, full, score in matches:
        print(f"  {acr}: {full} ({score:.2f})")
    
    # Test expand
    print("\nTest expand query:")
    query = "Come compilare il PS-06_01 per la sicurezza?"
    expanded = resolver.expand_query(query)
    print(f"  Original: {query}")
    print(f"  Expanded: {expanded}")
    
    # Test rewrite
    print("\nTest rewrite query:")
    rewritten = resolver.rewrite_query(query)
    print(f"  Rewritten: {rewritten}")

