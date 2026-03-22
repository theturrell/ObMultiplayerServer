# Joiner Setup

This is the expected setup for someone joining a host session.

## 1. Required baseline

- Same game edition and patch level as the host
- Same xOBSE version as the host
- Same `Pseudo-OnBlivion` plugin build
- Matching mod list for anything that affects animation state, skeletons, or core gameplay forms

If the host and joiner are not aligned here, desync risk goes up fast.

## 2. Easiest join flow

The preferred path for non-technical players is now:

1. Run `PseudoOnBlivionJoiner.exe`
2. Enter the host IP or DNS name
3. Enter the character name
4. Pick the Oblivion folder if auto-detect missed it
5. Press `Run Check` to verify the game folder, xOBSE install, and relay reachability
6. Press `Install xOBSE` if needed
7. Press `Join Game`

The app writes the joiner config, copies the bundled plugin into `Data\OBSE\Plugins`, and launches Oblivion through xOBSE.

## 2.1 After a playtest

If something goes wrong during a friend session, collect the joiner diagnostics with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\collect_playtest_logs.ps1
```

That bundles the joiner-side plugin log and config into a zip you can send back.

## 3. Network destination

Use one of the following addresses in the joiner's plugin config:

- Host Tailscale IP
- Host public IP plus forwarded port
- Shared VPS relay hostname

## 4. Joiner plugin config

Example:

```ini
[network]
server_host=100.64.10.20
server_port=7777
room=session-1
player_id=joiner-player
character_name=JoinerHero
host_authority=false
server_token=replace-this-if-private
send_interval_ms=100

[logging]
log_path=PseudoOnBlivion.log
```

Rules:

- `room` must match the host
- `server_port` must match the relay
- `server_token` must match if private sessions are enabled
- `player_id` must be unique per connected player

Install xOBSE if needed:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\install_xobse.ps1 -GamePath "C:\Games\Oblivion"
```

Then deploy the joiner profile directly:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\deploy_plugin.ps1 -GamePath "C:\Games\Oblivion" -Configuration Debug -IniPath plugin\profiles\PseudoOnBlivion.joiner.ini
```

## 5. What the joiner should expect today

Today, the codebase does provide:

- relay connection
- joiner-side preflight checks for relay reachability and local install health
- live outgoing local player state
- experimental same-cell remote stand-ins
- first-pass quest stage application
- first-pass inventory-loot mirroring plus simple world-drop replay

It still does not provide a fully polished multiplayer experience. The biggest remaining gaps are:

- hardened remote actor behavior across all cells and save/load edges
- synchronized animation playback
- full combat resolution
- true world/container loot replication
- richer quest/objective replication
