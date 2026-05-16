Param(
  [string]$PythonExe = "python",
  [switch]$Clean
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$DistDir = Join-Path $RepoRoot "dist"
$BuildDir = Join-Path $RepoRoot "build"
$AppDistDir = Join-Path $DistDir "RECT"
$AppExe = Join-Path $AppDistDir "RECT.exe"

Push-Location $RepoRoot
try {
  if ($Clean) {
    Remove-Item -Recurse -Force $BuildDir, $DistDir -ErrorAction SilentlyContinue
  }

  & $PythonExe -m pip install --upgrade pip
  & $PythonExe -m pip install -r requirements.txt

  & $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --name RECT `
    --windowed `
    --distpath $DistDir `
    --workpath $BuildDir `
    --specpath $BuildDir `
    --add-data "frontend;frontend" `
    --add-data "backend;backend" `
    --hidden-import backend.main `
    desktop\launcher.py

  if (-not (Test-Path $AppExe)) {
    throw "Expected executable was not created at $AppExe. The installer expects files under dist\RECT\."
  }

  Write-Host "Build complete: dist\RECT\RECT.exe"
  Write-Host "Installer input directory ready: dist\RECT\"
  Write-Host "Persistent SQLite data is stored in %APPDATA%\RECT unless RECT_DATA_DIR is set."
  Write-Host "To produce an installer, run Inno Setup with installer\RECT.iss"
}
finally {
  Pop-Location
}
