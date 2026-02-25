"""Helpers for connecting and reconciling NHIF and SHA remittance data sources."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from sha_compliance import nhif_contribution, sha_contribution

REQUIRED_NHIF_COLUMNS = {
    "employer",
    "employer_pin",
    "employee_id",
    "id_number",
    "payroll_month",
    "gross_salary",
    "nhif_remitted_amount",
}

REQUIRED_SHA_COLUMNS = {
    "employer",
    "employer_pin",
    "employee_id",
    "id_number",
    "payroll_month",
    "gross_salary",
    "sha_remitted_amount",
}


@dataclass(frozen=True)
class ReadinessReport:
    source_name: str
    records: int
    missing_columns: tuple[str, ...]
    null_counts: dict[str, int]
    duplicate_match_keys: int


CRITICAL_MATCH_COLUMNS = ["employer_pin", "payroll_month", "id_number", "employee_id"]


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip().upper()


def _match_key(df: pd.DataFrame) -> pd.Series:
    id_key = df["id_number"].map(_clean_text)
    emp_key = df["employee_id"].map(_clean_text)
    return id_key.where(id_key != "", emp_key)


def assess_source_readiness(
    df: pd.DataFrame,
    required_columns: set[str],
    source_name: str,
) -> ReadinessReport:
    """Check whether a source extract is ready for NHIF↔SHA reconciliation."""
    missing = tuple(sorted(required_columns - set(df.columns)))

    if missing:
        return ReadinessReport(
            source_name=source_name,
            records=len(df),
            missing_columns=missing,
            null_counts={},
            duplicate_match_keys=0,
        )

    working = df.copy()
    working["match_key"] = _match_key(working)
    grouped = working.groupby(["employer_pin", "payroll_month", "match_key"], dropna=False).size()

    null_counts = {
        col: int(working[col].isna().sum()) + int((working[col].astype(str).str.strip() == "").sum())
        for col in CRITICAL_MATCH_COLUMNS
    }

    return ReadinessReport(
        source_name=source_name,
        records=len(df),
        missing_columns=missing,
        null_counts=null_counts,
        duplicate_match_keys=int((grouped > 1).sum()),
    )


def reconcile_nhif_sha(nhif_df: pd.DataFrame, sha_df: pd.DataFrame) -> pd.DataFrame:
    """Join NHIF and SHA extracts using a composite key and compute compliance signals."""
    nhif = nhif_df.copy()
    sha = sha_df.copy()

    nhif["match_key"] = _match_key(nhif)
    sha["match_key"] = _match_key(sha)

    key_columns = ["employer_pin", "payroll_month", "match_key"]

    keep_nhif = key_columns + ["employer", "employee_id", "id_number", "gross_salary", "nhif_remitted_amount"]
    keep_sha = key_columns + ["employee_id", "id_number", "gross_salary", "sha_remitted_amount"]

    joined = nhif[keep_nhif].merge(
        sha[keep_sha],
        on=key_columns,
        how="outer",
        suffixes=("_nhif", "_sha"),
    )

    joined["gross_salary"] = joined["gross_salary_sha"].combine_first(joined["gross_salary_nhif"]).fillna(0.0)
    joined["legacy_nhif_expected"] = joined["gross_salary"].apply(nhif_contribution)
    joined["expected_sha"] = joined["gross_salary"].apply(sha_contribution)

    joined["nhif_remitted_amount"] = joined["nhif_remitted_amount"].fillna(0.0)
    joined["sha_remitted_amount"] = joined["sha_remitted_amount"].fillna(0.0)

    joined["sha_gap"] = (joined["expected_sha"] - joined["sha_remitted_amount"]).round(2)
    joined["under_remitted_under_sha"] = joined["sha_gap"] > 0
    joined["regime_delta"] = (joined["expected_sha"] - joined["legacy_nhif_expected"]).round(2)

    return joined.sort_values(["employer_pin", "payroll_month", "match_key"]).reset_index(drop=True)


def build_batch_audit_report(reconciled_df: pd.DataFrame) -> dict[str, object]:
    """Return structured summary tables for batch audits and report exports."""
    working = reconciled_df.copy()
    if working.empty:
        empty_cols = ["employer_pin", "records", "flagged_records", "potential_loss", "avg_gap"]
        month_cols = ["payroll_month", "records", "flagged_records", "potential_loss"]
        return {
            "totals": {
                "records": 0,
                "flagged_records": 0,
                "potential_loss": 0.0,
                "compliance_rate": 0.0,
            },
            "employer_summary": pd.DataFrame(columns=empty_cols),
            "monthly_summary": pd.DataFrame(columns=month_cols),
            "flagged_records": working,
        }

    working["payroll_month"] = working["payroll_month"].fillna("UNKNOWN")
    working["sha_gap_positive"] = working["sha_gap"].clip(lower=0)

    totals = {
        "records": int(len(working)),
        "flagged_records": int(working["under_remitted_under_sha"].sum()),
        "potential_loss": round(float(working["sha_gap_positive"].sum()), 2),
        "compliance_rate": round(
            float((~working["under_remitted_under_sha"]).sum()) / float(len(working)) * 100,
            2,
        ),
    }

    employer_summary = (
        working.groupby("employer_pin", as_index=False)
        .agg(
            records=("match_key", "count"),
            flagged_records=("under_remitted_under_sha", "sum"),
            potential_loss=("sha_gap_positive", "sum"),
            avg_gap=("sha_gap", "mean"),
        )
        .sort_values(["potential_loss", "flagged_records"], ascending=False)
        .reset_index(drop=True)
    )
    employer_summary["potential_loss"] = employer_summary["potential_loss"].round(2)
    employer_summary["avg_gap"] = employer_summary["avg_gap"].round(2)

    monthly_summary = (
        working.groupby("payroll_month", as_index=False)
        .agg(
            records=("match_key", "count"),
            flagged_records=("under_remitted_under_sha", "sum"),
            potential_loss=("sha_gap_positive", "sum"),
        )
        .sort_values("payroll_month")
        .reset_index(drop=True)
    )
    monthly_summary["potential_loss"] = monthly_summary["potential_loss"].round(2)

    flagged_records = working[working["under_remitted_under_sha"]].copy()

    return {
        "totals": totals,
        "employer_summary": employer_summary,
        "monthly_summary": monthly_summary,
        "flagged_records": flagged_records,
    }
