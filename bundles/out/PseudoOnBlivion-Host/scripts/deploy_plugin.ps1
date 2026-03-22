param(
    [string]$GamePath,
    [string]$Configuration = "Debug",
    [string]$IniPath = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$packageScript = Join-Path $scriptDir "package_plugin.ps1"
$findScript = Join-Path $scriptDir "find_oblivion.ps1"
$stagingRoot = Join-Path $scriptDir "dist"

if ([string]::IsNullOrWhiteSpace($GamePath)) {
    if (Test-Path $findScript) {
        $detected = & $findScript | Select-Object -First 1
        if ($detected) {
            $GamePath = $detected
        }
    }
}

if ([string]::IsNullOrWhiteSpace($GamePath)) {
    throw "Could not detect Oblivion automatically. Pass -GamePath explicitly."
}

& $packageScript -Configuration $Configuration -OutputRoot $stagingRoot -IniPath $IniPath

$sourceDir = Join-Path $stagingRoot "Data\OBSE\Plugins"
$targetDir = Join-Path $GamePath "Data\OBSE\Plugins"
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

Copy-Item (Join-Path $sourceDir "*") $targetDir -Force

Write-Output "Deployed plugin files to $targetDir"
