---
spec: 2026-06-04-ingestion-parsing
stage: implement
report: 04-implement-T3
created: 2026-06-05
---

# Educator Report — IMPLEMENT · M1 Ingestion & parsing (T3 · `config/` settings + logging)

> **How to read this.** Top-down: first *where* this task sits, then the
> *domain* it encodes (configuration discipline, the accession↔FY↔filename
> join, logging hygiene), then the *architecture* view, then the mandatory
> two-level **Code Walkthrough** (module → file → function → line). By the end
> you should be able to re-present every line of `settings.py`, `logging.py`,
> the conftest fixtures, and the test, and defend why each exists.

---

## 1. Where we are (orientation)

We just finished **T3** of **M1 (Ingestion & parsing)** — the third task of the
project's first code module. T1 laid the packaging skeleton; T2 defined the two
typed contracts (`Element`, `XBRLFact`) in `config.schema`. **T3 fills in the
rest of the `config/` floor**: a single `Settings` object (`config.settings`)
and a logging skeleton (`config.logging`). On the data-flow diagram
(`docs/architecture.md` §4: ingest → chunk → index → retrieve → agent → answer)
nothing *flows* yet — but everything that will flow now has a single place to
ask "where is the corpus?" and "which filings exist?". This is the task that
*unblocks the extractors*: T4 (XBRL → facts) and T6 (PDF → elements) both open
files, and after T3 they open them by asking `Settings`, never by hardcoding a
path. We are at the very bottom-left of the diagram, wiring the power before
the machines.

## 2. The domain in play (teach me)

Four concepts converge in this small task. Three are about *fidelity through
discipline*; one is plumbing done right.

### 2.1 Why a *single* settings object (Constitution §1.7)

A financial-grounding system lives and dies by reproducibility. If module A
reads a path from `os.getenv("CORPUS")` and module B hardcodes
`C:\Users\...\yearly`, the two can silently disagree about *what data the
system is even answering over*. The constitution's answer is categorical:
**all configuration flows through exactly one `config.settings` object**;
business code never calls `os.getenv` and never bakes in an absolute path.
`pydantic-settings` gives us that object with three properties we want:

- **Typed + validated** — `project_root` is a `Path`, `log_level` is a `str`;
  a malformed override fails at construction, not deep in a parse.
- **Env-overridable, with a safe default** — every field can be overridden by
  an environment variable (we namespace them `AUDITAGENT_…`), but defaults to
  a value computed from the repo layout, so a fresh `git clone` "just works"
  with zero configuration.
- **One instance** — `get_settings()` is `@lru_cache`-wrapped, so the whole
  process shares one object. Configuration is read once and cannot drift
  between modules. (We *prove* this with a `is`-identity test.)

The alternative — a module-level `config.py` of bare constants, or scattered
`os.getenv` — was rejected: no validation, no single override surface, and
nothing stops two modules disagreeing.

### 2.2 The accession ↔ fiscal-year ↔ filename join (the heart of T3)

This is the domain subtlety worth real fluency. A JPMorgan 10-K is identified
*three different ways* depending on who's naming it:

| Naming | Example | Who uses it |
|---|---|---|
| **Accession number** | `0000019617-25-000270` | SEC/EDGAR — the canonical filing id; our `source_filing` tag and every derived path key |
| **Period-end date** | `jpm-20241231.htm` / `.pdf` | the *filenames* JPM gives the documents |
| **Fiscal year** | FY2024 | how a human (and our provenance) refers to it |

Look closely at that example row: accession `…-25-…` (filed in 20**25**), file
named `…20241231` (period ends Dec 2024), reporting FY**2024**. **Three
different years touch one filing.** If any code independently parses the fiscal
year out of the filename (`20241231` → 2024) in one place and reads it from a
map in another, the two derivations can drift — and a drifted provenance tag is
exactly the silent corruption M1 exists to prevent.

The discipline (plan §73-80, a §1.5-style single-source-of-truth applied to
provenance): **write the join down once**. `Settings.FILINGS` is an ordered
table of `(accession, fiscal_year, pdf_filename, xbrl_instance)` rows. Every
consumer — the conftest fixtures here, the XBRL extractor (T4), the PDF parser
(T6), the pipeline (T10) — reads the join from this one table. **The filename
date is never re-parsed for a fiscal year anywhere.** They physically cannot
disagree because there is only one source.

A second subtlety hides in FY2025: its accession is `0001628280-26-008131` —
note the **different filer prefix** (`0001628280`, not JPM's usual
`0000019617`). That is why we can't compute the accession from a pattern; the
authoritative thing is the *vendored folder on disk*, so the table is pinned to
the disk truth and the test asserts every row's files actually exist.

### 2.3 Logging hygiene (Constitution §3)

`print` is forbidden for runtime output. Two reasons: (1) `print` goes to
stdout with no level, no timestamp, no module attribution — useless for a
pipeline you need to debug six months from now; (2) it can't be silenced or
routed centrally. The standard-library `logging` module fixes both. The
convention is two-part: **every module** does
`logger = logging.getLogger(__name__)` (so each log line names the module that
emitted it), and **one boundary** (a CLI `main`, a test session) calls
`configure_logging()` once to install the root handler and set the level. The
*level itself* is read from `Settings.log_level` — so the same §1.7 single-source
rule covers "how loud are the logs," not just "where is the data."

### 2.4 The framework: `pydantic-settings`

It is the settings-shaped sibling of Pydantic (which T2 already pulled in for
the contracts). `BaseSettings` adds environment-variable binding and `.env`
file loading on top of `BaseModel`'s typed validation. We get it "for free"
because it's already the downstream stack's type system (FastAPI in M6 uses
Pydantic models directly). Newly installed this task:
`pydantic-settings==2.14.1` (+ its `python-dotenv` dependency) — both were
already named in the plan's Risks and locked in T1's `uv.lock`, so this is a
declared dependency, not a surprise.

## 3. The high-level view (architecture)

In the layer map (`docs/architecture.md` §3, imports flow downward only),
**`config` is the floor** — it imports nothing above it; everything imports it.
T3 completes that floor's *configuration* surface. The module boundary after
T3:

```
                       ┌─────────────────── config (the floor) ───────────────────┐
   environment ──┐     │  schema.py   (T2)  Element, XBRLFact, enums               │
  AUDITAGENT_*   ├────▶│  settings.py (T3)  Settings · FILINGS · get_settings()    │
     .env        ┘     │  logging.py  (T3)  configure_logging()                    │
                       └────────────▲───────────────────────────┬─────────────────┘
                                    │ imports config only        │ provides paths + join
                                    │                            ▼
                          ingestion.xbrl (T4) · ingestion.elements (T6) · pipeline (T10)
```

T3 **produces no typed §5 contract** (`Element`/`XBRLFact` were T2's job; this
task adds the small `Filing` record, a settings-local value object, not a
cross-layer contract). What it produces is *the configured environment those
contracts get built in*: the paths the producers read, the FY/accession join
they stamp into provenance, and the logging they emit through. Inputs:
environment variables (optional) + the repo layout. Outputs: one `Settings`
singleton + a `configure_logging()` entry point.

## 4. The drill-down (low level) — the two-level Code Walkthrough

### Module level

- **Module:** `config` (the dependency floor; `docs/architecture.md` §3).
- **Role / data-flow position:** pre-ingest configuration. Sits *below* every
  ingestion module; provides corpus paths, the derived-output root, the
  authoritative filing manifest, and logging setup.
- **Boundary change:** adds two public entry points — `get_settings() ->
  Settings` and `configure_logging(level=None)` — plus the `Settings`/`Filing`
  types and the `Settings.FILINGS` class constant. No §5 contract is touched
  (`Filing` is a settings-internal value object). Dependency direction holds:
  `config.logging → config.settings` is *within* the floor; nothing imports
  upward.

### File level

**`src/config/settings.py`** — the single configuration object.

- `_PROJECT_ROOT = Path(__file__).resolve().parents[2]` — the repo root,
  computed *from the file's own location* (`src/config/settings.py` → up 3 =
  repo root), never hardcoded. A clone anywhere on disk resolves correctly.
  This is how we honor "no absolute paths" (§3) while still producing absolute
  paths at runtime.
- `class Filing(BaseModel)` — one row of the manifest: `accession`,
  `fiscal_year`, `pdf_filename`, `xbrl_instance`. A typed record (not a bare
  tuple) so a misread field is named, not positional. It is a *value object*
  local to settings — deliberately **not** one of the §5 cross-layer contracts.
- `class Settings(BaseSettings)`:
  - `model_config = SettingsConfigDict(env_prefix="AUDITAGENT_", env_file=".env", extra="ignore")`
    — env vars bind as `AUDITAGENT_LOG_LEVEL` etc.; a `.env` file is read if
    present; unknown env keys are ignored (so an unrelated `AUDITAGENT_…` set by
    another tool can't crash construction).
  - `project_root: Path = _PROJECT_ROOT` and `log_level: str = "INFO"` — the two
    overridable fields, each with a repo-sensible default.
  - `FILINGS: ClassVar[tuple[Filing, ...]]` — **the join, written once.** It's a
    `ClassVar`, so Pydantic treats it as a class constant, *not* an env-tunable
    field — correct, because the vendored corpus is fixed in the repo. Five rows,
    ordered by fiscal year, each pinned to the disk-verified filenames (incl.
    FY2025's different-prefix accession `0001628280-26-008131`).
  - `corpus_pdf_dir` / `xbrl_dir` / `derived_dir` (properties) — the three roots,
    all derived from `project_root`. `derived_dir` is the gitignored output root
    (§1.8); the source dirs are read-only.
  - `accession_to_fy` (property) — the `{accession: fy}` map, *derived from*
    `FILINGS` so it can't disagree with the table (the test pins this).
  - `filing_for(accession)` — lookup that **raises `KeyError` on an unknown
    accession** rather than returning `None`. Failing loud is the §1.5
    fail-closed posture: a typo must not masquerade as "no data."
  - `pdf_path(filing)` / `xbrl_instance_path(filing)` — turn a `Filing` into a
    concrete absolute path (`corpus_pdf_dir/pdf_filename`,
    `xbrl_dir/accession/xbrl_instance`). Centralizing this composition is why
    the test, conftest, and T4/T6/T10 never re-spell the path join.
- `@lru_cache def get_settings() -> Settings` — the process singleton (§1.7).
  `lru_cache` (no args) memoizes the zero-arg call, so every caller shares one
  object.

**`src/config/logging.py`** — the logging skeleton.

- `_LOG_FORMAT` — timestamp + level + logger-name + message; the attributable
  format `print` can't give.
- `configure_logging(level=None)` — the single boundary entry point. Resolves
  the level from the argument *or* `Settings.log_level` (§1.7 again), upper-cases
  it, and calls `logging.basicConfig`. `basicConfig` is a no-op once handlers
  exist, so the function is idempotent — safe to call from a CLI and a test
  session both. Business modules never call this; they only `getLogger`.

**`tests/conftest.py`** — shared fixtures (additive; the T1 "no `sys.path`
manipulation" docstring is preserved verbatim).

- `settings` (session-scoped) — returns `get_settings()`. Every test that needs
  a path goes through this, so there's one place to change if the layout moves.
- `sample_filing` (session-scoped) — FY2024's `Filing`, fetched by
  `filing_for("0000019617-25-000270")`. This is the hook T4/T6 will hang their
  "parse one filing once" session fixtures on; picking by accession (not list
  index) keeps it readable and routes through the same lookup the pipeline uses.

**`tests/unit/test_settings.py`** — the acceptance check + two companions.

- `EXPECTED_FY` — the five-row ground truth, written *independently* of the
  table under test so the test can't "agree with itself."
- `test_filings_table_resolves` (**the named AC**) — asserts the table has
  exactly five rows, each `accession → fiscal_year` matches `EXPECTED_FY`, all
  five accessions are distinct, and **each row's PDF and iXBRL instance actually
  exist on disk** under the settings-rooted paths. That last clause is what
  upgrades the table from "a claim" to "verified against the vendored corpus."
- `test_get_settings_is_cached_singleton` — `get_settings() is get_settings()`;
  pins the §1.7 one-object contract.
- `test_accession_to_fy_consistent_with_filings` — the derived map equals the
  map rebuilt from `FILINGS`; pins that the convenience accessor can't drift
  from its source.

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| Config mechanism | one `pydantic-settings` `Settings` + `get_settings()` | scattered `os.getenv` / bare-constant `config.py` | §1.7 single source; typed, validated, env-overridable, one instance |
| The FY↔accession↔filename join | one ordered `FILINGS` table, filename date never re-parsed for FY | derive FY from filename where needed | three namings per filing + FY2025's odd prefix → any second derivation can drift provenance (§1.5 discipline) |
| `FILINGS` as `ClassVar` | class constant | env-tunable field | the vendored corpus is fixed in-repo; the manifest is code, not config |
| Path roots | properties derived from `project_root` | each dir its own env field | smaller config surface; one override (`project_root`) relocates the whole checkout |
| Unknown accession | `filing_for` raises `KeyError` | return `None` | fail-closed (§1.5): a typo must not look like "no data" |
| `get_settings` identity | `@lru_cache` singleton | construct per call | §1.7 "one object"; configuration read once, no drift |
| Logging | `configure_logging` + `getLogger(__name__)`, level from settings | `print` | §3: attributable, level-controlled, centrally routable output |

## 6. Open threads & what's next

- **No new `[RATIFY]`/`[VERIFY]` markers** opened by T3. The plan's anchor-tag
  `[VERIFY in IMPLEMENT]` is still T5's; the §1.3 restatement ratification and
  architecture §7 vendored-XBRL refinement are still queued for **T11** (the
  doc-promotions task).
- **`pydantic-settings==2.14.1`** newly installed into the `.venv` (+
  `python-dotenv`); already declared in the plan's Risks and locked in T1's
  `uv.lock`, so no manifest change is needed.
- **Carried forward:** the path helpers and `sample_filing` fixture are
  *infrastructure for T4/T6* — they're exercised lightly now (only the
  acceptance test reads paths) and fully once the extractors parse real files.
- **Next:** `T4` — the XBRL extractor (`ingestion/xbrl.py`): Arelle loads each
  accession's iXBRL instance + linkbases and emits `XBRLFact`s, the sole
  producer of that contract and the structural firewall (§1.2). Run
  `/implement T4`.
