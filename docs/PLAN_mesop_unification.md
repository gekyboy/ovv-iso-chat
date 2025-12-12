# 🎯 Piano Unificazione Mesop - OVV ISO Chat v3.1

**Data**: 12 dicembre 2025
**Branch**: main (merged)
**Stato**: ✅ COMPLETATO 100%
**Obiettivo**: Unificare Chainlit + Streamlit in singola app Mesop

## 📋 Checklist Operativa F07 → Migrazione completa Mesop

### 0) Preparazione (anti-duplicati + governance)
- [x] Branch creato: feat/mesop-unification
- [x] File di coordinamento creati:
  - [x] `docs/PLAN_mesop_unification.md` (questo file)
  - [x] `docs/PARITY_matrix.md` (tabella: Feature → Chainlit/Streamlit → Mesop → test)
  - [x] `docs/LEDGER_changes.md` (registro: "nuovi moduli", "funzioni estratte", "refactor fatti")
- [x] Rule of engagement: prima di creare codice nuovo, cercare se esiste già

### 1) POC Mesop (deve funzionare end-to-end)
- [x] Dipendenza Mesop aggiunta in requirements.txt
- [x] `app_mesop.py` (entrypoint) creato
- [x] `src/ui/mesop_handlers.py` (event handlers) creato
- [x] Single call alla pipeline attuale implementato
- [x] Test POC:
  - [x] Domanda semplice glossario (direct route)
  - [x] Domanda procedurale con retrieval

### 2) Estrarre "logica UI-agnostica" da app_chainlit.py
- [x] `src/ui/shared/sources.py` (cited_sources, previews, pdf_links, titles)
- [x] `src/ui/shared/commands.py` (parse/dispatch comandi)
- [x] `src/ui/shared/documents.py` (path manager, indicizzazione pdf)
- [x] `src/ui/shared/postprocess.py` (cleanup answer)

### 3) Feature Parity Chat: port totale da Chainlit → Mesop
- [x] 3.1 Auth + sessione RBAC usando UserStore
- [x] 3.2 Chat loop + status live multi-agent con progress UI
- [x] 3.3 Fonti con preview + PDF viewer integrato
- [x] 3.4 /documenti UI completa con path manager
- [x] 3.5 Feedback 👍👎 + persistence

### 4) Unificazione Admin: Streamlit → Mesop
- [x] 4.1 Estrarre service layer: `admin/services/` creato con tutti i servizi
- [x] 4.2 Mesop Admin UI: route /admin con menu laterale e RBAC

### 5) Eventi impliciti (motivazione principale di Mesop)
- [x] Tracking eventi: click fonte, copy testo, scroll, dwell time
- [x] Salvataggio su storage per consensus learning

### 6) Test finale e cleanup
- [x] Integrazione completa testata (pipeline RAG funzionante)
- [x] Documentazione aggiornata (PARITY_matrix.md, LEDGER_changes.md)
- [x] Cleanup codice duplicato (logica estratta in shared modules)

## 🎯 Motivazione Mesop
- **Eventi DOM nativi**: copy/scroll/dwell che Chainlit non può fare bene
- **Unificazione**: singola app invece di due processi separati
- **Manutenibilità**: meno duplicazione codice UI

## 🔧 Architettura Finale
```
app_mesop.py (entrypoint)
├── Chat Area (ex Chainlit)
│   ├── Auth RBAC (stesso di Chainlit)
│   ├── Chat loop con MultiAgent pipeline
│   ├── Fonti + PDF viewer
│   ├── Comandi (/teach, /memoria, etc.)
│   └── Feedback system
├── Admin Area (ex Streamlit)
│   ├── Dashboard
│   ├── Proposals (global memory approval)
│   ├── Glossary CRUD
│   ├── Memories browser
│   ├── Users management (admin-only)
│   ├── Analytics
│   ├── Consensus signals
│   └── Conversations history
└── Shared Backend (riuso massimo)
    ├── Pipeline RAG/Multi-agent
    ├── RBAC (bcrypt + JWT)
    └── Data stores (Qdrant, SQLite, etc.)
```

## 📊 Stato Corrente
- **Iniziato**: 12 dicembre 2025
- **Completato**: 12 dicembre 2025 ✅
- **Stato**: 100% Feature Parity Raggiunta
- **Prossimo step**: Deploy e ottimizzazioni produzione

## ⚠️ Vincoli
- **VRAM**: RTX 3060 6GB (max 5.5GB)
- **Sessioni**: Max 45 minuti di lavoro continuo
- **Test**: Dopo ogni modifica significativa
- **Documentazione**: Ogni decisione → FUSION_LOG.md
