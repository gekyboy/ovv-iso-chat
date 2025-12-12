# 🎯 Piano Unificazione Mesop - OVV ISO Chat v3.1

**Data**: 12 dicembre 2025
**Branch**: feat/mesop-unification
**Obiettivo**: Unificare Chainlit + Streamlit in singola app Mesop

## 📋 Checklist Operativa F07 → Migrazione completa Mesop

### 0) Preparazione (anti-duplicati + governance)
- [x] Branch creato: feat/mesop-unification
- [x] File di coordinamento creati:
  - [x] `docs/PLAN_mesop_unification.md` (questo file)
  - [ ] `docs/PARITY_matrix.md` (tabella: Feature → Chainlit/Streamlit → Mesop → test)
  - [ ] `docs/LEDGER_changes.md` (registro: "nuovi moduli", "funzioni estratte", "refactor fatti")
- [x] Rule of engagement: prima di creare codice nuovo, cercare se esiste già

### 1) POC Mesop (deve funzionare end-to-end)
- [ ] Dipendenza Mesop aggiunta in requirements.txt
- [ ] `app_mesop.py` (entrypoint) creato
- [ ] `src/ui/mesop_handlers.py` (event handlers) creato
- [ ] Single call alla pipeline attuale implementato
- [ ] Test POC:
  - [ ] Domanda semplice glossario (direct route)
  - [ ] Domanda procedurale con retrieval

### 2) Estrarre "logica UI-agnostica" da app_chainlit.py
- [ ] `src/ui/shared/sources.py` (cited_sources, previews, pdf_links, titles)
- [ ] `src/ui/shared/commands.py` (parse/dispatch comandi)
- [ ] `src/ui/shared/documents.py` (path manager, indicizzazione pdf)
- [ ] `src/ui/shared/postprocess.py` (cleanup answer)

### 3) Feature Parity Chat: port totale da Chainlit → Mesop
- [ ] 3.1 Auth + sessione RBAC usando UserStore
- [ ] 3.2 Chat loop + status live multi-agent con progress UI
- [ ] 3.3 Fonti con preview + PDF viewer integrato
- [ ] 3.4 /documenti UI completa con path manager
- [ ] 3.5 Feedback 👍👎 + persistence

### 4) Unificazione Admin: Streamlit → Mesop
- [ ] 4.1 Estrarre service layer: `admin/services/` creato con tutti i servizi
- [ ] 4.2 Mesop Admin UI: route /admin con menu laterale e RBAC

### 5) Eventi impliciti (motivazione principale di Mesop)
- [ ] Tracking eventi: click fonte, copy testo, scroll, dwell time
- [ ] Salvataggio su storage per consensus learning

### 6) Test finale e cleanup
- [ ] Integrazione completa testata
- [ ] Documentazione aggiornata
- [ ] Cleanup codice duplicato

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
- **Prossimo step**: Aggiungere dipendenza Mesop e creare POC

## ⚠️ Vincoli
- **VRAM**: RTX 3060 6GB (max 5.5GB)
- **Sessioni**: Max 45 minuti di lavoro continuo
- **Test**: Dopo ogni modifica significativa
- **Documentazione**: Ogni decisione → FUSION_LOG.md
