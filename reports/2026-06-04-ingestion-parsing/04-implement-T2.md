---
spec: 2026-06-04-ingestion-parsing
stage: implement
report: 04-implement-T2
created: 2026-06-05
---

# Educator Report — IMPLEMENT · T2 The typed contracts (`config.schema`)

> **How to read this.** This is the lead's 360° companion to the second
> `/implement` of M1. T1 built the empty rooms; **T2 carves the two objects the
> whole system will pass around** — `Element` and `XBRLFact` — and pins down the
> handful of enums that make a fistful of fidelity rules (entity, period,
> element kind) into *types* the compiler and the validator can police. The
> report opens at the altitude of *what a "typed contract" is and why it lives
> in one shared place*, teaches the XBRL/financial domain each field encodes
> (instant vs duration, consolidated vs subsidiary, Decimal vs float,
> restatements), then drills into the mandatory two-level **Code Walkthrough**:
> the module boundary T2 drew, then every field, enum, and the period validator,
> line-presentable. Read top-to-bottom to finish able to defend *why the schema
> looks exactly like this* — because every field here is a fidelity decision,
> not a data-modelling convenience. Markdown is the source of truth; the sibling
> PDF is rendered by `reports/render.py`.

---

## 1. Where we are (orientation)

The **IMPLEMENT** stage continues with **T2 — `config/` schema: the typed
contracts**, the second of eleven M1 tasks and the one that *unblocks everything
else*. T1 made `config` and `ingestion` importable; T2 fills `config` with its
first real content: `src/config/schema.py`. On the roadmap (`docs/roadmap.md`)
we are still in M1 (the bottom of the chain); on the data-flow map
(`docs/architecture.md` §4) we are still left of the first arrow — but T2
produces the **vocabulary** that flows along every arrow downstream:

```
  ingestion (M1) ─► chunking (M2) ─► index (M3) ─► retrieval (M4) ─► agent (M5) ─► answer
     │                                                                              ▲
     └── emits Element ──────────────► (M2 consumes)                                │
     └── emits XBRLFact ─────────────► (M3/DuckDB + M5/calc consume) ───────────────┘
            ▲
   T2 defines BOTH of these types (in config.schema), so every box above
   speaks the same two nouns without importing each other.
```

Why this step mattered: a contract is *the agreement between layers*. Until
`Element` and `XBRLFact` exist as concrete types, the XBRL extractor (T4) has
nothing to return, the serializer (T9) has nothing to write, and the firewall
guard (T8) has no single `XBRLFact` definition to point at. T2 is small in lines
and enormous in leverage — it is the schema the next nine tasks are written
against.

## 2. The domain in play (teach me)

T2's domain is two things at once: the **engineering idea of a typed contract**,
and the **financial-reporting semantics** each field encodes. You need both,
because here they are the same decision — every field is a fidelity rule wearing
a type.

**What a "typed contract" is, and why it lives in `config`.** A contract is the
shape of the data that crosses a module boundary: what fields exist, their
types, their invariants. "Typed" means that shape is a real class the runtime
checks, not a loose `dict` everyone hopes is filled in correctly. We put both
contracts in `config.schema` — the lowest layer — for one structural reason
(architecture §5): if `Element` lived in `chunking` and `XBRLFact` in `index`,
then every layer that touches a figure would have to import a *sibling* layer
just to name the type, and the clean downward-only import graph (§1.6) would
collapse into a web. One shared schema module beneath everything means
`ingestion`, `chunking`, `index`, and `agent` all import their nouns from the
same floor, and never from each other.

**Why Pydantic v2 and not a plain `dataclass`.** A stdlib `@dataclass` gives you
the fields for free but checks *nothing* at construction — you could build an
`XBRLFact` with a `float` value, a missing entity, or an instant date on a
duration fact, and nothing would complain until a number was wrong in front of a
user. **Pydantic v2** validates at the boundary: types are coerced/checked, and
a `@model_validator` can enforce cross-field invariants (our period
exclusivity). Since the downstream stack (LangGraph M5, FastAPI M6) speaks
Pydantic anyway, the contracts are validated *and* native to the tools that
consume them. The cost — a third-party dependency — was named in the plan's
Risks and is the same library the rest of the system needs.

**The financial domain each field encodes** — this is the part worth real fluency:

- **Element kind (text / table / heading).** A 10-K is prose, dense tables, and
  section headers. M2 chunks each differently (a table becomes a table-to-text
  summary; a heading anchors a section). So "what kind of block is this" is a
  first-class enum, not a guess.
- **Provenance (fiscal_year, item, page).** The reason ingestion exists is so a
  downstream citation can say *"FY2024, Item 7, page 113."* Every Element carries
  its fiscal year, its 10-K **Item** (more below), and its page — lose any of
  these and the answer can't be grounded (§1.5, "no citation → no claim").
- **The 10-K Item.** A 10-K is legally structured into Items: Item 1 (Business),
  1A (Risk Factors), 7 (MD&A — management's narrative), 7A (market risk), 8
  (Financial Statements), etc. Neither parser emits Item boundaries, so `item`
  starts `unknown` and is stamped by a later deterministic pass (T7) — never
  guessed. The field exists now so T7 has somewhere to write.
- **Entity (consolidated vs the bank).** *The* classic 10-K fidelity trap: "JPMorgan
  Chase & Co." (the consolidated registrant, CIK 0000019617) is **not** "JPMorgan
  Chase Bank, N.A." (a subsidiary). Both appear in the same document with
  *different* numbers. So entity is an explicit enum on every fact (and every
  Element), defaulting to consolidated, and the subsidiary value is set only on a
  structural signal — never inferred from prose. The two enum members are exactly
  `JPMC_CONSOLIDATED` and `JPMORGAN_CHASE_BANK_NA`.
- **Period type — instant vs duration.** This is the XBRL concept most people
  miss. A **balance-sheet** figure (Total assets) is an *instant*: true *as of*
  one date (2024-12-31). An **income-statement** or **cash-flow** figure (Net
  income) is a *duration*: accumulated *over a span* (2024-01-01 .. 2024-12-31).
  Blending them — comparing an "as of" number with a "for the year" number —
  produces nonsense, so the XBRL period type is preserved as a two-value enum,
  and the model validator (below) makes it *impossible* to build a fact that
  carries both an instant date and a duration range.
- **`value: Decimal`, never `float`.** Financial figures must match the filed
  value *exactly*. `float` is binary and can't represent many decimal fractions
  precisely (`0.1 + 0.2 != 0.3`); a cent of drift on a billion-dollar line is a
  fidelity failure. `Decimal` stores the exact base-10 number, and serializes to
  a canonical string (T9), so AC4's exact-match anchor test is even *possible*.
- **`unit`, `decimals`, `dimensions`.** A figure isn't a number alone: `unit`
  says what it's denominated in (`USD`, `USD/shares`, `shares`, `pure` for a
  ratio); `decimals` is XBRL precision metadata; `dimensions` holds any remaining
  reporting axes (segment, business unit) as `axis → member` pairs so a
  dimensional breakdown loses nothing. The consolidation axis feeds `entity`;
  every *other* axis lands in `dimensions`.
- **Identity & restatements (`fact_id`, `source_filing`).** Each `XBRLFact` gets a
  stable `fact_id` of `{source_filing}:{concept}:{context_ref}:{unit}`. The XBRL
  `context_ref` already encodes entity + period + every dimension, so that tuple
  is unique *by XBRL semantics* (T4 guards it with a uniqueness test rather than
  trusting it). `source_filing` (the accession folder) is what makes
  **restatements** survivable: the FY2022 Net income as *first filed* in the 2022
  10-K and as *restated* in the 2024 10-K share concept/period/entity but differ
  in `source_filing`, so both are retained and distinguishable (AC3). M1 only
  *preserves* this; choosing which to show is a downstream rule (§1.3).

**The firewall connection (why "defined once" is the whole point).** Constitution
§1.2 — "numbers come only from XBRL" — is enforced not by reviewer vigilance but
by *type ownership*: `XBRLFact` is defined in exactly one place (`config.schema`)
and constructed in exactly one place (`ingestion.xbrl`, T4). T2 establishes the
first half — the single definition site. The firewall test (T8) later asserts the
PDF path never even references the type. None of that is checkable unless T2
first makes `config.schema` the sole home; that is why T2's acceptance check is a
*location* test, not just a "does it parse" test.

## 3. The high-level view (architecture)

Where T2 sits in the layer map (`docs/architecture.md` §3, imports downward
only) and which §5 contracts it produces:

```
   higher layers (M2+)  ──────────── import their nouns from ────────────┐
                                                                         │
   ┌──────────────────────────── config (the floor) ───────────────────▼─┐
   │  config.schema   ◄── T2 lands here                                   │
   │     Element          (→ produced by ingestion, consumed by chunking) │
   │     XBRLFact         (→ produced by ingestion, consumed by index/calc)│
   │     ElementKind · PeriodType · Entity   (the fidelity enums)         │
   │  config.settings / config.logging   ◄── still empty (arrive in T3)   │
   └──────────────────────────────────────────────────────────────────────┘
                          │ imports
                          ▼
              pydantic (external, v2)   ── the only thing config.schema imports
```

**What changed at the module boundary.** Before T2, `config` was a docstring.
After T2, `config.schema` **exports two of architecture §5's seven typed
contracts** — `Element` and `XBRLFact` — plus the three enums. The import
direction stays legal (§1.6): `config.schema` imports only the stdlib and
`pydantic`; it imports *nothing* from `ingestion` or above. No producer code yet
(T4/T6 do that) — T2 ships the *shape*, validated, and the proof that the shape
lives in the right place.

## 4. The drill-down (low level) — the two-level Code Walkthrough

The mandatory core (Constitution §2): module level, then file level.

### 4a. Module level

- **Module touched:** `config` — specifically the new `config.schema` submodule.
- **Role & data-flow position:** `config` is the shared-contracts floor beneath
  every layer (§3); `config.schema` is where the cross-boundary *types* live.
  T2 produces two of the seven §5 contracts (`Element`, `XBRLFact`).
- **Inputs / outputs / contracts at the boundary:** no functions, no runtime
  data flow yet. The deliverable is *type definitions*: `Element`, `XBRLFact`,
  `ElementKind`, `PeriodType`, `Entity`, importable from `config.schema`, with
  `XBRLFact`'s period invariant enforced at construction.
- **Dependencies introduced:** `pydantic` (v2) is now imported at runtime by
  `config.schema` (declared in T1's manifest, locked in `uv.lock`, installed into
  the venv this task). No upward import; the §1.6 graph is intact.
- **§5 contracts referenced by name:** **`Element`** (ingestion → chunking) and
  **`XBRLFact`** (ingestion → index/DuckDB + calc tool). The other five contracts
  (`Chunk`, `RetrievedContext`, `AgentState`, `Citation`, `TelemetryEvent`)
  belong to later milestones and are untouched.

### 4b. File level

**`src/config/schema.py`** — the contracts and their enums. Walk it top to bottom:

- **`ElementKind(StrEnum)`** — `TEXT` / `TABLE` / `HEADING`. A `StrEnum` (new-ish
  stdlib, clean on 3.13) so each member *is* its lowercase string value —
  convenient for JSONL serialization (T9) and DuckDB (M3) where the value lands as
  plain text. Exists because M2 treats the three kinds differently.
- **`PeriodType(StrEnum)`** — `INSTANT` / `DURATION`. The two-value enum that keeps
  balance-sheet "as of" figures from blending with income-statement "for the
  period" figures. The docstring states the rule so a future reader meets the
  domain at the type.
- **`Entity(StrEnum)`** — `JPMC_CONSOLIDATED` / `JPMORGAN_CHASE_BANK_NA`. The
  entity firewall as a type: the consolidated registrant is never silently the
  subsidiary. The enum value equals the member name (an explicit, greppable
  token) because it travels into serialized output and DuckDB filters.
- **`Element(BaseModel)`** — one parsed PDF unit. Fields: `element_id` (stable
  `{accession}:{page}:{ordinal}`), `kind`, `text` (for tables, a
  structure-preserving serialization M2 will summarize), `fiscal_year`, `item`
  (`"unknown"` until T7 stamps it), `page` (1-based), `entity` (**defaults**
  `JPMC_CONSOLIDATED` — the only field with a default that matters, because M1
  stamps every Element consolidated), `source_filing` (accession), `ordinal`
  (reading-order index, also the serializer's total-order sort key in T9). It
  exists so the PDF path (T6) has a typed thing to emit and chunking has a typed
  thing to consume.
- **`XBRLFact(BaseModel)`** — one machine-readable figure. Fields: `fact_id`
  (the unique tuple), `entity`, `concept` (qualified tag like `us-gaap:Assets`),
  `period_type`, the three period date fields (`period_instant`,
  `period_start`, `period_end`, all `date | None`), `value: Decimal` (the
  fidelity-critical choice), `unit`, `decimals` (`int | None`, precision
  metadata), `dimensions` (`dict[str,str]` via `Field(default_factory=dict)` so
  each instance gets its own dict — no shared-mutable bug), and `source_filing`.
  It is the *sole* numeric contract, and (from T4 on) constructed in only one
  module.
- **`XBRLFact._enforce_period_exclusivity` (`@model_validator(mode="after")`)** —
  the cross-field invariant. After the fields are set, it checks: an `instant`
  fact must have `period_instant` set and `period_start`/`period_end` **unset**;
  a `duration` fact must have start **and** end set and `period_instant`
  **unset**. Any violation raises `ValueError` at construction. This is the §1.3 /
  architecture §10.2 "never blend period types" rule made unbreakable: you
  *cannot* hold a blended fact in memory, so one can never reach the stream.

**`tests/unit/test_contracts_location.py`** — the acceptance, two tests:
- **`test_types_defined_in_config`** (the *named* AC8 acceptance) — for each of the
  five types, asserts `typ.__module__ == "config.schema"`. This proves not just
  that the names *import* from `config.schema`, but that they are **defined**
  there (a type re-exported from `ingestion` would have a different
  `__module__`). That is the single-home guarantee the firewall (§1.2) and the
  downward-only rule (§1.6) rest on.
- **`test_period_exclusivity_enforced`** — constructs a valid instant and a valid
  duration (both succeed), then asserts a period-blended construction **raises**
  in each direction. *Why this test is here and not only in T4:* a no-op validator
  would still pass T4's corpus tests (real filed facts are well-formed), so the
  validator's *rejection* behaviour would go unproven. §4.4 says test the
  behaviour where you introduce it — the validator is introduced in T2, so its
  rejection is proven in T2. (This is distinct from T4's
  `test_period_date_fields_exclusive`, which asserts every *real* fact conforms.)

**The check, run verbatim:**

```
tests/unit/test_contracts_location.py::test_types_defined_in_config PASSED   [ 50%]
tests/unit/test_contracts_location.py::test_period_exclusivity_enforced PASSED [100%]
============================== 2 passed in 1.94s ==============================
```

The named acceptance check
(`test_contracts_location.py::test_types_defined_in_config`) **passes**; the
period-validator companion passes too. T2 touches none of
chunking/retrieval/agent/tools, so the §4.3 cheap-eval tier is **n/a**.

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| Contract modelling | **Pydantic v2 models** | stdlib `@dataclass` | Boundary validation + cross-field invariants; native to the M5/M6 stack |
| Where types live | **`config.schema` (one floor)** | Each type in its consuming layer | One shared home keeps the §1.6 import graph downward-only; one home for `XBRLFact` = the §1.2 firewall is checkable |
| `value` type | **`Decimal`** | `float` | Exact-match numeric fidelity (§1.2); no binary-float drift |
| Enum base | **`StrEnum`** | `Enum` / bare strings | Member *is* its string value → clean JSONL/DuckDB serialization, still type-checked |
| Period modelling | **Type enum + exclusivity validator** | Free-form date fields | Makes blending instant/duration *impossible to construct* (§1.3) |
| `dimensions` default | **`Field(default_factory=dict)`** | `= {}` literal | Each instance gets its own dict — no shared-mutable aliasing |
| Period-validator test | **In T2 (`test_contracts_location.py`)** | Only T4's corpus test | A no-op validator passes corpus tests; rejection must be proven where introduced (§4.4) |
| `config/__init__.py` re-export | **Left untouched** | Re-export the types from the package root | Not in T2's Files list; `from config.schema import …` is the contract — no scope creep |

## 6. Open threads & what's next

**Nothing deferred from T2 itself** — the contracts are complete and validated.
Forward pointers:

- **`item` is `unknown` until T7.** The field exists and is typed; the Item-
  boundary stamping pass (T7) fills it. Until then every Element legitimately
  carries `item="unknown"`.
- **`XBRLFact` has a definition site but no constructor yet.** T2 fixes *where*
  the type lives; **T4** makes `ingestion.xbrl` its sole producer, and **T8** then
  proves the PDF path never constructs one. The firewall is a three-task arc;
  T2 is step one.
- **`config.settings` / `config.logging` are still empty.** T3 lands the single
  `pydantic-settings` object (the `FILINGS` accession↔FY table, corpus paths) and
  the logging skeleton — the next task, and the one that gives T4/T6 their paths.
- **Heavy parser deps still not installed.** Only `pydantic` was added to the venv
  (schema.py needs nothing more). Arelle/Docling install on demand when T4/T6
  import them.

**Next SDD step:** `/implement T3` — `config.settings` + logging. I will **not**
auto-invoke it; that's the lead's call. The spec's `status` is already
`implement` and stays there.
