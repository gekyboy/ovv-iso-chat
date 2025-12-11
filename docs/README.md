# OVV ISO Chat v3.1

> Sistema RAG locale per documenti ISO-SGI con memoria persistente.

## 🚀 Quick Start

```powershell
# 1. Setup ambiente
.\scripts\setup.ps1

# 2. Attiva venv
.\venv\Scripts\Activate.ps1

# 3. Verifica installazione
pytest tests/ -v

# 4. Avvia chat (dopo ingestion)
python -m src.main
```

## 📋 Requisiti

- **Python**: 3.12+
- **GPU**: NVIDIA RTX 3060 6GB (o superiore)
- **Docker**: Per Qdrant
- **Ollama**: Per LLM locale

## 🏗️ Struttura

```
ovv-iso-chat/
├── src/
│   ├── ingestion/     # Estrazione e chunking PDF
│   ├── memory/        # Memoria LangGraph
│   └── integration/   # Pipeline RAG
├── config/
│   └── config.yaml    # Configurazione v3.1
├── data/
│   ├── input_docs/    # PDF sorgente
│   ├── persist/       # Memoria persistente
│   └── logs/          # Log applicazione
├── scripts/
│   └── setup.ps1      # Setup automatico
├── tests/             # Test suite
└── benchmarks/        # Benchmark performance
```

## 🔧 Stack Tecnologico

| Componente | Modello | Device |
|------------|---------|--------|
| Embedding | BAAI/bge-m3 | CUDA |
| Reranker L1 | FlashRank | CPU |
| Reranker L2 | Qwen3 GGUF | CPU |
| LLM | qwen3:8b-q4 | CUDA |
| Vector DB | Qdrant | Docker |

## 📖 Documentazione

- `SESSION_CONTEXT.md` - Stato corrente del progetto
- `FUSION_LOG.md` - Log decisioni e merge

## 🧪 Test

```powershell
# Test completi
pytest tests/ -v

# Test specifico
pytest tests/test_ingestion.py -v

# Con coverage
pytest tests/ --cov=src
```

## 📊 Vincoli VRAM

- **Warning**: 5000 MB
- **Critical**: 5500 MB
- **Strategia**: Lazy load LLM, reranker CPU, batch ridotti

---

*v3.1.0 - Setup Minimo per MVP*

