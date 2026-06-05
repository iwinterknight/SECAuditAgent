---
spec: 2026-06-04-ingestion-parsing
stage: clarify
report: 01-clarify
created: 2026-06-04
---

# Educator Report — CLARIFY · M1 Ingestion & Parsing

> **How to read this.** This is the first report of the project's Reporting
> Protocol (Constitution §2), produced at the end of the CLARIFY step for the
> M1 spec. It starts at the architecture / domain level and drills down to the
> spec we just wrote. It deliberately *teaches the domain* — XBRL, EDGAR,
> iXBRL, the DuckDB-vs-Qdrant split — because those concepts are the
> foundation the entire system stands on, and M1 is where they first touch
> code. Markdown is the source of truth; the sibling `01-clarify.pdf` is
> rendered from it.

---

## 1. Where we are (orientation)

**The CLARIFY step for M1 — Ingestion & parsing — just finished.** We wrote
`specs/2026-06-04-ingestion-parsing/spec.md`: a behavior contract (no code
yet) for turning the five JPMorgan Chase & Co. 10-K filings (FY2021–FY2025)
into two normalized, provenance-tagged data streams.

To see *why this step matters*, place it on two maps.

**The roadmap (`docs/roadmap.md`, M0–M10).** The project is built bottom-up,
because each layer depends on the one beneath it — you cannot retrieve before
you index, you cannot index before you chunk, you cannot chunk before you
ingest. So:

- **M0 — Scaffolding (done).** The non-code foundation: the constitution
  (the law), the architecture (the target-state map), the roadmap (this
  tracker), the SDD machinery (`.agent/` commands, the `sdd-feature-cycle`
  skill), the corpus (the PDFs + XBRL under `data/SEC/`), and the `.gitignore`
  / Git-LFS plumbing. M0 produced *no* `src/` code on purpose — it set the
  rules of the game.
- **M1 — Ingestion & parsing (this spec, now in CLARIFY).** The **bottom of
  the dependency chain** and the first application code in the project. It
  reads the raw corpus and emits the normalized objects everything else
  consumes. If M1 loses fidelity, every downstream guarantee is already
  broken before retrieval is even written.

**The data flow (`docs/architecture.md` §4).** The answer engine is a
pipeline:

```
ingest → chunk → index → retrieve → agent (router → tools → validator) → cited answer
  ▲
  └─ M1 is HERE — the source of both the narrative stream and the numeric stream
```

M1 is the headwaters. Two rivers start here, and the project's keystone rule
is that they must never be allowed to mix in the wrong way (more on that
below).

---

## 2. The domain in play (teach me)

This is the teaching core. Everything M1 does is shaped by four ideas: what a
10-K is, what XBRL is, where the data comes from (EDGAR), and why we keep
numbers in a different kind of store than prose (DuckDB vs Qdrant).

### 2.1 The 10-K and the two kinds of information inside it

A **10-K** is the annual report a public company files with the SEC. It is a
large document — JPMorgan's runs to hundreds of pages — organized into
standard **Items** (Item 1 Business, Item 1A Risk Factors, Item 7 MD&A,
Item 7A Market Risk, Item 8 Financial Statements, …).

A 10-K carries **two distinct kinds of information**, and conflating them is
the cardinal sin this project is built to avoid:

1. **Narrative** — the prose, headings, and tables *as laid out on the page*.
   This is what a human reads. It is qualitative, contextual, and lives in the
   PDF.
2. **Numbers** — the precise financial figures the company filed
   *machine-readably* as **XBRL**. These are quantitative, exact, and live in
   a separate structured feed.

The reason this matters: if you ask an LLM "what were JPMorgan's total assets
in FY2024?" and it reads the number off a rendered table, it can transpose a
digit, shift a decimal, or grab the wrong column — and it will say it with
total confidence. That is a **hallucination vector**. The whole architecture
exists to remove the LLM from the number-reading loop.

### 2.2 XBRL — what it is and how we use it

**XBRL = eXtensible Business Reporting Language.** It is a standardized,
machine-readable format for financial facts. Where a PDF table *shows* you
"Total assets ... 4,002,814", XBRL *states* it as a structured fact with five
parts:

| Part | Meaning | Example |
|---|---|---|
| **Concept** | *what* the number is — a tag from a taxonomy | `us-gaap:Assets` |
| **Entity** | *whose* number it is — identified by CIK | JPMorgan Chase & Co. (CIK 0000019617) |
| **Period** | *when* — and of what kind (see below) | instant, 2024-12-31 |
| **Unit** | the unit of measure | USD |
| **Value** | the figure itself | 4002814000000 |

- The **taxonomy** is the controlled vocabulary of concepts. **`us-gaap`** is
  the US GAAP financial taxonomy the SEC mandates; a tag like
  `us-gaap:NetIncomeLoss` means the same thing across every filer, which is
  exactly what makes the data comparable and queryable.
- The **period type** is the single most important fidelity distinction in
  the whole dataset:
  - **instant** — a balance-sheet figure, true "as of" one date (e.g. Total
    assets *as of* 2024-12-31). It is a snapshot.
  - **duration** — a flow figure, accumulated "for the year" (e.g. Net income
    *for* 2024-01-01 → 2024-12-31). It is a span.
  Blending an instant with a duration — or quoting a balance as if it were a
  flow — is a category error that produces nonsense. M1 preserves this
  distinction end-to-end.

**How we use it:** the XBRL feed is the project's **numeric ground truth**.
The deterministic calc path reads figures *only* from XBRL (via DuckDB, §2.4),
never from a number an LLM read off a parsed table. This is Constitution
§1.2, and it is enforced structurally: in M1, the PDF parser is *physically
not allowed* to write into the fact stream. The two rivers never cross.

### 2.3 iXBRL, linkbases, and what we actually vendored

Modern filings use **inline XBRL (iXBRL)**: instead of a separate data file,
the XBRL facts are *embedded inside* the human-readable `.htm` 10-K document,
wrapped in invisible tags. So one file is simultaneously the web page a person
reads and the structured data a machine extracts.

An iXBRL filing is not one file but a small **package**:

- **`jpm-YYYYMMDD.htm`** — the iXBRL **instance**: the document with the facts
  tagged inline.
- **`.xsd`** — the **schema**: defines the filer's custom concepts.
- The **linkbases**, four XML files that give the bare concepts meaning and
  structure:
  - **`_lab`** (label) — human-readable names for concepts.
  - **`_pre`** (presentation) — how concepts are ordered for display.
  - **`_cal`** (calculation) — arithmetic relationships (subtotals roll up).
  - **`_def`** (definition) — dimensional relationships.

**What we did:** we downloaded the complete iXBRL packages for all five
filings from EDGAR and **vendored** them into the repo under
`data/SEC/10-K Filings/xbrl/<accession>/` (via Git LFS — see §2.3 of the
spec's source table). We kept the instance + schema + four linkbases per
filing (6 files × 5 = 30) and deliberately dropped the exhibits, chart
images, and `.zip` duplicates. The payoff: a fresh `git clone` (with
`git lfs`) has *everything ingestion needs on disk* — M1 reads locally and
needs no live network call at run time. (This is why one of the spec's Open
Questions — "the EDGAR pull mechanism" — is now largely **resolved**.)

### 2.4 EDGAR and its "pull" mechanism

**EDGAR** (Electronic Data Gathering, Analysis, and Retrieval) is the SEC's
public filing system — every 10-K, 10-Q, 8-K, etc. lands there and is free to
the public. Each company has a **CIK** (Central Index Key); JPMorgan's is
**0000019617**. Each individual submission has an **accession number** (e.g.
`0000019617-24-000225`), which is the unique address of one filing and the
natural **source-filing boundary** we tag every fact with.

The **pull mechanism** is just *how you fetch from EDGAR*. There are two
flavors, and the distinction drove a real design choice:

1. **The structured Company Facts API** — a single JSON endpoint
   (`data.sec.gov/api/xbrl/companyfacts/CIK0000019617.json`) that returns
   *EDGAR's already-merged view* of a company's facts across all filings.
   Convenient, but it collapses provenance: you lose which specific filing a
   given figure came from.
2. **The per-filing instance documents** — the raw iXBRL package for each
   accession. Richer, because each filing's facts (including its own restated
   prior-year comparatives) stay separated by source.

We chose **(2)**, because the project's fidelity rules *require* per-filing
provenance: we keep "the FY2022 figure as first filed in 2022" and "the
FY2022 figure as restated in the 2024 10-K" as **distinct, source-tagged
facts**. The merged API can't express that. (Etiquette note for any future
*refresh* path: EDGAR asks automated clients to send a descriptive
`User-Agent` and to rate-limit to ~10 requests/sec. We don't need it now
because the packages are vendored, but it's recorded for the optional refresh
tool.)

### 2.5 Why DuckDB for numbers, Qdrant for prose

The system uses **two** stores, on purpose, because the two rivers from §2.1
need different machinery:

| | **Qdrant** | **DuckDB** |
|---|---|---|
| Kind | Vector database | Embedded OLAP SQL engine |
| Holds | Narrative chunks as embeddings | XBRL facts as typed rows |
| Answers | "find me text *similar in meaning* to this question" (semantic search) | "give me the *exact* value where concept=Assets, entity=Co., FY=2024" |
| Strength | Fuzzy, meaning-based recall over prose | Exact, deterministic, auditable numeric lookup + arithmetic |

**Why not put the numbers in Qdrant too?** Because vector search is
*approximate by design* — it returns what's *near* in meaning, not what's
*exactly equal*. For "total assets in FY2024" you do not want the nearest
neighbour; you want the one true filed figure, every time, with no chance of
a near-miss. Financial figures are a **relational/keyed** problem (exact
match on entity + concept + period), which is precisely what a SQL store like
DuckDB is built for. DuckDB is embedded (no server to run), columnar (fast
aggregate math), and reads the facts deterministically. Put another way:
Qdrant is for *recall*, DuckDB is for *truth*. M1 produces the **XBRLFact**
objects that M3 will load into DuckDB.

---

## 3. The high-level view (architecture)

**Layer.** M1 is the `ingestion/` layer — the bottom of the `src/` stack
(`docs/architecture.md` §3). Imports flow downward only, so `ingestion/`
imports from `config/` (shared types + settings) and nothing above it.

**What M1 produces — two streams + the shared schema:**

```
                                   ┌─────────── Element stream ──────────►  (to M2 chunking)
   PDFs  ──► [ PDF parser ] ───────┘   text / table / heading + provenance
                                         (FY, Item/section, page, entity)

   iXBRL ──► [ XBRL extractor ] ───┐
   packages                        └─────────── XBRLFact stream ─────────►  (to M3 index → DuckDB,
                                       entity, concept, period(instant/        and M5 calc tool)
                                       duration), value, unit, source-filing
```

**The two typed contracts (`docs/architecture.md` §5) M1 owns and emits:**

- **Element** — one atomic parsed unit of *narrative*: a kind (text / table /
  heading) plus provenance (fiscal year, 10-K Item/section, page) and, where
  determinable, an entity. M2 chunking consumes these.
- **XBRLFact** — one atomic *number*: entity, concept, period (instant vs
  duration + the date/range), value, unit, and a source-filing tag. M3 and
  the M5 calc tool consume these.

These types live in `src/config/`, not in `ingestion/`, so that *every*
downstream module imports the contract from the shared layer rather than
reaching up into ingestion. M1 also lands the minimal `config/` skeleton
(settings: corpus paths, EDGAR config; plus a logging skeleton) that the rest
of the project has been waiting on.

**The structural firewall.** The PDF parser writes Elements; the XBRL
extractor writes XBRLFacts; *the parser never writes a number into the fact
stream.* That separation is not a convention you have to remember — it's the
physical embodiment of Constitution §1.2, and it's verifiable by
construction.

---

## 4. The drill-down (the spec we wrote)

CLARIFY's job is a **behavior contract** — *what*, never *how*. Here is what
`spec.md` commits M1 to, and **why each clause earns its place**.

**Element stream (from the PDFs).** Every Element carries (fiscal year, 10-K
Item/section, page) provenance and a kind. *Why:* downstream chunking and
every citation depend on being able to say "this claim came from FY2024,
Item 7, page 84." Provenance lost here cannot be recovered later.

**XBRLFact stream (from the vendored packages).** Every fact carries entity,
concept, period (instant vs duration + dates), value, unit, and source-filing
tag. **All facts from every filing are retained, including each filing's
restated prior-year comparatives.** *Why:* this is what lets the system later
distinguish "FY2022 as originally filed" from "FY2022 as restated in 2024" —
a distinction that is meaningless if you only keep one.

**The acceptance criteria** (the checklist a reviewer verifies) and the WHY
behind the load-bearing ones:

| AC (paraphrased) | Why it matters / what failure it prevents |
|---|---|
| All five filings parse to Elements with FY/Item/page provenance | No provenance → no citations → §1.5 breaks |
| XBRLFacts extracted from all five packages with entity/concept/period/value/unit/source | The numeric ground-truth contract; missing any field breaks an exact lookup |
| Restated comparatives retained + distinguishable by source filing | Enables the restatement source-of-truth rule downstream |
| **Deterministic cheap test:** Total assets & Net income per FY **exactly** match the filed XBRL | The §4.3 per-implement guard — proves fidelity by exact match, not "close enough" |
| Numbers originate **only** from XBRL (parser can't write facts) | Structural enforcement of §1.2 — the anti-hallucination firewall |
| Entity explicit on every fact (Co. ≠ Bank, N.A.) | Prevents the §1.3 entity-confusion fidelity bug |
| Rebuilds from committed source (LFS), no run-time EDGAR fetch; derived artifacts gitignored | §1.8 — reproducible, corpus read-only at runtime |

Note the test anchors are **Total assets** and **Net income** — chosen
because they are *clean `us-gaap` primitives* (likely `us-gaap:Assets` and
`us-gaap:NetIncomeLoss`, to be confirmed against the taxonomy in PLAN), every
filer reports them, and they exercise *both* period types (Assets is instant;
Net income is duration). One anchor of each kind is a tight, decisive
fidelity probe.

**Deliberately out of scope** (so the reader doesn't assume otherwise):
chunking and table-to-text (M2); building the actual Qdrant/DuckDB stores
(M3); *applying* the restatement rule at answer time (M1 only *preserves* the
source-tagged data); and the full golden eval set (M7). M1 seeds only the
anchor numeric truth.

---

## 5. Decisions & trade-offs

The forks CLARIFY settled or surfaced, and why:

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| XBRL source | Per-filing iXBRL packages, vendored | EDGAR merged Company-Facts API | Per-filing preserves source provenance for the restatement rule; the merged view collapses it |
| Fetch timing | Read vendored packages from disk | Live EDGAR pull at run time | Deterministic, offline, reproducible from a clone (§1.8) |
| XBRL scope | Keep **all** facts, tagged by source filing | Keep only each FY's "final" figure | Retaining restatements is required to distinguish original vs restated later |
| Restatement source-of-truth | **Original** filing for FY N (lead-ratified 2026-06-04) | Latest restatement as default | The as-originally-reported figure is the stable citation; restatements are captured but not default |
| Provenance granularity | FY + **Item-level section** + page | FY + page only | Item-level scoping is what lets retrieval and citations target the right part of a 300-page filing |
| Numeric store (downstream) | DuckDB for facts | Qdrant for everything | Exact keyed lookup needs SQL truth, not approximate vector recall |
| Test anchors | Total assets + Net income, exact match | Derived ratios (e.g. CET1) | Clean `us-gaap` primitives; one instant + one duration; unambiguous ground truth |

---

## 6. Open threads & what's next

**Carried into PLAN (deferred, by design — CLARIFY forbids tech choices):**

- **PDF parser choice — Docling vs Unstructured.** Judged in PLAN against
  real 10-K table/section fidelity. This is the biggest open technical fork.
- **Exact `us-gaap` tag stability across the 2021→2025 taxonomy versions.**
  Confirm the chosen Total-assets / Net-income tags resolve for all five FYs.
- **Exact Element / XBRLFact field lists + the serialized intermediate
  format.** Shape ratified in PLAN (architecture §5 says the module's
  spec/plan owns the field lists).
- **Optional EDGAR *refresh* path** — whether to keep a way to re-pull and
  verify the vendored copies. Low priority; vendoring removed the urgency.

**Resolved during CLARIFY:** the §1.3 restatement `[RATIFY]` marker (→
original filing for FY N, lead-ratified 2026-06-04). When M1 lands, that
resolution is promoted into `docs/constitution.md` §1.3 and the architecture
§7/§9 wording is updated to say "vendored" rather than "pulled from EDGAR."

**Next SDD step:** `/plan`. PLAN will read this confirmed spec + the
constitution + the architecture + (once it exists) the code, choose the
parser, fix the contract field lists, and design the deterministic ingest —
then auto-dispatch the `spec-reviewer`. It will produce its own Educator
Report, `02-plan.md`.
