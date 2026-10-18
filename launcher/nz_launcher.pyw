"""NZ Direct Launcher: pick a Zombies map (and optionally a mod) and boot
straight into the match with the direct-launch boiii build.

Runs the game from the separate folder (default
C:\\BO3Direct\\steamapps\\common\\Call of Duty Black Ops III), never from the
Steam install. Standard library only.

    pythonw nz_launcher.pyw          GUI
    python  nz_launcher.pyw --list   print what it finds and exit
"""

from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nz_net  # noqa: E402
from nz_net import NetError  # noqa: E402

APP_NAME = "NZ Direct Launcher"
APP_ID = "311210"
DEFAULT_ROOT = Path(r"C:\BO3Direct\steamapps\common\Call of Duty Black Ops III")
SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "NZDirect" / "settings.json"
HISTORY_PATH = SETTINGS_PATH.with_name("history.json")
LOG_NAME = "boiii_direct_launch.log"

# Match summary: a GSC script (shipped next to this launcher, installed into the
# game folder) writes it at every round end and at game over.
SUMMARY_SCRIPT = Path(__file__).with_name("nzdirect_summary.gsc")
SUMMARY_SCRIPT_DEST = Path("boiii") / "custom_scripts" / "zm" / "nzdirect_summary.gsc"
SUMMARY_FILE = Path("boiii") / "scriptdata" / "nzdirect" / "match.json"
# Gobblegum pack: the launcher passes +set nzd_bgb gum,gum,... and this Lua
# script (run by boiii at startup) puts it into the game's equipped pack.
BGB_SCRIPT = Path(__file__).with_name("nzdirect_bgb.lua")
BGB_SCRIPT_DEST = Path("boiii") / "ui_scripts" / "nzdirect_bgb" / "__init__.lua"
BGB_LOG = "nzdirect_bgb.log"
# Replaced by the Lua script; removed from the game folder when found.
OLD_BGB_FILES = [Path("boiii") / "custom_scripts" / "zm" / "nzdirect_bgb.gsc",
                 Path("boiii") / "scriptdata" / "nzdirect" / "bgb.txt"]
PROPERTIES = Path("boiii_players") / "properties.json"

GUMS_CLASSIC = [
    ("zm_bgb_alchemical_antithesis", "Alchemical Antithesis"),
    ("zm_bgb_always_done_swiftly", "Always Done Swiftly"),
    ("zm_bgb_anywhere_but_here", "Anywhere But Here"),
    ("zm_bgb_armamental_accomplishment", "Armamental Accomplishment"),
    ("zm_bgb_arms_grace", "Arm's Grace"),
    ("zm_bgb_arsenal_accelerator", "Arsenal Accelerator"),
    ("zm_bgb_coagulant", "Coagulant"),
    ("zm_bgb_danger_closest", "Danger Closest"),
    ("zm_bgb_eye_candy", "Eye Candy"),
    ("zm_bgb_firing_on_all_cylinders", "Firing On All Cylinders"),
    ("zm_bgb_impatient", "Impatient"),
    ("zm_bgb_in_plain_sight", "In Plain Sight"),
    ("zm_bgb_lucky_crit", "Lucky Crit"),
    ("zm_bgb_newtonian_negation", "Newtonian Negation"),
    ("zm_bgb_now_you_see_me", "Now You See Me"),
    ("zm_bgb_projectile_vomiting", "Projectile Vomiting"),
    ("zm_bgb_stock_option", "Stock Option"),
    ("zm_bgb_sword_flay", "Sword Flay"),
    ("zm_bgb_tone_death", "Tone Death"),
    ("zm_bgb_aftertaste", "Aftertaste"),
]
GUMS_MEGA = [
    ("zm_bgb_board_games", "Board Games"),
    ("zm_bgb_board_to_death", "Board To Death"),
    ("zm_bgb_bullet_boost", "Bullet Boost"),
    ("zm_bgb_burned_out", "Burned Out"),
    ("zm_bgb_cache_back", "Cache Back"),
    ("zm_bgb_crate_power", "Crate Power"),
    ("zm_bgb_crawl_space", "Crawl Space"),
    ("zm_bgb_dead_of_nuclear_winter", "Dead of Nuclear Winter"),
    ("zm_bgb_disorderly_combat", "Disorderly Combat"),
    ("zm_bgb_ephemeral_enhancement", "Ephemeral Enhancement"),
    ("zm_bgb_extra_credit", "Extra Credit"),
    ("zm_bgb_fatal_contraption", "Fatal Contraption"),
    ("zm_bgb_fear_in_headlights", "Fear in Headlights"),
    ("zm_bgb_flavor_hexed", "Flavor Hexed"),
    ("zm_bgb_head_drama", "Head Drama"),
    ("zm_bgb_idle_eyes", "Idle Eyes"),
    ("zm_bgb_immolation_liquidation", "Immolation Liquidation"),
    ("zm_bgb_kill_joy", "Kill Joy"),
    ("zm_bgb_killing_time", "Killing Time"),
    ("zm_bgb_licensed_contractor", "Licensed Contractor"),
    ("zm_bgb_mind_blown", "Mind Blown"),
    ("zm_bgb_near_death_experience", "Near Death Experience"),
    ("zm_bgb_on_the_house", "On the House"),
    ("zm_bgb_perkaholic", "Perkaholic"),
    ("zm_bgb_phoenix_up", "Phoenix Up"),
    ("zm_bgb_pop_shocks", "Pop Shocks"),
    ("zm_bgb_power_vacuum", "Power Vacuum"),
    ("zm_bgb_profit_sharing", "Profit Sharing"),
    ("zm_bgb_reign_drops", "Reign Drops"),
    ("zm_bgb_respin_cycle", "Respin Cycle"),
    ("zm_bgb_round_robbin", "Round Robbin'"),
    ("zm_bgb_secret_shopper", "Secret Shopper"),
    ("zm_bgb_self_medication", "Self Medication"),
    ("zm_bgb_shopping_free", "Shopping Free"),
    ("zm_bgb_slaughter_slide", "Slaughter Slide"),
    ("zm_bgb_soda_fountain", "Soda Fountain"),
    ("zm_bgb_temporal_gift", "Temporal Gift"),
    ("zm_bgb_unbearable", "Unbearable"),
    ("zm_bgb_undead_man_walking", "Undead Man Walking"),
    ("zm_bgb_unquenchable", "Unquenchable"),
    ("zm_bgb_wall_power", "Wall Power"),
    ("zm_bgb_whos_keeping_score", "Who's Keeping Score"),
]
GUM_TITLES = {k: f"{t}  (Classic)" for k, t in GUMS_CLASSIC} | {k: f"{t}  (Mega)" for k, t in GUMS_MEGA}
NO_GUM = "(empty)"

# PE checksum of the BlackOps3.exe the direct-launch build supports.
SUPPORTED_EXE_CHECKSUM = 0x6531394

OFFICIAL_MAPS = [
    ("zm_zod", "Shadows of Evil"),
    ("zm_factory", "The Giant"),
    ("zm_castle", "Der Eisendrache"),
    ("zm_island", "Zetsubou No Shima"),
    ("zm_stalingrad", "Gorod Krovi"),
    ("zm_genesis", "Revelations"),
    ("zm_prototype", "Nacht der Untoten"),
    ("zm_asylum", "Verrückt"),
    ("zm_sumpf", "Shi No Numa"),
    ("zm_theater", "Kino der Toten"),
    ("zm_cosmodrome", "Ascension"),
    ("zm_temple", "Shangri-La"),
    ("zm_moon", "Moon"),
    ("zm_tomb", "Origins"),
]

COLOR_CODES = re.compile(r"\^[0-9A-Za-z]")


@dataclass
class Item:
    kind: str  # "map" or "mod"
    name: str  # map: engine map name; mod: publisher id or folder name
    title: str
    source: str  # "Official", "Workshop", "Local"
    preview: Path | None = None
    description: str = ""

    @property
    def label(self) -> str:
        return f"{self.title}  ({self.name})"


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------

def clean(text: str) -> str:
    return COLOR_CODES.sub("", str(text)).strip()


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def find_preview(*folders: Path) -> Path | None:
    for folder in folders:
        for name in ("previewimage.png", "preview.png", "Thumbnail.png", "thumbnail.png"):
            if (folder / name).is_file():
                return folder / name
    return None


def item_from_workshop_json(data: dict, folder: Path, source: str, dir_name: str,
                            kind: str | None = None) -> Item:
    folder_name = str(data.get("FolderName") or dir_name)
    publisher = str(data.get("PublisherID") or "")
    t = str(data.get("Type", "")).lower()
    kind = kind or (t if t in ("map", "mod") else ("map" if folder_name.startswith("zm_") else "mod"))
    # Maps are started by map name; mods are mounted by Workshop ID.
    name = folder_name if kind == "map" else (publisher if publisher.isdigit() else folder_name)
    return Item(kind, name, clean(data.get("Title") or folder_name), source,
                find_preview(folder, folder.parent), clean(data.get("Description") or ""))


def scan(root: Path) -> tuple[list[Item], list[Item]]:
    maps: list[Item] = []
    mods: list[Item] = []

    for name, title in OFFICIAL_MAPS:
        if (root / "zone" / f"{name}.ff").exists():
            maps.append(Item("map", name, title, "Official"))

    found: list[Item] = []
    for sub, kind in (("usermaps", "map"), ("mods", "mod")):
        base = root / sub
        for entry in sorted(base.iterdir()) if base.is_dir() else []:
            # workshop.json is either in the item folder or in its zone\ folder.
            folder = next((f for f in (entry, entry / "zone") if (f / "workshop.json").is_file()), None)
            data = read_json(folder / "workshop.json") if folder else None
            if data is None:
                folder = next((f for f in (entry / "zone", entry)
                               if f.is_dir() and any(f.glob("*.ff"))), None)
                if folder is None:
                    continue
                data = {"FolderName": entry.name}
            found.append(item_from_workshop_json(data, folder, "Local", entry.name, kind))

    workshop = root.parent.parent / "workshop" / "content" / APP_ID
    for entry in sorted(workshop.iterdir()) if workshop.is_dir() else []:
        data = read_json(entry / "workshop.json")
        if data is not None:
            found.append(item_from_workshop_json(data, entry, "Workshop", entry.name))

    seen: set[tuple[str, str]] = set()
    for item in found:
        key = (item.kind, item.name.lower())
        if key in seen:
            continue
        seen.add(key)
        (maps if item.kind == "map" else mods).append(item)

    official = [m for m in maps if m.source == "Official"]
    custom = sorted((m for m in maps if m.source != "Official"), key=lambda i: i.title.lower())
    return official + custom, sorted(mods, key=lambda i: i.title.lower())


def pe_checksum(path: Path) -> int | None:
    try:
        with open(path, "rb") as f:
            head = f.read(1024)
        pe = struct.unpack_from("<I", head, 0x3C)[0]
        with open(path, "rb") as f:
            f.seek(pe + 24 + 64)  # PE sig + COFF header, then CheckSum
            return struct.unpack("<I", f.read(4))[0]
    except (OSError, struct.error):
        return None


def is_steam_install(root: Path) -> bool:
    """A Steam library has steamapps\\appmanifest_311210.acf next to common\\;
    the separate folder (made by hand or by the friend setup) never has one."""
    if (root / "NZDIRECT_MIRROR.txt").is_file() or "bo3direct" in str(root).lower():
        return False
    return ((root.parent.parent / f"appmanifest_{APP_ID}.acf").exists()
            or "steamapps\\common" in str(root).lower())


def check_root(root: Path) -> str | None:
    """Returns a problem description, or None if the folder is usable."""
    if not (root / "boiii.exe").is_file():
        return f"boiii.exe not found in:\n{root}"
    exe = root / "BlackOps3.exe"
    if not exe.is_file():
        return f"BlackOps3.exe not found in:\n{root}"
    if is_steam_install(root):
        return ("This looks like the Steam install. The direct-launch build must run from "
                "the separate folder (C:\\BO3Direct\\...) so the Steam files stay untouched.")
    cs = pe_checksum(exe)
    if cs != SUPPORTED_EXE_CHECKSUM:
        return (f"BlackOps3.exe in this folder has checksum {cs:#x} (expected "
                f"{SUPPORTED_EXE_CHECKSUM:#x}). Launching could make boiii offer to replace it.")
    return None


def game_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq boiii.exe", "/NH"],
                             capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except OSError:
        return False
    return "boiii.exe" in out.lower()


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

DEFAULTS = {
    "game_root": str(DEFAULT_ROOT),
    "display": "fullscreen",
    "skip_intro": True,
    "skip_cinematics": True,
    "unsafe_lua": False,
    "extra_args": "",
    "username": "",
    "friends": [],  # {"name", "node"}: node is the friend's ZeroTier ID
    "recent": [],  # players met in lobbies, same shape
    "bgb_enabled": False,
    "bgb_pack": [],
    "zt_central_token": "",
    "open_networks": [],  # lobby networks to leave/delete if the launcher was closed mid-lobby
    "last_map": "zm_castle",
    "last_mod": "",
}


def load_settings() -> dict:
    data = read_json(SETTINGS_PATH) or {}
    s = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    # Friends used to be IP addresses; those entries can't be used any more.
    s["friends"] = [f for f in s["friends"] if isinstance(f, dict) and nz_net.NODE_RE.match(str(f.get("node", "")))]
    return s


def read_player_name(root: Path) -> str:
    data = read_json(root / PROPERTIES) or {}
    return nz_net.clean_name(data.get("playerName", "")) if data.get("playerName") else ""


def write_player_name(root: Path, name: str) -> None:
    """boiii's in-game name, so the name in lobbies and in game match.
    Only written into the separate game folder (check_root passed)."""
    path = root / PROPERTIES
    data = read_json(path) or {}
    if data.get("playerName") == name:
        return
    data["playerName"] = name
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def friend_id(name: str, node: str) -> str:
    return f"{name}#{node}"


def parse_friend_id(text: str) -> tuple[str, str] | None:
    m = re.fullmatch(r"\s*(.{1,16}?)\s*#\s*([0-9a-fA-F]{10})\s*", text)
    return (nz_net.clean_name(m.group(1)), m.group(2).lower()) if m else None


def save_settings(s: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_PATH)
    except Exception as e:  # noqa: BLE001 - never lose the reason silently
        try:
            with open(SETTINGS_PATH.with_name("errors.log"), "a", encoding="utf-8") as log:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} saving settings: {e!r}\n")
        except OSError:
            pass


def build_args(map_name: str, mod: str, s: dict, players: int = 1) -> list[str]:
    args = ["boiii.exe", "-launch", "-noupdate"]
    if s["skip_intro"]:
        args.append("-nointro")
    if s["skip_cinematics"]:
        args.append("-nocinematics")
    if s["display"] == "borderless":
        args.append("-borderless")
    elif s["display"] == "windowed":
        args.append("-windowed")
    if s["unsafe_lua"]:
        args.append("-unsafe-lua")
    args += ["+set", "direct_map", map_name]
    if mod:
        args += ["+set", "direct_mod", mod]
    if players > 1:
        # Hosting a lobby: the match waits at its start until everyone is in;
        # the free slots let a player who dropped come back.
        args += ["+set", "sv_maxclients", str(nz_net.MAX_PLAYERS), "+set", "lobby_min_players", str(players)]
    # direct_exit: the game closes when the match ends, back to the launcher.
    args += ["+set", "direct_log", "1", "+set", "direct_exit", "1"]
    args += s["extra_args"].split()
    return args


def build_join_args(address: str, unsafe_lua: bool, s: dict) -> list[str]:
    """Joins a friend's match. boiii's connect mounts the host's mod/usermap."""
    args = ["boiii.exe", "-launch", "-noupdate"]
    if s["skip_intro"]:
        args.append("-nointro")
    if s["skip_cinematics"]:
        args.append("-nocinematics")
    if s["display"] in ("borderless", "windowed"):
        args.append("-" + s["display"])
    if unsafe_lua or s["unsafe_lua"]:
        args.append("-unsafe-lua")
    args += ["+set", "direct_log", "1", "+set", "direct_exit", "1"]
    args += s["extra_args"].split()
    args += ["+connect", address]
    return args


# --------------------------------------------------------------------------
# Match history
# --------------------------------------------------------------------------

def install_scripts(root: Path) -> None:
    """Copies the launcher's GSC scripts into the game folder when they changed."""
    for rel in OLD_BGB_FILES:
        try:
            (root / rel).unlink(missing_ok=True)
        except OSError:
            pass
    for src, rel in ((SUMMARY_SCRIPT, SUMMARY_SCRIPT_DEST), (BGB_SCRIPT, BGB_SCRIPT_DEST)):
        dest = root / rel
        try:
            data = src.read_bytes()
            if not dest.is_file() or dest.read_bytes() != data:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        except OSError:
            pass


def load_history() -> list[dict]:
    data = read_json(HISTORY_PATH)
    return data.get("matches", []) if isinstance(data, dict) else []


def save_history(matches: list[dict]) -> None:
    try:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(json.dumps({"matches": matches[-500:]}, indent=1), encoding="utf-8")
    except OSError:
        pass


DEFAULT_PORT = 27017


def split_address(address: str) -> tuple[str, int]:
    host, _, port = address.strip().rpartition(":")
    if not host:
        return address.strip(), DEFAULT_PORT
    return host, int(port) if port.isdigit() else DEFAULT_PORT


def query_host(address: str, timeout: float = 1.5) -> dict | None:
    """Asks a boiii game at `address` for its info (map, mod, players).
    None when nothing answers, i.e. the friend is not hosting."""
    import socket
    try:
        host, port = split_address(address)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(b"\xff\xff\xff\xffgetInfo nzd", (host, port))
            data = s.recv(65535)
    except (OSError, ValueError):
        return None
    cmd, _, body = data[4:].decode("utf-8", "replace").partition("\n")
    if cmd.strip() != "infoResponse":
        return None
    parts = body.strip().strip("\\").split("\\")
    return dict(zip(parts[::2], parts[1::2]))


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    return f"{h}:{rem // 60:02}:{rem % 60:02}" if h else f"{rem // 60}:{rem % 60:02}"


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

NO_MOD = "None (no mod)"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("920x640")
        self.minsize(780, 540)
        self.settings = load_settings()
        if not self.settings["username"]:
            self.settings["username"] = (read_player_name(Path(self.settings["game_root"]))
                                         or nz_net.clean_name(os.environ.get("USERNAME", "Player")))
        self.maps: list[Item] = []
        self.mods: list[Item] = []
        self.visible_maps: list[Item] = []
        self.preview_image: tk.PhotoImage | None = None
        self.proc: subprocess.Popen | None = None
        # Online lobby: at most one of host/client at a time.
        self.net_ok = False
        self.node = ""
        self.host: nz_net.LobbyHost | None = None
        self.client: nz_net.LobbyClient | None = None
        self.lobby_state: dict = {}
        self.joined_match = -1
        self.join_status = ""

        self._build()
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self) -> None:
        if (self.host or self.client) and not messagebox.askyesno(
                APP_NAME, "You are in a lobby. Leave it and quit?"):
            return
        host, client = self.host, self.client
        self.host = self.client = None
        try:
            if host:
                host.close()
                self.track_network(host.nwid, False)
            if client:
                client.leave()
                self.track_network(client.nwid, False)
        except Exception:  # quitting anyway; leftovers are cleaned up next start
            pass
        self.destroy()

    # ---- layout
    def _build(self) -> None:
        root_row = ttk.Frame(self, padding=(10, 8, 10, 0))
        root_row.pack(fill="x", side="top")
        ttk.Label(root_row, text="Game folder:").pack(side="left")
        self.root_var = tk.StringVar(value=self.settings["game_root"])
        ttk.Entry(root_row, textvariable=self.root_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(root_row, text="Browse…", command=self.browse).pack(side="left")
        ttk.Button(root_row, text="Refresh", command=self.refresh).pack(side="left", padx=(6, 0))

        self.status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status, padding=(10, 4), relief="sunken", anchor="w").pack(fill="x", side="bottom")

        self.tabs = ttk.Notebook(self, padding=(10, 8, 10, 0))
        self.tabs.pack(fill="both", expand=True)
        body = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(body, text="Play")
        self.lobby_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(self.lobby_tab, text="Online lobby")
        self.friends_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(self.friends_tab, text="Friends")
        self.bgb_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(self.bgb_tab, text="Gobblegums")
        self.history_tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(self.history_tab, text="History")

        # Map list
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Map", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        search_row = ttk.Frame(left)
        search_row.pack(fill="x", pady=(2, 4))
        ttk.Label(search_row, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.fill_maps())
        ttk.Entry(search_row, textvariable=self.search_var).pack(side="left", fill="x", expand=True, padx=4)

        self.map_tree = ttk.Treeview(left, columns=("source", "name"), show="tree headings", selectmode="browse")
        self.map_tree.heading("#0", text="Title")
        self.map_tree.heading("source", text="Source")
        self.map_tree.heading("name", text="Map name")
        self.map_tree.column("#0", width=260)
        self.map_tree.column("source", width=80, stretch=False)
        self.map_tree.column("name", width=150, stretch=False)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.map_tree.yview)
        self.map_tree.configure(yscrollcommand=scroll.set)
        self.map_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.map_tree.bind("<<TreeviewSelect>>", lambda _e: self.on_map_selected())
        self.map_tree.bind("<Double-1>", lambda _e: self.launch())

        # Right column
        right = ttk.Frame(body, padding=(12, 0, 0, 0), width=320)
        right.pack(side="left", fill="y")
        right.pack_propagate(False)

        self.preview = ttk.Label(right, text="", anchor="center")
        self.preview.pack(fill="x", pady=(0, 6))
        self.map_title = ttk.Label(right, text="", font=("Segoe UI", 11, "bold"), wraplength=300)
        self.map_title.pack(anchor="w")

        ttk.Label(right, text="Mod", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.mod_var = tk.StringVar(value=NO_MOD)
        self.mod_box = ttk.Combobox(right, textvariable=self.mod_var, state="readonly")
        self.mod_box.pack(fill="x", pady=(2, 0))
        self.mod_box.bind("<<ComboboxSelected>>", lambda _e: self.on_mod_selected())
        self.mod_note = ttk.Label(right, text="BO3 runs one mod at a time.", foreground="#666", wraplength=300)
        self.mod_note.pack(anchor="w")

        ttk.Label(right, text="Options", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.skip_intro = tk.BooleanVar(value=self.settings["skip_intro"])
        self.skip_cine = tk.BooleanVar(value=self.settings["skip_cinematics"])
        self.unsafe_lua = tk.BooleanVar(value=self.settings["unsafe_lua"])
        ttk.Checkbutton(right, text="Skip intro videos", variable=self.skip_intro).pack(anchor="w")
        ttk.Checkbutton(right, text="Skip cinematics (map loading movie)", variable=self.skip_cine).pack(anchor="w")
        ttk.Checkbutton(right, text="Allow unsafe Lua (needed by some mods)", variable=self.unsafe_lua).pack(anchor="w")
        disp = ttk.Frame(right)
        disp.pack(anchor="w", pady=(4, 0))
        ttk.Label(disp, text="Display:").pack(side="left")
        self.display = tk.StringVar(value=self.settings["display"])
        for value in ("fullscreen", "borderless", "windowed"):
            ttk.Radiobutton(disp, text=value.capitalize(), value=value, variable=self.display).pack(side="left", padx=2)
        extra = ttk.Frame(right)
        extra.pack(fill="x", pady=(4, 0))
        ttk.Label(extra, text="Extra args:").pack(side="left")
        self.extra = tk.StringVar(value=self.settings["extra_args"])
        ttk.Entry(extra, textvariable=self.extra).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Label(right, foreground="#666", wraplength=300, text=(
            "The game closes when the match ends and you are back here. "
            "To play with friends, pick the map here, then use the Online lobby tab.")).pack(anchor="w", pady=(6, 0))

        self.launch_btn = ttk.Button(right, text="▶  Play solo", command=self.launch)
        self.launch_btn.pack(fill="x", pady=(14, 0), ipady=6)

        self._build_history(self.history_tab)
        self._build_friends(self.friends_tab)
        self._build_lobby(self.lobby_tab)
        self._build_bgb(self.bgb_tab)

    def _build_history(self, tab: ttk.Frame) -> None:
        cols = ("map", "mod", "round", "kills", "points", "downs", "length", "result")
        heads = ("Map", "Mod", "Round", "Kills", "Points", "Downs", "Length", "Result")
        widths = (150, 150, 55, 55, 65, 55, 65, 90)
        top = ttk.Frame(tab)
        top.pack(fill="both", expand=True)
        self.history_tree = ttk.Treeview(top, columns=cols, show="tree headings", selectmode="browse", height=12)
        self.history_tree.heading("#0", text="Date")
        self.history_tree.column("#0", width=130, stretch=False)
        for c, h, w in zip(cols, heads, widths):
            self.history_tree.heading(c, text=h)
            self.history_tree.column(c, width=w, stretch=c in ("map", "mod"), anchor="w" if c in ("map", "mod", "result") else "e")
        scroll = ttk.Scrollbar(top, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scroll.set)
        self.history_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.history_tree.bind("<<TreeviewSelect>>", lambda _e: self.show_match())

        ttk.Label(tab, text="Players", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        pcols = ("points", "score", "kills", "headshots", "downs", "revives")
        self.player_tree = ttk.Treeview(tab, columns=pcols, show="tree headings", height=4)
        self.player_tree.heading("#0", text="Player")
        self.player_tree.column("#0", width=200)
        for c in pcols:
            self.player_tree.heading(c, text=c.capitalize())
            self.player_tree.column(c, width=80, anchor="e", stretch=False)
        self.player_tree.pack(fill="x")
        self.history: list[dict] = load_history()
        self.fill_history()

    # ---- friends
    def _build_friends(self, tab: ttk.Frame) -> None:
        me = ttk.LabelFrame(tab, text="You", padding=8)
        me.pack(fill="x")
        row = ttk.Frame(me)
        row.pack(fill="x")
        ttk.Label(row, text="Username:").pack(side="left")
        self.username = tk.StringVar(value=self.settings["username"])
        ttk.Entry(row, textvariable=self.username, width=20).pack(side="left", padx=4)
        ttk.Button(row, text="Save", command=self.save_username).pack(side="left")
        ttk.Label(row, text="(also your name in game)", foreground="#666").pack(side="left", padx=6)
        row = ttk.Frame(me)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Your friend ID:").pack(side="left")
        self.my_id = tk.StringVar(value="set up online play first (Online lobby tab)")
        ttk.Entry(row, textvariable=self.my_id, state="readonly", width=34).pack(side="left", padx=4)
        ttk.Button(row, text="Copy", command=lambda: self.copy(self.my_id.get())).pack(side="left")

        add = ttk.Frame(tab)
        add.pack(fill="x", pady=(10, 4))
        ttk.Label(add, text="Add friend:").pack(side="left")
        self.friend_entry = tk.StringVar()
        entry = ttk.Entry(add, textvariable=self.friend_entry, width=30)
        entry.pack(side="left", padx=4)
        entry.bind("<Return>", lambda _e: self.add_friend())
        ttk.Button(add, text="Add", command=self.add_friend).pack(side="left")
        ttk.Label(tab, foreground="#666", wraplength=820, text=(
            "Type the username of someone you have played with in a lobby, or their friend ID "
            "(name#id, from their Friends tab). Friends get into your lobbies without asking; "
            "anyone else with the code has to be let in by you.")).pack(anchor="w")

        lists = ttk.Frame(tab)
        lists.pack(fill="both", expand=True, pady=(8, 0))
        left = ttk.Frame(lists)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Friends", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.friend_tree = ttk.Treeview(left, columns=("id",), show="tree headings", selectmode="browse", height=10)
        self.friend_tree.heading("#0", text="Username")
        self.friend_tree.heading("id", text="Friend ID")
        self.friend_tree.column("#0", width=150)
        self.friend_tree.column("id", width=200)
        self.friend_tree.pack(fill="both", expand=True)
        ttk.Button(left, text="Remove", command=self.remove_friend).pack(anchor="w", pady=(4, 0))

        right = ttk.Frame(lists, padding=(12, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="Recent players", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.recent_tree = ttk.Treeview(right, columns=("id",), show="tree headings", selectmode="browse", height=10)
        self.recent_tree.heading("#0", text="Username")
        self.recent_tree.heading("id", text="Friend ID")
        self.recent_tree.column("#0", width=150)
        self.recent_tree.column("id", width=200)
        self.recent_tree.pack(fill="both", expand=True)
        self.recent_tree.bind("<Double-1>", lambda _e: self.add_recent())
        ttk.Button(right, text="Add as friend", command=self.add_recent).pack(anchor="w", pady=(4, 0))
        self.fill_friends()

    def copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set(f"Copied: {text}")

    def save_username(self) -> None:
        name = self.username.get().strip()
        if not nz_net.NAME_RE.match(name):
            messagebox.showinfo(APP_NAME, "Usernames are 1-16 characters: letters, digits, space, _ . -")
            return
        if self.host or self.client:
            messagebox.showinfo(APP_NAME, "Leave the lobby before changing your username.")
            return
        self.settings["username"] = name
        save_settings(self.settings)
        root = self.root()
        if root.is_dir() and not check_root(root):
            write_player_name(root, name)
        self.update_my_id()
        self.status.set(f"Username saved: {name}")

    def update_my_id(self) -> None:
        if self.node:
            self.my_id.set(friend_id(self.settings["username"], self.node))

    def fill_friends(self) -> None:
        self.friend_tree.delete(*self.friend_tree.get_children())
        for i, f in enumerate(self.settings["friends"]):
            self.friend_tree.insert("", "end", iid=str(i), text=f["name"], values=(friend_id(f["name"], f["node"]),))
        friends = {f["node"] for f in self.settings["friends"]}
        self.recent_tree.delete(*self.recent_tree.get_children())
        for i, f in enumerate(self.settings["recent"]):
            if f["node"] not in friends:
                self.recent_tree.insert("", "end", iid=str(i), text=f["name"], values=(friend_id(f["name"], f["node"]),))

    def friend_map(self) -> dict[str, str]:
        return {f["node"]: f["name"] for f in self.settings["friends"]}

    def remember_friend(self, name: str, node: str) -> None:
        self.settings["friends"] = [f for f in self.settings["friends"] if f["node"] != node]
        self.settings["friends"].append({"name": name, "node": node})
        self.settings["friends"].sort(key=lambda f: f["name"].lower())
        save_settings(self.settings)
        self.fill_friends()
        if self.host:
            self.host.friends = self.friend_map()

    def remember_recent(self, name: str, node: str) -> None:
        if node == self.node or not nz_net.NODE_RE.match(node):
            return
        recent = [f for f in self.settings["recent"] if f["node"] != node]
        recent.insert(0, {"name": name, "node": node})
        self.settings["recent"] = recent[:50]
        for f in self.settings["friends"]:  # keep friends' names current
            if f["node"] == node:
                f["name"] = name
        save_settings(self.settings)
        self.fill_friends()

    def add_friend(self) -> None:
        text = self.friend_entry.get().strip()
        if not text:
            return
        parsed = parse_friend_id(text)
        if parsed is None:
            matches = [f for f in self.settings["recent"] if f["name"].lower() == text.lower()]
            if len(matches) == 1:
                parsed = (matches[0]["name"], matches[0]["node"])
            elif len(matches) > 1:
                messagebox.showinfo(APP_NAME, f"Several recent players are called {text}; "
                                    "pick the right one in Recent players.")
                return
            else:
                messagebox.showinfo(APP_NAME, (
                    f"You haven't played with anyone called \"{text}\" yet.\n\n"
                    "Ask them for their friend ID (Friends tab, looks like name#1a2b3c4d5e), "
                    "or send them a lobby code: after you let them in once, you can add them by username."))
                return
        if parsed[1] == self.node:
            messagebox.showinfo(APP_NAME, "That's your own friend ID.")
            return
        self.remember_friend(*parsed)
        self.friend_entry.set("")

    def add_recent(self) -> None:
        sel = self.recent_tree.selection()
        if sel:
            f = self.settings["recent"][int(sel[0])]
            self.remember_friend(f["name"], f["node"])

    def remove_friend(self) -> None:
        sel = self.friend_tree.selection()
        if sel:
            del self.settings["friends"][int(sel[0])]
            save_settings(self.settings)
            self.fill_friends()
            if self.host:
                self.host.friends = self.friend_map()

    # ---- online lobby
    def _build_lobby(self, tab: ttk.Frame) -> None:
        net = ttk.Frame(tab)
        net.pack(fill="x")
        self.net_status = tk.StringVar(value="Checking online play…")
        self.setup_btn = ttk.Button(net, text="Set up online play", command=self.setup_network)
        self.setup_btn.pack(side="right")
        ttk.Label(net, textvariable=self.net_status, wraplength=640).pack(side="left", fill="x", expand=True)

        start = ttk.Frame(tab)
        start.pack(fill="x", pady=(10, 0))
        host = ttk.LabelFrame(start, text="Host", padding=8)
        host.pack(side="left", fill="both", expand=True)
        self.host_match = ttk.Label(host, text="", wraplength=380)
        self.host_match.pack(anchor="w")
        self.create_btn = ttk.Button(host, text="Create lobby", command=self.create_lobby)
        self.create_btn.pack(anchor="w", pady=(6, 0))
        join = ttk.LabelFrame(start, text="Join", padding=8)
        join.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ttk.Label(join, text="Lobby code:").pack(anchor="w")
        row = ttk.Frame(join)
        row.pack(fill="x", pady=(2, 0))
        self.code_entry = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.code_entry, width=20, font=("Consolas", 11))
        entry.pack(side="left")
        entry.bind("<Return>", lambda _e: self.join_lobby())
        self.join_btn = ttk.Button(row, text="Join", command=self.join_lobby)
        self.join_btn.pack(side="left", padx=6)

        box = ttk.LabelFrame(tab, text="Lobby", padding=8)
        box.pack(fill="both", expand=True, pady=(10, 0))
        top = ttk.Frame(box)
        top.pack(fill="x")
        self.lobby_title = ttk.Label(top, text="Not in a lobby.", font=("Segoe UI", 10, "bold"))
        self.lobby_title.pack(side="left")
        self.code_var = tk.StringVar()
        self.copy_code_btn = ttk.Button(top, text="Copy code", command=lambda: self.copy(self.code_var.get()))
        self.code_label = ttk.Label(top, textvariable=self.code_var, font=("Consolas", 14, "bold"))
        self.lobby_info = ttk.Label(box, text="", foreground="#444", wraplength=820)
        self.lobby_info.pack(anchor="w", pady=(2, 4))
        self.lobby_tree = ttk.Treeview(box, columns=("status", "id"), show="tree headings", selectmode="browse", height=6)
        self.lobby_tree.heading("#0", text="Player")
        self.lobby_tree.heading("status", text="Status")
        self.lobby_tree.heading("id", text="Friend ID")
        self.lobby_tree.column("#0", width=180)
        self.lobby_tree.column("status", width=260)
        self.lobby_tree.column("id", width=220)
        self.lobby_tree.pack(fill="both", expand=True)
        buttons = ttk.Frame(box)
        buttons.pack(fill="x", pady=(6, 0))
        self.start_btn = ttk.Button(buttons, text="▶  Start match", command=self.start_lobby_match)
        self.accept_btn = ttk.Button(buttons, text="Let in", command=lambda: self.lobby_member_action("admit"))
        self.deny_btn = ttk.Button(buttons, text="Decline / kick", command=lambda: self.lobby_member_action("deny"))
        self.befriend_btn = ttk.Button(buttons, text="Add as friend", command=self.befriend_lobby_member)
        self.rejoin_btn = ttk.Button(buttons, text="Join the match", command=self.rejoin_match)
        self.leave_btn = ttk.Button(buttons, text="Leave lobby", command=self.leave_lobby)
        self.lobby_rows: dict[str, dict] = {}
        self.update_host_match()
        self.refresh_lobby()
        self.check_network()

    def check_network(self) -> None:
        def work() -> None:
            ok, text = nz_net.network_ready()
            node = ""
            if ok:
                try:
                    node = nz_net.ZeroTier().node_id()
                except NetError:
                    ok = False
            self.after(0, self._network_checked, ok, text, node)

        threading.Thread(target=work, daemon=True).start()

    def _network_checked(self, ok: bool, text: str, node: str) -> None:
        self.net_ok = ok
        self.node = node
        self.net_status.set(text)
        self.update_my_id()
        if ok:
            self.setup_btn.pack_forget()
            self.cleanup_stale_networks()
        else:
            self.setup_btn.pack(side="right", before=self.setup_btn.master.winfo_children()[-1])
        self.refresh_lobby()

    def cleanup_stale_networks(self) -> None:
        """Networks left behind when the launcher was closed mid-lobby."""
        stale = self.settings.get("open_networks", [])
        if not stale or self.host or self.client:
            return
        self.settings["open_networks"] = []
        save_settings(self.settings)

        def work() -> None:
            try:
                zt = nz_net.ZeroTier()
                local = nz_net.LocalController(zt)
                for nwid in stale:
                    zt.leave(nwid)
                    if nwid.startswith(self.node) and local.available():
                        local.delete(nwid)
            except NetError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def track_network(self, nwid: str, add: bool) -> None:
        nets = [n for n in self.settings.get("open_networks", []) if n != nwid]
        if add:
            nets.append(nwid)
        self.settings["open_networks"] = nets
        save_settings(self.settings)

    def setup_network(self) -> None:
        root = self.root()
        problem = check_root(root) if root.is_dir() else f"Folder not found:\n{root}"
        if problem:
            messagebox.showerror(APP_NAME, problem)
            return
        installed = nz_net.zt_installed()
        if not messagebox.askokcancel(APP_NAME, (
                ("Online play uses ZeroTier, a private, encrypted virtual LAN, so nobody has to "
                 "open router ports or share IP addresses.\n\n")
                + ("" if installed else "This will download and install ZeroTier One 1.14.2 (about 11 MB, "
                   "signed by ZeroTier, Inc.).\n")
                + "It also lets this launcher control ZeroTier and adds Windows Firewall rules so that "
                  "players in your lobby (and only them) can reach the game.\n\n"
                  "Windows will ask for administrator permission. Continue?")):
            return
        self.setup_btn.configure(state="disabled")

        def work() -> None:
            error = nz_net.run_setup(root / "boiii.exe", lambda t: self.after(0, self.net_status.set, t))
            self.after(0, self._setup_done, error)

        threading.Thread(target=work, daemon=True).start()

    def _setup_done(self, error: str | None) -> None:
        self.setup_btn.configure(state="normal")
        if error:
            self.net_status.set("Online play is not set up.")
            messagebox.showerror(APP_NAME, error)
        self.check_network()

    def update_host_match(self) -> None:
        m = self.selected_map()
        mod = self.selected_mod() if m and m.source == "Official" else None
        text = ("Map: " + (m.title if m else "(pick one on the Play tab)")
                + (f"  +  {mod.title}" if mod else ""))
        self.host_match.configure(text=text + "\nChange the map and mod on the Play tab.")
        if self.host and m:
            self.host.set_match(self.lobby_match())

    def lobby_match(self) -> dict:
        m = self.selected_map()
        mod = self.selected_mod() if m and m.source == "Official" else None
        return {"map": m.name if m else "", "map_title": m.title if m else "",
                "mod": mod.name if mod else "", "mod_title": mod.title if mod else "",
                "unsafe_lua": bool(self.unsafe_lua.get())}

    def me(self) -> dict:
        pack = self.settings["bgb_pack"] if self.settings["bgb_enabled"] else []
        return {"name": self.settings["username"], "bgb": nz_net.clean_pack(pack)}

    def need_network(self) -> bool:
        if not self.net_ok:
            messagebox.showinfo(APP_NAME, "Set up online play first (button at the top of this tab).")
            return False
        if not self.settings["username"]:
            messagebox.showinfo(APP_NAME, "Pick a username first (Friends tab).")
            self.tabs.select(self.friends_tab)
            return False
        return True

    def controller_factory(self, zt):
        local = nz_net.LocalController(zt)
        if local.available():
            return local
        token = self.settings.get("zt_central_token", "")
        if token:
            central = nz_net.CentralController(token)
            if central.available():
                return central
        raise NetError("central")

    def create_lobby(self) -> None:
        if self.host or self.client or not self.need_network():
            return
        if not self.selected_map():
            messagebox.showinfo(APP_NAME, "Pick a map on the Play tab first.")
            return
        try:
            has_local = nz_net.LocalController(nz_net.ZeroTier()).available()
        except NetError as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        if not has_local and not self.settings.get("zt_central_token"):
            token = simpledialog.askstring(APP_NAME, (
                "Your ZeroTier version (1.16 or newer) can't run lobbies by itself.\n"
                "Either uninstall ZeroTier and click 'Set up online play' again (installs 1.14.2),\n"
                "or paste an API token from a free my.zerotier.com account\n"
                "(Account > API Access Tokens). It is stored on this PC only.\n\nAPI token:"), parent=self)
            if not token:
                return
            self.settings["zt_central_token"] = token.strip()
            save_settings(self.settings)
        host = nz_net.LobbyHost(self.me(), self.friend_map(), lambda: self.after(0, self.refresh_lobby),
                                self.controller_factory)
        host.match = self.lobby_match()
        self.host = host
        self.lobby_title.configure(text="Creating lobby…")
        self.refresh_lobby()

        def work() -> None:
            try:
                host.open()
                self.after(0, self._lobby_created, host, None)
            except NetError as e:
                self.after(0, self._lobby_created, host, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _lobby_created(self, host, error: str | None) -> None:
        if error:
            self.host = None
            if error == "central":
                self.settings["zt_central_token"] = ""
                save_settings(self.settings)
                error = "The ZeroTier Central API token was not accepted."
            messagebox.showerror(APP_NAME, f"Could not create the lobby:\n{error}")
        else:
            self.track_network(host.nwid, True)
            self.code_var.set(nz_net.lobby_code(host.nwid))
            self.copy(self.code_var.get())
            self.status.set("Lobby created; the code is copied. Send it to your friends.")
        self.refresh_lobby()

    def join_lobby(self) -> None:
        if self.host or self.client or not self.need_network():
            return
        code = self.code_entry.get().strip()
        try:
            client = nz_net.LobbyClient(code, self.me(), lambda k, d: self.after(0, self.client_event, k, d))
        except NetError as e:
            messagebox.showinfo(APP_NAME, str(e))
            return
        self.client = client
        self.lobby_state: dict = {}
        self.joined_match = -1
        self.join_status = "Joining…"
        self.track_network(client.nwid, True)
        client.start()
        self.refresh_lobby()

    def client_event(self, kind: str, data) -> None:
        client = self.client
        if client is None:
            return
        if kind == "status":
            self.join_status = data
        elif kind == "state":
            first = not self.lobby_state
            self.lobby_state = data
            self.join_status = ""
            for p in data.get("players", []):
                self.remember_recent(nz_net.clean_name(p.get("name", "")), str(p.get("node", "")))
            if first:
                self.joined_match = data.get("match_id", 0) if data.get("status") == "in_game" else -1
            if data.get("status") == "in_game" and data.get("match_id") != self.joined_match:
                self.joined_match = data.get("match_id")
                self.join_host_game(auto=True)
        else:
            messages = {"closed": "The host closed the lobby.", "kicked": "The host removed you from the lobby.",
                        "lost": "Lost the connection to the lobby."}
            self.client = None
            self.track_network(client.nwid, False)
            self.refresh_lobby()
            messagebox.showinfo(APP_NAME, messages.get(kind) or f"Could not join: {data}")
            return
        self.refresh_lobby()

    def join_host_game(self, auto: bool) -> None:
        """Waits until the host's game answers, then joins it."""
        client = self.client
        if not client or (self.proc and self.proc.poll() is None):
            return
        match = self.lobby_state.get("match", {})
        mod = match.get("mod", "")
        if mod and not any(m.name == mod for m in self.mods):
            messagebox.showerror(APP_NAME, f"The host is playing with the mod \"{match.get('mod_title') or mod}\", "
                                 "which you don't have installed (subscribe to it on the Steam Workshop).")
            return
        self.join_status = "The host is starting the match…"
        self.refresh_lobby()
        address = f"{client.host_ip}:{nz_net.GAME_PORT}"

        def work() -> None:
            for _ in range(180):
                if self.client is not client:
                    return
                info = query_host(address, timeout=1)
                if info and info.get("mapname"):
                    self.after(0, self._host_game_up, client, address, info)
                    return
                time.sleep(1)
            self.after(0, self._host_game_timeout, client)

        threading.Thread(target=work, daemon=True).start()

    def _host_game_timeout(self, client) -> None:
        if self.client is client:
            self.join_status = "The host's game didn't answer. Use 'Join the match' to try again."
            self.refresh_lobby()

    def _host_game_up(self, client, address: str, info: dict) -> None:
        if self.client is not client or (self.proc and self.proc.poll() is None):
            return
        self.join_status = ""
        match = self.lobby_state.get("match", {})
        host = self.lobby_state.get("host", "host")
        record = {"map": info["mapname"], "map_title": match.get("map_title") or info["mapname"],
                  "mod": match.get("mod", ""), "mod_title": match.get("mod_title", ""), "joined": host}
        unsafe = bool(match.get("unsafe_lua")) or "enhancement" in match.get("mod_title", "").lower()
        self.start_game(build_join_args(address, unsafe, self.current_settings()),
                        f"{record['map_title']} with {host}", record)

    def rejoin_match(self) -> None:
        if self.client and self.lobby_state.get("status") == "in_game":
            self.join_host_game(auto=False)

    def start_lobby_match(self) -> None:
        host = self.host
        if not host or not host.nwid or host.status == "in_game":
            return
        m = self.selected_map()
        if not m:
            messagebox.showinfo(APP_NAME, "Pick a map on the Play tab first.")
            return
        players = [p for p in host.players() if p["ready"]]
        if host.pending and not messagebox.askyesno(
                APP_NAME, "Someone is still waiting to be let in. Start without them?"):
            return
        if not self.can_start():
            return
        mod = self.selected_mod() if m.source == "Official" else None
        s = self.current_settings()
        s.update(last_map=m.name, last_mod=mod.name if mod else "")
        save_settings(s)
        host.me = self.me()
        host.set_match(self.lobby_match())
        what = m.title + (f" + {mod.title}" if mod else "") + f" ({len(players)} players)"
        match = {"map": m.name, "map_title": m.title, "mod": mod.name if mod else "",
                 "mod_title": mod.title if mod else "", "hosting": len(players)}
        if self.start_game(build_args(m.name, mod.name if mod else "", s, len(players)), what, match):
            host.set_status("in_game")

    def selected_lobby_node(self) -> str | None:
        sel = self.lobby_tree.selection()
        return sel[0] if sel else None

    def lobby_member_action(self, action: str) -> None:
        node = self.selected_lobby_node()
        if not self.host or not node or node == self.host.node:
            return
        threading.Thread(target=getattr(self.host, action), args=(node,), daemon=True).start()

    def befriend_lobby_member(self) -> None:
        node = self.selected_lobby_node()
        row = self.lobby_rows.get(node or "")
        if row and row.get("name") and node != self.node:
            self.remember_friend(row["name"], node)
            self.refresh_lobby()

    def leave_lobby(self) -> None:
        if self.host:
            if self.host.status == "in_game" and self.proc and self.proc.poll() is None:
                if not messagebox.askyesno(APP_NAME, "Your match is running. Close the lobby anyway? "
                                           "Players in the match lose the connection."):
                    return
            host, self.host = self.host, None
            self.code_var.set("")
            threading.Thread(target=lambda: (host.close(), self.after(0, self.track_network, host.nwid, False)),
                             daemon=True).start()
        elif self.client:
            client, self.client = self.client, None
            threading.Thread(target=client.leave, daemon=True).start()
            self.track_network(client.nwid, False)
        self.refresh_lobby()

    def refresh_lobby(self) -> None:
        """Redraws the lobby box from the host/client state."""
        friends = self.friend_map()
        rows: dict[str, dict] = {}
        for w in (self.start_btn, self.accept_btn, self.deny_btn, self.befriend_btn, self.rejoin_btn,
                  self.leave_btn, self.code_label, self.copy_code_btn):
            w.pack_forget()
        idle = not self.host and not self.client
        for w in (self.create_btn, self.join_btn):
            w.configure(state="normal" if idle and self.net_ok else "disabled")

        if self.host and self.host.nwid:
            host = self.host
            playing = host.status == "in_game"
            self.lobby_title.configure(text="Your lobby  ·  code:")
            self.code_label.pack(side="left", padx=8)
            self.copy_code_btn.pack(side="left")
            match = host.match
            ctl = f"  ·  lobby run by {host.ctl.name}" if host.ctl else ""
            self.lobby_info.configure(text=(
                f"{'In game' if playing else 'Waiting'}: {match.get('map_title', '?')}"
                + (f" + {match.get('mod_title')}" if match.get("mod_title") else "")
                + f"  ·  up to {nz_net.MAX_PLAYERS} players{ctl}"
                + (f"\n{host.error}" if host.error else "")))
            for p in host.players():
                status = "host (you)" if p["host"] else ("in lobby" if p["ready"] else "connecting…")
                if not p["host"] and p["node"] in friends:
                    status += "  ·  friend"
                rows[p["node"]] = {"name": p["name"], "status": status}
            for node in list(host.pending):
                rows[node] = {"name": "", "status": "wants to join: select and click 'Let in'"
                              if len(host.members) + 1 < nz_net.MAX_PLAYERS else "wants to join (lobby full)"}
            self.start_btn.pack(side="left", ipadx=8)
            self.start_btn.configure(state="disabled" if playing else "normal")
            for w in (self.accept_btn, self.deny_btn, self.befriend_btn):
                w.pack(side="left", padx=(6, 0))
            self.leave_btn.configure(text="Close lobby")
            self.leave_btn.pack(side="right")
        elif self.host:
            self.lobby_title.configure(text="Creating lobby…")
            self.lobby_info.configure(text="Setting up a private network for your lobby (takes a few seconds).")
        elif self.client:
            st = self.lobby_state
            hname = st.get("host") or friends.get(self.client.host_node, "")
            verified = self.client.host_node in friends
            self.lobby_title.configure(text=(f"Lobby of {hname}" if hname else "Lobby")
                                       + ("  ·  friend" if verified else ""))
            match = st.get("match", {})
            lines = []
            if self.join_status:
                lines.append(self.join_status)
            if match:
                lines.append(f"{'In game' if st.get('status') == 'in_game' else 'Waiting for the host to start'}: "
                             f"{match.get('map_title', '?')}"
                             + (f" + {match.get('mod_title')}" if match.get("mod_title") else ""))
                mod = match.get("mod", "")
                if mod and not any(m.name == mod for m in self.mods):
                    lines.append("You don't have this mod installed; subscribe to it on the Steam Workshop.")
            if not verified:
                lines.append(f"Host ID: {self.client.host_node} (not in your friends)")
            self.lobby_info.configure(text="\n".join(lines))
            for p in st.get("players", []):
                node = str(p.get("node", ""))
                status = "host" if p.get("host") else ("in lobby" if p.get("ready") else "connecting…")
                if node == self.node:
                    status += " (you)"
                elif node in friends:
                    status += "  ·  friend"
                rows[node] = {"name": nz_net.clean_name(p.get("name", "")), "status": status}
            self.befriend_btn.pack(side="left")
            if st.get("status") == "in_game":
                self.rejoin_btn.pack(side="left", padx=(6, 0))
            self.leave_btn.configure(text="Leave lobby")
            self.leave_btn.pack(side="right")
        else:
            self.lobby_title.configure(text="Not in a lobby.")
            self.lobby_info.configure(text=(
                "Create a lobby and send the code to your friends, or enter a friend's code. "
                "No IP addresses or router settings needed."))

        self.lobby_rows = rows
        sel = self.selected_lobby_node()
        self.lobby_tree.delete(*self.lobby_tree.get_children())
        for node, r in rows.items():
            fid = friend_id(r["name"], node) if r["name"] else node
            self.lobby_tree.insert("", "end", iid=node, text=r["name"] or "(unknown player)",
                                   values=(r["status"], fid))
        if sel and self.lobby_tree.exists(sel):
            self.lobby_tree.selection_set(sel)
        if self.host:
            for node, m in list(self.host.members.items()):
                if m["conn"] is not None and m["name"] != node:
                    self.remember_recent(m["name"], node)

    # ---- gobblegums
    def _build_bgb(self, tab: ttk.Frame) -> None:
        ttk.Label(tab, wraplength=820, text=(
            "Pick up to 5 gums. Every match started from this launcher (solo, hosting or joining) "
            "puts them into your equipped GobbleGum pack, as if you had changed it in the game's "
            "own pack menu: the scoreboard, the GobbleGum machines and mods all use it.")).pack(anchor="w")
        self.bgb_enabled = tk.BooleanVar(value=self.settings["bgb_enabled"])
        ttk.Checkbutton(tab, text="Use this pack (off: leave the game's pack as it is)",
                        variable=self.bgb_enabled, command=self.save_bgb).pack(anchor="w", pady=(8, 4))
        grid = ttk.Frame(tab)
        grid.pack(anchor="w")
        choices = [NO_GUM] + [GUM_TITLES[k] for k, _ in GUMS_CLASSIC] + [GUM_TITLES[k] for k, _ in GUMS_MEGA]
        pack = nz_net.clean_pack(self.settings["bgb_pack"])
        self.bgb_slots: list[tk.StringVar] = []
        for i in range(5):
            ttk.Label(grid, text=f"Slot {i + 1}:").grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=GUM_TITLES.get(pack[i], NO_GUM) if i < len(pack) else NO_GUM)
            box = ttk.Combobox(grid, textvariable=var, values=choices, state="readonly", width=40, height=25)
            box.grid(row=i, column=1, sticky="w", padx=6, pady=2)
            box.bind("<<ComboboxSelected>>", lambda _e: self.save_bgb())
            self.bgb_slots.append(var)
        self.bgb_note = ttk.Label(tab, text="", foreground="#666", wraplength=820)
        self.bgb_note.pack(anchor="w", pady=(8, 0))
        ttk.Label(tab, foreground="#666", wraplength=820, text=(
            "The game keeps the pack afterwards, also when you start it without the launcher.")).pack(anchor="w")
        self.update_bgb_note()

    def save_bgb(self) -> None:
        by_title = {v: k for k, v in GUM_TITLES.items()}
        pack: list[str] = []
        for var in self.bgb_slots:
            gum = by_title.get(var.get())
            if gum and gum not in pack:
                pack.append(gum)
            elif gum:
                var.set(NO_GUM)  # no duplicates in a pack
        self.settings["bgb_pack"] = pack
        self.settings["bgb_enabled"] = bool(self.bgb_enabled.get())
        save_settings(self.settings)
        self.update_bgb_note()
        if self.client:
            self.client.send_pack(self.me()["bgb"])
        if self.host:
            self.host.me = self.me()

    def update_bgb_note(self) -> None:
        pack = self.settings["bgb_pack"]
        if not self.settings["bgb_enabled"]:
            self.bgb_note.configure(text="Off: the game uses the pack saved in your game.")
        elif not pack:
            self.bgb_note.configure(text="No gums picked: the game uses the pack saved in your game.")
        else:
            self.bgb_note.configure(text=f"{len(pack)} gum(s) in your pack.")

    def fill_history(self) -> None:
        self.history_tree.delete(*self.history_tree.get_children())
        for i, h in reversed(list(enumerate(self.history))):
            players = h.get("players", [])
            self.history_tree.insert("", "end", iid=str(i), text=h.get("date", ""), values=(
                h.get("map_title", h.get("map", "")), h.get("mod_title", "") or "-",
                h.get("round", "-") if h.get("round") else "-",
                sum(p.get("kills", 0) for p in players) if players else "-",
                sum(p.get("score", 0) for p in players) if players else "-",
                sum(p.get("downs", 0) for p in players) if players else "-",
                fmt_duration(h.get("seconds", 0)), h.get("result", "")))
        if self.history:
            iid = str(len(self.history) - 1)
            self.history_tree.selection_set(iid)
            self.history_tree.see(iid)
        self.show_match()

    def show_match(self) -> None:
        self.player_tree.delete(*self.player_tree.get_children())
        sel = self.history_tree.selection()
        if not sel:
            return
        for p in self.history[int(sel[0])].get("players", []):
            self.player_tree.insert("", "end", text=p.get("name", "?"), values=tuple(
                p.get(k, 0) for k in ("points", "score", "kills", "headshots", "downs", "revives")))

    # ---- data
    def root(self) -> Path:
        return Path(self.root_var.get().strip().strip('"'))

    def browse(self) -> None:
        d = filedialog.askdirectory(initialdir=self.root_var.get() or "C:\\")
        if d:
            self.root_var.set(str(Path(d)))
            self.refresh()

    def refresh(self) -> None:
        root = self.root()
        self.maps, self.mods = scan(root) if root.is_dir() else ([], [])
        self.fill_maps()
        self.mod_box["values"] = [NO_MOD] + [m.label for m in self.mods]
        last_mod = self.settings.get("last_mod", "")
        self.mod_var.set(next((m.label for m in self.mods if m.name == last_mod), NO_MOD))
        problem = check_root(root) if root.is_dir() else f"Folder not found:\n{root}"
        n_custom = sum(1 for m in self.maps if m.source != "Official")
        self.status.set(problem.replace("\n", " ") if problem else
                        f"{len(self.maps) - n_custom} official maps, {n_custom} custom maps, {len(self.mods)} mods")
        self.on_mod_selected()

    def fill_maps(self) -> None:
        q = self.search_var.get().lower().strip()
        self.map_tree.delete(*self.map_tree.get_children())
        self.visible_maps = [m for m in self.maps if not q or q in m.title.lower() or q in m.name.lower()]
        select = None
        for i, m in enumerate(self.visible_maps):
            iid = str(i)
            self.map_tree.insert("", "end", iid=iid, text=m.title, values=(m.source, m.name))
            if m.name == self.settings.get("last_map"):
                select = iid
        if select is None and self.visible_maps:
            select = "0"
        if select is not None:
            self.map_tree.selection_set(select)
            self.map_tree.see(select)

    def selected_map(self) -> Item | None:
        sel = self.map_tree.selection()
        return self.visible_maps[int(sel[0])] if sel else None

    def selected_mod(self) -> Item | None:
        label = self.mod_var.get()
        return next((m for m in self.mods if m.label == label), None)

    def on_map_selected(self) -> None:
        m = self.selected_map()
        self.map_title.configure(text=m.title if m else "")
        self.preview_image = None
        if m and m.preview and m.preview.suffix.lower() == ".png":
            try:
                img = tk.PhotoImage(file=str(m.preview))
                factor = max(1, (img.width() + 299) // 300)
                self.preview_image = img.subsample(factor, factor)
            except tk.TclError:
                self.preview_image = None
        self.preview.configure(image=self.preview_image or "", text="" if self.preview_image else "")
        is_usermap = bool(m and m.source != "Official")
        if is_usermap:
            self.mod_var.set(NO_MOD)
            self.mod_box.configure(state="disabled")
            self.mod_note.configure(text="Custom maps load without a mod (BO3 can't combine a usermap with a mod).")
        else:
            self.mod_box.configure(state="readonly")
            self.mod_note.configure(text="BO3 runs one mod at a time.")
        if hasattr(self, "host_match"):
            self.update_host_match()

    def on_mod_selected(self) -> None:
        mod = self.selected_mod()
        if mod and "enhancement" in mod.title.lower():
            self.unsafe_lua.set(True)  # All-around Enhancement asks for it otherwise
        if hasattr(self, "host_match"):
            self.update_host_match()

    # ---- launch
    def current_settings(self) -> dict:
        """Saves the options as shown in the window and returns them."""
        self.settings.update(
            game_root=str(self.root()), display=self.display.get(), skip_intro=self.skip_intro.get(),
            skip_cinematics=self.skip_cine.get(), unsafe_lua=self.unsafe_lua.get(),
            extra_args=self.extra.get())
        save_settings(self.settings)
        return self.settings

    def can_start(self) -> bool:
        root = self.root()
        problem = check_root(root) if root.is_dir() else f"Folder not found:\n{root}"
        if problem:
            messagebox.showerror(APP_NAME, problem)
            return False
        if game_running():
            messagebox.showwarning(APP_NAME, "Black Ops III (boiii.exe) is already running.")
            return False
        return True

    def launch(self) -> None:
        m = self.selected_map()
        if not m:
            messagebox.showinfo(APP_NAME, "Pick a map first.")
            return
        if not self.can_start():
            return
        mod = self.selected_mod() if m.source == "Official" else None
        s = self.current_settings()
        s.update(last_map=m.name, last_mod=mod.name if mod else "")
        save_settings(s)
        what = m.title + (f" + {mod.title}" if mod else "")
        match = {"map": m.name, "map_title": m.title, "mod": mod.name if mod else "",
                 "mod_title": mod.title if mod else ""}
        self.start_game(build_args(m.name, mod.name if mod else "", s), what, match)

    def start_game(self, args: list[str], what: str, match: dict) -> bool:
        if not self.can_start():
            return False
        root = self.root()
        log = root / LOG_NAME
        install_scripts(root)
        write_player_name(root, self.settings["username"])
        stale_files = [log, root / SUMMARY_FILE, root / BGB_LOG]
        pack = self.me()["bgb"]
        if pack:
            # Before +connect, which must come last.
            at = args.index("+connect") if "+connect" in args else len(args)
            args = args[:at] + ["+set", "nzd_bgb", ",".join(pack)] + args[at:]
        for stale in stale_files:
            try:
                stale.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            self.proc = subprocess.Popen(args, cwd=str(root), executable=str(root / "boiii.exe"))
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Could not start boiii.exe:\n{e}")
            return False

        self.launch_btn.configure(state="disabled")
        self.status.set(f"Starting {what}…")
        match["root"] = str(root)
        threading.Thread(target=self.watch, args=(log, what, time.time(), match), daemon=True).start()
        self.iconify()
        return True

    def watch(self, log: Path, what: str, started: float, match: dict) -> None:
        """Follows boiii's direct-launch log and reports progress."""
        reported = ""
        while self.proc and self.proc.poll() is None:
            text = ""
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
            if "EXE_ERR_SERVER_TIMEOUT" in text or "[Sys_Error]" in text:
                state = "The game reported an error; see boiii_direct_launch.log in the game folder."
            elif "Connect failed" in text:
                state = "Could not join: " + re.findall(r"Connect failed: ([^\n]*)", text)[-1]
            elif "client active" in text:
                m = re.findall(r"\[direct_launch\] ([0-9.]+)s: client active", text)
                state = f"In game: {what} (loaded in {float(m[0]):.0f} s)" if m else f"In game: {what}"
                if match.get("hosting") and int(time.time()) % 3 == 0:
                    info = query_host(f"127.0.0.1:{DEFAULT_PORT}", timeout=0.5) or {}
                    state += f"  -  {info.get('clients', '?')}/{match['hosting']} players in"
            elif "map spawned" in text:
                state = f"Loading {what}…"
            elif "loading mod" in text:
                state = f"Loading mod for {what}…"
            else:
                state = f"Starting {what}… ({time.time() - started:.0f} s)"
            if state != reported:
                reported = state
                self.after(0, self.status.set, state)
            time.sleep(1)
        self.after(0, self.match_finished, match, started)

    def match_finished(self, match: dict, started: float) -> None:
        """Back from the game: record the match and show it in the history."""
        self.launch_btn.configure(state="normal")
        if self.host and match.get("hosting"):
            self.host.set_status("lobby")
        root = Path(match.pop("root"))
        text = ""
        try:
            text = (root / LOG_NAME).read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
        summary = read_json(root / SUMMARY_FILE) or {}
        if "client active" not in text:
            self.status.set("Game closed before the match started.")
            self.deiconify()
            self.refresh_lobby()
            return
        loaded = re.findall(r"\[direct_launch\] ([0-9.]+)s: client active", text)
        in_match = time.time() - started - (float(loaded[0]) if loaded else 0)
        match.update(
            date=time.strftime("%Y-%m-%d %H:%M", time.localtime(started)),
            round=summary.get("round", 0),
            seconds=summary.get("time_ms", 0) / 1000 if summary.get("time_ms") else max(0, in_match),
            result=("Game over" if summary.get("final") else
                    f"With {match['joined']}" if match.get("joined") else "Left match"),
            players=summary.get("players", []))
        self.history.append(match)
        save_history(self.history)
        self.fill_history()
        self.tabs.select(self.lobby_tab if self.host or self.client else self.history_tab)
        self.refresh_lobby()
        self.status.set(f"{match['map_title']}: {match['result'].lower()}"
                        + (f" on round {match['round']}" if match["round"] else "") + ".")
        self.deiconify()
        self.lift()
        self.focus_force()


def main() -> None:
    if "--list" in sys.argv:
        root = Path(load_settings()["game_root"])
        maps, mods = scan(root)
        print(f"root: {root}\ncheck: {check_root(root) or 'ok'}")
        for m in maps:
            print(f"map  [{m.source:8}] {m.name:22} {m.title}  preview={'yes' if m.preview else 'no'}")
        for m in mods:
            print(f"mod  [{m.source:8}] {m.name:22} {m.title}")
        return
    App().mainloop()


if __name__ == "__main__":
    main()
