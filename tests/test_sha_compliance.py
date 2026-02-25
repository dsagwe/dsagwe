from sha_compliance import (
    expected_under_sha,
    infer_from_nhif_contribution,
    infer_from_sha_contribution,
    infer_salary_range_from_nhif,
    infer_salary_range_from_sha,
    nhif_contribution,
    sha_contribution,
)


def test_nhif_band_edges():
    assert nhif_contribution(5999) == 150
    assert nhif_contribution(6000) == 300
    assert nhif_contribution(99999) == 1600
    assert nhif_contribution(100000) == 1700


def test_nhif_top_band_is_greater_or_equal_100000():
    assert nhif_contribution(100000) == 1700
    assert nhif_contribution(150000) == 1700


def test_sha_minimum_and_rate():
    assert sha_contribution(5000) == 300
    assert sha_contribution(12000) == 330.0


def test_expected_under_sha():
    assert expected_under_sha(30000, 900) is False
    assert expected_under_sha(30000, 800) is True


def test_infer_salary_range_from_nhif():
    assert infer_salary_range_from_nhif(900) == (30000, 34999)
    assert infer_salary_range_from_nhif(1700) == (100000, None)
    assert infer_salary_range_from_nhif(925) is None


def test_infer_salary_range_from_sha():
    assert infer_salary_range_from_sha(300) == (0.0, 10909.09)
    assert infer_salary_range_from_sha(825) == (30000.0, 30000.0)
    assert infer_salary_range_from_sha(299.99) is None


def test_infer_from_nhif_and_sha_crosswalk():
    nhif_inferred = infer_from_nhif_contribution(900)
    assert nhif_inferred is not None
    assert nhif_inferred["salary_min"] == 30000
    assert nhif_inferred["implied_sha_min"] == 825.0

    sha_inferred = infer_from_sha_contribution(825)
    assert sha_inferred is not None
    assert sha_inferred["salary_min"] == 30000.0
    assert sha_inferred["possible_nhif_contributions"] == [900]
