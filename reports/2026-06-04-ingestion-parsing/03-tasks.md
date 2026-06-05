---
spec: 2026-06-04-ingestion-parsing
stage: tasks
report: 03-tasks
created: 2026-06-04
---

# Educator Report — TASKS · M1 Ingestion & parsing (Elements + XBRLFacts)

> **How to read this.** This is the lead's 360° companion to the TASKS step. It
> opens at the altitude of *decomposition as a discipline* — why we cut a
> confirmed plan into exactly these eleven pieces — and drills down to each
> task, the dependency edge that orders it, and the one acceptance check that
> decisively proves it. It teaches the *why* behind the shape of the list:
> what "one concern per task" buys us, why a test rides **with** the behavior
> it proves instead of trailing it, and how the §4 eval tiering lands a single
> cheap deterministic gate at M1. Read top-to-bottom to finish able to defend
> the task list, not just read it. Markdown is the source of truth; the sibling
> PDF is rendered by `reports/render.py`.

---

## 1. Where we are (orientation)

The **TASKS** step for **M1 — Ingestion & parsing** just finished. The chain so
far: CLARIFY produced the contract (*what* M1 must do,
[`spec.md`](../../specs/2026-06-04-ingestion-parsing/spec.md)); PLAN produced the
design (*how*, [`plan.md`](../../specs/2026-06-04-ingestion-parsing/plan.md));
TASKS now produces the **build order** —
[`tasks.md`](../../specs/2026-06-04-ingestion-parsing/tasks.md), eleven ordered,
PR-sized, one-concern tasks (T1–T11), each carrying the single test that proves
it. Nothing here touches `src/`; TASKS only *plans the cuts*. On the roadmap
(`docs/roadmap.md`) M1 is still the bottom of the dependency chain and the first
application code; on the data-flow map (`docs/architecture.md` §4) we are still
at the far left:

```
  ▶ ingestion (M1)  ─►  chunking (M2)  ─►  index (M3)  ─►  retrieval (M4)  ─►  agent (M5)  ─►  answer
    PDF → Elements                       (the eleven tasks below build this leftmost box)
    XBRL → XBRLFacts
```

Why this step matters: a plan describes a destination; a task list is the
*sequence of safe, individually-verifiable steps* to reach it. The discipline
is that **each step compiles, tests green, and could be a single reviewed
commit.** If the decomposition is wrong — tasks too big, concerns bundled, a
test that doesn't actually pin the behavior — every later `/implement` inherits
the mess. So this step's whole job is to make the build *boring*: pick up
`tasks.md`, do T1, prove it, commit; do T2, prove it, commit.

## 2. The domain in play (teach me)

This step's "domain" is two-layered. There is the **engineering discipline** of
decomposition and test-tiering, and there are the **data nuances** that forced
specific task boundaries. You need both to defend the list.

**One concern per task — and what a "concern" is.** A concern is a single reason
to change code. Bootstrapping the package is one concern; defining the typed
contracts is another; extracting facts from XBRL is another. The rule (from the
TASKS command, §4.4 of the Constitution behind it) is that a task never bundles
a refactor with a feature, or a test-fix with a behavior change. Why we care:
when a task does exactly one thing, its **acceptance check is unambiguous** — if
it fails, you know *which* concern broke. Bundled tasks produce "something in
this 600-line diff is wrong" — the exact debugging tax SDD exists to avoid.

**"PR-sized" and the 2-hour heuristic.** Each task should land in under ~2 hours
of focused work and read as one coherent commit. This isn't bureaucracy: small
diffs get *real* review, and a green test on a small diff is strong evidence.
T4 (the XBRL extractor) is the one task that strains this ceiling — flagged
below — because the Arelle context/unit/transform logic is genuinely one
indivisible concern (you can't half-extract a fact). We kept it whole rather
than make an artificial cut that splits a single behavior across two commits.

**Tests ride *with* the change (the §4.4 rule), not after it.** A tempting but
wrong decomposition makes "write the code" one task and "write the tests"
a later task. We reject that. The test that proves a behavior is part of the
*same* task that introduces the behavior, for a concrete reason: a behavior
with no test is **unverifiable at the moment it's written**, so its task has no
decisive acceptance check, so you can't honestly mark it done. Tests-trailing
also tends to produce tests written to pass the code (confirmation), not tests
written to pin the contract. Riding-with keeps the test honest because you're
proving the *spec's* claim, task by task.

**The §4 eval tiering, and why M1 lands exactly one cheap gate.** The
Constitution splits evaluation into a **cheap deterministic tier** (exact-match
numeric vs XBRL, retrieval hit@k — fast, runs every `/implement`) and a **heavy
tier** (LLM-as-judge, re-embedding — named and queued for the pre-merge gate).
M1's cheap tier is **T5**: `us-gaap:Assets` (instant) and `us-gaap:NetIncomeLoss`
(duration), consolidated, per FY, exact-match against the filed value — ten
assertions. There is **no heavy tier** at M1 (no LLM or embedding surface
exists yet) and **no §4.2 eval-regression gate** (that gate guards
retrieval/agent/chunking changes against a baseline; ingestion sits *below*
all of them, so there is no baseline to regress). The task list says this
explicitly so a future reader doesn't go looking for a golden-set entry that
isn't supposed to exist yet — the golden set proper is M7.

**Why the cheap-eval gate is its own task (T5), separate from the extractor
(T4).** This is the subtlest decomposition call. T4 *produces* facts and proves
they're well-formed (fields present, ids unique, nils skipped, a volume floor).
T5 proves a *different* thing: that two specific, business-critical numbers come
out **numerically exact**. They're separated because (a) T5 carries
[VERIFY-in-IMPLEMENT] work — reading the ten true integers out of the five
instances and pinning them — which is a distinct activity from writing the
extractor; and (b) T5 is the **first seed of the M7 numeric truth set**, so it
earns first-class status as the §4.3 gate rather than hiding as one more
assertion inside T4's well-formedness test. The §4.4 "ride with the behavior"
rule still holds: T5 rides immediately *after* the behavior it checks, and only
the extractor it depends on sits above it.

**The data nuances that dictated specific boundaries.** Three facts about the
corpus forced three task shapes:

- **The firewall needs *both* producer paths to exist before it can be
  checked.** "Numbers come only from XBRL" (Constitution §1.2) is enforced
  structurally — `XBRLFact` is defined once and constructed only in
  `ingestion.xbrl`. You cannot *test* that the Element path never builds an
  `XBRLFact` until the Element path (T6/T7) *and* the fact path (T4) both
  exist. So the firewall guard is its own task (**T8**) that depends on all
  three. It's a type-ownership check, **not a digit-grep** — an Element's table
  text legitimately contains digits (it *is* the rendered table); what it must
  never do is *construct a fact*.
- **Restatements force a two-instance test.** Each 10-K restates 2–3 prior
  years, so the FY2022 figure as *originally filed* (2022 10-K) and as
  *restated* (2024 10-K) must both survive, distinguishable by source
  accession. That's why T4's entity/period test specifically parses **two**
  instances (2022 + 2024) and asserts both FY2022 facts are present — a
  single-instance parse could never prove retention.
- **Item boundaries aren't in either parser's output.** Neither Docling nor
  Arelle knows "this is Item 7." A deterministic post-pass
  (`ingestion.sections`, **T7**) scans heading Elements and stamps each Element
  with its Item — and where it can't find a boundary it stamps `unknown` and
  warns, **never** the previous Item's label. That "fail honest, not silent"
  behavior is itself a tested contract (T7's `test_missing_header_yields_unknown`).

**Frameworks this step leaned on (named, since the list pins them).** The tasks
reference the libraries PLAN chose, and T1 *pins* them: **Arelle**
(`arelle-release`, the reference iXBRL processor — T4), **Docling** (structured
PDF parse with table structure — T6), **Pydantic v2 + pydantic-settings**
(validated contracts + one settings object — T2/T3), and **pyproject + hatchling
+ uv** in **src-layout** (the first packaging manifest — T1). Version-pinning
Arelle and Docling is called out in T1's notes because a silent minor-version
bump to an XBRL transform table or a PDF model is exactly the kind of
non-reproducibility AC7 forbids.

## 3. The high-level view (architecture)

Decomposition is, concretely, a **topological sort of the plan's dependency
graph**. Read the eleven tasks as a DAG — an edge `A → B` means "B needs A
to exist first":

```
  T1  Bootstrap packaging + skeleton            (no deps — the ground)
   │
   ▼
  T2  config.schema  (Element, XBRLFact, …)     ── the typed contracts
   │
   ├──────────────────────────────┬─────────────────────────┐
   ▼                              ▼                         ▼
  T3  config.settings + logging   T9  serialize (JSONL)    (T2 alone is enough
   │   (FILINGS, paths)            │   write/read           for serialize + the
   │                              │                        contracts location)
   ├───────────────┐              │
   ▼               ▼              │
  T4  xbrl.py      T6  elements.py│   ◄── the two producer paths (the firewall's two sides)
   │  (XBRLFact)    │  (Element)   │
   ▼               ▼              │
  T5  anchors      T7  sections   │   ◄── T5 = cheap-eval gate; T7 = Item stamping
   │  (cheap gate)  │  (assign_items)
   │               │              │
   └──────┬────────┴──────────────┤
          ▼                       ▼
         T8  firewall guard      T10  pipeline CLI (the join + rebuild, @slow)
         (needs T4+T6+T7)         (needs T9 + T4 + T6 + T7)

  T11  Doc-promotions (constitution/architecture/spec text)   (no code deps — placed last
                                                               so docs describe shipped behavior)
```

What the shape tells you:

- **T1 → T2 is the spine.** Nothing imports until the package installs (T1) and
  the contracts exist (T2). Every other task hangs off these two.
- **The graph forks into two independent producer chains** —
  `T3→T4→T5` (the XBRL/number side) and `T3→T6→T7` (the PDF/narrative side) —
  which is the **structural firewall made visible as a build order**. The two
  sides never share a node until T8 (the guard that proves they stayed
  separate) and T10 (the pipeline that runs both and writes their separate
  outputs).
- **T8 and T10 are the join points**, and both correctly sit at the bottom:
  you can't guard the firewall or rebuild the whole corpus until both paths
  exist.
- **T11 is deliberately last and edge-free** — it promotes doc markers
  (the §1.3 `[RATIFY]`, the architecture §7 vendoring wording, a citation fix)
  the Constitution requires to land *in the same change* as the behavior they
  describe. Placing it last means the docs are edited to describe code that
  already shipped, not code we hope to ship.

M1 produces two of architecture §5's seven typed contracts — **`Element`**
(ingestion → chunking) and **`XBRLFact`** (ingestion → index/calc) — and both
are *defined* in T2's `config.schema`, honoring the downward-only import rule
(Constitution §1.6): `ingestion → config`, never the reverse.

## 4. The drill-down (low level) — task by task, and what its check proves

For each task: the one concern, the dependency edge that orders it, and the
single thing its acceptance check *decisively* proves.

**T1 — Bootstrap packaging + repo skeleton.** *Concern:* make `src/` installable
and importable. *Proves:* `test_packaging.py::test_config_and_ingestion_importable`
— an editable src-layout install resolves `import config` and `import ingestion`,
and the `slow` marker is registered. This is the "does the ground exist" check;
everything else is unreachable until it's green. *Why first:* no dependency —
it's the only task that creates the package itself.

**T2 — `config.schema`, the typed contracts.** *Concern:* define the five types
(`Element`, `XBRLFact`, `ElementKind`, `PeriodType`, `Entity`) — and define them
**in `config`, not `ingestion`**. *Proves:*
`test_contracts_location.py::test_types_defined_in_config` — the types import
from `config.schema` and are *owned* there. This check exists because the
firewall and the whole layer-separation rule rest on `XBRLFact` having exactly
one home; the test makes "defined once, in the right module" a fact, not an
intention. The period-exclusivity validator (instant ⇒ only `period_instant`;
duration ⇒ only start/end) is part of this task because the *type* is where that
invariant belongs. *Depends-on:* T1.

**T3 — `config.settings` + logging.** *Concern:* the single settings object and
the authoritative `FILINGS` table (`accession, fiscal_year, pdf_filename,
xbrl_instance`). *Proves:* `test_settings.py::test_filings_table_resolves` — all
five rows map accession→FY correctly **and** each row's PDF and XBRL instance
actually exist on disk under the settings-rooted paths. This check is the
single-source-of-truth guard from PLAN's Fork 6 made executable: if the date-named
PDF and the accession key ever drift, this test fails. *Depends-on:* T2.

**T4 — XBRL extractor (Arelle → `XBRLFact`s).** *Concern:* the sole `XBRLFact`
producer — load instance + linkbases, resolve context (entity, period, dims),
resolve unit, apply the iXBRL scale/sign/transform, skip nil/un-transformable
facts. *Proves:* four well-formedness checks in `test_xbrl_extract.py` (fields
present; fact_ids unique per filing; nils and un-transformable facts skipped not
coerced to 0; a non-degenerate fact-count floor) **plus** three in
`test_entity_period.py` (entity always set and distinct; period date-fields
exclusive; **restated FY2022 present from both the 2022 and 2024 instances**).
Together they prove the fact stream is *well-formed, honest about gaps, and
restatement-preserving*. *Depends-on:* T3 (paths), T2 (`XBRLFact`).
**This is the borderline-large task** — see §6.

**T5 — Anchor numeric truth (the cheap-eval gate).** *Concern:* prove two
specific numbers are *exactly* right. *Proves:*
`test_xbrl_anchors.py::test_total_assets_and_net_income_exact` — exact-match of
`us-gaap:Assets` and `us-gaap:NetIncomeLoss`, consolidated, per FY, against the
filed XBRL value (10 assertions = 2 metrics × 5 FY). This **is** the §4.3 cheap
deterministic tier and the first seed of the M7 truth set. It's separated from
T4 because it carries the `[VERIFY in IMPLEMENT]` work (reading and pinning the
ten true integers) and because a numeric-exactness gate is a different claim than
well-formedness. *Depends-on:* T4.

**T6 — PDF parser (Docling → `Element`s with provenance).** *Concern:* the sole
`Element` producer — structured parse, `kind ∈ {text, table, heading}`, every
Element stamped with FY + page + entity (consolidated) + an `item` field left
`unknown` pending T7. *Proves:*
`test_elements_provenance.py::test_every_element_has_provenance` and
`::test_element_count_floor` — every Element has full provenance and each filing
yields more than a floor count (non-degenerate parse). *Depends-on:* T3 (paths),
T2 (`Element`). Runs in parallel-concept with T4 — the two producer chains are
independent.

**T7 — Item-boundary stamping (`sections`).** *Concern:* a deterministic pure
pass that stamps each Element with its 10-K Item, or `unknown` if no boundary is
found. *Proves:* two checks — `test_sections.py::test_missing_header_yields_unknown`
(a garbled Item header ⇒ `unknown`, **never** the previous Item's label — proven
on a pure mini-fixture) **and**
`test_elements_provenance.py::test_known_elements_land_in_right_item` (real
corpus: an MD&A Element ⇒ Item 7, a financial-statements Element ⇒ Item 8). The
pair proves *both* that it lands known content correctly *and* that it fails
honest rather than silent. *Depends-on:* T6.

**T8 — Firewall guard (the §1.2 structural check).** *Concern:* prove the Element
path never builds a fact. *Proves:*
`test_firewall.py::test_element_path_never_constructs_xbrlfact` — a static
AST/import check that no symbol in `ingestion.elements`/`ingestion.sections`
references `XBRLFact`, and that `XBRLFact` is defined only in `config.schema`.
**Type-ownership, not a digit-grep** — Element text legitimately contains digits.
This is the keystone §1.2 rule made executable, and it can only pass once both
paths exist. *Depends-on:* T4, T6, T7.

**T9 — JSONL serialization (deterministic write/read).** *Concern:* the
`write_jsonl`/`read_jsonl` round-trip and its byte-stability invariants (rows
sorted by total key, `sort_keys=True`, `Decimal`→canonical string, dates→ISO-8601,
`\n` endings, UTF-8). *Proves:*
`test_serialize.py::test_roundtrip_and_byte_stable` — both types round-trip equal,
and re-serializing identical input yields byte-identical output. *Decomposition
note:* this is a **new test versus the plan's table** — splitting serialization
into its own task gives it a decisive, isolated check (faster than proving
determinism only through the full pipeline rebuild). *Depends-on:* T2 (types
only — serialize needs no parser).

**T10 — Ingestion pipeline CLI (the join + rebuild).** *Concern:* the *only*
place the PDF↔accession↔FY join is resolved (`run()` reads `Settings.FILINGS`);
writes `elements/` + `facts/` JSONL under gitignored `data/derived/`. *Proves:*
`test_pipeline_rebuild.py::test_deterministic_and_gitignored` (`@slow`) — a run
over all five filings writes both streams, a second run is byte-identical, an
unknown accession raises a hard error, and no network fetch occurs. This is the
AC7 rebuild-from-committed-source guarantee. Marked `@slow` and excluded from the
default per-implement run because it re-parses the whole corpus. *Depends-on:*
T9 (serialize), T4 (facts), T6 (elements), T7 (items).

**T11 — Doc-promotions.** *Concern:* land the doc changes the Constitution
requires *with* the code — ratify §1.3 (drop `[RATIFY]`, state "original filing
for FY N"), refine architecture §7/§2/§9 to say the XBRL is **vendored** (not
"pulled from EDGAR into a gitignored path" as the live mechanism), and fix the
spec's dangling `architecture §6.7` citation to **Constitution §6 item 7**.
*Proves:* a **text presence/absence check**, not a pytest — see §6. *Depends-on:*
none (doc-only; placed last so docs describe shipped behavior). roadmap M1→`done`
is deferred to EVALUATE, not here.

**Coverage check — every spec AC maps to a task's acceptance check:** AC1
(Elements + provenance) → T6/T7; AC2 (XBRLFacts + fields) → T4; AC3 (restatements
retained) → T4's `test_restated_fy2022_both_present`; AC4 (cheap deterministic
anchor) → T5; AC5 (numbers only from XBRL) → T8; AC6 (entity explicit) →
T4's entity test; AC7 (rebuild from committed source, gitignored) → T10; AC8
(config holds schema + settings + logging) → T2/T3. T11 is the Constitution-
mandated doc-promotion that rides in the same change.

## 5. Decisions & trade-offs

These are the *decomposition* forks — the choices about how to cut, not what to
build (those were PLAN's).

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| Tests placement | **Ride with the producing task** | Separate "write tests" task(s) | A behavior with no test has no decisive acceptance check; riding-with keeps the test honest (§4.4) |
| Cheap-eval anchor | **Its own task (T5)** | One more assertion inside T4 | Carries `[VERIFY]` data-pinning work + seeds the M7 truth set — earns first-class gate status |
| Firewall guard | **Its own task (T8)** | Fold into T4 or T6 | Needs *both* producer paths to exist; can't be checked until T4+T6+T7 land |
| Serialization | **Its own task (T9)** | Prove determinism only via T10 rebuild | Decisive, isolated, fast check; doesn't need the parsers — only the types |
| T4 extractor sizing | **Keep whole (flagged)** | Split context/unit/transform across tasks | Extracting one fact is one indivisible behavior; an artificial cut splits a single concern across commits |
| Item stamping | **Its own task (T7)** after T6 | Stamp Items inside the Docling parse (T6) | Different concern (deterministic post-pass) + needs the heading Elements T6 produces |
| Pipeline rebuild test | **`@slow`, excluded from default run** | Run on every `/implement` | Re-parses the whole corpus; cheap tier must stay fast — producer tests use a session fixture instead |
| T11 doc acceptance | **Text presence/absence check** | A pytest assertion | Doc edits have no runtime surface; a text check is the honest, decisive proof for a doc-only task |
| T11 placement | **Last, edge-free** | First or alongside the code | Docs should describe *shipped* behavior; landing last guarantees that |

## 6. Open threads & what's next

**Two tasks flagged for the lead's eyes:**

- **T4 is borderline-large** — it's the one task that strains the ~2-hour /
  PR-sized ceiling, because the Arelle context + unit + scale/sign/transform +
  nil-skipping logic is a single indivisible concern (you cannot half-extract a
  fact). We kept it whole rather than make an artificial cut that splits one
  behavior across two commits. If during `/implement T4` it proves too big, the
  natural fault line is *extraction* (produce raw facts) vs *context/period
  resolution* (entity + instant/duration) — but only split if the size genuinely
  bites.
- **T11's acceptance is a text check, not a pytest** — appropriate for a
  doc-only task (doc edits have no runtime surface to assert against), but worth
  naming so it's a conscious exception to the "every task names a test"
  rule, not an oversight.

**Markers carried forward into IMPLEMENT:**

- **T5's anchor *values* are `[VERIFY in IMPLEMENT]`** — the ten true integers
  (`us-gaap:Assets` and `us-gaap:NetIncomeLoss` per FY) get read out of the five
  instances and pinned during `/implement T5`, with a per-FY `{fiscal_year:
  concept_tag}` override fallback if a tag doesn't resolve across all five
  taxonomy versions (2021→2025).
- **The §1.3 `[RATIFY]` and the architecture §7 vendoring wording** are still
  live in the docs until T11 promotes them — by design, so they land in the same
  change as the code that makes them true.

**Open Questions still open (by design):** an optional EDGAR *refresh/verify*
path (low priority — we read vendored copies), and final tag-stability
confirmation across taxonomy versions (settled inside T5).

**Next SDD step:** `/implement T1` — bootstrap the packaging + skeleton, the
only task with no dependencies. I will **not** auto-invoke it; that's the lead's
call. Status bumps from `tasks` to `implement` on that first `/implement`.
