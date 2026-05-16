from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pdfrw import PdfReader, PdfWriter, PageMerge

APP_NAME = "RECT"
APP_TITLE = "Relational Engagement & Compliance Tracker"
PENALTY_RATE = Decimal("0.02")


def app_data_dir() -> Path:
    if os.environ.get("RECT_DATA_DIR"):
        root = Path(os.environ["RECT_DATA_DIR"])
    elif sys.platform.startswith("win") and os.environ.get("APPDATA"):
        root = Path(os.environ["APPDATA"]) / APP_NAME
    else:
        root = Path.home() / ".rect"
    root.mkdir(parents=True, exist_ok=True)
    (root / "notices").mkdir(exist_ok=True)
    (root / "evidence_bundles").mkdir(exist_ok=True)
    (root / "templates").mkdir(exist_ok=True)
    return root


DATA_DIR = app_data_dir()
DB_PATH = Path(os.environ.get("RECT_DB_PATH", DATA_DIR / "rect.db"))


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative


FRONTEND_DIR = resource_path("frontend")


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class OfficerContext(BaseModel):
    officer_id: str
    officer_name: str
    role: str


def get_officer(
    x_officer_id: str = Header(default="system"),
    x_officer_name: str = Header(default="System Officer"),
    x_role: str = Header(default="compliance_officer"),
) -> OfficerContext:
    return OfficerContext(officer_id=x_officer_id, officer_name=x_officer_name, role=x_role)


def require_role(*roles: str):
    def dependency(officer: OfficerContext = Depends(get_officer)) -> OfficerContext:
        if officer.role not in roles and officer.role != "administrator":
            raise HTTPException(status_code=403, detail="Insufficient permissions for this compliance action")
        return officer

    return dependency


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def audit(conn: sqlite3.Connection, actor: OfficerContext, action: str, entity_type: str, entity_id: str, before: Any, after: Any) -> None:
    before_json = json.dumps(before, sort_keys=True, default=str) if before is not None else None
    after_json = json.dumps(after, sort_keys=True, default=str) if after is not None else None
    chain_material = f"{now_iso()}|{actor.officer_id}|{action}|{entity_type}|{entity_id}|{before_json}|{after_json}"
    digest = hashlib.sha256(chain_material.encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT INTO audit_logs(id, actor_id, actor_name, action, entity_type, entity_id, before_json, after_json, hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), actor.officer_id, actor.officer_name, action, entity_type, entity_id, before_json, after_json, digest, now_iso()),
    )


def setup_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS employers (
                id TEXT PRIMARY KEY,
                sha_employer_code TEXT NOT NULL UNIQUE,
                employer_name TEXT NOT NULL,
                kra_pin TEXT,
                registration_date TEXT,
                industry TEXT,
                county TEXT,
                sub_county TEXT,
                email TEXT,
                phone TEXT,
                postal_address TEXT,
                compliance_status TEXT NOT NULL DEFAULT 'unknown',
                risk_score REAL NOT NULL DEFAULT 0,
                current_arrears REAL NOT NULL DEFAULT 0,
                penalty_exposure REAL NOT NULL DEFAULT 0,
                consecutive_default_months INTEGER NOT NULL DEFAULT 0,
                last_engagement_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS remittances (
                id TEXT PRIMARY KEY,
                employer_id TEXT NOT NULL,
                period TEXT NOT NULL,
                amount_due REAL NOT NULL DEFAULT 0,
                amount_paid REAL NOT NULL DEFAULT 0,
                outstanding_balance REAL NOT NULL DEFAULT 0,
                statutory_penalty REAL NOT NULL DEFAULT 0,
                payment_date TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(employer_id, period),
                FOREIGN KEY(employer_id) REFERENCES employers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS compliance_cases (
                id TEXT PRIMARY KEY,
                employer_id TEXT NOT NULL,
                case_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'open',
                stage TEXT NOT NULL DEFAULT 'soft_reminder',
                priority INTEGER NOT NULL DEFAULT 3,
                assigned_officer_id TEXT,
                assigned_officer_name TEXT,
                opened_at TEXT NOT NULL,
                due_at TEXT,
                closed_at TEXT,
                closure_reason TEXT,
                summary TEXT,
                FOREIGN KEY(employer_id) REFERENCES employers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS engagements (
                id TEXT PRIMARY KEY,
                employer_id TEXT NOT NULL,
                case_id TEXT,
                channel TEXT NOT NULL,
                officer_id TEXT NOT NULL,
                officer_name TEXT NOT NULL,
                summary TEXT NOT NULL,
                employer_commitment TEXT,
                follow_up_deadline TEXT,
                outcome TEXT NOT NULL,
                stage_after TEXT,
                evidence_uri TEXT,
                created_at TEXT NOT NULL,
                hash TEXT NOT NULL,
                FOREIGN KEY(employer_id) REFERENCES employers(id) ON DELETE CASCADE,
                FOREIGN KEY(case_id) REFERENCES compliance_cases(id) ON DELETE SET NULL
            );

            CREATE TRIGGER IF NOT EXISTS prevent_engagement_update
            BEFORE UPDATE ON engagements
            BEGIN
              SELECT RAISE(ABORT, 'engagement history is immutable');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_engagement_delete
            BEFORE DELETE ON engagements
            BEGIN
              SELECT RAISE(ABORT, 'engagement history is immutable');
            END;

            CREATE TABLE IF NOT EXISTS notices (
                id TEXT PRIMARY KEY,
                employer_id TEXT NOT NULL,
                case_id TEXT,
                notice_type TEXT NOT NULL,
                pdf_path TEXT NOT NULL,
                arrears REAL NOT NULL,
                penalties REAL NOT NULL,
                generated_by TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                FOREIGN KEY(employer_id) REFERENCES employers(id) ON DELETE CASCADE,
                FOREIGN KEY(case_id) REFERENCES compliance_cases(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS sync_logs (
                id TEXT PRIMARY KEY,
                connector TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                records_received INTEGER NOT NULL DEFAULT 0,
                records_upserted INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT,
                hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_employers_search ON employers(employer_name, sha_employer_code, kra_pin, county, industry);
            CREATE INDEX IF NOT EXISTS idx_remittances_employer_period ON remittances(employer_id, period);
            CREATE INDEX IF NOT EXISTS idx_engagements_employer_time ON engagements(employer_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_cases_queue ON compliance_cases(status, stage, due_at, priority);
            """
        )
        seed_demo_data(conn)


def seed_demo_data(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) AS n FROM employers").fetchone()["n"]
    if existing:
        return
    system = OfficerContext(officer_id="seed", officer_name="RECT Seed", role="administrator")
    employers = [
        ("SHA-10001", "Nairobi Textiles Ltd", "P051234567A", "Manufacturing", "Nairobi", "Industrial Area", "hr@nairobtextiles.example", "+254700111222"),
        ("SHA-10002", "Pwani Logistics Cooperative", "P052222222B", "Transport", "Mombasa", "Changamwe", "accounts@pwanilogistics.example", "+254711222333"),
        ("SHA-10003", "Rift Valley Agro Processors", "P053333333C", "Agriculture", "Uasin Gishu", "Eldoret East", "payroll@rvagro.example", "+254722333444"),
    ]
    for code, name, pin, industry, county, sub_county, email, phone in employers:
        employer = EmployerCreate(
            sha_employer_code=code,
            employer_name=name,
            kra_pin=pin,
            industry=industry,
            county=county,
            sub_county=sub_county,
            email=email,
            phone=phone,
            registration_date="2024-01-01",
        )
        employer_id = create_employer(conn, employer, system, commit=False)
        for months_ago in range(5, -1, -1):
            period_date = date.today().replace(day=1) - timedelta(days=months_ago * 30)
            period = period_date.strftime("%Y-%m")
            due = Decimal("150000") + Decimal(months_ago * 10000)
            paid = Decimal("0") if months_ago in {1, 2, 3} else due
            upsert_remittance(conn, employer_id, RemittanceIn(period=period, amount_due=due, amount_paid=paid, source="seed"), system, commit=False)
        open_case_if_needed(conn, employer_id, system)
    refresh_all_employer_rollups(conn)


class EmployerCreate(BaseModel):
    sha_employer_code: str
    employer_name: str
    kra_pin: str | None = None
    registration_date: str | None = None
    industry: str | None = None
    county: str | None = None
    sub_county: str | None = None
    email: str | None = None
    phone: str | None = None
    postal_address: str | None = None


class RemittanceIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    amount_due: Decimal = Decimal("0")
    amount_paid: Decimal = Decimal("0")
    payment_date: str | None = None
    source: str = "manual"


class EngagementCreate(BaseModel):
    case_id: str | None = None
    channel: Literal["call", "email", "sms", "field_visit", "demand_notice", "escalation", "tribunal_action", "other"]
    summary: str
    employer_commitment: str | None = None
    follow_up_deadline: str | None = None
    outcome: Literal["contacted", "no_response", "promise_to_pay", "paid", "disputed", "escalated", "notice_served"]
    stage_after: str | None = None
    evidence_uri: str | None = None


class CaseCreate(BaseModel):
    employer_id: str
    stage: str = "soft_reminder"
    priority: int = 3
    assigned_officer_id: str | None = None
    assigned_officer_name: str | None = None
    due_at: str | None = None
    summary: str | None = None


class NoticeRequest(BaseModel):
    employer_ids: list[str]
    notice_type: Literal["first_demand", "final_demand", "litigation_warning"] = "first_demand"
    template_path: str | None = None


class SyncRequest(BaseModel):
    connector: Literal["api", "rpa"]
    mode: Literal["dry_run", "incremental", "full"] = "dry_run"
    endpoint: str | None = None


def recalculate_employer(conn: sqlite3.Connection, employer_id: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT period, outstanding_balance, statutory_penalty FROM remittances WHERE employer_id=? ORDER BY period",
        (employer_id,),
    ).fetchall()
    arrears = sum(Decimal(str(row["outstanding_balance"])) for row in rows)
    penalties = sum(Decimal(str(row["statutory_penalty"])) for row in rows)
    consecutive = 0
    for row in reversed(rows):
        if Decimal(str(row["outstanding_balance"])) > 0:
            consecutive += 1
        else:
            break
    engagement_count = conn.execute("SELECT COUNT(*) AS n FROM engagements WHERE employer_id=?", (employer_id,)).fetchone()["n"]
    risk = min(100, int(consecutive * 18 + (arrears / Decimal("10000")) + max(0, 6 - engagement_count) * 2))
    status = "compliant"
    if arrears > 0:
        status = "critical" if consecutive >= 3 or arrears >= Decimal("500000") else "in_default"
    conn.execute(
        """
        UPDATE employers
        SET current_arrears=?, penalty_exposure=?, consecutive_default_months=?, risk_score=?, compliance_status=?, updated_at=?
        WHERE id=?
        """,
        (float(arrears), float(penalties), consecutive, risk, status, now_iso(), employer_id),
    )
    return {"current_arrears": float(arrears), "penalty_exposure": float(penalties), "consecutive_default_months": consecutive, "risk_score": risk, "compliance_status": status}


def refresh_all_employer_rollups(conn: sqlite3.Connection) -> None:
    for row in conn.execute("SELECT id FROM employers").fetchall():
        recalculate_employer(conn, row["id"])


def create_employer(conn: sqlite3.Connection, payload: EmployerCreate, actor: OfficerContext, commit: bool = True) -> str:
    employer_id = str(uuid.uuid4())
    timestamp = now_iso()
    record = payload.model_dump()
    conn.execute(
        """
        INSERT INTO employers(id, sha_employer_code, employer_name, kra_pin, registration_date, industry, county, sub_county, email, phone, postal_address, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            employer_id,
            payload.sha_employer_code,
            payload.employer_name,
            payload.kra_pin,
            payload.registration_date,
            payload.industry,
            payload.county,
            payload.sub_county,
            payload.email,
            payload.phone,
            payload.postal_address,
            timestamp,
            timestamp,
        ),
    )
    audit(conn, actor, "create", "employer", employer_id, None, record)
    if commit:
        conn.commit()
    return employer_id


def upsert_remittance(conn: sqlite3.Connection, employer_id: str, payload: RemittanceIn, actor: OfficerContext, commit: bool = True) -> str:
    employer = conn.execute("SELECT id FROM employers WHERE id=?", (employer_id,)).fetchone()
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    existing = row_to_dict(conn.execute("SELECT * FROM remittances WHERE employer_id=? AND period=?", (employer_id, payload.period)).fetchone())
    amount_due = money(payload.amount_due)
    amount_paid = money(payload.amount_paid)
    outstanding = max(Decimal("0"), amount_due - amount_paid)
    penalty = money(outstanding * PENALTY_RATE)
    timestamp = now_iso()
    if existing:
        remittance_id = existing["id"]
        conn.execute(
            """
            UPDATE remittances
            SET amount_due=?, amount_paid=?, outstanding_balance=?, statutory_penalty=?, payment_date=?, source=?, updated_at=?
            WHERE id=?
            """,
            (float(amount_due), float(amount_paid), float(outstanding), float(penalty), payload.payment_date, payload.source, timestamp, remittance_id),
        )
        action = "update"
    else:
        remittance_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO remittances(id, employer_id, period, amount_due, amount_paid, outstanding_balance, statutory_penalty, payment_date, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (remittance_id, employer_id, payload.period, float(amount_due), float(amount_paid), float(outstanding), float(penalty), payload.payment_date, payload.source, timestamp, timestamp),
        )
        action = "create"
    after = payload.model_dump(mode="json") | {"outstanding_balance": float(outstanding), "statutory_penalty": float(penalty)}
    audit(conn, actor, action, "remittance", remittance_id, existing, after)
    recalculate_employer(conn, employer_id)
    if outstanding > 0:
        open_case_if_needed(conn, employer_id, actor)
    if commit:
        conn.commit()
    return remittance_id


def open_case_if_needed(conn: sqlite3.Connection, employer_id: str, actor: OfficerContext) -> str | None:
    employer = conn.execute("SELECT * FROM employers WHERE id=?", (employer_id,)).fetchone()
    if not employer or employer["current_arrears"] <= 0:
        return None
    active = conn.execute("SELECT id FROM compliance_cases WHERE employer_id=? AND status='open'", (employer_id,)).fetchone()
    if active:
        return active["id"]
    case_id = str(uuid.uuid4())
    case_number = f"RECT-{datetime.now(UTC).strftime('%Y%m%d')}-{employer['sha_employer_code']}"
    stage = "final_demand" if employer["consecutive_default_months"] >= 3 else "soft_reminder"
    priority = 1 if employer["risk_score"] >= 75 else 2 if employer["risk_score"] >= 50 else 3
    conn.execute(
        """
        INSERT INTO compliance_cases(id, employer_id, case_number, status, stage, priority, assigned_officer_id, assigned_officer_name, opened_at, due_at, summary)
        VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
        """,
        (case_id, employer_id, case_number, stage, priority, actor.officer_id, actor.officer_name, now_iso(), (date.today() + timedelta(days=7)).isoformat(), "Automatically opened because arrears were detected."),
    )
    audit(conn, actor, "create", "case", case_id, None, {"employer_id": employer_id, "stage": stage, "priority": priority})
    return case_id


def create_engagement(conn: sqlite3.Connection, employer_id: str, payload: EngagementCreate, actor: OfficerContext) -> str:
    employer = conn.execute("SELECT id FROM employers WHERE id=?", (employer_id,)).fetchone()
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    engagement_id = str(uuid.uuid4())
    timestamp = now_iso()
    digest = hashlib.sha256(f"{engagement_id}|{employer_id}|{payload.summary}|{timestamp}|{actor.officer_id}".encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT INTO engagements(id, employer_id, case_id, channel, officer_id, officer_name, summary, employer_commitment, follow_up_deadline, outcome, stage_after, evidence_uri, created_at, hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (engagement_id, employer_id, payload.case_id, payload.channel, actor.officer_id, actor.officer_name, payload.summary, payload.employer_commitment, payload.follow_up_deadline, payload.outcome, payload.stage_after, payload.evidence_uri, timestamp, digest),
    )
    conn.execute("UPDATE employers SET last_engagement_at=?, updated_at=? WHERE id=?", (timestamp, timestamp, employer_id))
    if payload.case_id and payload.stage_after:
        conn.execute("UPDATE compliance_cases SET stage=? WHERE id=?", (payload.stage_after, payload.case_id))
    audit(conn, actor, "create", "engagement", engagement_id, None, payload.model_dump())
    recalculate_employer(conn, employer_id)
    return engagement_id


def generate_notice_pdf(conn: sqlite3.Connection, employer_id: str, notice_type: str, actor: OfficerContext, template_path: str | None = None) -> str:
    employer = row_to_dict(conn.execute("SELECT * FROM employers WHERE id=?", (employer_id,)).fetchone())
    if not employer:
        raise HTTPException(status_code=404, detail="Employer not found")
    remittances = [row_to_dict(row) for row in conn.execute("SELECT * FROM remittances WHERE employer_id=? AND outstanding_balance > 0 ORDER BY period", (employer_id,)).fetchall()]
    active_case = conn.execute("SELECT id FROM compliance_cases WHERE employer_id=? AND status='open' ORDER BY opened_at DESC LIMIT 1", (employer_id,)).fetchone()
    notice_id = str(uuid.uuid4())
    safe_code = employer["sha_employer_code"].replace("/", "-")
    output_path = DATA_DIR / "notices" / f"{safe_code}-{notice_type}-{notice_id[:8]}.pdf"
    arrears = money(employer["current_arrears"])
    penalties = money(employer["penalty_exposure"])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=24 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    title = {
        "first_demand": "FIRST DEMAND NOTICE FOR OUTSTANDING SHIF REMITTANCES",
        "final_demand": "FINAL DEMAND NOTICE FOR REPEAT NON-REMITTANCE",
        "litigation_warning": "LITIGATION WARNING AND SANCTION ESCALATION NOTICE",
    }[notice_type]
    story: list[Any] = [Paragraph("SOCIAL HEALTH AUTHORITY", styles["Title"]), Paragraph(APP_TITLE, styles["Heading2"]), Spacer(1, 8 * mm)]
    story.extend(
        [
            Paragraph(title, styles["Heading1"]),
            Paragraph(f"Date: {date.today().isoformat()}", styles["Normal"]),
            Paragraph(f"Employer: <b>{employer['employer_name']}</b>", styles["Normal"]),
            Paragraph(f"SHA Employer Code: {employer['sha_employer_code']} | KRA PIN: {employer.get('kra_pin') or 'N/A'}", styles["Normal"]),
            Spacer(1, 5 * mm),
            Paragraph(
                "Our records indicate outstanding statutory social health insurance remittances. "
                "This notice is generated from the RECT compliance case record and should be reconciled immediately.",
                styles["BodyText"],
            ),
            Spacer(1, 4 * mm),
        ]
    )
    table_rows = [["Period", "Amount Due", "Paid", "Outstanding", "2% Penalty"]]
    for item in remittances:
        table_rows.append([
            item["period"],
            f"KES {item['amount_due']:,.2f}",
            f"KES {item['amount_paid']:,.2f}",
            f"KES {item['outstanding_balance']:,.2f}",
            f"KES {item['statutory_penalty']:,.2f}",
        ])
    table_rows.append(["TOTAL", "", "", f"KES {arrears:,.2f}", f"KES {penalties:,.2f}"])
    table = Table(table_rows, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecfeff")),
    ]))
    story.append(table)
    story.extend([
        Spacer(1, 5 * mm),
        Paragraph("Required action: settle the outstanding balance and provide proof of payment within seven days, unless a shorter statutory deadline applies to an escalated case.", styles["BodyText"]),
        Paragraph(f"Generated by: {actor.officer_name} ({actor.officer_id})", styles["Normal"]),
        Paragraph(f"RECT Notice ID: {notice_id}", styles["Normal"]),
    ])
    doc.build(story)

    if template_path:
        template = PdfReader(template_path)
        overlay = PdfReader(fdata=buffer.getvalue())
        for idx, page in enumerate(overlay.pages):
            base = template.pages[min(idx, len(template.pages) - 1)]
            PageMerge(base).add(page).render()
        PdfWriter(str(output_path), trailer=template).write()
    else:
        output_path.write_bytes(buffer.getvalue())

    case_id = active_case["id"] if active_case else None
    conn.execute(
        """
        INSERT INTO notices(id, employer_id, case_id, notice_type, pdf_path, arrears, penalties, generated_by, generated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (notice_id, employer_id, case_id, notice_type, str(output_path), float(arrears), float(penalties), actor.officer_id, now_iso()),
    )
    engagement = EngagementCreate(
        case_id=case_id,
        channel="demand_notice",
        summary=f"Generated {notice_type.replace('_', ' ')} for KES {arrears:,.2f} arrears and KES {penalties:,.2f} penalties.",
        outcome="notice_served",
        stage_after="final_demand" if notice_type == "final_demand" else "litigation_escalation" if notice_type == "litigation_warning" else "first_demand",
        evidence_uri=str(output_path),
    )
    create_engagement(conn, employer_id, engagement, actor)
    audit(conn, actor, "create", "notice", notice_id, None, {"pdf_path": str(output_path), "notice_type": notice_type})
    return notice_id


app = FastAPI(title=APP_TITLE, version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1", "http://localhost"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup() -> None:
    setup_db()


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    index = FRONTEND_DIR / "index.html"
    return index.read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "app": APP_NAME, "data_dir": str(DATA_DIR), "db_path": str(DB_PATH)}


@app.get("/api/dashboard")
def dashboard() -> dict[str, Any]:
    with connect() as conn:
        refresh_all_employer_rollups(conn)
        summary = row_to_dict(conn.execute(
            """
            SELECT COUNT(*) AS total_employers,
                   SUM(current_arrears) AS total_arrears,
                   SUM(penalty_exposure) AS total_penalties,
                   AVG(risk_score) AS avg_risk,
                   SUM(CASE WHEN compliance_status='critical' THEN 1 ELSE 0 END) AS critical_count
            FROM employers
            """
        ).fetchone())
        top_defaulters = [row_to_dict(row) for row in conn.execute("SELECT * FROM employers ORDER BY current_arrears DESC LIMIT 10").fetchall()]
        county = [row_to_dict(row) for row in conn.execute("SELECT county, COUNT(*) AS employers, SUM(current_arrears) AS arrears FROM employers GROUP BY county ORDER BY arrears DESC").fetchall()]
        queue = [row_to_dict(row) for row in conn.execute("SELECT c.*, e.employer_name, e.sha_employer_code, e.current_arrears, e.risk_score FROM compliance_cases c JOIN employers e ON e.id=c.employer_id WHERE c.status='open' ORDER BY c.priority, c.due_at LIMIT 25").fetchall()]
    return {"summary": summary, "top_defaulters": top_defaulters, "county_exposure": county, "follow_up_queue": queue}


@app.get("/api/employers")
def list_employers(
    q: str = "",
    county: str | None = None,
    industry: str | None = None,
    status: str | None = None,
    min_risk: int | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
) -> dict[str, Any]:
    clauses = []
    params: list[Any] = []
    if q:
        clauses.append("(employer_name LIKE ? OR sha_employer_code LIKE ? OR kra_pin LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if county:
        clauses.append("county=?")
        params.append(county)
    if industry:
        clauses.append("industry=?")
        params.append(industry)
    if status:
        clauses.append("compliance_status=?")
        params.append(status)
    if min_risk is not None:
        clauses.append("risk_score>=?")
        params.append(min_risk)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS n FROM employers {where}", params).fetchone()["n"]
        rows = [row_to_dict(row) for row in conn.execute(f"SELECT * FROM employers {where} ORDER BY risk_score DESC, current_arrears DESC LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()]
    return {"total": total, "items": rows}


@app.post("/api/employers")
def add_employer(payload: EmployerCreate, actor: OfficerContext = Depends(require_role("compliance_officer", "supervisor"))) -> dict[str, str]:
    with connect() as conn:
        employer_id = create_employer(conn, payload, actor)
    return {"id": employer_id}


@app.get("/api/employers/{employer_id}")
def get_employer(employer_id: str) -> dict[str, Any]:
    with connect() as conn:
        employer = row_to_dict(conn.execute("SELECT * FROM employers WHERE id=?", (employer_id,)).fetchone())
        if not employer:
            raise HTTPException(status_code=404, detail="Employer not found")
        remittances = [row_to_dict(row) for row in conn.execute("SELECT * FROM remittances WHERE employer_id=? ORDER BY period DESC", (employer_id,)).fetchall()]
        engagements = [row_to_dict(row) for row in conn.execute("SELECT * FROM engagements WHERE employer_id=? ORDER BY created_at DESC", (employer_id,)).fetchall()]
        cases = [row_to_dict(row) for row in conn.execute("SELECT * FROM compliance_cases WHERE employer_id=? ORDER BY opened_at DESC", (employer_id,)).fetchall()]
        notices = [row_to_dict(row) for row in conn.execute("SELECT * FROM notices WHERE employer_id=? ORDER BY generated_at DESC", (employer_id,)).fetchall()]
    return {"employer": employer, "remittances": remittances, "engagements": engagements, "cases": cases, "notices": notices}


@app.post("/api/employers/{employer_id}/remittances")
def save_remittance(employer_id: str, payload: RemittanceIn, actor: OfficerContext = Depends(require_role("compliance_officer", "supervisor"))) -> dict[str, str]:
    with connect() as conn:
        remittance_id = upsert_remittance(conn, employer_id, payload, actor)
    return {"id": remittance_id}


@app.post("/api/employers/{employer_id}/engagements")
def save_engagement(employer_id: str, payload: EngagementCreate, actor: OfficerContext = Depends(require_role("compliance_officer", "supervisor", "legal_officer"))) -> dict[str, str]:
    with connect() as conn:
        engagement_id = create_engagement(conn, employer_id, payload, actor)
        conn.commit()
    return {"id": engagement_id}


@app.get("/api/cases")
def list_cases(status: str = "open", stage: str | None = None) -> dict[str, Any]:
    params: list[Any] = [status]
    stage_clause = ""
    if stage:
        stage_clause = " AND c.stage=?"
        params.append(stage)
    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute(
            f"SELECT c.*, e.employer_name, e.sha_employer_code, e.current_arrears, e.risk_score FROM compliance_cases c JOIN employers e ON e.id=c.employer_id WHERE c.status=?{stage_clause} ORDER BY c.priority, c.due_at",
            params,
        ).fetchall()]
    return {"items": rows}


@app.post("/api/cases")
def create_case(payload: CaseCreate, actor: OfficerContext = Depends(require_role("supervisor", "legal_officer"))) -> dict[str, str]:
    with connect() as conn:
        case_id = str(uuid.uuid4())
        case_number = f"RECT-{datetime.now(UTC).strftime('%Y%m%d')}-{case_id[:8].upper()}"
        conn.execute(
            """
            INSERT INTO compliance_cases(id, employer_id, case_number, status, stage, priority, assigned_officer_id, assigned_officer_name, opened_at, due_at, summary)
            VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
            """,
            (case_id, payload.employer_id, case_number, payload.stage, payload.priority, payload.assigned_officer_id or actor.officer_id, payload.assigned_officer_name or actor.officer_name, now_iso(), payload.due_at, payload.summary),
        )
        audit(conn, actor, "create", "case", case_id, None, payload.model_dump())
        conn.commit()
    return {"id": case_id, "case_number": case_number}


@app.post("/api/notices")
def generate_notices(payload: NoticeRequest, actor: OfficerContext = Depends(require_role("compliance_officer", "supervisor", "legal_officer"))) -> dict[str, Any]:
    generated: list[str] = []
    with connect() as conn:
        for employer_id in payload.employer_ids:
            generated.append(generate_notice_pdf(conn, employer_id, payload.notice_type, actor, payload.template_path))
        conn.commit()
    return {"generated_notice_ids": generated}


@app.get("/api/notices/{notice_id}/download")
def download_notice(notice_id: str) -> FileResponse:
    with connect() as conn:
        notice = conn.execute("SELECT * FROM notices WHERE id=?", (notice_id,)).fetchone()
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")
    return FileResponse(notice["pdf_path"], media_type="application/pdf", filename=Path(notice["pdf_path"]).name)


@app.get("/api/export/employers.csv")
def export_employers() -> StreamingResponse:
    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute("SELECT * FROM employers ORDER BY employer_name").fetchall()]
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=rect-employers.csv"})


@app.post("/api/sync/run")
def run_sync(payload: SyncRequest, actor: OfficerContext = Depends(require_role("administrator", "supervisor"))) -> dict[str, Any]:
    sync_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sync_logs(id, connector, mode, status, message, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sync_id,
                payload.connector,
                payload.mode,
                "dry_run" if payload.mode == "dry_run" else "configured_pending_authorized_connector",
                "RECT provides a connector boundary for authorized SHA API or officer-driven MFA RPA synchronization; no unauthorized scraping is performed.",
                now_iso(),
                now_iso(),
            ),
        )
        audit(conn, actor, "run", "sync", sync_id, None, payload.model_dump())
        conn.commit()
    return {"sync_id": sync_id, "status": "logged", "integration_policy": "authorized API first; MFA-aware RPA only with officer consent"}


@app.get("/api/audit")
def audit_log(limit: int = Query(default=100, le=500), actor: OfficerContext = Depends(require_role("auditor", "supervisor", "legal_officer"))) -> dict[str, Any]:
    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
    return {"items": rows}


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    setup_db()
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
