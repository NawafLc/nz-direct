<#
Builds the release files into .\build:
  NZDirect-Setup.exe      setup wizard (everything inside)
  NZDirect-FriendKit.zip  the same files as a zip with "Setup NZ Direct.cmd"

Needs Python 3.12+ with PyInstaller (pip install pyinstaller), a boiii.exe
built from boiii-free with boiii\boiii-free.patch applied, and boiii's data
folder (created by any boiii run, %LOCALAPPDATA%\boiii\data).

  .\build.ps1 -BoiiiExe ..\boiii-free\build\bin\x64\Release\boiii.exe
#>
param(
    [string]$BoiiiExe = (Join-Path $PSScriptRoot '..\boiii-free\build\bin\x64\Release\boiii.exe'),
    [string]$BoiiiData = (Join-Path $env:LOCALAPPDATA 'boiii\data'),
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$out = Join-Path $root 'build'
$work = Join-Path $out 'pyinstaller'
$kit = Join-Path $out 'kit'

foreach ($p in $BoiiiExe, (Join-Path $BoiiiData 'launcher')) {
    if (-not (Test-Path $p)) { throw "Missing: $p" }
}
if (Test-Path $kit) { Remove-Item $kit -Recurse -Force }
New-Item -ItemType Directory -Force $out, $work | Out-Null

function PyInstaller([string[]]$arguments) {
    & $Python -m PyInstaller --noconfirm --onefile --noconsole --distpath $out --workpath $work --specpath $work @arguments
    if ($LASTEXITCODE) { throw "PyInstaller failed ($LASTEXITCODE)" }
}

Write-Host "== NZDirect.exe (launcher)" -ForegroundColor Cyan
$l = Join-Path $root 'launcher'
PyInstaller @('--name', 'NZDirect', '--icon', $BoiiiExe,
    '--add-data', "$l\nzdirect_summary.gsc;.", '--add-data', "$l\nzdirect_bgb.lua;.",
    "$l\nz_launcher.pyw")

Write-Host "== kit" -ForegroundColor Cyan
New-Item -ItemType Directory -Force "$kit\files\launcher", "$kit\files\source", "$kit\files\boiii_data" | Out-Null
Copy-Item "$root\setup\*" $kit
Copy-Item $BoiiiExe "$kit\files\boiii.exe"
Copy-Item "$out\NZDirect.exe", "$l\nzdirect_summary.gsc", "$l\nzdirect_bgb.lua" "$kit\files\launcher"
Copy-Item "$l\nz_launcher.pyw", "$l\nz_net.py" "$kit\files\source"
Copy-Item "$BoiiiData\*" "$kit\files\boiii_data" -Recurse

Write-Host "== NZDirect-FriendKit.zip" -ForegroundColor Cyan
$zip = Join-Path $out 'NZDirect-FriendKit.zip'
& $Python -c @"
import pathlib, sys, zipfile
kit, zip_path = pathlib.Path(sys.argv[1]), sys.argv[2]
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in sorted(kit.rglob('*')):
        if p.is_file():
            z.write(p, 'NZDirect-FriendKit/' + p.relative_to(kit).as_posix())
"@ $kit $zip
if ($LASTEXITCODE) { throw "zip failed" }

Write-Host "== NZDirect-Setup.exe (installer)" -ForegroundColor Cyan
PyInstaller @('--name', 'NZDirect-Setup', '--icon', $BoiiiExe,
    '--add-data', "$kit;kit", "$root\installer\nzdirect_setup.py")

Get-Item "$out\NZDirect-Setup.exe", $zip | Select-Object Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } } | Format-Table
