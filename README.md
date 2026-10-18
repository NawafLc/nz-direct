# NZ Direct

A launcher for **Black Ops III Zombies** on a modified
[boiii-free](https://github.com/Ezz-lol/boiii-free). It boots straight into a
match, and you can play online with friends using lobby codes.

- **Straight into the match.** Pick a map (official, Workshop or custom) and
  an optional mod; the game skips the menus. When the match ends you are back
  in the launcher.
- **Online lobbies.** Create a lobby and send the code. No IP addresses, no
  router settings.
  - A lobby is a private, encrypted [ZeroTier](https://www.zerotier.com)
    network that the host's own PC controls; the launcher installs ZeroTier
    for you.
  - Friends get in automatically. Anyone else has to be let in by the host.
  - The network is deleted when the lobby closes.
- **Friends.** Add friends by username (anyone you've played with) or by
  friend ID (`name#1a2b3c4d5e`).
- **Gobblegums.** Pick your 5 gums in the launcher. They become your equipped
  pack for solo, hosting and joining, also with mods such as All-around
  Enhancement.
- **Match history.** Round, kills, points and downs for every match.
- **Your Steam install is never changed.** NZ Direct runs from its own
  folder:
  - game files are hard links and folder links into Steam, so they take no
    extra space;
  - only small config files are copied;
  - the BlackOps3.exe version boiii supports is downloaded into that folder
    only, and its SHA-1 is checked.

## Install

1. Install Black Ops III from Steam.
2. Download **NZDirect-Setup.exe** from
   [Releases](https://github.com/NawafLc/nz-direct/releases) and run it.
   SmartScreen may warn because the program isn't signed: click
   *More info → Run anyway*.
3. Start **NZ Direct** from the desktop:
   - Friends tab: pick a username.
   - Online lobby tab: click *Set up online play*. Windows asks for
     administrator permission once (to install ZeroTier and add two
     firewall rules).

Prefer a zip? **NZDirect-FriendKit.zip** in Releases has the same files plus
`Setup NZ Direct.cmd` and [FRIEND_SETUP.txt](setup/FRIEND_SETUP.txt).

To uninstall: Windows Settings → Apps → Installed apps → *NZ Direct*. It
removes the NZ Direct folder; Steam is not affected.

## Repository

| Folder | Contents |
| --- | --- |
| `launcher/` | The launcher (Python/tkinter, standard library only): `nz_launcher.pyw`, `nz_net.py` (ZeroTier lobbies), plus a GSC script (match summary) and a Lua script (Gobblegum pack) that it installs into the game folder |
| `setup/` | `setup_nzdirect.ps1` creates the NZ Direct folder (dry run: `-DryRun`). Also the uninstaller and the friend instructions |
| `installer/` | The setup wizard (`NZDirect-Setup.exe`) |
| `boiii/` | The boiii-free changes as patches, with build steps |
| `build.ps1` | Builds `NZDirect.exe`, the friend kit zip and `NZDirect-Setup.exe` into `build/` |

Run the launcher from source with `pythonw launcher\nz_launcher.pyw`.
Build the release files with `.\build.ps1` (needs PyInstaller and a boiii.exe
built from `boiii/`).

## Notes

- **ZeroTier version.** ZeroTier 1.16 and newer ship without the network
  controller that hosting needs, so the launcher installs 1.14.2 (its
  signature is checked first). If a newer ZeroTier is already installed,
  hosting asks for a free ZeroTier Central API token instead. Joining works
  with any version.
- **Firewall.** The firewall rules only accept the game (UDP 27017) and the
  lobby (TCP 27018) from lobby addresses (`10.244.0.0/14`).
- **Not affiliated.** Not affiliated with Activision, Treyarch, Valve or
  ZeroTier. You need to own Black Ops III on Steam.
