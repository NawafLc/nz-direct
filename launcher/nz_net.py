"""Online lobbies for the NZ Direct launcher.

A lobby is a private ZeroTier network. The host's own ZeroTier service is
the network controller (or, when the installed ZeroTier has no controller, the
host's ZeroTier Central account), so nobody else can let players in:

  - The lobby code is the network ID. Knowing it only lets a PC *ask* to join.
  - The host's launcher admits friends automatically (ZeroTier node IDs come
    from each PC's private key, so they can't be faked) and asks the host
    about anyone else.
  - Only admitted PCs can reach the host's game and lobby ports; ZeroTier
    traffic is end-to-end encrypted. The network is deleted when the lobby
    closes.

Players never type an IP: each lobby gets its own 10.244-247.x.0/24 subnet
derived from the network ID, the host is always .1.

Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

GAME_PORT = 27017
LOBBY_PORT = 27018
MAX_PLAYERS = 4
SUBNET_RANGE = "10.244.0.0/14"

# ZeroTier 1.16+ ships without the network controller; 1.14.2 is the last
# release that has it. The installer's signature is checked before it runs.
ZT_MSI_URL = "https://download.zerotier.com/RELEASES/1.14.2/dist/ZeroTier%20One.msi"
ZT_HOME = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "ZeroTier" / "One"
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "NZDirect"
TOKEN_COPY = DATA_DIR / "zt_authtoken.secret"
CENTRAL_API = "https://api.zerotier.com/api/v1"
# ZeroTier's download server answers 403 to Python's default "Python-urllib" agent.
USER_AGENT = "NZDirect/1.0 (Windows)"

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NAME_RE = re.compile(r"^[A-Za-z0-9_.\- ]{1,16}$")
GUM_RE = re.compile(r"^zm_bgb_[a-z0-9_]{1,40}$")
NODE_RE = re.compile(r"^[0-9a-f]{10}$")


class NetError(Exception):
    pass


# --------------------------------------------------------------------------
# Names, codes, addresses
# --------------------------------------------------------------------------

def clean_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.\- ]", "", str(name)).strip()[:16]
    return name or "Player"


def clean_pack(pack) -> list[str]:
    out: list[str] = []
    for gum in pack if isinstance(pack, list) else []:
        if isinstance(gum, str) and GUM_RE.match(gum) and gum not in out and len(out) < 5:
            out.append(gum)
    return out


_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford: no I, L, O, U


def lobby_code(nwid: str) -> str:
    n = int(nwid, 16)
    chars = "".join(_B32[(n >> (5 * i)) & 31] for i in reversed(range(13)))
    return f"{chars[:4]}-{chars[4:8]}-{chars[8:]}"


def parse_code(code: str) -> str | None:
    """Lobby code (or a raw 16-digit network ID) -> network ID."""
    raw = re.sub(r"[\s\-]", "", code).upper()
    if re.fullmatch(r"[0-9A-F]{16}", raw):
        return raw.lower()
    raw = raw.replace("O", "0").replace("I", "1").replace("L", "1")
    if len(raw) != 13 or any(c not in _B32 for c in raw):
        return None
    n = 0
    for c in raw:
        n = n * 32 + _B32.index(c)
    return f"{n:016x}" if n < 1 << 64 else None


def subnet_of(nwid: str) -> str:
    h = hashlib.sha256(nwid.encode()).digest()
    return f"10.{244 + h[0] % 4}.{h[1]}"


def host_ip(nwid: str) -> str:
    return subnet_of(nwid) + ".1"


# --------------------------------------------------------------------------
# ZeroTier service
# --------------------------------------------------------------------------

def zt_installed() -> bool:
    try:
        r = subprocess.run(["sc", "query", "ZeroTierOneService"], capture_output=True,
                           text=True, creationflags=NO_WINDOW)
    except OSError:
        return False
    return r.returncode == 0


def read_token() -> str | None:
    for path in (TOKEN_COPY, ZT_HOME / "authtoken.secret"):
        try:
            token = path.read_text(encoding="ascii", errors="ignore").strip()
        except OSError:
            continue
        if token:
            return token
    return None


def zt_port() -> int:
    try:
        return int((ZT_HOME / "zerotier-one.port").read_text().strip())
    except (OSError, ValueError):
        return 9993


def http_json(method: str, url: str, headers: dict, body=None, timeout: float = 6):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        **headers, "Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise NetError(f"{method} {url.split('?')[0]}: HTTP {e.code}") from None
    except (urllib.error.URLError, OSError) as e:
        raise NetError(f"{method} {url.split('?')[0]}: {e}") from None
    return json.loads(text) if text.strip() else None


class ZeroTier:
    """The local ZeroTier One service (http://127.0.0.1:9993)."""

    def __init__(self) -> None:
        token = read_token()
        if not token:
            raise NetError("ZeroTier is not set up for this launcher yet.")
        self.headers = {"X-ZT1-Auth": token}
        self.base = f"http://127.0.0.1:{zt_port()}"

    def call(self, method: str, path: str, body=None):
        return http_json(method, self.base + path, self.headers, body)

    def node_id(self) -> str:
        return self.call("GET", "/status")["address"]

    def online(self) -> bool:
        return bool(self.call("GET", "/status").get("online"))

    def network(self, nwid: str) -> dict | None:
        try:
            return self.call("GET", f"/network/{nwid}")
        except NetError:
            return None

    def join(self, nwid: str) -> None:
        self.call("POST", f"/network/{nwid}", {"allowManaged": True, "allowDNS": False,
                                                "allowGlobal": False, "allowDefault": False})

    def leave(self, nwid: str) -> None:
        try:
            self.call("DELETE", f"/network/{nwid}")
        except NetError:
            pass


def network_config() -> dict:
    return {"name": "NZ Direct lobby", "private": True, "enableBroadcast": True,
            "v4AssignMode": {"zt": False}, "v6AssignMode": {"zt": False, "rfc4193": False, "6plane": False},
            "ipAssignmentPools": []}


class LocalController:
    """Controller built into ZeroTier One (<= 1.14)."""

    name = "this PC"

    def __init__(self, zt: ZeroTier) -> None:
        self.zt = zt

    def available(self) -> bool:
        try:
            self.zt.call("GET", "/controller")
            return True
        except NetError:
            return False

    def create(self, node: str) -> str:
        nwid = self.zt.call("POST", f"/controller/network/{node}______", {})["id"]
        cfg = network_config()
        cfg["routes"] = [{"target": subnet_of(nwid) + ".0/24", "via": None}]
        self.zt.call("POST", f"/controller/network/{nwid}", cfg)
        return nwid

    def members(self, nwid: str) -> dict[str, dict]:
        ids = self.zt.call("GET", f"/controller/network/{nwid}/member") or {}
        out = {}
        for mid in ids:
            m = self.zt.call("GET", f"/controller/network/{nwid}/member/{mid}")
            out[mid] = {"authorized": bool(m.get("authorized")), "ips": m.get("ipAssignments") or []}
        return out

    def set_member(self, nwid: str, mid: str, authorized: bool, ip: str | None = None) -> None:
        body = {"authorized": authorized}
        if ip is not None:
            body["ipAssignments"] = [ip] if ip else []
        self.zt.call("POST", f"/controller/network/{nwid}/member/{mid}", body)

    def delete(self, nwid: str) -> None:
        try:
            self.zt.call("DELETE", f"/controller/network/{nwid}")
        except NetError:
            pass


class CentralController:
    """The host's own ZeroTier Central account (for ZeroTier 1.16+)."""

    name = "ZeroTier Central"

    def __init__(self, token: str) -> None:
        self.headers = {"Authorization": f"token {token.strip()}"}

    def call(self, method: str, path: str, body=None):
        return http_json(method, CENTRAL_API + path, self.headers, body, timeout=10)

    def available(self) -> bool:
        try:
            self.call("GET", "/status")
            return True
        except NetError:
            return False

    def create(self, node: str) -> str:
        nwid = self.call("POST", "/network", {"config": network_config()})["id"]
        cfg = network_config()
        cfg["routes"] = [{"target": subnet_of(nwid) + ".0/24", "via": None}]
        self.call("POST", f"/network/{nwid}", {"config": cfg})
        return nwid

    def members(self, nwid: str) -> dict[str, dict]:
        out = {}
        for m in self.call("GET", f"/network/{nwid}/member") or []:
            cfg = m.get("config") or {}
            out[m["nodeId"]] = {"authorized": bool(cfg.get("authorized")),
                                "ips": cfg.get("ipAssignments") or []}
        return out

    def set_member(self, nwid: str, mid: str, authorized: bool, ip: str | None = None) -> None:
        cfg = {"authorized": authorized}
        if ip is not None:
            cfg["ipAssignments"] = [ip] if ip else []
        self.call("POST", f"/network/{nwid}/member/{mid}", {"config": cfg})

    def delete(self, nwid: str) -> None:
        try:
            self.call("DELETE", f"/network/{nwid}")
        except NetError:
            pass


# --------------------------------------------------------------------------
# One-time setup (needs administrator rights, the user confirms the UAC prompt)
# --------------------------------------------------------------------------

SETUP_PS1 = r"""
param([string]$Msi, [string]$TokenOut, [string]$User, [string]$Boiii,
      [string]$Launcher, [string]$Range, [string]$Result)
$ErrorActionPreference = 'Stop'
try {
    if (-not (Get-Service ZeroTierOneService -ErrorAction SilentlyContinue)) {
        if ($Msi -eq 'none' -or -not (Test-Path $Msi)) { throw 'ZeroTier installer missing.' }
        $sig = Get-AuthenticodeSignature $Msi
        if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'ZeroTier') {
            throw "The ZeroTier installer's signature is not valid ($($sig.Status))."
        }
        $p = Start-Process msiexec.exe -ArgumentList "/i `"$Msi`" /qn /norestart" -Wait -PassThru
        if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "ZeroTier install failed (msiexec $($p.ExitCode))." }
    }
    Start-Service ZeroTierOneService -ErrorAction SilentlyContinue
    $src = Join-Path $env:ProgramData 'ZeroTier\One\authtoken.secret'
    for ($i = 0; $i -lt 60 -and -not (Test-Path $src); $i++) { Start-Sleep -Seconds 1 }
    if (-not (Test-Path $src)) { throw 'ZeroTier did not start.' }
    New-Item -ItemType Directory -Force (Split-Path $TokenOut) | Out-Null
    Copy-Item $src $TokenOut -Force
    & icacls.exe $TokenOut /inheritance:r /grant:r "${User}:(R)" "*S-1-5-18:(F)" "*S-1-5-32-544:(F)" | Out-Null

    # Inbound rules, only from lobby addresses. Windows' own "Block" rules for
    # these programs (from a dismissed firewall prompt) would override them.
    Get-NetFirewallRule -DisplayName 'NZ Direct*' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    $programs = @($Boiii) + ($Launcher -split ';' | Where-Object { $_ })
    foreach ($prog in $programs) {
        Get-NetFirewallApplicationFilter -Program $prog -ErrorAction SilentlyContinue |
            Get-NetFirewallRule | Where-Object { $_.Action -eq 'Block' -and $_.Direction -eq 'Inbound' } |
            Remove-NetFirewallRule
    }
    New-NetFirewallRule -DisplayName 'NZ Direct game (lobby players)' -Direction Inbound -Action Allow `
        -Program $Boiii -Protocol UDP -LocalPort 27017 -RemoteAddress $Range -Profile Any | Out-Null
    foreach ($prog in ($Launcher -split ';' | Where-Object { $_ })) {
        New-NetFirewallRule -DisplayName 'NZ Direct lobby (lobby players)' -Direction Inbound -Action Allow `
            -Program $prog -Protocol TCP -LocalPort 27018 -RemoteAddress $Range -Profile Any | Out-Null
    }
    $status = 'ok'
} catch {
    $status = 'error: ' + $_.Exception.Message
}
# Files this elevated process creates are not readable by the normal account
# otherwise; the launcher reads the result as the user.
Set-Content -Path $Result -Value $status
& icacls.exe $Result /grant "${User}:(R)" | Out-Null
"""


def launcher_programs() -> list[str]:
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return [str(exe)]
    return [str(p) for p in (exe.with_name("python.exe"), exe.with_name("pythonw.exe")) if p.exists()]


def run_setup(boiii_exe: Path, progress=lambda text: None) -> str | None:
    """Installs ZeroTier if needed, gives this launcher access to it and opens
    the firewall for lobby players. Returns an error message or None."""
    work = Path(tempfile.mkdtemp(prefix="nzdirect_setup_"))
    msi = "none"
    if not zt_installed():
        progress("Downloading ZeroTier 1.14.2…")
        target = work / "ZeroTierOne-1.14.2.msi"
        try:
            req = urllib.request.Request(ZT_MSI_URL, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r, open(target, "wb") as f:
                while chunk := r.read(1 << 16):
                    f.write(chunk)
        except OSError as e:
            return f"Could not download ZeroTier: {e}"
        msi = str(target)
    script = work / "setup.ps1"
    script.write_text(SETUP_PS1, encoding="utf-8-sig")
    result = work / "result.txt"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\")

    def q(value: str) -> str:  # inside a PowerShell single-quoted string
        return '"' + str(value).replace("'", "''") + '"'

    inner = " ".join([
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", q(script),
        "-Msi", q(msi), "-TokenOut", q(TOKEN_COPY), "-User", q(user), "-Boiii", q(boiii_exe),
        "-Launcher", q(";".join(launcher_programs())), "-Range", q(SUBNET_RANGE), "-Result", q(result)])
    progress("Waiting for you to allow the setup (Windows will ask)…")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList '{inner}'"],
                       capture_output=True, creationflags=NO_WINDOW, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Setup did not run: {e}"
    try:
        status = result.read_text(encoding="utf-8-sig", errors="replace").strip()
    except FileNotFoundError:
        return "Setup was cancelled (Windows' permission prompt was declined or closed)."
    except OSError:
        status = "ok"  # it ran; whether it worked is checked below
    if status != "ok":
        return status.removeprefix("error: ")
    progress("Waiting for ZeroTier to come online…")
    for _ in range(60):
        try:
            if ZeroTier().online():
                return None
        except NetError:
            pass
        time.sleep(1)
    return "ZeroTier is installed but not online yet; try again in a minute."


def network_ready() -> tuple[bool, str]:
    if not zt_installed():
        return False, "Online play needs a one-time setup (installs ZeroTier, a private virtual LAN)."
    try:
        zt = ZeroTier()
        node = zt.node_id()
        if not zt.online():
            return False, "ZeroTier is starting… (no internet connection?)"
    except NetError:
        return False, "Online play needs a one-time setup (gives this launcher access to ZeroTier)."
    return True, f"Online play ready (your ID: {node})"


# --------------------------------------------------------------------------
# Lobby protocol: JSON lines over TCP on the lobby network only
# --------------------------------------------------------------------------

def send_msg(sock: socket.socket, msg: dict) -> None:
    sock.sendall((json.dumps(msg) + "\n").encode())


def read_msgs(sock: socket.socket):
    buf = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            return
        buf += chunk
        if len(buf) > 65536:
            return
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict):
                yield msg


class LobbyHost:
    """Owns the lobby network. Callbacks run on worker threads."""

    def __init__(self, me: dict, friends: dict[str, str], on_change, controller_factory) -> None:
        self.me = me  # {"name", "bgb"}
        self.friends = friends  # node -> name
        self.on_change = on_change
        self.controller_factory = controller_factory
        self.zt: ZeroTier | None = None
        self.ctl = None
        self.nwid = ""
        self.node = ""
        self.ip = ""
        self.members: dict[str, dict] = {}  # node -> {name, ip, bgb, conn, admitted}
        self.pending: dict[str, float] = {}  # node -> first seen
        self.denied: set[str] = set()
        self.match: dict = {}
        self.status = "lobby"
        self.match_id = 0
        self.closed = False
        self.error = ""
        self.lock = threading.Lock()
        self.server: socket.socket | None = None

    # ---- lifecycle
    def open(self) -> None:
        """Blocking: creates and joins the network. Raises NetError."""
        self.zt = ZeroTier()
        self.node = self.zt.node_id()
        self.ctl = self.controller_factory(self.zt)
        self.nwid = self.ctl.create(self.node)
        self.ip = host_ip(self.nwid)
        self.zt.join(self.nwid)
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.node in self.ctl.members(self.nwid):
                break
            time.sleep(1)
        self.ctl.set_member(self.nwid, self.node, True, self.ip)
        while time.time() < deadline:
            net = self.zt.network(self.nwid) or {}
            if any(a.startswith(self.ip + "/") for a in net.get("assignedAddresses") or []):
                break
            time.sleep(1)
        else:
            self.close()
            raise NetError("The lobby network did not come up (ZeroTier gave this PC no lobby address).")
        for _ in range(20):  # the address can take a moment to be usable
            try:
                self.server = socket.create_server((self.ip, LOBBY_PORT))
                break
            except OSError:
                time.sleep(0.5)
        else:
            self.close()
            raise NetError(f"Could not open the lobby port {LOBBY_PORT}.")
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._member_loop, daemon=True).start()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.broadcast({"type": "closed"})
        with self.lock:
            for m in self.members.values():
                if m.get("conn"):
                    try:
                        m["conn"].close()
                    except OSError:
                        pass
        if self.server:
            try:
                self.server.close()
            except OSError:
                pass
        if self.zt and self.nwid:
            self.zt.leave(self.nwid)
        if self.ctl and self.nwid:
            self.ctl.delete(self.nwid)

    # ---- members
    def _next_ip(self) -> str:
        used = {m["ip"] for m in self.members.values()}
        base = subnet_of(self.nwid)
        return next(f"{base}.{i}" for i in range(2, 255) if f"{base}.{i}" not in used)

    def admit(self, node: str) -> None:
        with self.lock:
            if node in self.members or len(self.members) + 1 >= MAX_PLAYERS:
                return
            ip = self._next_ip()
            self.members[node] = {"name": self.friends.get(node, node), "ip": ip, "bgb": [],
                                  "conn": None}
            self.pending.pop(node, None)
            self.denied.discard(node)
        try:
            self.ctl.set_member(self.nwid, node, True, ip)
        except NetError as e:
            self.error = str(e)
        self.changed()

    def deny(self, node: str) -> None:
        with self.lock:
            self.pending.pop(node, None)
            self.denied.add(node)
            m = self.members.pop(node, None)
        if m and m.get("conn"):
            try:
                send_msg(m["conn"], {"type": "kicked"})
                m["conn"].close()
            except OSError:
                pass
        try:
            self.ctl.set_member(self.nwid, node, False, "")
        except NetError:
            pass
        self.changed()

    def _member_loop(self) -> None:
        while not self.closed:
            try:
                found = self.ctl.members(self.nwid)
            except NetError as e:
                self.error = str(e)
                time.sleep(3)
                continue
            new_pending = False
            for node, info in found.items():
                if node == self.node or node in self.members or node in self.denied:
                    continue
                if node in self.friends:
                    self.admit(node)
                elif node not in self.pending:
                    self.pending[node] = time.time()
                    new_pending = True
            if new_pending:
                self.changed()
            time.sleep(2)

    def _accept_loop(self) -> None:
        while not self.closed:
            try:
                conn, (addr, _port) = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(conn, addr), daemon=True).start()

    def _client(self, conn: socket.socket, addr: str) -> None:
        # The source address identifies the member: ZeroTier only delivers
        # packets from admitted members with the address the host assigned.
        with self.lock:
            node = next((n for n, m in self.members.items() if m["ip"] == addr), None)
        if node is None:
            conn.close()
            return
        conn.settimeout(None)
        try:
            for msg in read_msgs(conn):
                kind = msg.get("type")
                if kind == "hello":
                    with self.lock:
                        m = self.members.get(node)
                        if m is None:
                            break
                        old = m.get("conn")
                        m.update(name=clean_name(msg.get("name", "")), bgb=clean_pack(msg.get("bgb")),
                                 conn=conn)
                    if old and old is not conn:
                        try:
                            old.close()
                        except OSError:
                            pass
                    self.changed()
                elif kind == "bgb":
                    with self.lock:
                        if node in self.members:
                            self.members[node]["bgb"] = clean_pack(msg.get("bgb"))
        except OSError:
            pass
        with self.lock:
            m = self.members.get(node)
            if m and m.get("conn") is conn:
                m["conn"] = None
        try:
            conn.close()
        except OSError:
            pass
        self.changed()

    # ---- state
    def players(self) -> list[dict]:
        with self.lock:
            out = [{"name": self.me["name"], "node": self.node, "host": True, "ready": True}]
            for node, m in self.members.items():
                out.append({"name": m["name"], "node": node, "host": False, "ready": m["conn"] is not None})
        return out

    def state(self) -> dict:
        return {"type": "state", "host": self.me["name"], "host_node": self.node, "match": self.match,
                "players": self.players(), "status": self.status, "match_id": self.match_id,
                "max": MAX_PLAYERS}

    def broadcast(self, msg: dict) -> None:
        with self.lock:
            conns = [m["conn"] for m in self.members.values() if m.get("conn")]
        for c in conns:
            try:
                send_msg(c, msg)
            except OSError:
                pass

    def changed(self) -> None:
        if not self.closed:
            self.broadcast(self.state())
        self.on_change()

    def set_match(self, match: dict) -> None:
        self.match = match
        self.changed()

    def set_status(self, status: str) -> None:
        if status == "in_game":
            self.match_id += 1
        self.status = status
        self.changed()

    def packs(self) -> dict[str, list[str]]:
        """Player name -> Gobblegum pack, for the in-game script."""
        out = {}
        if self.me.get("bgb"):
            out[self.me["name"]] = self.me["bgb"]
        with self.lock:
            for m in self.members.values():
                if m["bgb"] and m["conn"] is not None:
                    out[m["name"]] = m["bgb"]
        return out


class LobbyClient:
    """Joins a lobby by code. Callbacks run on worker threads."""

    def __init__(self, code: str, me: dict, on_event) -> None:
        nwid = parse_code(code)
        if not nwid:
            raise NetError("That is not a valid lobby code.")
        self.nwid = nwid
        self.host_node = nwid[:10]
        self.host_ip = host_ip(nwid)
        self.me = me
        self.on_event = on_event  # (kind, data)
        self.zt = ZeroTier()
        self.sock: socket.socket | None = None
        self.closed = False
        self.state: dict = {}

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            if self.zt.node_id() == self.host_node:
                raise NetError("That is your own lobby.")
            self.zt.join(self.nwid)
            self.on_event("status", "Asking to join…")
            deadline = time.time() + 30
            while not self.closed:
                net = self.zt.network(self.nwid) or {}
                status = net.get("status", "")
                if status == "OK" and net.get("assignedAddresses"):
                    break
                if status == "ACCESS_DENIED":
                    self.on_event("status", "Waiting for the host to let you in…")
                elif status == "NOT_FOUND" or (status in ("", "REQUESTING_CONFIGURATION")
                                                and time.time() > deadline):
                    raise NetError("No lobby with that code (or the host closed it).")
                time.sleep(1)
            self.on_event("status", "Connecting to the lobby…")
            for _ in range(30):
                if self.closed:
                    return
                try:
                    self.sock = socket.create_connection((self.host_ip, LOBBY_PORT), timeout=3)
                    break
                except OSError:
                    time.sleep(1)
            else:
                raise NetError("Let in, but could not reach the host's launcher.")
            self.sock.settimeout(None)
            send_msg(self.sock, {"type": "hello", "name": self.me["name"], "bgb": self.me.get("bgb", [])})
            for msg in read_msgs(self.sock):
                kind = msg.get("type")
                if kind == "state":
                    self.state = msg
                    self.on_event("state", msg)
                elif kind in ("closed", "kicked"):
                    self.on_event(kind, None)
                    self.closed = True
                    break
            if not self.closed:
                self.on_event("lost", None)
        except (NetError, OSError) as e:
            if not self.closed:
                self.on_event("error", str(e))
        finally:
            self.leave()

    def send_pack(self, pack: list[str]) -> None:
        if self.sock:
            try:
                send_msg(self.sock, {"type": "bgb", "bgb": pack})
            except OSError:
                pass

    def leave(self) -> None:
        self.closed = True
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.zt.leave(self.nwid)
