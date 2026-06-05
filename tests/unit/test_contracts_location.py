"""T2 acceptance — the typed contracts live in config.schema, and only there.

Two integrity checks on the contracts this task introduces:

1. **Location** (the named AC8 acceptance): ``Element``, ``XBRLFact``, and
   their enums import from ``config.schema`` and are *defined* there — not
   re-exported from ``ingestion``. ``XBRLFact`` having exactly one home is what
   makes the §1.2 firewall and the downward-only import rule (§1.6)
   structurally checkable.
2. **The one invariant that can't wait for T4**: the period-exclusivity model
   validator actually *rejects* a period-blended fact at construction. A no-op
   validator would still pass T4's corpus tests (real facts are well-formed),
   so its rejection behaviour is proven here, where it is introduced (§4.4).
"""

import datetime as dt
from decimal import Decimal

import pytest

from config.schema import Element, ElementKind, Entity, PeriodType, XBRLFact


def test_types_defined_in_config():
    for typ in (Element, XBRLFact, ElementKind, PeriodType, Entity):
        assert typ.__module__ == "config.schema", (
            f"{typ.__name__} must be defined in config.schema, "
            f"not {typ.__module__}"
        )


def test_period_exclusivity_enforced():
    base = dict(
        fact_id="f",
        entity=Entity.JPMC_CONSOLIDATED,
        concept="us-gaap:Assets",
        value=Decimal("1"),
        unit="USD",
        source_filing="0000019617-25-000270",
    )

    # valid instant and valid duration both construct cleanly
    XBRLFact(
        **base,
        period_type=PeriodType.INSTANT,
        period_instant=dt.date(2024, 12, 31),
    )
    XBRLFact(
        **base,
        period_type=PeriodType.DURATION,
        period_start=dt.date(2024, 1, 1),
        period_end=dt.date(2024, 12, 31),
    )

    # instant carrying a duration range → rejected
    with pytest.raises(ValueError):
        XBRLFact(
            **base,
            period_type=PeriodType.INSTANT,
            period_instant=dt.date(2024, 12, 31),
            period_end=dt.date(2024, 12, 31),
        )

    # duration carrying a stray instant → the §1.3 period blend → rejected
    with pytest.raises(ValueError):
        XBRLFact(
            **base,
            period_type=PeriodType.DURATION,
            period_start=dt.date(2024, 1, 1),
            period_end=dt.date(2024, 12, 31),
            period_instant=dt.date(2024, 12, 31),
        )
