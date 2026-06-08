# 01 · Data foundation — from filings to a corpus

> Code: `src/ingestion/*`, contracts in `src/config/schema.py`. This is the
> **offline** half — it runs once and produces the corpus everything else reads.

## A 10-K has two bodies, so we keep two streams

Every 10-K is filed twice over:

1. **The document** — ~300 pages of prose, tables, headings (the PDF / HTML you read).
2. **Inline XBRL (iXBRL)** — the *same* report with every reported figure machine-
   tagged: `us-gaap:Assets = 4002814000000` for the period ending 2024-12-31, in USD.

These map to the two kinds of question (narrative vs numeric), so we extract them
into two separate, typed streams and never mix them:

| Stream | Built by | Contract | Used for |
|---|---|---|---|
| **Elements** | `ingestion/elements.py` (PDF) | `Element` | narrative retrieval (doc 02) |
| **XBRLFacts** | `ingestion/xbrl.py` (XBRL) | `XBRLFact` | exact figures + arithmetic (doc 03) |

## The §1.2 firewall (the single most important rule)

> **Financial numbers are *constructed* only in the XBRL path.** `XBRLFact` is
> defined in exactly one place (`schema.py`) and built in exactly one place
> (`ingestion/xbrl.py`). No number is ever read out of parsed PDF text.

Why so strict: PDF text is OCR-/layout-derived and lossy — "$4,002,814" can drop a
digit or merge a column. XBRL is what the company *filed* to the SEC, exact and
typed. By making XBRL the *only* constructor of figures, "the model can't invent a
number" stops being a hope and becomes a structural property. The contracts enforce
the supporting invariants:

- `value: Decimal` (never `float`) — exact-match fidelity isn't lost to float drift.
- A `model_validator` rejects any fact that **blends period types** — an `instant`
  (balance-sheet "as of") carrying a duration's start/end, or vice-versa. A blended
  fact can't even be constructed, let alone reach an answer.
- `Entity` keeps **JPMC consolidated** distinct from the **bank subsidiary** — both
  appear in the same filing with different numbers; conflating them is a fidelity bug.

## Building the Elements stream — Docling

`elements.py` runs **Docling** (layout model + **TableFormer** for table structure)
over each PDF and emits one `Element` per text block / table / heading:

```python
class Element(BaseModel):
    element_id: str       # stable: {accession}:{page}:{ordinal}
    kind: ElementKind     # text | table | heading
    text: str             # tables are serialized structure-preservingly
    fiscal_year: int
    item: str             # "Item 7", "Item 15", … ("unknown" until a boundary)
    page: int             # 1-based page in the source PDF
    entity: Entity
    source_filing: str    # accession, e.g. "0000019617-25-000270"
    ordinal: int          # reading-order index within the filing
```

Two fields do a lot of downstream work: **`page`** powers citations ("(FY2024, p.97)"),
and **`ordinal`** (reading order) powers parent-expansion in retrieval (doc 02) — and
caused a real bug there worth reading about.

### The memory saga (a genuine nuance)

A single Docling `convert()` over a 300-page PDF **OOM-ed** (`std::bad_alloc`): the
backend accumulates per-page state for the whole document at once. Fixes, in order
of impact:

- **Page-windowing** — parse in 16-page windows and release each window's backend
  state before the next. Process RSS stays ~1.2 GB instead of climbing unbounded.
- **Lighter models** — `layout_v2` + **TableFormer FAST** (vs ACCURATE), `page_batch_size=1`.
- GPU wasn't an option (CPU-only torch, no NVIDIA driver) — and the blow-up was in
  CPU/system RAM during preprocessing, not VRAM anyway.

Lesson for doc 06: the heavyweight parse is exactly why ingestion is **offline and
parse-once** — you would never want this on a request path.

## Building the XBRLFacts stream — Arelle

`xbrl.py` runs **Arelle** over the filing's iXBRL to produce `XBRLFact`s. Arelle
applies the XBRL **transforms** (scale, sign) so `value` is the real number, resolves
the **unit** (USD, USD/shares, shares, pure), and carries the **period** (instant vs
duration with its dates) and any remaining **dimensions**. `fact_id` is stable
(`{filing}:{concept}:{context}:{unit}`) so re-running is deterministic.

## The JPMorgan structure finding (don't assume Item 7/8)

A textbook expectation is that MD&A is **Item 7** and the financial statements are
**Item 8**. JPMorgan (like many large filers) instead **incorporates them by
reference**: the MD&A and statements are filed as **Exhibit 13 under Item 15**. So
~82% of FY2024 Elements land in *Item 15*, not 7/8. The takeaway: derive structure
from the actual filing, don't hard-code a layout — `sections.py` assigns `item` from
real boundaries, and a test that assumed 7/8 was rewritten to assert reality.

## The corpus — deterministic JSONL, built once, baked

`serialize.py` writes each stream to **JSON Lines** (`read_jsonl` / `write_jsonl`),
sorted deterministically so a rebuild is byte-stable and diffable. `pipeline.py` is
the CLI that runs the whole chain (`python -m ingestion.pipeline [accession …]`).

```
data/derived/ingestion/
  elements/   <accession>.jsonl      # the Element stream (per filing)
  facts/      <accession>.jsonl      # the XBRLFact stream (per filing)
  embeddings/ <accession>.npy        # dense vectors, built lazily by retrieval
```

Final clean corpus (5 filings): **17,009 Elements** — FY2021 4,032 · FY2022 4,863 ·
FY2023 5,094 · FY2024 5,111 · FY2025 4,847 — plus ~7,000–7,400 XBRL facts per filing.
This directory is **gitignored** but **baked into the Docker image** (doc 05): the
container serves it, never rebuilds it.

→ Next: [02 · Retrieval](02-retrieval.md) — how the Element stream becomes answers.
