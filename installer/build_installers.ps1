param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$bundleScript = Join-Path $root "bundles\build_share_bundles.ps1"
$bundleRoot = Join-Path $root "bundles\out"
$outputRoot = Join-Path $bundleRoot "installers"
$isccCandidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    throw "Could not find ISCC.exe. Install Inno Setup 6 first."
}

& $bundleScript -Configuration $Configuration

New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null

& $iscc "/DSourceRoot=$bundleRoot" "/DOutputRoot=$outputRoot" (Join-Path $PSScriptRoot "PseudoOnBlivionHost.iss")
& $iscc "/DSourceRoot=$bundleRoot" "/DOutputRoot=$outputRoot" (Join-Path $PSScriptRoot "PseudoOnBlivionJoiner.iss")

Write-Output "Built installers in $outputRoot"
