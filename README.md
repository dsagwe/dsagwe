# DocFind

DocFind is a local-first desktop/web document search application for PDF, Excel, TXT/CSV/LOG content. It provides indexing, boolean/phrase/wildcard/fuzzy search, faceted filtering, result preview, and lightweight file management utilities.

## Implemented capabilities

- Recursive folder indexing for `.pdf`, `.xls`, `.xlsx`, `.txt`, `.csv`, `.log`.
- SQLite + FTS5 full-text index with Porter stemming.
- Search supports:
  - Boolean operators (`AND`, `OR`, `NOT`)
  - Phrase search (`"quarterly revenue"`)
  - Wildcards (`*`, and `?` mapped to `*`)
  - Proximity (`NEAR/5` syntax)
  - Fuzzy fallback (close-match retry when no direct hits)
  - Metadata filters (type/folder/tag/date/size + Excel sheet/header)
- Ranked results with per-file score and match count.
- Match snippets with highlighted terms.
- Reference location per hit (`page:n`, `sheet:...,row:n`, `line:n`).
- Split layout UI with filters, result list/grid toggle, and preview panel.
- Index status UI (progress, last indexed, index size).
- Saved searches, recent search history, CSV export.
- Add tags and notes endpoints for file annotations.

## Run as web app

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/main.py
```

Then open `http://localhost:8000`.

## Build Windows `.exe` (standalone desktop launcher)

1. Open **PowerShell** on Windows in the repo root.
2. Run:

```powershell
./desktop/build_exe.ps1
```

3. Output executable:

```text
dist/DocFind/DocFind.exe
```

This EXE starts the local FastAPI service on a free localhost port and opens DocFind in the default browser.

## Build Windows installer (`.exe` setup wizard)

After building the standalone EXE, compile the Inno Setup script:

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\DocFind.iss
```

Installer output:

```text
dist/installer/DocFind-Setup.exe
```

## Notes

- PDF OCR for scanned pages is represented with a graceful placeholder message unless OCR dependencies are installed.
- Password-protected PDFs are detected and indexed as `needs_password` status (prompt flow can be added in desktop shell/electron wrapper).
- The app is structured to be wrapped in Electron for richer native context-menu/file operations.


## Generate Windows installer automatically (recommended)

If you cannot build on your current machine, use the included GitHub Actions workflow:

1. Push this branch to GitHub.
2. Open **Actions → Build Windows Installer**.
3. Click **Run workflow**.
4. Download `DocFind-Windows-Installer` artifact.

Artifact produced by CI:

```text
dist/installer/DocFind-Setup.exe
```
