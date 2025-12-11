"""
Teach Assistant per OVV ISO Chat
Assistenza interattiva alla compilazione di tool/moduli

R16 - Assistenza Compilazione Tool
Created: 2025-12-08

Features:
- Gestisce contesto sessione teach
- Rileva domande su campi specifici
- Fornisce spiegazioni contestuali
- Traccia confusione per feedback Admin
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TeachContext:
    """Contesto della sessione teach corrente"""
    doc_id: str
    doc_name: str
    started_at: datetime
    fields_asked: List[str] = field(default_factory=list)
    
    def is_active(self, timeout_minutes: int = 10) -> bool:
        """Verifica se il contesto è ancora attivo"""
        elapsed = (datetime.now() - self.started_at).total_seconds() / 60
        return elapsed < timeout_minutes
    
    def add_field_asked(self, field_name: str):
        """Aggiunge campo alla lista di quelli chiesti"""
        if field_name not in self.fields_asked:
            self.fields_asked.append(field_name)


@dataclass
class FieldInfo:
    """Informazioni su un campo del tool"""
    name: str
    description: str
    tips: str
    
    def format_explanation(self) -> str:
        """Formatta spiegazione campo per output"""
        lines = [
            f"**📋 Campo: {self.name}**",
            "",
            f"**Descrizione:** {self.description}",
            ""
        ]
        
        if self.tips:
            lines.append("**💡 Suggerimenti:**")
            lines.append(f"_{self.tips}_")
        
        return "\n".join(lines)


class TeachAssistant:
    """
    Assistente per compilazione tool/moduli.
    
    Funzionalità:
    - Gestisce contesto sessione teach
    - Rileva domande su campi specifici
    - Fornisce spiegazioni contestuali
    - Traccia confusione per feedback Admin
    
    Example:
        >>> assistant = TeachAssistant()
        >>> is_field, name = assistant.detect_field_question("Non capisco il campo Severity")
        >>> if is_field:
        ...     info = assistant.get_field_info("MR-08_07", name)
        ...     print(info.format_explanation())
    """
    
    def __init__(
        self,
        mapping_path: str = "config/tools_mapping.json",
        feedback_namespace: str = "teach_feedback"
    ):
        self.mapping_path = Path(mapping_path)
        self.feedback_namespace = feedback_namespace
        
        # Carica mapping tool con campi
        self.tools_mapping: Dict = {}
        self._load_mapping()
        
        # Pattern per rilevare domande su campi
        self.field_patterns = [
            r"(non\s+capisco|non\s+so)\s+(il\s+)?campo\s+(.+)",
            r"cosa\s+(metto|scrivo|inserisco)\s+(nel|in|su)\s+(.+)",
            r"come\s+(compilo|riempio)\s+(il\s+)?campo\s+(.+)",
            r"(spiegami|dimmi)\s+(il\s+)?campo\s+(.+)",
            r"(cos['']?è|cosa\s+significa)\s+(il\s+)?campo\s+(.+)",
            r"campo\s+(.+)\s+(non|mi)\s+(è\s+)?chiar[oa]",
            r"^(severity|occurrence|detection|rpn)[\s\?]*$",
            r"^(descrizione|data|quantità|problema|effetto|causa)[\s\?]*$",
            r"(d[0-8])\s",  # Per 8D: D0, D1, etc.
        ]
        
        logger.info(f"TeachAssistant: {len(self.tools_mapping)} tool con campi caricati")
    
    def _load_mapping(self):
        """Carica mapping tool da JSON"""
        if not self.mapping_path.exists():
            logger.warning(f"Mapping non trovato: {self.mapping_path}")
            return
        
        try:
            with open(self.mapping_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.tools_mapping = data.get("tool_suggestions", {})
            
        except Exception as e:
            logger.error(f"Errore caricamento mapping: {e}")
    
    def get_tool_info(self, doc_id: str) -> Optional[Dict]:
        """
        Ottiene info tool da doc_id.
        
        Args:
            doc_id: ID documento (es. "MR-07_05")
            
        Returns:
            Dict con info tool o None
        """
        doc_id_upper = doc_id.upper().replace("-", "_").replace(" ", "_")
        
        # Cerca per doc_id esatto o parziale
        for tool_key, tool_data in self.tools_mapping.items():
            tool_doc_id = tool_data.get("doc_id", "").upper().replace("-", "_")
            
            if tool_doc_id == doc_id_upper:
                return tool_data
            if doc_id_upper in tool_key.upper():
                return tool_data
            if doc_id_upper in tool_doc_id or tool_doc_id in doc_id_upper:
                return tool_data
        
        return None
    
    def get_field_info(self, doc_id: str, field_name: str) -> Optional[FieldInfo]:
        """
        Ottiene info su un campo specifico di un tool.
        
        Args:
            doc_id: ID documento
            field_name: Nome del campo (fuzzy match)
            
        Returns:
            FieldInfo o None
        """
        tool = self.get_tool_info(doc_id)
        if not tool or "fields" not in tool:
            return None
        
        fields = tool.get("fields", [])
        field_name_lower = field_name.lower().strip()
        
        # Match esatto
        for f in fields:
            if f["name"].lower() == field_name_lower:
                return FieldInfo(
                    name=f["name"],
                    description=f.get("description", ""),
                    tips=f.get("tips", "")
                )
        
        # Match parziale (campo contiene la stringa o viceversa)
        for f in fields:
            fname_lower = f["name"].lower()
            if field_name_lower in fname_lower or fname_lower in field_name_lower:
                return FieldInfo(
                    name=f["name"],
                    description=f.get("description", ""),
                    tips=f.get("tips", "")
                )
        
        # Match su parole chiave nel nome campo
        for f in fields:
            fname_words = set(f["name"].lower().replace("(", " ").replace(")", " ").split())
            search_words = set(field_name_lower.split())
            if fname_words & search_words:  # Intersezione non vuota
                return FieldInfo(
                    name=f["name"],
                    description=f.get("description", ""),
                    tips=f.get("tips", "")
                )
        
        return None
    
    def get_all_fields(self, doc_id: str) -> List[FieldInfo]:
        """
        Ottiene tutti i campi di un tool.
        
        Args:
            doc_id: ID documento
            
        Returns:
            Lista di FieldInfo
        """
        tool = self.get_tool_info(doc_id)
        if not tool or "fields" not in tool:
            return []
        
        return [
            FieldInfo(
                name=f["name"],
                description=f.get("description", ""),
                tips=f.get("tips", "")
            )
            for f in tool.get("fields", [])
        ]
    
    def detect_field_question(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Rileva se il testo contiene una domanda su un campo specifico.
        
        Args:
            text: Testo messaggio utente
            
        Returns:
            Tuple (is_field_question, field_name_extracted)
        """
        text_lower = text.lower().strip()
        
        # Skip se troppo lungo (probabilmente una query normale)
        if len(text_lower) > 100:
            return False, None
        
        for pattern in self.field_patterns:
            try:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    # Estrai nome campo dal gruppo più significativo
                    groups = match.groups()
                    field_name = None
                    
                    # Cerca il gruppo più lungo che non sia una parola comune
                    common_words = {"il", "in", "nel", "su", "non", "mi", "è", "la", "lo", "un", "una"}
                    
                    for g in reversed(groups):
                        if g and len(g) >= 2 and g.strip() not in common_words:
                            field_name = g.strip()
                            break
                    
                    # Se nessun gruppo, usa l'intero match per pattern diretti
                    if not field_name and match.group(0):
                        field_name = match.group(0).strip()
                    
                    if field_name:
                        # Pulisci il nome campo
                        field_name = re.sub(r'[?\.\!]', '', field_name).strip()
                        logger.debug(f"Rilevata domanda su campo: '{field_name}'")
                        return True, field_name
            except re.error:
                continue
        
        return False, None
    
    def format_fields_list(self, doc_id: str) -> str:
        """
        Formatta lista campi per output UI.
        
        Args:
            doc_id: ID documento
            
        Returns:
            Stringa markdown formattata
        """
        fields = self.get_all_fields(doc_id)
        
        if not fields:
            return "ℹ️ *Dettagli campi non disponibili per questo documento.*"
        
        tool = self.get_tool_info(doc_id)
        tool_name = tool.get("name", doc_id) if tool else doc_id
        
        lines = [
            f"**📝 Campi del modulo {tool_name}** (`{doc_id}`)",
            "",
            "---",
            ""
        ]
        
        for i, field in enumerate(fields, 1):
            lines.append(f"**{i}. {field.name}**")
            lines.append(f"   {field.description}")
            if field.tips:
                lines.append(f"   💡 _{field.tips}_")
            lines.append("")
        
        lines.append("---")
        lines.append("*Chiedi dettagli su un campo specifico, es: \"Non capisco il campo Severity\"*")
        
        return "\n".join(lines)
    
    def format_teach_response_with_actions(
        self,
        doc_id: str,
        doc_name: str,
        base_response: str
    ) -> Tuple[str, List[Dict]]:
        """
        Formatta risposta teach con azioni per follow-up.
        
        Args:
            doc_id: ID documento
            doc_name: Nome documento
            base_response: Risposta base dal teach
            
        Returns:
            Tuple (formatted_response, actions_list)
        """
        # Costruisci risposta
        response = f"**📝 Come compilare {doc_name}** (`{doc_id}`)\n\n"
        response += "---\n\n"
        response += base_response
        response += "\n\n---\n"
        response += "🔍 **Hai bisogno di aiuto su un campo specifico?**\n"
        response += "_Seleziona un'azione o chiedi direttamente, es: \"Non capisco il campo Severity\"_"
        
        # Verifica se il tool ha campi definiti
        fields = self.get_all_fields(doc_id)
        
        # Costruisci azioni
        actions = []
        
        if fields:
            actions.append({
                "name": "teach_fields_list",
                "payload": {"doc_id": doc_id, "doc_name": doc_name},
                "label": "📋 Mostra tutti i campi"
            })
        
        actions.extend([
            {
                "name": "teach_errors",
                "payload": {"doc_id": doc_id, "doc_name": doc_name},
                "label": "⚠️ Errori comuni"
            },
            {
                "name": "teach_example",
                "payload": {"doc_id": doc_id, "doc_name": doc_name},
                "label": "📄 Esempio compilato"
            }
        ])
        
        return response, actions


class TeachFeedbackTracker:
    """
    Traccia feedback/confusione utenti sui campi.
    Salva dati per report Admin.
    """
    
    def __init__(self, memory_store=None):
        self.memory_store = memory_store
        self._confusion_cache: Dict[str, Dict[str, int]] = {}  # {doc_id: {field: count}}
        self._questions_log: List[Dict] = []  # Log dettagliato
    
    def track_field_question(
        self,
        doc_id: str,
        field_name: str,
        user_id: str
    ):
        """
        Traccia domanda su un campo.
        
        Args:
            doc_id: ID documento
            field_name: Nome campo chiesto
            user_id: ID utente
        """
        # Aggiorna cache locale
        if doc_id not in self._confusion_cache:
            self._confusion_cache[doc_id] = {}
        
        field_key = field_name.lower().strip()
        self._confusion_cache[doc_id][field_key] = self._confusion_cache[doc_id].get(field_key, 0) + 1
        
        # Log dettagliato
        self._questions_log.append({
            "doc_id": doc_id,
            "field": field_name,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        })
        
        logger.info(f"[R16] Tracciata domanda campo: {doc_id}/{field_name} (count: {self._confusion_cache[doc_id][field_key]})")
        
        # Salva in memory store se disponibile
        if self.memory_store:
            try:
                from src.memory.store import MemoryType
                
                content = f"Domanda campo: {field_name} in {doc_id} | user:{user_id} | timestamp:{datetime.now().isoformat()}"
                
                self.memory_store.add(
                    content=content,
                    mem_type=MemoryType.FACT,
                    namespace=("teach_feedback",)
                )
            except Exception as e:
                logger.warning(f"Errore salvataggio feedback: {e}")
    
    def get_confusion_count(self, doc_id: str, field_name: str) -> int:
        """Ottiene conteggio confusione per un campo"""
        if doc_id not in self._confusion_cache:
            return 0
        return self._confusion_cache[doc_id].get(field_name.lower().strip(), 0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Ottiene statistiche per Admin"""
        stats = {
            "total_questions": sum(
                sum(fields.values())
                for fields in self._confusion_cache.values()
            ),
            "by_document": {},
            "top_confused_fields": []
        }
        
        # Organizza per documento
        for doc_id, fields in self._confusion_cache.items():
            stats["by_document"][doc_id] = {
                "total": sum(fields.values()),
                "fields": dict(sorted(fields.items(), key=lambda x: -x[1]))
            }
        
        # Top campi problematici (globali)
        all_fields = []
        for doc_id, fields in self._confusion_cache.items():
            for field_name, count in fields.items():
                all_fields.append({
                    "doc_id": doc_id,
                    "field": field_name,
                    "count": count
                })
        
        stats["top_confused_fields"] = sorted(
            all_fields,
            key=lambda x: -x["count"]
        )[:10]
        
        return stats
    
    def should_notify_admin(self, doc_id: str, field_name: str, threshold: int = 3) -> bool:
        """Verifica se notificare Admin per campo problematico"""
        return self.get_confusion_count(doc_id, field_name) >= threshold
    
    def get_recent_questions(self, limit: int = 20) -> List[Dict]:
        """Ottiene le domande più recenti"""
        return self._questions_log[-limit:]


# Singleton instances
_teach_assistant: Optional[TeachAssistant] = None
_feedback_tracker: Optional[TeachFeedbackTracker] = None


def get_teach_assistant() -> TeachAssistant:
    """Ottiene istanza singleton TeachAssistant"""
    global _teach_assistant
    if _teach_assistant is None:
        _teach_assistant = TeachAssistant()
    return _teach_assistant


def get_feedback_tracker(memory_store=None) -> TeachFeedbackTracker:
    """Ottiene istanza singleton TeachFeedbackTracker"""
    global _feedback_tracker
    if _feedback_tracker is None:
        _feedback_tracker = TeachFeedbackTracker(memory_store)
    return _feedback_tracker


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    assistant = TeachAssistant()
    
    # Test get_tool_info
    print("=== TEST TOOL INFO ===")
    for doc_id in ["MR-07_05", "MR-08_07", "TOOLS-10_01", "MR-08_14"]:
        info = assistant.get_tool_info(doc_id)
        if info:
            fields_count = len(info.get("fields", []))
            print(f"✅ {doc_id}: {info.get('name', 'N/A')} - {fields_count} campi")
        else:
            print(f"❌ {doc_id}: Non trovato")
    
    # Test field detection
    print("\n=== TEST FIELD DETECTION ===")
    test_questions = [
        "Non capisco il campo Severity",
        "Cosa metto nel campo descrizione?",
        "Come compilo il campo RPN?",
        "Cos'è il campo Occurrence?",
        "Il campo data non mi è chiaro",
        "severity",
        "Quanti pezzi devo indicare?",  # Non dovrebbe matchare
        "D3",  # 8D discipline
        "Come funziona la ISO 9001?",  # Non dovrebbe matchare
    ]
    
    for q in test_questions:
        is_field, field_name = assistant.detect_field_question(q)
        status = "✅" if is_field else "❌"
        result = field_name or "N/A"
        print(f"{status} '{q[:40]}...' → {result}")
    
    # Test get_field_info
    print("\n=== TEST GET FIELD INFO ===")
    test_fields = [
        ("MR-08_07", "Severity"),
        ("MR-08_07", "RPN"),
        ("MR-07_05", "Descrizione"),
        ("TOOLS-10_01", "What"),
        ("MR-08_14", "D3"),
    ]
    
    for doc_id, field_name in test_fields:
        info = assistant.get_field_info(doc_id, field_name)
        if info:
            print(f"✅ {doc_id}/{field_name}: {info.name[:30]}...")
        else:
            print(f"❌ {doc_id}/{field_name}: Non trovato")
    
    # Test format fields
    print("\n=== TEST FORMAT FIELDS (MR-08_07) ===")
    print(assistant.format_fields_list("MR-08_07")[:800])
    
    # Test feedback tracker
    print("\n=== TEST FEEDBACK TRACKER ===")
    tracker = TeachFeedbackTracker()
    tracker.track_field_question("MR-08_07", "Severity", "user_1")
    tracker.track_field_question("MR-08_07", "Severity", "user_2")
    tracker.track_field_question("MR-08_07", "RPN", "user_3")
    tracker.track_field_question("MR-07_05", "Descrizione", "user_1")
    
    stats = tracker.get_stats()
    print(f"Totale domande: {stats['total_questions']}")
    print(f"Top campi: {stats['top_confused_fields'][:3]}")

