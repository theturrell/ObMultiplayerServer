param(
    [string]$PythonPath = "",
    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverDir = $scriptDir

if (-not (Test-Path (Join-Path $serverDir "relay_server.py"))) {
    $bundleServerDir = Join-Path (Split-Path -Parent $scriptDir) "server"
    if (Test-Path (Join-Path $bundleServerDir "relay_server.py")) {
        $serverDir = $bundleServerDir
    }
}

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $serverDir "relay_config.json"
}

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $exePath = Join-Path $serverDir "PseudoOnBlivionRelay.exe"
    if (Test-Path $exePath) {
        if (-not (Test-Path $ConfigPath)) {
            throw "Relay config not found at $ConfigPath"
        }

        & $exePath --config $ConfigPath
        exit $LASTEXITCODE
    }
}

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

if (-not (Test-Path $ConfigPath)) {
    throw "Relay config not found at $ConfigPath"
}

& $PythonPath (Join-Path $serverDir "relay_server.py") --config $ConfigPath
