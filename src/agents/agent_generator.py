"""
Agent 5: GeneratorAgent
Responsabilità:
- Generare risposta finale con LLM
- Citare correttamente le fonti
- Formattare output

Ottimizzazione VRAM: 
- LLM condiviso con ISOAgent esistente
- Prompt ottimizzato per token ridotti
"""

from typing import Dict, Any, List
import re
import time
import logging

from src.agents.state import emit_status

logger = logging.getLogger(__name__)


class GeneratorAgent:
    """
    Genera risposta finale con citazioni.
    
    Usa l'LLM Ollama tramite ISOAgent esistente.
    Prompt strutturato per massimizzare qualità con minimo token.
    """
    
    # R26: Template base (senza error feedback)
    # MODIFICATO v2: Lista esplicita doc_id, history, istruzioni anti-allucinazione
    PROMPT_TEMPLATE = """Sei un assistente esperto del Sistema di Gestione Integrato (SGI) OVV.
{conversation_history}
{glossary_section}
{memory_section}

📋 DOCUMENTI DISPONIBILI (PUOI CITARE **SOLO** QUESTI):
{available_docs_list}

📖 CONTENUTO DOCUMENTI:
{documents}
{modules_section}

❓ DOMANDA: {query}

⚠️ ISTRUZIONI CRITICHE:
1. PUOI citare **SOLO** i documenti elencati sopra in "DOCUMENTI DISPONIBILI"
2. 🚫 NON inventare codici come PS-XX_XX, IL-XX_XX, MR-XX_XX non presenti sopra
3. Quando citi un documento, usa il suo TITOLO DESCRITTIVO (es. "La procedura Gestione della sicurezza indica..." invece di "PS-06_01 indica...")
4. Se l'informazione NON è nei documenti, scrivi "Non ho trovato informazioni specifiche nei documenti disponibili"
5. 🚫 NON aggiungere sezioni "Riferimenti:" o "Fonti:" alla fine - il sistema le aggiunge automaticamente
6. Se la procedura prevede moduli MR, suggeriscili spiegando quando usarli
7. Rispondi in italiano professionale, conciso ma completo

💡 RISPOSTA:"""

    # R26: Template con error feedback per retry
    # MODIFICATO v2: Lista esplicita doc_id, history, istruzioni anti-allucinazione
    PROMPT_TEMPLATE_RETRY = """Sei un assistente esperto del Sistema di Gestione Integrato (SGI) OVV.

{error_feedback}
{conversation_history}
{glossary_section}
{memory_section}

📋 DOCUMENTI DISPONIBILI (PUOI CITARE **SOLO** QUESTI):
{available_docs_list}

📖 CONTENUTO DOCUMENTI:
{documents}
{modules_section}

❓ DOMANDA: {query}

🚨 ISTRUZIONI CRITICHE (HAI SBAGLIATO PRIMA, LEGGI ATTENTAMENTE):
1. PUOI citare **SOLO** i documenti elencati sopra: {available_docs_list}
2. 🚫 NON inventare codici documento che non esistono sopra
3. Usa il TITOLO DESCRITTIVO del documento, non il codice
4. Se non trovi l'informazione, dillo chiaramente senza inventare fonti
5. 🚫 NON aggiungere sezioni "Riferimenti:" o "Fonti:" alla fine

💡 RISPOSTA (correggi l'errore precedente):"""

    def __init__(self, config_path: str = "config/config.yaml"):
        """Inizializza l'agente generator."""
        self.name = "generator"
        self.config_path = config_path
        self._llm_agent = None
    
    @property
    def llm_agent(self):
        """Lazy loading dell'ISOAgent"""
        if self._llm_agent is None:
            from src.memory.llm_agent import ISOAgent
            self._llm_agent = ISOAgent(config_path=self.config_path)
        return self._llm_agent
    
    def _build_prompt(self, state: Dict[str, Any]) -> str:
        """
        Costruisce prompt ottimizzato.
        
        R26: Supporta retry con error feedback dal ValidatorAgent.
        v2: Aggiunta lista esplicita doc_id e history conversazione.
        
        Ordine elementi (basato su "Lost in the Middle" research):
        1. System intro
        2. Error feedback (se retry) - ALTA VISIBILITÀ
        3. Conversation history
        4. Glossario (alta visibilità)
        5. Memoria utente
        6. Lista doc_id disponibili (NUOVO)
        7. Documenti
        8. Query
        9. Istruzioni finali
        
        Args:
            state: Stato corrente
            
        Returns:
            Prompt formattato
        """
        glossary = state.get("glossary_context", "")
        memory = state.get("memory_context", "")
        docs = state.get("compressed_context", "Nessun documento trovato.")
        query = state.get("original_query", "")
        modules = state.get("modules_section", "")  # Moduli MR correlati
        
        # R26: Controlla se è un retry con error feedback
        previous_errors = state.get("previous_errors", [])
        retry_count = state.get("retry_count", 0)
        is_retry = retry_count > 0 and previous_errors
        
        # Sezione glossario
        glossary_section = ""
        if glossary:
            glossary_section = f"\n📚 DEFINIZIONI UFFICIALI:\n{glossary}\n"
        
        # Sezione memoria
        memory_section = ""
        if memory:
            memory_section = f"\n📝 CONTESTO UTENTE:\n{memory}\n"
        
        # NUOVO v2: Lista esplicita doc_id disponibili (anti-allucinazione)
        selected_sources = state.get("selected_sources", [])
        available_docs_list = ", ".join(selected_sources) if selected_sources else "Nessun documento"
        
        # NUOVO v2: History conversazione (ultimi 4 messaggi)
        conv_history = state.get("conversation_history", [])
        conversation_section = ""
        if conv_history:
            conversation_section = "\n💬 CONVERSAZIONE PRECEDENTE:\n"
            for msg in conv_history[-4:]:  # Ultimi 4 messaggi
                role = "Utente" if msg.get("role") == "user" else "Assistente"
                content = msg.get("content", "")[:300]  # Limita lunghezza
                if len(msg.get("content", "")) > 300:
                    content += "..."
                conversation_section += f"{role}: {content}\n"
            conversation_section += "\n"
        
        # R26: Usa template retry con error feedback
        if is_retry:
            error_feedback = previous_errors[-1] if previous_errors else ""
            
            logger.info(f"GeneratorAgent: retry #{retry_count} con error feedback")
            
            return self.PROMPT_TEMPLATE_RETRY.format(
                error_feedback=error_feedback,
                conversation_history=conversation_section,
                glossary_section=glossary_section,
                memory_section=memory_section,
                available_docs_list=available_docs_list,
                documents=docs,
                modules_section=modules,
                query=query
            )
        
        # Template normale
        return self.PROMPT_TEMPLATE.format(
            conversation_history=conversation_section,
            glossary_section=glossary_section,
            memory_section=memory_section,
            available_docs_list=available_docs_list,
            documents=docs,
            modules_section=modules,
            query=query
        )
    
    def _extract_citations(
        self, 
        answer: str, 
        available_sources: List[str]
    ) -> List[str]:
        """
        Estrae citazioni effettive dalla risposta.
        
        Verifica che le citazioni esistano nei documenti disponibili
        per evitare "citazioni fantasma".
        
        Args:
            answer: Risposta generata
            available_sources: Lista doc_id disponibili
            
        Returns:
            Lista doc_id effettivamente citati
        """
        cited = []
        
        # Pattern per citazioni (PS-XX_YY, IL-XX_YY, MR-XX_YY, TOOLS-XX_YY)
        patterns = [
            r'(PS-\d{2}_\d{2})',
            r'(IL-\d{2}_\d{2})',
            r'(MR-\d{2}_\d{2})',
            r'(TOOLS-\d{2}_\d{2})',
            r'(GLOSSARY_\w+)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, answer, re.IGNORECASE)
            for match in matches:
                # Verifica che sia nelle fonti disponibili
                match_upper = match.upper()
                if any(match_upper in src.upper() for src in available_sources):
                    if match not in cited:
                        cited.append(match)
        
        return cited
    
    def _estimate_confidence(
        self, 
        state: Dict[str, Any], 
        answer: str
    ) -> float:
        """
        Stima confidence della risposta.
        
        Basata su:
        - Numero documenti usati
        - Presenza glossario
        - Lunghezza risposta
        - Citazioni presenti
        
        Args:
            state: Stato corrente
            answer: Risposta generata
            
        Returns:
            Score confidence 0.0-1.0
        """
        confidence = 0.5  # Base
        
        # Più documenti = più confidence (max +0.3)
        doc_count = len(state.get("selected_sources", []))
        confidence += min(doc_count * 0.1, 0.3)
        
        # Glossario usato = +0.1
        if state.get("glossary_context"):
            confidence += 0.1
        
        # Risposta dettagliata = +0.1
        if len(answer) > 500:
            confidence += 0.1
        
        # Citazioni presenti = bonus
        if re.search(r'(PS|IL|MR|TOOLS)-\d{2}_\d{2}', answer):
            confidence += 0.05
        
        return min(confidence, 1.0)
    
    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Genera risposta finale.
        
        Args:
            state: Stato corrente del grafo
            
        Returns:
            Aggiornamenti allo stato con risposta e citazioni
        """
        # F11: Emetti stato
        emit_status(state, "generator")
        
        start = time.time()
        
        # Costruisci prompt
        prompt = self._build_prompt(state)
        
        # Genera con LLM
        try:
            if not self.llm_agent.llm:
                raise RuntimeError("LLM non disponibile")
            
            answer = self.llm_agent.llm.invoke(prompt)
            answer = answer.strip()
            
        except Exception as e:
            logger.error(f"Errore generazione: {e}")
            answer = f"Mi dispiace, si è verificato un errore nella generazione della risposta: {str(e)}"
        
        # Estrai citazioni
        available_sources = state.get("selected_sources", [])
        cited = self._extract_citations(answer, available_sources)
        
        # Stima confidence
        confidence = self._estimate_confidence(state, answer)
        
        latency = (time.time() - start) * 1000
        
        logger.info(
            f"GeneratorAgent: {len(answer)} chars, {len(cited)} citazioni, "
            f"confidence={confidence:.2f}"
        )
        
        return {
            "answer": answer,
            "cited_sources": cited,
            "confidence": confidence,
            "agent_trace": state.get("agent_trace", []) + [f"generator:{latency:.0f}ms"]
        }


# Test standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    agent = GeneratorAgent(config_path="config/config.yaml")
    
    test_state = {
        "original_query": "Come gestire i rifiuti pericolosi?",
        "glossary_context": "📚 DEFINIZIONI:\n• SGI = Sistema di Gestione Integrato",
        "memory_context": "",
        "compressed_context": """[PS: PS-06_01]
La gestione dei rifiuti pericolosi richiede l'utilizzo di contenitori omologati
e la compilazione del registro carico/scarico entro 10 giorni.""",
        "selected_sources": ["PS-06_01", "IL-06_02"],
        "agent_trace": []
    }
    
    result = agent(test_state)
    
    print(f"Risposta ({len(result['answer'])} chars):")
    print(result['answer'][:500])
    print(f"\nCitazioni: {result['cited_sources']}")
    print(f"Confidence: {result['confidence']:.2f}")
    print(f"Trace: {result['agent_trace']}")

