#!/usr/bin/env python3
"""Tiny relay smoke test client for local validation."""

from __future__ import annotations

import argparse
import json
import socket
import time


def now_ms() -> int:
    return int(time.time() * 1000)


def send_json(sock: socket.socket, message: dict) -> None:
    payload = json.dumps(message, separators=(",", ":")) + "\n"
    sock.sendall(payload.encode("utf-8"))


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Pseudo-OnBlivion relay smoke test")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--room", default="session-1")
    parser.add_argument("--sender", default="smoke-test")
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        send_json(
            sock,
            {
                "type": "hello",
                "room": args.room,
                "sender": args.sender,
                "timestamp": now_ms(),
                "payload": {
                    "build": "smoke-test",
                    "characterName": "Verifier",
                    "token": args.token,
                },
            },
        )
        welcome = recv_line(sock)
        print(welcome)


if __name__ == "__main__":
    main()
