@echo off
chcp 65001 >nul
title OVV ISO Chat v3.9.3

echo ============================================
echo    OVV ISO Chat v3.9.3 - Avvio Rapido
echo ============================================
echo.

REM Verifica venv
if not exist "venv\Scripts\activate.bat" (
    echo [!] Virtual environment non trovato!
    echo     Esegui prima: powershell -File scripts\setup.ps1
    echo.
    pause
    exit /b 1
)

REM Attiva venv
call venv\Scripts\activate.bat

REM Verifica Qdrant
echo [1/3] Verifica Qdrant...
curl -s http://localhost:6333/health >nul 2>&1
if errorlevel 1 (
    echo      Qdrant non in esecuzione - avvio Docker...
    docker start qdrant-ovv 2>nul
    if errorlevel 1 (
        docker run -d --name qdrant-ovv -p 6333:6333 -p 6334:6334 -v "%cd%\data\qdrant:/qdrant/storage" qdrant/qdrant:latest
    )
    timeout /t 5 >nul
)
echo      [OK] Qdrant

REM Verifica Ollama
echo [2/3] Verifica Ollama...
ollama list >nul 2>&1
if errorlevel 1 (
    echo      [!] Ollama non in esecuzione
    echo          Avvia Ollama manualmente: ollama serve
    echo.
) else (
    echo      [OK] Ollama
)

REM Avvia Chainlit
echo [3/3] Avvio Chainlit...
echo.
echo ============================================
echo    Chat disponibile su: http://localhost:7866
echo    Login: admin/admin123, engineer/eng123, user/user123
echo    Premi Ctrl+C per fermare
echo ============================================
echo.

chainlit run app_chainlit.py --host 0.0.0.0 --port 7866


