"""Sub-chunk chunking (app/retrieval.py) — the fix for long-Element/table embedding
truncation. Pure-function tests: no network, no embeddings.

importorskip skips cleanly if the demo extras aren't installed (`pip install -e .[demo]`).
"""

import pytest

retrieval = pytest.importorskip("retrieval")

from config.schema import Element, ElementKind  # noqa: E402 (after importorskip)


def _element(text: str, kind: ElementKind = ElementKind.TEXT) -> Element:
    return Element(
        element_id="acc:1:0",
        kind=kind,
        text=text,
        fiscal_year=2024,
        item="Item 1",
        page=1,
        source_filing="acc",
        ordinal=0,
    )


def test_short_element_is_a_single_subchunk():
    e = _element("A short paragraph, comfortably under the chunk-size cap.")
    assert retrieval._subchunks(e) == [e.text]


def test_long_prose_splits_into_bounded_windows():
    e = _element(("word " * 800).strip())  # ~4000 chars, well over the 1200 cap
    chunks = retrieval._subchunks(e)
    assert len(chunks) > 1
    assert max(len(c) for c in chunks) <= retrieval._CHUNK_CHARS  # each window bounded


def test_table_splits_row_wise_and_repeats_header():
    header = "<tr><th>Metric</th><th>Value</th></tr>"
    rows = "".join(f"<tr><td>row{i}</td><td>{i}</td></tr>" for i in range(200))
    e = _element(f"<table><tbody>{header}{rows}</tbody></table>", kind=ElementKind.TABLE)
    chunks = retrieval._subchunks(e)
    assert len(chunks) > 1, "a 200-row table must split"
    assert all("<th>Metric</th>" in c for c in chunks), "every group keeps the header"


def test_table_content_beyond_the_old_800_cap_is_indexed():
    # The bug being fixed: only the first 800 chars were embedded, so late rows were
    # invisible. Prove a far-down row now lands in some sub-chunk.
    header = "<tr><th>Metric</th><th>Value</th></tr>"
    rows = "".join(f"<tr><td>item{i}</td><td>{i}</td></tr>" for i in range(300))
    e = _element(f"<table><tbody>{header}{rows}</tbody></table>", kind=ElementKind.TABLE)
    chunks = retrieval._subchunks(e)
    assert any("item299" in c for c in chunks), "late table content must be represented"
