$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$BuildPython = Join-Path $Root ".venv-build\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $BuildPython)) {
    python -m venv .venv-build
}
& $BuildPython -m pip install --upgrade pip
& $BuildPython -m pip install -e ".[desktop]"
& $BuildPython -m unittest discover -s tests -v

Push-Location frontend
npm.cmd ci
npm.cmd run test
npm.cmd run build
Pop-Location

& $BuildPython scripts/build_icons.py
& $BuildPython -m PyInstaller --clean --noconfirm packaging/decision_shelf_windows.spec

New-Item -ItemType Directory -Force -Path release | Out-Null
$Archive = Join-Path $Root "release/Decision-Shelf-windows-x64.zip"
if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
Compress-Archive -Path "dist/Decision Shelf" -DestinationPath $Archive -CompressionLevel Optimal
Write-Host "Created $Archive"
