"""T4 acceptance — ``ingestion.xbrl.extract_facts`` is the faithful, sole producer
of ``XBRLFact``s.

These four checks pin the contract the rest of the system leans on (Constitution
§1.2, "numbers come only from XBRL"):

- every fact arrives fully shaped (``test_fact_fields_present``);
- a fact has one identity per filing (``test_fact_ids_unique_per_filing``), so the
  duplicate iXBRL taggings a filer scatters through the document collapse to one
  canonical figure;
- an absent value is dropped, never invented as ``0`` (``test_nil_and_untransformable_skipped``); and
- the extractor actually reads the thousands of facts a 10-K carries, not a
  silent handful (``test_filing_fact_count_floor``).

All four read the session-scoped ``xbrl_facts`` fixture (the FY2024 filing parsed
once). Exact numeric truth (Assets, NetIncome per year) is pinned separately by
the T5 anchor test — here the concern is *shape and fidelity*, not the digits.
"""

from decimal import Decimal
from types import SimpleNamespace

from config.schema import Entity, PeriodType, XBRLFact
from ingestion.xbrl import _resolve_value

# A 10-K's iXBRL package carries thousands of tagged figures; the five JPM
# filings all parse to >7,000 facts. A floor well below that still fires loudly if
# extraction silently collapses to a handful (a broken loader, a wrong filter).
_FACT_COUNT_FLOOR = 5000


def test_fact_fields_present(xbrl_facts: list[XBRLFact]) -> None:
    """Every extracted fact is fully populated and internally consistent."""
    assert xbrl_facts, "extractor returned no facts"

    accession = "0000019617-25-000270"  # the FY2024 sample filing
    for fact in xbrl_facts:
        # provenance + identity
        assert fact.source_filing == accession
        assert fact.fact_id.startswith(f"{accession}:")
        # concept is a qualified XBRL tag (prefix:localName)
        assert ":" in fact.concept
        # the figure itself is an exact Decimal, never a float or None
        assert isinstance(fact.value, Decimal)
        # entity is always one of the two known legal entities (§1.3)
        assert isinstance(fact.entity, Entity)
        # unit resolved to a non-empty token
        assert fact.unit
        # decimals is precision metadata or absent — never a stray string
        assert fact.decimals is None or isinstance(fact.decimals, int)
        assert isinstance(fact.dimensions, dict)
        # period fields match the period type (the schema validator guarantees
        # this at construction; asserting it here proves the extractor populated
        # the right ones, not just that the model would have rejected a bad blend)
        if fact.period_type is PeriodType.INSTANT:
            assert fact.period_instant is not None
            assert fact.period_start is None and fact.period_end is None
        else:
            assert fact.period_start is not None and fact.period_end is not None
            assert fact.period_instant is None


def test_fact_ids_unique_per_filing(xbrl_facts: list[XBRLFact]) -> None:
    """``fact_id`` identifies one fact per filing — duplicate taggings collapsed.

    A filer tags the same figure in several places (and sometimes at different
    rounding), all sharing concept + context + unit. If the extractor did not
    collapse them, the same Assets figure would appear two or three times; a
    unique-id count proves the dedup keeps exactly one canonical fact.
    """
    fact_ids = [fact.fact_id for fact in xbrl_facts]
    assert len(set(fact_ids)) == len(fact_ids)


def test_nil_and_untransformable_skipped(
    xbrl_facts: list[XBRLFact], nil_numeric_concepts: set[str]
) -> None:
    """A value that is absent or un-parseable is skipped, never coerced to 0.

    Two halves: the nil case is proven against the real corpus (a concept the
    instance tags as ``xsi:nil`` must not surface as a fact), and the
    untransformable case is proven directly on the value resolver (an empty or
    junk string yields ``None``, i.e. a skip, rather than ``Decimal(0)``).
    """
    # The corpus genuinely contains the case we claim to handle — otherwise this
    # test would pass vacuously even if nothing were ever skipped.
    assert nil_numeric_concepts, "expected the FY2024 instance to tag nil numeric facts"

    # us-gaap:CommitmentsAndContingencies is tagged nil (a placeholder line with no
    # number); it must be skipped, never emitted as a 0.
    assert "us-gaap:CommitmentsAndContingencies" in nil_numeric_concepts
    extracted_concepts = {fact.concept for fact in xbrl_facts}
    assert "us-gaap:CommitmentsAndContingencies" not in extracted_concepts

    # No emitted fact carries an empty/None value that slipped through.
    assert all(fact.value is not None for fact in xbrl_facts)

    # The untransformable path, directly: an empty string, a ``None``, and a dash
    # placeholder all resolve to a skip — never to a fabricated zero (§1.2).
    for junk in ("", None, "—", "n/a"):
        skipped = _resolve_value(
            SimpleNamespace(value=junk, contextID="c-test"), concept="us-gaap:Test"
        )
        assert skipped is None, f"value {junk!r} should be skipped, got {skipped!r}"


def test_filing_fact_count_floor(xbrl_facts: list[XBRLFact]) -> None:
    """The extractor reads the filing's thousands of facts, not a silent handful."""
    assert len(xbrl_facts) > _FACT_COUNT_FLOOR
