$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Assert-NativeSuccess {
    param(
        [string]$Step,
        [int]$ExitCode
    )
    if ($ExitCode -ne 0) {
        throw "$Step failed with exit code $ExitCode."
    }
}

$BuildPython = Join-Path $Root ".venv-build\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $BuildPython)) {
    python -m venv .venv-build
    Assert-NativeSuccess "Create build virtual environment" $LASTEXITCODE
}
& $BuildPython -m pip install --upgrade pip
Assert-NativeSuccess "Upgrade pip" $LASTEXITCODE
& $BuildPython -m pip install -e ".[desktop]"
Assert-NativeSuccess "Install Python dependencies" $LASTEXITCODE
& $BuildPython -m unittest discover -s tests -v
Assert-NativeSuccess "Run Python tests" $LASTEXITCODE

Push-Location frontend
try {
    npm.cmd ci
    Assert-NativeSuccess "Install frontend dependencies" $LASTEXITCODE
    npm.cmd run test
    Assert-NativeSuccess "Run frontend tests" $LASTEXITCODE
    if (Test-Path -LiteralPath dist) { Remove-Item -LiteralPath dist -Recurse -Force }
    npm.cmd run build
    Assert-NativeSuccess "Build frontend" $LASTEXITCODE
    if (-not (Test-Path -LiteralPath "dist/index.html")) {
        throw "Frontend build completed without producing dist/index.html."
    }
} finally {
    Pop-Location
}

& $BuildPython scripts/build_icons.py
Assert-NativeSuccess "Build application icons" $LASTEXITCODE
& $BuildPython -m PyInstaller --clean --noconfirm packaging/decision_shelf_windows.spec
Assert-NativeSuccess "Package Windows application" $LASTEXITCODE

if (-not (Test-Path -LiteralPath "dist/Decision Shelf")) {
    throw "PyInstaller completed without producing dist/Decision Shelf."
}

New-Item -ItemType Directory -Force -Path release | Out-Null
$Archive = Join-Path $Root "release/Decision-Shelf-windows-x64.zip"
if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
Compress-Archive -Path "dist/Decision Shelf" -DestinationPath $Archive -CompressionLevel Optimal
Write-Host "Created $Archive"
