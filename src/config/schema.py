"""The typed cross-layer contracts — Element and XBRLFact (and their enums).

This is the heart of the lowest layer (architecture §5; Constitution §1.6,
imports flow downward only). Element and XBRLFact are the two contracts every
higher layer speaks in, and they are defined **here and only here** so that:

- XBRLFact has exactly one definition site — the structural firewall (§1.2,
  "numbers come only from XBRL") rests on XBRLFact being *constructed* solely
  in the XBRL path, which is only meaningful if it is *defined* in exactly one
  place; and
- no module has to import another just to name a type (architecture §5).

Both are Pydantic v2 models: validation runs at the boundary, so a fact that
blends period types, or a value that isn't numeric, fails loudly at
construction instead of silently corrupting a downstream answer.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ElementKind(StrEnum):
    """What a parsed PDF Element is: prose, a table, or a section heading."""

    TEXT = "text"
    TABLE = "table"
    HEADING = "heading"


class PeriodType(StrEnum):
    """An XBRL fact's period shape: a point in time vs a span.

    ``instant`` — a balance-sheet "as of" figure (Assets at 2024-12-31).
    ``duration`` — an income/cash-flow "for the period" figure (NetIncome over
    2024-01-01 .. 2024-12-31). Blending the two is a fidelity bug
    (architecture §10.2); the enum keeps them distinct end to end.
    """

    INSTANT = "instant"
    DURATION = "duration"


class Entity(StrEnum):
    """The legal entity a figure is scoped to (Constitution §1.3).

    The consolidated registrant (JPMorgan Chase & Co., CIK 0000019617) is
    never silently conflated with its bank subsidiary (JPMorgan Chase Bank,
    N.A.) — both appear in the same filing with different numbers.
    """

    JPMC_CONSOLIDATED = "JPMC_CONSOLIDATED"
    JPMORGAN_CHASE_BANK_NA = "JPMORGAN_CHASE_BANK_NA"


class Element(BaseModel):
    """One parsed unit of a 10-K PDF, with full provenance.

    Produced solely by ``ingestion.elements`` (the PDF path); consumed by
    chunking (M2). Carries where it came from — fiscal year, 10-K Item, page —
    so every downstream chunk and citation can trace back to the source.
    """

    element_id: str  # stable id: {accession}:{page}:{ordinal}
    kind: ElementKind
    text: str  # for tables, a structure-preserving serialization M2 summarizes
    fiscal_year: int
    item: str  # 10-K Item, e.g. "Item 7"; "unknown" until a boundary is found
    page: int  # 1-based page in the source PDF
    entity: Entity = Entity.JPMC_CONSOLIDATED
    source_filing: str  # accession folder, e.g. "0000019617-25-000270"
    ordinal: int  # reading-order index within the filing


class XBRLFact(BaseModel):
    """One machine-readable figure from a filing's inline-XBRL package.

    Produced solely by ``ingestion.xbrl`` (the sole XBRLFact constructor — the
    §1.2 firewall); consumed by index→DuckDB (M3) and the calc tool (M5).
    ``value`` is ``Decimal``, never ``float``, so exact-match numeric fidelity
    (§1.2) is not lost to binary-float drift.
    """

    fact_id: str  # stable id {source_filing}:{concept}:{context_ref}:{unit}
    entity: Entity
    concept: str  # qualified tag, e.g. "us-gaap:Assets"
    period_type: PeriodType
    period_instant: date | None = None  # set iff period_type is instant
    period_start: date | None = None  # set iff period_type is duration
    period_end: date | None = None  # set iff period_type is duration
    value: Decimal  # post-transform numeric value (scale + sign applied)
    unit: str  # resolved unit ref: "USD", "USD/shares", "shares", "pure", …
    decimals: int | None = None  # XBRL `decimals` precision metadata
    dimensions: dict[str, str] = Field(default_factory=dict)  # remaining axes
    source_filing: str  # accession folder the instance was parsed from

    @model_validator(mode="after")
    def _enforce_period_exclusivity(self) -> "XBRLFact":
        """instant ⇒ only period_instant; duration ⇒ only start + end.

        A duration carrying a stray ``period_instant`` (or an instant carrying
        a start/end) is exactly the period blend §1.3 / architecture §10.2
        forbid — reject it at construction so a blended fact can never reach
        the fact stream.
        """
        if self.period_type is PeriodType.INSTANT:
            if self.period_instant is None:
                raise ValueError("instant fact must set period_instant")
            if self.period_start is not None or self.period_end is not None:
                raise ValueError(
                    "instant fact must not set period_start/period_end"
                )
        else:  # PeriodType.DURATION
            if self.period_start is None or self.period_end is None:
                raise ValueError(
                    "duration fact must set period_start and period_end"
                )
            if self.period_instant is not None:
                raise ValueError("duration fact must not set period_instant")
        return self
