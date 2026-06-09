"""Parent-expansion (app/retrieval.py) — reading-order neighbors, never across a filing
boundary (the multi-year ordinal-collision fix). Pure function, offline.
"""

import pytest

retrieval = pytest.importorskip("retrieval")

from config.schema import Element, ElementKind  # noqa: E402 (after importorskip)


def _el(idx: int, filing: str) -> Element:
    return Element(
        element_id=f"{filing}:1:{idx}",
        kind=ElementKind.TEXT,
        text=f"paragraph {idx}",
        fiscal_year=2024,
        item="Item 1",
        page=1,
        source_filing=filing,
        ordinal=idx,
    )


def test_expands_to_adjacent_reading_order_neighbors():
    elements = [_el(i, "A") for i in range(5)]
    out = retrieval._parent_expand(elements, [2])
    assert sorted(e.ordinal for e in out) == [1, 2, 3]  # the hit + its two neighbors


def test_never_crosses_a_filing_boundary():
    # filing A then filing B, concatenated; the last element of A must not pull in B's first
    elements = [_el(0, "A"), _el(1, "A"), _el(0, "B"), _el(1, "B")]
    out = retrieval._parent_expand(elements, [1])  # index 1 = last of filing A
    assert all(e.source_filing == "A" for e in out)
    assert {e.element_id for e in out} == {"A:1:0", "A:1:1"}


def test_deduplicates_overlapping_neighbor_windows():
    elements = [_el(i, "A") for i in range(5)]
    out = retrieval._parent_expand(elements, [1, 2])  # windows {0,1,2} and {1,2,3} overlap
    assert len(out) == len({e.element_id for e in out})  # no duplicates
    assert sorted(e.ordinal for e in out) == [0, 1, 2, 3]
