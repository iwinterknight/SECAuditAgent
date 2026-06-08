---
spec: 2026-06-04-ingestion-parsing
stage: implement
report: 04-implement-T9
created: 2026-06-08
---

# Educator Report — IMPLEMENT · M1 Ingestion & parsing (T9 · JSONL serialization — deterministic write/read)

> **How to read this.** Top-down: first *where* this task sits, then the *domain*
> it encodes (JSONL, and why **byte-identical determinism** is the whole point of
> this task — it underwrites the rebuild guarantee and the bake-once-reuse
> deployment), then the precise invariants and *why each one exists*, then the
> architecture view and the mandatory two-level **Code Walkthrough**. By the end
> you should be able to defend why we write **bytes** instead of text, and why
> `Decimal` must serialize to a string and never a float.

---

## 1. Where we are (orientation)

We just finished **T9** of **M1 (Ingestion & parsing)**. T4/T6/T7 produce the two
in-memory streams (`XBRLFact`s and item-stamped `Element`s); T9 is the
**persistence boundary** that writes them to disk and reads them back —
`ingestion.serialize.write_jsonl` / `read_jsonl`. This is the first concrete piece
of the **parse-once, reuse-forever** design you asked for: the expensive parse
happens once and its output is *serialized*, and everything downstream (and the
eventual Docker image) reads the serialized form rather than re-parsing. T9
doesn't decide *where* files go (that's T10, the pipeline); it decides *how* a
stream becomes bytes, deterministically. On the data-flow diagram it's the arrow
from the in-memory streams into the gitignored `data/derived/` corpus.

## 2. The domain in play (teach me)

### 2.1 JSONL, and why this form

**JSONL** (JSON Lines) is one JSON object per line, separated by `\n`. For a
stream of thousands of homogeneous records it beats the alternatives: it's
**append-friendly** (add a record = add a line), **streamable** (read line by line
without loading the whole file), **line-diffable** (a one-record change is a
one-line diff), and trivially parseable. A single giant JSON array would force
whole-file loads and make diffs useless; a binary format (Parquet) would be
faster but opaque and harder to verify byte-for-byte. For a corpus we want to
*audit and rebuild*, human-readable JSONL is the right call.

### 2.2 Determinism / byte-identity — the actual deliverable

The reason serialization is its **own task with its own gate** is one property:
**serializing the same rows twice produces byte-identical output.** Why it matters:

- **Rebuild verification (AC7).** The pipeline's promise is "a second
  `pipeline.run()` over unchanged source yields byte-identical JSONL." That is only
  checkable if serialization is deterministic — otherwise every rebuild differs and
  the guarantee is meaningless.
- **Bake-once-reuse trust (your deployment requirement).** If the derived corpus
  is built once and baked into a Docker image, byte-identity is what lets you
  *prove* the shipped bundle equals a fresh rebuild — diff the bytes. Non-determinism
  would make the baked artifact unverifiable.
- **Reproducibility.** A deterministic artifact is cacheable and comparable across
  machines and runs.

Byte-identity is unforgiving — *any* run-to-run wobble breaks it — so every source
of variation is pinned (next section).

### 2.3 The invariants, and what each one defends

| Invariant | Mechanism | What it prevents |
|---|---|---|
| Rows in a fixed order | sort by a **total key** — `ordinal` (Elements), `fact_id` (Facts) | dict/set iteration order or parse order reshuffling lines between runs |
| Object keys in a fixed order | `json.dumps(..., sort_keys=True)` | model field-order or version changes reordering keys |
| `Decimal` -> canonical **string** | pydantic `model_dump(mode="json")` | binary-float drift — a number losing precision (a §1.2 violation) |
| dates -> ISO-8601 `YYYY-MM-DD` | pydantic `mode="json"` | locale/format variation |
| `\n` endings, no `\r\n` | **`write_bytes`**, not `write_text` | Windows text mode silently rewriting `\n` -> `\r\n`, breaking byte-identity |
| UTF-8, compact, no trailing whitespace | `ensure_ascii=False`, `separators=(",", ":")` | encoding drift and stray spaces |

The `Decimal`-as-string point is the §1.2 firewall showing up again at the
persistence layer: a figure that survived the XBRL transform exactly must also
survive *disk* exactly. A float would quietly corrupt it.

### 2.4 Two implementation subtleties

- **Why `model_dump(mode="json")` *then* `json.dumps`, not `model_dump_json()`.**
  Pydantic's direct `model_dump_json()` emits keys in *field-definition* order and
  gives no `sort_keys` knob. To force a fixed key order we dump to a plain
  JSON-able dict first, then hand it to `json.dumps(..., sort_keys=True)`.
- **Validation on read.** `read_jsonl` parses each line with
  `model.model_validate_json`, so the same boundary validation that guards
  construction (a fact can't blend period types; a value must be numeric) runs
  again at read time. A corrupted derived file fails loudly, never silently feeds
  a bad row downstream.

## 3. The high-level view (architecture)

T9 adds `ingestion.serialize` — a small, **path-agnostic** module in the
`ingestion` layer. It consumes and reconstructs the two §5 contracts (`Element`,
`XBRLFact`) but constructs neither itself beyond reading them back; it imports
`config.schema` (the types) and `pydantic`, nothing sideways or up.

```
   in-memory streams                         on disk (gitignored data/derived/)

   list[Element] / list[XBRLFact]            {accession}.jsonl  (one JSON
            │                                 object per line)
            │   write_jsonl(rows, path):              ▲
            │     1. sort rows by total key           │  (bytes: LF, UTF-8)
            │        (ordinal / fact_id)              │
            │     2. json.dumps(sort_keys) per row ───┘
            ▼
   read_jsonl(path, model):  model.model_validate_json(line)  ─▶  list[model]

   (T10's pipeline chooses the paths and calls these; T9 is how, not where.)
```

- **Consumes / produces:** `Element` / `XBRLFact` in and out; bytes on disk.
- **Boundary note:** path-agnostic by design — the PDF<->accession<->FY join and
  the `data/derived/...` layout are T10's responsibility, kept out of here so
  serialization stays a pure, testable transform.

## 4. The drill-down (low level) — the two-level Code Walkthrough

### Module level

- **Module:** `ingestion.serialize` — the persistence boundary for both streams.
- **Role / data-flow position:** the arrow from the in-memory streams to the
  gitignored derived corpus; the inverse on read. Used by T10's pipeline.
- **Boundary change vs §5 contracts:** none — it serializes and re-validates the
  existing contracts; defines no new type.

### File level

**`src/ingestion/serialize.py`** — the whole task.

- **Module docstring** — teaches the determinism contract and enumerates the
  invariants, so a future reader can't "tidy" `write_bytes` into `write_text` (and
  silently reintroduce CRLF) or swap the two-step dump for `model_dump_json` (and
  lose `sort_keys`).
- `_SORT_KEYS = {Element: ...ordinal, XBRLFact: ...fact_id}` — the total key per
  stream as data; the one place the ordering rule lives.
- `write_jsonl(rows, path)` — list the rows; if non-empty, look up the sort key by
  row type (unknown type -> `ValueError`, fail closed) and sort; serialize each row
  with `json.dumps(model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
  separators=(",", ":"))`; join with `\n`; `mkdir` parents; **`write_bytes`** the
  UTF-8 encoding (LF on every OS).
- `read_jsonl(path, model)` — read UTF-8 text, and for each non-blank line return
  `model.model_validate_json(line)` — a validated `list[model]`. The inverse of
  `write_jsonl`, with the boundary checks re-applied.

**`tests/unit/test_serialize.py`** — pure tests (0.13s, no corpus):
- `test_roundtrip_and_byte_stable` — for both streams (Elements, Facts), built
  *out of* total-key order and covering both period shapes, empty/non-empty
  `dimensions`, both legal entities, and a non-ASCII em-dash: read-back equals the
  input sorted by total key; re-writing the same rows is byte-identical; and
  re-serializing the read-back is byte-identical. Plus on-disk invariants (no
  `\r\n`, trailing `\n`, valid UTF-8, no trailing whitespace, each line a JSON
  object).
- `test_empty_and_unsupported_type` — an empty list writes an empty file and reads
  back to `[]`; an unsupported model type fails closed with `ValueError`.

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| On-disk form | **JSONL** (one object/line) | one big JSON array / Parquet | append/stream/line-diff friendly and byte-auditable; array forces whole-file loads, Parquet is opaque (§2.1) |
| Writing | **`write_bytes`** with explicit `\n` | `write_text` | text mode on Windows rewrites `\n` -> `\r\n` and breaks byte-identity (§2.3) |
| `Decimal` | canonical **string** (`mode="json"`) | JSON number / float | a float loses precision — a §1.2 fidelity violation (§2.3) |
| Key order | `json.dumps(sort_keys=True)` over a dumped dict | `model_dump_json()` | the direct dumper has no `sort_keys`; field order isn't guaranteed stable (§2.4) |
| Sort key | type-dispatched `ordinal` / `fact_id` | leave ordering to the caller | the canonical total key belongs with serialization; one definition site |
| Read | re-validate via `model_validate_json` | `json.loads` into dicts | a corrupted derived row fails loudly, not silently downstream (§2.4) |
| Scope | its own module + its own test | fold into the pipeline (T10) | an isolated, fast, decisive determinism check beats proving it only through the slow full rebuild |

## 6. Open threads & what's next

- **No new `[RATIFY]`/`[VERIFY]` markers**; no contract changed; nothing
  discovered that splits the task.
- **This is the persistence half of "parse once, reuse."** T9 gives the *how*;
  **T10** gives the *where* and *when* — `pipeline.run()` resolves the
  PDF<->accession<->FY join, parses + extracts each filing **once**, and calls
  `write_jsonl` into the gitignored `data/derived/` corpus (the bake-ready
  artifact for Docker), with the byte-identical second run as its acceptance. T10
  also lights up the relocated real-corpus Item test (T7 -> T10), which reads this
  JSONL instead of re-parsing.
- **Next:** `/implement T10`. (T10 is `@slow` — it runs the single full parse over
  all five filings — so expect the one long run there, by design, exactly once.)
