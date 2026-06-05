---
id: 2026-06-04-ingestion-parsing
title: M1 — Ingestion & parsing (Elements + XBRLFacts from the JPM 10-Ks)
status: tasks
module: ingestion
owner: Sunit (sunitsingh.bitsg@gmail.com)
created: 2026-06-04
related-specs: []
---

# Spec: M1 — Ingestion & parsing (Elements + XBRLFacts from the JPM 10-Ks)

## Problem

The corpus — five JPMorgan Chase & Co. 10-K filings (FY2021–FY2025) — sits
in `data/SEC/10-K Filings/yearly/` as opaque PDFs. Nothing downstream can
chunk, index, retrieve, or answer over them until each filing is turned into
normalized, provenance-tagged data. `src/` does not exist yet; this is the
first application code in the project and the bottom of the dependency chain
(`docs/roadmap.md` M1).

Two distinct kinds of information have to come out of each filing, and they
must not be conflated. **Narrative** (prose, headings, tables as laid out on
the page) is what a reader sees; **numbers** are what the registrant filed
machine-readably as XBRL. The project's keystone fidelity rule is that
financial figures come from XBRL, never from a number an LLM or a parser read
off a rendered table (Constitution §1.2). So ingestion produces *two* streams
from *two* sources: parsed **Elements** from the PDF, and **XBRLFacts**
extracted from each filing's XBRL package. Those packages are already in hand —
the complete inline-XBRL (iXBRL) filings were downloaded from EDGAR and are
vendored into the repo under `data/SEC/10-K Filings/xbrl/<accession>/` (Git
LFS), so ingestion reads them locally rather than fetching at run time.

If this layer loses provenance (which fiscal year, which 10-K Item, which
page), mislabels entity (JPMorgan Chase & Co. consolidated vs JPMorgan Chase
Bank, N.A.), mixes period types (instant vs duration), or silently collapses
restated figures, every downstream fidelity guarantee is already broken before
retrieval is even written.

## Users & Use Cases

The direct consumers are downstream modules and the pipeline engineer, not an
end analyst yet:

- **Chunking (M2)** consumes the **Element** stream — it needs faithful text,
  table structure, and per-Element provenance (FY / Item / page) to build
  parent/child chunks and table-to-text summaries.
- **Index → DuckDB (M3)** and the **calc tool (M5)** consume the **XBRLFact**
  stream — they need each figure tagged with entity, concept, period type, and
  source filing to support exact, deterministic numeric lookup.
- **The pipeline engineer** runs ingestion to (re)build these streams
  deterministically from source and confirm a known figure parses correctly.
- **Eval (M7)** will later seed XBRL-derived numeric ground truth from the same
  facts; M1's anchor figures are the first seed of that truth set.

The moment of pain this removes: today a question like *"JPMorgan Chase & Co.'s
FY2024 total assets"* has no grounded source in the system at all. After M1 the
figure exists as a typed, entity- and period-scoped, source-tagged fact.

## Behavior

Once built, M1 produces two normalized streams from the five filings, plus the
shared schema and a minimal settings skeleton in `config/`.

**Element stream (from the PDFs).**
- Each filing parses into a sequence of **Elements**, each an atomic parsed
  unit with an element kind (text / table / heading).
- Every Element carries provenance: **fiscal year**, **10-K Item/section**
  (Item 1, 1A, 7, 7A, 8, …), and **page**.
- Where determinable, an Element is scoped to an **entity** (default: the
  consolidated registrant, JPMorgan Chase & Co.); subsidiary-scoped content is
  not silently labelled as the registrant.
- Table Elements preserve enough structure for M2 to summarize them faithfully;
  M1 does not itself produce table-to-text summaries.

**XBRLFact stream (from the vendored XBRL packages).**
- XBRL facts are extracted from each filing's inline-XBRL (iXBRL) package — the
  `.htm` instance plus its linkbases (`.xsd` schema, `_cal`/`_def`/`_lab`/`_pre`
  XML) — vendored under `data/SEC/10-K Filings/xbrl/<accession>/`. All five
  filings (FY2021–FY2025) are present; see the accession↔FY map below.
- Each **XBRLFact** carries: **entity**, **concept** (e.g. a us-gaap tag),
  **period** distinguishing **instant** vs **duration** (with the date/range),
  **value**, **unit**, and a **source-filing** tag (which 10-K it came from).
- **All facts from every filing are retained**, including each filing's
  restated prior-year comparatives. The FY2022 figure as first filed in the
  2022 10-K and as restated in the 2024 10-K are both present and distinguishable
  by source filing.
- **Numbers originate only from XBRL.** The PDF/table parser never writes a
  figure into the fact stream (Constitution §1.2).

**Source corpus (inputs, vendored).** Each filing's accession folder is the
source-filing boundary used for the source-filing tag and restatement rule:

| Accession (folder) | Fiscal year | iXBRL instance |
|---|---|---|
| `0000019617-22-000272` | FY2021 | `jpm-20211231.htm` |
| `0000019617-23-000231` | FY2022 | `jpm-20221231.htm` |
| `0000019617-24-000225` | FY2023 | `jpm-20231231.htm` |
| `0000019617-25-000270` | FY2024 | `jpm-20241231.htm` |
| `0001628280-26-008131` | FY2025 | `jpm-20251231.htm` |

(Exhibits, chart images, and the `.zip` duplicates were deliberately not
vendored — only the iXBRL instance + linkbases + schema per filing.)

**Fidelity constraints (contractual).**
- **Entity is explicit** on every fact and, where determinable, every Element;
  consolidated JPMorgan Chase & Co. is never conflated with JPMorgan Chase Bank,
  N.A. (Constitution §1.3, architecture §10.1).
- **Period type is preserved** end to end; instant and duration figures are
  never blended (architecture §10.2).
- **Restatement source-of-truth rule (ratified):** for a given fiscal year N,
  the **original filing for FY N** is the source of truth; later restatements
  are captured but are not the default. M1's job is only to *preserve* the
  source-tagged data so this rule can be applied downstream — M1 does not
  resolve it at this layer. (Resolves the Constitution §1.3 [RATIFY] item; lead-
  ratified 2026-06-04. Promotion of the marker into `docs/constitution.md` §1.3
  and `docs/architecture.md` §9 happens in the same change that lands M1.)

**Operational constraints.**
- The ingest is **deterministic and rebuildable** from **committed source** —
  the PDFs and the vendored XBRL packages, both under `data/SEC/` via Git LFS.
  A fresh clone (with `git lfs`) has everything ingestion needs; no run-time
  EDGAR fetch is required. Any *derived* output (parsed Elements, extracted
  facts, the serialized form) is reproducible and lives under a **gitignored**
  path (Constitution §1.8, architecture §4.1).
- *Architecture refinement:* architecture §7 currently says XBRL is "pulled
  from EDGAR … into a gitignored derived path." Vendoring the source packages
  supersedes that; promote the §7 wording (and the §2 stack note) in the same
  change that lands M1 (architecture §6.7).
- `src/config/` holds the shared **Element** and **XBRLFact** schema (the cross-
  layer contracts, architecture §5) and a minimal **settings** object (corpus
  paths, EDGAR configuration) and logging skeleton. Other modules import these
  types from `config/`, not from `ingestion/` (architecture §3).

## Out of Scope

- **Chunking** — parent/child splitting, table-to-text summaries, metadata
  stamping (M2).
- **Building the query-time stores** — no Qdrant collection, no DuckDB
  database, no embeddings (M3). M1 produces the normalized Element/XBRLFact
  objects (and a rebuildable serialized form), not the stores that are built
  from them.
- **Retrieval, the agent graph, tools, validator, API, UI, cloud** (M4–M6,
  M9–M10).
- **Applying the restatement rule at answer time.** M1 preserves the
  source-tagged data; choosing the right figure for a question is a downstream
  concern. The rule is *ratified* here, not *implemented* here.
- **A full golden set.** M1 seeds anchor numeric truth (Total assets, Net
  income per FY) for the cheap test; the golden set proper is M7.

## Open Questions

- **PDF parser choice (Docling vs Unstructured).** Decided in PLAN, judged
  against real 10-K table and section fidelity (architecture §9). *Owner:
  contributor in PLAN.* — tech, deferred.
- **EDGAR XBRL pull mechanism: largely RESOLVED.** The full iXBRL instance
  documents are vendored locally (the richer of the two options — preserves
  per-filing provenance for the source-filing tag), so M1 reads from disk and
  needs no live EDGAR fetch, User-Agent, or rate-limit handling. Remaining,
  smaller: whether to keep a *refresh* path that re-pulls from EDGAR (and how to
  verify the vendored copies against EDGAR). *Owner: contributor in PLAN —
  optional, low priority.*
- **Anchor concept-tag stability across taxonomy versions.** The exact us-gaap
  tags for Total assets and Net income may shift across the 2021→2025 taxonomy
  versions; confirm the chosen tags resolve for all five FYs. *Owner:
  contributor, verified during PLAN/IMPLEMENT against the data.*
- **Exact Element/XBRLFact field lists and the serialized intermediate format.**
  Shape is ratified in PLAN (architecture §5 says field lists are owned by the
  module's spec/plan). *Owner: contributor in PLAN.*
- **§1.3 restatement [RATIFY]: RESOLVED** (lead, 2026-06-04) → original filing
  for FY N. No longer blocking; recorded here for the doc-promotion in IMPLEMENT.

## Acceptance Criteria

- [ ] All five filings (FY2021–FY2025) parse to **Elements**; every Element
  carries (fiscal year, 10-K Item/section, page) provenance and an element kind
  (text / table / heading).
- [ ] **XBRLFacts** are extracted from all five vendored iXBRL packages; every
  fact carries entity, concept, period (instant vs duration + date/range),
  value, unit, and a source-filing tag.
- [ ] Facts from all five filings are retained including restated prior-year
  comparatives; the FY2022 figure as filed in 2022 and as restated in 2024 are
  both present and distinguishable by source filing.
- [ ] A **deterministic cheap test** asserts that **Total assets** and **Net
  income** for each FY, as loaded into XBRLFacts, **exactly match** the filed
  XBRL values.
- [ ] Numbers in the XBRLFact stream originate **only from XBRL** — verifiable
  by construction: the PDF/table parser does not write into the fact stream
  (§1.2).
- [ ] **Entity is explicit** on every fact; consolidated JPMorgan Chase & Co.
  facts are not conflated with JPMorgan Chase Bank, N.A. (§1.3).
- [ ] The ingest **rebuilds from committed source** (PDFs + vendored XBRL
  packages under `data/SEC/`, via Git LFS) with no run-time EDGAR fetch, and
  writes derived artifacts to a **gitignored** path (§1.8, architecture §4.1).
- [ ] `src/config/` holds the shared **Element** and **XBRLFact** schema and a
  minimal **settings** object (paths, EDGAR config) + logging skeleton; no other
  module imports `ingestion/` for these types.
