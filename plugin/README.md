# Plugin Notes

This folder is now a fuller OBSE plugin scaffold, and the built DLL exports `OBSEPlugin_Query` and `OBSEPlugin_Load`, but it is still not a finished multiplayer mod.

## What is here

- `PseudoOnBlivionPlugin.*` wires together the high-level plugin loop
- `network/NetworkClient.*` provides a tiny WinSock transport with send/receive paths
- `config/PluginConfig.*` loads an ini-style config
- `game/GameAdapter.*` isolates transport code from Oblivion runtime hooks, captures live local player state, drives experimental same-cell remote proxies, applies first-pass quest/loot updates, replays simple world-loot transforms, and now handles lightweight animation/combat application on the game thread
- `logging/Logger.*` writes a plugin log file
- `obse/PluginEntrypoint.cpp` now contains exported OBSE entry points plus standalone bootstrap helpers
- `PseudoOnBlivion.vcxproj` / `.sln` let you open the scaffold in Visual Studio

## What is intentionally missing

- real OBSE SDK headers and interface access
- robust actor spawning and remote avatar reconciliation
- deeper animation/combat hook installation
- true world/container loot replication
- richer quest/objective/script replication

## Integration points

When you wire this into a real OBSE build, the usual next steps are:

1. Live-test and harden proxy actors around cell transitions, save/load, and disconnect cleanup.
2. Replace the standalone bridge in `obse/PluginEntrypoint.cpp` with real OBSE exports where needed for your target runtime.
3. Add deeper animation and combat event hooks now that local state capture exists.
4. Replace first-pass world-loot replay with actual world/container replication.
5. Restrict quest writes so only the designated host can emit `quest_state`.

## Recommended authority model

- Host peer: quest progression, NPC interaction outcomes, cell ownership
- All peers: local movement intent, animation suggestions, local combat telemetry
- Server: routing, coarse validation, conflict logging
