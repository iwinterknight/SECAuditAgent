"""T6 acceptance — every parsed ``Element`` carries full provenance, and a real
10-K yields a substantial Element stream.

Both tests exercise the ``parsed_elements`` session fixture (the FY2024 10-K
parsed once via :func:`ingestion.elements.parse_elements`).

- ``test_every_element_has_provenance`` is the contract check the whole narrative
  path rests on: chunking (M2) and every downstream citation trust that each
  Element knows its fiscal year, page, kind, Item slot and entity (architecture
  §5). If any Element were missing a field — or silently scoped to the bank
  subsidiary — a citation built on it would be untraceable or wrong (§1.3, §1.5).
- ``test_element_count_floor`` guards against a *silent* degradation: a parser
  that breaks to a handful of Elements (a model/path regression, a half-failed
  parse) yet still "passes" the shape check. A real 10-K is hundreds of pages of
  prose and tables; an almost-empty parse is a fidelity failure, not a result.
"""

from config.schema import Element, ElementKind, Entity
from config.settings import Filing

# Floor for the FY2024 parse, set from the measured count (see report
# 04-implement-T6) and held well below it so the gate catches a gross regression
# — a broken layout model, a half-OOM'd parse — without being brittle to the
# few-element drift expected across Docling/model versions.
_ELEMENT_FLOOR = 3000  # measured FY2024 parse = 5,111 Elements (see report); held well below


def test_every_element_has_provenance(
    parsed_elements: list[Element], sample_filing: Filing
) -> None:
    """Every Element is fully provenanced and consistently stamped (architecture §5)."""
    assert parsed_elements, "expected a non-empty Element stream from the FY2024 10-K"
    for el in parsed_elements:
        assert isinstance(el, Element)
        # Provenance: fiscal year, page, kind, 10-K Item slot, legal entity.
        assert el.fiscal_year == sample_filing.fiscal_year
        assert el.page >= 1  # 1-based source page
        assert el.kind in {ElementKind.TEXT, ElementKind.TABLE, ElementKind.HEADING}
        assert el.item == "unknown"  # T7 fills this; never guessed at parse time
        assert el.entity is Entity.JPMC_CONSOLIDATED  # §1.3 — never inferred from prose
        # Identity + lineage.
        assert el.source_filing == sample_filing.accession
        assert el.text.strip()  # no empty Elements escape the parser
        assert el.element_id == f"{sample_filing.accession}:{el.page}:{el.ordinal}"

    # The stable id must be unique within a filing (it is the citation handle).
    ids = [el.element_id for el in parsed_elements]
    assert len(set(ids)) == len(ids), "element_id must be unique within a filing"


def test_element_count_floor(parsed_elements: list[Element]) -> None:
    """A real 10-K parses into a substantial Element stream, not a degenerate few."""
    assert len(parsed_elements) > _ELEMENT_FLOOR
