Param(
  [string]$PythonExe = "python",
  [switch]$Clean
)

$ErrorActionPreference = "Stop"

if ($Clean) {
  Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r requirements.txt

& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --name RECT `
  --windowed `
  --add-data "frontend;frontend" `
  --add-data "backend;backend" `
  --hidden-import backend.main `
  desktop\launcher.py

Write-Host "Build complete: dist\RECT\RECT.exe"
Write-Host "Persistent SQLite data is stored in %APPDATA%\RECT unless RECT_DATA_DIR is set."
Write-Host "To produce an installer, run Inno Setup with installer\RECT.iss"
