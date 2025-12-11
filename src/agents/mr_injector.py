"""
MR Injector - Inietta informazioni sui moduli correlati nel contesto LLM
Fase: Context Enrichment (prima della generazione)

Best Practice: "Grounded Generation" - le informazioni sui moduli sono
nel contesto LLM così l'LLM può citarle naturalmente nella risposta.

Usa:
- config/ps_mr_context.json (correlazioni PS → MR estratte dai PDF)
- config/document_metadata.json (dettagli MR/campi estratti con pdfplumber)

Created: 2025-12-10
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ModuleInfo:
    """Informazioni su un modulo correlato"""
    doc_id: str
    name: str
    usage_context: str  # Quando usarlo (dal contesto PS)
    fields_preview: List[str] = field(default_factory=list)  # Campi principali
    parent_ps: str = ""
    
    def __eq__(self, other):
        if not isinstance(other, ModuleInfo):
            return False
        return self.doc_id == other.doc_id
    
    def __hash__(self):
        return hash(self.doc_id)


class MRInjector:
    """
    Inietta informazioni sui moduli MR correlati nel contesto LLM.
    
    Strategia:
    1. Carica mappature PS → MR da ps_mr_context.json
    2. Carica dettagli MR da document_metadata.json
    3. Per ogni PS nel contesto, trova MR correlati
    4. Formatta sezione per il prompt LLM
    
    L'LLM riceve queste informazioni e può decidere autonomamente
    se e quando citare i moduli nella risposta, rendendo i suggerimenti
    naturali e contestuali.
    
    Example:
        >>> injector = MRInjector()
        >>> section = injector.format_modules_for_prompt(["PS-06_01"])
        >>> print(section)
        📋 MODULI DI REGISTRAZIONE CORRELATI:
        Se la risposta prevede registrazioni, suggerisci questi moduli:
        • MR-06_01 "Safety EWO" - per registrare infortuni
    """
    
    def __init__(
        self,
        ps_context_path: str = "config/ps_mr_context.json",
        metadata_path: str = "config/document_metadata.json"
    ):
        self.ps_context: Dict = {}
        self.mr_metadata: Dict = {}
        self._load_data(ps_context_path, metadata_path)
        
    def _load_data(self, ps_path: str, meta_path: str):
        """Carica i file di configurazione"""
        try:
            ps_file = Path(ps_path)
            if ps_file.exists():
                with open(ps_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.ps_context = data.get("procedure", {})
            else:
                logger.warning(f"MRInjector: file non trovato {ps_path}")
            
            meta_file = Path(meta_path)
            if meta_file.exists():
                with open(meta_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.mr_metadata = data.get("moduli_registrazione", {})
            else:
                logger.warning(f"MRInjector: file non trovato {meta_path}")
                
            logger.info(f"MRInjector: caricati {len(self.ps_context)} PS, {len(self.mr_metadata)} MR")
        except Exception as e:
            logger.warning(f"MRInjector: errore caricamento dati: {e}")
    
    def _normalize_mr_id(self, mr_id: str) -> str:
        """Normalizza MR ID al formato MR-XX_YY"""
        mr_id = mr_id.upper().replace("--", "-")
        match = re.match(r'MR[-_]?(\d+)[-_](\d+)', mr_id)
        if match:
            return f"MR-{match.group(1).zfill(2)}_{match.group(2).zfill(2)}"
        return mr_id
    
    def _normalize_ps_id(self, ps_id: str) -> str:
        """Normalizza PS ID per confronto"""
        return ps_id.upper().replace("_", "-").replace("--", "-")
    
    def _find_mr_details(self, mr_id: str) -> Dict:
        """Trova dettagli MR in metadata"""
        mr_id_norm = self._normalize_mr_id(mr_id)
        
        # Prova match esatto
        for mid, mdata in self.mr_metadata.items():
            if self._normalize_mr_id(mid) == mr_id_norm:
                return mdata
        
        # Prova match parziale
        for mid, mdata in self.mr_metadata.items():
            if mr_id_norm in self._normalize_mr_id(mid) or self._normalize_mr_id(mid) in mr_id_norm:
                return mdata
        
        return {}
    
    def _extract_usage(self, context: str, mr_name: str = "") -> str:
        """Estrae una frase d'uso dal contesto"""
        if not context:
            if mr_name:
                return f"per {mr_name}"
            return ""
        
        # Pulisci contesto
        context = context.strip()
        context = re.sub(r'\s+', ' ', context)
        
        # Cerca frase significativa
        # Rimuovi riferimenti a codici documento
        context_clean = re.sub(r'MR-?\d+_?\d+\w*\.?', '', context)
        context_clean = re.sub(r'PS-?\d+_?\d+\w*\.?', '', context_clean)
        
        # Prendi prima parte significativa
        if "." in context_clean:
            parts = context_clean.split(".")
            for part in parts:
                part = part.strip()
                if len(part) > 15:
                    return part[:80]
        
        if len(context_clean) > 15:
            return context_clean[:80]
        
        if mr_name:
            return f"per {mr_name}"
        
        return ""
    
    def _get_field_preview(self, mr_details: Dict) -> List[str]:
        """Estrae preview dei campi principali"""
        fields = mr_details.get("campi_compilazione", [])
        preview = []
        
        # Filtra campi validi
        for f in fields:
            nome = f.get("nome", "")
            if nome:
                # Pulisci nome campo
                nome = nome.strip()
                nome = re.sub(r'\s+', ' ', nome)
                # Evita campi troppo corti o troppo lunghi
                if 3 < len(nome) < 40:
                    # Evita duplicati e campi che sono solo codici
                    if nome not in preview and not re.match(r'^[A-Z]{2,3}-\d+', nome):
                        preview.append(nome)
            
            if len(preview) >= 4:
                break
        
        return preview
    
    def get_related_modules(self, ps_doc_id: str, max_modules: int = 3) -> List[ModuleInfo]:
        """
        Trova moduli MR correlati a un PS.
        
        Args:
            ps_doc_id: ID del PS (es. "PS-06_01")
            max_modules: Massimo numero di moduli da restituire
            
        Returns:
            Lista di ModuleInfo con informazioni sui moduli correlati
        """
        ps_id_norm = self._normalize_ps_id(ps_doc_id)
        
        # Trova PS nel contesto
        ps_data = None
        for pid, pdata in self.ps_context.items():
            if self._normalize_ps_id(pid) == ps_id_norm:
                ps_data = pdata
                break
        
        if not ps_data:
            return []
        
        modules = []
        mr_citati = ps_data.get("mr_citati", {})
        
        for mr_id_raw, mr_context in list(mr_citati.items())[:max_modules * 2]:
            # Normalizza MR ID
            mr_id = self._normalize_mr_id(mr_id_raw)
            
            # Cerca dettagli in metadata
            mr_details = self._find_mr_details(mr_id)
            
            # Determina nome
            mr_name = mr_context.get("nome", "")
            if not mr_name or len(mr_name) < 3:
                mr_name = mr_details.get("titolo", "")
            if not mr_name:
                mr_name = mr_id
            
            # Pulisci nome
            mr_name = mr_name.strip()
            if mr_name.startswith("MR-"):
                mr_name = mr_name[6:].strip() if len(mr_name) > 6 else mr_name
            
            # Crea ModuleInfo
            module = ModuleInfo(
                doc_id=mr_id,
                name=mr_name[:50] if mr_name else mr_id,
                usage_context=self._extract_usage(mr_context.get("contesto", ""), mr_name),
                fields_preview=self._get_field_preview(mr_details),
                parent_ps=ps_doc_id
            )
            
            # Evita duplicati
            if module not in modules:
                modules.append(module)
            
            if len(modules) >= max_modules:
                break
        
        return modules
    
    def format_modules_for_prompt(
        self, 
        ps_doc_ids: List[str],
        max_total: int = 5
    ) -> str:
        """
        Formatta sezione moduli per il prompt LLM.
        
        Args:
            ps_doc_ids: Lista di PS doc_id presenti nel contesto
            max_total: Massimo moduli totali
            
        Returns:
            Stringa formattata per il prompt, es:
            
            📋 MODULI DI REGISTRAZIONE CORRELATI:
            Se la risposta prevede registrazioni o documentazione, suggerisci questi moduli:
            • MR-06_01 "Safety EWO" - per registrare infortuni/incidenti
            • MR-06_02 "Near Misses" - per segnalare quasi-incidenti
        """
        all_modules: List[ModuleInfo] = []
        seen_ids: Set[str] = set()
        
        for ps_id in ps_doc_ids:
            modules = self.get_related_modules(ps_id, max_modules=3)
            for m in modules:
                if m.doc_id not in seen_ids:
                    all_modules.append(m)
                    seen_ids.add(m.doc_id)
        
        if not all_modules:
            return ""
        
        # Limita a max_total
        all_modules = all_modules[:max_total]
        
        # Formatta
        lines = [
            "",
            "📋 MODULI DI REGISTRAZIONE CORRELATI:",
            "Se la risposta prevede registrazioni o documentazione, suggerisci questi moduli:"
        ]
        
        for m in all_modules:
            usage = f" - {m.usage_context}" if m.usage_context else ""
            lines.append(f"• {m.doc_id} \"{m.name}\"{usage}")
        
        lines.append("")  # Riga vuota finale
        
        return "\n".join(lines)


# Test locale
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    injector = MRInjector()
    
    print("=== TEST MRInjector ===\n")
    
    # Test PS-06_01 (Sicurezza)
    print("PS-06_01 (Sicurezza):")
    modules = injector.get_related_modules("PS-06_01")
    for m in modules:
        print(f"  - {m.doc_id}: {m.name}")
        print(f"    Uso: {m.usage_context}")
    
    print("\n" + "=" * 50)
    
    # Test formato prompt
    print("\nFormato per prompt:")
    result = injector.format_modules_for_prompt(["PS-06_01", "PS-10_01"])
    print(result)


