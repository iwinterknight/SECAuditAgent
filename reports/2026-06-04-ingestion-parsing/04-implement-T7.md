---
spec: 2026-06-04-ingestion-parsing
stage: implement
report: 04-implement-T7
created: 2026-06-08
---

# Educator Report — IMPLEMENT · M1 Ingestion & parsing (T7 · Item-boundary stamping — `sections`)

> **How to read this.** Top-down: first *where* this task sits, then the *domain*
> it encodes (the 10-K Item/Part structure, why Item assignment is a separate
> deterministic pass, forward-fill semantics, and the "fail to `unknown`, never to
> a stale label" rule), then a deliberate *process* decision (why the real-corpus
> test moved to T10 instead of re-parsing here), then the *architecture* view and
> the mandatory two-level **Code Walkthrough**. By the end you should be able to
> re-present every line of `sections.py` and defend why a garbled Item heading
> must blank the section rather than inherit its neighbour.

---

## 1. Where we are (orientation)

We just finished **T7** of **M1 (Ingestion & parsing)**. T6 produced the Element
stream but deliberately left every Element's `item` field set to `"unknown"` —
the parser knows *layout* (heading vs prose vs table) but not *document section*.
**T7 fills that field.** `ingestion.sections.assign_items` is a pure, deterministic
post-parse pass that walks the Elements in reading order, finds the "Item N"
headings, and stamps each Element with the 10-K Item it falls under. On the
data-flow diagram (`docs/architecture.md` §4: ingest -> chunk -> ...), T7 doesn't
add a box — it *enriches* the Element stream between parse and serialize, so that
a downstream answer can say "per Item 7 (MD&A)" or scope a retrieval to the
financial statements (Item 8). It is the last piece of provenance an Element
needs before it is ready to chunk.

## 2. The domain in play (teach me)

### 2.1 The 10-K Item/Part structure

A 10-K is not free-form prose; the SEC mandates a fixed skeleton of numbered
**Items** grouped under four **Parts**:

- **Part I** — Item 1 Business, **1A Risk Factors**, 1B/1C, 2 Properties, 3 Legal
  Proceedings, 4 Mine Safety.
- **Part II** — Item 5 Market for the Registrant's Stock, 6 (reserved), **7
  Management's Discussion & Analysis (MD&A)**, 7A Quantitative & Qualitative
  Market-Risk Disclosures, **8 Financial Statements**, 9/9A/9B/9C.
- **Part III** — Items 10-14 (governance, compensation). **Part IV** — Item 15
  Exhibits, 16.

The Item is the unit analysts navigate by ("what did risk factors say?" = Item
1A; "what were the numbers?" = Item 8). Capturing it per Element is what makes a
citation locatable and a retrieval scopeable.

### 2.2 Why Item assignment is a *separate, deterministic* pass

It would be tempting to have the PDF parser tag Items, or to ask an LLM "what
section is this?". Both are wrong here:

- **The parser can't.** Docling recovers *visual* structure (this is a heading,
  that's a table); it has no concept of a 10-K's Item numbering.
- **An LLM mustn't.** Section membership is a *structural* fact recoverable
  deterministically from the heading sequence — exactly the kind of thing the
  Constitution keeps away from a model (no guessing where a rule suffices). A
  deterministic pass is reproducible, auditable, and free.

So `assign_items` is a plain function over the Element list: O(n), no I/O, no
model, no figures. It is the narrative-side analogue of the XBRL transform —
mechanical and exact.

### 2.3 Forward-fill, and scanning *headings* not prose

The algorithm is a **forward-fill**: maintain a "current Item," set it when a
recognized Item heading appears, and stamp every subsequent Element with it until
the next Item heading. Two design choices make it robust on a real 10-K:

- **Only headings are boundaries.** We inspect `kind == HEADING` Elements only.
  A paragraph that *mentions* "Item 7" in passing, or the "Form 10-K Index"
  table of contents, cannot move the boundary — because the TOC is a `TABLE`, not
  a `HEADING` (T6 classified it so). Scanning headings, not all text, is what
  keeps the index from hijacking the assignment.
- **Ordinary sub-headings inherit.** A heading like "Overview" under Item 7 is
  *not* an Item boundary, so it leaves the current Item untouched and inherits it.

### 2.4 Fail to `unknown`, never to a stale label (the rule this pass exists for)

The sharp edge (architecture §10, plan Risks): what if a heading clearly *is* an
Item boundary but its number is garbled by layout/OCR? The wrong behavior is to
carry the previous Item forward across it — that would silently file the new
section's content under the *previous* Item, mis-attributing a citation. So the
rule is: a heading that **begins with the word "Item" but whose number won't
parse** resets the current Item to `unknown` (and logs a warning). A boundary we
can see but can't name yields `unknown`, never a confident-but-wrong label. This
is the single behavior the named acceptance test pins.

(The candidate check uses a word boundary, so "Itemized" or "Items" are *not*
treated as Item headings — only the standalone word "Item" followed by a number.)

### 2.5 The process decision: why the corpus test moved to T10 (parse-once)

T7's plan listed two acceptance tests: a pure mini-fixture test (this task) **and**
a real-corpus test (`test_known_elements_land_in_right_item`: a real MD&A Element
must land in Item 7, a real financial-statements Element in Item 8). The corpus
test needs *parsed* Elements — but parsing the FY2024 10-K is a ~24-minute job on
this CPU/low-RAM host, and the lead's standing requirement is that the heavy parse
runs **once** and is reused, never re-run.

The plan's own **test strategy** already says this: corpus tests should *read the
serialized derived JSONL* ("fast, no re-parse"); only the pipeline-rebuild test
re-invokes parsing, and it is slow-marked. But the JSONL is produced by **T10**
(the pipeline), which is ordered *after* T7 — and T10 in turn needs T7's
`assign_items` to produce Item-stamped output. The clean resolution, taken here:

- **T7 ships the logic + the pure test now** (the logic is fully exercised by the
  mini-fixture, in milliseconds, with no corpus).
- **`test_known_elements_land_in_right_item` moves to T10**, where it reads the
  serialized, Item-stamped JSONL the pipeline writes — exactly as the plan's test
  strategy intends, and with the full parse happening exactly once.

This keeps T7 honest (no re-parse, no throwaway 24-minute run that the plan would
have rewritten anyway) and aligns the task order with the documented strategy.

## 3. The high-level view (architecture)

T7 adds a pure transform inside the **`ingestion`** layer. It consumes the
**`Element`** §5 contract and produces the same contract with one field populated
— it neither creates a new type nor touches `XBRLFact` (the §1.2 firewall is
untouched; this pass handles no numbers). Imports flow downward only: `sections`
imports `config.schema` and nothing sideways or up.

```
   ingestion.elements.parse_elements(...) -> list[Element]   (item = "unknown")
                              │
                              ▼
   ingestion.sections.assign_items(elements) -> list[Element]   (item stamped)
       scan HEADINGs in reading order:
         "Item 7. ..."  -> current = "Item 7"     (recognized)
         "Item -- ..."  -> current = "unknown" + warn  (garbled boundary)
         "Overview"     -> current unchanged       (ordinary sub-heading)
       every Element copied with item = current
                              │
                              ▼
   (T10) pipeline: parse -> assign_items -> serialize to data/derived/elements/*.jsonl
                              │
                              ▼
   corpus Item-correctness test reads the JSONL  (no re-parse)
```

- **Consumes / produces:** `Element` in, `Element` out (item-stamped). Pure: the
  input list is not mutated (each Element is `model_copy`-ed).
- **Boundary change:** none to any contract; this is the producer of the `item`
  value that the §5 Element contract always promised.

## 4. The drill-down (low level) — the two-level Code Walkthrough

### Module level

- **Module:** `ingestion` (the narrative lane). T7 adds `sections.py` and
  `tests/unit/test_sections.py`.
- **Role / data-flow position:** a pure enrichment pass between `parse_elements`
  (T6) and serialization (T9/T10); the producer of the Element `item` field.
- **Boundary change vs §5 contracts:** none — it reads and returns `Element`,
  filling the `item` slot. Constructs no `XBRLFact`; handles no numbers.

### File level

**`src/ingestion/sections.py`** — the Item-boundary pass (the whole task).

- **Module docstring** — teaches the Item/Part structure, the three rules
  (forward-fill from headings only; fail to `unknown` not a stale label; no number
  handling), and why the TOC (a table) can't move the boundary.
- `UNKNOWN_ITEM = "unknown"` — the single sentinel, named once (matches the value
  T6 stamped, and the contract's "`unknown` if boundary undetected").
- `_ITEM_CANDIDATE = r"^\s*item\b"` — is this heading *attempting* to be an Item
  boundary? The `\b` keeps "Itemized"/"Items" out. Candidate detection is
  deliberately separate from number parsing so a candidate we can't parse can
  become `unknown` rather than inherit.
- `_ITEM_HEADER = r"^\s*item\s+(\d{1,2}[A-Za-z]?)\b"` — a *recognized* header:
  "Item" + a 1-2 digit number with an optional single-letter suffix (1A, 7A, 9B).
- `_item_label(heading_text)` — returns the canonical label (`"Item 7"`,
  `"Item 1A"`, suffix upper-cased), or `UNKNOWN_ITEM` for a garbled candidate, or
  `None` for a non-Item heading (caller keeps the current Item). The three-way
  return is what encodes "boundary vs garbled-boundary vs not-a-boundary."
- `assign_items(elements)` — the public pass. Forward-fills `current_item` across
  the reading-order stream, logging a warning whenever a garbled boundary resets
  it to `unknown`; returns a new list of `model_copy`-ed Elements (pure — the
  input is untouched). This is the sole producer of the `item` value.

**`tests/unit/test_sections.py`** — pure logic tests over a checked-in fixture (no
corpus, 0.08s):
- `test_missing_header_yields_unknown` (the named acceptance) — content before any
  Item heading is `unknown`; a recognized "Item 1A" header forward-fills (suffix
  preserved); a **garbled** "Item -- ..." heading resets the section to `unknown`
  and its content is `unknown`, asserting explicitly that it is **never** the
  previous Item's label.
- `test_forward_fill_and_subheadings` — recognized Item headers forward-fill
  across an ordinary sub-heading; and `assign_items` leaves its input unmutated
  (purity).

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| Where Items are assigned | a separate deterministic pass over Elements | tag in the PDF parser / ask an LLM | the parser has no Item concept; section membership is deterministic, so no model belongs here (§2.2) |
| Boundary source | **heading** Elements only | scan all text for "Item N" | a prose mention or the TOC table would hijack the boundary; headings + TOC-as-table avoid that (§2.3) |
| Garbled boundary | reset to `unknown` + warn | carry the previous Item forward | mis-attributing a section to its neighbour is the exact bug this pass prevents (§2.4) |
| Candidate detection | `^\s*item\b` (word boundary) | `startswith("item")` | excludes "Itemized"/"Items" from being treated as boundaries (§2.4) |
| Purity | return `model_copy`-ed Elements | mutate the input list in place | a pure pass is reproducible and safe to re-run; the input stays the source of truth |
| Corpus Item test | **move to T10** (reads serialized JSONL) | run it here via a ~24-min re-parse | matches the plan's test strategy + the parse-once requirement; the here-run would be throwaway (§2.5) |
| `item` format | `"Item 7"` / `"Item 1A"` (string) | an enum / `(part, item)` tuple | plan's contract is a string; Parts aren't needed for retrieval scope at M1 |

## 6. Open threads & what's next

- **Relocated, not dropped.** `test_known_elements_land_in_right_item` (real
  corpus: MD&A -> Item 7, financials -> Item 8) now lives in **T10**, reading the
  serialized JSONL the pipeline writes. This is its proper data source and runs
  the full parse exactly once. T7's `Files`/acceptance were updated accordingly.
- **What the corpus test will still catch (and the pure test can't).** Real-data
  hazards — e.g. an "Item 1. Business." heading appearing in a front-matter index
  region as a heading, or Part boundaries — surface only against the real corpus.
  That validation is deferred to T10, by design, not skipped.
- **No new `[RATIFY]`/`[VERIFY]` markers** opened. No `XBRLFact` touched; the §1.2
  firewall is unchanged (T8 will assert this statically — it depends on T4, T6 and
  now T7, so T8 is unblocked).
- **Next:** with T6 + T7 done, the natural path is **T9 (serialize)** then **T10
  (pipeline)** — which persists the bake-ready `data/derived/` corpus the lead
  wants, runs the single slow parse, and lights up the relocated corpus test.
  (T8, the firewall guard, is also now unblocked and is pure/fast.)
