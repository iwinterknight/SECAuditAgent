---
spec: 2026-06-04-ingestion-parsing
status: plan
created: 2026-06-04
---

# Plan: M1 — Ingestion & parsing (Elements + XBRLFacts from the JPM 10-Ks)

## Approach

M1 is the first application code in the repo and the bottom of the dependency
chain. It turns each of the five vendored JPMorgan Chase & Co. 10-K filings
into **two independent, provenance-tagged streams** — `Element` (parsed PDF
units) and `XBRLFact` (machine-readable figures) — plus the shared `config/`
schema, settings, and logging skeleton every later module imports. The design's
single dominant constraint is the fidelity firewall (Constitution §1.2): the
two streams are produced by **two separate code paths that share no number**.
The PDF path emits only `Element`s; the XBRL path emits only `XBRLFact`s; the
`XBRLFact` type is constructed in exactly one module. That separation makes
"numbers come only from XBRL" true *by construction* and checkable by an
import/ownership test, not by reviewer vigilance. The firewall is about **type
ownership, not digit absence** — an `Element`'s table text legitimately contains
digits (it is the rendered table); what the PDF path never contains or
constructs is an `XBRLFact`. The firewall test asserts that ownership, not the
absence of numerals.

For the **XBRL path** I propose **Arelle** (`arelle-release`) — the SEC's
de-facto reference XBRL processor. The keystone risk in numeric extraction is
the inline-XBRL transform: an `ix:nonFraction` value carries `scale` (e.g.
`scale="6"` → the displayed figure is in millions) and `sign` attributes plus a
format transform, and its context resolves entity + period + dimensions. Getting
any of those wrong silently corrupts every figure. Arelle implements the full
iXBRL transform registry, context/unit resolution, and dimensional model.
Rejected: **py-xbrl** (lighter, but I'd be betting financial fidelity on a
less-exercised transform implementation) and **raw lxml** over the `ix:` tags
(hand-rolling scale/sign/format is precisely the error surface §1.2 exists to
remove).

For the **PDF path** I propose **Docling** (IBM) for parsing PDFs into a
structured document model with reading order, page numbers, and **table cell
structure**. Because the numbers come from XBRL, M1's PDF parse does *not* need
perfect numeric table extraction — but it must preserve table *structure* well
enough for M2 to build faithful table-to-text summaries, and Docling's table
model is the strongest on dense financial tables. Rejected: **Unstructured**
(comparable element partitioning, weaker table-structure fidelity on 10-K
tables) and **PyMuPDF/`fitz`** (pure-Python, fast, no model download, but emits
flat text with weak table structure — it would push table reconstruction onto
M2). The cost of Docling is a one-time layout/table **model download** on first
run, a real tension with the "offline rebuild" goal (architecture §7) that the
Risks section addresses. Neither parser detects 10-K **Item** boundaries
(Item 1, 1A, 7, 7A, 8…); that is a deterministic post-parse pass that scans the
parsed heading Elements, finds the Item headers, and stamps each Element with
the Item it falls under — never guessing (an undetected boundary stamps
`Item = unknown` and logs, rather than mis-attributing). On **Element entity**:
M1 stamps every Element `JPMC_CONSOLIDATED`. The spec's "where determinable"
clause is honest about the limit — narrative prose carries no reliable,
deterministic subsidiary-scope signal at this layer (unlike an XBRL context's
explicit legal-entity dimension), so subsidiary-scoping of *narrative* is
deferred to a later module rather than inferred here. "Where determinable" for
Elements in M1 therefore resolves to consolidated; the rich entity
determination happens on the fact stream, where the signal is structural.

For the **contracts and config**, `Element` and `XBRLFact` are **Pydantic v2**
models in `config/schema.py`, with enums for the fidelity-load-bearing fields
(`ElementKind`, `PeriodType = instant|duration`, `Entity`). Pydantic validates
at the boundary (entity is always set, period type is one of two values, value
is numeric) and is the type system the downstream stack (LangGraph M5, FastAPI
M6) uses anyway; rejected stdlib `@dataclass` (zero-dep but no boundary
validation, which the fidelity rules want). Settings are a single
**pydantic-settings** `Settings` object (Constitution §1.7) exposing corpus
paths, the vendored-XBRL root, the gitignored derived-output root, and log
level — no `os.getenv` in business code, no hardcoded absolute paths. The
PDF↔accession↔FY join lives in **one** authoritative structure on `Settings`: an
ordered `FILINGS` table of `(accession, fiscal_year, pdf_filename,
xbrl_instance)` rows. The PDFs are named by period-end date
(`jpm-20241231.pdf`) while `source_filing` and the derived paths are keyed by
**accession** (`0000019617-25-000270`); that mismatch is resolved in exactly one
place — `pipeline.run()` reads `FILINGS` — and the filename date is **never**
independently re-parsed for FY anywhere, so the two can't silently disagree
(a §1.5-style single-source-of-truth discipline applied to provenance). Because
M1 is the first code, it also lands the **packaging manifest**: a
`pyproject.toml` (PEP 621) with a **src-layout** so `config` and `ingestion`
import cleanly under an editable install; proposed backend **hatchling** +
**uv** for lock/install (fast, reproducible, lockfile-based), with plain
`pip`+`requirements.txt` and Poetry as the named alternatives. The existing
`reports/requirements.txt` (doc-tooling for the renderer) stays self-contained
and is *not* folded into the app manifest — M1 owns app deps, not a renderer
reorg.

Finally, M1 carries the **doc-promotions** the spec already flagged as landing
"in the same change": ratifying the Constitution §1.3 restatement default
(remove `[RATIFY]`), and refining architecture §7/§2/§9 from "XBRL pulled from
EDGAR into a gitignored path" to "iXBRL packages vendored under
`data/SEC/10-K Filings/xbrl/` (LFS), read locally." The restatement rule itself
is only *preserved* here, not *applied*: every fact is tagged with its source
accession, so the FY2022 figure as originally filed and as later restated are
both present and distinguishable — downstream picks which to use.

## Data & Schema Changes

Two **new** typed contracts in `config/schema.py` (architecture §5 owns the
intent; this plan ratifies the field lists):

**`Element`** — one parsed PDF unit.
| field | type | notes |
|---|---|---|
| `element_id` | `str` | stable id: `{accession}:{page}:{ordinal}` |
| `kind` | `ElementKind` enum | `text` / `table` / `heading` |
| `text` | `str` | plain text; for tables, a structure-preserving serialization (e.g. cell grid / HTML) M2 can summarize |
| `fiscal_year` | `int` | e.g. 2024 |
| `item` | `str` | 10-K Item/section, e.g. `Item 7`, `Item 1A`; `unknown` if boundary undetected |
| `page` | `int` | 1-based page in the source PDF |
| `entity` | `Entity` enum | default `JPMC_CONSOLIDATED`; `JPMORGAN_CHASE_BANK_NA` only where determinable |
| `source_filing` | `str` | accession folder, e.g. `0000019617-25-000270` |
| `ordinal` | `int` | reading-order index within the filing |

**`XBRLFact`** — one machine-readable figure.
| field | type | notes |
|---|---|---|
| `fact_id` | `str` | stable id `{source_filing}:{concept}:{context_ref}:{unit}`. The XBRL `context_ref` already encodes entity + period + every dimension, so the tuple is **unique per fact** by XBRL semantics (two facts sharing concept+context+unit would be an invalid duplicate). A uniqueness test guards this rather than trusting it. |
| `entity` | `Entity` enum | from the context's identifier + consolidation dimension; default consolidated registrant (CIK 0000019617) |
| `concept` | `str` | qualified tag, e.g. `us-gaap:Assets` |
| `period_type` | `PeriodType` enum | `instant` / `duration` |
| `period_instant` | `date \| None` | set when `instant` |
| `period_start`, `period_end` | `date \| None` | set when `duration` |
| `value` | `Decimal` | post-transform numeric value (scale + sign applied) |
| `unit` | `str` | resolved unit ref, e.g. `USD`, `USD/shares`, `shares`, `pure` |
| `decimals` | `int \| None` | XBRL `decimals` attribute (precision metadata) |
| `dimensions` | `dict[str, str]` | remaining axis→member pairs, so dimensional facts lose nothing |
| `source_filing` | `str` | accession folder the instance was parsed from |

`Decimal` (not `float`) for `value` — exact-match numeric fidelity (§1.2)
forbids binary-float drift.

**Serialized derived form.** Both streams serialize to **JSONL** under a
**gitignored** derived root — `data/derived/ingestion/elements/{accession}.jsonl`
and `data/derived/ingestion/facts/{accession}.jsonl` — one object per line,
inspectable and diffable. Rejected **Parquet** for facts (columnar, DuckDB-
native, attractive — but the columnar fact store is M3's job; M1 stays neutral
and inspectable). Source corpus is **read-only** (§1.8): the pipeline writes
only under `data/derived/` and never mutates `data/SEC/`. `data/derived/` is
added to `.gitignore`.

**Serialization invariants** (what AC7's *byte-identical* claim actually rests
on — named so a later reader can't weaken them):
- **Rows sorted by a total key** — facts by `fact_id` (unique, total order),
  Elements by `ordinal` (unique reading-order index). Restated comparatives
  (AC3) share `(concept, period, entity)` but differ in `source_filing`/
  `context_ref`, so `fact_id` still totally orders them.
- **Object keys emitted in a fixed order** (`json.dumps(..., sort_keys=True)`).
- **`Decimal` → canonical string** (no binary-float, no scientific-notation
  drift); **dates → ISO-8601** (`YYYY-MM-DD`); **`\n` line endings**, UTF-8,
  no trailing whitespace.

No existing store schema changes (no Qdrant/DuckDB yet — those are M3).

## Interface / Contract Changes

All new; nothing pre-existing to break. The module boundaries created:

- `config.schema` — exports `Element`, `XBRLFact`, `ElementKind`,
  `PeriodType`, `Entity`. **Consumed by** ingestion now; chunking/index/calc
  later. This is the only place `XBRLFact` is *defined*.
- `config.settings` — exports a `Settings` instance (`get_settings()`); exposes
  `corpus_pdf_dir`, `xbrl_dir`, `derived_dir`, `accession_to_fy` map, `log_level`.
- `config.logging` — `configure_logging()` / module-level `getLogger`
  convention (Constitution §3); no `print`.
- `ingestion.elements` — `parse_elements(pdf_path, *, fiscal_year, source_filing) -> list[Element]`. The **only** producer of `Element`. Imports `config` only.
- `ingestion.xbrl` — `extract_facts(accession_dir, *, source_filing) -> list[XBRLFact]`. The **only** producer of `XBRLFact`. Imports `config` only. Constructs `XBRLFact` and nothing else — the structural firewall.
- `ingestion.sections` — `assign_items(elements) -> list[Element]`. Pure function over Elements; the Item-boundary pass. No number handling.
- `ingestion.serialize` — `write_jsonl` / `read_jsonl` for both types.
- `ingestion.pipeline` — `run(accessions: list[str] | None = None) -> None`, CLI via `python -m ingestion.pipeline`. The **only** place the PDF↔accession↔FY join is resolved (reads `Settings.FILINGS`). Contract: `None` ⇒ all five filings; an explicit list runs that subset; an **unknown accession is a hard error** (fail loud, never silently skip — a typo must not look like success). Orchestrates parse → extract → serialize per filing.

**Import direction (Constitution §1.6):** `ingestion → config` only; `config`
imports nothing above it. `config` and `ingestion` are new top-level modules but
both are already named in architecture §3 and authorized by the spec, so neither
is an unspecced module. No upward import is introduced.

## Sequencing

Linear; each step ≈ one task in `tasks.md`.

1. **Packaging + skeleton.** `pyproject.toml` (PEP 621, py3.13, src-layout),
   dependency declarations, editable install verified (`import config` works).
   Empty `src/config/` and `src/ingestion/` packages.
2. **`config/` contracts + settings + logging.** `schema.py` (the two Pydantic
   models + enums), `settings.py` (pydantic-settings object, paths, accession↔FY
   map), `logging.py`. This unblocks everything else.
3. **XBRL extractor.** `ingestion/xbrl.py` over Arelle: load each accession's
   instance + linkbases, walk facts, resolve context (entity + period type +
   dimensions) and unit, apply the iXBRL transform, emit `XBRLFact`s.
4. **PDF parser + provenance.** `ingestion/elements.py` over Docling: parse to
   Elements with page + kind + FY + entity-default; then `ingestion/sections.py`
   stamps the 10-K Item per Element.
5. **Serialize + pipeline CLI.** `ingestion/serialize.py` + `ingestion/pipeline.py`;
   `python -m ingestion.pipeline` rebuilds both streams for all five filings into
   the gitignored derived dir.
6. **Tests** (the cheap-eval anchor test + provenance/firewall/entity-period/
   rebuild/contract-location tests).
7. **Doc-promotions.** Ratify Constitution §1.3 (`[RATIFY]` removed); refine
   architecture §7/§2/§9 (vendored XBRL supersedes EDGAR-pull); fix the dangling
   `architecture §6.7` citation in the spec (the "update docs in the same change"
   obligation is **Constitution §6 item 7**, not an architecture §6.7 — there is
   none). Roadmap M1 row flips to `done` at EVALUATE, not here.

## Edge Cases

- **iXBRL scale/sign** — value must have `scale` (×10ⁿ) and `sign` applied;
  Arelle does this. A fact whose transformed value can't be resolved is logged
  and skipped, never written with a raw/un-transformed number.
- **Nil facts** (`xsi:nil="true"`) — skipped, not written as value `0`/`null`.
- **Dimensional facts** (segment/business-unit breakdowns) — retained; the
  consolidation axis feeds `entity`, all other axes go into `dimensions` so
  nothing is dropped or flattened.
- **Entity dimension absent** — default `JPMC_CONSOLIDATED`; `*_BANK_NA` is set
  **only** on an explicit legal-entity dimension member. Never inferred from prose.
- **Period date-field exclusivity** — an `instant` fact has `period_instant`
  set and `period_start`/`period_end` both `None`; a `duration` fact has the
  reverse. A duration carrying a stray `period_instant` is the period-blending
  §1.3 forbids; an invariant test asserts the pairing on every fact.
- **Restated comparative** — same `(concept, period, entity)` as an original
  fact but different `value`/`source_filing`: both kept, no dedup, no "last
  wins" (AC3). Distinguishable by `source_filing`.
- **Undetected Item boundary** — Element stamped `item = unknown` + warning;
  never mis-attributed to a neighbouring Item.
- **Non-USD / ratio / per-share units** — `unit` preserves whatever the unit ref
  resolves to (`USD/shares`, `shares`, `pure`); not coerced to `USD`.
- **Query/period with no fiscal year** — N/A at M1 (a query concern, M4+); the
  FY is always known here from the accession↔FY map.
- **Re-run determinism** — a second `pipeline.run()` over unchanged source
  produces byte-identical JSONL (stable ids + sorted output); AC7.

## Test Strategy

Per Constitution §4. M1 is **ingestion** — below chunking/retrieval/agent — so
the §4.2 eval-regression gate is **N/A** (no baseline to move). But the cheap
deterministic exact-match-numeric tier (§4.3) is the fidelity anchor and is
authored here. All tests are `[new]` (first code). Run:
`python -m pytest tests/unit -q`.

**Fast vs corpus-backed split** (keeps the per-implement run *cheap*, §4.3): the
expensive parse/extract runs **once** via a session-scoped fixture that invokes
`pipeline.run()` (or reuses already-built derived JSONL); every field/anchor/
entity/uniqueness test then **reads the serialized derived streams** — fast,
no re-parse. Pure-code tests (firewall, contract-location, packaging, section
logic over a checked-in mini heading-fixture) need no corpus at all. Only
`test_pipeline_rebuild.py` re-invokes parsing end-to-end; it is marked
`@pytest.mark.slow` and excluded from the default per-implement run.

| AC | Test (all `[new]`) | Proves |
|---|---|---|
| AC1 Elements + provenance | `test_elements_provenance.py::test_every_element_has_provenance` | each Element across all 5 filings has FY + Item + page + kind |
| AC1 Item correctness | `test_elements_provenance.py::test_known_elements_land_in_right_item` | pinned anchors: an MD&A Element is `Item 7`, a financial-statements Element is `Item 8` — Item is *right*, not merely present |
| AC1 Unknown-Item path | `test_sections.py::test_missing_header_yields_unknown` | over a garbled-header mini-fixture, affected Elements get `unknown`, never the previous Item's label (no mis-attribution) |
| AC2 Facts + fields | `test_xbrl_extract.py::test_fact_fields_present` | every `XBRLFact` has entity/concept/period(+dates)/value/unit/source |
| AC2 Id uniqueness | `test_xbrl_extract.py::test_fact_ids_unique_per_filing` | `len(set(fact_ids)) == len(facts)` per filing — no silent id collision |
| AC2 Nil / un-transformable skipped | `test_xbrl_extract.py::test_nil_and_untransformable_skipped` | a known `xsi:nil` fact is **absent** from output, never coerced to `0`/`null`/raw (§1.2) |
| AC2 Non-degenerate volume | `test_xbrl_extract.py::test_filing_fact_count_floor` + `test_elements_provenance.py::test_element_count_floor` | each filing emits `> N` facts/Elements — catches a whole-filing extraction failure the field-level tests miss |
| AC3 Restatements retained | `test_entity_period.py::test_restated_fy2022_both_present` | FY2022 figure from the 2022 *and* 2024 filings both present, distinct by `source_filing` |
| **AC4 Cheap eval anchor** | `test_xbrl_anchors.py::test_total_assets_and_net_income_exact` | **exact-match**: `us-gaap:Assets` (instant) + `us-gaap:NetIncomeLoss` (duration), consolidated, per FY, equal the filed XBRL value (10 assertions = 2 metrics × 5 FY) |
| AC5 Numbers only from XBRL | `test_firewall.py::test_element_path_never_constructs_xbrlfact` | structural **type-ownership**: no symbol in `ingestion.elements`/`.sections` references `XBRLFact`; `XBRLFact` defined only in `config.schema`. (Not a digit-grep — Element text legitimately has digits.) |
| AC6 Entity explicit | `test_entity_period.py::test_entity_always_set_and_distinct` | every fact has an `entity`; consolidated ≠ N.A. |
| AC6 Period exclusivity | `test_entity_period.py::test_period_date_fields_exclusive` | `instant` ⇒ only `period_instant`; `duration` ⇒ only `period_start`/`period_end`; never both (§1.3) |
| AC7 Rebuild from committed source | `test_pipeline_rebuild.py::test_deterministic_and_gitignored` `@slow` | re-run is byte-identical; output path under gitignored `data/derived/`; no live fetch |
| AC8 Contracts in `config/` | `test_contracts_location.py::test_types_defined_in_config` | `Element`/`XBRLFact` import from `config.schema`; not from `ingestion` |
| AC8 Packaging smoke | `test_packaging.py::test_config_and_ingestion_importable` | editable src-layout install works — `import config`, `import ingestion` resolve under the test runner |

(All under `tests/unit/`.)

- **Cheap eval tier (§4.3):** `test_xbrl_anchors.py` *is* the exact-match
  numeric-vs-XBRL check. Its 10 anchor values (Total assets + Net income per FY)
  also **seed the eval numeric truth set** (M7). The expected integers are
  pinned in the test, marked `[VERIFY in IMPLEMENT against the instance]` —
  `us-gaap:Assets` / `us-gaap:NetIncomeLoss` are taxonomy-stable across
  2021→2025, confirmed during IMPLEMENT. **Fallback** if a tag doesn't resolve
  identically for some FY: a per-FY `{fiscal_year: concept_tag}` override map in
  the test fixture, so the anchor design degrades gracefully instead of blocking.
- **Golden-set entries:** **none** — M1 is not a retrieval/agent feature; the
  golden set proper is M7 (§4.4). The anchor truth above is the first seed.
- **Heavy eval tier (§4.3):** **N/A** for M1 (no LLM-judge / re-embedding
  surface). Named for completeness; nothing queued.
- **UI manual verification:** N/A until M9.

## Risks

**(a) Constitution tensions.**
- **§1.2 numbers-from-XBRL** — *complies by construction*: `XBRLFact` is
  defined and constructed only in the XBRL path; the firewall test enforces it.
- **§1.1 fidelity** — *complies*: the anchor exact-match test guards extraction
  against scale/sign/transform bugs.
- **§1.3 entity/period** — *complies*: entity from the XBRL context's
  consolidation dimension (default consolidated registrant), never prose;
  period type preserved as an enum end to end; restatements retained + source-
  tagged. This plan also *ratifies* the §1.3 `[RATIFY]` default (original filing
  for FY N) — a Constitution edit, lead-approved per §7, landed as a doc task.
- **§7 process exception (named, not hidden)** — that §1.3 ratification rides
  in M1's change rather than its own Constitution-amendment spec. This is a
  deliberate exception, justified because it only *resolves a pre-existing
  `[RATIFY]` marker* the lead already approved (spec 2026-06-04), with **no
  change to the principle's substance** — §7's "spec + lead approval" bar is met
  by the recorded ratification; a separate spec for a marker-removal would be
  ceremony. Flagged here so the lead can veto the bundling if they'd rather it
  stand alone.
- **§1.6 layers** — *complies*: `ingestion → config` only; no upward import;
  both modules pre-named in architecture §3.
- **§1.7 settings** — *complies*: one pydantic-settings object; no `os.getenv`
  in business code; no hardcoded paths.
- **§1.8 read-only corpus** — *complies*: writes only to gitignored
  `data/derived/`; source untouched.
- **§5.1 secrets** — *complies*: M1 needs no secret (no live EDGAR, no cloud
  LLM). No `.env` key added.

**(b) New dependencies** (named here before adding, Constitution §3 /
architecture §2):
- **`arelle-release` (Arelle)** — reference iXBRL processor; correct
  scale/sign/transform/context/dimension handling. The fidelity-critical pick
  over py-xbrl / raw lxml.
- **`docling`** — structured PDF parse with table-cell fidelity for 10-Ks; over
  Unstructured / PyMuPDF.
- **`pydantic` (v2)** + **`pydantic-settings`** — typed validated contracts and
  the single settings object; already the downstream stack's type system.
- **dev: `pytest`.** Packaging: **`pyproject.toml`** + proposed **hatchling**
  backend + **uv** installer/lock (vs pip-tools / Poetry). *These three —
  XBRL parser, PDF parser, and packaging/installer — are the forks most worth
  the lead's confirmation.*
- **Version-pin Arelle and Docling** in `pyproject.toml` (`==` or a tight
  range), not just name them: both carry the determinism-load-bearing logic
  (Arelle's iXBRL transform registry; Docling's table-structure model) that
  AC7's byte-identical guarantee rests on, so a silent minor bump could move
  output. Pins are recorded with the lockfile.

**(c) Eval-baseline impact** — **none**: M1 touches no retrieval/agent/chunking,
moves no committed baseline (none exists). The anchor numeric values become the
first seed of eval truth (M7), not a regression target now.

**Other risks.**
- **Docling first-run model download** — tensions with offline rebuild
  (architecture §7). *Mitigate:* document the one-time fetch; models cache
  locally; subsequent rebuilds are offline. Re-evaluate a no-model parser if the
  offline constraint hardens.
- **Parse latency** — Docling over 5 × ~17 MB PDFs is minutes, offline and
  one-time; acceptable for an ingest step.
- **Arelle validation noise / memory** — the 12 MB instances + linkbases load
  fully; cap log noise, stream facts.
- **EDGAR rate limits** — N/A (no live fetch; vendored source).
- **Taxonomy tag drift** — anchor tags confirmed to resolve for all five FYs in
  IMPLEMENT (Open Question), before pinning expected values.

## Affected files (best guess)

- `pyproject.toml` — new: PEP 621 manifest, deps, src-layout
- `src/config/__init__.py` — new
- `src/config/schema.py` — new: `Element`, `XBRLFact`, enums
- `src/config/settings.py` — new: pydantic-settings `Settings`, paths, accession↔FY
- `src/config/logging.py` — new: logging skeleton
- `src/ingestion/__init__.py` — new
- `src/ingestion/xbrl.py` — new: Arelle iXBRL → `XBRLFact` (sole producer)
- `src/ingestion/elements.py` — new: Docling PDF → `Element` (sole producer)
- `src/ingestion/sections.py` — new: 10-K Item-boundary stamping
- `src/ingestion/serialize.py` — new: JSONL read/write
- `src/ingestion/pipeline.py` — new: orchestration + `__main__` CLI
- `tests/unit/test_xbrl_anchors.py` — new (cheap eval tier)
- `tests/unit/test_xbrl_extract.py` — new
- `tests/unit/test_elements_provenance.py` — new
- `tests/unit/test_entity_period.py` — new
- `tests/unit/test_firewall.py` — new
- `tests/unit/test_pipeline_rebuild.py` — new
- `tests/unit/test_contracts_location.py` — new
- `tests/conftest.py` — new (fixtures: a small parsed sample / accession paths)
- `.gitignore` — add `data/derived/`
- `docs/constitution.md` — §1.3 `[RATIFY]` → ratified
- `docs/architecture.md` — §7/§2/§9 vendored-XBRL refinement
- `specs/2026-06-04-ingestion-parsing/spec.md` — fix dangling `architecture §6.7`
  citation → Constitution §6(7) (doc-promotion step)
- `docs/roadmap.md` — M1 row → `done` (at EVALUATE)
