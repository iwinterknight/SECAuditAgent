---
spec: 2026-06-04-ingestion-parsing
stage: implement
report: 04-implement-T5
created: 2026-06-07
---

# Educator Report — IMPLEMENT · M1 Ingestion & parsing (T5 · Anchor numeric truth — the cheap-eval gate)

> **How to read this.** Top-down: first *where* this task sits, then the
> *domain* it encodes (exact-match anchoring, the two anchor metrics and their
> period shapes, consolidated+dimensionless scoping, the §4.3 cheap-eval tier,
> the M7 truth-set seed, taxonomy tag stability), then the *architecture* view,
> then the mandatory two-level **Code Walkthrough**. T5 writes no `src/` code —
> it adds one test file — so the walkthrough is of a *gate*, not a producer. By
> the end you should be able to re-present every construct in
> `tests/unit/test_xbrl_anchors.py` and defend why a single-dollar drift in any
> of ten figures must turn the build red.

---

## 1. Where we are (orientation)

We just finished **T5** of **M1 (Ingestion & parsing)**. T4 made the XBRL lane
*produce* facts; **T5 proves those facts are numerically true.** It is the first
**deterministic fidelity gate** in the project: `test_xbrl_anchors.py` pins ten
figures — **Total assets** and **Net income**, each for FY2021–FY2025 — to the
exact integer JPMorgan Chase filed in XBRL, and fails the moment extraction
drifts by one dollar. On the data-flow diagram (`docs/architecture.md` §4:
ingest → chunk → index → retrieve → agent → answer) T5 doesn't add a box; it
**clamps the left-most box's output to ground truth**. T4 established the
*shape* of an `XBRLFact` (every field populated, periods exclusive, entities
distinct, ids unique); T5 establishes the *digits* — the part a shape test
deliberately left alone. This is also the moment the Constitution's cheap
deterministic eval tier (§4.3) stops being a policy and becomes a runnable
check, and the moment the **M7 numeric truth set** gets its first ten seeds.

## 2. The domain in play (teach me)

T5 is conceptually smaller than T4 but it encodes the project's whole reason for
existing. Six ideas.

### 2.1 Exact-match, not "close enough"

Most software testing tolerates approximation — floats compare within an
epsilon, timings within a window. **Financial fidelity does not.** JPMorgan's
FY2024 total assets are `$4,002,814,000,000` exactly; `$4,002,813,000,000` is a
*wrong answer*, not a rounding. The whole §1.2 firewall — numbers come only from
XBRL, never from an LLM or a parsed table — exists so the system can promise
exactness. A tolerance-based anchor would quietly admit the very bugs the
firewall is built to stop: a missed `scale="6"` (off by 10⁶), a dropped sign, a
half-applied transform. So the anchor asserts `Decimal` **equality**. `Decimal`
(not `float`) is load-bearing here too: `float("4002814000000")` is representable,
but intermediate float arithmetic anywhere upstream could round, and an
exact-match gate on a float type would be self-defeating. The fact carries a
`Decimal`; the test compares against a `Decimal`; no binary-float ever touches
the figure.

### 2.2 Two metrics, two period shapes

The anchor deliberately picks **one instant and one duration** (the period
distinction T4's §2.3 was about):

- **Total assets** (`us-gaap:Assets`) — an **instant**: a balance-sheet "as of"
  figure, dated at year-end (`2024-12-31`). It's the single most-quoted measure
  of a bank's size.
- **Net income** (`us-gaap:NetIncomeLoss`) — a **duration**: an income-statement
  "for the year" figure, spanning the full FY (`2024-01-01 … 2024-12-31`). It's
  the headline of profitability.

Pinning one of each means the gate exercises *both* period-resolution paths —
including T4's end-exclusive **-1-day** correction — on every run. If that
correction ever regressed (an instant surfacing at `2025-01-01`), the instant
anchor would fail to find its fact and the gate would fire. So the anchor isn't
just a value check; it's a standing regression test on period handling.

### 2.3 Consolidated and dimensionless: the figure an analyst quotes

For each (FY, metric) the anchor selects the fact that is **consolidated**
(`Entity.JPMC_CONSOLIDATED` — the registrant JPMorgan Chase & Co., not the bank
subsidiary, T4 §2.4) and **dimensionless** (`dimensions == {}` — no segment, no
business-unit, no instrument breakdown). That pair is precisely the
registrant-level total a reader sees on the face of the financial statements —
and, not coincidentally, exactly how a downstream numeric lookup (the M5 calc
tool) will scope a figure: by concept + entity + period, with no dimensional
qualifier. The anchor therefore validates the same selection path the live
system will use, not an artificial one. Each such selection must resolve to
**exactly one** fact; that uniqueness is itself part of the gate (see §2.6).

### 2.4 The §4.3 cheap deterministic tier — this *is* the eval

The Constitution splits evaluation into tiers (§4): a **cheap deterministic**
tier that runs on every implement (exact-match numeric vs XBRL, or retrieval
hit@k on a small fixed set), and a **heavy** tier (LLM-judge, re-embedding) that
is queued, not run inline. T5 *is* the cheap tier's first instance. There is no
separate eval command to run for this task — the acceptance test and the
cheap-eval check are the same ten assertions. That's why `tasks.md` calls T5
"the §4.3 cheap deterministic tier" rather than pointing at an `eval/` harness:
at M1 (below chunking/retrieval/agent) there's no eval-regression baseline to
move, so the deterministic anchor stands alone.

### 2.5 Seeding the M7 numeric truth set

These ten figures are not throwaway test constants. The eval milestone (M7) will
assert that the *answered* system — retrieval + agent + calc, end to end —
reproduces known-true numbers. The cheapest, least-disputable such numbers are
exactly these: headline figures, filed in XBRL, verifiable against the public
10-K. T5 pins them once, at the source, so M7 inherits a vetted seed instead of
re-deriving truth later. Writing them down here, against the extractor, is the
first link in a chain that ends at "the agent's answer equals the filing."

### 2.6 The `[VERIFY in IMPLEMENT]` discipline and taxonomy tag stability

The plan flagged a real risk (spec Open Question): the us-gaap **taxonomy**
evolves yearly, so a concept tag valid for FY2021 might be renamed by FY2025 —
and a pinned tag that silently fails to resolve for one FY would make the anchor
pass *vacuously* (zero facts matched, nothing asserted). The plan's countermeasure
was a marker, `[VERIFY in IMPLEMENT]`: don't trust the tags or type the values
from memory — **read all ten from the five instances during IMPLEMENT and
confirm each resolves to exactly one fact.** That verification ran this task. The
finding: **both `us-gaap:Assets` and `us-gaap:NetIncomeLoss` are stable across
all five FYs** — each resolves to exactly one consolidated, dimensionless fact,
all in USD at `decimals=-6`. That resolves the spec's "anchor concept-tag
stability" Open Question outright. The graceful-degradation fallback the plan
asked for — a per-FY `{(fiscal_year, tag): actual_tag}` override map — is still
present in the test but **empty**: it's the one sanctioned place to record a
future rename, so the gate degrades by *adding a mapping* rather than by
loosening the exact-match assertion. The two guards together (exactly-one-match
+ exact-value) make a vacuous pass impossible: a tag that stopped resolving would
fail the count assertion, not slip through.

The ten verified values (full dollars; filings report $ in millions):

| FY | Total assets (`us-gaap:Assets`, instant) | Net income (`us-gaap:NetIncomeLoss`, duration) |
|---|---|---|
| 2021 | 3,743,567,000,000 | 48,334,000,000 |
| 2022 | 3,665,743,000,000 | 37,676,000,000 |
| 2023 | 3,875,393,000,000 | 49,552,000,000 |
| 2024 | 4,002,814,000,000 | 58,471,000,000 |
| 2025 | 4,424,900,000,000 | 57,048,000,000 |

## 3. The high-level view (architecture)

T5 adds no module and no `src/` symbol. It is a **test-only** task — a consumer
of the `XBRLFact` §5 contract that asserts on the output of `ingestion.xbrl`
(T4). In the layer map nothing moves; what changes is that the ingestion layer
now has a *truth clamp* on its numeric output:

```
   config.settings.FILINGS ──▶ (FY ↔ accession join, single source of truth)
              │
              ▼
   ingestion.xbrl.extract_facts(dir, *, source_filing) ──▶ list[XBRLFact]
              │                                                    │
              │  (per FY, all five filings, parsed once)           │
              ▼                                                    ▼
   tests/unit/test_xbrl_anchors.py                      ┌─ select: concept + consolidated
     facts_by_fy  ── session fixture ──────────────────▶│          + dimensionless + period
     _anchor_fact ── exactly-one selection ─────────────┤          ⇒ exactly one fact
     test_…_exact ── Decimal-equality × 10 ─────────────└─ assert value == filed integer
                                                                   assert unit == "USD"
```

- **Consumes:** `config.settings` (the `FILINGS` table, to iterate the five
  filings and keep the FY↔accession join in its one home), `config.schema`
  (`Entity`, `PeriodType`, `XBRLFact`), and `ingestion.xbrl.extract_facts`.
  Imports flow downward only; a test reaching into the modules it guards is the
  normal direction.
- **Produces:** no runtime artifact — a **pass/fail signal**. Its "output" is the
  guarantee that the ten anchor figures are extracted exactly, on every implement.
- **Boundary note:** the task's `Files:` list is exactly one file. The all-five
  extraction fixture lives **inside the test module**, not in `conftest.py`,
  precisely so T5 stays within its declared file (conftest's fixtures are FY2024
  + FY2022 only; widening them would have touched a file outside the task).

## 4. The drill-down (low level) — the two-level Code Walkthrough

### Module level

- **Module:** `tests/unit` (the cheap-eval gate); it validates `ingestion.xbrl`
  against `config`'s contracts. No `src/` module changed.
- **Role / data-flow position:** a clamp on the numeric output of the left-most
  ingest box — the executable form of Constitution §4.3 (cheap deterministic
  eval) and §1.1/§1.2 (numeric fidelity), and the first seed of the M7 truth set.
- **Boundary change:** none to any contract. The task adds one test file that
  *reads* the `XBRLFact` §5 contract and asserts on values; it constructs no
  `XBRLFact` (the firewall is untouched) and exposes no new public symbol.

### File level

**`tests/unit/test_xbrl_anchors.py`** — the anchor gate (the whole task).

- **Module docstring** — teaches why the gate exists: exact-match over both
  period shapes, consolidated+dimensionless scoping, the §4.3 tier, the M7 seed,
  and the `[VERIFY in IMPLEMENT]` provenance of the pinned values. A reader opening
  the file learns the *why* before the *what*.
- `_ASSETS`, `_NET_INCOME`, `_PERIOD_TYPE` — the two anchor concept tags and the
  period shape each is reported in (`Assets`→instant, `NetIncomeLoss`→duration).
  Naming the period shape in data (not in branching logic) keeps the selection
  helper generic.
- `_FISCAL_YEARS` — the five FYs `(2021…2025)`, the one place the FY span is
  written.
- `_EXPECTED` — the pinned truth: `{(fiscal_year, concept): full_dollar_int}`,
  ten entries. Values use digit-group underscores so the filed `$M` figure stays
  legible (`4_002_814_000_000` reads as $4,002,814 million). This is the data the
  `[VERIFY in IMPLEMENT]` step produced; it is also the literal M7 seed.
- `_CONCEPT_OVERRIDES` — the per-FY tag-rename hook, **empty today** (both tags
  proved stable). Present so a future taxonomy drift is absorbed by *adding a
  mapping* here, never by weakening an assertion.
- `_ANCHORS` — the ten `(FY, concept)` pairs, built metric-major so the
  parametrize ids read `FY2021-Assets … FY2025-NetIncomeLoss`.
- `facts_by_fy` (session fixture) — extracts **all five filings once**, keyed by
  fiscal year, routing through `Settings.FILINGS` so the FY↔accession join is
  never re-derived. Session scope pays the multi-second parse a single time for
  all ten cases — the same parse-once discipline the conftest fact fixtures use,
  kept local because the task owns only this file.
- `_anchor_fact(facts, concept, period_type, fy)` — selects the one consolidated,
  dimensionless fact for an anchor: filters by concept, empty `dimensions`,
  `JPMC_CONSOLIDATED`, the right `PeriodType`, and the exact period (instant at
  `date(fy,12,31)`; duration `date(fy,1,1)…date(fy,12,31)`). It **asserts exactly
  one match** — zero means the tag failed to resolve (catches a vacuous pass),
  many means an ambiguous anchor (a dedup or dimension leak). That count assertion
  is half the gate.
- `test_total_assets_and_net_income_exact` (parametrized × 10) — the named
  acceptance check. For each `(FY, concept)`: look up the pinned `expected`, apply
  any override to get the query `tag`, pull the single fact via `_anchor_fact`,
  then assert `fact.value == Decimal(expected)` **and** `fact.unit == "USD"` (an
  exact figure in the wrong unit is still wrong). Parametrization makes each
  anchor an independently-reported case — a regression names the precise
  `FY2023-NetIncomeLoss` rather than a vague whole — while the shared
  `::test_total_assets_and_net_income_exact` node prefix means the acceptance
  selector still runs all ten.

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| Match strictness | `Decimal` **equality** | tolerance / `pytest.approx` | a financial figure is exact or wrong; tolerance would admit scale/sign/transform bugs (§2.1) |
| Anchor metrics | total assets + net income | a larger basket of concepts | one instant + one duration covers both period paths with the two most-quoted, least-disputable figures (§2.2) |
| Fact scoping | consolidated + dimensionless | any matching fact / a segment slice | the registrant total an analyst quotes, and the same path the M5 calc tool will use (§2.3) |
| Uniqueness | assert **exactly one** match | take the first / `any()` | a vacuous pass (tag didn't resolve) and an ambiguous anchor both become failures (§2.6) |
| Pinned values | read from the 5 instances in IMPLEMENT | type from memory / the public 10-K | the `[VERIFY in IMPLEMENT]` discipline — grade against the data the extractor actually sees (§2.6) |
| Tag drift | empty `_CONCEPT_OVERRIDES` hook | hard-code one tag / drop the FY that drifts | both tags proved stable; the hook degrades by *adding a mapping*, never by loosening the gate (§2.6) |
| Test shape | `parametrize` × 10 | one function, ten inline asserts | a failure names the exact `FY-metric`; the node prefix still satisfies the single-named-test acceptance |
| Extraction fixture | session-scoped, **in the test file** | add it to `conftest.py` | parse-once economy *and* stay within T5's one declared file (conftest is outside scope) |
| Unit | also assert `== "USD"` | value only | a right number in the wrong unit is wrong; both anchors are USD |

## 6. Open threads & what's next

- **Open Question resolved.** "Anchor concept-tag stability across taxonomy
  versions" (spec Open Questions) is now answered: `us-gaap:Assets` and
  `us-gaap:NetIncomeLoss` resolve identically across FY2021–FY2025. The override
  map stays as the standing safety hook, empty. (The doc-promotion that flips the
  spec's status text is T11; T5 records the finding.)
- **No new `[RATIFY]`/`[VERIFY]` markers** opened; T4's anchor `[VERIFY]` is now
  discharged.
- **Discovered nothing** that splits the task — `tasks.md` "Discovered work"
  stays empty.
- **Carried forward (unchanged from T4):** Arelle's taxonomy cache must be
  pre-populated for T10's "no network fetch" guarantee — the anchor fixture, like
  the other fact fixtures, relies on the warm cache to extract offline.
- **Next:** `T6` — the PDF lane: `ingestion.elements.parse_elements` over Docling,
  the **sole `Element` producer**, with FY/section/page provenance. This opens the
  *prose* half of ingest (the firewall's other side) and brings the one-time
  Docling model download the plan flagged. Run `/implement T6`.
