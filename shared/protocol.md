# Protocol Notes

Messages are newline-delimited JSON objects.

Each payload contains:

- `type`: message type identifier
- `room`: logical session key
- `sender`: player/session id
- `timestamp`: unix milliseconds
- `payload`: type-specific data

## Handshake

### Client -> Server

```json
{
  "type": "hello",
  "room": "session-1",
  "sender": "player-a",
  "timestamp": 1710000000000,
  "payload": {
    "build": "pseudo-onblivion-dev",
    "protocolVersion": 1,
    "characterName": "HeroOfKvatch",
    "role": "host"
  }
}
```

### Server -> Client

```json
{
  "type": "welcome",
  "room": "session-1",
  "sender": "server",
  "timestamp": 1710000000001,
  "payload": {
    "sessionId": "player-a",
    "peers": ["player-b"],
    "protocolVersion": 1,
    "isHost": true
  }
}
```

## Player State

```json
{
  "type": "player_state",
  "room": "session-1",
  "sender": "player-a",
  "timestamp": 1710000000100,
  "payload": {
    "position": { "x": 1.0, "y": 2.0, "z": 3.0 },
    "rotation": { "x": 0.0, "y": 0.0, "z": 90.0 },
    "cell": "ImperialCityMarketDistrict",
    "isInCombat": false,
    "health": 95.0,
    "magicka": 60.0,
    "stamina": 80.0,
    "equippedWeaponFormId": "",
    "combatTargetRefId": "0001ABCD"
  }
}
```

## Combat Event

```json
{
  "type": "combat_event",
  "room": "session-1",
  "sender": "player-a",
  "timestamp": 1710000000200,
  "payload": {
    "kind": "weapon_hit",
    "targetRefId": "0x0001ABCD",
    "weaponFormId": "0x00000D7A",
    "damage": 12.0
  }
}
```

Current implementation notes:

- `enter_combat` / `leave_combat` are lightweight state transitions emitted from local combat state changes
- the plugin now includes the current combat target id in both `player_state` and lightweight combat transition messages when it can resolve one
- `weapon_hit` is supported on the receive side if a concrete `targetRefId` and `damage` are provided
- the plugin can now apply damage directly to resolved actor refs when the relay delivers a targeted hit event

## Animation Event

```json
{
  "type": "animation_event",
  "room": "session-1",
  "sender": "player-a",
  "timestamp": 1710000000250,
  "payload": {
    "group": "Forward",
    "loop": true
  }
}
```

The current plugin derives these as lightweight animation suggestions from movement/combat state changes and plays them on remote stand-ins.

## Quest State

Quest synchronization should be sparse, explicit, and host-authoritative.

```json
{
  "type": "quest_state",
  "room": "session-1",
  "sender": "host-player",
  "timestamp": 1710000000300,
  "payload": {
    "questId": "MQ01",
    "stage": 30,
    "status": "running",
    "objectiveIndex": 10,
    "objectiveDisplayed": true,
    "objectiveCompleted": false,
    "completed": false,
    "failed": false,
    "makeActive": true,
    "scriptLine": "",
    "objectiveFlags": {
      "heardRumor": true,
      "enteredSewer": false
    }
  }
}
```

New joiners receive the latest persisted `quest_state` messages after `welcome`.

## Loot State

Loot synchronization is also host-authoritative and persisted by the relay so late joiners inherit the current room view.

```json
{
  "type": "loot_state",
  "room": "session-1",
  "sender": "host-player",
  "timestamp": 1710000000400,
  "payload": {
    "lootId": "crate-001",
    "action": "spawn",
    "formId": "0x000229AA",
    "containerRefId": "0x0001ABCD",
    "itemRefId": "0x0002BCDE",
    "cell": "ImperialCityMarketDistrict",
    "position": { "x": 100.0, "y": 200.0, "z": 300.0 },
    "rotation": { "x": 0.0, "y": 0.0, "z": 1.57 },
    "isWorldObject": true,
    "count": 1,
    "removed": false
  }
}
```

`containerRefId` and `itemRefId` are optional fields used by the current plugin to target a specific in-world container or disable a picked-up world item when enough identity data is available. If a loot payload carries a transform and `isWorldObject`, the current plugin can also replay a simple host-authored world drop in the local cell.
