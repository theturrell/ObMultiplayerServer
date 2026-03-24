from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
from queue import Empty, Queue
from datetime import datetime
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_NAME = "Pseudo-OnBlivion Joiner"
DEFAULT_PORT = "7777"
DEFAULT_ROOM = "session-1"
DEFAULT_TOKEN = "change-me"
DEFAULT_SEND_INTERVAL_MS = "100"
APP_PROTOCOL_VERSION = "1"
REPO_ZIP_URL = "https://github.com/theturrell/ObMultiplayerServer/archive/refs/heads/master.zip"
JOINER_BUNDLE_RELATIVE = Path("bundles") / "out" / "PseudoOnBlivion-Joiner"
VERSION_FILE_NAME = "version.json"


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
    return root / "joiner_settings.json"


def can_write_to_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def launch_update_script(
    script_path: Path,
    target_dir: Path,
    source_dir: Path,
    exe_name: str,
    process_names: list[str],
) -> None:
    process_arg = ";".join(process_names)
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-WaitPid",
        str(os.getpid()),
        "-SourceDir",
        str(source_dir),
        "-TargetDir",
        str(target_dir),
        "-ExeName",
        exe_name,
        "-ProcessNames",
        process_arg,
    ]

    if can_write_to_directory(target_dir):
        subprocess.Popen(command, cwd=target_dir)
        return

    ps_args = ",".join("'" + arg.replace("'", "''") + "'" for arg in command[1:])
    elevated = (
        f"Start-Process -FilePath '{command[0]}' -Verb RunAs "
        f"-ArgumentList @({ps_args})"
    )
    subprocess.Popen(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            elevated,
        ],
        cwd=target_dir,
    )


def write_update_script(root: Path) -> Path:
    script_path = root / "apply_update.ps1"
    script_path.write_text(
        "\n".join(
            [
                "param(",
                "    [int]$WaitPid,",
                "    [string]$SourceDir,",
                "    [string]$TargetDir,",
                "    [string]$ExeName,",
                "    [string]$ProcessNames",
                ")",
                "$deadline = (Get-Date).AddSeconds(30)",
                "while (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) {",
                "    if ((Get-Date) -gt $deadline) { break }",
                "    Start-Sleep -Milliseconds 500",
                "}",
                "$names = @()",
                "if ($ProcessNames) {",
                "    $names = $ProcessNames.Split(';') | Where-Object { $_ -and $_.Trim() }",
                "}",
                "foreach ($name in $names) {",
                "    Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
                "}",
                "Start-Sleep -Milliseconds 500",
                "New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null",
                "Get-ChildItem -LiteralPath $TargetDir -Force -ErrorAction SilentlyContinue |",
                "    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue",
                "New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null",
                "robocopy $SourceDir $TargetDir /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null",
                "$code = $LASTEXITCODE",
                "if ($code -ge 8) {",
                '    throw "Update copy failed with robocopy exit code $code."',
                "}",
                "$exePath = Join-Path $TargetDir $ExeName",
                "if (Test-Path $exePath) {",
                "    Start-Process -FilePath $exePath -WorkingDirectory $TargetDir",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    return script_path


def version_file_for(root: Path) -> Path:
    return root / VERSION_FILE_NAME


def load_bundle_version(root: Path) -> dict[str, str]:
    path = version_file_for(root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_build_timestamp(payload: dict[str, str]) -> datetime | None:
    value = str(payload.get("builtAtUtc", "")).strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


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


def sanitize_player_id(character_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", character_name.strip().lower()).strip("-")
    return slug or "joiner-player"


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
        locate_path("plugin") / script_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def ini_text(values: dict[str, str]) -> str:
    return "\n".join(
        [
            "[network]",
            f"server_host={values['server_host']}",
            f"server_port={values['server_port']}",
            f"room={values['room']}",
            f"player_id={sanitize_player_id(values['character_name'])}",
            f"character_name={values['character_name']}",
            "host_authority=false",
            f"server_token={values['server_token']}",
            f"send_interval_ms={values['send_interval_ms']}",
            "",
            "[logging]",
            "log_path=PseudoOnBlivion.log",
            "",
        ]
    )


class JoinerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1080x860")
        self.root.minsize(860, 680)
        self.canvas: tk.Canvas | None = None
        self.scrollable_frame: ttk.Frame | None = None

        self.queue: Queue[tuple[str, str]] = Queue()
        self.busy = False

        self.server_host_var = tk.StringVar()
        self.server_port_var = tk.StringVar(value=DEFAULT_PORT)
        self.room_var = tk.StringVar(value=DEFAULT_ROOM)
        self.character_name_var = tk.StringVar()
        self.server_token_var = tk.StringVar(value=DEFAULT_TOKEN)
        self.game_path_var = tk.StringVar()
        self.send_interval_var = tk.StringVar(value=DEFAULT_SEND_INTERVAL_MS)
        self.status_var = tk.StringVar(value="Fill in the server address and character name, then press Join Game.")

        self.configure_style()
        self.build_ui()
        self.load_settings()
        self.autodetect_game_path()
        self.root.after(150, self.poll_queue)

    def configure_style(self) -> None:
        self.root.configure(bg="#f3ede4")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Root.TFrame", background="#f3ede4")
        style.configure("Card.TFrame", background="#fffaf4", relief="flat")
        style.configure("Title.TLabel", font=("Georgia", 22, "bold"), foreground="#2c241b", background="#f3ede4")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground="#5f5347", background="#f3ede4")
        style.configure("Section.TLabel", font=("Segoe UI Semibold", 11), foreground="#31281f", background="#fffaf4")
        style.configure("Field.TLabel", font=("Segoe UI", 10), foreground="#473b30", background="#fffaf4")
        style.configure("Status.TLabel", font=("Segoe UI", 10), foreground="#3f352b", background="#efe4d1")
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 10))
        style.configure("Secondary.TButton", font=("Segoe UI", 10))
        style.configure("TEntry", padding=7)

    def build_ui(self) -> None:
        outer_frame = ttk.Frame(self.root, style="Root.TFrame")
        outer_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer_frame, bg="#f3ede4", highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(outer_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        root_frame = ttk.Frame(canvas, style="Root.TFrame", padding=18)
        window_id = canvas.create_window((0, 0), window=root_frame, anchor="nw")
        root_frame.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        self.canvas = canvas
        self.scrollable_frame = root_frame

        ttk.Label(root_frame, text="Pseudo-OnBlivion Joiner", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root_frame,
            text="Simple join flow: enter the host address, choose your character name, and launch.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 18))
        ttk.Label(
            root_frame,
            text=f"Protocol {APP_PROTOCOL_VERSION}  |  Preflight checks included",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        card = ttk.Frame(root_frame, style="Card.TFrame", padding=18)
        card.pack(fill="both", expand=True)

        ttk.Label(card, text="Connection", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")

        self.add_field(card, 1, "Server address", self.server_host_var, "Host IP, Tailscale IP, or DNS name")
        self.add_field(card, 2, "Port", self.server_port_var, "Usually 7777", width=18)
        self.add_field(card, 3, "Room", self.room_var, "Must match the host room name")
        self.add_field(card, 4, "Character name", self.character_name_var, "Shown to the session and used for your player id")
        self.add_field(card, 5, "Private token", self.server_token_var, "Leave as provided by the host")

        advanced = ttk.LabelFrame(card, text="Advanced", padding=12)
        advanced.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        advanced.columnconfigure(1, weight=1)
        ttk.Label(advanced, text="Send interval (ms)", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(advanced, textvariable=self.send_interval_var, width=12).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(card, text="Game folder", style="Section.TLabel").grid(row=7, column=0, columnspan=3, sticky="w", pady=(16, 0))
        game_row = ttk.Frame(card, style="Card.TFrame")
        game_row.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        game_row.columnconfigure(0, weight=1)
        ttk.Entry(game_row, textvariable=self.game_path_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(game_row, text="Browse", style="Secondary.TButton", command=self.choose_game_path).grid(row=0, column=1, padx=(10, 0))
        ttk.Button(game_row, text="Detect", style="Secondary.TButton", command=self.autodetect_game_path).grid(row=0, column=2, padx=(10, 0))

        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(22, 0))
        ttk.Button(actions, text="Install xOBSE", style="Secondary.TButton", command=self.install_xobse).pack(side="left")
        ttk.Button(actions, text="Run Check", style="Secondary.TButton", command=self.run_preflight).pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Save Settings", style="Secondary.TButton", command=self.save_settings_only).pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Update App", style="Secondary.TButton", command=self.update_app).pack(side="left", padx=(10, 0))
        ttk.Button(actions, text="Join Game", style="Primary.TButton", command=self.join_game).pack(side="right")

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
            wraplength=680,
        )
        status_card.pack(fill="x")

        for column in range(3):
            card.columnconfigure(column, weight=1 if column == 1 else 0)

    def on_mousewheel(self, event: tk.Event) -> None:
        if self.canvas is None:
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def add_field(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        hint: str,
        width: int | None = None,
    ) -> None:
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

        self.server_host_var.set(data.get("server_host", ""))
        self.server_port_var.set(data.get("server_port", DEFAULT_PORT))
        self.room_var.set(data.get("room", DEFAULT_ROOM))
        self.character_name_var.set(data.get("character_name", ""))
        self.server_token_var.set(data.get("server_token", DEFAULT_TOKEN))
        self.game_path_var.set(data.get("game_path", ""))
        self.send_interval_var.set(data.get("send_interval_ms", DEFAULT_SEND_INTERVAL_MS))

    def save_settings(self) -> None:
        settings = {
            "server_host": self.server_host_var.get().strip(),
            "server_port": self.server_port_var.get().strip(),
            "room": self.room_var.get().strip(),
            "character_name": self.character_name_var.get().strip(),
            "server_token": self.server_token_var.get().strip(),
            "game_path": self.game_path_var.get().strip(),
            "send_interval_ms": self.send_interval_var.get().strip(),
        }
        settings_path().write_text(json.dumps(settings, indent=2), encoding="utf-8")

    def save_settings_only(self) -> None:
        error = self.validate_inputs()
        if error:
            messagebox.showerror(APP_NAME, error)
            return
        self.save_settings()
        self.status_var.set("Settings saved. You can press Join Game whenever you are ready.")

    def autodetect_game_path(self) -> None:
        detected = detect_game_path()
        if detected is not None:
            self.game_path_var.set(str(detected))

    def choose_game_path(self) -> None:
        current = self.game_path_var.get().strip() or str(Path.home())
        chosen = filedialog.askdirectory(title="Choose your Oblivion folder", initialdir=current)
        if chosen:
            self.game_path_var.set(chosen)

    def current_values(self) -> dict[str, str]:
        token = self.server_token_var.get().strip()
        return {
            "server_host": self.server_host_var.get().strip(),
            "server_port": self.server_port_var.get().strip() or DEFAULT_PORT,
            "room": self.room_var.get().strip() or DEFAULT_ROOM,
            "character_name": self.character_name_var.get().strip(),
            "server_token": token or DEFAULT_TOKEN,
            "game_path": self.game_path_var.get().strip(),
            "send_interval_ms": self.send_interval_var.get().strip() or DEFAULT_SEND_INTERVAL_MS,
        }

    def validate_inputs(self) -> str | None:
        values = self.current_values()
        if not values["server_host"]:
            return "Enter the host server address first."
        if not values["character_name"]:
            return "Enter the character name first."
        if not values["game_path"]:
            return "Choose the Oblivion installation folder first."

        game_path = Path(values["game_path"])
        if not (game_path / "Oblivion.exe").exists():
            return "The selected game folder does not contain Oblivion.exe."

        if not support_plugin_dir().exists():
            return "The bundled plugin files are missing from this install."

        try:
            int(values["server_port"])
        except ValueError:
            return "Port must be a number."

        try:
            int(values["send_interval_ms"])
        except ValueError:
            return "Send interval must be a number."

        return None

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
        self.root.after(150, self.poll_queue)

    def post_status(self, text: str) -> None:
        self.queue.put(("status", text))

    def ensure_xobse(self, game_path: Path) -> None:
        if (game_path / "xOBSE_loader.exe").exists() or (game_path / "obse_loader.exe").exists():
            return
        raise RuntimeError("xOBSE is not installed yet. Press Install xOBSE first.")

    def build_preflight_report(self, values: dict[str, str]) -> str:
        game_path = Path(values["game_path"])
        plugin_dir = support_plugin_dir()
        lines: list[str] = []

        lines.append(f"Game folder: {game_path}")
        if (game_path / "Oblivion.exe").exists():
            lines.append("OK: Oblivion.exe found")
        else:
            raise RuntimeError("Preflight failed: Oblivion.exe was not found in the selected game folder.")

        if (game_path / "xOBSE_loader.exe").exists() or (game_path / "obse_loader.exe").exists():
            lines.append("OK: xOBSE loader found")
        else:
            raise RuntimeError("Preflight failed: xOBSE is not installed in the selected game folder.")

        required_files = ["PseudoOnBlivion.dll"]
        missing_files = [name for name in required_files if not (plugin_dir / name).exists()]
        if missing_files:
            raise RuntimeError(
                "Preflight failed: bundled support files are missing: " + ", ".join(missing_files)
            )
        lines.append("OK: bundled plugin files found")

        try:
            with socket.create_connection(
                (values["server_host"], int(values["server_port"])),
                timeout=3.0,
            ):
                lines.append(f"OK: relay reachable at {values['server_host']}:{values['server_port']}")
        except OSError as exc:
            raise RuntimeError(
                "Preflight failed: could not reach the host relay at "
                f"{values['server_host']}:{values['server_port']} ({exc})."
            ) from exc

        lines.append(f"Room: {values['room']}")
        lines.append(f"Character: {values['character_name']}")
        lines.append("Ready: join flow checks passed")
        return "\n".join(lines)

    def run_preflight(self) -> None:
        error = self.validate_inputs()
        if error:
            messagebox.showerror(APP_NAME, error)
            return

        values = self.current_values()

        def work() -> None:
            self.post_status("Running preflight checks against the game folder and relay...")
            report = self.build_preflight_report(values)
            self.save_settings()
            self.post_status(report)

        self.run_background("Running checks...", work)

    def install_xobse(self) -> None:
        error = self.validate_inputs()
        if error and "host server address" not in error and "character name" not in error:
            messagebox.showerror(APP_NAME, error)
            return
        if not self.game_path_var.get().strip():
            messagebox.showerror(APP_NAME, "Choose the Oblivion installation folder first.")
            return

        game_path = Path(self.game_path_var.get().strip())

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
            self.post_status("xOBSE installed. You can now press Join Game.")

        self.run_background("Installing xOBSE...", work)

    def update_app(self) -> None:
        def work() -> None:
            self.post_status("Downloading the latest joiner bundle from GitHub...")
            temp_root = Path(tempfile.mkdtemp(prefix="pseudoonblivion-joiner-update-"))
            archive_path = temp_root / "repo.zip"
            urllib.request.urlretrieve(REPO_ZIP_URL, archive_path)
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(temp_root)

            extracted_roots = [path for path in temp_root.iterdir() if path.is_dir()]
            if not extracted_roots:
                raise RuntimeError("Updater failed: downloaded repo archive was empty.")

            source_dir = extracted_roots[0] / JOINER_BUNDLE_RELATIVE
            if not source_dir.exists():
                raise RuntimeError(f"Updater failed: joiner bundle not found at {source_dir}.")

            local_version = load_bundle_version(app_root())
            remote_version = load_bundle_version(source_dir)
            local_built_at = parse_build_timestamp(local_version)
            remote_built_at = parse_build_timestamp(remote_version)
            if local_built_at is not None and remote_built_at is not None and remote_built_at <= local_built_at:
                raise RuntimeError(
                    "Updater cancelled: the downloaded joiner bundle is not newer than the installed one. "
                    "Push the rebuilt bundles to GitHub first, then try Update App again."
                )

            script_path = write_update_script(temp_root)
            self.post_status("Applying update and relaunching the joiner app...")
            launch_update_script(
                script_path,
                app_root(),
                source_dir,
                "PseudoOnBlivionJoiner.exe",
                ["PseudoOnBlivionJoiner"],
            )
            self.root.after(100, self.root.destroy)

        self.run_background("Updating joiner app...", work)

    def deploy_plugin(self, values: dict[str, str]) -> Path:
        game_path = Path(values["game_path"])
        plugin_target = game_path / "Data" / "OBSE" / "Plugins"
        plugin_target.mkdir(parents=True, exist_ok=True)

        for source in support_plugin_dir().iterdir():
            if source.name.lower() == "pseudoonblivion.ini":
                continue
            destination = plugin_target / source.name
            if source.is_file():
                shutil.copy2(source, destination)

        ini_target = plugin_target / "PseudoOnBlivion.ini"
        ini_target.write_text(ini_text(values), encoding="utf-8")
        return ini_target

    def launch_game(self, game_path: Path) -> None:
        for executable_name in ("xOBSE_loader.exe", "obse_loader.exe"):
            candidate = game_path / executable_name
            if candidate.exists():
                subprocess.Popen([str(candidate)], cwd=game_path)  # noqa: S603
                return
        subprocess.Popen([str(game_path / "Oblivion.exe")], cwd=game_path)  # noqa: S603

    def join_game(self) -> None:
        error = self.validate_inputs()
        if error:
            messagebox.showerror(APP_NAME, error)
            return

        values = self.current_values()
        game_path = Path(values["game_path"])

        def work() -> None:
            self.post_status("Checking xOBSE install...")
            self.ensure_xobse(game_path)
            self.post_status("Checking relay reachability...")
            self.build_preflight_report(values)
            self.post_status("Copying the multiplayer plugin into Oblivion...")
            ini_target = self.deploy_plugin(values)
            self.save_settings()
            self.post_status(f"Saved join settings to {ini_target}. Launching Oblivion...")
            self.launch_game(game_path)
            self.post_status("Oblivion launched. If the host relay is online, your client should connect automatically.")

        self.run_background("Preparing your game...", work)


def main() -> None:
    root = tk.Tk()
    JoinerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
