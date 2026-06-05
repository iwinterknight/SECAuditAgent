---
spec: 2026-06-04-ingestion-parsing
stage: implement
report: 04-implement-T4
created: 2026-06-05
---

# Educator Report — IMPLEMENT · M1 Ingestion & parsing (T4 · XBRL extractor — Arelle to `XBRLFact`s)

> **How to read this.** Top-down: first *where* this task sits, then the
> *domain* it encodes (inline XBRL, contexts, period types, entity scoping,
> the transform, nil facts, duplicate taggings, restatements), then the
> *architecture* view, then the mandatory two-level **Code Walkthrough**
> (module → file → function → line). By the end you should be able to
> re-present every line of `ingestion/xbrl.py`, the new conftest fixtures, and
> the seven tests — and defend why each exists. This is the task where the
> system's central promise, *"numbers come only from XBRL"*, stops being a
> sentence in the constitution and becomes running code.

---

## 1. Where we are (orientation)

We just finished **T4** of **M1 (Ingestion & parsing)** — the first task that
*produces data*. T1 built the packaging skeleton; T2 defined the two typed
contracts (`Element`, `XBRLFact`); T3 wired the `config/` floor (paths, the
filing manifest, logging). **T4 is the first of the two ingestion producers**:
`ingestion.xbrl.extract_facts` reads a filing's inline-XBRL package and emits a
list of `XBRLFact`s — the machine-readable figures every numeric answer will be
grounded in. On the data-flow diagram (`docs/architecture.md` §4: ingest →
chunk → index → retrieve → agent → answer) this is the **left-most box, top
half**: the XBRL lane of ingest. Its sibling, the PDF lane (`ingestion.elements`,
T6), produces the *prose* the retriever searches; this lane produces the
*numbers* the calc tool will trust. The two lanes are kept physically apart on
purpose — that separation is the §1.2 firewall, and T4 is the half of it that
manufactures `XBRLFact`s. After T4 the system can, for the first time, hold the
true total assets of JPMorgan Chase for five fiscal years as exact `Decimal`s.

## 2. The domain in play (teach me)

This is the densest domain task in M1. Eight concepts converge. Take them in
order — each builds on the last.

### 2.1 Inline XBRL (iXBRL): a filing that is both a document and a database

A modern SEC 10-K is filed as **inline XBRL** — a single `.htm` file that is
*simultaneously* a human-readable web page and a machine-readable data set. The
prose and tables render in a browser; woven invisibly into that same HTML are
`<ix:…>` tags that mark up specific numbers as **facts**. When JPM's balance
sheet shows "Total assets $4,002,814" in a table, an `<ix:nonFraction>` tag
around that cell declares: *this is the concept `us-gaap:Assets`, for this
reporting context, in US dollars, scaled by 10⁶.* Two tag families matter:

- **`ix:nonFraction`** — a *numeric* fact (an amount, a count, a ratio). These
  become `XBRLFact`s.
- **`ix:nonNumeric`** — a *text* fact (the document type, the entity's legal
  name, a policy paragraph). Not a figure; we skip these.

Surrounding the instance are the **linkbases** — separate XML files that give
the facts meaning: the **schema** (`.xsd`, declares the company's custom
concepts), and the calculation / definition / label / presentation linkbases
(`_cal/_def/_lab/_pre.xml`). The instance plus its linkbases is the *XBRL
package*; on disk it's the accession folder we vendored, e.g.
`…/xbrl/0000019617-25-000270/` with one `jpm-20241231.htm` and its five
siblings.

### 2.2 The context: who, when, and along which axes

Every numeric fact points at a **context** — the XBRL object that answers three
questions about the number:

- **Entity** — which legal entity reports it (more in §2.4);
- **Period** — the instant or span it applies to (more in §2.3);
- **Dimensions** — optional *axes* that further qualify it (by business
  segment, by financial instrument, by legal entity, …).

Two facts of the same concept (say `us-gaap:Deposits`) differ *only* by their
context: one for 2024-12-31 consolidated, another for 2023-12-31, another for a
specific segment. The context is therefore the key that makes a bare concept tag
into a specific, locatable figure. Our job in T4 is to read each fact's context
and project it onto the flat fields of `XBRLFact` (`entity`, `period_type`,
`period_*`, `dimensions`).

### 2.3 Period type and the end-exclusive date trap

XBRL distinguishes two period shapes, and conflating them is a fidelity bug the
constitution explicitly forbids (§1.3 / architecture §10.2):

- **instant** — a balance-sheet "as of" figure. *Assets at 2024-12-31.*
- **duration** — an income-statement / cash-flow "for the period" figure. *Net
  income over 2024-01-01 … 2024-12-31.*

`XBRLFact` keeps them in separate fields (`period_instant` vs
`period_start`+`period_end`) and a model validator rejects any fact that blends
them. So far, so clean. The **trap** is in how Arelle stores the dates: it uses
the **end-exclusive** convention. A `<instant>2024-12-31</instant>` is stored
internally as **midnight on 2025-01-01** (the start of the next day); an FY2024
duration is stored as `2024-01-01 … 2025-01-01`. If you naively call
`.date()` you get `2025-01-01` for a balance that every human and every filed
table calls *December 31, 2024*. The fix is small but load-bearing: **subtract
one day** from the instant and from the duration's end (the start is inclusive
and kept as-is). T4's `test_period_date_fields_exclusive` pins exactly this — it
asserts `us-gaap:Assets` surfaces at `2024-12-31` and *never* at `2025-01-01`.

### 2.4 Entity scoping: the registrant is not its bank

Constitution §1.3 forbids conflating **JPMorgan Chase & Co.** (the consolidated
holding company, the SEC registrant, CIK `0000019617`) with **JPMorgan Chase
Bank, N.A.** (its principal bank subsidiary). Both appear in the *same* 10-K,
under the *same* CIK, with *different* numbers (regulatory capital, deposits).
XBRL distinguishes them not by the context's entity-identifier (that's the CIK
for both) but by a **dimension**: a fact scoped to the subsidiary carries an
explicit `dei:LegalEntityAxis` member whose name is the bank. So entity
resolution is: *default to consolidated; switch to the bank only when the
context carries that specific axis-member.* It is never inferred from prose,
never guessed — only read from the tagged member. Of FY2024's ~7,300 facts,
exactly 36 are the bank's; the other ~7,260 are consolidated.

### 2.5 The transform — and why we trust `fact.value`

An `ix:nonFraction` tag can declare a **scale** (`scale="6"` means "multiply the
displayed digits by 10⁶"), a **sign** (`sign="-"` flips it), and a **format**
(how the text "8,910" maps to a number). The filer writes "8,910" in a table
tagged `scale="6"`; the *true* value is 8,910,000,000. **Arelle applies all of
this for us** and exposes the final number as `fact.value` (a string,
`"8910000000"`). This is the single most important thing to trust correctly: we
parse `Decimal(fact.value)` directly and **never re-apply scale** — doing so
would multiply by a million twice. We verified this in exploration
(`InvestmentBankingRevenue` came back as `8910000000`, not `8910`). The value is
parsed as **`Decimal`, never `float`**, because float's binary rounding would
silently corrupt a figure that must exact-match the filing (§1.2).

### 2.6 Nil facts: absence is not zero

A filer can tag a concept as **`xsi:nil`** — "this line exists in the taxonomy
but has no value here." FY2024 does this for `us-gaap:CommitmentsAndContingencies`
(a balance-sheet placeholder line). A nil fact's value is the empty string, and
the cardinal rule is: **skip it; never write it as `0`.** Zero is a claim
("we have exactly nothing here"); nil is the *absence* of a claim. Coercing nil
to zero would fabricate a figure — precisely the corruption the firewall exists
to prevent. The same posture covers any value that won't parse as a `Decimal`:
log it and skip, never substitute a number.

### 2.7 Duplicate taggings and the dedup: one canonical fact per identity

Here is a subtlety that only surfaces against real filings, and it shaped the
implementation. **A filer routinely tags the same figure in several places** —
total assets might appear in the balance sheet, in a footnote, and in an MD&A
table, each with its own `ix:nonFraction`. Arelle returns each *tagging* as a
separate fact object. Worse, the same figure is sometimes tagged at **different
rounding precision** — Long-Term Debt at the million (`decimals="-6"` →
100,780,000,000) in one place and at the hundred-million (`decimals="-8"` →
100,800,000,000) in another. Raw, FY2024 yields 7,816 fact objects but only
7,296 *distinct* figures; the surplus are duplicate taggings.

These collisions all share a **`fact_id`** (`{filing}:{concept}:{context}:{unit}`
— the same concept, same context, same unit). The resolution: **collapse each
`fact_id` group to one canonical fact, keeping the most precise tagging**
(largest `decimals`; an exact `decimals=None` outranks every rounded sibling).
This is what every serious XBRL consumer (including the SEC's own viewer) does.
Crucially, we *guard fidelity while doing it*: if two **equally precise**
taggings disagreed on the numeric value, that's a genuine **inconsistent
duplicate** (a filer error) — we log it loudly rather than silently pick one. We
verified there are zero genuine conflicts in JPM's filings (the only apparent
ones were `9000000000` vs `9000000000.0`, numerically identical). After dedup,
`fact_id` is unique per filing — which is exactly what
`test_fact_ids_unique_per_filing` asserts.

### 2.8 Restatements: a prior year, reported twice, both kept

When a company **restates** a prior year (re-classifies or corrects it), the
restated figure appears as a *comparative* in a later filing. A 10-K income
statement shows three years, so FY2024's filing carries FY2022 net income, fees,
etc. — and some of those FY2022 numbers differ from what the *original* FY2022
filing reported. Concretely, `jpm:FeesAndCommissions1` for FY2022 was **4,233M
as first filed** and **6,581M as the FY2024 comparative** (a reclassification).
The fidelity rule (spec AC3): **keep both.** Because `fact_id` is prefixed with
`source_filing`, the two never collide — dedup operates *within* a filing, never
across filings. A later restatement is an *additional* provenance-distinct fact,
never an overwrite of the figure as first filed. `test_restated_fy2022_both_present`
proves exactly this.

### 2.9 The framework: Arelle

**Arelle** (`arelle-release==2.41.4`) is the open-source XBRL processor we lean
on. It does the genuinely hard work we would never want to reimplement: parsing
the inline-XBRL HTML, discovering and loading the linkbases, resolving the
us-gaap/dei taxonomy, building the context and unit objects, and — critically —
applying the scale/sign/format transform so `fact.value` is the final number.
We use a narrow slice of its API (`Cntlr` to load a model; `model.facts` to
iterate; per-fact `qname`/`value`/`decimals`/`unit`/`context`; per-context
period and dimension accessors). The alternative — hand-parsing iXBRL with an
XML library — was never viable: we'd be reimplementing the transform and
taxonomy resolution, the two places fidelity is easiest to get wrong. Arelle was
named in the plan's Risks, so it is a declared dependency, not a surprise.

## 3. The high-level view (architecture)

In the layer map (`docs/architecture.md` §3, imports flow downward only),
`ingestion` sits one level above the `config` floor and imports it only. T4 adds
the **XBRL producer** to that layer. The boundary after T4:

```
        ┌──────────────── config (the floor) ────────────────┐
        │  schema.py   XBRLFact (the contract, defined here)  │
        │  settings.py  paths + FILINGS join                  │
        └───────────▲─────────────────────────────▲───────────┘
                    │ imports config only          │ XBRLFact (constructed ONLY below)
                    │                              │
   accession dir ──▶│  ingestion.xbrl.extract_facts(dir, *, source_filing)  │──▶ list[XBRLFact]
   (one .htm +      │  ── the SOLE XBRLFact producer (the §1.2 firewall) ── │
    linkbases)      └──────────────────────────────────────────────────────┘
                                       ▲
                          Arelle loads instance + linkbases,
                          applies scale/sign/transform
```

- **Consumes:** an accession directory (resolved from `config.settings` by the
  caller) and a `source_filing` tag. Imports `config.schema` (for the contract)
  and Arelle. No upward imports; no PDF path.
- **Produces:** the **`XBRLFact`** §5 contract — and this module is the *only*
  place in the system that constructs one. That exclusivity *is* the firewall:
  numbers can only enter the system here, from tagged XBRL, never from the PDF
  lane or an LLM. (T8 will add a static test that enforces the "only here"
  property; T4 establishes it.)
- **Decision space:** for each Arelle fact, six resolutions — value, period,
  entity, dimensions, unit, decimals — plus two filters (numeric-only,
  non-nil/transformable) and one collapse (dedup). Each is a small, testable
  helper.

## 4. The drill-down (low level) — the two-level Code Walkthrough

### Module level

- **Module:** `ingestion` (the XBRL lane); `docs/architecture.md` §3/§4.
- **Role / data-flow position:** the top half of the left-most ingest box — the
  producer of machine-readable figures. Sits above `config`, below everything
  that consumes facts (index→DuckDB in M3, the calc tool in M5).
- **Boundary change:** adds one public entry point,
  `extract_facts(accession_dir, *, source_filing) -> list[XBRLFact]`, and makes
  `ingestion.xbrl` the **sole constructor** of the `XBRLFact` §5 contract.
  Dependency direction holds (imports `config` + Arelle only; nothing upward,
  nothing from the PDF lane).

### File level

**`src/ingestion/xbrl.py`** — the extractor (the whole task).

- `extract_facts(accession_dir, *, source_filing)` — the public entry point.
  Finds the instance, loads it with Arelle, iterates `model.facts`, keeps the
  numeric ones, resolves each into an `XBRLFact` (or skips it), dedups the
  result, logs a one-line summary, and returns the canonical list. Wraps the
  work in `try/finally` so the parsed model is always closed (the pipeline, T10,
  loads five in a row — leaked models would balloon memory).
- `_find_instance(accession_dir)` — returns the lone `*.htm` in the folder (the
  instance; its siblings are `.xsd`/`.xml` linkbases). **Fails closed** if
  there isn't exactly one — a corrupt package must error, not be guessed at
  (§1.5). Decouples the extractor from the manifest: hand it a directory and it
  finds the instance itself.
- `_precision(fact)` — a fact's precision as a sortable number: `decimals` if
  set, `+inf` when `decimals is None` (an *exact* value outranks any rounded
  one). The key the dedup sorts on.
- `_dedupe_facts(facts)` — groups by `fact_id`, keeps the most precise tagging
  per group, drops the coarser echoes. Guards fidelity: if equally precise
  taggings disagree on the *numeric* value (a real inconsistent duplicate), it
  logs a warning rather than hiding the conflict. (`Decimal` compares and hashes
  by value, so `9e9` and `9e9.0` count as one — only a true disagreement grows
  the set.)
- `_build_fact(model_fact, *, source_filing)` — resolves one Arelle numeric fact
  into an `XBRLFact`, or returns `None` (a skip) for the three un-representable
  cases. Returns `None` and *logs* for: a nil fact (§2.6), an unparseable value,
  or a forever-period fact. Otherwise composes the `fact_id` and constructs the
  contract. This is the **one place** an `XBRLFact()` is built.
- `_resolve_value(model_fact, *, concept)` — `Decimal(fact.value)`; the value is
  already transformed (§2.5) so we never re-scale. Catches a parse failure and
  returns `None` (skip), never `Decimal(0)`. Tested directly with junk inputs.
- `_resolve_period(context, *, concept)` — projects the context's period onto
  `(type, instant, start, end)`, applying the end-exclusive **-1-day**
  correction (§2.3). Returns `None` (skip) for a forever period (no
  instant/duration to record).
- `_resolve_entity_and_dimensions(context)` — one pass over the context's axes:
  the `dei:LegalEntityAxis` member is projected onto `Entity` (consolidated by
  default, bank-N.A. on the matching member) and **not** echoed into
  `dimensions`; every *other* axis is kept losslessly as
  `{axis-qname: member-qname}`. Handles typed dimensions too (their member's
  text value).
- `_resolve_unit(model_fact)` — builds the unit string from the fact's
  measure(s): `([USD],[])`→`"USD"`, `([USD],[shares])`→`"USD/shares"`,
  `([pure],[])`→`"pure"`.
- `_resolve_decimals(model_fact)` — the `decimals` attribute as an `int`, or
  `None` for `"INF"` (exact) and an absent attribute.

**`tests/conftest.py`** — three session-scoped fixtures (additive; the T1
"no `sys.path` manipulation" docstring and the T3 `settings`/`sample_filing`
fixtures are preserved).

- `xbrl_facts` — the FY2024 filing parsed **once** into `XBRLFact`s; the shared
  corpus for the six shape/entity/period tests. Parsing an instance is
  multi-second, so a session fixture pays it a single time.
- `fy2022_facts` — the FY2022 filing parsed once; paired with `xbrl_facts` so
  the restatement test can show a prior year surviving from both filings.
- `nil_numeric_concepts` — the set of concepts the FY2024 instance tags as *nil*
  numeric facts, read **straight from Arelle**. This is independent ground
  truth: sourcing the nil set from the model (not the extractor's own output)
  keeps `test_nil_and_untransformable_skipped` from grading the extractor against
  itself.

**`tests/unit/test_xbrl_extract.py`** — four checks on fact *shape and fidelity*
(exact digits are T5's job).

- `test_fact_fields_present` — every fact is fully populated and internally
  consistent: provenance tag, qualified concept, `Decimal` value, a known
  `Entity`, a unit, `decimals` an int-or-`None`, a `dimensions` dict, and period
  fields matching the period type.
- `test_fact_ids_unique_per_filing` — `fact_id`s are unique, i.e. the dedup
  collapsed every duplicate tagging to one canonical fact (§2.7).
- `test_nil_and_untransformable_skipped` — two halves: the real corpus (the
  nil `CommitmentsAndContingencies` is absent from output, and the nil set is
  non-empty so the test can't pass vacuously) **and** the resolver directly
  (`_resolve_value` returns `None` for `""`, `None`, `"—"`, `"n/a"` — a skip,
  never a fabricated `0`).
- `test_filing_fact_count_floor` — the extractor reads the filing's *thousands*
  of facts (`> 5000`; FY2024 has 7,296), not a silent handful — a catastrophic
  under-extraction (broken loader, wrong filter) fires here.

**`tests/unit/test_entity_period.py`** — three checks on the two fidelity axes
the firewall is most easily wrong about.

- `test_entity_always_set_and_distinct` — every fact has a known `Entity` (no
  silent default), both entities actually appear (the §1.3 split is exercised),
  and no fact keeps a `LegalEntityAxis` key in `dimensions` (the axis is
  projected to `entity`, not duplicated).
- `test_period_date_fields_exclusive` — instant and duration never co-populate,
  **and** the -1-day correction holds: `us-gaap:Assets` surfaces at `2024-12-31`
  and never `2025-01-01`; FY2024 net income spans `2024-01-01 … 2024-12-31`.
- `test_restated_fy2022_both_present` — `jpm:FeesAndCommissions1` for FY2022
  exists once in each filing, each tagged to its own `source_filing`, with
  distinct `fact_id`s and *different values* — a genuine restatement, both
  retained (§2.8).

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| The fact value | parse `Decimal(fact.value)` as-is | re-apply `scale`/`sign` ourselves | Arelle already transforms; re-scaling double-counts (§2.5) |
| Numeric type | `Decimal` | `float` | binary-float rounding corrupts exact-match fidelity (§1.2) |
| Period dates | subtract one day from instant + duration-end | use Arelle's stored datetimes directly | Arelle stores end-exclusive; raw `.date()` gives Jan-1-next, not the reported Dec-31 (§2.3) |
| Entity | project `dei:LegalEntityAxis` member onto `Entity`, drop that axis from `dimensions` | infer from prose / keep the axis in dimensions | §1.3 — read, never guess; entity is a field, not a duplicated dimension |
| Other dimensions | keep losslessly as `{axis: member}` | discard non-entity axes | a dimensional fact's full scope must survive for correct querying |
| Duplicate taggings | dedup per `fact_id`, keep the **most precise** | keep all / put `decimals` in `fact_id` | downstream wants one canonical figure per identity; unique `fact_id` is the acceptance gate (§2.7) |
| Inconsistent duplicates | log a warning, keep one | silently pick / hard-crash | surface a filer error without aborting extraction (§1.2) |
| Nil / unparseable | skip + log | coerce to `0` | absence is not zero; zero is a fabricated claim (§2.6) |
| Restatements | retain across filings (dedup within a filing only) | dedup across filings by concept+period | a later restatement must not overwrite the figure as first filed (§2.8 / AC3) |
| Instance discovery | glob the lone `*.htm`, fail closed otherwise | look the filename up in `FILINGS` | keeps the extractor decoupled from the manifest; the caller owns the join |
| Nil test ground truth | read the nil set straight from Arelle | trust the extractor's own output | an independent source can't let the test grade the code against itself |

## 6. Open threads & what's next

- **Taxonomy resolution / offline (carried forward to T10).** Arelle resolves
  the standard us-gaap/dei taxonomy through its HTTP cache; ours is populated
  (from exploration), so the tests run offline and fast. A *fresh* machine would
  fetch the taxonomy on first parse. T10's acceptance explicitly requires "no
  network fetch," so the pipeline task must pin Arelle to a pre-populated cache
  (or vendored taxonomy). Noted, not solved here — T4 is scoped to extraction.
- **No new `[RATIFY]`/`[VERIFY]` markers** opened. The plan's anchor-tag
  `[VERIFY in IMPLEMENT]` belongs to **T5** (the exact-match anchor test), which
  reads the 10 expected integers (Assets + NetIncome × 5 FY) and pins them — T4
  deliberately tested *shape*, leaving *digits* to T5, the cheap-eval gate and
  first seed of the M7 numeric truth set.
- **The firewall's other half** is still structural-only until **T8**: T4
  establishes "`XBRLFact` is constructed only in `ingestion.xbrl`"; T8 adds the
  static AST/import test that *enforces* it once the PDF lane (T6/T7) exists.
- **Discovered nothing** that splits the task — `tasks.md` "Discovered work"
  stays empty.
- **Next:** `T5` — anchor numeric truth: exact-match `us-gaap:Assets` (instant)
  and `us-gaap:NetIncomeLoss` (duration), consolidated, per fiscal year, against
  the filed values (10 assertions). Run `/implement T5`.
