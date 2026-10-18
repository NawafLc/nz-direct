<#
NZ Direct friend setup.

Builds a separate Black Ops III folder next to (never inside) your Steam
install, puts the NZ Direct boiii build and launcher in it and makes a desktop
shortcut. Your Steam folder is only read, never changed:

  zone\ files                 hard links to Steam's (no extra disk space)
  zone\snd, usermaps, mods,   junctions (folder links) into Steam's folder
  video, redist, workshop
  small config folders        copied
  BlackOps3.exe               the version boiii supports (PE checksum
                              0x6531394), copied or downloaded into the new
                              folder only and checked against its SHA-1

Run again any time (for example after a Black Ops III update) to refresh the
links; it only adds what is missing or out of date.

  setup_nzdirect.ps1                      interactive
  setup_nzdirect.ps1 -Target D:\BO3Direct
  setup_nzdirect.ps1 -DryRun              show what would happen, change nothing
#>
[CmdletBinding()]
param(
    [string]$Target = "",
    [string]$SteamGame = "",      # override: Steam's "Call of Duty Black Ops III" folder
    [string]$ExeSource = "",      # use this BlackOps3.exe (checked) instead of downloading
    [switch]$DryRun,
    [switch]$NoShortcut,
    [switch]$NoSettings,          # don't touch %APPDATA%\NZDirect or %LOCALAPPDATA%\boiii
    [switch]$NoRegister,          # no entry in Windows "Installed apps"
    [switch]$Yes                  # no questions
)

$ErrorActionPreference = 'Stop'
$Kit = Join-Path $PSScriptRoot 'files'
$AppId = '311210'
$SupportedChecksum = 0x6531394
$SupportedSha1 = '9D03F81086112113BFB1DD22B8538B9398AC3B9B'
$ExeUrls = @(
    'https://archive.org/download/black-ops-3_20260926/BlackOps3.exe',
    'https://archive.org/download/black-ops-3_20260927/BlackOps3.exe'
)
$script:Changes = 0

function Say([string]$text, [string]$color = 'Gray') { Write-Host $text -ForegroundColor $color }
function Fail([string]$text) { Say "`nERROR: $text" 'Red'; throw $text }

# ---------------------------------------------------------------- Steam
function Get-SteamRoots {
    $roots = @()
    foreach ($key in 'HKCU:\Software\Valve\Steam', 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam', 'HKLM:\SOFTWARE\Valve\Steam') {
        try {
            $p = Get-ItemProperty -Path $key -ErrorAction Stop
            foreach ($v in $p.SteamPath, $p.InstallPath) { if ($v) { $roots += [IO.Path]::GetFullPath($v) } }
        } catch {}
    }
    $roots += "${env:ProgramFiles(x86)}\Steam"
    $libs = @()
    foreach ($r in ($roots | Select-Object -Unique)) {
        $vdf = Join-Path $r 'steamapps\libraryfolders.vdf'
        if (Test-Path $vdf) {
            $libs += $r
            foreach ($m in [regex]::Matches((Get-Content $vdf -Raw), '"path"\s+"([^"]+)"')) {
                $libs += [IO.Path]::GetFullPath(($m.Groups[1].Value -replace '\\\\', '\'))
            }
        }
    }
    return $libs | Select-Object -Unique
}

function Find-SteamGame {
    foreach ($lib in Get-SteamRoots) {
        $acf = Join-Path $lib "steamapps\appmanifest_$AppId.acf"
        if (-not (Test-Path $acf)) { continue }
        $dir = 'Call of Duty Black Ops III'
        $m = [regex]::Match((Get-Content $acf -Raw), '"installdir"\s+"([^"]+)"')
        if ($m.Success) { $dir = $m.Groups[1].Value }
        $game = Join-Path $lib "steamapps\common\$dir"
        if (Test-Path (Join-Path $game 'zone')) { return $game }
    }
    return $null
}

# ---------------------------------------------------------------- helpers
function Get-PeChecksum([string]$path) {
    try {
        $fs = [IO.File]::OpenRead($path)
        try {
            $br = New-Object IO.BinaryReader($fs)
            $fs.Position = 0x3C
            $pe = $br.ReadUInt32()
            $fs.Position = $pe + 24 + 64
            return $br.ReadUInt32()
        } finally { $fs.Dispose() }
    } catch { return $null }
}

function Get-Sha1([string]$path) { (Get-FileHash -Algorithm SHA1 -LiteralPath $path).Hash.ToUpper() }

function Test-Inside([string]$path, [string]$folder) {
    $p = [IO.Path]::GetFullPath($path).TrimEnd('\') + '\'
    $f = [IO.Path]::GetFullPath($folder).TrimEnd('\') + '\'
    return $p.StartsWith($f, [StringComparison]::OrdinalIgnoreCase)
}

# Every write goes through Guard: nothing may be created, changed or removed
# inside the Steam library's steamapps folder.
function Guard([string]$path) {
    if (Test-Inside $path $script:SteamApps) { Fail "Refusing to write inside the Steam folder: $path" }
}

function Act([string]$text, [scriptblock]$action) {
    $script:Changes++
    if ($DryRun) { Say "  would: $text" 'DarkCyan'; return }
    Say "  $text"
    & $action
}

function Ensure-Dir([string]$path) {
    Guard $path
    if (-not (Test-Path -LiteralPath $path)) {
        Act "create folder $path" { New-Item -ItemType Directory -Path $path -Force | Out-Null }
    }
}

function Get-LinkTarget([string]$path) {
    $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    if ($item -and $item.LinkType -in 'Junction', 'SymbolicLink') { return [string]($item.Target | Select-Object -First 1) }
    return $null
}

function Ensure-Junction([string]$link, [string]$target) {
    Guard $link
    if (-not (Test-Path -LiteralPath $target)) {
        Ensure-Dir $link  # Steam has no such folder: use an empty local one
        return
    }
    $current = Get-LinkTarget $link
    if ($current -and ([IO.Path]::GetFullPath($current).TrimEnd('\') -ieq [IO.Path]::GetFullPath($target).TrimEnd('\'))) { return }
    if (Test-Path -LiteralPath $link) {
        if ($current) {
            # A junction elsewhere: removing the link never touches its target.
            Act "relink $link -> $target" { [IO.Directory]::Delete($link); New-Item -ItemType Junction -Path $link -Target $target | Out-Null }
        } else {
            Say "  keeping existing folder $link (not a link)" 'Yellow'
        }
        return
    }
    Act "link $link -> $target" { New-Item -ItemType Junction -Path $link -Target $target | Out-Null }
}

function Ensure-HardLink([string]$link, [string]$target) {
    Guard $link
    $t = Get-Item -LiteralPath $target
    $l = Get-Item -LiteralPath $link -ErrorAction SilentlyContinue
    if ($l -and $l.Length -eq $t.Length -and $l.LastWriteTimeUtc -eq $t.LastWriteTimeUtc) { return }
    if ($l) {
        # Steam replaced its file (game update): drop our old link, link the new one.
        Act "refresh link $link" { [IO.File]::Delete($link); New-Item -ItemType HardLink -Path $link -Target $target | Out-Null }
    } else {
        if ($DryRun) { $script:Changes++; return }  # hundreds of these; counted, not listed
        New-Item -ItemType HardLink -Path $link -Target $target | Out-Null
        $script:Changes++
    }
}

function Copy-IfMissing([string]$src, [string]$dest) {
    Guard $dest
    if (-not (Test-Path -LiteralPath $src) -or (Test-Path -LiteralPath $dest)) { return }
    Act "copy $(Split-Path $src -Leaf) -> $dest" { Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force }
}

function Copy-Update([string]$src, [string]$dest) {
    Guard $dest
    if ((Test-Path -LiteralPath $dest) -and (Get-Sha1 $src) -eq (Get-Sha1 $dest)) { return }
    Act "install $(Split-Path $dest -Leaf) -> $(Split-Path $dest)" { Copy-Item -LiteralPath $src -Destination $dest -Force }
}

# ---------------------------------------------------------------- main
Say "NZ Direct friend setup" 'Cyan'
if ($DryRun) { Say "(dry run: nothing is changed)" 'DarkCyan' }

foreach ($f in 'boiii.exe', 'launcher') {
    if (-not (Test-Path (Join-Path $Kit $f))) { Fail "The kit is incomplete ($f missing). Extract the whole zip first." }
}

$steam = if ($SteamGame) { [IO.Path]::GetFullPath($SteamGame) } else { Find-SteamGame }
if (-not $steam -or -not (Test-Path (Join-Path $steam 'zone'))) {
    Fail "Black Ops III from Steam was not found. Install it with Steam first (or pass -SteamGame <folder>)."
}
$script:SteamApps = Split-Path (Split-Path $steam)  # ...\steamapps
Say "Steam game folder: $steam"

$drive = [IO.Path]::GetPathRoot($steam)
if (-not $Target) {
    $default = Join-Path $drive 'BO3Direct'
    if ($Yes) { $Target = $default } else {
        $answer = Read-Host "Folder for NZ Direct (must be on drive $drive) [$default]"
        $Target = if ($answer) { $answer.Trim('"', ' ') } else { $default }
    }
}
$Target = [IO.Path]::GetFullPath($Target)
if ([IO.Path]::GetPathRoot($Target) -ine $drive) {
    Fail "The folder must be on the same drive as the Steam game ($drive), because the game files are hard-linked, not copied."
}
if ((Test-Inside $Target $script:SteamApps) -or (Test-Inside $script:SteamApps $Target) -or (Test-Inside $steam $Target)) {
    Fail "Pick a folder outside the Steam library (for example $(Join-Path $drive 'BO3Direct'))."
}
$volume = Get-Volume -DriveLetter $drive[0] -ErrorAction SilentlyContinue
if ($volume -and $volume.FileSystem -ne 'NTFS') { Fail "Drive $drive is $($volume.FileSystem); hard links need NTFS." }

$mirror = Join-Path $Target "steamapps\common\$(Split-Path $steam -Leaf)"
Say "NZ Direct folder:  $Target"
Say "Game copy:         $mirror"
if (-not $Yes -and -not $DryRun) {
    $ok = Read-Host "Continue? [Y/n]"
    if ($ok -and $ok -notmatch '^[Yy]') { Say "Cancelled."; exit 1 }
}

# Snapshot of the Steam game's top level, to prove afterwards that it is unchanged.
$before = Get-ChildItem -LiteralPath $steam -Force | ForEach-Object { "$($_.Name)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" }

Say "`n[1/6] Folders and links" 'Cyan'
Ensure-Dir $Target
Ensure-Dir (Join-Path $Target 'steamapps\common')
Ensure-Dir $mirror
$workshop = Join-Path $script:SteamApps 'workshop'
Ensure-Junction (Join-Path $Target 'steamapps\workshop') $workshop
foreach ($d in 'usermaps', 'mods', 'video', 'redist') {
    Ensure-Junction (Join-Path $mirror $d) (Join-Path $steam $d)
}

Say "`n[2/6] Game files (zone\)" 'Cyan'
$zone = Join-Path $mirror 'zone'
Ensure-Dir $zone
$n = $script:Changes
foreach ($item in Get-ChildItem -LiteralPath (Join-Path $steam 'zone') -Force) {
    $dest = Join-Path $zone $item.Name
    if ($item.PSIsContainer) { Ensure-Junction $dest $item.FullName }
    elseif (-not $DryRun -or -not (Test-Path -LiteralPath $dest)) { Ensure-HardLink $dest $item.FullName }
}
Say "  $($script:Changes - $n) zone file(s) $(if ($DryRun) {'would be '})linked or refreshed"

Say "`n[3/6] Small files and settings (copied)" 'Cyan'
foreach ($item in Get-ChildItem -LiteralPath $steam -File -Force) {
    if ($item.Extension -in '.exe', '.dmp', '.log', '.old' -or $item.Name -like '*.boiii_download') { continue }
    Copy-IfMissing $item.FullName (Join-Path $mirror $item.Name)
}
foreach ($d in 'LPC', 'players', 'boiii_players') {
    Copy-IfMissing (Join-Path $steam $d) (Join-Path $mirror $d)
}
Ensure-Dir (Join-Path $mirror 'players')
Ensure-Dir (Join-Path $mirror 'boiii_players')
$marker = Join-Path $mirror 'NZDIRECT_MIRROR.txt'
if (-not (Test-Path $marker)) {
    Act "write $marker" {
        Set-Content -Path $marker -Encoding UTF8 -Value @(
            "Separate Black Ops III folder made by the NZ Direct friend setup.",
            "Game files are linked from: $steam",
            "Delete this whole folder ($Target) to remove NZ Direct; the Steam install is not affected.")
    }
}

Say "`n[4/6] BlackOps3.exe (version 0x6531394, this folder only)" 'Cyan'
$exe = Join-Path $mirror 'BlackOps3.exe'
Guard $exe
if ((Test-Path $exe) -and (Get-PeChecksum $exe) -eq $SupportedChecksum) {
    Say "  already the supported version"
} else {
    $candidates = @()
    if ($ExeSource) { $candidates += [IO.Path]::GetFullPath($ExeSource) }
    $candidates += (Join-Path $steam 'BlackOps3.exe')
    $source = $candidates | Where-Object { (Test-Path $_) -and (Get-PeChecksum $_) -eq $SupportedChecksum -and (Get-Sha1 $_) -eq $SupportedSha1 } | Select-Object -First 1
    if ($source) {
        Act "copy the supported BlackOps3.exe from $source" { Copy-Item -LiteralPath $source -Destination $exe -Force }
    } elseif ($DryRun) {
        Act "download the supported BlackOps3.exe (~101 MB) from archive.org (boiii's own source) into $exe" {}
    } else {
        $tmp = "$exe.download"
        $done = $false
        foreach ($url in $ExeUrls) {
            Say "  downloading $url (~101 MB)..."
            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                $ProgressPreference = 'SilentlyContinue'
                Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
                if ((Get-Sha1 $tmp) -eq $SupportedSha1 -and (Get-PeChecksum $tmp) -eq $SupportedChecksum) { $done = $true; break }
                Say "  the download did not match the expected file; trying the next source" 'Yellow'
            } catch { Say "  download failed: $($_.Exception.Message)" 'Yellow' }
        }
        if (-not $done) {
            Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
            Fail "Could not get the supported BlackOps3.exe. Try again later, or get it from a friend and run: setup_nzdirect.ps1 -ExeSource <path to BlackOps3.exe>"
        }
        if (Test-Path $exe) { Remove-Item -LiteralPath $exe -Force }
        Move-Item -LiteralPath $tmp -Destination $exe
        $script:Changes++
        Say "  downloaded and verified (SHA-1 $SupportedSha1)"
    }
}

Say "`n[5/6] NZ Direct boiii and launcher" 'Cyan'
Copy-Update (Join-Path $Kit 'boiii.exe') (Join-Path $mirror 'boiii.exe')
$zm = Join-Path $mirror 'boiii\custom_scripts\zm'
Ensure-Dir $zm
foreach ($gsc in Get-ChildItem (Join-Path $Kit 'launcher') -Filter '*.gsc') {
    Copy-Update $gsc.FullName (Join-Path $zm $gsc.Name)
}
$launcherDir = Join-Path $Target 'NZDirect'
Ensure-Dir $launcherDir
foreach ($f in Get-ChildItem (Join-Path $Kit 'launcher') -File) {
    Copy-Update $f.FullName (Join-Path $launcherDir $f.Name)
}
$launcherExe = Join-Path $launcherDir 'NZDirect.exe'
$uninstaller = Join-Path $PSScriptRoot 'uninstall_nzdirect.ps1'
if (Test-Path $uninstaller) { Copy-Update $uninstaller (Join-Path $launcherDir 'uninstall_nzdirect.ps1') }

Say "`n[6/6] Settings and shortcut" 'Cyan'
if (-not $NoSettings) {
    # boiii downloads its data on the very first start and would then also
    # replace boiii.exe with the stock build; seeding the data avoids both.
    $boiiiData = Join-Path $env:LOCALAPPDATA 'boiii\data'
    if (-not (Test-Path (Join-Path $boiiiData 'launcher')) -and (Test-Path (Join-Path $Kit 'boiii_data'))) {
        Act "copy boiii's data to $boiiiData" {
            New-Item -ItemType Directory -Force $boiiiData | Out-Null
            Copy-Item -Path (Join-Path $Kit 'boiii_data\*') -Destination $boiiiData -Recurse -Force
        }
    }
    $settingsFile = Join-Path $env:APPDATA 'NZDirect\settings.json'
    $settings = [ordered]@{}
    if (Test-Path $settingsFile) {
        try { (Get-Content $settingsFile -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $settings[$_.Name] = $_.Value } } catch {}
    }
    if ($settings['game_root'] -ne $mirror) {
        Act "point the launcher at $mirror" {
            $settings['game_root'] = $mirror
            New-Item -ItemType Directory -Force (Split-Path $settingsFile) | Out-Null
            $settings | ConvertTo-Json -Depth 6 | Set-Content -Path $settingsFile -Encoding UTF8
        }
    }
}
if (-not $NoRegister) {
    # Per-user entry in Settings > Apps > Installed apps (no admin needed).
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NZDirect'
    $uninstall = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $launcherDir 'uninstall_nzdirect.ps1')`""
    $current = (Get-ItemProperty -Path $key -ErrorAction SilentlyContinue).UninstallString
    if ($current -ne $uninstall) {
        Act "register NZ Direct in Installed apps" {
            New-Item -Path $key -Force | Out-Null
            $values = @{
                DisplayName = 'NZ Direct'; Publisher = 'NawafLc'; DisplayVersion = '1.0.0'
                InstallLocation = $Target; DisplayIcon = "$launcherExe,0"
                UninstallString = $uninstall; NoModify = 1; NoRepair = 1
            }
            foreach ($k in $values.Keys) {
                $type = if ($values[$k] -is [int]) { 'DWord' } else { 'String' }
                New-ItemProperty -Path $key -Name $k -Value $values[$k] -PropertyType $type -Force | Out-Null
            }
        }
    }
}
if (-not $NoShortcut) {
    $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'NZ Direct.lnk'
    Act "desktop shortcut $lnk" {
        $sh = New-Object -ComObject WScript.Shell
        $s = $sh.CreateShortcut($lnk)
        $s.TargetPath = $launcherExe
        $s.WorkingDirectory = $launcherDir
        $s.IconLocation = "$(Join-Path $mirror 'boiii.exe'),0"
        $s.Description = 'NZ Direct: Black Ops III Zombies launcher'
        $s.Save()
    }
}

$after = Get-ChildItem -LiteralPath $steam -Force | ForEach-Object { "$($_.Name)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" }
if (Compare-Object @($before) @($after)) { Fail "The Steam game folder changed during setup. This should never happen; please report it." }

Say ""
if ($DryRun) {
    Say "Dry run finished: $($script:Changes) change(s) would be made. The Steam folder was not touched." 'Green'
} else {
    Say "Done ($($script:Changes) change(s)). The Steam folder was not touched." 'Green'
    Say "Start 'NZ Direct' from your desktop, pick a username (Friends tab) and click"
    Say "'Set up online play' on the Online lobby tab. Then enter your friend's lobby code."
}
