param(
    [string]$PythonPath = "",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"
    )
    $PythonPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $PythonPath -or -not (Test-Path $PythonPath)) {
    throw "Could not find python.exe. Pass -PythonPath explicitly."
}

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $scriptDir "dist"
}

$specRoot = Join-Path $scriptDir "spec"
New-Item -ItemType Directory -Force -Path $OutputRoot, $specRoot | Out-Null

$maxAttempts = 3
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    & $PythonPath -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name PseudoOnBlivionHost `
        --distpath $OutputRoot `
        --workpath (Join-Path $scriptDir "build") `
        --specpath $specRoot `
        (Join-Path $scriptDir "host_gui.py")

    if ($LASTEXITCODE -eq 0) {
        break
    }

    if ($attempt -ge $maxAttempts) {
        throw "PyInstaller failed with exit code $LASTEXITCODE after $attempt attempt(s)"
    }

    Start-Sleep -Milliseconds 500
}

Write-Output "Built host GUI executable: $(Join-Path $OutputRoot 'PseudoOnBlivionHost.exe')"
