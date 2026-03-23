#!/usr/bin/env python3
"""End-to-end relay/session validation for replay, host authority, and protocol checks."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def now_ms() -> int:
    return int(time.time() * 1000)


def send_json(sock: socket.socket, payload: dict) -> None:
    sock.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))


def recv_line(sock: socket.socket) -> str:
    chunks: list[bytes] = []
    while True:
        chunk = sock.recv(1)
        if not chunk:
            break
        if chunk == b"\n":
            break
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8")


def recv_json(sock: socket.socket) -> dict:
    line = recv_line(sock)
    if not line:
        raise RuntimeError("expected json line, got EOF")
    return json.loads(line)


def build_hello(room: str, sender: str, role: str, protocol_version: int = 1) -> dict:
    return {
        "type": "hello",
        "room": room,
        "sender": sender,
        "timestamp": now_ms(),
        "payload": {
            "build": "session-e2e",
            "protocolVersion": protocol_version,
            "characterName": sender,
            "role": role,
            "token": "",
        },
    }


def wait_for_port(host: str, port: int, timeout_s: float = 10.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"relay did not start on {host}:{port}")


def main() -> None:
    root = Path(__file__).resolve().parent
    relay_path = root / "relay_server.py"
    python_exe = sys.executable
    host = "127.0.0.1"
    port = 7781
    room = "e2e-session"

    with tempfile.TemporaryDirectory(prefix="pseudo-onblivion-e2e-") as temp_dir:
        state_root = Path(temp_dir) / "state"
        relay = subprocess.Popen(
            [
                python_exe,
                str(relay_path),
                "--host",
                host,
                "--port",
                str(port),
                "--state-root",
                str(state_root),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            wait_for_port(host, port)

            with socket.create_connection((host, port), timeout=5) as host_sock:
                send_json(host_sock, build_hello(room, "host-player", "host"))
                host_welcome = recv_json(host_sock)
                assert host_welcome["type"] == "welcome"
                assert host_welcome["payload"]["isHost"] is True

                send_json(
                    host_sock,
                    {
                        "type": "player_state",
                        "room": room,
                        "sender": "host-player",
                        "timestamp": now_ms(),
                        "payload": {
                            "position": {"x": 11.0, "y": 22.0, "z": 33.0},
                            "rotation": {"x": 0.1, "y": 0.2, "z": 0.3},
                            "cell": "ImperialCityMarketDistrict",
                            "isInCombat": True,
                            "health": 91.5,
                            "magicka": 52.0,
                            "stamina": 76.0,
                            "equippedWeaponFormId": "00000D7A",
                            "combatTargetRefId": "0001ABCD",
                            "profile": {
                                "characterName": "Kotchking",
                                "raceFormId": "00000907",
                                "raceName": "Imperial",
                                "classFormId": "0002299C",
                                "className": "Knight",
                                "birthsignFormId": "000224FC",
                                "birthsignName": "The Warrior",
                                "hairFormId": "00090475",
                                "hairName": "Ren's Hair",
                                "eyesFormId": "00027306",
                                "eyesName": "Blue Eyes",
                                "isFemale": False,
                                "scale": 1.05,
                                "hairColorR": 88,
                                "hairColorG": 61,
                                "hairColorB": 44,
                            },
                        },
                    },
                )
                send_json(
                    host_sock,
                    {
                        "type": "quest_state",
                        "room": room,
                        "sender": "host-player",
                        "timestamp": now_ms(),
                        "payload": {
                            "questId": "MQ01",
                            "stage": 30,
                            "status": "running",
                            "objectiveIndex": 10,
                            "objectiveDisplayed": True,
                            "objectiveCompleted": False,
                            "completed": False,
                            "failed": False,
                            "makeActive": True,
                            "scriptLine": "",
                        },
                    },
                )
                send_json(
                    host_sock,
                    {
                        "type": "loot_state",
                        "room": room,
                        "sender": "host-player",
                        "timestamp": now_ms(),
                        "payload": {
                            "lootId": "world-drop-001",
                            "action": "spawn",
                            "formId": "0x000229AA",
                            "containerRefId": "",
                            "itemRefId": "",
                            "cell": "ImperialCityMarketDistrict",
                            "position": {"x": 101.0, "y": 202.0, "z": 303.0},
                            "rotation": {"x": 0.0, "y": 0.0, "z": 1.57},
                            "hasTransform": True,
                            "isWorldObject": True,
                            "count": 1,
                            "removed": False,
                        },
                    },
                )
                send_json(
                    host_sock,
                    {
                        "type": "loot_state",
                        "room": room,
                        "sender": "host-player",
                        "timestamp": now_ms() + 1,
                        "payload": {
                            "lootId": "world-drop-002",
                            "action": "picked_up",
                            "formId": "0x000229AA",
                            "containerRefId": "",
                            "itemRefId": "0x0002BCDE",
                            "cell": "ImperialCityMarketDistrict",
                            "count": 1,
                            "removed": True,
                            "isWorldObject": True,
                        },
                    },
                )

                with socket.create_connection((host, port), timeout=5) as joiner_sock:
                    send_json(joiner_sock, build_hello(room, "joiner-player", "peer"))
                    joiner_welcome = recv_json(joiner_sock)
                    assert joiner_welcome["type"] == "welcome"
                    assert joiner_welcome["payload"]["isHost"] is False

                    replayed_player = recv_json(joiner_sock)
                    replayed_quest = recv_json(joiner_sock)
                    replayed_loot = recv_json(joiner_sock)
                    replayed_loot_removed = recv_json(joiner_sock)
                    assert replayed_player["type"] == "player_state"
                    assert replayed_player["payload"]["magicka"] == 52.0
                    assert replayed_player["payload"]["equippedWeaponFormId"] == "00000D7A"
                    assert replayed_player["payload"]["combatTargetRefId"] == "0001ABCD"
                    assert replayed_player["payload"]["profile"]["characterName"] == "Kotchking"
                    assert replayed_player["payload"]["profile"]["raceName"] == "Imperial"
                    assert replayed_player["payload"]["profile"]["className"] == "Knight"
                    assert replayed_player["payload"]["profile"]["birthsignName"] == "The Warrior"
                    assert replayed_player["payload"]["profile"]["hairFormId"] == "00090475"
                    assert replayed_player["payload"]["profile"]["eyesFormId"] == "00027306"
                    assert replayed_quest["type"] == "quest_state"
                    assert replayed_quest["payload"]["makeActive"] is True
                    assert replayed_loot["type"] == "loot_state"
                    assert replayed_loot["payload"]["isWorldObject"] is True
                    assert replayed_loot["payload"]["position"]["x"] == 101.0
                    assert replayed_loot_removed["type"] == "loot_state"
                    assert replayed_loot_removed["payload"]["removed"] is True
                    assert replayed_loot_removed["payload"]["lootId"] == "world-drop-002"

                    peer_joined = recv_json(host_sock)
                    assert peer_joined["type"] == "peer_joined"
                    assert peer_joined["payload"]["sessionId"] == "joiner-player"

                    send_json(
                        joiner_sock,
                        {
                            "type": "quest_state",
                            "room": room,
                            "sender": "joiner-player",
                            "timestamp": now_ms(),
                            "payload": {
                                "questId": "MQ01",
                                "stage": 999,
                                "status": "broken",
                            },
                        },
                    )
                    host_sock.settimeout(1.0)
                    try:
                        leaked = recv_line(host_sock)
                    except socket.timeout:
                        leaked = ""
                    assert leaked == "", leaked

                    send_json(
                        joiner_sock,
                        {
                            "type": "combat_event",
                            "room": room,
                            "sender": "joiner-player",
                            "timestamp": now_ms(),
                            "payload": {
                                "kind": "weapon_hit",
                                "targetRefId": "0001ABCD",
                                "weaponFormId": "00000D7A",
                                "damage": 25.0,
                            },
                        },
                    )
                    host_sock.settimeout(1.0)
                    try:
                        leaked = recv_line(host_sock)
                    except socket.timeout:
                        leaked = ""
                    assert leaked == "", leaked

                peer_left = recv_json(host_sock)
                assert peer_left["type"] == "peer_left"
                assert peer_left["payload"]["sessionId"] == "joiner-player"

            with socket.create_connection((host, port), timeout=5) as mismatch_sock:
                send_json(mismatch_sock, build_hello(room, "bad-client", "peer", protocol_version=2))
                mismatch_sock.settimeout(1.0)
                closed = recv_line(mismatch_sock)
                assert closed == "", closed

            persisted = json.loads((state_root / f"{room}.json").read_text(encoding="utf-8"))
            assert len(persisted["questStates"]) == 1
            assert len(persisted["lootStates"]) == 2
            persisted_loot = {
                entry["payload"]["lootId"]: entry["payload"] for entry in persisted["lootStates"]
            }
            assert persisted_loot["world-drop-002"]["removed"] is True

            print("session_e2e_test: PASS")
        finally:
            relay.terminate()
            try:
                relay.wait(timeout=5)
            except subprocess.TimeoutExpired:
                relay.kill()
                relay.wait(timeout=5)


if __name__ == "__main__":
    main()
