"""NZ Direct Setup: a small Windows setup wizard around setup/setup_nzdirect.ps1.

Built into NZDirect-Setup.exe by build.ps1 (PyInstaller), with the friend kit
(setup script, boiii.exe, launcher, boiii data) bundled as "kit". It finds Black
Ops III in Steam, asks for a folder, runs the setup script and shows its output.
The Steam install is never written to (the script checks that itself).
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP = "NZ Direct Setup"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def kit_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "kit"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent / "build" / "kit"


def steam_game() -> Path | None:
    roots: list[Path] = []
    for hive, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
        try:
            with winreg.OpenKey(hive, key) as k:
                roots.append(Path(winreg.QueryValueEx(k, value)[0]))
        except OSError:
            pass
    roots.append(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam")
    libraries: list[Path] = []
    for root in roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        libraries.append(root)
        libraries += [Path(m.replace("\\\\", "\\")) for m in re.findall(r'"path"\s+"([^"]+)"', text)]
    for lib in dict.fromkeys(libraries):
        acf = lib / "steamapps" / "appmanifest_311210.acf"
        try:
            m = re.search(r'"installdir"\s+"([^"]+)"', acf.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        game = lib / "steamapps" / "common" / (m.group(1) if m else "Call of Duty Black Ops III")
        if (game / "zone").is_dir():
            return game
    return None


def existing_install() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\NZDirect") as k:
            return Path(winreg.QueryValueEx(k, "InstallLocation")[0])
    except OSError:
        return None


class Setup(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP)
        self.geometry("720x520")
        self.minsize(620, 440)
        self.game = steam_game()
        self.installed = existing_install()
        self.target: Path | None = None
        self.proc: subprocess.Popen | None = None
        # The setup runs on a worker thread; it only talks to the window
        # through this queue, which the window polls.
        self.events: queue.Queue = queue.Queue()

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="NZ Direct", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(body, wraplength=680, text=(
            "Installs the NZ Direct launcher and its own copy of Black Ops III next to your Steam "
            "install: game files are linked from Steam (no extra disk space), and your Steam folder "
            "is never changed. Needs Black Ops III from Steam.")).pack(anchor="w", pady=(4, 10))

        if self.game:
            ttk.Label(body, text=f"Black Ops III found: {self.game}").pack(anchor="w")
        else:
            ttk.Label(body, foreground="#b00020", text=(
                "Black Ops III was not found in Steam. Install it with Steam first.")).pack(anchor="w")

        row = ttk.Frame(body)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text="Install to:").pack(side="left")
        drive = (self.game.drive.upper() + "\\") if self.game else "C:\\"
        self.folder = tk.StringVar(value=str(self.installed or Path(drive) / "BO3Direct"))
        ttk.Entry(row, textvariable=self.folder).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse…", command=self.browse).pack(side="left")
        ttk.Label(body, foreground="#666", text=(
            f"Must be on the same drive as the game ({drive}), outside the Steam folder.")).pack(anchor="w")
        self.shortcut = tk.BooleanVar(value=True)
        ttk.Checkbutton(body, text="Desktop shortcut", variable=self.shortcut).pack(anchor="w", pady=(6, 0))

        self.log = tk.Text(body, height=12, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(10, 6))
        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.pack(fill="x")

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        self.install_btn = ttk.Button(buttons, text="Repair / update" if self.installed else "Install",
                                      command=self.install)
        self.install_btn.pack(side="right", ipadx=12)
        self.launch_btn = ttk.Button(buttons, text="Launch NZ Direct", command=self.launch)
        ttk.Button(buttons, text="Close", command=self.close).pack(side="left")
        if not self.game:
            self.install_btn.configure(state="disabled")
        self.protocol("WM_DELETE_WINDOW", self.close)

    def browse(self) -> None:
        d = filedialog.askdirectory(initialdir=self.folder.get())
        if d:
            self.folder.set(str(Path(d)))

    def write(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def install(self) -> None:
        target = Path(self.folder.get().strip().strip('"'))
        if not target.is_absolute():
            messagebox.showinfo(APP, "Pick a full folder path, for example D:\\BO3Direct.")
            return
        self.target = target
        self.install_btn.configure(state="disabled")
        self.launch_btn.pack_forget()
        self.progress.start(12)
        script = kit_dir() / "setup_nzdirect.ps1"
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                "-Target", str(target), "-SteamGame", str(self.game), "-Yes"]
        if not self.shortcut.get():
            args.append("-NoShortcut")
        self.write(f"Installing to {target}…\n")

        def work() -> None:
            try:
                self.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             creationflags=NO_WINDOW, text=True, encoding="utf-8",
                                             errors="replace")
                for line in self.proc.stdout:  # type: ignore[union-attr]
                    self.events.put(("line", line))
                code = self.proc.wait()
            except OSError as e:
                self.events.put(("line", f"Could not run the setup: {e}\n"))
                code = -1
            self.events.put(("done", code))

        threading.Thread(target=work, daemon=True).start()
        self.poll()

    def poll(self) -> None:
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "done":
                self.done(value)
                return
            self.write(value)
        self.after(100, self.poll)

    def done(self, code: int) -> None:
        self.progress.stop()
        self.proc = None
        self.install_btn.configure(state="normal", text="Repair / update")
        if code == 0:
            self.write("\nNZ Direct is installed.\n")
            self.launch_btn.pack(side="right", padx=(0, 8), ipadx=12)
        else:
            self.write("\nSetup did not finish (see the messages above). Nothing in Steam was changed.\n")

    def launch(self) -> None:
        exe = (self.target or Path(self.folder.get())) / "NZDirect" / "NZDirect.exe"
        try:
            subprocess.Popen([str(exe)], cwd=str(exe.parent))
        except OSError as e:
            messagebox.showerror(APP, f"Could not start NZ Direct:\n{e}")
            return
        self.destroy()

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno(APP, "Setup is still running. Stop it?"):
                return
            self.proc.kill()
        self.destroy()


if __name__ == "__main__":
    Setup().mainloop()
