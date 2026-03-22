#!/usr/bin/env python3
"""Verifies host-authoritative quest and loot state replay for new joiners."""

from __future__ import annotations

import argparse
import json
import socket
import time


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
    return json.loads(recv_line(sock))


def build_hello(room: str, sender: str, role: str) -> dict:
    return {
        "type": "hello",
        "room": room,
        "sender": sender,
        "timestamp": now_ms(),
        "payload": {
            "build": "world-state-smoke",
            "protocolVersion": 1,
            "characterName": sender,
            "role": role,
            "token": "",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pseudo-OnBlivion world-state smoke test")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--room", default="world-state-test")
    args = parser.parse_args()

    with socket.create_connection((args.host, args.port), timeout=5) as host:
        send_json(host, build_hello(args.room, "host-player", "host"))
        welcome = recv_json(host)
        assert welcome["type"] == "welcome"
        assert welcome["payload"]["isHost"] is True

        send_json(
            host,
            {
                "type": "quest_state",
                "room": args.room,
                "sender": "host-player",
                "timestamp": now_ms(),
                "payload": {
                    "questId": "MQ01",
                    "stage": 30,
                    "status": "running",
                },
            },
        )
        send_json(
            host,
            {
                "type": "loot_state",
                "room": args.room,
                "sender": "host-player",
                "timestamp": now_ms(),
                "payload": {
                    "lootId": "crate-001",
                    "action": "spawn",
                    "formId": "0x000229AA",
                    "count": 1,
                },
            },
        )

        with socket.create_connection((args.host, args.port), timeout=5) as joiner:
            send_json(joiner, build_hello(args.room, "joiner-player", "peer"))
            joiner_welcome = recv_json(joiner)
            assert joiner_welcome["type"] == "welcome"
            assert joiner_welcome["payload"]["isHost"] is False

            replayed_quest = recv_json(joiner)
            replayed_loot = recv_json(joiner)
            print(json.dumps(replayed_quest, separators=(",", ":")))
            print(json.dumps(replayed_loot, separators=(",", ":")))

            host_peer_joined = recv_json(host)
            assert host_peer_joined["type"] == "peer_joined"
            assert host_peer_joined["payload"]["sessionId"] == "joiner-player"

            send_json(
                joiner,
                {
                    "type": "quest_state",
                    "room": args.room,
                    "sender": "joiner-player",
                    "timestamp": now_ms(),
                    "payload": {
                        "questId": "MQ01",
                        "stage": 999,
                        "status": "broken",
                    },
                },
            )

            joiner.settimeout(1.0)
            try:
                leaked = recv_line(host)
            except socket.timeout:
                leaked = ""
            assert leaked == "", leaked


if __name__ == "__main__":
    main()
