from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_NAME = "Pseudo-OnBlivion Host"
DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_PORT = "7777"
DEFAULT_ROOM = "session-1"
DEFAULT_PLAYER_ID = "host-player"
DEFAULT_CHARACTER_NAME = "HostHero"
DEFAULT_TOKEN = "change-me"
DEFAULT_SEND_INTERVAL_MS = "100"
DEFAULT_LOG_LEVEL = "INFO"
APP_PROTOCOL_VERSION = "1"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def support_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()

    def add(candidate: Path) -> None:
        resolved = candidate.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        roots.append(resolved)

    base = app_root()
    add(base)
    for parent in base.parents:
        add(parent)
    return roots


def locate_path(*relative_parts: str) -> Path:
    for root in support_roots():
        candidate = root.joinpath(*relative_parts)
        if candidate.exists():
            return candidate
    return app_root().joinpath(*relative_parts)


def settings_path() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home()))
    root = appdata / "PseudoOnBlivion"
    root.mkdir(parents=True, exist_ok=True)
    return root / "host_settings.json"


def support_plugin_dir() -> Path:
    candidates = [
        locate_path("Data", "OBSE", "Plugins"),
        locate_path("plugin", "dist", "Data", "OBSE", "Plugins"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def scripts_dir() -> Path:
    candidates = [
        locate_path("scripts"),
        locate_path("plugin"),
        locate_path("server"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def server_dir() -> Path:
    return locate_path("server")


def common_oblivion_paths() -> list[Path]:
    return [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam" / "steamapps" / "common" / "Oblivion",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam" / "steamapps" / "common" / "Oblivion",
        Path(r"C:\GOG Games\Oblivion"),
        Path(r"C:\Games\Oblivion"),
    ]


def steam_libraryfolders_paths() -> list[Path]:
    candidates = []
    steam_roots = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
    ]
    pattern = re.compile(r'"path"\s*"([^"]+)"')

    for steam_root in steam_roots:
        library_file = steam_root / "steamapps" / "libraryfolders.vdf"
        if not library_file.exists():
            continue
        try:
            content = library_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for raw_path in pattern.findall(content):
            library_root = Path(raw_path.replace("\\\\", "\\"))
            candidates.append(library_root / "steamapps" / "common" / "Oblivion")

    return candidates


def detect_game_path() -> Path | None:
    for candidate in [*common_oblivion_paths(), *steam_libraryfolders_paths()]:
        if (candidate / "Oblivion.exe").exists():
            return candidate
    return None


def local_ipv4_candidates() -> list[str]:
    results: list[str] = []
    try:
        hostname = socket.gethostname()
        for entry in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            address = entry[4][0]
            if address.startswith("127."):
                continue
            if address not in results:
                results.append(address)
    except OSError:
        pass
    return results


def powershell_command(script_name: str, game_path: Path) -> list[str]:
    script_path = resolve_script_path(script_name)
    return [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-GamePath",
        str(game_path),
    ]


def resolve_script_path(script_name: str) -> Path:
    candidates = [
        scripts_dir() / script_name,
        server_dir() / script_name,
        locate_path("plugin") / script_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def plugin_ini_text(values: dict[str, str | bool]) -> str:
    return "\n".join(
        [
            "[network]",
            "server_host=127.0.0.1",
            f"server_port={values['server_port']}",
            f"room={values['room']}",
            f"player_id={values['player_id']}",
            f"character_name={values['character_name']}",
            "host_authority=true",
            f"server_token={values['server_token']}",
            f"send_interval_ms={values['send_interval_ms']}",
            "",
            "[logging]",
            "log_path=PseudoOnBlivion.log",
            "",
        ]
    )


def relay_config_text(values: dict[str, str | bool]) -> str:
    payload = {
        "host": values["bind_host"],
        "port": int(values["server_port"]),
        "log_level": values["log_level"],
        "log_file": str(server_dir() / "relay.log"),
        "room_capacity": 8,
        "require_token": bool(values["require_token"]),
        "server_token": values["server_token"],
        "state_root": str(app_root() / "server_state"),
        "protocol_version": int(APP_PROTOCOL_VERSION),
        "host_player_id": values["player_id"],
        "require_host_for_world_state": True,
    }
    return json.dumps(payload, indent=2)


class HostApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("860x680")
        self.root.minsize(760, 620)

        self.queue: Queue[tuple[str, str]] = Queue()
        self.busy = False
        self.relay_process: subprocess.Popen[str] | None = None

        self.bind_host_var = tk.StringVar(value=DEFAULT_BIND_HOST)
        self.server_port_var = tk.StringVar(value=DEFAULT_PORT)
        self.room_var = tk.StringVar(value=DEFAULT_ROOM)
        self.player_id_var = tk.StringVar(value=DEFAULT_PLAYER_ID)
        self.character_name_var = tk.StringVar(value=DEFAULT_CHARACTER_NAME)
        self.server_token_var = tk.StringVar(value=DEFAULT_TOKEN)
        self.game_path_var = tk.StringVar()
        self.send_interval_var = tk.StringVar(value=DEFAULT_SEND_INTERVAL_MS)
        self.log_level_var = tk.StringVar(value=DEFAULT_LOG_LEVEL)
        self.require_token_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Configure the host session, then start the relay and launch the game.")
        self.friend_info_var = tk.StringVar(value="")

        self.configure_style()
        self.build_ui()
        self.load_settings()
        self.autodetect_game_path()
        self.refresh_friend_info()
        self.root.after(150, self.poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def configure_style(self) -> None:
        self.root.configure(bg="#ece7de")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Root.TFrame", background="#ece7de")
        style.configure("Card.TFrame", background="#fffaf4", relief="flat")
        style.configure("Title.TLabel", font=("Georgia", 22, "bold"), foreground="#2c241b", background="#ece7de")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground="#5f5347", background="#ece7de")
        style.configure("Section.TLabel", font=("Segoe UI Semibold", 11), foreground="#31281f", background="#fffaf4")
        style.configure("Field.TLabel", font=("Segoe UI", 10), foreground="#473b30", background="#fffaf4")
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 10))
        style.configure("Secondary.TButton", font=("Segoe UI", 10))
        style.configure("TEntry", padding=7)

    def build_ui(self) -> None:
        root_frame = ttk.Frame(self.root, style="Root.TFrame", padding=18)
        root_frame.pack(fill="both", expand=True)

        ttk.Label(root_frame, text="Pseudo-OnBlivion Host", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root_frame,
            text="One place for the relay, host plugin config, helper scripts, and launching Oblivion through xOBSE.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 6))
        ttk.Label(
            root_frame,
            text=f"Protocol {APP_PROTOCOL_VERSION}  |  Host authority enabled",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 14))

        card = ttk.Frame(root_frame, style="Card.TFrame", padding=18)
        card.pack(fill="both", expand=True)
        for column in range(3):
            card.columnconfigure(column, weight=1 if column == 1 else 0)

        ttk.Label(card, text="Relay Settings", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.add_field(card, 1, "Bind host", self.bind_host_var, "Usually 0.0.0.0 for friends, 127.0.0.1 for solo local")
        self.add_field(card, 2, "Port", self.server_port_var, "Usually 7777", width=18)
        self.add_field(card, 3, "Room", self.room_var, "Friends must use this exact room name")
        self.add_field(card, 4, "Host player id", self.player_id_var, "Used for host authority inside the relay")
        self.add_field(card, 5, "Character name", self.character_name_var, "Shown in the multiplayer session")
        self.add_field(card, 6, "Shared token", self.server_token_var, "Give this to friends if private sessions are enabled")

        advanced = ttk.LabelFrame(card, text="Advanced", padding=12)
        advanced.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        advanced.columnconfigure(1, weight=1)
        ttk.Label(advanced, text="Send interval (ms)", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(advanced, textvariable=self.send_interval_var, width=12).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(advanced, text="Relay log level", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(advanced, textvariable=self.log_level_var, values=["DEBUG", "INFO", "WARNING", "ERROR"], width=12, state="readonly").grid(row=1, column=1, sticky="w", pady=4)
        ttk.Checkbutton(advanced, text="Require shared token for joiners", variable=self.require_token_var, command=self.refresh_friend_info).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Label(card, text="Game Folder", style="Section.TLabel").grid(row=8, column=0, columnspan=3, sticky="w", pady=(16, 0))
        game_row = ttk.Frame(card, style="Card.TFrame")
        game_row.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        game_row.columnconfigure(0, weight=1)
        ttk.Entry(game_row, textvariable=self.game_path_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(game_row, text="Browse", style="Secondary.TButton", command=self.choose_game_path).grid(row=0, column=1, padx=(10, 0))
        ttk.Button(game_row, text="Detect", style="Secondary.TButton", command=self.autodetect_game_path).grid(row=0, column=2, padx=(10, 0))

        ttk.Label(card, text="Friend Info", style="Section.TLabel").grid(row=10, column=0, columnspan=3, sticky="w", pady=(16, 0))
        friend_card = tk.Label(
            card,
            textvariable=self.friend_info_var,
            bg="#f4ead8",
            fg="#3f352b",
            justify="left",
            anchor="w",
            padx=14,
            pady=12,
            font=("Consolas", 10),
            wraplength=760,
        )
        friend_card.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(22, 0))
        ttk.Button(actions, text="Run Check", style="Secondary.TButton", command=self.run_preflight).pack(side="left")
        ttk.Button(actions, text="Install xOBSE", style="Secondary.TButton", command=self.install_xobse).pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Open Firewall", style="Secondary.TButton", command=self.open_firewall).pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Save Settings", style="Secondary.TButton", command=self.save_settings_only).pack(side="left", padx=(10, 0))

        relay_row = ttk.Frame(card, style="Card.TFrame")
        relay_row.grid(row=13, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(relay_row, text="Start Relay", style="Secondary.TButton", command=self.start_relay).pack(side="left")
        ttk.Button(relay_row, text="Stop Relay", style="Secondary.TButton", command=self.stop_relay).pack(side="left", padx=(10, 0))
        ttk.Button(relay_row, text="Host Session", style="Primary.TButton", command=self.host_session).pack(side="right")
        ttk.Button(relay_row, text="Launch Game", style="Secondary.TButton", command=self.launch_game_only).pack(side="right", padx=(10, 0))

        status_frame = ttk.Frame(root_frame, padding=14, style="Root.TFrame")
        status_frame.pack(fill="x", pady=(14, 0))
        status_card = tk.Label(
            status_frame,
            textvariable=self.status_var,
            bg="#efe4d1",
            fg="#3f352b",
            justify="left",
            anchor="w",
            padx=14,
            pady=12,
            font=("Segoe UI", 10),
            wraplength=780,
        )
        status_card.pack(fill="x")

    def add_field(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, hint: str, width: int | None = None) -> None:
        ttk.Label(parent, text=label, style="Field.TLabel").grid(row=row, column=0, sticky="w", pady=(10, 0))
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=1, sticky="ew", pady=(10, 0), padx=(12, 0))
        ttk.Label(parent, text=hint, style="Field.TLabel").grid(row=row, column=2, sticky="w", pady=(10, 0), padx=(12, 0))

    def load_settings(self) -> None:
        path = settings_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        self.bind_host_var.set(data.get("bind_host", DEFAULT_BIND_HOST))
        self.server_port_var.set(data.get("server_port", DEFAULT_PORT))
        self.room_var.set(data.get("room", DEFAULT_ROOM))
        self.player_id_var.set(data.get("player_id", DEFAULT_PLAYER_ID))
        self.character_name_var.set(data.get("character_name", DEFAULT_CHARACTER_NAME))
        self.server_token_var.set(data.get("server_token", DEFAULT_TOKEN))
        self.game_path_var.set(data.get("game_path", ""))
        self.send_interval_var.set(data.get("send_interval_ms", DEFAULT_SEND_INTERVAL_MS))
        self.log_level_var.set(data.get("log_level", DEFAULT_LOG_LEVEL))
        self.require_token_var.set(bool(data.get("require_token", False)))

    def save_settings(self) -> None:
        values = self.current_values()
        settings_path().write_text(json.dumps(values, indent=2), encoding="utf-8")

    def save_settings_only(self) -> None:
        error = self.validate_inputs()
        if error:
            messagebox.showerror(APP_NAME, error)
            return
        self.write_runtime_files(self.current_values())
        self.save_settings()
        self.status_var.set("Host settings saved. You can now start the relay or host the session.")

    def autodetect_game_path(self) -> None:
        detected = detect_game_path()
        if detected is not None:
            self.game_path_var.set(str(detected))

    def choose_game_path(self) -> None:
        current = self.game_path_var.get().strip() or str(Path.home())
        chosen = filedialog.askdirectory(title="Choose your Oblivion folder", initialdir=current)
        if chosen:
            self.game_path_var.set(chosen)

    def current_values(self) -> dict[str, str | bool]:
        return {
            "bind_host": self.bind_host_var.get().strip() or DEFAULT_BIND_HOST,
            "server_port": self.server_port_var.get().strip() or DEFAULT_PORT,
            "room": self.room_var.get().strip() or DEFAULT_ROOM,
            "player_id": self.player_id_var.get().strip() or DEFAULT_PLAYER_ID,
            "character_name": self.character_name_var.get().strip() or DEFAULT_CHARACTER_NAME,
            "server_token": self.server_token_var.get().strip() or DEFAULT_TOKEN,
            "game_path": self.game_path_var.get().strip(),
            "send_interval_ms": self.send_interval_var.get().strip() or DEFAULT_SEND_INTERVAL_MS,
            "log_level": self.log_level_var.get().strip() or DEFAULT_LOG_LEVEL,
            "require_token": self.require_token_var.get(),
        }

    def validate_inputs(self) -> str | None:
        values = self.current_values()
        if not values["game_path"]:
            return "Choose the Oblivion installation folder first."
        game_path = Path(str(values["game_path"]))
        if not (game_path / "Oblivion.exe").exists():
            return "The selected game folder does not contain Oblivion.exe."
        if not support_plugin_dir().exists():
            return "The bundled plugin files are missing from this host install."
        try:
            int(str(values["server_port"]))
        except ValueError:
            return "Port must be a number."
        try:
            int(str(values["send_interval_ms"]))
        except ValueError:
            return "Send interval must be a number."
        if not str(values["room"]).strip():
            return "Room name cannot be empty."
        return None

    def refresh_friend_info(self) -> None:
        ips = local_ipv4_candidates()
        address = ", ".join(ips) if ips else "Use your Tailscale IP or public IP"
        token_line = str(self.server_token_var.get().strip() or DEFAULT_TOKEN) if self.require_token_var.get() else "(not required)"
        self.friend_info_var.set(
            "\n".join(
                [
                    f"Address to give friends: {address}",
                    f"Port: {self.server_port_var.get().strip() or DEFAULT_PORT}",
                    f"Room: {self.room_var.get().strip() or DEFAULT_ROOM}",
                    f"Token: {token_line}",
                ]
            )
        )

    def relay_executable(self) -> Path | None:
        for exe in (
            server_dir() / "PseudoOnBlivionRelay.exe",
            server_dir() / "dist" / "PseudoOnBlivionRelay.exe",
        ):
            if exe.exists():
                return exe
        return None

    def relay_config_path(self) -> Path:
        return server_dir() / "relay_config.json"

    def write_runtime_files(self, values: dict[str, str | bool]) -> None:
        server_dir().mkdir(parents=True, exist_ok=True)
        self.relay_config_path().write_text(relay_config_text(values), encoding="utf-8")

        game_path = Path(str(values["game_path"]))
        plugin_target = game_path / "Data" / "OBSE" / "Plugins"
        plugin_target.mkdir(parents=True, exist_ok=True)

        for source in support_plugin_dir().iterdir():
            if source.name.lower() == "pseudoonblivion.ini":
                continue
            if source.is_file():
                shutil.copy2(source, plugin_target / source.name)

        (plugin_target / "PseudoOnBlivion.ini").write_text(plugin_ini_text(values), encoding="utf-8")

    def run_background(self, label: str, work: Callable[[], None]) -> None:
        if self.busy:
            return
        self.busy = True
        self.status_var.set(label)

        def runner() -> None:
            try:
                work()
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("error", str(exc)))
            else:
                self.queue.put(("done", "Done."))

        threading.Thread(target=runner, daemon=True).start()

    def poll_queue(self) -> None:
        try:
            while True:
                kind, message = self.queue.get_nowait()
                if kind == "status":
                    self.status_var.set(message)
                elif kind == "error":
                    self.busy = False
                    self.status_var.set(message)
                    messagebox.showerror(APP_NAME, message)
                elif kind == "done":
                    self.busy = False
                    self.status_var.set(message)
        except Empty:
            pass
        self.refresh_friend_info()
        self.root.after(150, self.poll_queue)

    def post_status(self, text: str) -> None:
        self.queue.put(("status", text))

    def ensure_xobse(self, game_path: Path) -> None:
        if (game_path / "xOBSE_loader.exe").exists() or (game_path / "obse_loader.exe").exists():
            return
        raise RuntimeError("xOBSE is not installed yet. Press Install xOBSE first.")

    def build_preflight_report(self, values: dict[str, str | bool]) -> str:
        game_path = Path(str(values["game_path"]))
        relay_exe = self.relay_executable()
        lines: list[str] = [f"Game folder: {game_path}"]

        if not (game_path / "Oblivion.exe").exists():
            raise RuntimeError("Preflight failed: Oblivion.exe was not found in the selected game folder.")
        lines.append("OK: Oblivion.exe found")

        self.ensure_xobse(game_path)
        lines.append("OK: xOBSE loader found")

        if not support_plugin_dir().exists():
            raise RuntimeError("Preflight failed: bundled host plugin files are missing.")
        lines.append("OK: bundled plugin files found")

        if relay_exe is not None:
            lines.append(f"OK: relay executable found at {relay_exe}")
        elif (server_dir() / "relay_server.py").exists():
            lines.append("OK: python relay script found")
        else:
            raise RuntimeError("Preflight failed: relay executable/script is missing from the host support folder.")

        lines.append(f"Bind host: {values['bind_host']}")
        lines.append(f"Port: {values['server_port']}")
        lines.append(f"Room: {values['room']}")
        lines.append(f"Host player id: {values['player_id']}")
        lines.append("Ready: host checks passed")
        return "\n".join(lines)

    def install_xobse(self) -> None:
        values = self.current_values()
        game_path = Path(str(values["game_path"]))
        if not values["game_path"]:
            messagebox.showerror(APP_NAME, "Choose the Oblivion installation folder first.")
            return

        def work() -> None:
            self.post_status("Installing xOBSE into the game folder...")
            result = subprocess.run(
                powershell_command("install_xobse.ps1", game_path),
                cwd=app_root(),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "xOBSE install failed.")
            self.save_settings()
            self.post_status("xOBSE installed. You can now start the relay and launch the host game.")

        self.run_background("Installing xOBSE...", work)

    def open_firewall(self) -> None:
        def work() -> None:
            self.post_status("Opening the Windows Firewall port for the host relay...")
            result = subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(resolve_script_path("open_firewall_port.ps1")),
                ],
                cwd=app_root(),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Firewall script failed.")
            self.post_status("Firewall rule applied.")

        self.run_background("Opening firewall...", work)

    def run_preflight(self) -> None:
        error = self.validate_inputs()
        if error:
            messagebox.showerror(APP_NAME, error)
            return
        values = self.current_values()

        def work() -> None:
            self.post_status("Running host preflight checks...")
            report = self.build_preflight_report(values)
            self.write_runtime_files(values)
            self.save_settings()
            self.post_status(report)

        self.run_background("Running checks...", work)

    def start_relay_process(self, values: dict[str, str | bool]) -> None:
        if self.relay_process is not None and self.relay_process.poll() is None:
            return

        self.write_runtime_files(values)
        self.save_settings()

        relay_exe = self.relay_executable()
        config_path = self.relay_config_path()
        if relay_exe is not None:
            self.relay_process = subprocess.Popen(
                [str(relay_exe), "--config", str(config_path)],
                cwd=server_dir(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        relay_script = server_dir() / "relay_server.py"
        if relay_script.exists():
            self.relay_process = subprocess.Popen(
                [sys.executable, str(relay_script), "--config", str(config_path)],
                cwd=server_dir(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        raise RuntimeError("Could not find a relay executable or relay_server.py.")

    def start_relay(self) -> None:
        error = self.validate_inputs()
        if error:
            messagebox.showerror(APP_NAME, error)
            return
        values = self.current_values()

        def work() -> None:
            self.post_status("Starting the host relay...")
            self.start_relay_process(values)
            self.post_status("Relay started. Friends can now connect with the shown address, room, and token.")

        self.run_background("Starting relay...", work)

    def stop_relay(self) -> None:
        if self.relay_process is None or self.relay_process.poll() is not None:
            self.status_var.set("Relay is not currently running from this host app.")
            return
        self.relay_process.terminate()
        try:
            self.relay_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.relay_process.kill()
            self.relay_process.wait(timeout=5)
        self.relay_process = None
        self.status_var.set("Relay stopped.")

    def launch_game(self, game_path: Path) -> None:
        for executable_name in ("xOBSE_loader.exe", "obse_loader.exe"):
            candidate = game_path / executable_name
            if candidate.exists():
                subprocess.Popen([str(candidate)], cwd=game_path)  # noqa: S603
                return
        subprocess.Popen([str(game_path / "Oblivion.exe")], cwd=game_path)  # noqa: S603

    def launch_game_only(self) -> None:
        error = self.validate_inputs()
        if error:
            messagebox.showerror(APP_NAME, error)
            return
        values = self.current_values()
        game_path = Path(str(values["game_path"]))

        def work() -> None:
            self.post_status("Preparing the host plugin and launching Oblivion through xOBSE...")
            self.ensure_xobse(game_path)
            self.write_runtime_files(values)
            self.save_settings()
            self.launch_game(game_path)
            self.post_status("Host game launched through xOBSE.")

        self.run_background("Launching game...", work)

    def host_session(self) -> None:
        error = self.validate_inputs()
        if error:
            messagebox.showerror(APP_NAME, error)
            return
        values = self.current_values()
        game_path = Path(str(values["game_path"]))

        def work() -> None:
            self.post_status("Preparing the host session...")
            self.ensure_xobse(game_path)
            self.write_runtime_files(values)
            self.save_settings()
            self.start_relay_process(values)
            self.post_status("Relay started. Launching the host game through xOBSE...")
            self.launch_game(game_path)
            self.post_status("Host session started. Share the shown address, room, and token with your friend.")

        self.run_background("Hosting session...", work)

    def on_close(self) -> None:
        if self.relay_process is not None and self.relay_process.poll() is None:
            self.relay_process.terminate()
            try:
                self.relay_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.relay_process.kill()
                self.relay_process.wait(timeout=3)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    HostApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
