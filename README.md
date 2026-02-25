# SHA Compliance Neon UI

This project provides a neon-themed compliance operations UI built with Streamlit.

## Theme specification implemented

- Background: `#050508`
- Primary neon (cyan): `#00F5FF`
- Secondary (purple): `#BF00FF`
- Wins/positive: `#00FF88`
- Losses/alerts: `#FF2D55`
- Text: `#E8F4FD`
- Muted: `#4A6274`
- Cards: `rgba(0,245,255,0.03)` background + `rgba(0,245,255,0.08)` border
- Font: mono for all labels/numbers
- Neon glow: text-shadow + drop-shadow
- Motion: staggered fade-up load effect (Framer Motion hook + CSS animation fallback)

## Pages

- `/dashboard`
  - KPI stat cards
  - Task list
  - Pending approvals
- `/tasks`
  - Task tracker
  - Status badges: `COMPLETED`, `IN PROGRESS`, `BLOCKED`, `PENDING`
- `/inference`
  - Input NHIF contribution and infer salary band + implied SHA contribution range
  - Input SHA contribution and infer salary + possible NHIF contribution(s)
- `/batch-audit`
  - Upload NHIF and SHA extracts in one run
  - Run readiness checks for both sources
  - Reconcile and audit all records in bulk
  - Generate report pack downloads (CSV + Excel)

## Batch audit report outputs

`/batch-audit` generates:

- Full reconciled dataset (`batch_audit_reconciled.csv`)
- Employer-level summary (`employer_audit_summary.csv`)
- Month-level summary (`monthly_audit_summary.csv`)
- Excel pack (`sha_batch_audit_report.xlsx`) with totals, employer summary, monthly summary, flagged records

Minimum columns for uploads:

**NHIF extract**
- `employer`
- `employer_pin`
- `employee_id`
- `id_number`
- `payroll_month`
- `gross_salary`
- `nhif_remitted_amount`

**SHA extract**
- `employer`
- `employer_pin`
- `employee_id`
- `id_number`
- `payroll_month`
- `gross_salary`
- `sha_remitted_amount`

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Build an executable file

Yes — you can generate an executable bundle for the app with PyInstaller.

### Windows `.exe` (recommended via GitHub Actions)

This repo now includes a workflow at `.github/workflows/build-windows-exe.yml` that builds a native Windows executable on `windows-latest`.

1. Push your code to GitHub.
2. Open **Actions** → **Build Windows Executable**.
3. Click **Run workflow**.
4. Download artifact: `sha_compliance_windows_exe`.
5. Inside it, run: `sha_compliance_app.exe`.

1. Install build dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-build.txt
```

2. Build executable:

```bash
python build_executable.py
```

3. Output location:

- Linux/macOS binary: `dist/sha_compliance_app/sha_compliance_app`
- Windows executable (build on Windows): `dist/sha_compliance_app/sha_compliance_app.exe`

Notes:
- Build on the same OS you plan to run on (Windows builds Windows `.exe`).
- The executable starts Streamlit and runs `app.py` through `launcher.py`.

## Deploy (Streamlit Community Cloud)

1. Push this repository to GitHub.
2. Open Streamlit Community Cloud and create a new app.
3. Select repo + branch + `app.py` as the entrypoint.
4. Deploy.
