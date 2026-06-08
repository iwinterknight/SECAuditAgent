"""T9 — deterministic JSONL serialization for both ingest streams.

The decisive property is **byte-identity**: serializing the same rows twice yields
identical bytes (what AC7's rebuild guarantee and the bake-once-reuse corpus rest
on), and a round-trip (write -> read -> write) is byte-identical too. These pure
tests pin that, plus the on-disk invariants (LF endings, UTF-8, no trailing
whitespace) and exact ``Decimal``/``date`` fidelity across the round-trip. No
corpus, no parse.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel

from config.schema import Element, ElementKind, Entity, PeriodType, XBRLFact
from ingestion.serialize import read_jsonl, write_jsonl


def _elements() -> list[Element]:
    """Three Elements, intentionally out of ``ordinal`` order, one with a non-ASCII
    character (em-dash) to exercise UTF-8."""
    return [
        Element(
            element_id="acc:5:2",
            kind=ElementKind.TABLE,
            text="<table><tr><td>1,234</td></tr></table>",
            fiscal_year=2024,
            item="Item 8",
            page=5,
            source_filing="acc",
            ordinal=2,
        ),
        Element(
            element_id="acc:1:0",
            kind=ElementKind.HEADING,
            text="Item 7. MD&A — Overview",  # em-dash: UTF-8, not ASCII
            fiscal_year=2024,
            item="Item 7",
            page=1,
            source_filing="acc",
            ordinal=0,
        ),
        Element(
            element_id="acc:3:1",
            kind=ElementKind.TEXT,
            text="Net revenue rose.",
            fiscal_year=2024,
            item="Item 7",
            page=3,
            source_filing="acc",
            ordinal=1,
        ),
    ]


def _facts() -> list[XBRLFact]:
    """Three XBRLFacts, out of ``fact_id`` order, covering both period shapes, an
    empty and a non-empty ``dimensions``, and both legal entities."""
    return [
        XBRLFact(
            fact_id="acc:us-gaap:NetIncomeLoss:cD:USD",
            entity=Entity.JPMC_CONSOLIDATED,
            concept="us-gaap:NetIncomeLoss",
            period_type=PeriodType.DURATION,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            value=Decimal("58471000000"),
            unit="USD",
            decimals=-6,
            source_filing="acc",
        ),
        XBRLFact(
            fact_id="acc:us-gaap:Assets:cI:USD",
            entity=Entity.JPMC_CONSOLIDATED,
            concept="us-gaap:Assets",
            period_type=PeriodType.INSTANT,
            period_instant=date(2024, 12, 31),
            value=Decimal("4002814000000"),
            unit="USD",
            decimals=-6,
            source_filing="acc",
        ),
        XBRLFact(
            fact_id="acc:us-gaap:Deposits:cI:USD:bank",
            entity=Entity.JPMORGAN_CHASE_BANK_NA,
            concept="us-gaap:Deposits",
            period_type=PeriodType.INSTANT,
            period_instant=date(2024, 12, 31),
            value=Decimal("2400000000000"),
            unit="USD",
            decimals=-6,
            dimensions={"us-gaap:LegalEntityAxis": "jpm:BankNAMember"},
            source_filing="acc",
        ),
    ]


def test_roundtrip_and_byte_stable(tmp_path: Path) -> None:
    """For both streams: read-back equals input (sorted by total key), and the
    output is byte-identical across a re-write and across a read+re-write."""
    cases = [
        (_elements(), Element, lambda e: e.ordinal, "elements.jsonl"),
        (_facts(), XBRLFact, lambda f: f.fact_id, "facts.jsonl"),
    ]
    for rows, model, key, fname in cases:
        path = tmp_path / fname
        write_jsonl(rows, path)
        first = path.read_bytes()

        # Round-trip: read back equals the input, in total-key (sorted) order.
        back = read_jsonl(path, model)
        assert back == sorted(rows, key=key)

        # Determinism: re-writing the same rows is byte-identical.
        again = tmp_path / f"again-{fname}"
        write_jsonl(rows, again)
        assert again.read_bytes() == first

        # Round-trip stability: re-serializing the read-back is byte-identical.
        reserialized = tmp_path / f"reser-{fname}"
        write_jsonl(back, reserialized)
        assert reserialized.read_bytes() == first

        # On-disk invariants: LF endings, valid UTF-8, trailing newline, no
        # trailing whitespace, each line a standalone JSON object.
        assert b"\r\n" not in first
        assert first.endswith(b"\n")
        for line in first.decode("utf-8").splitlines():
            assert line == line.rstrip()
            assert isinstance(json.loads(line), dict)


def test_empty_and_unsupported_type(tmp_path: Path) -> None:
    """An empty list writes an empty file and reads back to ``[]``; an unsupported
    model type fails closed."""
    empty = tmp_path / "empty.jsonl"
    write_jsonl([], empty)
    assert empty.read_bytes() == b""
    assert read_jsonl(empty, Element) == []

    class Other(BaseModel):
        x: int

    with pytest.raises(ValueError):
        write_jsonl([Other(x=1)], tmp_path / "bad.jsonl")
