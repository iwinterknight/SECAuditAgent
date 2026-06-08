"""T5 cheap-eval gate — the exact-match numeric anchor (Constitution §4.3).

This is the project's first *deterministic fidelity gate*. It pins ten figures —
**Total assets** (``us-gaap:Assets``) and **Net income** (``us-gaap:NetIncomeLoss``)
for each of FY2021–FY2025 — to the exact integer the registrant filed in XBRL, and
fails the moment extraction drifts by a single dollar. The whole §1.2 firewall
exists so that numbers come from XBRL and nothing transcribes them; this test is the
tripwire that proves the XBRL path *itself* stays faithful through Arelle's
scale/sign/transform, the end-exclusive date correction, the duplicate-tagging
dedup, and entity/period resolution.

Why these two metrics: total assets is the headline **instant** (a balance "as of"
year-end) and net income is the headline **duration** (a flow "for the year"), so a
single pair exercises both period shapes end to end. Why **consolidated and
dimensionless**: the anchor is the registrant-level total an analyst would quote —
JPMorgan Chase & Co., with no segment/business-unit breakdown — selected exactly the
way a downstream numeric lookup will scope a figure (entity + concept + period, no
dimensions). Each selection must resolve to *exactly one* fact: ten anchors, ten
single facts, ten exact matches.

The values are not typed from memory — they were read from the five vendored
instances during IMPLEMENT and pinned here (the ``[VERIFY in IMPLEMENT]`` step).
Both concept tags proved taxonomy-stable across the 2021→2025 us-gaap versions, so
the per-FY override hook (``_CONCEPT_OVERRIDES``) is present but empty: it is the one
sanctioned place to record a tag rename for some FY, rather than weakening the gate.

These ten anchors are also the **first seed of the M7 numeric truth set** — the same
figures the eval harness will later assert the *answered* system reproduces.
"""

from datetime import date
from decimal import Decimal

import pytest

from config.schema import Entity, PeriodType, XBRLFact
from config.settings import Settings
from ingestion.xbrl import extract_facts

# The two anchor concepts and the period shape each one is reported in.
_ASSETS = "us-gaap:Assets"
_NET_INCOME = "us-gaap:NetIncomeLoss"
_PERIOD_TYPE: dict[str, PeriodType] = {
    _ASSETS: PeriodType.INSTANT,  # a balance "as of" Dec-31
    _NET_INCOME: PeriodType.DURATION,  # a flow "for the year"
}

_FISCAL_YEARS = (2021, 2022, 2023, 2024, 2025)

# Filing-verified anchor truth (read from the five instances during IMPLEMENT).
# Values are full dollars; the filings report $ in millions, so e.g. FY2024 total
# assets of $4,002,814 million is pinned as 4_002_814_000_000.
_EXPECTED: dict[tuple[int, str], int] = {
    # Total assets — instant, at Dec-31 of each FY.
    (2021, _ASSETS): 3_743_567_000_000,
    (2022, _ASSETS): 3_665_743_000_000,
    (2023, _ASSETS): 3_875_393_000_000,
    (2024, _ASSETS): 4_002_814_000_000,
    (2025, _ASSETS): 4_424_900_000_000,
    # Net income — duration, the full FY span.
    (2021, _NET_INCOME): 48_334_000_000,
    (2022, _NET_INCOME): 37_676_000_000,
    (2023, _NET_INCOME): 49_552_000_000,
    (2024, _NET_INCOME): 58_471_000_000,
    (2025, _NET_INCOME): 57_048_000_000,
}

# Per-FY concept-tag overrides — the graceful-degradation hook the task calls for.
# Both anchor tags resolve to exactly one consolidated, dimensionless fact for every
# FY2021–FY2025, so no override is needed today. If a future taxonomy renames a
# concept for some FY, map ``(fiscal_year, canonical_tag) -> actual_tag`` here — the
# one place a per-FY tag may differ — instead of loosening the exact-match gate.
_CONCEPT_OVERRIDES: dict[tuple[int, str], str] = {}

# The ten (FY, metric) anchors, ordered metric-major for readable test ids.
_ANCHORS: list[tuple[int, str]] = [
    (fy, concept) for concept in (_ASSETS, _NET_INCOME) for fy in _FISCAL_YEARS
]


@pytest.fixture(scope="session")
def facts_by_fy(settings: Settings) -> dict[int, list[XBRLFact]]:
    """Every filing extracted once, keyed by fiscal year.

    The anchor gate spans all five filings, so — like the conftest fact fixtures —
    the multi-second iXBRL parse runs a single time per session and all ten
    assertions read from this cache. Routes through ``Settings.FILINGS`` so the
    accession↔FY join stays in its single source of truth (never re-derived here).
    """
    return {
        filing.fiscal_year: extract_facts(
            settings.xbrl_dir / filing.accession, source_filing=filing.accession
        )
        for filing in settings.FILINGS
    }


def _anchor_fact(
    facts: list[XBRLFact], concept: str, period_type: PeriodType, fy: int
) -> XBRLFact:
    """The single consolidated, dimensionless fact for one anchor in one FY.

    Scopes a figure the way a downstream numeric lookup will: by concept,
    consolidated entity, no dimensional breakdown, and the exact period the FY
    denotes — an instant at year-end for a balance, the full-year span for a flow.
    Asserting *exactly one* match is itself part of the gate: zero means the tag
    failed to resolve, many means the anchor is ambiguous (a dedup or dimension
    leak) — either way the figure can't be trusted as ground truth.
    """
    matches: list[XBRLFact] = []
    for fact in facts:
        if (
            fact.concept != concept
            or fact.dimensions
            or fact.entity != Entity.JPMC_CONSOLIDATED
        ):
            continue
        if fact.period_type is not period_type:
            continue
        if period_type is PeriodType.INSTANT:
            period_ok = fact.period_instant == date(fy, 12, 31)
        else:
            period_ok = fact.period_start == date(fy, 1, 1) and fact.period_end == date(
                fy, 12, 31
            )
        if period_ok:
            matches.append(fact)

    assert len(matches) == 1, (
        f"FY{fy} {concept}: expected exactly one consolidated, dimensionless fact, "
        f"found {len(matches)}"
    )
    return matches[0]


@pytest.mark.parametrize(
    ("fiscal_year", "concept"),
    _ANCHORS,
    ids=[f"FY{fy}-{concept.split(':')[1]}" for fy, concept in _ANCHORS],
)
def test_total_assets_and_net_income_exact(
    facts_by_fy: dict[int, list[XBRLFact]], fiscal_year: int, concept: str
) -> None:
    """Each anchor figure, as extracted, exactly equals the filed XBRL value.

    Ten parametrized cases (2 metrics × 5 FY) make up the §4.3 cheap deterministic
    tier: a single-dollar drift in scale/sign/transform, a period mis-resolution, or
    an entity mix-up fails the precise (FY, metric) case rather than a vague whole.
    """
    expected = _EXPECTED[(fiscal_year, concept)]
    tag = _CONCEPT_OVERRIDES.get((fiscal_year, concept), concept)
    fact = _anchor_fact(
        facts_by_fy[fiscal_year], tag, _PERIOD_TYPE[concept], fiscal_year
    )

    # Exact-match numeric fidelity — Decimal equality, no binary-float drift (§1.2).
    assert fact.value == Decimal(expected), (
        f"FY{fiscal_year} {concept}: extracted {fact.value}, expected {expected}"
    )
    # A correct number in the wrong unit is still wrong; both anchors are USD.
    assert fact.unit == "USD"
