#!/usr/bin/env python3
"""Verifies that two clients can join a room and receive relayed player_state traffic."""

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


def build_hello(room: str, sender: str) -> dict:
    return {
        "type": "hello",
        "room": room,
        "sender": sender,
        "timestamp": now_ms(),
        "payload": {
            "build": "fanout-smoke",
            "characterName": sender,
        },
    }


def build_player_state(room: str, sender: str) -> dict:
    return {
        "type": "player_state",
        "room": room,
        "sender": sender,
        "timestamp": now_ms(),
        "payload": {
            "position": {"x": 1.0, "y": 2.0, "z": 3.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 90.0},
            "cell": "ImperialCityMarketDistrict",
            "isInCombat": False,
            "health": 87.5,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pseudo-OnBlivion relay fan-out smoke test")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--room", default="session-1")
    args = parser.parse_args()

    with socket.create_connection((args.host, args.port), timeout=5) as client_a:
        with socket.create_connection((args.host, args.port), timeout=5) as client_b:
            send_json(client_a, build_hello(args.room, "client-a"))
            send_json(client_b, build_hello(args.room, "client-b"))

            print(recv_line(client_a))
            print(recv_line(client_b))
            print(recv_line(client_a))

            send_json(client_a, build_player_state(args.room, "client-a"))
            forwarded = recv_line(client_b)
            print(forwarded)


if __name__ == "__main__":
    main()
