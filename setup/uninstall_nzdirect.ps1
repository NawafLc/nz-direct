<#
NZ Direct uninstaller. Removes the NZ Direct folder (made by setup_nzdirect.ps1),
the desktop shortcut and the Windows "Installed apps" entry.

The folder holds links into the Steam install. Every link is removed as a
link first (never followed), so nothing in the Steam folder is touched.
Your launcher settings (%APPDATA%\NZDirect) and ZeroTier are kept unless you
pass -RemoveSettings; uninstall ZeroTier from Windows Settings > Apps.
#>
[CmdletBinding()]
param(
    [string]$Target = "",
    [switch]$RemoveSettings,
    [switch]$Yes
)
$ErrorActionPreference = 'Stop'
if (-not $Target) { $Target = Split-Path $PSScriptRoot }  # <Target>\NZDirect\uninstall_nzdirect.ps1
$Target = [IO.Path]::GetFullPath($Target)

$marker = Get-ChildItem -LiteralPath (Join-Path $Target 'steamapps\common') -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName 'NZDIRECT_MIRROR.txt' } | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $marker) {
    Write-Host "$Target is not an NZ Direct folder (no NZDIRECT_MIRROR.txt); nothing removed." -ForegroundColor Red
    exit 1
}
if (Test-Path (Join-Path $Target 'steamapps\appmanifest_311210.acf')) {
    Write-Host "$Target looks like a Steam library; nothing removed." -ForegroundColor Red
    exit 1
}
if (-not $Yes) {
    $ok = Read-Host "Remove NZ Direct from $Target ? The Steam install is not affected. [y/N]"
    if ($ok -notmatch '^[Yy]') { exit 1 }
}

Get-Process boiii, NZDirect -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Target*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# 1. Unlink every junction/symlink (deepest first). Deleting a link never
#    touches its target.
$links = Get-ChildItem -LiteralPath $Target -Recurse -Force -Attributes ReparsePoint -ErrorAction SilentlyContinue |
    Sort-Object { $_.FullName.Length } -Descending
foreach ($l in $links) {
    if ($l.PSIsContainer) { [IO.Directory]::Delete($l.FullName) } else { [IO.File]::Delete($l.FullName) }
}
$left = @(Get-ChildItem -LiteralPath $Target -Recurse -Force -Attributes ReparsePoint -ErrorAction SilentlyContinue)
if ($left.Count) { Write-Host "Some links could not be removed; stopping." -ForegroundColor Red; exit 1 }

# 2. The rest is plain files and hard links (removing a hard link only
#    removes this name; Steam's copy stays).
Remove-Item -LiteralPath $Target -Recurse -Force

$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'NZ Direct.lnk'
if (Test-Path $lnk) { Remove-Item $lnk -Force }
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NZDirect' -Recurse -Force -ErrorAction SilentlyContinue
if ($RemoveSettings) {
    Remove-Item (Join-Path $env:APPDATA 'NZDirect') -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "NZ Direct was removed. The Steam install was not touched." -ForegroundColor Green
