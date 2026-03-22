param(
    [string]$Configuration = "Debug",
    [string]$OutputRoot = "",
    [string]$IniPath = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $scriptDir "dist"
}

$dllPath = Join-Path $scriptDir "build\$Configuration\PseudoOnBlivion.dll"
$pdbPath = Join-Path $scriptDir "build\$Configuration\PseudoOnBlivion.pdb"

if ([string]::IsNullOrWhiteSpace($IniPath)) {
    $IniPath = Join-Path $scriptDir "PseudoOnBlivion.ini.example"
}

if (-not (Test-Path $dllPath)) {
    throw "Built DLL not found at $dllPath. Build the project first."
}

if (-not (Test-Path $IniPath)) {
    throw "Plugin ini file not found at $IniPath."
}

$pluginDir = Join-Path $OutputRoot "Data\OBSE\Plugins"
New-Item -ItemType Directory -Force -Path $pluginDir | Out-Null

Copy-Item $dllPath (Join-Path $pluginDir "PseudoOnBlivion.dll") -Force

if (Test-Path $pdbPath) {
    Copy-Item $pdbPath (Join-Path $pluginDir "PseudoOnBlivion.pdb") -Force
}

Copy-Item $IniPath (Join-Path $pluginDir "PseudoOnBlivion.ini") -Force

Write-Output "Packaged plugin files to $pluginDir"
