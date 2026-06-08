---
spec: 2026-06-04-ingestion-parsing
stage: implement
report: 04-implement-T6
created: 2026-06-07
---

# Educator Report — IMPLEMENT · M1 Ingestion & parsing (T6 · PDF parser — Docling → Elements with provenance)

> **How to read this.** Top-down: first *where* this task sits, then the
> *domain* it encodes (structured PDF parsing, the Element contract and why
> provenance is stamped here, the firewall mirror, what the parser refuses to
> guess, body-vs-furniture, and the memory-engineering story that dominated this
> task), then the *architecture* view, then the mandatory two-level **Code
> Walkthrough**. T6 writes the project's first real `src/` *producer* on the PDF
> side — `ingestion.elements.parse_elements`, the **sole** `Element` source. By
> the end you should be able to re-present every function in `elements.py` and
> defend why a 345-page filing is parsed in 16-page windows rather than all at
> once.

---

## 1. Where we are (orientation)

We just finished **T6** of **M1 (Ingestion & parsing)**. T4/T5 built and proved
the *numeric* lane (XBRLFacts, exact-match anchors). **T6 opens the *narrative*
lane** — the prose, headings and tables of the 10-K — and it is the PDF-side
mirror of the §1.2 firewall: `parse_elements` is the **one and only** place an
`Element` is constructed, just as `extract_facts` is the one place an `XBRLFact`
is. On the data-flow diagram (`docs/architecture.md` §4: ingest → chunk → index →
retrieve → agent → answer) T6 fills in the other half of the left-most box. Its
output — a reading-order list of provenanced `Element`s — is exactly what
chunking (M2) will consume; M2 never re-reads the PDF. Concretely, the FY2024
10-K (`jpm-20241231.pdf`, **345 pages**) parses into **5,111 Elements**
(3,989 text, 827 headings, 295 tables) — the first time the
system has turned a filing's *prose* into structured, citable units.

## 2. The domain in play (teach me)

### 2.1 What Docling is, and why a "structured parse" (not text extraction)

A 10-K PDF is a *visual* artifact: a stream of glyphs placed at coordinates, with
no inherent notion of "paragraph," "heading," or "table." Naive text extraction
(e.g. `pdftotext`) gives you a flat character soup — columns interleave, table
cells smear into one line, headings are indistinguishable from body text. That is
useless for retrieval, where we need to know *this is a heading*, *this is a
table with these rows*, *this paragraph is on page 73*.

**Docling** solves this with machine learning, in two stages:

- a **layout model** rasterizes each page to an image and labels every region —
  title, section header, paragraph, list item, table, picture, page header/footer
  — and emits them in **reading order** (resolving columns); and
- a **table-structure model (TableFormer)** reconstructs each table's row/column
  grid so a table comes back as real cells, not smeared text.

`document.iterate_items()` then walks that recovered structure as
`(node, level)` pairs. Our job in `elements.py` is small and deterministic:
*classify* each node into one of three kinds, *stamp provenance*, and drop what
we can't represent faithfully. We do not re-derive layout — that's the model's
job; we consume its output.

### 2.2 The `Element` contract, and why provenance is stamped *here*

`Element` (defined once in `config/schema.py`, architecture §5) is the typed unit
the narrative path speaks in:

| field | meaning |
|---|---|
| `element_id` | stable id `{accession}:{page}:{ordinal}` — the citation handle |
| `kind` | `text` \| `table` \| `heading` (`ElementKind`) |
| `text` | the prose, or a structure-preserving HTML serialization for a table |
| `fiscal_year` | which filing year this came from |
| `item` | the 10-K Item (Item 1, 1A, 7…); **`"unknown"` until T7** |
| `page` | 1-based source page |
| `entity` | legal entity — **always `JPMC_CONSOLIDATED`** at M1 |
| `source_filing` | accession folder, e.g. `0000019617-25-000270` |
| `ordinal` | filing-global reading-order index |

Provenance is stamped at *this* layer because it is the only layer that still
knows it. Once an Element flows into chunking, embedding and retrieval, the
fiscal year and page are gone unless we recorded them at birth. Every downstream
**Citation** (§1.5 — "no citation, no claim") for a narrative answer is
ultimately a pointer back to an `element_id`; if the Element didn't capture page
and FY here, the citation would be untraceable. This is the same discipline as
the XBRL lane stamping `source_filing` on every fact.

### 2.3 The firewall mirror — tables are prose, not figures

The Constitution's §1.2 rule is "numbers come only from XBRL." `elements.py` is
the structural enforcement of its mirror: **this module never imports or
constructs an `XBRLFact`, and never reads a number off a table to answer with.**
A table Element's `text` is structure-preserving HTML — useful for *retrieval*
("show me the contractual-obligations table") and for M2 to summarize — but the
*figures* an answer quotes always come from the XBRL fact store, never from this
parsed HTML. Table parsing is for finding and framing; XBRL is for the number.
Keeping the two construction sites disjoint (different module, different type) is
what makes the firewall a structural fact rather than a coding convention.

### 2.4 What the parser refuses to guess

Two fields are deliberately *not* inferred at parse time:

- **`entity` defaults to consolidated.** JPMorgan Chase & Co. (the registrant)
  and JPMorgan Chase Bank, N.A. (the subsidiary) appear in the same document
  (§1.3). The XBRL lane can tell them apart because the filer *tags* the
  subsidiary with a `dei:LegalEntityAxis` member — a machine-readable signal.
  Prose has no such signal, and guessing "this paragraph is about the bank
  subsidiary" from wording would be exactly the kind of inference §1.3 forbids.
  So every Element is consolidated; subsidiary scoping lives only where it can be
  read, not guessed.
- **`item` is left `"unknown"`.** Which 10-K Item a page belongs to (Item 1A Risk
  Factors, Item 7 MD&A, Item 8 Financial Statements…) is a *sequential-scan*
  problem: you find the "Item 7" heading and everything until "Item 7A" inherits
  it. That is T7's job. T6 stamps `"unknown"` rather than half-guess a boundary.

### 2.5 Body vs furniture

Docling sorts content into *layers*; `iterate_items()` yields only the **BODY**
layer by default. Running headers and footers (the "JPMorgan Chase & Co. / 2024
Form 10-K" banner repeated on all 345 pages) are **furniture**, excluded
automatically — which matters, because otherwise that banner would become ~345
near-duplicate Elements that flood retrieval with noise. We *also* drop the
`PAGE_HEADER`/`PAGE_FOOTER` labels defensively, so a banner that leaks into the
body layer still never becomes an Element.

### 2.6 The memory-engineering story (the part that dominated T6)

This task's real difficulty was not parsing logic — it was making a heavy ML
pipeline run on a memory-constrained host without sacrificing the output. It is
worth recording in full, because it is a recurring shape (Arelle/Docling both
lean on big caches and models) and because the fix changed the code.

**The symptom.** Parsing the full 345-page filing in one `convert()` call died
with a native `std::bad_alloc` (C++ heap exhaustion) in Docling's *preprocess*
stage — the page-rasterization step — cascading across pages and finally a hard
**segmentation fault**. The host has 16.8 GB total but only ~5–6 GB free (other
processes hold the rest), and Docling runs on **CPU** here (no CUDA GPU; the
installed torch is the `+cpu` build).

**What the evidence showed.** The number of pages that survived before the OOM
*tracked free RAM* (~25 pages at 6.7 GB free; ~4 at 4.8 GB) — the signature of a
memory ceiling, not a logic bug. A bounded 12-page parse always succeeded and
produced correct Elements, so `parse_elements` itself was never at fault.

**Three fixes, escalating:**

1. **One page in flight per stage** (`page_batch_size`/`layout_batch_size`/
   `table_batch_size` = 1). Necessary but *insufficient* alone — the crossover
   barely moved, because the accumulation isn't about how many pages infer at
   once.
2. **Lighter models** — the `docling_layout_v2` region model instead of the large
   default `heron`, and TableFormer **FAST** instead of **ACCURATE**. This freed
   enough resident RAM to push the crash from ~page 26 to ~page 150 — proof the
   models' baseline footprint was a big part of the squeeze — but the full doc
   still died, because…
3. **Page windowing** (the decisive fix). Docling holds per-page backend state
   for *every* page within a single `convert()` call, so a 345-page document
   accumulates until the heap is gone. The fix: convert the PDF in **16-page
   windows**, releasing each window's document before the next. A direct
   measurement confirmed memory then stays *flat* across windows (~1.0–1.2 GB
   resident, steady), so the parse completes regardless of document length or
   host RAM. Because `page_range` reports **absolute** page numbers, the windowed
   output is byte-for-byte the same as a single-shot parse would have been — the
   windows are an invisible memory optimization, not a change to provenance or
   ordering.

**The trade made knowingly.** Choices (2) cost a little detection accuracy
(`v2` is a smaller region model than `heron`; FAST is a smaller table model than
ACCURATE). On a clean, digital-native 10-K layout that is an acceptable trade for
a parse that *finishes* — and it is reversible: on a higher-RAM or GPU host, the
heavier models can be restored by changing only `_get_converter`. (Recorded as a
watch-item for M2/eval in §6.)

## 3. The high-level view (architecture)

T6 lands the first real producer in the **`ingestion`** layer on the PDF side. In
the layer map (architecture §3, imports flow downward only) `ingestion` sits
above `config` and below everything else; `elements.py` imports *down* into
`config.schema` (the `Element` contract) and *out* to its parsing libraries
(`docling`, `docling_core`, `pypdfium2`) — no upward imports.

```
   config.settings (FILINGS, pdf_path)
            │  pdf_path(filing)
            ▼
   ingestion.elements.parse_elements(pdf, *, fiscal_year, source_filing)
            │
            │  _page_count(pdf)  ── pypdfium2 ──▶ 345
            │
            ▼   for each 16-page window:
   DocumentConverter.convert(pdf, page_range=(s,e)).document   (lighter models, batch=1)
            │
            ▼   document.iterate_items()  (BODY layer, reading order)
   _classify → kind | None        _page_of → absolute page
            │                              │
            ▼                              ▼
   Element(element_id, kind, text, fiscal_year, item="unknown",
           page, entity=JPMC_CONSOLIDATED, source_filing, ordinal)
            │   (release window, gc.collect, next window)
            ▼
   list[Element]  ──▶ consumed by chunking (M2)
```

- **Consumes:** the PDF path (via `config.settings.pdf_path`) and Docling's parse.
- **Produces:** the **`Element`** §5 contract — and *only* that; it constructs no
  `XBRLFact`.
- **Dependency note:** `pypdfium2` is used for the page count. It is **not a new
  dependency** — it is already in the locked tree as Docling's own PDF rendering
  engine; T6 simply imports it for a cheap, read-only page count.

## 4. The drill-down (low level) — the two-level Code Walkthrough

### Module level

- **Module:** `ingestion` (the PDF lane). T6 adds `elements.py`, modifies
  `tests/conftest.py`, and adds `tests/unit/test_elements_provenance.py`.
- **Role / data-flow position:** the sole `Element` producer; first box of the
  pipeline on the narrative side; output feeds chunking (M2).
- **Boundary change vs §5 contracts:** introduces the construction site of
  `Element`. No other contract is touched; the firewall (`XBRLFact` only built in
  `ingestion.xbrl`) is preserved — `elements.py` neither imports nor builds an
  `XBRLFact`.

### File level

**`src/ingestion/elements.py`** — the parser (the whole task).

- **Module docstring** — teaches the firewall mirror, the three Docling
  conventions (layout+TableFormer, body-vs-furniture, models-download-once), and
  what the module refuses to decide (entity, item).
- `_HEADING_LABELS`, `_FURNITURE_LABELS` — the label sets that route a `TextItem`
  to `HEADING` or to the drop pile. Data, not branching logic.
- `_PAGE_WINDOW = 16` — the window size, with the memory rationale inline.
- `_get_converter()` (`@lru_cache`) — builds the Docling converter **once** per
  process (models load once; warm cache for T10's offline guarantee). Encodes the
  memory budget: OCR off, table-structure on but **FAST**, layout model **`v2`**,
  per-stage batch = 1, process-wide `page_batch_size = 1`.
- `_classify(item)` — `TableItem` → `TABLE`; a `TextItem` → `HEADING` (title/
  section-header label) or `TEXT`, unless it is furniture; everything else
  (pictures, charts, groups) → `None` (dropped). Matches tables by *type* and
  prose-vs-heading by *label*.
- `_page_of(item)` — the absolute 1-based page from `item.prov[0].page_no`, or
  `None` (→ dropped) if the node has no provenance. A guessed page is worse than
  no Element.
- `_table_text(item, doc)` — serializes a table to structure-preserving **HTML**;
  on failure returns `""` (the caller drops it) so one malformed table never
  sinks the filing.
- `_page_count(pdf_path)` — pypdfium2 page count (no inference), driving the
  windows.
- `_elements_from_document(document, *, fiscal_year, source_filing, ordinal_start)`
  — the per-document iteration, pulled out so every window shares one
  reading-order `ordinal` sequence (keeping `element_id` dense and unique across
  window boundaries). Builds each `Element`; skips furniture / no-page /
  empty-text nodes; returns `(elements, skipped)`.
- `parse_elements(pdf_path, *, fiscal_year, source_filing)` — the public entry
  point and sole `Element` producer. Validates the path, reads the page count,
  then loops 16-page windows: `convert(page_range=…)` → `_elements_from_document`
  → extend → **release the window** (`del` + `gc.collect()`). Fails closed
  (`ValueError`) if *zero* Elements are produced — a silent empty parse is a
  fidelity failure.

**`tests/conftest.py`** — adds the `parsed_elements` session fixture: the FY2024
PDF parsed once via `parse_elements` (the PDF twin of the `xbrl_facts` fixture),
so the multi-minute parse runs a single time for the whole test session.

**`tests/unit/test_elements_provenance.py`** — the acceptance gate:
- `test_every_element_has_provenance` — for every Element: correct `fiscal_year`,
  `page >= 1`, a valid `kind`, `item == "unknown"`, `entity is JPMC_CONSOLIDATED`,
  matching `source_filing`, non-empty `text`, and `element_id ==
  {accession}:{page}:{ordinal}`; plus `element_id` uniqueness across the filing.
- `test_element_count_floor` — `len(parsed_elements) > 3000`, the floor set
  from the measured **5,111** and held well below it to catch a gross
  regression (broken model, half-OOM'd parse) without being brittle to small
  model-version drift.

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| Parser | Docling structured parse | naive text extraction (`pdftotext`) | need labeled regions + table cell structure + reading order, not character soup (§2.1) |
| Layout model | lighter `docling_layout_v2` | default `heron` | `heron`'s resident footprint OOMs this CPU host; `v2` runs in far less RAM, small accuracy cost (§2.6) |
| Table model | TableFormer **FAST** | **ACCURATE** (default) | smaller model, still recovers cell structure; ACCURATE OOMs on the squeeze (§2.6) |
| Whole-doc memory | **16-page windows**, released each | one `convert()` over 345 pages | single-shot accumulates per-page state → `std::bad_alloc` → segfault; windowing caps peak at one window, RSS stays flat (§2.6) |
| Page count | `pypdfium2` (already locked) | a second full convert / hard-code 345 | cheap read, no new dependency, no inference; not hard-coded so it generalizes to all five filings |
| Per-stage batch | all = 1 | Docling defaults (4) | bounds in-flight pages; necessary though not sufficient alone (§2.6) |
| `entity` | always `JPMC_CONSOLIDATED` | infer subsidiary from prose | §1.3 — subsidiary is read from a tagged XBRL axis, never guessed from wording (§2.4) |
| `item` | `"unknown"` | guess the Item at parse time | Item boundaries are T7's sequential-scan job; don't half-guess (§2.4) |
| Table `text` | structure-preserving HTML | flattened text / a parsed number | keeps the grid for M2; numbers come from XBRL, never a parsed table (§2.3) |
| Furniture | drop `PAGE_HEADER`/`FOOTER` | keep them | the repeated banner would become ~345 near-duplicate Elements (§2.5) |
| `element_id` | `{accession}:{page}:{ordinal}`, global ordinal | per-page ordinal / UUID | readable, stable, unique within a filing; the citation handle (§2.2) |
| Empty parse | raise `ValueError` | return `[]` | a silent empty parse is a fidelity failure, not a valid result |
| Test parse scope | FY2024 once (session fixture) | parse all five filings | one representative filing proves the contract; five parses would be needlessly slow |
| `slow` marker | **not** marked | mark `@pytest.mark.slow` | mirrors the T4 corpus-parse precedent; the spec scopes `slow` to T10's end-to-end pipeline. (Noted as a possible follow-up if the per-implement loop needs it.) |

## 6. Open threads & what's next

- **Fidelity trade-off carried forward (watch-item).** To fit this host's memory,
  T6 runs lighter layout/table models than Docling's defaults. On a clean 10-K
  layout this is expected to be fine, but M2 (chunking) and the eval milestone
  should *watch* table-structure quality; if it disappoints, the heavier models
  are a one-line change in `_get_converter` on a higher-RAM/GPU host. No
  `[RATIFY]`/`[VERIFY]` marker is opened, but this is flagged for the next
  engineer.
- **Carried forward (unchanged):** the warm Docling model cache (now populated
  with `layout_v2` + TableFormer FAST) is what T10's "no network fetch" offline
  guarantee will rely on — the same cache discipline as Arelle's taxonomy cache.
- **Discovered nothing** that splits the task — `tasks.md` "Discovered work" stays
  empty.
- **Next:** `T7` — Item/section tagging: a sequential scan over the Element stream
  that fills the `item` field (`unknown` → "Item 7" etc.) by detecting Item
  headings and carrying them forward. T6 deliberately left that field open for it.
  Run `/implement T7`.
