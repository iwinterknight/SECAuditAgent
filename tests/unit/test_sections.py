"""T7 unit tests for the Item-boundary pass (``assign_items``) over a tiny,
checked-in heading fixture — no corpus, no parse, runs in milliseconds.

The real-corpus Item-correctness check (an MD&A Element -> ``Item 7``, a
financial-statements Element -> ``Item 8``) reads the serialized derived JSONL,
so it lives with the pipeline that produces that JSONL (T10), per the plan's test
strategy ("corpus tests read the serialized derived streams -- fast, no
re-parse"). These pure tests pin the *logic*: forward-fill from Item headings, the
1A/7A suffix, and -- the case this pass exists for -- failing a garbled boundary
to ``unknown`` rather than mis-attributing it to the previous Item.
"""

from config.schema import Element, ElementKind
from ingestion.sections import UNKNOWN_ITEM, assign_items


def _el(kind: ElementKind, text: str, ordinal: int) -> Element:
    """Build a minimal Element for the fixture (entity defaults to consolidated)."""
    return Element(
        element_id=f"acc:1:{ordinal}",
        kind=kind,
        text=text,
        fiscal_year=2024,
        item=UNKNOWN_ITEM,
        page=1,
        source_filing="acc",
        ordinal=ordinal,
    )


def test_missing_header_yields_unknown() -> None:
    """A garbled Item heading resets the section to ``unknown``, never the prior Item.

    Also pins that content before the first Item heading is ``unknown`` (cover page
    / index): a boundary is required to leave ``unknown``, never assumed.
    """
    heading, text = ElementKind.HEADING, ElementKind.TEXT
    elements = [
        _el(text, "JPMorgan Chase & Co. Annual Report on Form 10-K", 0),  # cover
        _el(heading, "Item 1A. Risk Factors", 1),
        _el(text, "Credit risk is the risk of loss ...", 2),
        _el(heading, "Item -- Quantitative Disclosures", 3),  # candidate, no number
        _el(text, "Market-risk content under the garbled header ...", 4),
    ]

    out = assign_items(elements)
    item_of = {e.ordinal: e.item for e in out}

    assert item_of[0] == UNKNOWN_ITEM       # before any Item heading
    assert item_of[1] == "Item 1A"          # recognized header (suffix preserved)
    assert item_of[2] == "Item 1A"          # forward-filled into following prose
    assert item_of[3] == UNKNOWN_ITEM       # garbled boundary -> unknown ...
    assert item_of[4] == UNKNOWN_ITEM       # ... and the content under it too
    assert item_of[4] != "Item 1A"          # the whole point: never the prior Item


def test_forward_fill_and_subheadings() -> None:
    """Recognized Item headers forward-fill; ordinary sub-headings do not reset it."""
    heading, text = ElementKind.HEADING, ElementKind.TEXT
    elements = [
        _el(heading, "Item 7. Management's Discussion and Analysis", 0),
        _el(heading, "Overview", 1),  # ordinary sub-heading, not an Item boundary
        _el(text, "Net revenue rose ...", 2),
        _el(heading, "Item 8. Financial Statements and Supplementary Data", 3),
        _el(text, "Consolidated balance sheets ...", 4),
    ]

    out = assign_items(elements)

    assert [e.item for e in out] == ["Item 7", "Item 7", "Item 7", "Item 8", "Item 8"]
    # assign_items is pure: the input Elements are untouched.
    assert all(e.item == UNKNOWN_ITEM for e in elements)
