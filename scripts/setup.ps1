# ============================================================================
# OVV ISO Chat v3.1 - Setup Script
# ============================================================================
# Esegue:
#   1. Creazione/attivazione venv
#   2. Installazione dipendenze Poetry
#   3. Pull modello Ollama
#   4. Avvio container Qdrant
# ============================================================================

param(
    [switch]$SkipOllama,
    [switch]$SkipQdrant,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  OVV ISO Chat v3.1 - Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ----------------------------------------------------------------------------
# 1. Verifica prerequisiti
# ----------------------------------------------------------------------------
Write-Host "[1/5] Verifica prerequisiti..." -ForegroundColor Yellow

# Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "  ❌ Python non trovato!" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Python: $($python.Source)" -ForegroundColor Green

# Poetry
$poetry = Get-Command poetry -ErrorAction SilentlyContinue
if (-not $poetry) {
    Write-Host "  ⚠ Poetry non trovato, installazione..." -ForegroundColor Yellow
    pip install poetry
}
Write-Host "  ✓ Poetry installato" -ForegroundColor Green

# Docker (per Qdrant)
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker -and -not $SkipQdrant) {
    Write-Host "  ⚠ Docker non trovato - Qdrant non sarà avviato" -ForegroundColor Yellow
    $SkipQdrant = $true
}

# Ollama
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama -and -not $SkipOllama) {
    Write-Host "  ⚠ Ollama non trovato - LLM non sarà scaricato" -ForegroundColor Yellow
    $SkipOllama = $true
}

Write-Host ""

# ----------------------------------------------------------------------------
# 2. Setup Virtual Environment
# ----------------------------------------------------------------------------
Write-Host "[2/5] Setup Virtual Environment..." -ForegroundColor Yellow

Set-Location $ProjectRoot

if (-not (Test-Path "venv")) {
    Write-Host "  Creazione venv..." -ForegroundColor Gray
    python -m venv venv
}

# Attivazione venv
Write-Host "  Attivazione venv..." -ForegroundColor Gray
& "$ProjectRoot\venv\Scripts\Activate.ps1"

Write-Host "  ✓ Virtual environment attivo" -ForegroundColor Green
Write-Host ""

# ----------------------------------------------------------------------------
# 3. Installazione dipendenze
# ----------------------------------------------------------------------------
Write-Host "[3/5] Installazione dipendenze Poetry..." -ForegroundColor Yellow

poetry install --no-interaction
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ Errore installazione Poetry!" -ForegroundColor Red
    exit 1
}

# Install UI group
poetry install --with ui --no-interaction

Write-Host "  ✓ Dipendenze installate" -ForegroundColor Green
Write-Host ""

# ----------------------------------------------------------------------------
# 4. Ollama - Pull modello
# ----------------------------------------------------------------------------
if (-not $SkipOllama) {
    Write-Host "[4/5] Ollama - Download modello..." -ForegroundColor Yellow
    
    Write-Host "  Pulling qwen3:8b-instruct-q4_K_M (~5GB)..." -ForegroundColor Gray
    ollama pull qwen3:8b-instruct-q4_K_M
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ Modello scaricato" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Download modello fallito (continua comunque)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[4/5] Ollama - Skipped" -ForegroundColor Gray
}
Write-Host ""

# ----------------------------------------------------------------------------
# 5. Qdrant - Avvio container
# ----------------------------------------------------------------------------
if (-not $SkipQdrant) {
    Write-Host "[5/5] Qdrant - Avvio container Docker..." -ForegroundColor Yellow
    
    # Verifica se container esiste già
    $existingContainer = docker ps -a --filter "name=qdrant-ovv" --format "{{.Names}}" 2>$null
    
    if ($existingContainer -eq "qdrant-ovv") {
        Write-Host "  Container esistente, riavvio..." -ForegroundColor Gray
        docker start qdrant-ovv
    } else {
        Write-Host "  Creazione nuovo container..." -ForegroundColor Gray
        docker run -d `
            --name qdrant-ovv `
            -p 6333:6333 `
            -p 6334:6334 `
            -v "${ProjectRoot}/data/qdrant:/qdrant/storage" `
            qdrant/qdrant:latest
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ Qdrant in esecuzione su http://localhost:6333" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Avvio Qdrant fallito" -ForegroundColor Yellow
    }
} else {
    Write-Host "[5/5] Qdrant - Skipped" -ForegroundColor Gray
}

Write-Host ""

# ----------------------------------------------------------------------------
# Riepilogo
# ----------------------------------------------------------------------------
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Setup Completato!" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Prossimi step:" -ForegroundColor Yellow
Write-Host "  1. Attiva venv:  .\venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "  2. Verifica VRAM: nvidia-smi" -ForegroundColor Gray
Write-Host "  3. Test base:     pytest tests/ -v" -ForegroundColor Gray
Write-Host "  4. Avvia chat:    python -m src.main" -ForegroundColor Gray
Write-Host ""

# Verifica VRAM se nvidia-smi disponibile
$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    Write-Host "VRAM attuale:" -ForegroundColor Yellow
    nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits
}

