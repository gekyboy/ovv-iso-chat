# 🏭 OVV ISO Chat v3.9.1

> Il tuo assistente **discorsivo e proattivo** per i documenti ISO aziendali. Chiedi quello che ti serve, lui trova la risposta nei documenti, te la spiega in dettaglio e ti suggerisce **moduli e strumenti correlati**.

> 🆕 **v3.9.1**: **PDF Consultabili & Citazioni Leggibili** - I PDF si aprono in sidebar, le citazioni mostrano titoli italiani tra virgolette, fonti separate da glossario!

> 📂 **Nuovo in v3.9.1**: Comando `/documenti` per gestire la cartella documenti direttamente dalla chat (F10)!

## Indice

- [🚀 Quick Start](#-quick-start)
- [📖 Guida Utente](#-guida-utente)
- [🔬 Deep Dive Tecnico](#-deep-dive-tecnico)
- [📜 Appendici](#-appendici)

---

# 🚀 Quick Start

**Prerequisiti**: Windows 10+, GPU NVIDIA con 6GB+ VRAM, Docker Desktop attivo.

## 1️⃣ Avvia

> 📁 **Doppio click su:** `avvia_chat.bat`

## 2️⃣ Apri il browser

Vai su: **http://localhost:7866**

## 3️⃣ Login

| Chi sei | Username | Password |
|---------|----------|----------|
| 🔴 **Admin** | `admin` | `admin123` |
| 🟡 **Ingegnere** | `engineer` | `eng123` |
| 🟢 **Utente** | `user` | `user123` |

## 4️⃣ Prova subito questi comandi

```
Come gestisco i rifiuti pericolosi?     → Domanda normale
/teach MR-10_01                          → Spiega come compilare un modulo
/status                                  → Stato del sistema
```

---

# 📖 Guida Utente

## ❓ Cos'è OVV ISO Chat?

Immagina di avere centinaia di documenti aziendali: procedure, istruzioni, moduli. Cercare un'informazione significa sfogliare PDF, perdere tempo, rischiare di non trovare nulla.

**OVV ISO Chat risolve questo problema.**

È come avere un collega esperto che ha letto TUTTI i documenti e può risponderti in linguaggio naturale. Gli chiedi *"Come gestire i rifiuti?"* e lui ti risponde citando esattamente le procedure giuste.

### 🎯 A cosa serve?

- **Trovare informazioni velocemente** nei documenti ISO
- **Capire le procedure** senza leggere manuali interi
- **Avere risposte con fonti** sempre citate
- **Ricordare le tue preferenze** per risposte personalizzate

### 🏢 Per chi è pensato?

- Quality Manager, HSE Manager
- Responsabili di produzione
- Auditor interni
- Operatori che consultano procedure

---

## 👤 Cosa Puoi Fare in Base al Tuo Ruolo

### 🟢 Utente (`user`)
*L'utente base può usare la chat e salvare le proprie preferenze.*

| Cosa puoi fare | Come si fa |
|----------------|------------|
| 💬 **Fare domande** | Scrivi la domanda e premi Invio |
| 📖 **Capire un documento** | `/teach MR-10_01` |
| 💾 **Salvare una preferenza** | `/memoria preference Preferisco risposte brevi` |
| 💡 **Salvare un fatto** | `/memoria fact Il Quick Kaizen dura max 5 giorni` |
| 📚 **Cercare nel glossario** | `/glossario WCM` |
| 📤 **Proporre per tutti** | `/propose fact CDL significa Centro Di Lavoro` |
| 📊 **Vedere lo stato** | `/status` |
| 📂 **Vedere cartella documenti** | `/documenti` |
| 👍👎 **Dare feedback** | Clicca i pulsanti dopo ogni risposta |

### 🟡 Ingegnere (`engineer`)
*L'ingegnere può fare tutto quello che fa l'utente, più:*

| Cosa puoi fare in più | Come si fa |
|-----------------------|------------|
| 👁️ **Vedere proposte in attesa** | `/pending` |
| ❌ **Rifiutare una proposta** | `/reject abc123 Motivo del rifiuto` |
| 👥 **Vedere memorie altri utenti** | `/memorie mario` |
| 📂 **Cambiare cartella documenti** | `/documenti D:\MieiPDF` |
| 📂 **Path recenti** | `/documenti recenti` |

### 🔴 Amministratore (`admin`)
*L'admin può fare tutto, incluso approvare e gestire utenti.*

| Cosa puoi fare in più | Come si fa |
|-----------------------|------------|
| ✅ **Approvare una proposta** | `/approve abc123` |
| 🌍 **Aggiungere memoria globale** | `/global add fact Gli audit sono mensili` |
| 📚 **Aggiungere al glossario** | `/glossario add QK = Quick Kaizen` |
| 🎛️ **Pannello Admin visuale** | Vai su **http://localhost:8501** |

---

## 💬 Tutti i Comandi

### Domande Normali
```
Come gestisco i rifiuti pericolosi?
Cosa dice la procedura PS-06_01?
Qual è la differenza tra NC e AC?
```

### Comandi Speciali (Tutti gli utenti)
```
/teach MR-10_01                              → Spiega come compilare il modulo
/memoria fact WCM significa World Class      → Salva un fatto
/memoria preference Risposte dettagliate     → Salva una preferenza
/glossario NC                                → Cerca significato acronimo
/glossario add QK = Quick Kaizen             → Aggiunge termine (se admin)
/status                                      → Stato del sistema
/propose fact CDL = Centro Di Lavoro         → Proponi per approvazione Admin
/history                                     → Cronologia tue conversazioni (R28)
/history 20                                  → Ultime 20 sessioni
/history today                               → Solo sessioni di oggi
/documenti                                   → Mostra cartella documenti attuale
```

### Comandi Admin/Engineer
```
/documenti D:\MieiPDF                        → Cambia cartella documenti (F10)
/documenti recenti                           → Mostra path usati di recente
/documenti reset                             → Torna alla cartella di default
```

```
/pending                                     → Lista proposte in attesa
/reject abc123 Non corretto                  → Rifiuta proposta
/approve abc123                              → Approva proposta (solo Admin)
/global add fact Gli audit sono mensili      → Memoria globale (solo Admin)
/memorie mario                               → Vedi memorie di un utente
/gaps                                        → Lacune segnalate dagli utenti (R19)
/acronyms                                    → Acronimi estratti automaticamente (R05)
/acronyms approve WCM                        → Approva acronimo → glossario
/acronyms reject XYZ motivo                  → Rifiuta acronimo estratto
/teach_stats                                 → Statistiche assistenza compilazione (R16)
/history all                                 → Cronologia tutti gli utenti (R28)
```

---

## 📝 Esempi d'Uso

### Esempio 1: Domanda Semplice

**Tu scrivi:**
```
Come gestire i rifiuti pericolosi?
```

**Il sistema risponde:**
```
La gestione dei rifiuti pericolosi è regolamentata dalla procedura PS-06_01 
e dalle istruzioni operative IL-06_02.

**Punti chiave:**

1. **Identificazione**: I rifiuti pericolosi devono essere identificati 
   secondo il codice CER e classificati per tipologia.

2. **Stoccaggio**: Utilizzare contenitori omologati con etichettatura 
   conforme. Lo stoccaggio temporaneo non deve superare i 12 mesi.

3. **Registrazione**: Compilare il registro di carico/scarico (MR-06_01) 
   entro 10 giorni dall'operazione.

4. **Trasporto**: Solo trasportatori autorizzati con formulario FIR.

📚 **Fonti:** PS-06_01, IL-06_02, MR-06_01
⏱️ *2847ms*
```

### Esempio 2: Usare Acronimi

**Tu scrivi:**
```
Cosa dice il SGI sulla gestione delle NC?
```

**Il sistema capisce** che SGI = Sistema di Gestione Integrato e NC = Non Conformità, e ti risponde in modo appropriato citando le procedure corrette.

### Esempio 2.5: Disambiguazione Intelligente (R06)

**Tu scrivi:**
```
Mostrami le NC
```

**Il sistema riconosce** che NC è ambiguo (può essere "Non Conformità" o "Nota di Credito") e non c'è abbastanza contesto. Ti chiede:

```
❓ **NC** può significare:

**1. Non Conformità** ⭐ _tua preferenza abituale_
**2. Nota di Credito**

Quale intendi in questo caso?
```

**Tu clicchi** su "Non Conformità" e il sistema:
1. Risponde alla tua domanda
2. **Ricorda** la tua preferenza per la prossima volta (ma senza forzarla!)

**Nota**: Se avessi scritto "Mostrami le NC dell'audit", il sistema avrebbe capito automaticamente che intendevi "Non Conformità" dal contesto "audit".

### Esempio 3: Imparare a Compilare un Modulo

**Tu scrivi:**
```
/teach MR-10_01
```

**Il sistema risponde:**
```
📖 **Come compilare MR-10_01:**

Il modulo MR-10_01 è il **Modulo di Segnalazione Miglioramento** utilizzato 
per proporre Quick Kaizen e iniziative di miglioramento continuo.

| Campo | Descrizione | Esempio |
|-------|-------------|---------|
| Data | Data della segnalazione | 06/12/2025 |
| Proponente | Nome e reparto | Mario Rossi - Produzione |
| Area | Area di intervento | Linea 3 - Assemblaggio |
| Proposta | Soluzione proposta | Riorganizzare layout |
| Benefici | Risultati previsti | -15% tempo ciclo |

**Note importanti:**
- Per Quick Kaizen, l'implementazione deve avvenire entro 5 giorni
- Dopo implementazione, compilare la sezione "Risultati ottenuti"

📚 **Riferimento:** PS-10_01 - Gestione Miglioramento Continuo
```

### Esempio 4: Correlazioni Automatiche (v3.9)

**Tu scrivi:**
```
Ho avuto un infortunio sul lavoro, cosa devo fare?
```

**Il sistema risponde:**
```
Per gestire un infortunio sul lavoro devi seguire la procedura PS-06_01 
e utilizzare il modulo Safety EWO (MR-06_01).

**Passi principali:**
1. Segnala immediatamente l'infortunio al responsabile
2. Compila il modulo MR-06_01 - Safety EWO entro 24 ore
3. Avvia l'analisi causa radice con i 5 Perché

📌 **Strumenti da utilizzare insieme:**
- 5 Perché → analisi causa radice
- 5W1H → raccolta dati iniziali
- 4M Ishikawa → diagramma causa-effetto

⚠️ **IMPORTANTE**: NON usare MR-06_02 (Near Miss) - quello è per 
quasi-incidenti SENZA lesioni!

📚 **Fonti:** PS-06_01, MR-06_01_Safety EWO, IL-06_03
⏱️ *3847ms*
```

**Nota:** Il sistema ha capito che si tratta di un infortunio REALE (non un near miss) e ha suggerito il modulo corretto con gli strumenti correlati.

### Esempio 5: Salvare una Preferenza

**Tu scrivi:**
```
/memoria preference Preferisco risposte brevi e con elenchi puntati
```

**Il sistema risponde:**
```
✅ Preferenza salvata! Le prossime risposte saranno più brevi e strutturate.
```

---

## 🎛️ Pannello Admin (Solo Amministratori)

Se sei **admin**, hai accesso anche al pannello visuale:

**URL:** http://localhost:8501

| Sezione | Cosa puoi fare |
|---------|----------------|
| 📊 **Dashboard** | Vedere statistiche e KPI del sistema |
| 📋 **Proposte** | Approvare/rifiutare proposte degli utenti |
| 📚 **Glossario** | Aggiungere, modificare, eliminare acronimi |
| 🧠 **Memorie** | Vedere e gestire le memorie di tutti |
| 👥 **Utenti** | Creare, modificare, eliminare utenti |

---

## 👍👎 Sistema Feedback

Dopo ogni risposta, puoi valutarla con i pulsanti **Utile** o **Non utile**.

Il sistema **impara** dai tuoi feedback:
- Le risposte che ti piacciono diventano più probabili
- Le risposte che non ti piacciono vengono penalizzate

Questo rende il sistema sempre più personalizzato per te!

---

## 🧠 Apprendimento Automatico (v3.5)

Il sistema impara **automaticamente** dalle tue azioni, senza che tu debba fare nulla:

| Cosa fai | Cosa impara il sistema |
|----------|------------------------|
| 📋 **Clicchi** su una fonte citata | "Questo documento è utile" |
| 📝 **Copi** parte della risposta | "Questa informazione è rilevante" |
| ⏱️ **Leggi** a lungo una risposta | "Contenuto interessante" |
| 🔄 **Riformuli** la domanda | "La risposta non era soddisfacente" |
| ✅ **Completi** un /teach | "Questa spiegazione funziona" |

**Consenso Multi-Utente:** Quando più utenti confermano la stessa cosa (es. cliccano la stessa fonte, copiano la stessa definizione), il sistema può promuovere automaticamente quella conoscenza a **globale** per tutti gli utenti.

> 💡 **Esempio**: Se 3 utenti diversi cliccano sulla fonte PS-06_01 quando chiedono "gestione rifiuti", il sistema capisce che quel documento è rilevante per quel tema.

---

## 📄 Fonti nelle Risposte

Ogni risposta mostra le **fonti consultate** in modo chiaro e organizzato (v3.9.1):

```
---
📚 **Fonti consultate:**
- 📄 PS-06_01_Rev.04_Gestione della sicurezza negli ambienti di lavoro
- 📄 IL-06_02_Rev.02_Rifiuti pericolosi

📖 **Termini glossario:**
- 📝 Emergency Work Order
```

**Novità v3.9.1:**
- **Titoli leggibili nel testo**: Le citazioni nel testo mostrano il titolo italiano tra virgolette (es. `"Gestione della sicurezza"`) invece del codice tecnico (es. `PS-06_01`)
- **Nome completo nel footer**: Include `doc_id_Rev.XX_Titolo italiano`
- **Separazione PDF/Glossario**: I documenti PDF sono separati dai termini del glossario
- **PDF consultabili**: Clicca sul nome per aprire il PDF nella sidebar (non download)
- **Apertura alla pagina giusta**: Il PDF si apre alla pagina corretta

---

# 🔬 Deep Dive Tecnico

> ⚠️ **Questa sezione è per chi vuole capire come funziona il sistema internamente.**
> Se vuoi solo usarlo, la Guida Utente è sufficiente.

---

## 🔮 Come Funziona? (Spiegato Semplice)

Il sistema funziona in due fasi: prima **impara** dai documenti, poi **risponde** alle domande.

### Fase 1: Imparare dai Documenti 📚➡️🧠

```
I tuoi PDF ──► Lettura ──► Comprensione ──► Memoria Digitale
```

1. **Leggiamo i PDF** - Il sistema apre ogni documento e estrae il testo
2. **Dividiamo in pezzi** - Ogni documento viene spezzato in parti più piccole (chunk) per essere più facile da cercare
3. **Creiamo "impronte digitali"** - Ogni pezzo viene trasformato in numeri (embedding) che ne catturano il significato
4. **Salviamo in memoria** - Questi numeri finiscono in un database speciale che sa cercare per significato

Pensa ai chunk come post-it: invece di cercare in un libro intero, cerchi tra tanti post-it organizzati per argomento.

### Fase 2: Rispondere alle Domande 🗣️➡️💡

```
La tua domanda ──► Ricerca ──► Selezione ──► Risposta intelligente
```

1. **Capiamo la domanda** - Espandiamo acronimi (SGI → Sistema di Gestione Integrato) e arricchiamo il contesto
2. **Cerchiamo i pezzi giusti** - Troviamo i chunk più simili alla tua domanda (come un motore di ricerca super intelligente)
3. **Filtriamo il meglio** - Usiamo due "giudici" AI per tenere solo i documenti veramente rilevanti
4. **Generiamo la risposta** - Un modello di linguaggio legge i documenti selezionati e scrive una risposta chiara

### Come si Incontrano? 🤝

```
                    ┌─────────────────┐
                    │  La tua domanda │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Comprensione  │  "Cosa sta chiedendo?"
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼────────┐     │     ┌────────▼────────┐
     │  Memoria delle  │     │     │   I documenti   │
     │  tue preferenze │     │     │   trasformati   │
     └────────┬────────┘     │     └────────┬────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼────────┐
                    │  Il cervello AI │  "Risposta basata su tutto"
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │    RISPOSTA     │
                    │  + Fonti citate │
                    └─────────────────┘
```

È come un incrocio dove:
- **Da sinistra** arrivano i documenti preparati
- **Da destra** arrivano le tue preferenze e la storia
- **Al centro** l'AI mette tutto insieme

---

## 🛠️ Tecnologie Utilizzate

### I "Cervelli" dell'AI

| Componente | Modello | Cosa fa |
|------------|---------|---------|
| **Comprensione testo** | BGE-M3 | Trasforma testo in numeri che catturano il significato |
| **Primo filtro** | FlashRank | Scarta velocemente i documenti meno rilevanti |
| **Secondo filtro** | Qwen3 Reranker | Analisi fine per tenere solo il meglio |
| **Generazione risposte** | Llama 3.1 8B | Scrive risposte naturali e accurate |

### L'Infrastruttura

| Componente | Tecnologia | Ruolo |
|------------|------------|-------|
| **Database vettoriale** | Qdrant | Cerca documenti per significato, non per parole esatte |
| **Server LLM** | Ollama | Esegue i modelli AI localmente (niente cloud!) |
| **Interfaccia** | Chainlit | UI moderna con feedback integrato |
| **Autenticazione** | bcrypt + JWT | Login sicuro con ruoli RBAC |
| **Orchestrazione** | Python | Collega tutto insieme |

### Requisiti Hardware

- **GPU**: NVIDIA RTX 3060 6GB (o superiore)
- **RAM**: 16GB consigliati
- **Storage**: ~10GB per modelli e dati

---

## 🏗️ Architettura Tecnica

### Schema del Sistema

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              OVV ISO Chat v3.9                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         INGESTION PIPELINE                          │   │
│  │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐  │   │
│  │  │   PDF    │──►│ Extractor│──►│ Chunker  │──►│ BGE-M3 Embedder  │  │   │
│  │  │ Documents│   │ (PyMuPDF)│   │(Parent+  │   │ (Dense + Sparse) │  │   │
│  │  └──────────┘   └──────────┘   │ Child)   │   └────────┬─────────┘  │   │
│  │                                └──────────┘            │            │   │
│  │                                                        ▼            │   │
│  │                                              ┌──────────────────┐   │   │
│  │                                              │     Qdrant       │   │   │
│  │                                              │  Vector Database │   │   │
│  │                                              └──────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          RAG PIPELINE                                │   │
│  │                                                                      │   │
│  │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐  │   │
│  │  │  Query   │──►│ Glossary │──►│ Hybrid   │──►│    Reranking     │  │   │
│  │  │  Input   │   │ Expansion│   │ Retrieval│   │ L1: FlashRank    │  │   │
│  │  └──────────┘   └──────────┘   │ (40 docs)│   │ L2: Qwen3 GGUF   │  │   │
│  │                                └──────────┘   └────────┬─────────┘  │   │
│  │                                                        │            │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │                                                              │  │   │
│  │  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐  │  │   │
│  │  │  │   Memory     │ + │  Top 5 Docs  │ ──►│  Llama 3.1 8B    │  │  │   │
│  │  │  │   Context    │   │  (Reranked)  │   │   (Generation)   │  │  │   │
│  │  │  └──────────────┘   └──────────────┘   └────────┬─────────┘  │  │   │
│  │  │                                                  │           │  │   │
│  │  └──────────────────────────────────────────────────┼───────────┘  │   │
│  │                                                     ▼              │   │
│  │                                            ┌──────────────────┐    │   │
│  │                                            │     Response     │    │   │
│  │                                            │   + Sources      │    │   │
│  │                                            └──────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         MEMORY SYSTEM                                │   │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐ │   │
│  │  │  Preferences │   │    Facts     │   │  Bayesian Feedback Boost │ │   │
│  │  │  (User prefs)│   │  (Learned)   │   │  (0.8x - 1.2x scoring)   │ │   │
│  │  └──────────────┘   └──────────────┘   └──────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📄 Pipeline di Ingestion

### 1. Estrazione PDF (`extractor.py`)

```python
# Il documento viene aperto con PyMuPDF
PDF → ExtractedDocument {
    metadata: {
        doc_type: "PS" | "IL" | "MR" | "TOOLS",
        chapter: "06",
        doc_number: "01",
        revision: "3",
        title: "Gestione Rifiuti",
        priority: 1.0  # PS=1.0, IL=0.9, MR=0.85, TOOLS=0.85
    },
    pages: [ExtractedPage...],
    full_text: "..."
}
```

**Pattern di estrazione filename:**
- `PS-06_01` → Procedura di Sistema, Capitolo 06, Documento 01
- `IL-07_02` → Istruzione di Lavoro, Capitolo 07, Documento 02
- `MR-10_03` → Modulo di Registrazione, Capitolo 10, Documento 03

### 2. Chunking Gerarchico (`chunker.py`)

Il testo viene diviso in due livelli:

```
Documento Originale (es. 5000 caratteri)
         │
         ▼
┌─────────────────────────────────────────────┐
│              PARENT CHUNKS                  │
│  (1200 caratteri, overlap 200)              │
│                                             │
│  [Parent 1] [Parent 2] [Parent 3] [Parent 4]│
│      │          │          │          │     │
│      ▼          ▼          ▼          ▼     │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐    │
│  │Child │  │Child │  │Child │  │Child │    │
│  │ 1.1  │  │ 2.1  │  │ 3.1  │  │ 4.1  │    │
│  │Child │  │Child │  │Child │  │Child │    │
│  │ 1.2  │  │ 2.2  │  │ 3.2  │  │ 4.2  │    │
│  │Child │  │Child │  │Child │  │Child │    │
│  │ 1.3  │  │ 2.3  │  │ 3.3  │  │ 4.3  │    │
│  └──────┘  └──────┘  └──────┘  └──────┘    │
│  (400 caratteri ciascuno, overlap 100)      │
└─────────────────────────────────────────────┘
```

**Strategia per tipo documento:**
- **Dense** (PS, IL): Parent + Child chunks → ricerca dettagliata
- **Synthetic** (MR, TOOLS): Chunk generati da metadata semantici (v3.9)

### 2.5 Synthetic Chunking per MR/TOOLS (R30) - v3.9

I documenti **MR** (Moduli Registrazione) e **TOOLS** sono template tabellari vuoti, inutili se estratti direttamente da PDF. Il sistema genera **chunk sintetici** dai metadata:

```
┌────────────────────────────────────────────────────────────────────────────┐
│  PROBLEMA: PDF MR/TOOLS = tabelle vuote                                   │
│                                                                            │
│  ┌─────────────────┐                                                       │
│  │ MR-10_01.pdf    │ → Estrazione → "| Campo | Valore |" (inutile!)       │
│  │ [Major Kaizen]  │                                                       │
│  └─────────────────┘                                                       │
│                                                                            │
│  SOLUZIONE: Chunk Sintetici da Metadata                                    │
│                                                                            │
│  ┌─────────────────┐     ┌──────────────────────────────────────────────┐ │
│  │ semantic_       │     │ 📄 MODULO: MR-10_01 - Major Kaizen           │ │
│  │ metadata.json   │  →  │ 📂 Categoria: kaizen_project                  │ │
│  │ document_       │     │ 🎯 USA QUANDO: progetto miglioramento         │ │
│  │ metadata.json   │     │ ⚠️  NON USARE PER: quick kaizen, kaizen flash │ │
│  │ tools_mapping.  │     │ 🔗 PROCEDURA: PS-10_01                        │ │
│  │ json            │     │ 🛠️  DA USARE CON: 4M Ishikawa, 5 Perché,     │ │
│  └─────────────────┘     │     5W1H, Poka Yoke, QM Matrix                │ │
│                          │ 📋 CAMPI: Team, Cronoprogramma, Budget...     │ │
│                          └──────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────┘
```

**File Metadata (config/):**

| File | Contenuto | Documenti |
|------|-----------|-----------|
| `semantic_metadata.json` | 90 voci con `applies_when`, `not_for`, `incident_category`, `related_keywords` | Tutti MR + TOOLS |
| `document_metadata.json` | Titolo, scopo, correlazioni estratte da PDF | MR + TOOLS |
| `tools_mapping.json` | Keywords, concepts, campi per R15/R16 | 93 tool mappati |

**Vantaggi:**
- 📈 **Retrieval migliorato**: I chunk sintetici contengono semantica ricca (es. "usa quando hai un infortunio")
- 🔗 **Correlazioni automatiche**: Il sistema suggerisce strumenti correlati (es. "Da usare con: 5 Perché, Ishikawa")
- 🎯 **Intent matching**: Query "Ho avuto un infortunio" → trova `MR-06_01` (Safety EWO) e non `MR-06_02` (Near Miss)
- 📊 **Priorità equilibrata**: MR ora ha priorità 0.85 (era 0.5 - penalizzato)

### 2.7 Arricchimento Chunks - Prepending Context (R21)

Prima dell'embedding, ogni chunk (inclusi quelli sintetici) viene **arricchito** con contesto:

```
┌─────────────────────────────────────────────────────────────┐
│ CHUNK ORIGINALE                                             │
│ "La gestione dei rifiuti pericolosi richiede..."           │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ CHUNK ARRICCHITO                                            │
│                                                             │
│ [DOC: PS-06_01 | Sezione: 4.2 | Titolo: Gestione Rifiuti]  │
│ [Glossario: CER = Catalogo Europeo Rifiuti]                │
│                                                             │
│ La gestione dei rifiuti pericolosi richiede...             │
└─────────────────────────────────────────────────────────────┘
```

**Cosa viene aggiunto:**
- **Header contestuale**: doc_id, sezione, titolo, revisione
- **Glossario**: definizioni acronimi presenti nel chunk
- **Scopo documento**: solo per PS/IL (primi 200 caratteri)

**Benefici:**
- L'embedding cattura anche il contesto del documento
- Query "rifiuti PS-06" trova chunks del documento corretto
- Acronimi nel chunk sono ricercabili semanticamente

### 3. Embedding con BGE-M3 (`indexer.py`)

Ogni chunk viene trasformato in due tipi di vettori:

```python
Chunk Text: "La gestione dei rifiuti pericolosi richiede..."
                              │
                              ▼
              ┌───────────────────────────────┐
              │         BGE-M3 Model          │
              │      (BAAI/bge-m3)            │
              └───────────────┬───────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
   Dense Vector                            Sparse Vector
   [0.012, -0.034, ...]                   {"rifiuti": 0.8, 
   (1024 dimensioni)                       "pericolosi": 0.7,
                                           "gestione": 0.5}
```

- **Dense Vector**: Cattura il significato semantico globale
- **Sparse Vector**: Cattura le parole chiave importanti (BM25-style)

### 4. Indicizzazione in Qdrant

```python
# Struttura del punto in Qdrant
{
    "id": "uuid-...",
    "vector": {
        "dense": [0.012, -0.034, ...],  # 1024 dim
        "sparse": {"indices": [...], "values": [...]}
    },
    "payload": {
        "text": "La gestione dei rifiuti...",
        "doc_id": "PS-06_01",
        "doc_type": "PS",
        "chapter": "06",
        "chunk_type": "parent",  # o "child"
        "priority": 1.0,
        "metadata": {...}
    }
}
```

---

## 🔍 Pipeline di Retrieval

### Flow Completo della Query (v3.8)

```
Query: "Come gestire le NC nel processo?"
                    │
                    ▼
        ┌───────────────────────┐
        │  0. DISAMBIGUATION    │  (R06)
        │  NC ambiguo?          │
        │  Contesto: "processo" │
        │  → Non Conformità ✓   │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  1. GLOSSARY EXPANSION │  (R20)
        │  + Context Injection   │
        │  SGI → Sistema di      │
        │  Gestione Integrato    │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  1.5 LLM QUERY EXPAND │  (v3.8)
        │  Genera sub-query     │
        │  per topic complessi  │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  2. HyDE GENERATION   │  (R23)
        │  LLM genera documento  │
        │  ipotetico (150 parole)│
        └───────────┬───────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌───────────────┐       ┌───────────────┐
│ 3a. DOCS      │       │ 3b. GLOSSARY  │  (R22)
│ RETRIEVAL     │       │ RETRIEVAL     │
│ iso_sgi_docs  │       │ glossary_terms│
└───────┬───────┘       └───────┬───────┘
        │                       │
        └───────────┬───────────┘
                    ▼
        ┌───────────────────────┐
        │  3c. RRF MERGE        │  (R22)
        │  Reciprocal Rank      │
        │  Fusion + Boost       │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  4. RERANK L1         │
        │  FlashRank (CPU)      │
        │  40 → 15 documenti    │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  5. RERANK L2         │
        │  Qwen3 GGUF (CPU)     │
        │  15 → 5 documenti     │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  6. MEMORY INJECTION  │
        │  + preferenze utente  │
        │  + fatti appresi      │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │  6. LLM GENERATION    │
        │  Llama 3.1 8B (GPU)   │
        │  Risposta + Fonti     │
        └───────────────────────┘
```

### Dettaglio Reranking a 2 Livelli

```python
# Livello 1: FlashRank (veloce, CPU)
# Modello: ms-marco-MiniLM-L-12-v2
# Input: 40 documenti dal retrieval
# Output: Top 15 per relevance score

# Livello 2: Qwen3 Reranker (preciso, CPU)  
# Modello: Qwen3-Reranker-0.6B-GGUF
# Input: 15 documenti da L1
# Output: Top 5 per final score
```

Perché due livelli?
- **L1** è velocissimo (~10ms) ma meno preciso
- **L2** è più lento (~200ms) ma molto più accurato
- Combinandoli: velocità + qualità

---

## 📚 Sistema Glossario

Il glossario è il primo step della pipeline di query: **espande gli acronimi** prima della ricerca per migliorare il retrieval.

### Glossary Context Injection (R20)

Le definizioni degli acronimi vengono ora **iniettate esplicitamente** nel prompt dell'LLM:

```
📚 DEFINIZIONI ACRONIMI:
• WCM = World Class Manufacturing (metodologia di miglioramento continuo)
• PDCA = Plan-Do-Check-Act (ciclo di Deming)
• NC = Non Conformità
```

**Perché è importante?**
- Prima: le definizioni erano nascoste tra parentesi nella query espansa
- Ora: l'LLM vede chiaramente le definizioni con **priorità visiva**
- Risultato: risposte più accurate che usano correttamente gli acronimi

### Dual Embedding - Glossario come Collezione (R22)

Il glossario è ora indicizzato come **collezione Qdrant separata** (`glossary_terms`):

```
Query: "WCM"
    │
    ├─► iso_sgi_docs (documenti)  ──┐
    │                               │
    └─► glossary_terms (definizioni)├──► RRF Merge ──► Risultati
                                    │
```

**Vantaggi:**
- Ricerca semantica sulle definizioni (non solo matching esatto)
- Query "cosa significa WCM?" trova la definizione via embedding
- Boost automatico per query definitorie (+50%)
- Reciprocal Rank Fusion (RRF) per merge risultati

### LLM Query Expansion Generale (v3.8)

Per query complesse o multi-aspetto, il sistema genera automaticamente **sub-query** per trovare TUTTE le informazioni rilevanti:

```
Query: "Come gestire i rifiuti?"
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM genera sub-query automaticamente:                       │
│                                                             │
│ Prompt: "Genera 2 sotto-query specifiche per questa        │
│          domanda. Rispondi SOLO con le query."             │
│                                                             │
│ Output:                                                     │
│ - gestione rifiuti non pericolosi raccolta differenziata   │
│ - gestione rifiuti pericolosi CER smaltimento              │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
       3 query parallele
       (originale + 2 sub)
              │
              ▼
         Qdrant Search
```

**Caratteristiche:**
- **Generale**: Nessuna regola hardcoded, funziona per QUALSIASI argomento
- **Automatico**: Attivato per query con termini generici (gestire, procedure, normativa)
- **Fallback**: Se LLM timeout, usa query originale senza bloccare
- **Veloce**: Prompt breve (80 token max), timeout 30s, cache implicita

**Vantaggi:**
- Risposte più complete su argomenti con sottocategorie
- Non richiede configurazione per ogni nuovo topic
- L'LLM capisce semanticamente cosa espandere

### HyDE - Hypothetical Document Embeddings (R23)

Prima del retrieval, il sistema genera un **documento ipotetico** che risponde alla query:

```
Query: "come gestire i rifiuti pericolosi"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ LLM genera documento ipotetico (150 parole):                │
│ "La gestione dei rifiuti pericolosi secondo ISO 14001       │
│  prevede: identificazione CER, registro carico/scarico..."  │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
         Embedding combinato:
         Query (25%) + Expanded (35%) + HyDE (40%)
                    │
                    ▼
              Qdrant Search
```

**Vantaggi:**
- Il documento ipotetico cattura pattern linguistici dei documenti reali
- Migliora precision retrieval del 15-20% per query complesse
- Template specifici per tipo documento (PS/IL/MR/TOOL)
- Skip automatico per query definitorie (già coperte da R20/R22)
- Cache documenti ipotetici (TTL 1 ora)

### Funzionalità del Glossario

| Funzione | Descrizione | Esempio |
|----------|-------------|---------|
| `resolve_acronym()` | Risolve singolo acronimo | `"PS"` → `"Procedura di Sistema"` |
| `resolve_with_context()` | Disambigua con contesto (R06) | `"NC" + "audit"` → `"Non Conformità"` |
| `expand_query()` | Espande tutti gli acronimi | `"PS e IL"` → `"PS (Procedura...) e IL (Istruzione...)"` |
| `fuzzy_match()` | Match approssimato | `"procedura"` → suggerisce `"PS"` |
| `rewrite_query()` | Riscrittura completa + contesto | Aggiunge metadata documento |

### Aggiornamento Dinamico

Il glossario può essere arricchito dalla memoria:

```
/memoria fact Quick Kaizen si abbrevia QK
```

Questo aggiunge `QK → Quick Kaizen` al glossario runtime.

---

## 🧠 Sistema di Memoria

### Tipi di Memoria Supportati

```python
class MemoryType(Enum):
    PREFERENCE = "preference"   # "Preferisco spiegazioni brevi"
    FACT = "fact"               # "Il Quick Kaizen si usa per miglioramenti rapidi"
    CORRECTION = "correction"   # "Non è FIFO ma LIFO per i rifiuti"
    PROCEDURE = "procedure"     # "Per la NC usa sempre il modulo MR-08"
    CONTEXT = "context"         # Contesto conversazione
```

### Bayesian Feedback Boost

Ogni memoria ha un `boost_factor` che varia tra 0.8 e 1.2 basato sui feedback:

```
Memoria: "Preferisco Quick Kaizen"
         │
         ├─ 👍 Positivo → boost += 0.05 (max 1.2)
         │
         └─ 👎 Negativo → boost -= 0.05 (min 0.8)

Score finale = base_confidence × boost_factor
```

### Namespace Memorie

Ogni utente ha il proprio namespace per le memorie:
- **Personali**: `user_{id}` - visibili solo all'utente
- **Globali**: `global` - visibili a tutti (solo Admin può scrivere)

---

## 🔐 Sistema di Autenticazione

### Ruoli e Permessi

**Permessi di LETTURA:**

| Cosa può leggere | `user` | `engineer` | `admin` |
|------------------|--------|------------|---------|
| Memorie globali | ✅ | ✅ | ✅ |
| Proprie memorie | ✅ | ✅ | ✅ |
| Memorie altri utenti | ❌ | ✅ | ✅ |

**Permessi di SCRITTURA:**

| Cosa può scrivere | `user` | `engineer` | `admin` |
|-------------------|--------|------------|---------|
| Proprie memorie | ✅ | ✅ | ✅ |
| Memorie globali | ❌ | ❌ | ✅ |
| Gestire utenti | ❌ | ❌ | ✅ |

### Gestione Utenti (Admin)

```bash
# Crea nuovo utente
python -c "
from src.auth.store import UserStore, Role
store = UserStore()
store.create_user('mario', 'password123', Role.USER, 'Mario Rossi')
"
```

### Servizi di Sistema

| Servizio | URL | Porta |
|----------|-----|-------|
| **Chainlit UI** | `http://localhost:7866` | 7866 |
| **Admin Panel** | `http://localhost:8501` | 8501 |
| **Qdrant DB** | `http://localhost:6333` | 6333 |
| **Ollama LLM** | `http://localhost:11434` | 11434 |

---

## 🎛️ Admin Panel Streamlit

Il pannello amministrativo è un'interfaccia web separata per la gestione centralizzata del sistema.

### Avvio Admin Panel

```powershell
cd D:\.ISO_OVV\ovv-iso-chat
poetry install --with ui
streamlit run admin_panel.py --server.port 8501
```

**URL:** `http://localhost:8501`

### Funzionalità

| Vista | Descrizione | Admin | Engineer |
|-------|-------------|-------|----------|
| **📊 Dashboard** | KPI cards + grafici statistiche | ✅ Full | ✅ Read-only |
| **📈 Analytics** | Metriche utilizzo, qualità RAG, report | ✅ Full | ✅ Read |
| **🤝 Consenso** | Apprendimento implicito, promozione memorie | ✅ Full | ✅ Read |
| **📋 Proposte** | Gestione proposte pending_global | ✅ Approve/Reject | ⚠️ Solo Reject |
| **📚 Glossario** | CRUD acronimi con paginazione | ✅ CRUD | ✅ Read |
| **🧠 Memorie** | Browser memorie per namespace | ✅ Full + Promote | ✅ Read |
| **👥 Utenti** | Gestione account utenti | ✅ CRUD | ❌ Negato |

### Workflow Approvazione Proposte

1. **Utente** propone memoria con `/propose` nella chat
2. **Proposta** finisce in `pending_global`
3. **Admin/Engineer** vede proposte nel pannello
4. **Admin** può approvare → memoria va in `global` + eventuale aggiunta glossario
5. **Admin/Engineer** può rifiutare → proposta eliminata

### Estrazione Automatica Acronimi

Quando una proposta contiene una definizione di acronimo (es. "WCM = World Class Manufacturing"), il sistema:
1. Rileva il pattern
2. Estrae acronimo e definizione
3. Aggiunge automaticamente al `glossary.json` durante l'approvazione

---

## ⚡ Ottimizzazione VRAM (RTX 3060 6GB)

### Budget VRAM

```
┌─────────────────────────────────────────────────────┐
│                    6144 MB TOTALE                   │
├─────────────────────────────────────────────────────┤
│  BGE-M3 Embedding     │████████████░░░│  ~2200 MB  │
│  Llama 3.1 8B LLM     │███████████████│  ~3500 MB  │
│  Buffer sistema       │██░░░░░░░░░░░░░│   ~400 MB  │
├─────────────────────────────────────────────────────┤
│  TOTALE               │███████████████│  ~6100 MB  │
│  (sotto soglia critica 5500 MB grazie a lazy load) │
└─────────────────────────────────────────────────────┘
```

### Strategie di Ottimizzazione

1. **Lazy Loading**: LLM caricato solo quando serve
2. **CPU Rerankers**: FlashRank e Qwen3 GGUF su CPU (0 VRAM)
3. **FP16 Embeddings**: BGE-M3 in half precision
4. **Batch ridotto**: 16 (fallback 8) per embedding
5. **GPU Layers**: 35 su 40 per LLM (bilancio velocità/VRAM)

---

## 🔧 Configurazione Avanzata

Modifica `config/config.yaml` per personalizzare:

```yaml
# Chunking
ingestion:
  chunking:
    parent_size: 1200    # Aumenta per più contesto
    child_size: 400      # Riduci per più precisione

# Retrieval
retrieval:
  top_k: 20              # Più documenti iniziali
  final_k: 5             # Più documenti in risposta

# LLM
llm:
  generation:
    temperature: 0.3     # 0=deterministico, 1=creativo
    num_gpu_layers: 35   # Riduci se poca VRAM
```

---

## 📊 Metriche di Performance

| Metrica | Valore Target | Note |
|---------|--------------|------|
| Latenza query | < 30s | Prima query più lenta (caricamento modelli) |
| Recall@5 | > 0.85 | 85% documenti rilevanti nei top 5 |
| VRAM max | < 5.5GB | Con margine di sicurezza |
| Throughput | ~2 query/min | Con GPU condivisa |

---

## 📁 Struttura del Progetto

```
ovv-iso-chat/
├── app.py                    # Interfaccia Gradio (legacy)
├── app_chainlit.py           # Interfaccia Chainlit (v3.3)
├── admin_panel.py            # Admin Panel Streamlit (v3.2.2)
├── admin/                    # Modulo Admin Panel
│   ├── __init__.py
│   ├── auth.py               # Autenticazione admin
│   └── views/
│       ├── dashboard.py      # KPI + grafici
│       ├── analytics.py      # Metriche e report (R07-R11)
│       ├── consensus.py      # Consenso multi-utente (R08-R10)
│       ├── proposals.py      # Gestione proposte
│       ├── glossary.py       # CRUD glossario
│       ├── memories.py       # Browser memorie
│       └── users.py          # Gestione utenti
├── config/
│   ├── config.yaml           # Configurazione principale
│   ├── glossary.json         # Acronimi e abbreviazioni
│   ├── users.json            # Database utenti (v3.2)
│   ├── tools_mapping.json    # Mapping tool 93 entries (R15/R16)
│   ├── semantic_metadata.json # 90 MR/TOOLS con metadata semantici (R30)
│   ├── document_metadata.json # Metadati estratti da PDF (R30)
│   ├── ps_mr_context.json    # Contesto MR estratto da PS (R30)
│   └── acronym_proposals.json # Proposte acronimi (R05)
├── .chainlit/
│   └── config.toml           # Configurazione Chainlit
├── src/
│   ├── auth/                 # Autenticazione RBAC (v3.2)
│   │   ├── models.py         # User, Role
│   │   ├── store.py          # UserStore
│   │   └── middleware.py     # Auth callbacks
│   ├── ingestion/
│   │   ├── extractor.py      # Estrazione PDF
│   │   ├── chunker.py        # Chunking gerarchico PS/IL
│   │   ├── synthetic_chunker.py # Chunk sintetici MR/TOOLS (R30)
│   │   ├── enricher.py       # Prepending Context + Semantic (R21, R30)
│   │   ├── indexer.py        # BGE-M3 + Qdrant
│   │   └── glossary_indexer.py # Dual Embedding (R22)
│   ├── integration/
│   │   ├── rag_pipeline.py   # Pipeline RAG completa (R20-R23, R30)
│   │   ├── glossary.py       # Espansione acronimi
│   │   ├── disambiguator.py  # Disambiguazione contestuale (R06)
│   │   ├── hyde.py           # HyDE Generator (R23)
│   │   ├── tool_suggester.py # Suggerimento Tool (R15)
│   │   ├── teach_assistant.py # Assistenza Compilazione (R16)
│   │   └── citation_extractor.py # Estrazione citazioni (R14)
│   ├── agents/
│   │   ├── orchestrator.py   # Orchestrazione pipeline multi-agent
│   │   ├── agent_retriever.py # Retrieval + Intent Detection (R30)
│   │   ├── agent_context.py  # Contesto + MR Injection (R30)
│   │   ├── agent_generator.py # Generazione risposta con moduli
│   │   ├── agent_validator.py # Validazione citazioni (R26)
│   │   ├── mr_injector.py    # Inietta moduli correlati (R30)
│   │   └── state.py          # Stato pipeline condiviso
│   ├── memory/
│   │   ├── store.py          # Storage + Bayesian boost
│   │   ├── updater.py        # Aggiornamento memoria
│   │   └── llm_agent.py      # Agent LLM per estrazione
│   ├── analytics/            # Modulo Analytics (v3.4)
│   │   ├── gap_detector.py   # Segnalazione lacune (R19)
│   │   ├── gap_store.py      # Persistenza segnalazioni
│   │   └── acronym_extractor.py # Estrazione acronimi (R05)
│   ├── learning/             # Modulo Apprendimento (v3.5)
│   │   ├── signals/          # Raccolta segnali impliciti
│   │   ├── analyzers/        # Analisi comportamento
│   │   ├── consensus/        # Voting e promozione
│   │   ├── learners/         # Orchestrazione
│   │   ├── hooks.py          # Integrazione Chainlit
│   │   └── scheduler.py      # Job notturni
│   └── main.py               # CLI principale
├── data/
│   ├── input_docs/           # PDF da indicizzare
│   ├── persist/              # Dati persistenti
│   └── logs/                 # Log applicazione
└── benchmarks/
    └── benchmark_models.py   # Test performance
```

---

## 🔥 Funzionalità Avanzate

### Warmup all'Avvio

All'avvio dell'applicazione, tutti i modelli vengono pre-caricati in memoria:

```
🔥 Warmup modelli in corso...
✅ LLM warmup OK
✅ Embedding model warmup OK
✅ FlashRank warmup OK
✅ Glossary warmup OK
🎉 Warmup completato in 11.5s
```

**Beneficio**: La prima query è veloce (~30s) invece dei 10+ minuti senza warmup.

### Query Reformulation con History

Il sistema capisce il **contesto conversazionale** e riformula le query di follow-up:

| Query Utente | Query Riformulata |
|--------------|-------------------|
| "Cos'è la RI?" | "Cos'è la RI (Richiesta di Investimento)?" |
| "e la RO?" | "Cos'è la RO (Richiesta d'Offerta) e differenze con RI?" |
| "parlamene" | "Parlami di più su: [ultima query]" |
| "quindi la differenza?" | "Qual è la differenza tra RI e RO? Spiega entrambi." |

**Pattern riconosciuti:**
- `parlamene` / `continua` / `dimmi` → espande ultima query
- `e la X?` → confronta con termine precedente
- `quindi la differenza?` → richiede confronto esplicito

---

## 🎯 Funzionalità UI Avanzate (v3.6)

### Disambiguazione Contestuale Acronimi (R06 v2.0)

Quando un acronimo ha **più significati possibili**, il sistema lo disambigua in modo **intelligente e contestuale** usando un sistema a punteggio pesato:

```
Query: "NC durante l'audit qualità"
              │
              ▼
   ┌──────────────────────────────────────────────────────┐
   │  1. CONTEXT ANALYSIS (60%)                           │
   │     Keywords match: "audit", "qualità"               │
   │     → Qualità score: 0.85                            │
   │     → Contabilità score: 0.10                        │
   └──────────────────────────────────────────────────────┘
              │
              ▼
   ┌──────────────────────────────────────────────────────┐
   │  2. USER PREFERENCE (25%)                            │
   │     Preferenza salvata: contabilità                  │
   │     → Qualità score: 0.40                            │
   │     → Contabilità score: 1.00                        │
   └──────────────────────────────────────────────────────┘
              │
              ▼
   ┌──────────────────────────────────────────────────────┐
   │  3. DOMAIN FREQUENCY (15%)                           │
   │     NC nel dominio ISO = qualità 85%                 │
   │     → Qualità score: 0.85                            │
   │     → Contabilità score: 0.15                        │
   └──────────────────────────────────────────────────────┘
              │
              ▼
   ┌──────────────────────────────────────────────────────┐
   │  CALCOLO FINALE                                      │
   │  Qualità:     0.85×60% + 0.40×25% + 0.85×15% = 0.74 │
   │  Contabilità: 0.10×60% + 1.00×25% + 0.15×15% = 0.33 │
   │                                                      │
   │  Gap = 0.41 > 0.35 (CERTAINTY_THRESHOLD)            │
   │  → CERTO! ✅ Risposta automatica                     │
   └──────────────────────────────────────────────────────┘
              │
              ▼
   NC = "Non Conformità" (risolto automaticamente)
```

**Comportamento Intelligente:**

| Scenario | Gap | Comportamento |
|----------|-----|---------------|
| **Contesto chiaro** (audit, qualità) | ≥ 0.35 | NC = "Non Conformità" automatico |
| **Contesto finanziario** (fattura) | ≥ 0.35 | NC = "Nota di Credito" automatico |
| **Contesto ambiguo** ("Mostrami le NC") | < 0.35 | Chiede con suggerimento |

**Se Chiede:**

```
🔤 **NC** può significare:

**1. Non Conformità** 📍 _probabile dal contesto: audit, qualità_
**2. Nota di Credito** ⭐ _tua preferenza abituale_

❓ Quale intendi?
```

**Pesi e Costanti:**
| Parametro | Valore | Descrizione |
|-----------|--------|-------------|
| `WEIGHT_CONTEXT` | 60% | Il contesto della query domina |
| `WEIGHT_PREFERENCE` | 25% | Preferenze utente sono suggerimenti soft |
| `WEIGHT_FREQUENCY` | 15% | Frequenza nel dominio ISO |
| `CERTAINTY_THRESHOLD` | 0.35 | Gap minimo per decisione automatica |

**Override Tracking:**
Se il contesto vince spesso sulla preferenza utente, il sistema riduce gradualmente il peso della preferenza per quell'acronimo (evita di chiedere sempre la stessa cosa).

**Acronimi Ambigui Configurati:**

| Acronimo | Significato 1 | Significato 2 | Significato 3 |
|----------|---------------|---------------|---------------|
| **NC** | Non Conformità | Nota di Credito | - |
| **AC** | Azione Correttiva | Aria Condizionata | - |
| **PM** | Professional Maintenance | Project Manager | Preventive Maintenance |
| **QC** | Quality Control | Quick Change | - |
| **CDL** | Centro Di Lavoro | Ciclo Di Lavoro | - |

### Fonti Intelligenti (R14)

Le risposte mostrano **solo le fonti effettivamente citate** nella risposta:

```
📚 **Fonti citate:**
- PS-06_01 (92%) ← Click per preview
- IL-06_02 (87%)

⚠️ Attenzione: MR-06_03 citato ma non trovato nei documenti
```

**Funzionalità:**
- Estrazione citazioni dal testo LLM con regex
- Filtraggio: solo documenti citati (non tutti i 5 recuperati)
- Preview cliccabile nel sidebar Chainlit
- Rilevamento "citazioni fantasma" (doc citati ma non esistenti)

### Correlazioni Strumenti Automatiche (R30)

Quando parli di un argomento che richiede l'uso di **moduli o strumenti**, il sistema li cita automaticamente nella risposta:

```
User: "Come compilo un Major Kaizen?"

🤖 Il modulo MR-10_01 (Major Kaizen) è destinato ai progetti di 
miglioramento MAJOR con impatto significativo e team dedicato.

Per compilarlo correttamente, si devono seguire i campi relativi 
allo scopo e all'utilizzo del progetto.

📌 **Da utilizzare insieme a:**
- 5 Perché → per trovare root cause
- 4M Ishikawa → per analisi causa
- 5W1H → per raccogliere dati iniziali
- QM Matrix → per correlare difetti/cause
- Poka Yoke → per soluzioni anti-errore

📚 Fonti: MR-10_01_Major Kaizen, PS-10_01_Miglioramento
```

**Come funziona:**
1. **Intent Detection**: Query analizzata per intent (kaizen, infortunio, near miss...)
2. **MR Injection**: Moduli correlati iniettati nel contesto dal `MRInjector`
3. **Semantic Chunks**: I chunk sintetici contengono le correlazioni già formattate
4. **LLM cita**: L'LLM include naturalmente le correlazioni nella risposta

**Vantaggi:**
- L'utente scopre strumenti che non conosceva
- Non deve cercare manualmente le correlazioni tra procedure
- Ogni modulo "spiega" con cosa va usato

### Suggerimento Tool Pratici (R15)

Dopo una risposta su problemi operativi, il sistema suggerisce **tool pratici**:

```
📚 Fonti citate: PS-08_08 (89%)
---
🛠️ **Tool consigliati per questo problema:**

📌 **Cartellino Anomalia** (MR-07_05)
   Registrazione anomalie/difetti

📌 **5W1H** (TOOLS-10_01)
   Analisi strutturata del problema

[📝 Come compilo Cartellino Anomalia?] [📝 Come compilo 5W1H?]
```

**Funzionalità:**
- Intent detection: distingue query azionabili da informative
- Mapping JSON: **93 tool** con keywords/concepts (v3.9)
- Fallback semantico con embedding similarity
- Bottoni cliccabili che eseguono `/teach`

### Assistenza Compilazione Tool (R16)

Il comando `/teach` è ora **interattivo**:

```
/teach FMEA
```

```
📝 **Come compilare FMEA** (MR-08_07)

[spiegazione dettagliata...]

🔍 **Hai bisogno di aiuto su un campo specifico?**

[📋 Mostra tutti i campi] [⚠️ Errori comuni] [📄 Esempio compilato]
```

**Domande follow-up:**
```
User: "Non capisco il campo Severity"

📋 **Campo: Severity (S)**

Gravità dell'effetto su scala 1-10

💡 **Suggerimenti:**
10=pericolo senza preavviso, 9=pericolo con preavviso, 1=nessun effetto
```

**Funzionalità:**
- Contesto sessione: mantiene doc_id per 10 minuti
- Field detection: rileva domande su campi specifici
- **93 tool mappati** con campi e descrizioni (v3.9)
- Feedback tracker per Admin (`/teach_stats`)

### Segnalazione Lacune Intelligente (R19)

Quando il sistema non trova informazioni, propone di segnalare:

```
[Risposta RAG incerta...]

---
📍 **Possibile lacuna rilevata**

Non ho trovato una definizione chiara per **WCM**.

Ho trovato il termine in questi documenti ma senza definizione:
- `PS-06_01`
- `IL-07_02`

❓ **Vuoi segnalare questa lacuna all'Admin?**

[✅ Sì, segnala] [❌ No, non serve]
```

**Segnali analizzati (5):**
1. Nessun documento recuperato
2. Score retrieval basso (<0.4)
3. LLM esprime incertezza (14 pattern)
4. Termine non nel glossario
5. Termine citato ma non definito

**Admin:** `/gaps` mostra statistiche e segnalazioni pending.

### Estrazione Automatica Acronimi (R05)

Il sistema estrae **automaticamente** definizioni di acronimi dai documenti:

**Pattern riconosciuti (5):**
```
1. WCM (World Class Manufacturing)     → parentesi dopo
2. (World Class Manufacturing) WCM     → parentesi prima
3. WCM significa World Class...        → connettivo italiano
4. WCM = World Class Manufacturing     → uguale/due punti
5. WCM, ovvero World Class...          → connettivo italiano
```

**Workflow Admin:**
```
/acronyms                  → Lista proposte pending
/acronyms approve WCM      → Approva → aggiunge al glossario
/acronyms reject XYZ motivo → Rifiuta con motivo
/acronyms stats            → Statistiche estrazione
```

**Validazione:**
- Confidence score 0-1 (soglia 0.6)
- Match iniziali (WCM = World Class Manufacturing ✓)
- Blacklist ~50 termini comuni (IL, PS, ISO...)
- Skip se già nel glossario

### Apprendimento Implicito + Consenso Multi-Utente (R08-R10)

Il sistema **impara automaticamente** dalle tue interazioni senza richiedere feedback esplicito:

```
┌─────────────────────────────────────────────────────────────┐
│                 SEGNALI IMPLICITI TRACCIATI                 │
├─────────────────────────────────────────────────────────────┤
│  📋 Click su fonte citata     → Documento utile             │
│  📝 Copia testo risposta      → Contenuto rilevante         │
│  ⏱️  Tempo lettura (dwell)     → Risposta interessante       │
│  📜 Scroll completo           → Contenuto approfondito      │
│  🔄 Riformulazione query      → Risposta non soddisfacente  │
│  ➡️  Follow-up                 → Vuole approfondire          │
│  ✅ /teach completato         → Contenuto confermato        │
└─────────────────────────────────────────────────────────────┘
```

**Pattern Comportamentali Rilevati:**

| Pattern | Cosa rileva | Azione automatica |
|---------|-------------|-------------------|
| **Preferenza formato** | Dwell time + scroll depth | "Preferisce risposte brevi/dettagliate" |
| **Interesse topic** | Documenti cliccati spesso | "Interessato a [topic]" |
| **Livello expertise** | Termini tecnici in query | "Utente esperto/base" |
| **Frustrazione** | Re-ask + quick dismiss | Alert per Admin |

**Consenso Multi-Utente:**

Quando più utenti confermano la stessa informazione, questa viene promossa automaticamente:

```
Utente 1: /teach "WCM = World Class Manufacturing"
Utente 2: copia "WCM significa World Class"
Utente 3: click su fonte che definisce WCM
                    │
                    ▼
         ┌─────────────────────┐
         │  CONSENSO RAGGIUNTO │
         │  3 utenti, score 0.8│
         └─────────────────────┘
                    │
                    ▼
         Promozione automatica a
         memoria GLOBALE (o pending)
```

**Soglie consenso:**
- Minimo **3 utenti** diversi
- Score consenso **≥ 0.7**
- Similarità contenuto **≥ 75%**

**Admin Panel - Tab Consenso (🤝):**

| Sottotab | Funzionalità |
|----------|--------------|
| **Dashboard** | Metriche segnali, candidati pronti, ratio positivi |
| **Candidati** | Lista con pulsanti Approva/Rifiuta per ogni candidato |
| **Promozioni** | Storico memorie promosse con stats |
| **Segnali** | Monitoraggio per tipo (click, copy, dwell, ecc.) |
| **Config** | Soglie, feature toggles, run manuale analisi |

**Job Notturni Automatici:**

| Ora | Job | Descrizione |
|-----|-----|-------------|
| 03:00 | Nightly Analysis | Analisi comportamento utenti |
| 04:00 | Consensus Check | Promozione memorie con consenso |
| 05:00 | Signal Cleanup | Pulizia dati vecchi (30gg retention) |

### Cronologia Conversazioni (R28)

Il sistema **logga automaticamente** tutte le conversazioni per analisi e miglioramento:

```
┌─────────────────────────────────────────────────────────────┐
│                    CONVERSATION LOGGER                      │
├─────────────────────────────────────────────────────────────┤
│  📁 Sessione (per utente)                                   │
│  ├── user_id, role, started_at, ended_at                   │
│  ├── total_interactions, feedback_counts                   │
│  └── interactions[]                                         │
│      └── 💬 Interazione (ogni Q&A)                         │
│          ├── query_original/reformulated/expanded          │
│          ├── response_text (risposta LLM completa)         │
│          ├── sources_cited, sources_missing                │
│          ├── latency_total_ms                              │
│          ├── feedback (positive/negative)                  │
│          ├── tools_suggested                               │
│          └── gap_detected/reported                         │
└─────────────────────────────────────────────────────────────┘
```

**Dati registrati per ogni interazione:**

| Campo | Descrizione |
|-------|-------------|
| `query_original` | Domanda esatta dell'utente |
| `query_reformulated` | Query dopo reformulation con history |
| `query_expanded` | Query dopo espansione acronimi |
| `response_text` | Risposta LLM completa |
| `sources_cited` | doc_id effettivamente citati |
| `sources_missing` | Citazioni fantasma (allucinazioni) |
| `latency_total_ms` | Tempo totale risposta |
| `feedback` | positive/negative (se dato) |
| `gap_detected` | Se rilevata lacuna (R19) |
| `tools_suggested` | Tool consigliati (R15) |

**Comando `/history`:**

```
/history         → Ultime 10 sessioni tue
/history 20      → Ultime 20 sessioni
/history today   → Solo oggi
/history all     → Tutti gli utenti (Admin)
```

**Admin Panel - Tab "💬 Conversazioni":**

| Funzionalità | Descrizione |
|--------------|-------------|
| **📊 KPI Cards** | Sessioni, messaggi, utenti unici, feedback ratio |
| **📋 Lista Sessioni** | Espandibili con dettaglio ogni Q&A |
| **📤 Export CSV** | Download cronologia filtrata |
| **👥 Stats per Utente** | Tabella top utenti con metriche |
| **🗑️ Cleanup** | Rimuovi sessioni vecchie (Admin) |

**Persistenza:**
- Path: `data/persist/conversations/sess_*.json`
- Retention: 90 giorni (configurabile)
- Indice giornaliero per query rapide

---

# 🚀 Progetti Futuri

> Funzionalità pianificate per le prossime versioni

| ID | Progetto | Descrizione | Priorità |
|----|----------|-------------|----------|
| F04 | ImplicitLearner Integration | Integrare segnali impliciti (copy, click, dwell) nell'UI | Alta |
| F05 | GraphRAG Integration | Knowledge Graph per retrieval basato su relazioni tra entità | Media |
| F06 | UnifiedChunker | Chunker unificato PS/IL + MR/TOOLS per ingestion robusta | Alta ✅ |
| F07 | Mesop UI Alternative | Valutare migrazione a Google Mesop per eventi avanzati | Media |
| F08 | Valutazione Qwen3 8B | Benchmark Qwen3 vs Llama 3.1 per migliore supporto italiano | Bassa |
| F09 | Selettore Modello LLM | Scegliere Llama/Qwen dalla UI durante la conversazione | Alta |

### 🎯 F09: Selettore Modello LLM Dinamico

Permettere all'utente di scegliere il modello LLM direttamente dalla UI:

```
⚙️ IMPOSTAZIONI CHAT
├── 🤖 Modello LLM
│   ├── 🦙 Llama 3.1 8B (Predefinito)
│   └── 🐉 Qwen3 8B (Migliore italiano)
```

**Funzionalità:**
- Pannello Settings con dropdown modello
- Comando `/model llama` o `/model qwen`
- Cambio modello in tempo reale durante la conversazione
- Indicatore modello attivo nella risposta

**Vantaggi:**
- Qwen3: Migliore supporto italiano (119 lingue), architettura MoE più efficiente
- Llama 3.1: Modello stabile e bilanciato, ottimo per uso generale

---

# 📜 Appendici

## 📜 Storico Versioni

### v3.9.1 (Dicembre 2025) - "PDF Consultabili & Citazioni Leggibili"
- 📖 **PDF Consultabili in Sidebar** - I PDF si aprono direttamente nella sidebar (non download)
  - Usa `cl.Pdf(display="side")` per consultazione inline
  - Apertura automatica alla pagina 1
  - Nome completo file con revisione (es. `PS-06_01_Rev.04_Gestione della sicurezza.pdf`)
- 📝 **Citazioni con Titoli Italiani** - Nel testo i doc_id vengono sostituiti con titoli leggibili
  - `PS-06_01` → `"Gestione della sicurezza negli ambienti di lavoro"`
  - Virgolette italiane per citazioni nel testo
  - Post-processing automatico su ogni risposta
- 📚 **Footer Fonti Migliorato**:
  - Nome COMPLETO: `doc_id_Rev.XX_Titolo italiano`
  - **Separazione PDF/Glossario**: prima documenti (📄), poi termini glossario (📝)
  - Icone differenziate per tipo fonte
- 🔍 **Retrieval per Query Definitorie** - Anche le domande sul glossario recuperano PDF correlati
  - Query "cosa significa EWO" ora mostra anche documenti correlati negli allegati
  - Top-5 documenti correlati aggiunti automaticamente
- 🛡️ **Post-Processing Anti-Allucinazioni**:
  - `sanitize_invalid_citations()` - Rimuove citazioni non presenti nel contesto
  - `remove_llm_references_section()` - Rimuove sezioni "Riferimenti:" ridondanti
  - `replace_doc_ids_with_titles()` - Sostituisce codici con titoli leggibili
  - Grounding check attivo con threshold 0.6
- 📁 **File modificati**:
  - `app_chainlit.py` - Post-processing, `cl.Pdf`, separazione fonti
  - `src/agents/orchestrator.py` - Retrieval in `direct_glossary_answer()`
  - `templates/chat.html` - Separazione fonti PDF/Glossario
  - `test_ui.py` - Stessa logica per UI test
  - `config/config.yaml` - `grounding_check.enabled: true`

### v3.9.0 (Dicembre 2025) - "Semantic Chunking & Tool Correlations"
- 🧩 **Synthetic Chunking per MR/TOOLS (R30)** - Chunk generati da metadata invece che da PDF vuoti
  - **SyntheticChunker**: Genera chunk semantici per 68 MR + 22 TOOLS
  - Chunk ricchi: titolo, scopo, `applies_when`, `not_for`, correlazioni
  - Es: "📄 MR-10_01 - Major Kaizen | USA QUANDO: progetto miglioramento | DA USARE CON: 4M Ishikawa, 5 Perché..."
- 📊 **Semantic Metadata System** - 90 documenti analizzati manualmente
  - `semantic_metadata.json`: 90 voci con `incident_category`, `applies_when`, `not_for`
  - `document_metadata.json`: Metadati estratti da PDF (titolo, scopo, correlazioni)
  - `ps_mr_context.json`: Contesto MR estratto dai documenti PS correlati
- 🎯 **Intent Detection migliorato** - Rileva automaticamente:
  - `real_injury` → MR-06_01 (Safety EWO)
  - `near_miss` → MR-06_02 (Near Miss Report)
  - `kaizen` → MR-10_01, MR-10_02, TOOLS correlati
- 🔗 **Correlazioni Strumenti Automatiche** - La risposta include:
  > "...deve essere utilizzato insieme ad altri strumenti come il **5 Perché, Kaizen, Poka Yoke e OPL**"
- 💉 **MR Injector** - Inietta moduli correlati direttamente nel contesto LLM
  - Basato su `ps_mr_context.json` per correlazioni PS→MR
  - Attivato automaticamente quando PS recuperati
- 📈 **Priorità MR/TOOLS aumentata** - Da 0.5/0.8 a 0.85 (contenuto ora ricco)
- 🔄 **Re-ingestion completa** - 2811 chunks (2713 PS/IL + 98 sintetici MR/TOOLS)
- 📁 **File creati/modificati**:
  - `src/ingestion/synthetic_chunker.py` (NUOVO - ~250 righe)
  - `src/agents/mr_injector.py` (NUOVO)
  - `src/agents/agent_retriever.py` (Intent detection)
  - `src/ingestion/enricher.py` (Semantic context)
  - `scripts/reindex_with_enrichment.py` (Synthetic integration)
  - `config/semantic_metadata.json` (NUOVO - 90 entries)
  - `config/document_metadata.json` (NUOVO)
  - `config/ps_mr_context.json` (NUOVO)
  - `config/tools_mapping.json` (esteso a 93 entries)
  - `tests/test_synthetic_chunker.py` (NUOVO)
  - `tests/test_semantic_retrieval.py` (NUOVO)

### v3.8.0 (Dicembre 2025) - "General Query Expansion + Conversation Logger"
- 🧠 **LLM Query Expansion Generale** - L'LLM genera automaticamente sub-query per QUALSIASI domanda complessa
  - Nessuna regola hardcoded - soluzione completamente generale
  - Chiamata diretta Ollama con timeout 30s e fallback automatico
  - Attivato per query con termini generici (gestire, procedure, normativa)
  - Migliora completezza risposte su argomenti multi-aspetto
- 📄 **Citazioni con Titolo Descrittivo (F01)** - Le fonti mostrano il titolo completo del documento
  - Es: "IL-06_01 - Gestione dei rifiuti" invece di solo "IL-06_01"
  - Titolo estratto dai metadati PDF durante l'ingestion
  - Miglior leggibilità e comprensione per l'utente
- 📜 **Conversation Logger (R28)** - Cronologia completa di tutte le chat
  - **Session tracking**: Ogni sessione utente con metadata (inizio, fine, durata)
  - **Interaction logging**: Query completa, risposta LLM, fonti, latenza, feedback
  - **Comando `/history`**: Visualizza le tue sessioni passate
  - **Admin Panel Tab "💬 Conversazioni"**: Vista con filtri, KPI, export CSV
  - **Persistenza JSON**: Un file per sessione in `data/persist/conversations/`
  - **Retention**: 90 giorni configurabile
  - **19 test unitari** per validazione
- 🗄️ **Re-importazione Completa** - 150 documenti, 2787 chunks arricchiti
  - 1752 acronimi risolti automaticamente (R21)
  - Media +140 caratteri di contesto per chunk
  - Collection Qdrant pulita senza duplicati
- 📁 **File creati/modificati**:
  - `src/analytics/collectors/conversation_logger.py` (NUOVO - ~600 righe)
  - `admin/views/conversations.py` (NUOVO - ~300 righe)
  - `app_chainlit.py` (integrazione logging sessioni)
  - `admin_panel.py` (nuova tab Conversazioni)
  - `config/config.yaml` (sezione conversation_logging)
  - `tests/test_conversation_logger.py` (NUOVO - 19 test)
  - `src/agents/agent_analyzer.py` - `_llm_expand_query()` generale
  - `src/integration/rag_pipeline.py` - `RetrievedDoc.title`
  - `src/agents/orchestrator.py` - `_SourceWrapper` con titolo
  - `test_ui.py` e `templates/chat.html` - Display titolo fonti

### v3.7.0 (Dicembre 2025) - "Anti-Hallucination"
- 🛡️ **ValidatorAgent (R26)** - Citazioni verificate automaticamente
  - **Citation Check**: Verifica che documenti citati siano nel contesto
  - **Self-Refine Loop**: Rigenera risposta con feedback se invalida (max 2 retry)
  - **Context Injection**: Header esplicito con doc_id disponibili nel prompt
  - **Zero VRAM overhead**: Validazione regex-based CPU-only
- 🔄 **Flow Pipeline Aggiornato**:
  ```
  generator → validator → [VALID? END : generator(retry)]
  ```
- 📁 **File modificati/creati**:
  - `src/agents/agent_validator.py` (NUOVO)
  - `src/agents/state.py` (campi validazione)
  - `src/agents/agent_context.py` (doc_id header injection)
  - `src/agents/agent_generator.py` (retry prompt template)
  - `src/agents/orchestrator.py` (validation loop)
  - `config/config.yaml` (sezione validator)
  - `tests/test_validator_agent.py` (NUOVO)

### v3.6.1 (Dicembre 2025) - "Conversational Assistant"
- 🗣️ **System Prompt Discorsivo** - Risposte più complete e proattive
  - Prompt ottimizzato per modelli 8B (conciso ma incisivo)
  - Istruzioni POSITIVE (cosa fare) vs restrizioni (cosa non fare)
  - 4 comportamenti chiave: contestualizza, dettaglia, suggerisci, interagisci
- 📁 **File modificati**: `config/config.yaml`, `src/memory/llm_agent.py`

### v3.6.0 (Dicembre 2025) - "Smart Disambiguation"
- 🎯 **Disambiguazione Contestuale (R06 v2.0)** - Acronimi ambigui risolti intelligentemente
  - Contesto query domina (60%), preferenze utente soft (25%), frequenza dominio (15%)
  - `CERTAINTY_THRESHOLD = 0.35` per decisione automatica
  - Chiede solo quando gap tra top 2 significati < soglia
  - Keywords contestuali per ogni significato (audit → qualità, fattura → contabilità)
  - Acronimi: NC, AC, PM, QC, CDL con significati multipli
  - Preferenze utente per file separato per utente
  - Override tracking: traccia quando il contesto batte la preferenza
- 📁 **File**: `src/integration/disambiguator.py` (v2.0 fuso)
- ✅ **Test**: 39 test per disambiguazione contestuale

### v3.5.0 (Dicembre 2025) - "Learning & Consensus Complete"
- 🧠 **Apprendimento Implicito (R08)** - Sistema impara dalle interazioni senza feedback esplicito
- 🤝 **Consenso Multi-Utente (R10)** - Promozione automatica memorie quando 3+ utenti confermano
- 📊 **Behavior Analyzer** - Rileva preferenze, interessi, expertise, frustrazioni
- 🗳️ **Voting Tracker** - Traccia voti impliciti per consenso
- 🚀 **Global Promoter** - Promuove memorie user→global con validazione
- 🎛️ **Admin Panel: Tab Consenso** - Dashboard, candidati, promozioni, segnali, config
- ⏰ **Job Notturni** - Analisi@03:00, Consenso@04:00, Cleanup@05:00

### v3.4.0 (Dicembre 2025) - "UI Chat Stream Complete"
- 🔍 **Fonti Intelligenti (R14)** - Mostra solo fonti citate + preview cliccabile
- 🛠️ **Suggerimento Tool Pratici (R15)** - Bottoni per tool consigliati
- 📝 **Assistenza Compilazione (R16)** - `/teach` interattivo con field detection
- 📍 **Segnalazione Lacune (R19)** - Rileva e segnala gap nella knowledge base
- 🔤 **Estrazione Acronimi (R05)** - Estrae automaticamente definizioni dai documenti

### v3.3.0 (Dicembre 2025) - "Glossary Stream Complete"
- 🔮 **HyDE (R23)** - Genera documento ipotetico per migliorare retrieval
- 📚 **Dual Embedding (R22)** - Glossario come collezione Qdrant separata
- 📝 **Prepending Context (R21)** - Chunks arricchiti con metadata e glossario
- 💉 **Glossary Context Injection (R20)** - Definizioni iniettate nel prompt LLM

### v3.2.2 (Dicembre 2025)
- 🎛️ **Admin Panel Streamlit** - Pannello visuale su porta 8501
- 🔍 **Fonti Intelligenti** - Mostra solo fonti effettivamente citate
- 🧹 **Deduplicazione Chunks** - Rimozione duplicati in ingestion
- ✏️ **Fix Citazioni Fantasma** - LLM non inventa più documenti

### v3.2.1 (Dicembre 2025)
- 📖 **Glossario Acronimi Ambigui** - Supporto significati multipli (es. CDL)
- 🤖 **Apprendimento Semi-Automatico** - Sistema rileva quando insegni qualcosa
- ✅ **Sistema Approvazione** - Comandi `/pending`, `/approve`, `/reject`
- 📋 **Namespace pending_global** - Proposte in coda per Admin

### v3.2.0 (Dicembre 2025)
- 🔐 **Autenticazione RBAC** - Ruoli Admin/Engineer/User
- 👍 **Feedback Bayesian** - Sistema impara dai tuoi feedback
- 📄 **Preview Documenti** - Anteprima cliccabile delle fonti
- 🧠 **Namespace Multi-utente** - Memorie personali + globali
- 💬 **Interfaccia Chainlit** - UI moderna

---

## 🤝 Contribuire

1. Fork del repository
2. Crea branch feature (`git checkout -b feature/nuova-funzione`)
3. Commit (`git commit -m 'Aggiunge nuova funzione'`)
4. Push (`git push origin feature/nuova-funzione`)
5. Apri Pull Request

---

## 📝 Licenza

MIT License - vedi [LICENSE](LICENSE) per dettagli.

---

## 🙏 Ringraziamenti

- [BAAI](https://huggingface.co/BAAI) per BGE-M3
- [Meta AI](https://huggingface.co/meta-llama) per Llama 3.1
- [Qwen](https://huggingface.co/Qwen) per il reranker
- [Qdrant](https://qdrant.tech/) per il vector database
- [Chainlit](https://chainlit.io/) per l'interfaccia chat

---

*Sviluppato con ❤️ per semplificare la gestione documentale ISO*
