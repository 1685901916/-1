$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "[1/4] Building frontend dist..."
Push-Location frontend
npm run build
Pop-Location

Write-Host "[2/4] Installing launcher dependencies..."
python -m pip install -e ".[launcher]" pyinstaller

Write-Host "[3/4] Cleaning previous launcher build..."
Remove-Item "$projectRoot\build\MangaEnhancementLauncher" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$projectRoot\dist\MangaEnhancementLauncher" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "[4/4] Packaging launcher..."
pyinstaller packaging\launcher.spec --noconfirm --clean

Write-Host ""
Write-Host "Done."
Write-Host "Output: $projectRoot\dist\MangaEnhancementLauncher"
