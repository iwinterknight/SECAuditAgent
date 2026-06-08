---
spec: 2026-06-04-ingestion-parsing
stage: implement
report: 04-implement-T10
created: 2026-06-08
---

# Educator Report — IMPLEMENT · M1 Ingestion & parsing (T10 · Ingestion pipeline CLI — the join + rebuild)

> **How to read this.** Top-down: first *where* this task sits, then the *domain*
> it encodes (the PDF<->accession<->FY join, the byte-identical rebuild, and a
> real, non-obvious discovery about how JPMorgan structures its 10-K), then the
> architecture view and the mandatory two-level **Code Walkthrough**. T10 is the
> capstone of M1: it turns the four pure producers into a one-command rebuild of
> the persisted, bake-ready corpus. By the end you should understand why ~82% of
> FY2024's Elements are labeled `Item 15`, and why that is *correct*.

---

## 1. Where we are (orientation)

We just finished **T10** of **M1 (Ingestion & parsing)** — the **pipeline**. T4/T6/
T7/T9 built the pieces (extract facts, parse Elements, stamp Items, serialize);
T10 is the **orchestrator** that wires them to the corpus. `ingestion.pipeline.run`
reads `Settings.FILINGS` (the sole PDF<->accession<->fiscal-year join) and, per
filing, runs both lanes into the gitignored derived corpus:

```
   PDF   -> parse_elements -> assign_items -> write_jsonl  (elements/{accession}.jsonl)
   iXBRL -> extract_facts                  -> write_jsonl  (facts/{accession}.jsonl)
```

This is the concrete realization of **parse once, reuse forever**: `run()` builds
`data/derived/ingestion/...` once; everything downstream (chunking M2, indexing M3)
and the eventual Docker image read that corpus instead of re-parsing. Because the
build is byte-identical on re-run, the corpus is a *verifiable* bake-once-reuse
artifact. On the data-flow diagram, T10 is the box that finally writes the
left-most stage's output to disk.

## 2. The domain in play (teach me)

### 2.1 The join lives in exactly one place

A JPM 10-K PDF is named by its period-end date (`jpm-20241231.pdf`); its
`source_filing` tag and every derived path are keyed by the SEC **accession**
(`0000019617-25-000270`); and it reports on a **fiscal year** (2024). Those three
namings must never disagree. `Settings.FILINGS` is the single ordered table that
ties them together, and **the pipeline is the only consumer that resolves the
join** — no other module re-parses a filename for a year or guesses an accession.
This is the §1.5 single-source-of-truth discipline applied to provenance: one
table, one reader.

### 2.2 Fail loud, up front

`run(accessions)` resolves *every* accession against `FILINGS` **before** parsing
anything. A typo'd accession raises immediately, rather than silently producing an
empty corpus that looks like a success. Validating up front also means the
expensive parse never starts on a bad input (§1.5 fail-closed). `None` rebuilds
all five filings; an explicit list rebuilds that subset.

### 2.3 The byte-identical rebuild (AC7), and why it matters

A second `run()` over unchanged source produces **byte-identical** JSONL. This
rests on three things already built: **stable ids** (`fact_id` / `element_id`,
T4/T6), **deterministic serialization** (sorted rows + sorted keys + canonical
Decimal, T9), and a **deterministic parse** (fixed model weights, no inference
randomness). Why it matters: it makes the rebuild *checkable* (re-run and diff),
and it makes the baked Docker corpus *trustworthy* — you can prove the shipped
bundle equals a fresh rebuild byte-for-byte. The `@slow` test asserts exactly
this, and runs under an offline environment so a pass also proves the rebuild
needs **no network** (Docling weights and Arelle taxonomy come from warm caches;
the XBRL packages are vendored).

### 2.4 The discovery: JPMorgan incorporates MD&A and the financials *by reference*

Building the FY2024 corpus surfaced a real, non-obvious fact about JPM's 10-K, and
the corpus test caught it. A "textbook" 10-K puts MD&A under **Item 7** and the
financial statements under **Item 8**. JPMorgan does **not**: its 10-K *body*
states Items 7 and 8 as **cross-references** and files the substantive content as
**Exhibit 13** under **Item 15**. Verbatim from the FY2024 body:

> **Item 7:** "Management's discussion and analysis ... appears on pages 52-167."
> **Item 8:** "The Consolidated Financial Statements, together with the Notes
> thereto and the report thereon ... of PricewaterhouseCoopers LLP ..."

So `assign_items` (a forward-fill from Item headings) correctly labels the body
Item 7/8 *headings*, and then labels the entire Exhibit 13 content — the real
MD&A (pages 52-167), the financial statements (174+), the notes — as **Item 15**,
because Item 15 ("Exhibits and Financial Statement Schedules") is the last body
Item heading before it. The FY2024 result:

| Item | Elements | What it is |
|---|---|---|
| Item 15 | 4,215 (82%) | Exhibit 13: the actual MD&A + financial statements + notes |
| Item 1A | 672 | Risk Factors (a real, large body) |
| Item 1 | 105 | Business |
| Item 7 / Item 8 | 2 / 3 | the body cross-reference statements only |

**`assign_items` is correct** — it stamps the literal document structure. But it
means the substantive MD&A/financials are *not* findable by their semantic Item
(7/8); they are under Item 15. That is fine for M1 (faithful provenance), but it
is a real **retrieval** concern (M2+): to scope a query to "MD&A" the system will
need to understand Exhibit 13's internal structure. That enhancement is logged as
**Discovered work** (its own future spec), deliberately out of M1's scope. The
corpus test was rewritten to assert this *real* behavior rather than the textbook
assumption — which is the whole value of testing against the live corpus.

## 3. The high-level view (architecture)

T10 adds `ingestion.pipeline`, the orchestrator at the top of the `ingestion`
layer. It is the only module that imports *all four* producers plus `config`:

```
   config.settings.FILINGS  ── the one PDF<->accession<->FY join
            │
            ▼
   ingestion.pipeline.run(accessions=None)
       resolve+validate accessions (unknown -> hard error, before any parse)
       for each filing:
         parse_elements -> assign_items -> write_jsonl   (elements/{acc}.jsonl)
         extract_facts                  -> write_jsonl   (facts/{acc}.jsonl)
            │
            ▼
   data/derived/ingestion/{elements,facts}/{accession}.jsonl   (gitignored)
       consumed by chunking (M2), indexing (M3), and the Docker image
```

- **Consumes:** `Settings.FILINGS` + the read-only source corpus (`data/SEC/`).
- **Produces:** the gitignored derived JSONL — and *only* there; it never mutates
  the source (§1.8).
- **Boundary note:** the two lanes share no number — the §1.2 firewall (enforced
  structurally by T8). `.gitignore` already covers `data/derived/` (added in T1),
  so no `.gitignore` change was needed despite being listed in the task.

## 4. The drill-down (low level) — the two-level Code Walkthrough

### Module level

- **Module:** `ingestion.pipeline` — the orchestrator + CLI. The only resolver of
  the corpus join.
- **Role / data-flow position:** turns the pure producers into a one-command
  rebuild of the persisted corpus; the last M1 stage.
- **Boundary change vs §5 contracts:** none — it composes existing contracts; the
  firewall is preserved (it constructs no `XBRLFact`/`Element` itself, it calls
  the producers).

### File level

**`src/ingestion/pipeline.py`** — the orchestrator.
- **module docstring** — teaches the join, the three contract points (join-here-
  only, fail-loud, read-only-source/byte-identical-rebuild), and the CLI.
- `_elements_path` / `_facts_path` — the gitignored JSONL path per stream
  (`data/derived/ingestion/{elements,facts}/{accession}.jsonl`).
- `_rebuild_filing(filing, settings)` — one filing's two lanes: parse -> assign
  Items -> write Elements; extract -> write Facts; logs the counts. The two lanes
  share no number.
- `run(accessions=None)` — resolves/validates accessions up front (unknown ->
  `KeyError`, before any parse), then rebuilds each filing. `None` -> all five.
- `main(argv=None)` + `__main__` — the `python -m ingestion.pipeline [accession ...]`
  CLI; configures logging at the boundary so per-filing progress is visible.

**`tests/unit/test_pipeline_rebuild.py`**
- `test_unknown_accession_raises` (**fast**) — a typo raises before any parse.
- `test_deterministic_and_gitignored` (**@slow**) — `run()` over all five writes
  both streams under the gitignored root; a second `run()` is byte-identical;
  `.gitignore` covers `data/derived/`. Launched offline to also prove no-fetch.

**`tests/unit/test_elements_provenance.py`** (modified)
- `fy2024_derived_elements` (session fixture) — reads the FY2024 Element JSONL,
  building it once if absent (the parse-once, read-the-serialized-stream model).
- `test_known_elements_land_in_right_item` (**@slow**) — asserts the real Item
  behavior on JPM's structure (body Item 7/8 headings labeled; Item 1A's large
  body; financial statements under Item 15 / Exhibit 13).

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| Where the join lives | only in `pipeline.run` (reads `FILINGS`) | re-derive FY from filename in producers | single source of truth for provenance (§2.1) |
| Unknown accession | hard error, validated **up front** | skip / warn / fail mid-parse | a typo must not look like success, and must not waste a parse (§2.2) |
| Derived form/paths | JSONL at `data/derived/ingestion/{elements,facts}/` | one combined file / Parquet | inspectable, diffable, byte-auditable; columnar store is M3 |
| Corpus test data | read the serialized JSONL (build once if absent) | re-parse in the test | parse-once; matches the plan's corpus-test strategy |
| Corpus test assertions | the **real** behavior (financials -> Item 15) | the textbook MD&A->7 / financials->8 | JPM incorporates by reference; test reality, not an assumption (§2.4) |
| Rebuild determinism | faithful: all five rebuilt twice | re-check one filing (cheaper) | literal AC7; the run is a background job, so the extra time is unattended |
| No-fetch proof | launch under offline env | in-test `monkeypatch.setenv` | huggingface_hub reads the flag at import, so in-test setenv is a no-op |
| Semantic MD&A/financials | logged as Discovered work | widen M1 to map Exhibit 13 | a real retrieval enhancement, but its own spec — out of M1 scope (§2.4) |

## 6. Open threads & what's next

- **`@slow` rebuild result:** [[SLOW_RESULT]]
- **Full corpus built:** [[CORPUS_TOTALS]]
- **Discovered work logged:** semantic section labels for incorporated-by-reference
  exhibits (Exhibit 13 -> MD&A/financials), so retrieval can scope to "MD&A" / "the
  financial statements" by Item. Its own future spec; out of M1 scope.
- **No new `[RATIFY]`/`[VERIFY]` markers.** The §1.2 firewall (T8) and byte-identical
  serialization (T9) both hold across the real corpus.
- **M1 status:** T1-T10 done; **T11** (doc-promotions — ratify §1.3, refine the
  architecture's EDGAR-vs-vendored wording, fix the citation) is the last task,
  then the **EVALUATE** pass closes M1. Run `/implement T11`.
