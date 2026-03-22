# Quickstart

This is the shortest path to try the current prototype on two systems.

## Host

1. Run `PseudoOnBlivionHostSetup.exe` or unzip `PseudoOnBlivion-Host.zip`
2. Run `scripts\install_xobse.ps1` if xOBSE is not already installed
3. Edit `Data\OBSE\Plugins\PseudoOnBlivion.ini`
4. Edit `server\relay_config.json`
5. Run `scripts\open_firewall_port.ps1` as admin if using your own network
6. Run `scripts\start_host_relay.ps1`
7. Launch Oblivion through xOBSE

## Joiner

1. Run `PseudoOnBlivionJoinerSetup.exe` or unzip `PseudoOnBlivion-Joiner.zip`
2. Run `scripts\install_xobse.ps1` if xOBSE is not already installed
3. Edit `Data\OBSE\Plugins\PseudoOnBlivion.ini`
4. Set `server_host` to the host's Tailscale IP, public IP, or DNS name
5. Launch Oblivion through xOBSE

## Important current limitation

At this stage the transport, packaging, and xOBSE plugin loading path are the parts that are real and tested.
Remote players are not yet visibly spawned in-world, so this is still a development prototype rather than a playable co-op release.
