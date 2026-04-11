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

# Build a Windows desktop executable folder that includes backend/frontend assets.
& $PythonExe -m PyInstaller `
  --noconfirm `
  --clean `
  --name DocFind `
  --windowed `
  --add-data "frontend;frontend" `
  --add-data "backend;backend" `
  --hidden-import backend.main `
  desktop\launcher.py

Write-Host "Build complete: dist\\DocFind\\DocFind.exe"
Write-Host "To produce an installer, run Inno Setup with installer\\DocFind.iss"
