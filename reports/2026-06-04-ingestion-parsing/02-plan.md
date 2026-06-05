---
spec: 2026-06-04-ingestion-parsing
stage: plan
report: 02-plan
created: 2026-06-04
---

# Educator Report — PLAN · M1 Ingestion & parsing (Elements + XBRLFacts)

> **How to read this.** This is the lead's 360° companion to the PLAN step. It
> opens at the architecture/domain altitude — *what we're building and why this
> shape* — and drills down to the design decisions, the rejected alternatives,
> and the tests that will prove it. It teaches the domain (iXBRL transforms,
> Arelle, Docling, XBRL contexts, the structural firewall, the packaging fork)
> from first principles. Read top-to-bottom to go from "why" → "how" → "exactly
> what we'll build." Markdown is the source of truth; the sibling PDF is
> rendered by `reports/render.py`.

---

## 1. Where we are (orientation)

The PLAN step for **M1 — Ingestion & parsing** just finished. CLARIFY produced
the contract (*what* M1 must do); PLAN produces the design (*how* we'll do it)
in [`plan.md`](../../specs/2026-06-04-ingestion-parsing/plan.md). M1 is the
**bottom of the dependency chain** (`docs/roadmap.md`) and the **first
application code in the repo** — there is no `src/` yet. On the data-flow map
(`docs/architecture.md` §4) everything flows left-to-right from here:

```
  ▶ ingestion (M1)  ─►  chunking (M2)  ─►  index (M3)  ─►  retrieval (M4)  ─►  agent (M5)  ─►  answer
    PDF → Elements
    XBRL → XBRLFacts
```

Nothing downstream can chunk, index, retrieve, or answer until M1 turns five
opaque JPMorgan Chase & Co. 10-K PDFs (and their vendored XBRL packages) into
two normalized, provenance-tagged streams. Because it sits at the bottom, **every
fidelity guarantee in the system is either established or lost here.** If M1
mislabels an entity, blends a period type, or lets an LLM-read number into the
numeric stream, no downstream validator can fully repair it. That is why this
PLAN spent most of its design budget on *one* idea — the structural firewall —
and on choosing tools that get XBRL's numeric transforms exactly right.

## 2. The domain in play (teach me)

This step's design engaged a specific slice of the domain deeply. Here is the
fluency you need to defend the plan.

**XBRL, and why it is the numeric source of truth.** XBRL (eXtensible Business
Reporting Language) is the machine-readable form of a financial filing. Where a
PDF table is pixels a human reads, XBRL is a set of **facts**, each a 5-part
tuple: a **concept** (what is being reported, e.g. `us-gaap:Assets`), an
**entity** (who, via a CIK identifier and optional dimensions), a **period**
(when), a **unit** (USD, shares, pure), and a **value**. Because the registrant
*filed* these numbers, reading them mechanically removes the single largest
error source in a RAG system — an LLM transcribing a figure off a parsed table
and shifting a decimal. This is Constitution §1.2, and it is the reason M1 has
two streams instead of one.

**Inline XBRL (iXBRL) and linkbases — what we vendored.** Modern filings ship as
**inline** XBRL: the facts are embedded *inside* the human-readable HTML document
using `ix:` tags (e.g. `<ix:nonFraction>` wrapping a number). One file
(`jpm-20241231.htm`, ~12 MB) is therefore both the rendered 10-K *and* the
machine data. Around it sit the **linkbases** — companion XML files that give the
facts meaning: `.xsd` (the schema defining custom concepts), `_lab` (human
labels), `_pre` (presentation order), `_cal` (calculation relationships, e.g.
"assets = liabilities + equity"), and `_def` (dimensional definitions). We
**vendored** the instance + all linkbases per filing under
`data/SEC/10-K Filings/xbrl/<accession>/` (Git LFS), so ingestion reads ground
truth from disk — no live network fetch.

**The iXBRL transform — the landmine this plan is built around.** An
`ix:nonFraction` value is *not* the number you see. It carries a **`scale`**
attribute (`scale="6"` means the displayed value is in millions — multiply by
10⁶), a **`sign`** attribute (`sign="-"` flips it), and a **format** transform
(e.g. `ixt:num-dot-decimal` says how to parse the digits). Get any of these
wrong and *every* figure is silently corrupt — off by a factor of a million, or
positive where it should be negative. This single hazard is why the plan chose
Arelle (below): hand-rolling these transforms is exactly the error surface §1.2
exists to eliminate.

**XBRL contexts — where entity and period come from.** Each fact points (via
`contextRef`) at a **context** that pins down *who* and *when*. The context's
`entity/identifier` is the CIK (`0000019617` = JPMorgan Chase & Co.); its
`segment`/dimensions can re-scope a fact to a subsidiary or business unit via a
**legal-entity dimension member**. The context's period is either an **instant**
("as of 2024-12-31" — balance-sheet figures like Total assets) or a **duration**
("for 2024-01-01…2024-12-31" — flow figures like Net income). **Entity** and
**period type** are first-class fidelity fields (Constitution §1.3, architecture
§10) precisely because the same filing reports JPMorgan Chase & Co. *and*
JPMorgan Chase Bank, N.A. with different numbers, and mixes instant and duration
figures on the same page. The plan reads both straight from the context — never
from prose.

**Accession numbers and restatements.** An **accession number**
(`0000019617-25-000270`) is EDGAR's unique id for one filing submission; we use
the accession folder as the **source-filing boundary**. This matters because each
10-K **restates** 2–3 prior years: the FY2022 Net income as *originally filed* in
the 2022 10-K can differ from the FY2022 figure as *restated* in the 2024 10-K.
The plan keeps **both** — parsing each instance independently and tagging every
fact with its source accession — so nothing is lost and the
ratified rule ("original filing for FY N is the default truth") can be applied
*downstream*, not guessed here.

**Frameworks this step leaned on, and what each buys us:**

- **Arelle** (`arelle-release`) — the SEC's de-facto reference XBRL processor. It
  implements the full iXBRL transform registry, context/unit resolution, and the
  dimensional model. We lean on it so the scale/sign/transform landmine is
  handled by battle-tested code, not by us.
- **Docling** (IBM) — parses PDFs into a structured document model with reading
  order, page numbers, and **table cell structure**. It buys us faithful table
  *structure* for M2's table-to-text summaries; its cost is a one-time model
  download.
- **Pydantic v2** + **pydantic-settings** — typed, *validated* contracts and a
  single settings object. Validation at the boundary (entity always set, period
  type one of two values, value is a `Decimal`) turns fidelity rules into
  runtime guarantees, and it's the type system M5/M6 use anyway.
- **pyproject.toml + hatchling + uv** (proposed) — the packaging manifest M1
  must land as the first code. `uv` gives fast, lockfile-reproducible installs;
  the **src-layout** keeps imports clean (`import config`, `import ingestion`).

**JSONL and why determinism needs rules.** The derived streams serialize to
**JSONL** (one JSON object per line) under a gitignored path. "Rebuildable and
byte-identical" (AC7) is not free — it requires *named invariants*: rows sorted
by a total key, object keys in fixed order, `Decimal` rendered canonically,
dates as ISO-8601, `\n` endings. The plan enumerates these so a future edit
can't silently break reproducibility.

## 3. The high-level view (architecture)

M1 introduces the **two lowest layers** of the system, and only those:

```
src/
  …                         (api, agent, retrieval, index, chunking — later)
  ingestion/   ◄── M1       PDF + XBRL → normalized Elements + XBRLFacts
  config/      ◄── M1/M0    shared schema (the contracts) + settings + logging
```

Imports flow **downward only** (Constitution §1.6): `ingestion → config`, and
`config` imports nothing above it. Both modules are pre-named in architecture §3,
so neither is an unspecced new top-level module.

M1 **produces two of the seven typed contracts** in architecture §5:

- **`Element`** (ingestion → chunking): one parsed PDF unit — text/table/heading
  + provenance (FY, Item, page, entity, source filing).
- **`XBRLFact`** (ingestion → index→DuckDB, calc tool): one machine-readable
  figure — entity, concept, period (instant/duration + dates), value, unit,
  dimensions, source filing.

The defining shape of the design is the **structural firewall** — a diagram in
prose:

```
  PDF  ──►  ingestion.elements  ──►  Element   ──►  elements/<accession>.jsonl
                 (sole Element producer)
                                                        ╳  no shared number
  XBRL ──►  ingestion.xbrl      ──►  XBRLFact  ──►  facts/<accession>.jsonl
                 (sole XBRLFact producer — the ONLY place XBRLFact is built)
```

Two separate code paths, two separate output types, **no number crosses
between them**. `XBRLFact` is *defined* once (`config.schema`) and *constructed*
once (`ingestion.xbrl`). That makes "numbers come only from XBRL" true by
construction and checkable by a test, not by reviewer goodwill. Crucially, the
firewall is about **type ownership, not digit absence** — an `Element`'s table
text legitimately contains digits (it *is* the rendered table); what the PDF path
never builds is an `XBRLFact`.

## 4. The drill-down (low level) — the plan, fork by fork

This is the PLAN focus: walk the approach, and for **every fork** name the
alternative and the one-line reason it lost.

**Fork 1 — XBRL extractor: Arelle.** *Rejected: py-xbrl* (lighter, but I'd be
betting financial fidelity on a less-exercised transform implementation);
*rejected: raw lxml over `ix:` tags* (hand-rolling scale/sign/format is precisely
the §1.2 error surface). Arelle wins because the iXBRL transform + context +
dimension handling must be correct, and Arelle is the reference implementation.

**Fork 2 — PDF parser: Docling.** *Rejected: Unstructured* (comparable element
partitioning, weaker table-structure fidelity on dense 10-K tables); *rejected:
PyMuPDF/`fitz`* (pure-Python and fast with no model download, but flat text with
weak table structure — it would push table reconstruction onto M2). A subtle
enabling insight: because numbers come from XBRL, M1's PDF parse does **not** need
perfect numeric table extraction — only good text, reading order, page
provenance, and table *structure*. Docling's table model is strongest there; its
cost (a one-time layout/table model download) is named as a tension in Risks.

**Fork 3 — Item-boundary detection.** Neither parser knows "this is Item 7." A
deterministic post-parse pass (`ingestion.sections`) scans the heading Elements,
finds the Item headers, and stamps each Element. **Never guesses** — an undetected
boundary stamps `Item = unknown` and logs, rather than mis-attributing to a
neighbour. (Reviewer-driven: we now also *test* that the `unknown` path fires
rather than mislabeling, and that known Elements land in the *right* Item — not
merely that an Item value is present.)

**Fork 4 — Element entity.** *Resolved during review:* M1 stamps **every Element
`JPMC_CONSOLIDATED`.** Narrative prose has no reliable, deterministic
subsidiary-scope signal at this layer (unlike an XBRL context's explicit
legal-entity dimension), so subsidiary-scoping of narrative is *deferred*, not
inferred. "Where determinable" for Elements honestly reduces to consolidated here;
the rich entity work happens on the fact stream, where the signal is structural.

**Fork 5 — Contracts & config: Pydantic v2 + pydantic-settings.** *Rejected:
stdlib `@dataclass`* (zero-dep, but no boundary validation — and the fidelity
rules want exactly that validation). `value` is a **`Decimal`**, not `float`, so
exact-match numeric fidelity can't suffer binary-float drift. Settings are **one**
pydantic-settings object (Constitution §1.7) — no `os.getenv` scattered in
business code, no hardcoded paths.

**Fork 6 — The PDF↔accession↔FY join (reviewer-driven).** The PDFs are named by
date (`jpm-20241231.pdf`) but `source_filing` and the derived paths are keyed by
**accession** (`0000019617-25-000270`). That mismatch is a single-source-of-truth
trap. Resolution: **one** authoritative `FILINGS` table on `Settings`
(`accession, fiscal_year, pdf_filename, xbrl_instance`), resolved in **exactly one
place** (`pipeline.run()`); the filename date is never independently re-parsed for
FY, so the two can't drift (a §1.5-style discipline applied to provenance).

**Fork 7 — Serialization: JSONL.** *Rejected (for now): Parquet for facts*
(columnar and DuckDB-native — attractive, but the columnar fact store is M3's job;
M1 stays neutral and inspectable). The byte-identical guarantee rests on the
named serialization invariants above.

**Fork 8 — Packaging: pyproject.toml + hatchling + uv, src-layout.** *Rejected:
plain pip + requirements.txt; Poetry.* This is the first code, so it sets
precedent — flagged as one of the three forks (with the two parsers) most worth
the lead's explicit confirmation. The renderer's `reports/requirements.txt` stays
self-contained; M1 owns *app* deps, not a renderer reorg.

**Constitution tensions (Risks), and how each is handled.** The plan complies
with §1.1 (anchor exact-match test guards extraction), §1.2 (the firewall, by
construction), §1.3 (entity from context, period as enum, restatements retained),
§1.6 (downward imports only), §1.7 (one settings object), §1.8 (writes only to
gitignored `data/derived/`), and §5.1 (no secret needed — no live EDGAR, no cloud
LLM). One **process** tension is named openly: the §1.3 `[RATIFY]` ratification
rides inside M1 rather than its own Constitution-amendment spec. That's a
deliberate **§7 exception** — it only *resolves a pre-existing marker* the lead
already approved, with no change to the principle's substance — flagged so the
lead can veto the bundling.

**Test strategy — the tiering, and why it exists.** Constitution §4 splits eval
into a **cheap deterministic tier** (runs every `/implement`) and a **heavy tier**
(LLM-as-judge, re-embedding — named and queued for the pre-merge/scheduled gate).
For M1:

- The **cheap tier** is `test_xbrl_anchors.py`: exact-match of `us-gaap:Assets`
  (instant) and `us-gaap:NetIncomeLoss` (duration), consolidated, per FY, against
  the filed XBRL value — 10 assertions that *also seed the eval numeric truth
  set* (M7). The §4.2 **eval-regression gate is N/A** for M1 (it's below
  chunking/retrieval/agent — no baseline to move), and the plan says so.
- The **heavy tier is N/A** (no LLM/embedding surface yet); **no golden-set
  entries** are needed (the golden set proper is M7).
- A reviewer-driven **fast-vs-corpus split** keeps the per-implement run cheap:
  the expensive parse runs *once* via a session fixture, and field/anchor/entity
  tests read the serialized JSONL; only the rebuild-determinism test re-parses
  and is marked `@slow`.

**Reviewer findings — status.** The `spec-reviewer` returned a strong critique;
all material findings are **resolved** in the plan: the PDF↔accession mapping
(Fork 6), Element-entity rule (Fork 4), `fact_id` uniqueness (the `contextRef`
already encodes period+dimensions, now guarded by a test), nil/un-transformable
skipping, `unknown`-Item and Item-correctness tests, the period date-field
exclusivity invariant, a packaging import-smoke test, a non-degenerate volume
floor, the serialization invariants, version-pinning Arelle/Docling, the §7
process note, and the dangling `architecture §6.7` citation (it should read
*Constitution §6 item 7*; fixed in the doc-promotion step). The
`[VERIFY in IMPLEMENT]` on the anchor *values* is carried forward by design, with
a per-FY tag-override fallback if a concept tag doesn't resolve across all FYs.

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| XBRL extractor | **Arelle** | py-xbrl; raw lxml | Reference iXBRL transforms (scale/sign/format) + context/dimension — fidelity-critical |
| PDF parser | **Docling** | Unstructured; PyMuPDF | Strongest table-*structure* fidelity for 10-Ks (numbers still come from XBRL) |
| Element entity (M1) | **All consolidated** | Infer subsidiary from prose | No reliable deterministic narrative signal; defer, don't guess |
| Contracts & settings | **Pydantic v2 + pydantic-settings** | stdlib dataclass + os.getenv | Boundary validation = fidelity as a runtime guarantee; one settings object (§1.7) |
| Numeric value type | **`Decimal`** | `float` | Exact-match fidelity forbids binary-float drift |
| PDF↔accession join | **One `FILINGS` map, resolved in pipeline** | Parse FY from filename | Single source of truth; date-vs-accession names can't drift |
| Serialization | **JSONL + named invariants** | Parquet | Inspectable, neutral; columnar store is M3's job |
| Packaging | **pyproject + hatchling + uv, src-layout** | pip+requirements; Poetry | Fast, lockfile-reproducible; clean imports — *lead to confirm* |
| §1.3 [RATIFY] landing | **Ratify inside M1** | Separate amendment spec | Marker-resolution only, lead pre-approved; §7 exception, flagged |

## 6. Open threads & what's next

**Forks awaiting the lead's confirmation** (the plan exits PLAN only when these
are settled): the three precedent-setting ones — **Arelle**, **Docling**, and the
**packaging/installer (hatchling + uv)** stack — plus a nod to the §1.3-in-M1
bundling.

**Carried-forward markers:** the anchor *values* in `test_xbrl_anchors.py` are
`[VERIFY in IMPLEMENT against the instance]` (the tags `us-gaap:Assets` /
`us-gaap:NetIncomeLoss` are taxonomy-stable, but the exact integers and tag
resolution per FY are confirmed against the data during IMPLEMENT, with a per-FY
override fallback).

**Open Questions still open (by design):** an optional EDGAR *refresh/verify*
path (low priority — we read vendored copies), and final confirmation of tag
stability across the 2021→2025 taxonomy versions (settled in IMPLEMENT).

**Risk carried forward:** Docling's one-time model download is a mild tension with
the offline-rebuild goal — documented, mitigated by local caching, revisited if
the offline constraint hardens.

**Next SDD step:** `/tasks` — decompose this plan into ordered, one-concern tasks
(roughly the 7 Sequencing steps), each with an acceptance check. I will **not**
invoke it; that's the lead's call after confirming the plan.
