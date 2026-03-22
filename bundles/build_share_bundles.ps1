param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$pluginDir = Join-Path $root "plugin"
$serverDir = Join-Path $root "server"
$launcherDir = Join-Path $root "launcher"
$docsDir = Join-Path $root "docs"
$relayBuildScript = Join-Path $serverDir "build_relay_exe.ps1"
$hostGuiBuildScript = Join-Path $launcherDir "build_host_gui_exe.ps1"
$joinerGuiBuildScript = Join-Path $launcherDir "build_joiner_gui_exe.ps1"
$bundleRoot = Join-Path $root "bundles\out"
$hostRoot = Join-Path $bundleRoot "PseudoOnBlivion-Host"
$joinRoot = Join-Path $bundleRoot "PseudoOnBlivion-Joiner"

Remove-Item $hostRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $joinRoot -Recurse -Force -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Force -Path $hostRoot, $joinRoot | Out-Null

if (Test-Path $relayBuildScript) {
    & $relayBuildScript -OutputRoot (Join-Path $serverDir "dist")
}
if (Test-Path $hostGuiBuildScript) {
    & $hostGuiBuildScript -OutputRoot (Join-Path $launcherDir "dist")
}
if (Test-Path $joinerGuiBuildScript) {
    & $joinerGuiBuildScript -OutputRoot (Join-Path $launcherDir "dist")
}

& (Join-Path $pluginDir "package_plugin.ps1") -Configuration $Configuration -OutputRoot $hostRoot
& (Join-Path $pluginDir "package_plugin.ps1") -Configuration $Configuration -OutputRoot $joinRoot

Copy-Item (Join-Path $pluginDir "profiles\PseudoOnBlivion.host.ini") (Join-Path $hostRoot "Data\OBSE\Plugins\PseudoOnBlivion.ini") -Force
Copy-Item (Join-Path $pluginDir "profiles\PseudoOnBlivion.joiner.ini") (Join-Path $joinRoot "Data\OBSE\Plugins\PseudoOnBlivion.ini") -Force

New-Item -ItemType Directory -Force -Path (Join-Path $hostRoot "server"), (Join-Path $hostRoot "scripts"), (Join-Path $joinRoot "scripts") | Out-Null

Copy-Item (Join-Path $serverDir "relay_server.py") (Join-Path $hostRoot "server\relay_server.py") -Force
Copy-Item (Join-Path $serverDir "relay_config.example.json") (Join-Path $hostRoot "server\relay_config.json") -Force
Copy-Item (Join-Path $serverDir "fanout_smoke_test.py") (Join-Path $hostRoot "server\fanout_smoke_test.py") -Force
Copy-Item (Join-Path $serverDir "session_e2e_test.py") (Join-Path $hostRoot "server\session_e2e_test.py") -Force
if (Test-Path (Join-Path $serverDir "dist\PseudoOnBlivionRelay.exe")) {
    Copy-Item (Join-Path $serverDir "dist\PseudoOnBlivionRelay.exe") (Join-Path $hostRoot "server\PseudoOnBlivionRelay.exe") -Force
}
if (Test-Path (Join-Path $launcherDir "dist\PseudoOnBlivionHost.exe")) {
    Copy-Item (Join-Path $launcherDir "dist\PseudoOnBlivionHost.exe") (Join-Path $hostRoot "PseudoOnBlivionHost.exe") -Force
}
Copy-Item (Join-Path $serverDir "start_host_relay.ps1") (Join-Path $hostRoot "scripts\start_host_relay.ps1") -Force
Copy-Item (Join-Path $serverDir "open_firewall_port.ps1") (Join-Path $hostRoot "scripts\open_firewall_port.ps1") -Force
Copy-Item (Join-Path $pluginDir "deploy_plugin.ps1") (Join-Path $hostRoot "scripts\deploy_plugin.ps1") -Force
Copy-Item (Join-Path $pluginDir "find_oblivion.ps1") (Join-Path $hostRoot "scripts\find_oblivion.ps1") -Force
Copy-Item (Join-Path $pluginDir "install_xobse.ps1") (Join-Path $hostRoot "scripts\install_xobse.ps1") -Force
Copy-Item (Join-Path $pluginDir "launch_oblivion_with_xobse.ps1") (Join-Path $hostRoot "scripts\launch_oblivion_with_xobse.ps1") -Force
Copy-Item (Join-Path $pluginDir "collect_playtest_logs.ps1") (Join-Path $hostRoot "scripts\collect_playtest_logs.ps1") -Force
Copy-Item (Join-Path $pluginDir "deploy_plugin.ps1") (Join-Path $joinRoot "scripts\deploy_plugin.ps1") -Force
Copy-Item (Join-Path $pluginDir "find_oblivion.ps1") (Join-Path $joinRoot "scripts\find_oblivion.ps1") -Force
Copy-Item (Join-Path $pluginDir "install_xobse.ps1") (Join-Path $joinRoot "scripts\install_xobse.ps1") -Force
Copy-Item (Join-Path $pluginDir "launch_oblivion_with_xobse.ps1") (Join-Path $joinRoot "scripts\launch_oblivion_with_xobse.ps1") -Force
Copy-Item (Join-Path $pluginDir "collect_playtest_logs.ps1") (Join-Path $joinRoot "scripts\collect_playtest_logs.ps1") -Force
if (Test-Path (Join-Path $launcherDir "dist\PseudoOnBlivionJoiner.exe")) {
    Copy-Item (Join-Path $launcherDir "dist\PseudoOnBlivionJoiner.exe") (Join-Path $joinRoot "PseudoOnBlivionJoiner.exe") -Force
}
Copy-Item (Join-Path $docsDir "QUICKSTART.md") (Join-Path $hostRoot "QUICKSTART.md") -Force
Copy-Item (Join-Path $docsDir "QUICKSTART.md") (Join-Path $joinRoot "QUICKSTART.md") -Force

@"
PSEUDO-ONBLIVION HOST BUNDLE

1. Run PseudoOnBlivionHost.exe
2. Set the relay host/port, room, character name, token, and game folder
3. Press Run Check
4. Press Install xOBSE if needed
5. Press Open Firewall if you are hosting over your network
6. Press Host Session to start the relay and launch the game correctly
7. After a playtest, run scripts\collect_playtest_logs.ps1 -IncludeServerState to bundle the logs and room snapshots
"@ | Set-Content (Join-Path $hostRoot "README_HOST.txt")

@"
PSEUDO-ONBLIVION JOINER BUNDLE

1. Run PseudoOnBlivionJoiner.exe
2. Enter the host IP or DNS name and your character name
3. Press Run Check to verify the game folder, xOBSE, and relay reachability
4. Press Install xOBSE if needed
5. Press Join Game
6. After a playtest, run scripts\collect_playtest_logs.ps1 to bundle your client log and config
"@ | Set-Content (Join-Path $joinRoot "README_JOINER.txt")

$hostZip = Join-Path $bundleRoot "PseudoOnBlivion-Host.zip"
$joinZip = Join-Path $bundleRoot "PseudoOnBlivion-Joiner.zip"
Remove-Item $hostZip, $joinZip -Force -ErrorAction SilentlyContinue

Compress-Archive -Path (Join-Path $hostRoot "*") -DestinationPath $hostZip -Force
Compress-Archive -Path (Join-Path $joinRoot "*") -DestinationPath $joinZip -Force

Write-Output "Built host bundle: $hostZip"
Write-Output "Built joiner bundle: $joinZip"
