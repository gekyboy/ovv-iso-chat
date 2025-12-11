"""
Agent 2: AnalyzerAgent
Responsabilità:
- Classificare l'intent della query
- Decomporre query complesse in sub-query
- Decidere routing (memoria, retrieval, teach)

Ottimizzazione VRAM: Classificazione rule-based, no LLM
"""

from typing import Dict, Any, List, Literal
import re
import time
import logging

from src.agents.state import emit_status

logger = logging.getLogger(__name__)


class AnalyzerAgent:
    """
    Analizza query e determina strategia di retrieval.
    
    Classificazione intent:
    - factual: domande su fatti specifici
    - procedural: come fare qualcosa
    - definitional: cosa significa X
    - comparison: confronto tra A e B
    - teach: richiesta spiegazione documento
    
    Non usa LLM - tutto rule-based per velocità e bassa VRAM.
    """
    
    # Pattern per classificazione intent
    INTENT_PATTERNS = {
        "definitional": [
            r"cosa significa",
            r"cos'è",
            r"che cos'è",
            r"definizione di",
            r"cosa vuol dire",
            r"cosa indica",
            r"acronimo",
            r"spiegami\s+[A-Z]{2,6}\b",  # "spiegami WCM"
            r"^\s*[A-Z]{2,6}\s*\??\s*$"  # Query solo acronimo "WCM?"
        ],
        "procedural": [
            r"come (si |devo |posso )?(?:fare|compilare|gestire|procedere)",
            r"procedura per",
            r"istruzioni per",
            r"passaggi per",
            r"step per",
            r"come (si )?usa",
            r"come (si )?compila",
            r"come (si )?registra"
        ],
        "comparison": [
            r"differenza tra",
            r"confronto",
            r"versus",
            r" vs ",
            r"meglio .+ o .+",
            r"quale scegliere",
            r"quale usare"
        ],
        "teach": [
            r"^/teach\s+\w+",
            r"spiegami come compilare",
            r"come compilo",
            r"aiutami con il modulo",
            r"esempio di compilazione"
        ]
    }
    
    # Pattern per complessità
    COMPLEXITY_INDICATORS = {
        "complex": [
            r"\b(e|inoltre|anche|contemporaneamente)\b.*\b(e|inoltre|anche)\b",
            r"(prima|poi|infine|successivamente)",
            r"(considerando|tenendo conto|in relazione a)",
            r"(tutti|ogni|ciascuno).+(e|anche).+",
        ],
        "medium": [
            r"\b(perché|quando|dove)\b",
            r"(specifico|particolare|dettaglio)",
            r"(quale|quali)\b"
        ]
    }
    
    # Pattern per rilevare bisogno memoria
    MEMORY_PATTERNS = [
        r"ricord",
        r"preferenz",
        r"come (mi |ti )?piace",
        r"solito",
        r"sempre",
        r"di norma",
        r"come faccio di solito"
    ]
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """Inizializza l'agente analyzer."""
        self.name = "analyzer"
        self.config_path = config_path
        self._ollama_url = "http://localhost:11434/api/generate"
        self._model = None
    
    def _get_model_name(self) -> str:
        """Legge il nome del modello da config."""
        if self._model is None:
            try:
                import yaml
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                self._model = config.get("llm", {}).get("model", "llama3.1:8b-instruct-q4_K_M")
            except Exception:
                self._model = "llama3.1:8b-instruct-q4_K_M"
        return self._model
    
    def _llm_expand_query(self, query: str) -> List[str]:
        """
        SOLUZIONE GENERALE: Usa LLM per espandere QUALSIASI query.
        
        L'LLM analizza la query e genera sub-query per coprire tutti
        gli aspetti rilevanti, senza regole hardcoded.
        
        Chiamata diretta a Ollama per minimizzare latenza.
        
        Args:
            query: Query originale
            
        Returns:
            Lista di sub-query (include originale)
        """
        import requests
        
        try:
            expansion_prompt = f"""Sei un assistente per documenti ISO/SGI aziendali.
Genera 2 sotto-query TESTUALI per cercare documenti relativi a questa domanda.

REGOLE IMPORTANTI:
- Scrivi query in italiano per ricerca testuale
- NON scrivere SQL, codice o comandi
- NON usare SELECT, FROM, WHERE
- Scrivi frasi brevi che potrebbero apparire nei documenti

DOMANDA: {query}

SOTTO-QUERY (una per riga):"""

            response = requests.post(
                self._ollama_url,
                json={
                    "model": self._get_model_name(),
                    "prompt": expansion_prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 80,  # Molto breve per velocità
                        "temperature": 0.3
                    }
                },
                timeout=60  # Aumentato da 30s per modelli sotto carico
            )
            
            if response.status_code != 200:
                raise Exception(f"Ollama status {response.status_code}")
            
            result_text = response.json().get("response", "")
            
            # Parse response
            lines = result_text.strip().split('\n')
            sub_queries = [query]  # Sempre includi originale
            
            for line in lines:
                # Rimuovi numerazione e spazi
                cleaned = re.sub(r'^[\d\.\-\*]+\s*', '', line.strip())
                if cleaned and len(cleaned) > 5 and cleaned != query:
                    sub_queries.append(cleaned)
            
            # Limita a 3 sub-query totali
            result = sub_queries[:3]
            logger.info(f"LLM Query Expansion: '{query}' → {result}")
            return result
            
        except Exception as e:
            logger.warning(f"LLM expansion fallita: {e}, uso query originale")
            return [query]
    
    def _classify_intent(
        self, 
        query: str
    ) -> Literal["factual", "procedural", "definitional", "comparison", "teach"]:
        """
        Classifica intent con pattern matching.
        
        Args:
            query: Query da classificare
            
        Returns:
            Intent classificato
        """
        query_lower = query.lower()
        
        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return intent
        
        return "factual"  # Default
    
    def _assess_complexity(
        self, 
        query: str
    ) -> Literal["simple", "medium", "complex"]:
        """
        Valuta complessità query.
        
        Args:
            query: Query da valutare
            
        Returns:
            Livello di complessità
        """
        query_lower = query.lower()
        
        # Count conjunctions and clauses
        conjunctions = len(re.findall(r'\b(e|o|ma|però|quindi|perché)\b', query_lower))
        
        if conjunctions >= 3:
            return "complex"
        
        for level, patterns in self.COMPLEXITY_INDICATORS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return level
        
        return "simple"
    
    def _decompose_query(
        self, 
        query: str, 
        complexity: str
    ) -> List[str]:
        """
        Decompone query in sub-query per retrieval più completo.
        
        SOLUZIONE GENERALE: Per query complesse o potenzialmente multi-aspetto,
        usa LLM per generare sub-query automaticamente. Nessuna regola hardcoded.
        
        Args:
            query: Query da decomporre
            complexity: Livello di complessità
            
        Returns:
            Lista di sub-query
        """
        # Query semplici e molto corte → nessuna decomposizione
        if complexity == "simple" and len(query.split()) <= 3:
            return [query]
        
        # Decomposizione esplicita per congiunzioni
        if re.search(r'\s+(?:e|inoltre|anche)\s+', query, re.IGNORECASE):
            sub_queries = re.split(
                r'\s+(?:e|inoltre|anche)\s+', 
                query, 
                flags=re.IGNORECASE
            )
            sub_queries = [q.strip() for q in sub_queries if q.strip()]
            if len(sub_queries) > 1:
                return sub_queries[:3]
        
        # Per query potenzialmente multi-aspetto → LLM expansion
        # Attiva per: complessità media/alta O query con termini generici
        generic_terms = ["gestire", "gestione", "procedure", "regole", "normativa", "come"]
        has_generic = any(term in query.lower() for term in generic_terms)
        
        if complexity in ["medium", "complex"] or has_generic:
            return self._llm_expand_query(query)
        
        return [query]
    
    def _should_use_memory(self, query: str) -> bool:
        """
        Determina se usare memoria utente.
        
        Args:
            query: Query da analizzare
            
        Returns:
            True se la query richiede contesto dalla memoria
        """
        query_lower = query.lower()
        return any(re.search(p, query_lower) for p in self.MEMORY_PATTERNS)
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analizza query e imposta strategia.
        
        Args:
            state: Stato corrente del grafo
            
        Returns:
            Aggiornamenti allo stato
        """
        # F11: Emetti stato
        emit_status(state, "analyzer")
        
        start = time.time()
        
        # Usa query espansa se disponibile
        query = state.get("expanded_query") or state.get("original_query", "")
        
        # Classificazioni
        intent = self._classify_intent(query)
        complexity = self._assess_complexity(query)
        sub_queries = self._decompose_query(query, complexity)
        use_memory = self._should_use_memory(query)
        
        latency = (time.time() - start) * 1000
        
        logger.info(
            f"AnalyzerAgent: intent={intent}, complexity={complexity}, "
            f"sub_queries={len(sub_queries)}, use_memory={use_memory}"
        )
        
        return {
            "query_intent": intent,
            "complexity": complexity,
            "sub_queries": sub_queries,
            "should_use_memory": use_memory,
            "agent_trace": state.get("agent_trace", []) + [f"analyzer:{latency:.0f}ms"]
        }


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    agent = AnalyzerAgent()
    
    test_queries = [
        "Cosa significa WCM?",
        "Come compilare il modulo MR-10_01?",
        "Differenza tra NC e AC",
        "Gestisci i rifiuti e anche le emergenze e le NC",
        "Ricordati che preferisco risposte brevi"
    ]
    
    for query in test_queries:
        state = {
            "original_query": query,
            "expanded_query": query,
            "agent_trace": []
        }
        result = agent(state)
        print(f"\nQuery: {query}")
        print(f"  Intent: {result['query_intent']}")
        print(f"  Complexity: {result['complexity']}")
        print(f"  Sub-queries: {result['sub_queries']}")
        print(f"  Use memory: {result['should_use_memory']}")

