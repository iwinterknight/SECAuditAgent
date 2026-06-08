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

import pytest

from config.schema import Element, ElementKind, Entity
from config.settings import Filing, get_settings
from ingestion.pipeline import run
from ingestion.serialize import read_jsonl

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


_FY2024_ACCESSION = "0000019617-25-000270"


@pytest.fixture(scope="session")
def fy2024_derived_elements() -> list[Element]:
    """The FY2024 Element stream, read from the derived JSONL the pipeline writes.

    Reuses the already-built corpus when present (the parse-once model); builds it
    once via ``pipeline.run`` if absent. Reading the serialized stream — rather than
    re-parsing — is the plan's test strategy for corpus tests.
    """
    path = (
        get_settings().derived_dir
        / "ingestion"
        / "elements"
        / f"{_FY2024_ACCESSION}.jsonl"
    )
    if not path.is_file():
        run([_FY2024_ACCESSION])  # slow: parse + extract + serialize this filing once
    return read_jsonl(path, Element)


def _find(elements: list[Element], predicate, description: str) -> Element:
    """First Element matching ``predicate``, or a clear failure naming what was sought."""
    match = next((e for e in elements if predicate(e)), None)
    assert match is not None, f"expected to find {description} in the FY2024 corpus"
    return match


@pytest.mark.slow
def test_known_elements_land_in_right_item(
    fy2024_derived_elements: list[Element],
) -> None:
    """Item assignment on the real FY2024 corpus, reflecting JPMorgan's structure.

    JPMorgan's 10-K body states Item 7 (MD&A) and Item 8 (Financial Statements) as
    *cross-references* and files the substantive content as **Exhibit 13** under
    **Item 15** ("Management's discussion and analysis ... appears on pages
    52-167"). So ``assign_items`` correctly labels the body Item 7/8 headings, while
    the actual financial statements land in Item 15. This pins that real behavior
    (and would catch a forward-fill regression that, say, dumped everything into
    ``unknown``). Marked slow: it reads the derived JSONL, building it once if absent.
    """
    elements = fy2024_derived_elements
    by_item: dict[str, int] = {}
    for element in elements:
        by_item[element.item] = by_item.get(element.item, 0) + 1

    # The body Item-7 and Item-8 *headings* are labeled with their own Item.
    item7 = _find(
        elements,
        lambda e: e.kind is ElementKind.HEADING and e.text.startswith("Item 7."),
        "the 'Item 7. ...' body heading",
    )
    assert item7.item == "Item 7"
    item8 = _find(
        elements,
        lambda e: e.kind is ElementKind.HEADING and e.text.startswith("Item 8."),
        "the 'Item 8. ...' body heading",
    )
    assert item8.item == "Item 8"

    # Forward-fill carries an Item across its whole section: Risk Factors (Item 1A)
    # is a large, multi-page body, not a lone heading.
    assert by_item.get("Item 1A", 0) > 100

    # Incorporate-by-reference: the auditor's report and the consolidated statements
    # of income — the substantive financial statements — are Exhibit 13 content,
    # filed under Item 15 (NOT the body's Item 8 cross-reference).
    auditor_report = _find(
        elements,
        lambda e: "Report of Independent Registered Public Accounting Firm" in e.text,
        "the auditor's report",
    )
    assert auditor_report.item == "Item 15"
    income_statement = _find(
        elements,
        lambda e: e.kind is ElementKind.HEADING
        and "Consolidated statements of income" in e.text,
        "the consolidated statements of income heading",
    )
    assert income_statement.item == "Item 15"
