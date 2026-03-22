param(
    [string]$GamePath = "",
    [string]$OutputRoot = "",
    [switch]$IncludeServerState
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

if ([string]::IsNullOrWhiteSpace($GamePath)) {
    $finder = Join-Path $scriptDir "find_oblivion.ps1"
    if (Test-Path $finder) {
        $GamePath = & $finder
    }
}

if ([string]::IsNullOrWhiteSpace($GamePath) -or -not (Test-Path (Join-Path $GamePath "Oblivion.exe"))) {
    throw "Could not find a valid Oblivion install. Pass -GamePath explicitly."
}

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $repoRoot "playtest_logs"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$sessionRoot = Join-Path $OutputRoot "PseudoOnBlivion-Logs-$timestamp"
$pluginSource = Join-Path $GamePath "Data\OBSE\Plugins"
$pluginOut = Join-Path $sessionRoot "plugin"
$serverOut = Join-Path $sessionRoot "server"

New-Item -ItemType Directory -Force -Path $sessionRoot, $pluginOut, $serverOut | Out-Null

$pluginFiles = @(
    "PseudoOnBlivion.log",
    "PseudoOnBlivion.ini"
)

foreach ($name in $pluginFiles) {
    $source = Join-Path $pluginSource $name
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $pluginOut $name) -Force
    }
}

$repoServerFiles = @(
    "relay.log",
    "relay_config.json",
    "relay_config.example.json"
)

foreach ($name in $repoServerFiles) {
    $source = Join-Path (Join-Path $repoRoot "server") $name
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $serverOut $name) -Force
    }
}

if ($IncludeServerState) {
    $stateRoot = Join-Path $repoRoot "server_state"
    if (Test-Path $stateRoot) {
        Copy-Item $stateRoot (Join-Path $sessionRoot "server_state") -Recurse -Force
    }
}

$summary = @"
PSEUDO-ONBLIVION PLAYTEST LOGS

Collected: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
GamePath: $GamePath
HostRepoRoot: $repoRoot

Included:
- plugin log/config if present
- relay log/config if present
$(if ($IncludeServerState) { "- server_state snapshots" } else { "- server_state snapshots not included" })
"@

$summary | Set-Content (Join-Path $sessionRoot "README.txt")

$zipPath = Join-Path $OutputRoot "PseudoOnBlivion-Logs-$timestamp.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path (Join-Path $sessionRoot "*") -DestinationPath $zipPath -Force

Write-Output "Collected playtest logs: $zipPath"
