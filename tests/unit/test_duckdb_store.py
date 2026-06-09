"""DuckDB facts store (app/duckdb_store.py) — exact, dimensionless, consolidated lookups
over the baked XBRL facts. Offline: reads the derived JSONL, no network, no LLM.

importorskip skips cleanly if the demo extras / derived corpus aren't present.
"""

from decimal import Decimal

import pytest

duckdb_store = pytest.importorskip("duckdb_store")

from config.schema import PeriodType  # noqa: E402 (after importorskip)


def test_total_assets_fy2024_is_exact_and_usd():
    result = duckdb_store.headline_value("us-gaap:Assets", PeriodType.INSTANT, 2024)
    assert result is not None
    value, unit = result
    assert unit == "USD"
    assert value == Decimal("4002814000000")  # $4,002,814 million, as filed


def test_value_is_decimal_never_float():
    value, _ = duckdb_store.headline_value("us-gaap:Assets", PeriodType.INSTANT, 2024)
    assert isinstance(value, Decimal)  # exact-match fidelity: never binary float


def test_returns_consolidated_total_not_a_dimensional_subfigure():
    # us-gaap:Assets is also tagged by segment; the store must return the consolidated
    # *total* (cardinality(dimensions)=0), which dwarfs any single breakdown.
    value, _ = duckdb_store.headline_value("us-gaap:Assets", PeriodType.INSTANT, 2021)
    assert value == Decimal("3743567000000")  # $3,743,567 million total


def test_duration_metric_net_income_fy2024():
    result = duckdb_store.headline_value("us-gaap:NetIncomeLoss", PeriodType.DURATION, 2024)
    assert result is not None
    value, _ = result
    assert value == Decimal("58471000000")  # $58,471 million


def test_unknown_year_returns_none():
    assert duckdb_store.headline_value("us-gaap:Assets", PeriodType.INSTANT, 1999) is None
