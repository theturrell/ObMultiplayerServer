# Game Integration Roadmap

This document explains what still needs to happen inside Oblivion before this becomes a usable co-op prototype.

## What exists now

- Relay server with room fan-out
- Optional shared-token private sessions
- Plugin config parser
- Plugin logging
- Plugin network send loop
- Plugin network receive loop
- Visual Studio project scaffold
- Exported `OBSEPlugin_Query` / `OBSEPlugin_Load` entry points
- Module-relative config and log file resolution
- Game adapter boundary for local player capture and remote state application
- Main-thread pump scaffold for applying queued remote updates
- Live local player position/rotation/cell/health capture through the xOBSE runtime layout
- Experimental same-cell remote proxy spawning and movement updates through xOBSE console commands
- First-pass host-authoritative quest stage/objective/activation application through xOBSE console commands
- First-pass world-loot transform replay for host-authored world drops
- Session reset on load/main-menu transitions and relay protocol mismatch rejection
- First-pass animation suggestion playback and targeted combat event application with combat-target hints

## What must be added next

## 1. OBSE SDK alignment

The current `plugin/obse/PluginEntrypoint.cpp` now exports the classic OBSE entry points, but it still needs:

- actual OBSE headers
- version checks against the installed game and OBSE runtime
- access to OBSE interfaces beyond the minimal ABI shim used in this repo

## 2. Remote game-thread application

The project now reads live local player state from the actual Oblivion/xOBSE runtime, can spawn/move basic same-cell stand-ins for remote players, and can apply simple host-authored quest stage plus inventory-loot updates.
The next runtime step is hardening those updates so they behave like a co-op feature instead of an engine experiment.

The remaining game-thread work means:

- smoother proxy movement/rotation updates
- more reliable cell-aware spawn/despawn logic
- smoothing and stale-update rejection
- richer weapon/attack event capture instead of the current lightweight combat transitions
- save/load and main-menu reset handling for replicated state

The current build now clears remote proxy and replicated quest/loot state when Oblivion returns to the main menu, exits, initializes, or loads a save. It also disconnects if the relay reports an unexpected protocol version.

Do not read or write game state from an arbitrary background thread. Gather and apply game state through safe hooks or task queues.
The new recurring xOBSE task pump is the intended application point for those updates.

## 3. Remote proxy actors

Incoming `player_state` messages need to map to in-world stand-ins:

- keep the current managed proxy spawn path stable across more cells and saves
- keep a mapping from `player_id` to proxy ref
- smooth movement to reduce jitter
- despawn on disconnect or room change

## 4. Combat model

Do not try to synchronize every physics event.

Use a constrained model:

- local client reports attack intent or hit claim
- host/authority validates it
- resolved damage is then replicated

The current build can now:

- emit lightweight combat enter/leave transitions
- receive targeted `combat_event` damage messages and apply health damage to resolved actor refs

It still does not have authoritative hit detection or robust attacker/weapon validation.

## 5. Quest model

Quest sync is the hardest part and should be opt-in and host-authoritative.

The current implementation now applies `SetStage`, optional objective visibility/completion flags, `SetActiveQuest`, optional quest script lines, and simple complete/fail commands using the incoming `quest_state`. It still does not replicate deeper quest scripts, aliases, or richer branching semantics.

Recommended rules:

- only the host emits `quest_state`
- quest stages only move forward unless a quest explicitly supports rollback
- only a curated allowlist of quests should be synchronized at first
- conflicting quest updates should be logged and rejected

## 6. Loot/world model

The current implementation mirrors loot into the player's inventory with `AddItem` / `RemoveItem` and can replay simple host-authored world-object drops when transform data is present.

To feel like real co-op, the next step is:

- actual world container mutation
- world pickup/removal ownership
- duplicate-prevention across reconnects and replays
- object-level persistence beyond simple inventory mirroring

## 7. Versioning

Before testing with friends, add protocol/build version checks so mismatched clients are rejected early.
