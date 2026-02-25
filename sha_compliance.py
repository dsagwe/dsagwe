"""Utilities for comparing legacy NHIF and current SHA contribution regimes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SalaryBand:
    lower: int
    upper: int | None
    contribution: int


NHIF_BANDS: tuple[SalaryBand, ...] = (
    SalaryBand(0, 5999, 150),
    SalaryBand(6000, 7999, 300),
    SalaryBand(8000, 11999, 400),
    SalaryBand(12000, 14999, 500),
    SalaryBand(15000, 19999, 600),
    SalaryBand(20000, 24999, 750),
    SalaryBand(25000, 29999, 850),
    SalaryBand(30000, 34999, 900),
    SalaryBand(35000, 39999, 950),
    SalaryBand(40000, 44999, 1000),
    SalaryBand(45000, 49999, 1100),
    SalaryBand(50000, 59999, 1200),
    SalaryBand(60000, 69999, 1300),
    SalaryBand(70000, 79999, 1400),
    SalaryBand(80000, 89999, 1500),
    SalaryBand(90000, 99999, 1600),
    SalaryBand(100000, None, 1700),  # KSh ≥100,000
)

SHA_RATE = 0.0275
SHA_MINIMUM = 300


def nhif_contribution(gross_salary: float) -> int:
    """Return legacy NHIF contribution based on salary bands (top band: KSh ≥100,000)."""
    salary = max(0, int(gross_salary))
    for band in NHIF_BANDS:
        upper = band.upper if band.upper is not None else float("inf")
        if band.lower <= salary <= upper:
            return band.contribution
    return NHIF_BANDS[-1].contribution


def sha_contribution(gross_salary: float) -> float:
    """Return SHA contribution as 2.75% of gross salary with KES 300 minimum."""
    salary = max(0.0, float(gross_salary))
    return round(max(SHA_MINIMUM, salary * SHA_RATE), 2)


def expected_under_sha(gross_salary: float, remitted_amount: float) -> bool:
    """True if remitted amount is lower than expected SHA contribution."""
    return float(remitted_amount) + 1e-9 < sha_contribution(gross_salary)


def infer_salary_range_from_nhif(contribution: float) -> tuple[int, int | None] | None:
    """Infer gross-salary band from a legacy NHIF contribution amount."""
    target = int(round(float(contribution)))
    for band in NHIF_BANDS:
        if band.contribution == target:
            return band.lower, band.upper
    return None


def infer_salary_range_from_sha(contribution: float) -> tuple[float, float | None] | None:
    """Infer gross-salary range from an SHA contribution amount."""
    amount = round(float(contribution), 2)
    if amount < SHA_MINIMUM:
        return None
    if amount == SHA_MINIMUM:
        return 0.0, round(SHA_MINIMUM / SHA_RATE, 2)
    salary = round(amount / SHA_RATE, 2)
    return salary, salary


def infer_from_nhif_contribution(contribution: float) -> dict[str, object] | None:
    """Infer salary range and implied SHA contribution range from NHIF amount."""
    salary_range = infer_salary_range_from_nhif(contribution)
    if salary_range is None:
        return None

    min_salary, max_salary = salary_range
    min_sha = sha_contribution(min_salary)
    max_sha = None if max_salary is None else sha_contribution(max_salary)

    return {
        "source": "NHIF",
        "contribution": int(round(float(contribution))),
        "salary_min": min_salary,
        "salary_max": max_salary,
        "implied_sha_min": min_sha,
        "implied_sha_max": max_sha,
    }


def infer_from_sha_contribution(contribution: float) -> dict[str, object] | None:
    """Infer salary range and possible NHIF contributions from SHA amount."""
    salary_range = infer_salary_range_from_sha(contribution)
    if salary_range is None:
        return None

    min_salary, max_salary = salary_range
    if max_salary is None:
        candidate_salaries = [int(min_salary)]
    elif min_salary == max_salary:
        candidate_salaries = [int(min_salary)]
    else:
        candidate_salaries = [int(min_salary), int(max_salary)]

    possible_nhif = sorted({nhif_contribution(salary) for salary in candidate_salaries})
    if max_salary is not None and min_salary != max_salary:
        for band in NHIF_BANDS:
            if band.lower >= int(min_salary) and (band.upper is None or band.upper <= int(max_salary)):
                possible_nhif.append(band.contribution)
        possible_nhif = sorted(set(possible_nhif))

    return {
        "source": "SHA",
        "contribution": round(float(contribution), 2),
        "salary_min": min_salary,
        "salary_max": max_salary,
        "possible_nhif_contributions": possible_nhif,
    }
