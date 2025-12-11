# Copia PDF da procedure sistema a data/input_docs/

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SourceDir = "D:\.pdf\procedure sistema"
$TargetDir = Join-Path $ProjectRoot "data\input_docs"

Write-Host "============================================"
Write-Host "  Copia PDF Documenti ISO"
Write-Host "============================================"
Write-Host ""

# Verifica sorgente
if (-not (Test-Path $SourceDir)) {
    Write-Host "Errore: Directory sorgente non trovata: $SourceDir"
    exit 1
}

# Crea directory target se non esiste
if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

# Conta PDF sorgente
$sourcePdfs = Get-ChildItem -Path $SourceDir -Filter "*.pdf" -Recurse
$count = $sourcePdfs.Count
Write-Host "Trovati $count file PDF in sorgente"
Write-Host ""

# Copia con struttura flat
$copied = 0
foreach ($pdf in $sourcePdfs) {
    $targetPath = Join-Path $TargetDir $pdf.Name
    
    # Evita sovrascrittura
    if (Test-Path $targetPath) {
        Write-Host "  Skip (esiste): $($pdf.Name)"
        continue
    }
    
    Copy-Item -Path $pdf.FullName -Destination $targetPath
    Write-Host "  Copiato: $($pdf.Name)"
    $copied++
}

Write-Host ""
Write-Host "============================================"
Write-Host "  Completato: $copied file copiati"
Write-Host "============================================"

# Lista file per tipo
$psFiles = Get-ChildItem -Path $TargetDir -Filter "PS-*.pdf" -ErrorAction SilentlyContinue
$ilFiles = Get-ChildItem -Path $TargetDir -Filter "IL-*.pdf" -ErrorAction SilentlyContinue
$mrFiles = Get-ChildItem -Path $TargetDir -Filter "MR-*.pdf" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Riepilogo per tipo:"
$psCount = if ($psFiles) { $psFiles.Count } else { 0 }
$ilCount = if ($ilFiles) { $ilFiles.Count } else { 0 }
$mrCount = if ($mrFiles) { $mrFiles.Count } else { 0 }
Write-Host "  PS (Procedure Sistema): $psCount"
Write-Host "  IL (Istruzioni Lavoro): $ilCount"
Write-Host "  MR (Moduli Registrazione): $mrCount"
