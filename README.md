# Pseudo-OnBlivion

`Pseudo-OnBlivion` is a prototype multiplayer stack for The Elder Scrolls IV: Oblivion built around two pieces:

- a lightweight custom relay server,
- an OBSE plugin that injects into the game and syncs a small, controlled subset of state.

This repository starts with the first practical slice:

- authenticated session handshake,
- live local player position/rotation/cell/health/magicka/stamina sync,
- experimental in-cell remote proxy spawning, smoothing, and cleanup,
- combat event forwarding with target hints,
- first-pass quest stage/objective/active/completion application,
- first-pass inventory loot plus world-object loot transform replay,
- an xOBSE plugin scaffold with a background socket client.

## Why this shape

A full "real multiplayer Oblivion" implementation is much harder than just moving actors around. The safest way to iterate is:

1. establish a stable transport layer,
2. define a compact sync protocol,
3. forward only low-risk state first,
4. gate quest replication behind explicit ownership rules.

That is what this starter does.

## Repository layout

- `server/` - dependency-free Python relay server
- `plugin/` - C++ xOBSE plugin scaffold and TCP transport
- `shared/` - protocol notes and message contract examples
- `docs/` - host, joiner, and game integration setup notes

## Current protocol coverage

### Implemented in the starter

- `hello` / `welcome`
- `player_state`
- `combat_event`
- `quest_state`
- `loot_state`
- server-side room membership, persistence, and late-join replay
- relay/client protocol-version rejection during handshake

### Designed but not fully wired into the game yet

- animation replication
- actor spawn/despawn
- quest authority arbitration
- world cell ownership and streaming

## Running the relay

The relay is plain Python and uses only the standard library:

```powershell
py server\relay_server.py --config server\relay_config.json
```

If your machine uses `python` instead of `py`, that works too.

Start by copying the sample config:

```powershell
Copy-Item server\relay_config.example.json server\relay_config.json
```

You can sanity-check the handshake from a second terminal:

```powershell
py server\smoke_test_client.py --host 127.0.0.1 --port 7777
```

That client should print a single `welcome` JSON message from the relay.

The relay now also persists the latest player, quest, and loot state per room under `state_root`.
It can now also write a relay log file directly via `log_file` in the relay config.

There is also a fuller automated relay/session check:

```powershell
python server\session_e2e_test.py
```

That test launches a temporary relay, validates replay for richer `player_state` / `quest_state` / `loot_state` payloads, checks host-only world-state writes, and confirms protocol mismatches are rejected during handshake.

For real friend playtests, you can now collect diagnostics with:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\collect_playtest_logs.ps1 -GamePath "C:\Program Files (x86)\Steam\steamapps\common\Oblivion" -IncludeServerState
```

That creates a zip containing the plugin log/config and, on the host machine, the relay log/config plus optional `server_state` snapshots.

For remote friends, set `host` to `0.0.0.0` in the relay config and either:

- use Tailscale,
- forward TCP `7777` on your router,
- or host the relay on a VPS.

## Plugin roadmap

The OBSE side is intentionally a skeleton. It shows where we will plug in:

- player polling from the game thread,
- event capture for combat/animation hooks,
- background network send/receive,
- marshaling remote updates back to in-game actor controllers.

The plugin now has a Visual Studio project, config parser, logging, send/receive transport, exported xOBSE-style entry points, live local player snapshot reads, an experimental remote proxy path that spawns same-cell stand-ins with xOBSE console calls, first-pass quest stage/objective/activation application, first-pass world loot transform replay, and session reset/protocol mismatch handling. Animation sync, hardened remote avatar reconciliation, and real gameplay validation are still not fully wired into the game world.

## Suggested next milestones

1. Live-test the proxy path in a real two-machine session and harden failure cases around cell transitions, save/load edges, and combat targets.
2. Tighten animation/combat replication beyond the current lightweight suggestion model.
3. Replace first-pass world loot replay with true world-container/object ownership replication.
4. Introduce quest authority rules:
   - only one peer owns a questline write path,
   - all quest stage updates are monotonic,
   - conflicting updates are rejected and logged.
5. Add live two-machine gameplay validation for movement, combat, and quest/loot recovery.

## Setup guides

- Host/network setup: `docs/HOST_SETUP.md`
- Joiner setup: `docs/JOINER_SETUP.md`
- Remaining in-game integration work: `docs/GAME_INTEGRATION.md`
- Fast handoff checklist: `docs/QUICKSTART.md`

## Build and package

Build the plugin scaffold:

```powershell
& 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\amd64\MSBuild.exe' plugin\PseudoOnBlivion.sln /t:Build /p:Configuration=Debug /p:Platform=Win32
```

Package it into a game-like folder layout:

```powershell
powershell -ExecutionPolicy Bypass -File plugin\package_plugin.ps1 -Configuration Debug
```

That will create:

- `plugin\dist\Data\OBSE\Plugins\PseudoOnBlivion.dll`
- `plugin\dist\Data\OBSE\Plugins\PseudoOnBlivion.ini`

To generate sendable host and joiner bundles:

```powershell
powershell -ExecutionPolicy Bypass -File bundles\build_share_bundles.ps1 -Configuration Debug
```

That will create:

- `bundles\out\PseudoOnBlivion-Host.zip`
- `bundles\out\PseudoOnBlivion-Joiner.zip`

The joiner bundle now also includes `PseudoOnBlivionJoiner.exe`, a simple Windows GUI for entering the host address and character name, installing xOBSE if needed, and launching the game.

To generate Windows installer executables for host and joiner machines:

```powershell
powershell -ExecutionPolicy Bypass -File installer\build_installers.ps1 -Configuration Debug
```

That will create:

- `bundles\out\installers\PseudoOnBlivionHostSetup.exe`
- `bundles\out\installers\PseudoOnBlivionJoinerSetup.exe`

## Important caveat

Oblivion was not designed for deterministic multiplayer simulation. Treat this as a "co-op illusion" architecture:

- one player is authoritative for certain world events,
- not every system should be synchronized,
- quests need carefully curated replication rules,
- AI and physics divergence are expected unless heavily constrained.
