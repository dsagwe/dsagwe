import pytest

pd = pytest.importorskip("pandas")

from data_integration import (  # noqa: E402
    REQUIRED_NHIF_COLUMNS,
    REQUIRED_SHA_COLUMNS,
    assess_source_readiness,
    build_batch_audit_report,
    reconcile_nhif_sha,
)


def test_assess_source_readiness_missing_columns():
    df = pd.DataFrame({"employer": ["A"]})
    report = assess_source_readiness(df, REQUIRED_NHIF_COLUMNS, "NHIF")
    assert report.source_name == "NHIF"
    assert "employee_id" in report.missing_columns


def test_assess_source_readiness_duplicate_keys():
    df = pd.DataFrame(
        {
            "employer": ["A", "A"],
            "employer_pin": ["P1", "P1"],
            "employee_id": ["E1", "E1"],
            "id_number": ["111", "111"],
            "payroll_month": ["2025-01", "2025-01"],
            "gross_salary": [30000, 30000],
            "sha_remitted_amount": [700, 700],
        }
    )
    report = assess_source_readiness(df, REQUIRED_SHA_COLUMNS, "SHA")
    assert report.missing_columns == ()
    assert report.duplicate_match_keys == 1


def test_reconcile_nhif_sha_outputs_expected_flags():
    nhif_df = pd.DataFrame(
        {
            "employer": ["Acme Ltd"],
            "employer_pin": ["P123"],
            "employee_id": ["E10"],
            "id_number": ["34567890"],
            "payroll_month": ["2025-01"],
            "gross_salary": [30000],
            "nhif_remitted_amount": [900],
        }
    )

    sha_df = pd.DataFrame(
        {
            "employer": ["Acme Ltd"],
            "employer_pin": ["P123"],
            "employee_id": ["E10"],
            "id_number": ["34567890"],
            "payroll_month": ["2025-01"],
            "gross_salary": [30000],
            "sha_remitted_amount": [800],
        }
    )

    reconciled = reconcile_nhif_sha(nhif_df, sha_df)
    assert len(reconciled) == 1
    row = reconciled.iloc[0]
    assert row["legacy_nhif_expected"] == 900
    assert row["expected_sha"] == 825.0
    assert row["sha_gap"] == 25.0
    assert bool(row["under_remitted_under_sha"]) is True


def test_build_batch_audit_report_returns_expected_summaries():
    reconciled = pd.DataFrame(
        {
            "employer_pin": ["P1", "P1", "P2"],
            "payroll_month": ["2025-01", "2025-02", "2025-01"],
            "match_key": ["A", "B", "C"],
            "sha_gap": [100.0, -10.0, 50.0],
            "under_remitted_under_sha": [True, False, True],
        }
    )

    report = build_batch_audit_report(reconciled)

    assert report["totals"]["records"] == 3
    assert report["totals"]["flagged_records"] == 2
    assert report["totals"]["potential_loss"] == 150.0
    assert report["totals"]["compliance_rate"] == 33.33

    assert list(report["employer_summary"]["employer_pin"]) == ["P1", "P2"]
    assert float(report["employer_summary"].iloc[0]["potential_loss"]) == 100.0
    assert len(report["monthly_summary"]) == 2
    assert len(report["flagged_records"]) == 2
