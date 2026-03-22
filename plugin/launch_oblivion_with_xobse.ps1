param(
    [string]$GamePath
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$findScript = Join-Path $scriptDir "find_oblivion.ps1"

if ([string]::IsNullOrWhiteSpace($GamePath) -and (Test-Path $findScript)) {
    $GamePath = & $findScript | Select-Object -First 1
}

if ([string]::IsNullOrWhiteSpace($GamePath) -or -not (Test-Path (Join-Path $GamePath "Oblivion.exe"))) {
    throw "Could not detect Oblivion automatically. Pass -GamePath explicitly."
}

$loaderCandidates = @(
    (Join-Path $GamePath "xOBSE_loader.exe"),
    (Join-Path $GamePath "obse_loader.exe")
)

$loader = $loaderCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $loader) {
    throw "Could not find xOBSE_loader.exe or obse_loader.exe in $GamePath. Install xOBSE first."
}

Start-Process -FilePath $loader -WorkingDirectory $GamePath
Write-Output "Launched Oblivion through $loader"
