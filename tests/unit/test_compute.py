"""The deterministic compute tool (app/agent.py `_tool_compute`) — every operation,
exact expected output. No LLM, no network: synthetic table, pure arithmetic in code.
"""

from decimal import Decimal

import pytest

agent = pytest.importorskip("agent")

# Synthetic facts ($ in dollars; _money displays millions): assets 100M→110M→121M.
TABLE = {
    ("Total assets", 2021): (Decimal("100000000"), "USD"),
    ("Total assets", 2022): (Decimal("110000000"), "USD"),
    ("Total assets", 2023): (Decimal("121000000"), "USD"),
    ("Total deposits", 2022): (Decimal("55000000"), "USD"),
    ("Diluted EPS", 2022): (Decimal("4.00"), "USD/shares"),
}


def _c(**args) -> str:
    return agent._tool_compute(TABLE, args)


def test_change_is_exact():
    out = _c(operation="change", metric="Total assets", from_year=2021, to_year=2022)
    assert "$10 million" in out and "[exact" in out


def test_percent_change():
    out = _c(operation="percent_change", metric="Total assets", from_year=2021, to_year=2022)
    assert "+10.0%" in out


def test_cagr():
    out = _c(operation="cagr", metric="Total assets", from_year=2021, to_year=2023)
    assert "+10.0%/yr" in out  # (121/100)^(1/2) - 1 = 10%


def test_sum_is_exact():
    out = _c(operation="sum", metric="Total assets")
    assert "$331 million" in out and "[exact" in out


def test_average():
    out = _c(operation="average", metric="Total assets")  # 331/3 = 110.33 -> 110
    assert "$110 million" in out


def test_min_and_max_report_the_year():
    assert "$100 million (FY2021)" in _c(operation="min", metric="Total assets")
    assert "$121 million (FY2023)" in _c(operation="max", metric="Total assets")


def test_ratio():
    out = _c(operation="ratio", metric="Total deposits", metric_b="Total assets", year=2022)
    assert "0.500" in out  # 55M / 110M


def test_percent_of():
    out = _c(operation="percent_of", metric="Total deposits", metric_b="Total assets", year=2022)
    assert "50.0%" in out


def test_difference_is_exact():
    out = _c(operation="difference", metric="Total assets", metric_b="Total deposits", year=2022)
    assert "$55 million" in out and "[exact" in out


def test_difference_refuses_mixed_units():
    out = _c(operation="difference", metric="Total assets", metric_b="Diluted EPS", year=2022)
    assert "different units" in out


def test_missing_data_is_handled_gracefully():
    assert "Cannot compute" in _c(
        operation="change", metric="Total assets", from_year=2021, to_year=2099
    )


def test_unknown_operation():
    assert "Unknown operation" in _c(operation="bogus", metric="Total assets")
