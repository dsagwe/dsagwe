# RECT — Relational Engagement & Compliance Tracker

RECT is a local-first compliance intelligence platform for Social Health Insurance Fund (SHIF) employer enforcement operations. It transforms static arrears spreadsheets into a relational, longitudinal, evidence-driven workflow system with employer master records, monthly remittance history, immutable engagement timelines, compliance cases, automated demand notices, audit logs, and deployment tooling for Windows workstations.

## 1. Problem analysis

Traditional Excel/CSV compliance workflows fail at operational enforcement because they are point-in-time snapshots. They cannot preserve longitudinal employer behaviour, prove who contacted an employer and when, track commitments, detect repeat offenders, automate notices, or assemble legally defensible evidence bundles. RECT addresses those gaps by making every employer, remittance period, case, engagement, notice, synchronization run, and audit event a relational record.

## 2. Proposed architecture

RECT uses a modular local-first architecture:

- **Frontend:** lightweight self-contained HTML/CSS/JavaScript dashboard served by FastAPI for registry search, case queues, remittance views, timeline review, PDF notice generation, and CSV export.
- **Backend:** Python FastAPI service containing compliance calculations, workflow orchestration, audit logging, notice generation, and integration boundaries.
- **Database:** SQLite in `%APPDATA%\RECT` on Windows or `~/.rect` on Linux/macOS, with schema choices that are PostgreSQL-ready.
- **Document engine:** ReportLab creates notices; pdfrw can merge generated content over an official letterhead PDF template.
- **Deployment:** PyInstaller desktop launcher and Inno Setup installer; Docker is included for local web deployment.

## 3. Database schema

Core tables are created automatically at startup:

| Table | Purpose |
| --- | --- |
| `employers` | SHA employer code, employer name, KRA PIN, registration details, industry, county/sub-county, contacts, current arrears, penalties, risk score, compliance status. |
| `remittances` | Monthly amount due, paid, balance, 2% penalty, payment date, source, and history by employer/period. |
| `compliance_cases` | Open/closed enforcement cases, stage, priority, assigned officer, due date, closure metadata. |
| `engagements` | Immutable calls, emails, SMS, field visits, notices, escalations, tribunal actions, commitments, follow-ups, outcomes, hashes, and evidence URIs. |
| `notices` | Generated demand notice metadata and PDF paths. |
| `sync_logs` | Authorized API/RPA synchronization attempts and outcomes. |
| `audit_logs` | Actor, action, entity, JSON before/after snapshots, timestamp, and hash for evidentiary traceability. |

## 4. Core modules and workflows

### Employer master registry

The registry stores SHA employer code, employer name, KRA PIN, registration date, industry classification, location, contacts, current compliance status, arrears exposure, penalty exposure, risk score, and default streak.

### Remittance history engine

Each monthly remittance row calculates:

```text
outstanding_balance = max(0, amount_due - amount_paid)
statutory_penalty = outstanding_balance * 0.02
```

Employer rollups are recalculated after each remittance update and drive case creation, risk scoring, and dashboard analytics.

### Engagement history engine

Engagement entries are append-only. SQLite triggers prevent update and delete operations on `engagements`, preserving legally defensible interaction history. Every demand notice generation also writes an engagement event with a PDF evidence URI.

### Compliance case management

Cases support stages such as:

1. `soft_reminder`
2. `first_demand`
3. `final_demand`
4. `litigation_escalation`
5. `tribunal_action`
6. `closed`

RECT automatically opens a case when arrears are detected and prioritizes cases based on risk score and arrears behaviour.

### Automated demand notices

A compliance officer selects a notice type and employer. RECT calculates arrears and penalties, generates a PDF, stores it under the persistent data directory, inserts a notice record, and logs an immutable demand-notice engagement.

Supported templates:

- First-time offender first demand
- Repeat offender final demand
- Litigation warning notice

If an official letterhead PDF path is supplied, pdfrw overlays RECT-generated notice content onto the template.

### Dashboards and analytics

The dashboard exposes:

- Total employers monitored
- Total arrears exposure
- 2% penalty exposure
- Critical case counts
- Average risk score
- Top defaulters
- County exposure
- Follow-up queue
- Employer-level timeline and remittance drill-downs

## 5. Recommended technology stack

| Layer | Technology | Rationale |
| --- | --- | --- |
| UI | Self-contained HTML/CSS/JavaScript served by FastAPI | No Node build or CDN required; suitable for bundled desktop deployment. |
| API | FastAPI + Pydantic | Typed API contracts, fast local performance, OpenAPI support. |
| Database | SQLite | Local-first, low-resource workstation friendly, easy backup. |
| Future database | PostgreSQL | Same relational model can be migrated for multi-user scale. |
| PDFs | ReportLab + pdfrw | Dynamic notices and official letterhead overlay. |
| Desktop packaging | PyInstaller | Creates Windows executable without requiring Python on user workstation. |
| Installer | Inno Setup | Familiar Windows setup wizard and shortcuts. |
| Container | Docker | Optional web deployment mode. |

## 6. Security model

RECT includes a practical security foundation for a local-first compliance workstation:

- Role-aware API dependencies for compliance officer, supervisor, legal officer, auditor, and administrator flows.
- Actor headers are recorded on audit events and engagements; production SSO or Windows identity integration can replace the local headers.
- Immutable engagement triggers prevent tampering with evidentiary history.
- Audit logs store JSON before/after snapshots and SHA-256 hashes.
- Persistent data lives outside the install directory to survive upgrades and support controlled backups.
- Integration runs are logged and explicitly constrained to authorized API or officer-driven MFA RPA workflows.

Recommended production hardening:

- Replace header identity with Windows Integrated Authentication, OAuth2/OIDC, or organization SSO.
- Encrypt SQLite at rest using SQLCipher where policy requires it.
- Store API/RPA credentials in Windows Credential Manager or an enterprise vault.
- Add MFA-compatible session timeout and workstation lock policies.
- Digitally sign generated PDFs and installer binaries.

## 7. Integration strategy for SHA systems

RECT deliberately does not bypass authentication, scrape without authorization, or reverse engineer protected systems. The preferred hierarchy is:

### Pathway A — authorized API integration

- Establish SHA/DHA/AfyaLink API access through formal channels.
- Use OAuth2 or client credentials where approved.
- Support FHIR R4 JSON endpoints if provided for employer/remittance resources.
- Implement incremental sync based on timestamps, page cursors, or source sequence IDs.
- Log each sync in `sync_logs` and each upsert in `audit_logs`.

### Pathway B — officer-authorized RPA

If APIs are unavailable and the user has authorized portal access:

- Use Playwright or Selenium as a controlled connector.
- Open the official login page for the officer.
- Pause for username/password/OTP/MFA entry by the human officer.
- Extract only datasets the officer is authorized to view.
- Store sync provenance and never persist plaintext credentials.

The `/api/sync/run` endpoint currently records the connector boundary and compliance policy, ready for an approved connector implementation.

## 8. Deployment architecture

- **Development web mode:** `python backend/main.py` then open `http://127.0.0.1:8000`.
- **Desktop mode:** `RECT.exe` starts the local FastAPI service on an available localhost port and opens the browser.
- **Persistence:** SQLite database, PDFs, evidence bundles, and templates are stored in `%APPDATA%\RECT` on Windows or `~/.rect` elsewhere.
- **Upgrade-safe:** application binaries are separate from operational data.

## 9. Implementation roadmap

### Phase 1 — Foundation

- Employer registry, remittance engine, penalty calculations, dashboard, search, case queue, engagement timeline.
- Local SQLite persistence and desktop launcher.

### Phase 2 — Enforcement operations

- Batch imports from CSV/XLSX.
- Advanced filtering by county, industry, risk, overdue days, penalty exposure, and engagement status.
- Bulk notice generation and evidence bundle export.
- Officer productivity reporting.

### Phase 3 — Security and governance

- Real authentication provider.
- SQLCipher or OS-level encryption.
- Digital signatures for notices and audit export bundles.
- Backup/restore workflows.

### Phase 4 — SHA integration

- Implement approved API connector.
- Add OAuth2 token refresh and incremental sync scheduler.
- If no API exists, implement MFA-aware RPA connector under approved operating procedures.

### Phase 5 — Intelligence layer

- Predictive default-risk models.
- NLP summaries of engagement histories.
- Suggested next enforcement actions.
- Repeat offender cohort analysis and tribunal readiness scoring.

## 10. Project structure

```text
backend/main.py                    FastAPI app, schema, rules, PDFs, APIs
frontend/index.html                React/Tailwind shell
frontend/main.js                   Dashboard and officer workflows
desktop/launcher.py                Local desktop launcher
desktop/build_exe.ps1              PyInstaller build script
installer/RECT.iss                 Inno Setup installer script
Dockerfile                         Optional container deployment
requirements.txt                   Python dependencies
.github/workflows/windows-installer.yml  CI build for Windows installer
```

## 11. API design

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Runtime and data-directory status. |
| `GET` | `/api/dashboard` | Arrears, risk, county exposure, and case queue metrics. |
| `GET` | `/api/employers` | Search/filter employer registry. |
| `POST` | `/api/employers` | Create employer master record. |
| `GET` | `/api/employers/{id}` | Employer profile, remittances, cases, notices, engagements. |
| `POST` | `/api/employers/{id}/remittances` | Insert/update monthly remittance and recalculate penalties. |
| `POST` | `/api/employers/{id}/engagements` | Append immutable engagement. |
| `GET` | `/api/cases` | Open case queue. |
| `POST` | `/api/cases` | Create enforcement case. |
| `POST` | `/api/notices` | Generate one or more demand notices. |
| `GET` | `/api/notices/{id}/download` | Download generated notice PDF. |
| `GET` | `/api/export/employers.csv` | Export registry. |
| `POST` | `/api/sync/run` | Log authorized API/RPA synchronization boundary. |
| `GET` | `/api/audit` | Auditor/supervisor audit log view. |

## 12. UI/UX workflow descriptions

1. Officer opens RECT and sees arrears exposure, penalty exposure, critical count, and average risk.
2. Officer searches for an employer by name, SHA code, or KRA PIN.
3. Employer profile shows arrears, penalties, risk, default streak, remittance rows, open cases, and immutable timeline.
4. Officer logs a call, visit, email, SMS, or commitment; RECT appends it to the timeline.
5. Officer generates first demand, final demand, or litigation-warning notice; RECT creates a PDF and records it as an engagement.
6. Supervisor reviews the follow-up queue ordered by priority and due date.
7. Auditor/legal officer exports audit logs and evidence material for tribunal or litigation preparation.

## 13. Packaging instructions

### Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/main.py
```

Open `http://127.0.0.1:8000`.

### Build Windows executable

Run in PowerShell on Windows:

```powershell
./desktop/build_exe.ps1 -Clean
```

Output:

```text
dist/RECT/RECT.exe
```

### Build installer

After building the executable folder:

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\RECT.iss
```

Output:

```text
dist/installer/RECT-Setup.exe
```

## 14. Sample code scaffold

Creating a remittance record through the API:

```bash
curl -X POST http://127.0.0.1:8000/api/employers/{id}/remittances \
  -H 'Content-Type: application/json' \
  -H 'x-officer-id: officer-001' \
  -H 'x-officer-name: Compliance Officer' \
  -H 'x-role: compliance_officer' \
  -d '{"period":"2026-05","amount_due":100000,"amount_paid":25000,"source":"manual"}'
```

Generating a notice:

```bash
curl -X POST http://127.0.0.1:8000/api/notices \
  -H 'Content-Type: application/json' \
  -H 'x-officer-id: officer-001' \
  -H 'x-officer-name: Compliance Officer' \
  -H 'x-role: compliance_officer' \
  -d '{"employer_ids":["EMPLOYER_UUID"],"notice_type":"final_demand"}'
```

## 15. Docker configuration

Build and run:

```bash
docker build -t rect .
docker run --rm -p 8000:8000 -v rect-data:/data/rect rect
```

## 16. PyInstaller configuration

The PyInstaller build is in `desktop/build_exe.ps1`. It bundles `backend` and `frontend`, names the app `RECT`, and preserves data in `%APPDATA%\RECT` instead of inside the install directory.

## 17. Demand notice generation workflow

1. Officer selects an employer and notice type.
2. Backend fetches active arrears periods.
3. Backend recalculates current arrears and 2% penalties.
4. ReportLab creates notice content.
5. Optional pdfrw overlay applies official letterhead PDF.
6. Notice PDF is stored in the persistent `notices` directory.
7. `notices` row is inserted.
8. Immutable `engagements` row is inserted with PDF evidence URI.
9. `audit_logs` row captures the action and hash.

## 18. Audit logging strategy

RECT logs every material action with:

- Actor ID and name
- Action type
- Entity type and entity ID
- JSON before and after snapshots where applicable
- Timestamp
- SHA-256 hash of the event material

Engagement entries have their own event hash and cannot be modified or deleted through the database due to triggers.

## 19. Compliance rule engine logic

Implemented baseline rules:

- 2% penalty on outstanding balance.
- Consecutive default month calculation from latest remittance period backwards.
- Automatic status assignment: `compliant`, `in_default`, or `critical`.
- Automatic case creation when arrears exist.
- Escalated case stage when default streak reaches three months.
- Risk score based on default streak, arrears magnitude, and engagement scarcity.

## 20. Future enhancements

- CSV/XLSX import wizard for 42,000+ non-compliant employers.
- Bulk PDF notice generation with queue progress and retry tracking.
- Evidence bundle generation as ZIP/PDF with timeline, notices, remittances, audit logs, and SHA sync provenance.
- Windows Credential Manager integration.
- SQLCipher-encrypted SQLite builds.
- Multi-user PostgreSQL/FastAPI deployment.
- OCR and attachment management for field evidence.
- Predictive risk model using payment behaviour, industry, county, and engagement history.
- NLP-generated engagement summaries and suggested next actions.
