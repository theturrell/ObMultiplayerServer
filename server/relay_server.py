#!/usr/bin/env python3
"""Stateful dependency-free relay server for the Pseudo-OnBlivion prototype."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 7777,
    "log_level": "INFO",
    "log_file": "relay.log",
    "room_capacity": 8,
    "require_token": False,
    "server_token": "",
    "state_root": "server_state",
    "protocol_version": 1,
    "host_player_id": "",
    "require_host_for_world_state": True,
}

WORLD_STATE_TYPES = {"quest_state", "loot_state"}
AUTHORITATIVE_COMBAT_KINDS = {"weapon_hit", "spell_hit", "damage", "kill"}


def now_ms() -> int:
    return int(time.time() * 1000)


def sanitize_room_name(room: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in room)
    return cleaned or "default"


@dataclass
class ClientSession:
    session_id: str
    room: str
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    metadata: dict[str, Any] = field(default_factory=dict)
    is_host: bool = False

    async def send(self, message: dict[str, Any]) -> None:
        encoded = json.dumps(message, separators=(",", ":")) + "\n"
        self.writer.write(encoded.encode("utf-8"))
        await self.writer.drain()


@dataclass
class RoomState:
    room: str
    host_session_id: str | None = None
    player_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    quest_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    loot_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    updated_at: int = field(default_factory=now_ms)

    def to_json(self) -> dict[str, Any]:
        return {
            "room": self.room,
            "hostSessionId": self.host_session_id,
            "updatedAt": self.updated_at,
            "playerStates": list(self.player_states.values()),
            "questStates": list(self.quest_states.values()),
            "lootStates": list(self.loot_states.values()),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "RoomState":
        room = str(payload.get("room", "session-1"))
        state = cls(room=room)
        state.host_session_id = payload.get("hostSessionId")
        state.updated_at = int(payload.get("updatedAt", now_ms()))
        for message in payload.get("playerStates", []):
            if isinstance(message, dict):
                sender = str(message.get("sender", ""))
                if sender:
                    state.player_states[sender] = message
        for message in payload.get("questStates", []):
            if isinstance(message, dict):
                quest_id = str(message.get("payload", {}).get("questId", ""))
                if quest_id:
                    state.quest_states[quest_id] = message
        for message in payload.get("lootStates", []):
            if isinstance(message, dict):
                loot_id = str(message.get("payload", {}).get("lootId", ""))
                if loot_id:
                    state.loot_states[loot_id] = message
        return state


class RelayServer:
    def __init__(
        self,
        room_capacity: int,
        require_token: bool,
        server_token: str,
        state_root: str,
        protocol_version: int,
        host_player_id: str,
        require_host_for_world_state: bool,
    ) -> None:
        self.rooms: dict[str, dict[str, ClientSession]] = {}
        self.room_states: dict[str, RoomState] = {}
        self.room_capacity = room_capacity
        self.require_token = require_token
        self.server_token = server_token
        self.protocol_version = protocol_version
        self.host_player_id = host_player_id
        self.require_host_for_world_state = require_host_for_world_state
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._load_existing_room_states()

    async def handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        logging.info("Connection opened from %s", peer)
        session: ClientSession | None = None

        try:
            hello = await self._read_message(reader)
            session = self._register_client(hello, reader, writer)
            await session.send(
                {
                    "type": "welcome",
                    "room": session.room,
                    "sender": "server",
                    "timestamp": now_ms(),
                    "payload": {
                        "sessionId": session.session_id,
                        "peers": [
                            client_id
                            for client_id in self.rooms[session.room]
                            if client_id != session.session_id
                        ],
                        "protocolVersion": self.protocol_version,
                        "isHost": session.is_host,
                    },
                }
            )

            await self._sync_room_state_to_client(session)

            await self._broadcast(
                session.room,
                {
                    "type": "peer_joined",
                    "room": session.room,
                    "sender": "server",
                    "timestamp": now_ms(),
                    "payload": {
                        "sessionId": session.session_id,
                        "isHost": session.is_host,
                    },
                },
                exclude={session.session_id},
            )

            while True:
                message = await self._read_message(reader)
                if message["room"] != session.room:
                    logging.warning(
                        "Dropping cross-room message from %s: %s",
                        session.session_id,
                        message,
                    )
                    continue
                if not self._validate_client_message(session, message):
                    continue
                await self._process_client_message(session, message)
        except asyncio.IncompleteReadError:
            logging.info("Connection closed by peer %s", peer)
        except ConnectionResetError:
            logging.info("Connection reset by peer %s", peer)
        except ValueError as exc:
            logging.warning("Protocol error from %s: %s", peer, exc)
        finally:
            if session is not None:
                await self._unregister_client(session)
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def _read_message(self, reader: asyncio.StreamReader) -> dict[str, Any]:
        raw = await reader.readline()
        if not raw:
            raise asyncio.IncompleteReadError(partial=b"", expected=1)
        try:
            message = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json: {exc}") from exc

        if not isinstance(message, dict):
            raise ValueError("message must be an object")

        required = {"type", "room", "sender", "timestamp", "payload"}
        missing = required.difference(message)
        if missing:
            raise ValueError(f"message missing keys: {sorted(missing)}")

        if not isinstance(message["payload"], dict):
            raise ValueError("payload must be an object")

        return message

    def _register_client(
        self,
        hello: dict[str, Any],
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> ClientSession:
        if hello["type"] != "hello":
            raise ValueError("first message must be hello")

        room = str(hello["room"])
        session_id = str(hello["sender"])
        metadata = hello.get("payload", {})
        room_clients = self.rooms.setdefault(room, {})
        room_state = self.room_states.setdefault(room, RoomState(room=room))
        token = ""
        if isinstance(metadata, dict):
            token = str(metadata.get("token", ""))

        if self.require_token and token != self.server_token:
            raise ValueError("invalid server token")

        if len(room_clients) >= self.room_capacity:
            raise ValueError(f"room is full: capacity={self.room_capacity}")

        if session_id in room_clients:
            raise ValueError(f"duplicate session id in room: {session_id}")

        claimed_host = False
        claimed_protocol_version = self.protocol_version
        if isinstance(metadata, dict):
            claimed_host = str(metadata.get("role", "")).lower() == "host"
            claimed_protocol_version = int(metadata.get("protocolVersion", self.protocol_version))

        if claimed_protocol_version != self.protocol_version:
            raise ValueError(
                f"protocol mismatch: client={claimed_protocol_version} server={self.protocol_version}"
            )

        if self.host_player_id and session_id == self.host_player_id:
            room_state.host_session_id = session_id
        elif room_state.host_session_id is None and claimed_host:
            room_state.host_session_id = session_id

        session = ClientSession(
            session_id=session_id,
            room=room,
            reader=reader,
            writer=writer,
            metadata=metadata if isinstance(metadata, dict) else {},
            is_host=(room_state.host_session_id == session_id),
        )
        room_clients[session_id] = session
        room_state.updated_at = now_ms()
        self._save_room_state(room_state)
        logging.info("Registered %s in room %s (host=%s)", session_id, room, session.is_host)
        return session

    async def _unregister_client(self, session: ClientSession) -> None:
        room_clients = self.rooms.get(session.room, {})
        removed = room_clients.pop(session.session_id, None)
        if removed is None:
            return

        room_state = self.room_states.setdefault(session.room, RoomState(room=session.room))
        room_state.player_states.pop(session.session_id, None)
        if room_state.host_session_id == session.session_id:
            room_state.host_session_id = self._choose_next_host(room_clients)
            for peer in room_clients.values():
                peer.is_host = peer.session_id == room_state.host_session_id
        room_state.updated_at = now_ms()
        self._save_room_state(room_state)

        logging.info("Unregistered %s from room %s", session.session_id, session.room)
        if not room_clients:
            self.rooms.pop(session.room, None)
        else:
            await self._broadcast(
                session.room,
                {
                    "type": "peer_left",
                    "room": session.room,
                    "sender": "server",
                    "timestamp": now_ms(),
                    "payload": {
                        "sessionId": session.session_id,
                        "nextHostSessionId": room_state.host_session_id,
                    },
                },
                exclude={session.session_id},
            )

    async def _process_client_message(
        self,
        session: ClientSession,
        message: dict[str, Any],
    ) -> None:
        room_state = self.room_states.setdefault(session.room, RoomState(room=session.room))
        message_type = str(message["type"])

        if message_type == "player_state":
            room_state.player_states[session.session_id] = message
        elif message_type == "quest_state":
            quest_id = str(message["payload"].get("questId", ""))
            if not quest_id:
                logging.warning("Dropping quest_state without questId from %s", session.session_id)
                return
            room_state.quest_states[quest_id] = message
        elif message_type == "loot_state":
            loot_id = str(message["payload"].get("lootId", ""))
            if not loot_id:
                logging.warning("Dropping loot_state without lootId from %s", session.session_id)
                return
            room_state.loot_states[loot_id] = message

        room_state.updated_at = now_ms()
        self._save_room_state(room_state)
        await self._broadcast(session.room, message, exclude={session.session_id})

    def _validate_client_message(self, session: ClientSession, message: dict[str, Any]) -> bool:
        if str(message.get("sender")) != session.session_id:
            logging.warning(
                "Dropping spoofed sender message from %s: %s",
                session.session_id,
                message,
            )
            return False

        message_type = str(message.get("type", ""))
        if message_type in WORLD_STATE_TYPES and self.require_host_for_world_state and not session.is_host:
            logging.warning(
                "Rejecting non-host %s message from %s",
                message_type,
                session.session_id,
            )
            return False

        if message_type == "combat_event":
            payload = message.get("payload", {})
            kind = str(payload.get("kind", "")).lower()
            damage = float(payload.get("damage", 0) or 0)
            if (
                self.require_host_for_world_state
                and not session.is_host
                and (kind in AUTHORITATIVE_COMBAT_KINDS or damage > 0)
            ):
                logging.warning(
                    "Rejecting non-host authoritative combat_event from %s: kind=%s damage=%s",
                    session.session_id,
                    kind,
                    damage,
                )
                return False

        return True

    async def _sync_room_state_to_client(self, session: ClientSession) -> None:
        room_state = self.room_states.get(session.room)
        if room_state is None:
            return

        for sender, message in room_state.player_states.items():
            if sender == session.session_id:
                continue
            await session.send(message)

        for message in room_state.quest_states.values():
            await session.send(message)

        for message in room_state.loot_states.values():
            await session.send(message)

    def _choose_next_host(self, room_clients: dict[str, ClientSession]) -> str | None:
        if self.host_player_id and self.host_player_id in room_clients:
            return self.host_player_id
        for session_id, session in room_clients.items():
            if str(session.metadata.get("role", "")).lower() == "host":
                return session_id
        return None

    async def _broadcast(
        self, room: str, message: dict[str, Any], exclude: set[str] | None = None
    ) -> None:
        exclude = exclude or set()
        clients = self.rooms.get(room, {})
        dead_sessions: list[str] = []

        for session_id, session in clients.items():
            if session_id in exclude:
                continue
            try:
                await session.send(message)
            except ConnectionError:
                dead_sessions.append(session_id)

        for session_id in dead_sessions:
            stale = clients.pop(session_id, None)
            if stale is not None:
                stale.writer.close()
                try:
                    await stale.writer.wait_closed()
                except ConnectionError:
                    pass

    def _state_path(self, room: str) -> Path:
        return self.state_root / f"{sanitize_room_name(room)}.json"

    def _save_room_state(self, state: RoomState) -> None:
        path = self._state_path(state.room)
        path.write_text(json.dumps(state.to_json(), separators=(",", ":"), indent=2), encoding="utf-8")

    def _load_existing_room_states(self) -> None:
        for path in self.state_root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    state = RoomState.from_json(payload)
                    self.room_states[state.room] = state
            except Exception as exc:  # pragma: no cover - best effort state recovery
                logging.warning("Failed to load room state from %s: %s", path, exc)


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    for signame in ("SIGINT", "SIGTERM"):
        if not hasattr(signal, signame):
            continue
        try:
            loop.add_signal_handler(getattr(signal, signame), stop_event.set)
        except NotImplementedError:
            logging.debug("Signal handlers are not supported by this event loop")
            return


def load_config(config_path: str | None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if not config_path:
        return config

    with open(config_path, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)

    if not isinstance(loaded, dict):
        raise ValueError("config file must contain a JSON object")

    config.update(loaded)
    return config


async def run_server(config: dict[str, Any]) -> None:
    relay = RelayServer(
        room_capacity=int(config["room_capacity"]),
        require_token=bool(config["require_token"]),
        server_token=str(config["server_token"]),
        state_root=str(config["state_root"]),
        protocol_version=int(config["protocol_version"]),
        host_player_id=str(config["host_player_id"]),
        require_host_for_world_state=bool(config["require_host_for_world_state"]),
    )
    server = await asyncio.start_server(
        relay.handle_connection,
        str(config["host"]),
        int(config["port"]),
        family=socket.AF_INET,
        reuse_address=True,
    )
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    logging.info("Relay listening on %s", sockets)

    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)

    async with server:
        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            logging.info("Shutdown requested from console")
        finally:
            server.close()
            await server.wait_closed()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pseudo-OnBlivion relay server")
    parser.add_argument("--config", help="Optional JSON config file")
    parser.add_argument("--host", help="Host interface to bind")
    parser.add_argument("--port", type=int, help="TCP port to bind")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Verbosity level",
    )
    parser.add_argument("--log-file", help="Optional log file path")
    parser.add_argument(
        "--room-capacity",
        type=int,
        help="Documented multiplayer target size",
    )
    parser.add_argument(
        "--require-token",
        action="store_true",
        help="Reject clients whose hello payload token does not match server_token",
    )
    parser.add_argument("--server-token", help="Shared token for private sessions")
    parser.add_argument("--state-root", help="Directory used for persisted room state")
    parser.add_argument("--protocol-version", type=int, help="Protocol version exposed to clients")
    parser.add_argument("--host-player-id", help="Force a specific player id to own world-state writes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    for key in (
        "host",
        "port",
        "log_level",
        "log_file",
        "room_capacity",
        "server_token",
        "state_root",
        "protocol_version",
        "host_player_id",
    ):
        cli_value = getattr(args, key, None)
        if cli_value is not None:
            config[key] = cli_value
    if args.require_token:
        config["require_token"] = True

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_file = str(config.get("log_file", "")).strip()
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, str(config["log_level"])),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )
    logging.info("Configured target room capacity: %s", config["room_capacity"])
    logging.info(
        "Private session mode: %s",
        "enabled" if config["require_token"] else "disabled",
    )
    logging.info(
        "World-state host authority: %s",
        "required" if config["require_host_for_world_state"] else "disabled",
    )
    try:
        asyncio.run(run_server(config))
    except KeyboardInterrupt:
        logging.info("Shutdown requested")


if __name__ == "__main__":
    main()
