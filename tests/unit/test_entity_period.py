"""T4 acceptance — the two dimensions the firewall is most easily wrong about:
*whose* number it is (entity) and *when* it applies (period).

Constitution §1.3 forbids conflating JPMorgan Chase & Co. (consolidated) with its
subsidiary JPMorgan Chase Bank, N.A. — both file under one CIK and appear in the
same instance, separated only by a tagged ``dei:LegalEntityAxis`` member. And a
balance-sheet "as of 2024-12-31" must never blur into an income-statement "for
2024", nor inherit Arelle's end-exclusive boundary (a 2024-12-31 instant is stored
as Jan-1-next and must be corrected back).

``test_restated_fy2022_both_present`` guards the third fidelity trap: a prior year
restated in a later filing. The FY2024 10-K re-reports FY2022 figures as
comparatives, some changed from the original FY2022 filing; both must survive,
distinguished by ``source_filing`` — a later restatement never silently
overwrites the figure as first filed.
"""

from datetime import date

from config.schema import Entity, PeriodType, XBRLFact

# The two filings whose FY2022 figures are compared. The FY2024 10-K carries
# FY2022 as a (restated) comparative alongside the original FY2022 filing.
_FY2022_FILING = "0000019617-23-000231"
_FY2024_FILING = "0000019617-25-000270"


def _consolidated(
    facts: list[XBRLFact], concept: str, *, start: date, end: date
) -> list[XBRLFact]:
    """Dimensionless, consolidated facts for one concept over one duration."""
    return [
        fact
        for fact in facts
        if fact.concept == concept
        and not fact.dimensions
        and fact.entity == Entity.JPMC_CONSOLIDATED
        and fact.period_start == start
        and fact.period_end == end
    ]


def test_entity_always_set_and_distinct(xbrl_facts: list[XBRLFact]) -> None:
    """Every fact is scoped to a known entity, and both entities are present.

    "Always set" — no fact is left without a legal entity (a silent default would
    let a subsidiary figure masquerade as consolidated). "Distinct" — both the
    consolidated registrant and the bank subsidiary actually appear, so the §1.3
    split is exercised, not merely possible.
    """
    assert all(isinstance(fact.entity, Entity) for fact in xbrl_facts)

    entities = {fact.entity for fact in xbrl_facts}
    assert entities == {Entity.JPMC_CONSOLIDATED, Entity.JPMORGAN_CHASE_BANK_NA}

    # The entity is carried by `entity`, not echoed in `dimensions`: the
    # consolidation axis is projected out, so no fact keeps a LegalEntityAxis key.
    assert not any(
        "LegalEntityAxis" in axis for fact in xbrl_facts for axis in fact.dimensions
    )


def test_period_date_fields_exclusive(xbrl_facts: list[XBRLFact]) -> None:
    """Period fields are mutually exclusive, and the dates are the reported ones.

    Two guarantees: instant and duration never co-populate (a fact is one or the
    other), and Arelle's end-exclusive storage is corrected back to the dates a
    reader sees — a 2024-12-31 balance, not the Jan-1-next boundary.
    """
    for fact in xbrl_facts:
        if fact.period_type is PeriodType.INSTANT:
            assert fact.period_instant is not None
            assert fact.period_start is None and fact.period_end is None
        else:
            assert fact.period_start is not None and fact.period_end is not None
            assert fact.period_instant is None

    # Instant correction: the consolidated total-assets balance is dated
    # 2024-12-31, never the end-exclusive 2025-01-01 Arelle stores internally.
    assets = [
        fact
        for fact in xbrl_facts
        if fact.concept == "us-gaap:Assets"
        and not fact.dimensions
        and fact.entity == Entity.JPMC_CONSOLIDATED
    ]
    assert assets
    assets_instants = {fact.period_instant for fact in assets}
    assert date(2024, 12, 31) in assets_instants
    assert date(2025, 1, 1) not in assets_instants

    # Duration correction: FY2024 net income spans 2024-01-01 .. 2024-12-31 — the
    # end date is the reported Dec-31, not the stored Jan-1-next.
    net_income = _consolidated(
        xbrl_facts, "us-gaap:NetIncomeLoss", start=date(2024, 1, 1), end=date(2024, 12, 31)
    )
    assert net_income


def test_restated_fy2022_both_present(
    xbrl_facts: list[XBRLFact], fy2022_facts: list[XBRLFact]
) -> None:
    """A restated prior year survives from both filings, distinct by provenance.

    ``jpm:FeesAndCommissions1`` for FY2022 is reported one way in the original
    FY2022 10-K and reclassified to a different figure as the FY2024 10-K's
    comparative. The extractor must keep *both* — same concept and period, but
    different ``source_filing`` and ``fact_id`` — so a later restatement never
    erases the figure as first filed (spec AC3).
    """
    original = _consolidated(
        fy2022_facts, "jpm:FeesAndCommissions1", start=date(2022, 1, 1), end=date(2022, 12, 31)
    )
    restated = _consolidated(
        xbrl_facts, "jpm:FeesAndCommissions1", start=date(2022, 1, 1), end=date(2022, 12, 31)
    )

    # Exactly one canonical fact in each filing (dedup did not drop the comparative
    # and did not leave duplicate taggings).
    assert len(original) == 1
    assert len(restated) == 1
    first_filed, comparative = original[0], restated[0]

    # Each is tagged to the filing it came from.
    assert first_filed.source_filing == _FY2022_FILING
    assert comparative.source_filing == _FY2024_FILING

    # Distinct identities — the later comparative is an additional fact, not an
    # overwrite of the original.
    assert first_filed.fact_id != comparative.fact_id

    # And it is a genuine restatement: the FY2022 figure was changed in the FY2024
    # filing, and both values are retained.
    assert first_filed.value != comparative.value
