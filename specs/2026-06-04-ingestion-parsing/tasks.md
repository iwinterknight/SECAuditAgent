---
spec: 2026-06-04-ingestion-parsing
status: tasks
created: 2026-06-04
---

# Tasks: M1 — Ingestion & parsing (Elements + XBRLFacts from the JPM 10-Ks)

Ordered and sequential — each task depends on the ones above it unless noted.
Tests ride **with** the change that introduces them (§4.4). The cheap-eval
anchor (T5) is the only §4.3 deterministic gate; there is no §4.2 eval-
regression gate at M1 (ingestion is below chunking/retrieval/agent) and no
golden-set entry is required (the golden set proper is M7).

No pre-flight task: this is the first code (no pre-existing failing test, no
baseline to capture). The single trunk is used; the lead commits on their own
cadence.

## Tasks

- [x] **T1. Bootstrap packaging + repo skeleton.**
      Files: `pyproject.toml`, `uv.lock`, `src/config/__init__.py`,
      `src/ingestion/__init__.py`, `tests/conftest.py`,
      `tests/unit/test_packaging.py`
      Acceptance: `tests/unit/test_packaging.py::test_config_and_ingestion_importable`
      passes — editable src-layout install resolves `import config` and
      `import ingestion`; the `slow` pytest marker is registered.
      Notes: `pyproject.toml` = PEP 621, Python 3.13, **src-layout**
      (`package-dir` under `src/`); deps **version-pinned** — `arelle-release`,
      `docling`, `pydantic>=2`, `pydantic-settings`; dev `pytest`; backend
      **hatchling**, lock/install via **uv**. Register `markers = ["slow"]` and
      configure `pytest` to find `tests/`. `reports/requirements.txt`
      (doc-tooling) stays separate — do **not** fold it in. The three precedent-
      setting forks (Arelle, Docling, hatchling+uv) are lead-confirmed before
      this lands.
      done 2026-06-05: src-layout editable install resolves `import config` /
      `import ingestion`; `slow` marker registered; 131-pkg `uv.lock` committed.
      Acceptance `test_packaging.py::test_config_and_ingestion_importable` green
      (2/2).

- [ ] **T2. `config/` schema — the typed contracts.**
      Files: `src/config/schema.py`, `tests/unit/test_contracts_location.py`
      Acceptance: `tests/unit/test_contracts_location.py::test_types_defined_in_config`
      passes — `Element`, `XBRLFact`, `ElementKind`, `PeriodType`, `Entity`
      import from `config.schema` and are defined there (not in `ingestion`).
      Notes: Pydantic v2 models per the plan's field lists; `value: Decimal`
      (not float). A model validator enforces **period exclusivity** (`instant`
      ⇒ only `period_instant`; `duration` ⇒ only `period_start`/`period_end`).
      `Entity` enum = `JPMC_CONSOLIDATED` | `JPMORGAN_CHASE_BANK_NA`.
      Depends-on: T1

- [ ] **T3. `config/` settings + logging.**
      Files: `src/config/settings.py`, `src/config/logging.py`,
      `tests/conftest.py`, `tests/unit/test_settings.py`
      Acceptance: `tests/unit/test_settings.py::test_filings_table_resolves`
      passes — all five `FILINGS` rows map `accession → fiscal_year` correctly
      and each row's `pdf_filename` + `xbrl_instance` exist on disk under the
      settings-rooted paths.
      Notes: one **pydantic-settings** `Settings` + `get_settings()` (§1.7); the
      authoritative `FILINGS` table `(accession, fiscal_year, pdf_filename,
      xbrl_instance)`; `corpus_pdf_dir`/`xbrl_dir`/`derived_dir`/`log_level`;
      `configure_logging()` using `getLogger(__name__)`, no `print`. `conftest`
      gains accession-path fixtures derived from `get_settings()` (single source
      of truth for paths — no hardcoding in tests).
      Depends-on: T2

- [ ] **T4. XBRL extractor — Arelle → `XBRLFact`s.**
      Files: `src/ingestion/xbrl.py`, `tests/conftest.py`,
      `tests/unit/test_xbrl_extract.py`, `tests/unit/test_entity_period.py`
      Acceptance: `tests/unit/test_xbrl_extract.py` (`test_fact_fields_present`,
      `test_fact_ids_unique_per_filing`, `test_nil_and_untransformable_skipped`,
      `test_filing_fact_count_floor`) **and** `tests/unit/test_entity_period.py`
      (`test_entity_always_set_and_distinct`, `test_period_date_fields_exclusive`,
      `test_restated_fy2022_both_present`) all pass.
      Notes: `extract_facts(accession_dir, *, source_filing) -> list[XBRLFact]`
      — the **sole** `XBRLFact` producer. Arelle loads instance + linkbases;
      resolve context (entity via the consolidation dimension, default
      consolidated CIK `0000019617`; `period_type` + dates; other axes →
      `dimensions`), resolve unit, apply the iXBRL **scale/sign/transform**;
      **skip** nil / un-transformable facts (log, never coerce to `0`). `conftest`
      adds a session-scoped facts fixture (parse one accession once; the
      restatement test parses the 2022 + 2024 instances).
      Depends-on: T3 (paths), T2 (`XBRLFact`)

- [ ] **T5. Anchor numeric truth — the cheap-eval gate (seeds M7).**
      Files: `tests/unit/test_xbrl_anchors.py`
      Acceptance: `tests/unit/test_xbrl_anchors.py::test_total_assets_and_net_income_exact`
      passes — **exact-match** of `us-gaap:Assets` (instant) and
      `us-gaap:NetIncomeLoss` (duration), consolidated, per FY, against the filed
      XBRL value (10 assertions = 2 metrics × 5 FY).
      Notes: this **is** the §4.3 cheap deterministic tier and the first seed of
      the M7 numeric truth set. `[VERIFY in IMPLEMENT]` — read the 10 expected
      integers from the five instances and pin them; per-FY `{fiscal_year:
      concept_tag}` override fallback if a tag doesn't resolve across all FYs.
      Depends-on: T4

- [ ] **T6. PDF parser — Docling → `Element`s with provenance.**
      Files: `src/ingestion/elements.py`, `tests/conftest.py`,
      `tests/unit/test_elements_provenance.py`
      Acceptance: `tests/unit/test_elements_provenance.py::test_every_element_has_provenance`
      and `::test_element_count_floor` pass — every Element has `fiscal_year` +
      `page` + `kind` + an `item` field (`unknown` until T7) + `entity =
      JPMC_CONSOLIDATED`; each filing yields `> N` Elements.
      Notes: `parse_elements(pdf_path, *, fiscal_year, source_filing) ->
      list[Element]` — the **sole** `Element` producer. Docling structured parse;
      `kind ∈ {text, table, heading}`; table `text` is structure-preserving for
      M2; entity defaults consolidated for all Elements (no narrative inference);
      `item` left `unknown` pending T7. `conftest` adds a parsed-elements session
      fixture (parse one PDF once). Document Docling's one-time model download.
      Depends-on: T3 (paths), T2 (`Element`)

- [ ] **T7. Item-boundary stamping — `sections`.**
      Files: `src/ingestion/sections.py`, `tests/unit/test_sections.py`,
      `tests/unit/test_elements_provenance.py`
      Acceptance: `tests/unit/test_sections.py::test_missing_header_yields_unknown`
      (pure mini heading-fixture: a garbled Item header ⇒ `unknown`, never the
      previous Item's label) **and**
      `tests/unit/test_elements_provenance.py::test_known_elements_land_in_right_item`
      (real corpus: an MD&A Element ⇒ `Item 7`; a financial-statements Element ⇒
      `Item 8`) pass.
      Notes: `assign_items(elements) -> list[Element]` — a deterministic pure
      pass that scans heading Elements for Item headers and stamps each Element
      with the Item it falls under; undetected boundary ⇒ `unknown` + warning. No
      number handling.
      Depends-on: T6

- [ ] **T8. Firewall guard — the §1.2 structural check.**
      Files: `tests/unit/test_firewall.py`
      Acceptance: `tests/unit/test_firewall.py::test_element_path_never_constructs_xbrlfact`
      passes — static check that no symbol in `ingestion.elements` /
      `ingestion.sections` references `XBRLFact`, and `XBRLFact` is defined only
      in `config.schema` (**type-ownership**, not a digit-grep — Element text
      legitimately contains digits).
      Notes: AST / import inspection. This is the §1.2 "numbers only from XBRL"
      mechanism made executable; it can only pass once both paths exist.
      Depends-on: T4, T6, T7

- [ ] **T9. JSONL serialization — deterministic write/read.**
      Files: `src/ingestion/serialize.py`, `tests/unit/test_serialize.py`
      Acceptance: `tests/unit/test_serialize.py::test_roundtrip_and_byte_stable`
      passes — `write_jsonl`→`read_jsonl` round-trips both types equal, and
      re-serializing identical input yields **byte-identical** output.
      Notes: enforces the plan's serialization invariants — rows sorted by total
      key (`fact_id` / `ordinal`), `sort_keys=True`, `Decimal`→canonical string,
      dates→ISO-8601, `\n` endings, UTF-8, no trailing whitespace. (New test vs
      the plan's table: decomposition gives serialize its own decisive check,
      faster and more isolated than the full pipeline rebuild.)
      Depends-on: T2 (types)

- [ ] **T10. Ingestion pipeline CLI — the join + rebuild.**
      Files: `src/ingestion/pipeline.py`, `.gitignore`,
      `tests/unit/test_pipeline_rebuild.py`
      Acceptance: `tests/unit/test_pipeline_rebuild.py::test_deterministic_and_gitignored`
      (`@pytest.mark.slow`) passes — `pipeline.run()` over all five filings writes
      `elements/` + `facts/` JSONL under gitignored `data/derived/`; a second run
      is byte-identical; an unknown accession raises; no network fetch occurs.
      Notes: `run(accessions: list[str] | None = None)` — the **only** place the
      PDF↔accession↔FY join is resolved (reads `Settings.FILINGS`); `None` ⇒ all
      five; unknown accession ⇒ **hard error**; CLI `python -m ingestion.pipeline`.
      Add `data/derived/` to `.gitignore`. `@slow`, excluded from the default
      per-implement run.
      Depends-on: T9 (serialize), T4 (facts), T6 (elements), T7 (items)

- [ ] **T11. Doc-promotions — ratify §1.3, refine architecture, fix citation.**
      Files: `docs/constitution.md`, `docs/architecture.md`,
      `specs/2026-06-04-ingestion-parsing/spec.md`
      Acceptance: text check — `docs/constitution.md` §1.3 no longer contains
      `[RATIFY]` and states "original filing for FY N"; `docs/architecture.md`
      §7/§2/§9 reference the **vendored** XBRL packages (not "pulled from EDGAR …
      gitignored derived path" as the live mechanism); the spec's
      `architecture §6.7` citation is corrected to **Constitution §6 item 7**.
      Notes: doc-only — no `src/` change (acceptance is a presence/absence text
      check, not pytest). `docs/roadmap.md` M1 → `done` is deferred to EVALUATE,
      not here. Lands in the same change as the code per Constitution §6(7).
      Depends-on: none (doc-only; placed last so the docs describe shipped behavior)

## Discovered work

(none yet — populate during IMPLEMENT if scope surfaces.)
