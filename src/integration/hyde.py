"""
HyDE Generator per OVV ISO Chat v3.3
Implementa Hypothetical Document Embeddings (R23)

Paper: "Precise Zero-Shot Dense Retrieval without Relevance Labels"
https://arxiv.org/abs/2212.10496

Flow:
1. Query → LLM genera documento ipotetico
2. Documento ipotetico → Embedding BGE-M3
3. Embedding → Cerca documenti reali simili

Vantaggi:
- Cattura meglio l'intento semantico della query
- Il documento ipotetico ha pattern linguistici simili ai documenti reali
- Migliora precision del retrieval del 15-20%
"""

import logging
import hashlib
import time
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class HyDEResult:
    """Risultato generazione documento ipotetico"""
    query: str
    hypothetical_document: str
    doc_type_hint: str  # PS, IL, MR, GENERAL
    generation_time_ms: float
    from_cache: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "hypothetical_document": self.hypothetical_document,
            "doc_type_hint": self.doc_type_hint,
            "generation_time_ms": self.generation_time_ms,
            "from_cache": self.from_cache
        }


class HyDEGenerator:
    """
    Genera documenti ipotetici per migliorare retrieval ISO-SGI.
    
    Features:
    - Template specifici per tipo documento (PS/IL/MR)
    - Caching documenti ipotetici
    - Skip per query definitorie (già coperte da R20/R22)
    - Skip per query troppo corte
    
    Uso:
        generator = HyDEGenerator(config, llm)
        result = generator.generate("come gestire i rifiuti pericolosi")
        # result.hypothetical_document contiene il documento generato
    """
    
    # Template per generazione documento ipotetico per tipo
    TEMPLATES = {
        "PS": """Scrivi un breve paragrafo (max 150 parole) di una Procedura di Sistema (PS) 
del Sistema di Gestione Integrato ISO che risponde alla domanda: {query}

Il testo deve sembrare estratto da una procedura reale e includere:
- Riferimenti a responsabilità (RSGI, RQ, Direzione)
- Fasi del processo
- Standard ISO di riferimento (9001, 14001, 45001)

Scrivi SOLO il contenuto, senza titoli.""",

        "IL": """Scrivi un breve paragrafo (max 150 parole) di una Istruzione di Lavoro (IL) 
operativa che spiega: {query}

Il testo deve sembrare estratto da una istruzione reale e includere:
- Passaggi operativi numerati o sequenziali
- Strumenti o attrezzature necessari
- Controlli da effettuare

Scrivi SOLO il contenuto, senza titoli.""",

        "MR": """Scrivi una breve descrizione (max 150 parole) di un Modulo di Registrazione (MR) 
relativo a: {query}

Il testo deve includere:
- Campi principali del modulo
- Chi deve compilarlo e quando
- Procedura collegata

Scrivi SOLO il contenuto, senza titoli.""",

        "GENERAL": """Scrivi un breve paragrafo informativo (max 150 parole) sulla documentazione 
del Sistema di Gestione Integrato ISO che risponde a: {query}

Includi riferimenti a:
- Standard ISO pertinenti (9001 qualità, 14001 ambiente, 45001 sicurezza)
- Tipi di documenti (Procedure, Istruzioni, Moduli)
- Strumenti WCM/Kaizen se applicabile

Scrivi SOLO il contenuto, senza titoli.""",

        "TOOL": """Scrivi una breve descrizione (max 150 parole) di uno strumento WCM/Kaizen 
o tool del Sistema di Gestione che riguarda: {query}

Il testo deve includere:
- Scopo dello strumento
- Come si usa
- Quando applicarlo
- Benefici attesi

Scrivi SOLO il contenuto, senza titoli."""
    }
    
    # Pattern per skip HyDE
    SKIP_PATTERNS = [
        r"cosa significa",
        r"cos'è",
        r"che cos'è",
        r"definizione di",
        r"cosa vuol dire",
        r"acronimo",
        r"^\s*[A-Z][A-Z0-9]{1,5}\s*\??\s*$",  # Solo acronimo
    ]
    
    def __init__(
        self,
        config: Optional[Dict] = None,
        llm: Any = None,
        embedder: Any = None
    ):
        """
        Inizializza HyDE Generator.
        
        Args:
            config: Configurazione (sezione 'hyde' da config.yaml)
            llm: LLM instance per generazione (Ollama)
            embedder: Embedder per generare embedding documento ipotetico
        """
        self.config = config or {}
        self._llm = llm
        self._embedder = embedder
        
        # Carica config HyDE
        hyde_config = self.config.get("hyde", {})
        self.enabled = hyde_config.get("enabled", True)
        self.skip_definitions = hyde_config.get("skip_for_definition_queries", True)
        
        # Config generazione
        gen_config = hyde_config.get("generation", {})
        self.max_length = gen_config.get("max_length", 200)
        self.temperature = gen_config.get("temperature", 0.3)
        
        # Config embedding combination
        emb_config = hyde_config.get("embedding", {})
        self.combine_method = emb_config.get("combine_method", "weighted_average")
        self.weights = emb_config.get("weights", {
            "query_original": 0.25,
            "query_expanded": 0.35,
            "hyde_document": 0.40
        })
        
        # Cache
        cache_config = hyde_config.get("cache", {})
        self.cache_enabled = cache_config.get("enabled", True)
        self.cache_max_entries = cache_config.get("max_entries", 500)
        self.cache_ttl_seconds = cache_config.get("ttl_seconds", 3600)
        self._cache: Dict[str, HyDEResult] = {}
        
        logger.info(
            f"HyDEGenerator inizializzato: enabled={self.enabled}, "
            f"cache={self.cache_enabled}"
        )
    
    def set_llm(self, llm: Any):
        """Imposta LLM per generazione"""
        self._llm = llm
    
    def set_embedder(self, embedder: Any):
        """Imposta embedder per embedding documento ipotetico"""
        self._embedder = embedder
    
    def _detect_doc_type(self, query: str) -> str:
        """
        Rileva tipo documento più probabile dalla query.
        
        Ordine di priorità: IL > MR > TOOL > PS > GENERAL
        (IL e MR sono più specifici di PS)
        
        Args:
            query: Query utente
            
        Returns:
            Tipo documento: PS, IL, MR, TOOL, GENERAL
        """
        query_lower = query.lower()
        
        # 1. Tool WCM (molto specifico)
        if any(kw in query_lower for kw in [
            "tool", "strumento", "wcm", "kaizen", "5s", "pdca",
            "fmea", "8d", "smed", "tpm"
        ]):
            return "TOOL"
        
        # 2. Istruzioni di Lavoro (priorità su PS per "come fare")
        if any(kw in query_lower for kw in [
            "come fare", "come si", "istruzione", "passaggi",
            "operativ", "step", "fasi", "eseguire"
        ]):
            return "IL"
        
        # 3. Moduli di Registrazione
        if any(kw in query_lower for kw in [
            "modulo", "form", "compilare", "registr", "check list",
            "checklist", "scheda", "template"
        ]):
            return "MR"
        
        # 4. Procedure di Sistema
        if any(kw in query_lower for kw in [
            "procedura", "processo", "responsabilità", "chi deve",
            "politica", "obiettivi", "riesame", "audit"
        ]):
            return "PS"
        
        return "GENERAL"
    
    def _should_skip(self, query: str) -> bool:
        """
        Determina se skip HyDE per questa query.
        
        Skip per:
        - Query definitorie (coperte da R20/R22)
        - Query troppo corte (< 3 parole)
        - Query che sono solo acronimi
        
        Args:
            query: Query utente
            
        Returns:
            True se deve skippare HyDE
        """
        # Skip se disabilitato
        if not self.enabled:
            return True
        
        # Skip per query troppo corte
        words = query.split()
        if len(words) < 3:
            return True
        
        # Skip per query definitorie
        if self.skip_definitions:
            query_lower = query.lower()
            for pattern in self.SKIP_PATTERNS:
                if re.search(pattern, query_lower):
                    return True
        
        return False
    
    def _get_cache_key(self, query: str) -> str:
        """Genera chiave cache per query"""
        return hashlib.md5(query.strip().lower().encode()).hexdigest()
    
    def _is_cache_valid(self, result: HyDEResult) -> bool:
        """Verifica se risultato cache è ancora valido"""
        if not self.cache_enabled:
            return False
        
        age = datetime.now() - result.timestamp
        return age.total_seconds() < self.cache_ttl_seconds
    
    def _cleanup_cache(self):
        """Rimuove entry cache scadute o in eccesso"""
        if not self.cache_enabled:
            return
        
        # Rimuovi scadute
        now = datetime.now()
        expired_keys = [
            k for k, v in self._cache.items()
            if (now - v.timestamp).total_seconds() > self.cache_ttl_seconds
        ]
        for k in expired_keys:
            del self._cache[k]
        
        # Rimuovi eccesso (FIFO)
        if len(self._cache) > self.cache_max_entries:
            # Ordina per timestamp e rimuovi più vecchi
            sorted_items = sorted(
                self._cache.items(),
                key=lambda x: x[1].timestamp
            )
            to_remove = len(self._cache) - self.cache_max_entries
            for k, _ in sorted_items[:to_remove]:
                del self._cache[k]
    
    def generate(self, query: str) -> Optional[HyDEResult]:
        """
        Genera documento ipotetico per la query.
        
        Args:
            query: Query utente
            
        Returns:
            HyDEResult con documento ipotetico, o None se skip
        """
        # Check skip
        if self._should_skip(query):
            logger.debug(f"HyDE skip: query='{query[:50]}...'")
            return None
        
        # Check cache
        cache_key = self._get_cache_key(query)
        if self.cache_enabled and cache_key in self._cache:
            cached = self._cache[cache_key]
            if self._is_cache_valid(cached):
                cached.from_cache = True
                logger.debug(f"HyDE cache hit: {cache_key[:8]}")
                return cached
        
        # Check LLM disponibile
        if self._llm is None:
            logger.warning("HyDE: LLM non disponibile")
            return None
        
        # Genera documento ipotetico
        start_time = time.time()
        
        try:
            # Rileva tipo documento
            doc_type = self._detect_doc_type(query)
            template = self.TEMPLATES.get(doc_type, self.TEMPLATES["GENERAL"])
            prompt = template.format(query=query)
            
            # Genera con LLM
            response = self._llm.invoke(prompt)
            
            # Pulisci risposta
            hypothetical_doc = self._clean_response(response)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            result = HyDEResult(
                query=query,
                hypothetical_document=hypothetical_doc,
                doc_type_hint=doc_type,
                generation_time_ms=elapsed_ms,
                from_cache=False,
                timestamp=datetime.now()
            )
            
            # Salva in cache
            if self.cache_enabled:
                self._cache[cache_key] = result
                self._cleanup_cache()
            
            logger.info(
                f"HyDE generated: type={doc_type}, "
                f"len={len(hypothetical_doc)}, time={elapsed_ms:.0f}ms"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"HyDE generation failed: {e}")
            return None
    
    def _clean_response(self, response: str) -> str:
        """
        Pulisce risposta LLM.
        
        - Rimuove tag di pensiero (qwen3)
        - Limita lunghezza
        - Rimuove whitespace extra
        """
        text = response.strip()
        
        # Rimuovi tag <think>...</think> di qwen3
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # Rimuovi eventuali prefissi comuni
        prefixes_to_remove = [
            "Ecco il documento:",
            "Documento ipotetico:",
            "Risposta:",
        ]
        for prefix in prefixes_to_remove:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()
        
        # Limita lunghezza (in caratteri, ~4 chars per parola)
        max_chars = self.max_length * 5
        if len(text) > max_chars:
            # Tronca a frase completa
            text = text[:max_chars]
            last_period = text.rfind('.')
            if last_period > max_chars * 0.5:
                text = text[:last_period + 1]
        
        # Normalizza whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def generate_embedding(
        self,
        query: str,
        expanded_query: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Genera embedding combinato con HyDE.
        
        Args:
            query: Query originale
            expanded_query: Query espansa (con glossario)
            
        Returns:
            Dict con:
            - combined_embedding: Embedding pesato finale
            - hyde_document: Documento ipotetico generato
            - weights_used: Pesi usati per combinazione
        """
        if self._embedder is None:
            logger.warning("HyDE: Embedder non disponibile")
            return None
        
        # Genera documento ipotetico
        hyde_result = self.generate(query)
        
        if hyde_result is None:
            # Fallback: usa solo query espansa
            return None
        
        try:
            # Genera embedding per tutti
            texts_to_embed = [query]
            
            if expanded_query and expanded_query != query:
                texts_to_embed.append(expanded_query)
            
            texts_to_embed.append(hyde_result.hypothetical_document)
            
            # Genera embeddings
            embeddings = self._embedder.encode(
                texts_to_embed,
                return_sparse=False,
                show_progress=False
            )
            dense_vectors = embeddings["dense"]
            
            # Combina con pesi
            import numpy as np
            
            if len(texts_to_embed) == 3:
                # Query + Expanded + HyDE
                weights = [
                    self.weights.get("query_original", 0.25),
                    self.weights.get("query_expanded", 0.35),
                    self.weights.get("hyde_document", 0.40)
                ]
            elif len(texts_to_embed) == 2:
                # Query + HyDE (no expanded)
                weights = [0.4, 0.6]
            else:
                weights = [1.0]
            
            # Normalizza pesi
            weights = np.array(weights)
            weights = weights / weights.sum()
            
            # Media pesata
            combined = np.zeros(len(dense_vectors[0]))
            for vec, w in zip(dense_vectors, weights):
                combined += np.array(vec) * w
            
            # Normalizza a unit vector
            norm = np.linalg.norm(combined)
            if norm > 0:
                combined = combined / norm
            
            return {
                "combined_embedding": combined.tolist(),
                "hyde_document": hyde_result.hypothetical_document,
                "hyde_doc_type": hyde_result.doc_type_hint,
                "hyde_time_ms": hyde_result.generation_time_ms,
                "hyde_from_cache": hyde_result.from_cache,
                "weights_used": weights.tolist()
            }
            
        except Exception as e:
            logger.error(f"HyDE embedding generation failed: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Ottiene statistiche HyDE"""
        return {
            "enabled": self.enabled,
            "cache_enabled": self.cache_enabled,
            "cache_entries": len(self._cache),
            "cache_max": self.cache_max_entries,
            "combine_method": self.combine_method,
            "weights": self.weights
        }
    
    def clear_cache(self):
        """Svuota cache"""
        self._cache.clear()
        logger.info("HyDE cache cleared")


# Utility per test
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    # Test semplice senza LLM
    config = {
        "hyde": {
            "enabled": True,
            "skip_for_definition_queries": True,
            "generation": {"max_length": 150},
            "cache": {"enabled": True}
        }
    }
    
    generator = HyDEGenerator(config)
    
    print("\n=== TEST HyDE Generator ===\n")
    
    # Test detection
    test_queries = [
        ("procedura gestione rifiuti", "PS"),
        ("come fare manutenzione preventiva", "IL"),
        ("modulo registrazione NC", "MR"),
        ("strumento 5S", "TOOL"),
        ("documentazione ISO", "GENERAL"),
    ]
    
    print("Test detection tipo documento:")
    for query, expected in test_queries:
        detected = generator._detect_doc_type(query)
        status = "✅" if detected == expected else "❌"
        print(f"  {status} '{query}' → {detected} (atteso: {expected})")
    
    # Test skip
    skip_queries = [
        ("cosa significa WCM?", True),
        ("cos'è una NC?", True),
        ("rifiuti", True),  # troppo corta
        ("come gestire i rifiuti pericolosi", False),
    ]
    
    print("\nTest skip detection:")
    for query, should_skip in skip_queries:
        skipped = generator._should_skip(query)
        status = "✅" if skipped == should_skip else "❌"
        print(f"  {status} '{query}' → skip={skipped} (atteso: {should_skip})")
    
    print("\n✅ Test completati")

