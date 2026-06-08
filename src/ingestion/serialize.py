"""Deterministic JSONL serialization for the two ingest streams (Element, XBRLFact).

Both streams are persisted as **JSONL** — one JSON object per line — under a
gitignored derived root. This module is the read/write boundary for that form, and
its one non-negotiable property is **determinism**: serializing the same rows
twice produces **byte-identical** output. That is what lets the ingestion rebuild
be verified (AC7: "a second `pipeline.run()` is byte-identical") and what makes the
derived corpus a trustworthy, *bake-once-reuse* deployment artifact — you can prove
a shipped bundle equals a fresh rebuild by comparing bytes.

Byte-identity is unforgiving, so every source of run-to-run variation is pinned:

- **Rows are sorted by a *total* key.** Elements by ``ordinal`` (unique within a
  filing), XBRLFacts by ``fact_id`` (it folds in concept + context + unit, so it
  totally orders them). No ties means no reshuffling between runs.
- **Object keys are emitted in a fixed order** (``json.dumps(..., sort_keys=True)``)
  — independent of model field order.
- **``Decimal`` serializes to a canonical string, never a binary float** (pydantic
  ``mode="json"``), so exact-match numeric fidelity (§1.2) survives a round-trip;
  **dates serialize to ISO-8601** (``YYYY-MM-DD``).
- **Compact separators** (no spaces), **``\n`` line endings**, **UTF-8**, no
  trailing whitespace. We write **bytes** rather than text so the on-disk newlines
  are ``\n`` on every OS — Windows text mode would translate ``\n`` to ``\r\n`` and
  silently break byte-identity.

The module is path-agnostic: callers (the pipeline, T10) decide *where* each
stream is written; this module decides only *how*.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from config.schema import Element, XBRLFact

_Model = TypeVar("_Model", bound=BaseModel)

# The "total key" that orders each stream. ``ordinal`` is unique within a filing's
# Elements; ``fact_id`` is unique within a filing's XBRLFacts — so each gives a
# total order (no ties), which is what makes the sorted output stable run to run.
_SORT_KEYS = {
    Element: lambda row: row.ordinal,
    XBRLFact: lambda row: row.fact_id,
}


def write_jsonl(rows: Sequence[Element] | Sequence[XBRLFact], path: Path) -> None:
    """Serialize a homogeneous list of Elements or XBRLFacts to deterministic JSONL.

    ``rows`` must be all-Element or all-XBRLFact (the pipeline writes one stream per
    file); the row type selects the sort key. Parent directories are created. The
    output is byte-identical for equal input — see the module docstring for the
    invariants that guarantee it.
    """
    rows = list(rows)
    if rows:
        sort_key = _SORT_KEYS.get(type(rows[0]))
        if sort_key is None:
            raise ValueError(
                "write_jsonl serializes Element or XBRLFact, not "
                f"{type(rows[0]).__name__}"
            )
        rows = sorted(rows, key=sort_key)
    lines = [
        json.dumps(
            row.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for row in rows
    ]
    content = "".join(f"{line}\n" for line in lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes (not write_text): keep newlines LF on every OS, so byte-identity
    # holds — Windows text mode would rewrite \n as \r\n.
    path.write_bytes(content.encode("utf-8"))


def read_jsonl(path: Path, model: type[_Model]) -> list[_Model]:
    """Read a JSONL file back into a list of ``model`` instances (validated).

    The inverse of :func:`write_jsonl`: each non-blank line is parsed and validated
    by the given Pydantic ``model`` (``Element`` or ``XBRLFact``), so a row that
    blends period types or carries a non-numeric value fails loudly at read time,
    exactly as it would at construction.
    """
    text = path.read_text(encoding="utf-8")
    return [
        model.model_validate_json(line) for line in text.splitlines() if line.strip()
    ]
