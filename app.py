from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from data_integration import (
    REQUIRED_NHIF_COLUMNS,
    REQUIRED_SHA_COLUMNS,
    assess_source_readiness,
    build_batch_audit_report,
    reconcile_nhif_sha,
)
from sha_compliance import infer_from_nhif_contribution, infer_from_sha_contribution

st.set_page_config(page_title="SHA Compliance Workspace", layout="wide")

PALETTE = {
    "background": "#050508",
    "primary": "#00F5FF",
    "secondary": "#BF00FF",
    "positive": "#00FF88",
    "alert": "#FF2D55",
    "text": "#E8F4FD",
    "muted": "#4A6274",
}

TASKS = [
    {"title": "Reconcile March payroll remittances", "owner": "Compliance Ops", "status": "IN PROGRESS"},
    {"title": "Review top-20 under-remitting employers", "owner": "Regional Lead", "status": "PENDING"},
    {"title": "Approve surcharge notices", "owner": "Legal", "status": "BLOCKED"},
    {"title": "Close February inspection findings", "owner": "Field Team", "status": "COMPLETED"},
]

PENDING_APPROVALS = [
    {"item": "Penalty waiver request — Employer PIN A001", "amount": "KES 1,280,500", "age": "3 days"},
    {"item": "Backdated correction upload — Employer PIN B019", "amount": "KES 740,000", "age": "1 day"},
    {"item": "Dispute escalation — Employer PIN C221", "amount": "KES 2,110,200", "age": "5 days"},
]

STATUS_CLASS = {
    "COMPLETED": "status-completed",
    "IN PROGRESS": "status-progress",
    "BLOCKED": "status-blocked",
    "PENDING": "status-pending",
}

st.markdown(
    f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;500;700&display=swap');

        .stApp {{
            background: {PALETTE['background']};
            color: {PALETTE['text']};
            font-family: 'Roboto Mono', monospace;
        }}

        html, body, [class*="css"], [data-testid="stSidebar"], [data-testid="stMetricValue"],
        [data-testid="stMetricLabel"], p, li, div, span, h1, h2, h3, h4, label {{
            font-family: 'Roboto Mono', monospace !important;
            color: {PALETTE['text']};
        }}

        [data-testid="stSidebar"] {{
            background: #070b10;
            border-right: 1px solid rgba(0,245,255,0.12);
            box-shadow: 0 0 28px rgba(0,245,255,0.12);
        }}

        .app-title, .neon, h1, h2, h3 {{
            color: {PALETTE['primary']} !important;
            text-shadow: 0 0 8px rgba(0,245,255,0.75), 0 0 16px rgba(0,245,255,0.45);
            filter: drop-shadow(0 0 8px rgba(0,245,255,0.45));
        }}

        .sub-neon {{
            color: {PALETTE['secondary']};
            text-shadow: 0 0 8px rgba(191,0,255,0.65), 0 0 14px rgba(191,0,255,0.4);
            filter: drop-shadow(0 0 8px rgba(191,0,255,0.4));
        }}

        .card {{
            border: 1px solid rgba(0,245,255,0.08);
            background: rgba(0,245,255,0.03);
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 0 14px rgba(0,245,255,0.16);
            animation: fadeUp 0.6s ease forwards;
            opacity: 0;
            transform: translateY(12px);
        }}

        .kpi-value {{
            font-size: 1.6rem;
            font-weight: 700;
            color: {PALETTE['primary']};
            text-shadow: 0 0 10px rgba(0,245,255,0.75);
            filter: drop-shadow(0 0 8px rgba(0,245,255,0.45));
        }}

        .muted {{ color: {PALETTE['muted']}; }}

        .status-badge {{
            display: inline-block;
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 0.78rem;
            font-weight: 700;
            border: 1px solid;
            letter-spacing: 0.03em;
            text-shadow: 0 0 8px currentColor;
            filter: drop-shadow(0 0 6px currentColor);
        }}

        .status-completed {{ color: {PALETTE['positive']}; border-color: rgba(0,255,136,0.55); background: rgba(0,255,136,0.09); }}
        .status-progress {{ color: {PALETTE['primary']}; border-color: rgba(0,245,255,0.55); background: rgba(0,245,255,0.09); }}
        .status-blocked {{ color: {PALETTE['alert']}; border-color: rgba(255,45,85,0.55); background: rgba(255,45,85,0.09); }}
        .status-pending {{ color: {PALETTE['secondary']}; border-color: rgba(191,0,255,0.55); background: rgba(191,0,255,0.09); }}

        .stButton > button, .stDownloadButton > button {{
            border: 1px solid rgba(0,245,255,0.6);
            background: rgba(0,245,255,0.1);
            color: {PALETTE['text']};
            text-shadow: 0 0 8px rgba(0,245,255,0.7);
            box-shadow: 0 0 10px rgba(0,245,255,0.35);
        }}

        @keyframes fadeUp {{ to {{ opacity: 1; transform: translateY(0); }} }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.components.v1.html(
    """
    <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/framer-motion/dist/framer-motion.js"></script>
    <script>
      const cards = window.parent.document.querySelectorAll('.card');
      cards.forEach((card, index) => {
        card.style.animationDelay = `${index * 120}ms`;
      });
    </script>
    """,
    height=0,
)


def _as_csv_bytes(dataframe: pd.DataFrame) -> bytes:
    return dataframe.to_csv(index=False).encode("utf-8")


def _as_excel_bytes(report: dict[str, object]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([report["totals"]]).to_excel(writer, index=False, sheet_name="totals")
        report["employer_summary"].to_excel(writer, index=False, sheet_name="employer_summary")
        report["monthly_summary"].to_excel(writer, index=False, sheet_name="monthly_summary")
        report["flagged_records"].to_excel(writer, index=False, sheet_name="flagged_records")
    output.seek(0)
    return output.read()


with st.sidebar:
    st.markdown("## <span class='app-title'>SHA Command UI</span>", unsafe_allow_html=True)
    page = st.radio("Navigation", ["/dashboard", "/tasks", "/inference", "/batch-audit"], index=0)

st.markdown("# <span class='app-title'>Compliance Operations Hub</span>", unsafe_allow_html=True)
st.markdown("<p class='muted'>Monitor contribution health, workflows, and approvals in one neon control surface.</p>", unsafe_allow_html=True)

if page == "/dashboard":
    st.markdown("## <span class='neon'>/dashboard</span>", unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    for idx, (column, label, value) in enumerate(
        [
            (k1, "TOTAL EMPLOYERS MONITORED", "1,248"),
            (k2, "PENDING APPROVALS", "27"),
            (k3, "OPEN COMPLIANCE TASKS", "64"),
            (k4, "ESTIMATED RECOVERABLE (KES)", "48,392,700"),
        ]
    ):
        with column:
            st.markdown(
                f"""
                <div class='card' style='animation-delay:{idx * 120}ms;'>
                  <div class='muted'>{label}</div>
                  <div class='kpi-value'>{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    left, right = st.columns(2)
    with left:
        st.markdown("### <span class='sub-neon'>Task List</span>", unsafe_allow_html=True)
        for idx, task in enumerate(TASKS):
            st.markdown(
                f"""
                <div class='card' style='animation-delay:{idx * 120}ms; margin-bottom: 12px;'>
                    <div><strong>{task['title']}</strong></div>
                    <div class='muted'>Owner: {task['owner']}</div>
                    <div style='margin-top:8px;'>
                        <span class='status-badge {STATUS_CLASS[task['status']]}'>
                            {task['status']}
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with right:
        st.markdown("### <span class='sub-neon'>Pending Approvals</span>", unsafe_allow_html=True)
        for idx, approval in enumerate(PENDING_APPROVALS):
            st.markdown(
                f"""
                <div class='card' style='animation-delay:{idx * 120}ms; margin-bottom: 12px;'>
                    <div><strong>{approval['item']}</strong></div>
                    <div class='muted'>Exposure: {approval['amount']}</div>
                    <div class='muted'>Age: {approval['age']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

elif page == "/tasks":
    st.markdown("## <span class='neon'>/tasks</span>", unsafe_allow_html=True)
    st.markdown("<p class='muted'>Task tracker with compliance workflow status badges.</p>", unsafe_allow_html=True)

    filter_status = st.multiselect(
        "Filter by status",
        ["COMPLETED", "IN PROGRESS", "BLOCKED", "PENDING"],
        default=["COMPLETED", "IN PROGRESS", "BLOCKED", "PENDING"],
    )

    visible_tasks = [task for task in TASKS if task["status"] in filter_status]
    if not visible_tasks:
        st.warning("No tasks match the selected status filter.")

    for idx, task in enumerate(visible_tasks):
        st.markdown(
            f"""
            <div class='card' style='animation-delay:{idx * 120}ms; margin-bottom: 12px;'>
                <div style='display:flex; justify-content:space-between; align-items:center;'>
                    <div>
                        <div><strong>{task['title']}</strong></div>
                        <div class='muted'>Owner: {task['owner']}</div>
                    </div>
                    <span class='status-badge {STATUS_CLASS[task['status']]}'>{task['status']}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

elif page == "/inference":
    st.markdown("## <span class='neon'>/inference</span>", unsafe_allow_html=True)
    st.markdown(
        "<p class='muted'>Use NHIF contribution as a variable to infer salary and SHA outcomes, and vice versa.</p>",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### <span class='sub-neon'>Infer from NHIF contribution</span>", unsafe_allow_html=True)
        nhif_value = st.number_input("NHIF contribution (KES)", min_value=0.0, value=900.0, step=50.0, key="infer-nhif")
        nhif_inference = infer_from_nhif_contribution(nhif_value)
        if nhif_inference is None:
            st.error("NHIF contribution does not match known legacy NHIF bands.")
        else:
            upper = nhif_inference["salary_max"]
            salary_text = (
                f"KES {nhif_inference['salary_min']:,.0f} to KES {upper:,.0f}"
                if upper is not None
                else f"KES {nhif_inference['salary_min']:,.0f} and above"
            )
            implied_upper = nhif_inference["implied_sha_max"]
            sha_text = (
                f"KES {nhif_inference['implied_sha_min']:,.2f} to KES {implied_upper:,.2f}"
                if implied_upper is not None
                else f"KES {nhif_inference['implied_sha_min']:,.2f} and above"
            )
            st.success(f"Inferred salary band: {salary_text}")
            st.info(f"Implied SHA contribution range: {sha_text}")

    with c2:
        st.markdown("### <span class='sub-neon'>Infer from SHA contribution</span>", unsafe_allow_html=True)
        sha_value = st.number_input("SHA contribution (KES)", min_value=0.0, value=825.0, step=25.0, key="infer-sha")
        sha_inference = infer_from_sha_contribution(sha_value)
        if sha_inference is None:
            st.error("SHA contribution is below the legal minimum (KES 300).")
        else:
            upper = sha_inference["salary_max"]
            if upper is None or upper == sha_inference["salary_min"]:
                salary_text = f"KES {sha_inference['salary_min']:,.2f}"
            else:
                salary_text = f"KES {sha_inference['salary_min']:,.2f} to KES {upper:,.2f}"
            st.success(f"Inferred gross salary: {salary_text}")
            st.info(
                "Possible NHIF contributions: "
                + ", ".join(f"KES {value:,.0f}" for value in sha_inference["possible_nhif_contributions"])
            )

else:
    st.markdown("## <span class='neon'>/batch-audit</span>", unsafe_allow_html=True)
    st.markdown(
        "<p class='muted'>Upload NHIF and SHA extracts to run a batch audit and generate downloadable reports.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("**Minimum NHIF columns**: " + ", ".join(sorted(REQUIRED_NHIF_COLUMNS)))
    st.markdown("**Minimum SHA columns**: " + ", ".join(sorted(REQUIRED_SHA_COLUMNS)))

    nhif_file = st.file_uploader("Upload NHIF extract CSV", type=["csv"], key="nhif-batch")
    sha_file = st.file_uploader("Upload SHA extract CSV", type=["csv"], key="sha-batch")

    if nhif_file and sha_file:
        nhif_df = pd.read_csv(nhif_file)
        sha_df = pd.read_csv(sha_file)

        nhif_report = assess_source_readiness(nhif_df, REQUIRED_NHIF_COLUMNS, "NHIF")
        sha_report = assess_source_readiness(sha_df, REQUIRED_SHA_COLUMNS, "SHA")

        checks = st.columns(2)
        for idx, report in enumerate((nhif_report, sha_report)):
            with checks[idx]:
                st.markdown(f"### <span class='sub-neon'>{report.source_name} readiness</span>", unsafe_allow_html=True)
                st.write(f"Records: **{report.records:,}**")
                if report.missing_columns:
                    st.error(f"Missing columns: {', '.join(report.missing_columns)}")
                else:
                    st.success("Schema validated")
                    st.write(f"Duplicate keys: **{report.duplicate_match_keys:,}**")
                    st.write(f"Nulls in key fields: **{sum(report.null_counts.values()):,}**")

        if not nhif_report.missing_columns and not sha_report.missing_columns:
            reconciled = reconcile_nhif_sha(nhif_df, sha_df)
            report_payload = build_batch_audit_report(reconciled)

            totals = report_payload["totals"]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Rows audited", f"{totals['records']:,}")
            m2.metric("Flagged", f"{totals['flagged_records']:,}")
            m3.metric("Potential loss", f"KES {totals['potential_loss']:,.2f}")
            m4.metric("Compliance rate", f"{totals['compliance_rate']:,.2f}%")

            st.markdown("### <span class='sub-neon'>Employer summary</span>", unsafe_allow_html=True)
            st.dataframe(report_payload["employer_summary"], use_container_width=True)

            st.markdown("### <span class='sub-neon'>Monthly summary</span>", unsafe_allow_html=True)
            st.dataframe(report_payload["monthly_summary"], use_container_width=True)

            st.markdown("### <span class='sub-neon'>Flagged records</span>", unsafe_allow_html=True)
            st.dataframe(report_payload["flagged_records"], use_container_width=True)

            d1, d2, d3, d4 = st.columns(4)
            d1.download_button(
                "Download full audit CSV",
                _as_csv_bytes(reconciled),
                file_name="batch_audit_reconciled.csv",
                mime="text/csv",
            )
            d2.download_button(
                "Download employer report",
                _as_csv_bytes(report_payload["employer_summary"]),
                file_name="employer_audit_summary.csv",
                mime="text/csv",
            )
            d3.download_button(
                "Download monthly report",
                _as_csv_bytes(report_payload["monthly_summary"]),
                file_name="monthly_audit_summary.csv",
                mime="text/csv",
            )
            d4.download_button(
                "Download Excel pack",
                _as_excel_bytes(report_payload),
                file_name="sha_batch_audit_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    else:
        st.info("Upload both NHIF and SHA CSV files to run a batch audit.")
