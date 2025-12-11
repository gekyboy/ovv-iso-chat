"""
Tool Suggester per OVV ISO Chat
Suggerisce tool/moduli pratici basandosi su:
1. Intent detection (query azionabile?)
2. Mapping JSON (keywords/concepts)
3. Ricerca semantica (fallback)

R15 - Suggerimento Tool pratici
Created: 2025-12-08
"""

import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolSuggestion:
    """Rappresenta un tool suggerito"""
    doc_id: str
    name: str
    reason: str          # Perché suggerito
    source: str          # "mapping" o "semantic"
    score: float         # Score di rilevanza (0-1)
    suggest_when: str    # Quando usare


class ToolSuggester:
    """
    Sistema multi-livello per suggerire tool pratici.
    
    Livelli:
    1. Intent Detection - Filtra query non azionabili
    2. Mapping JSON - Match esplicito keywords/concepts
    3. Semantico - Fallback con embedding similarity
    
    Example:
        >>> suggester = ToolSuggester()
        >>> suggestions = suggester.suggest_tools("Ho una NC su un pezzo")
        >>> for s in suggestions:
        ...     print(f"{s.name}: {s.suggest_when}")
    """
    
    def __init__(
        self,
        mapping_path: str = "config/tools_mapping.json",
        qdrant_client = None,
        collection_name: str = "iso_sgi_docs_v31"
    ):
        """
        Inizializza il suggester.
        
        Args:
            mapping_path: Percorso al file di mapping JSON
            qdrant_client: Client Qdrant per ricerca semantica (opzionale)
            collection_name: Nome collezione per ricerca semantica
        """
        self.mapping_path = Path(mapping_path)
        self.qdrant_client = qdrant_client
        self.collection_name = collection_name
        
        # Carica mapping
        self.tools_mapping: Dict = {}
        self.actionable_patterns: List[str] = []
        self.informational_patterns: List[str] = []
        
        self._load_mapping()
        
        logger.info(f"ToolSuggester: {len(self.tools_mapping)} tool caricati")
    
    def _load_mapping(self):
        """Carica il mapping da JSON"""
        if not self.mapping_path.exists():
            logger.warning(f"Mapping non trovato: {self.mapping_path}")
            self._create_default_mapping()
            return
        
        try:
            with open(self.mapping_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.tools_mapping = data.get("tool_suggestions", {})
            
            intent = data.get("intent_patterns", {})
            self.actionable_patterns = intent.get("actionable", [])
            self.informational_patterns = intent.get("informational", [])
            
        except Exception as e:
            logger.error(f"Errore caricamento mapping: {e}")
            self._create_default_mapping()
    
    def _create_default_mapping(self):
        """Crea mapping minimo di default"""
        self.tools_mapping = {
            "MR_07_05_Cartellino_Anomalia": {
                "doc_id": "MR-07_05",
                "name": "Cartellino Anomalia",
                "concepts": ["anomalia", "difetto", "NC"],
                "keywords": ["anomalia", "difetto", "segnalare"],
                "suggest_when": "Registrazione anomalie",
                "priority": 1
            }
        }
        self.actionable_patterns = [
            r"ho\s+(un|una)\s+(problema|NC|anomalia)",
            r"come\s+(gestisco|risolvo)"
        ]
        self.informational_patterns = [
            r"^cos['\']?è",
            r"^spiegami"
        ]
    
    def is_actionable_query(self, query: str) -> bool:
        """
        Rileva se la query richiede azione pratica.
        Se NO → non suggerire tool.
        
        Args:
            query: Query utente
            
        Returns:
            True se azionabile, False se informativa
            
        Example:
            >>> suggester.is_actionable_query("Come gestisco una NC?")
            True
            >>> suggester.is_actionable_query("Cos'è una NC?")
            False
        """
        query_lower = query.lower().strip()
        
        # 1. Controlla pattern INFORMATIVI (escludono suggerimenti)
        for pattern in self.informational_patterns:
            try:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    logger.debug(f"Query informativa: {query[:50]}... (pattern: {pattern})")
                    return False
            except re.error:
                continue
        
        # 2. Controlla pattern AZIONABILI (includono suggerimenti)
        for pattern in self.actionable_patterns:
            try:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    logger.debug(f"Query azionabile: {query[:50]}... (pattern: {pattern})")
                    return True
            except re.error:
                continue
        
        # 3. Default: NO suggerimenti (per evitare rumore)
        return False
    
    def match_from_mapping(
        self,
        query: str,
        answer: str = "",
        min_matches: int = 1
    ) -> List[ToolSuggestion]:
        """
        Cerca tool dal mapping JSON basandosi su keywords/concepts.
        
        Args:
            query: Query utente
            answer: Risposta LLM (opzionale, per context)
            min_matches: Minimo keywords da matchare
            
        Returns:
            Lista di ToolSuggestion ordinata per rilevanza
        """
        text_to_search = f"{query} {answer}".lower()
        results: List[Tuple[ToolSuggestion, int, int]] = []
        
        for tool_key, tool_data in self.tools_mapping.items():
            keywords = [k.lower() for k in tool_data.get("keywords", [])]
            concepts = [c.lower() for c in tool_data.get("concepts", [])]
            
            # Conta match keywords
            keyword_matches = sum(1 for k in keywords if k in text_to_search)
            
            # Conta match concepts (peso maggiore)
            concept_matches = sum(1 for c in concepts if c in text_to_search)
            
            total_matches = keyword_matches + (concept_matches * 2)  # Concepts pesano doppio
            
            if total_matches >= min_matches:
                priority = tool_data.get("priority", 5)
                score = min(1.0, total_matches / 5)  # Normalizza score
                
                suggestion = ToolSuggestion(
                    doc_id=tool_data.get("doc_id", ""),
                    name=tool_data.get("name", tool_key),
                    reason=f"Match: {keyword_matches} keywords, {concept_matches} concepts",
                    source="mapping",
                    score=score,
                    suggest_when=tool_data.get("suggest_when", "")
                )
                
                results.append((suggestion, total_matches, priority))
        
        # Ordina per matches DESC, poi priority ASC
        results.sort(key=lambda x: (-x[1], x[2]))
        
        return [r[0] for r in results]
    
    def search_semantic(
        self,
        query: str,
        threshold: float = 0.7,
        limit: int = 3
    ) -> List[ToolSuggestion]:
        """
        Cerca tool con embedding similarity (fallback).
        Cerca solo documenti TOOLS/MR nel Qdrant.
        
        Args:
            query: Query utente
            threshold: Soglia minima score
            limit: Massimo risultati
            
        Returns:
            Lista di ToolSuggestion
        """
        if not self.qdrant_client:
            logger.debug("Qdrant client non disponibile, skip ricerca semantica")
            return []
        
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchAny
            
            # Filtra solo TOOLS e MR
            filter_condition = Filter(
                should=[
                    FieldCondition(
                        key="doc_type",
                        match=MatchAny(any=["TOOLS", "MR"])
                    )
                ]
            )
            
            # Embedding query - usa modello già caricato se disponibile
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer("BAAI/bge-m3")
                query_embedding = model.encode(query).tolist()
            except Exception as e:
                logger.warning(f"Errore embedding: {e}")
                return []
            
            # Search
            results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=filter_condition,
                limit=limit,
                score_threshold=threshold
            )
            
            suggestions = []
            seen_docs: Set[str] = set()
            
            for hit in results:
                doc_id = hit.payload.get("doc_id", "")
                
                # Deduplica per doc_id
                if doc_id in seen_docs:
                    continue
                seen_docs.add(doc_id)
                
                suggestions.append(ToolSuggestion(
                    doc_id=doc_id,
                    name=hit.payload.get("title", doc_id),
                    reason=f"Similarità semantica: {hit.score:.0%}",
                    source="semantic",
                    score=hit.score,
                    suggest_when="Rilevato per similarità con la query"
                ))
            
            return suggestions
            
        except Exception as e:
            logger.warning(f"Errore ricerca semantica: {e}")
            return []
    
    def suggest_tools(
        self,
        query: str,
        answer: str = "",
        max_suggestions: int = 2
    ) -> List[ToolSuggestion]:
        """
        Metodo principale: suggerisce tool per la query.
        
        Sistema multi-livello:
        1. Intent detection → se informativa, return []
        2. Mapping JSON → match esplicito (alta priorità)
        3. Semantico → fallback se mapping insufficiente
        
        Args:
            query: Query utente
            answer: Risposta LLM (per context)
            max_suggestions: Massimo tool da suggerire
            
        Returns:
            Lista di ToolSuggestion (max 2)
            
        Example:
            >>> suggester.suggest_tools("Ho una NC su un pezzo lavorato")
            [ToolSuggestion(doc_id='MR-07_05', name='Cartellino Anomalia', ...),
             ToolSuggestion(doc_id='TOOLS-10_01', name='5W1H', ...)]
        """
        # STEP 1: Intent detection
        if not self.is_actionable_query(query):
            logger.info(f"[R15] Query non azionabile, nessun tool suggerito")
            return []
        
        suggestions: List[ToolSuggestion] = []
        
        # STEP 2: Mapping JSON (priorità alta)
        mapping_results = self.match_from_mapping(query, answer)
        suggestions.extend(mapping_results)
        logger.info(f"[R15] Mapping: {len(mapping_results)} tool trovati")
        
        # STEP 3: Semantico (solo se pochi risultati da mapping)
        if len(suggestions) < 2:
            semantic_results = self.search_semantic(query, threshold=0.7)
            
            # Aggiungi solo se non duplicati
            existing_docs = {s.doc_id for s in suggestions}
            for sr in semantic_results:
                if sr.doc_id not in existing_docs:
                    suggestions.append(sr)
            
            logger.info(f"[R15] Semantico: {len(semantic_results)} tool aggiuntivi")
        
        # STEP 4: Deduplica e limita
        unique = self._deduplicate(suggestions)
        final = unique[:max_suggestions]
        
        logger.info(f"[R15] Tool suggeriti finali: {[t.doc_id for t in final]}")
        
        return final
    
    def _deduplicate(self, suggestions: List[ToolSuggestion]) -> List[ToolSuggestion]:
        """Rimuove duplicati basandosi su doc_id"""
        seen: Set[str] = set()
        unique: List[ToolSuggestion] = []
        
        for s in suggestions:
            if s.doc_id not in seen:
                seen.add(s.doc_id)
                unique.append(s)
        
        return unique
    
    def format_suggestions_for_ui(
        self,
        suggestions: List[ToolSuggestion]
    ) -> str:
        """
        Formatta i suggerimenti per l'UI Chainlit.
        
        Args:
            suggestions: Lista tool suggeriti
            
        Returns:
            Stringa markdown formattata
        """
        if not suggestions:
            return ""
        
        lines = [
            "",
            "---",
            "**🛠️ Tool consigliati per questo problema:**",
            ""
        ]
        
        for tool in suggestions:
            emoji = "📌" if tool.source == "mapping" else "🔍"
            source_label = "admin mapping" if tool.source == "mapping" else f"semantico ({tool.score:.0%})"
            
            lines.append(f"{emoji} **{tool.name}** (`{tool.doc_id}`)")
            lines.append(f"   _{tool.suggest_when}_")
            lines.append(f"   Suggerito da: {source_label}")
            lines.append("")
        
        lines.append("*Clicca su un tool o usa `/teach <doc_id>` per sapere come compilarlo*")
        
        return "\n".join(lines)


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    suggester = ToolSuggester()
    
    # Test intent detection
    print("=== TEST INTENT DETECTION ===")
    test_queries = [
        ("Ho una non conformità su un pezzo", True),
        ("Cos'è una NC?", False),
        ("Come gestisco un reclamo cliente?", True),
        ("Spiegami la procedura PS-08_01", False),
        ("Il macchinario si è guastato", True),
        ("Quanti capitoli ha la ISO 9001?", False),
        ("Devo registrare un'anomalia", True),
        ("Definizione di WCM", False),
    ]
    
    for query, expected in test_queries:
        result = suggester.is_actionable_query(query)
        status = "✅" if result == expected else "❌"
        print(f"{status} '{query[:40]}...' → {result} (atteso: {expected})")
    
    # Test suggerimenti
    print("\n=== TEST SUGGERIMENTI ===")
    test_suggestions = [
        "Ho una non conformità su un pezzo lavorato",
        "Cliente reclama per difetto prodotto",
        "Devo analizzare le cause di un guasto macchina",
        "Voglio fare un quick kaizen per migliorare il processo"
    ]
    
    for query in test_suggestions:
        print(f"\nQuery: {query}")
        suggestions = suggester.suggest_tools(query)
        
        if suggestions:
            for s in suggestions:
                print(f"  → {s.name} ({s.doc_id}) - {s.reason}")
        else:
            print("  → Nessun tool suggerito")
    
    # Test formattazione
    print("\n=== TEST FORMATTAZIONE ===")
    if test_suggestions:
        suggestions = suggester.suggest_tools(test_suggestions[0])
        formatted = suggester.format_suggestions_for_ui(suggestions)
        print(formatted)

