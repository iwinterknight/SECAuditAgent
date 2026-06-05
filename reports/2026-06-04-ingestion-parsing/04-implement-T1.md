---
spec: 2026-06-04-ingestion-parsing
stage: implement
report: 04-implement-T1
created: 2026-06-05
---

# Educator Report — IMPLEMENT · T1 Bootstrap packaging + repo skeleton

> **How to read this.** This is the lead's 360° companion to the first
> `/implement` of M1. It opens at the altitude of *what a Python package even
> is* — why an importable, installable `src/` is the precondition for every
> other line of code in the project — and drills down to the two-level **Code
> Walkthrough** (Constitution §2): first the module boundary this task drew,
> then each file and what its code does and why. T1 ships almost no behaviour
> (the packages are empty skeletons); its whole job is to make the ground
> exist. So this report leans hard into the *domain of packaging itself* —
> src-layout, editable installs, build backends, lockfiles, dependency pinning,
> pytest markers — because that domain **is** the deliverable. Read it
> top-to-bottom to finish able to defend why `import config` works and why we
> went to such trouble to make sure it works *honestly*. Markdown is the source
> of truth; the sibling PDF is rendered by `reports/render.py`.

---

## 1. Where we are (orientation)

The **IMPLEMENT** stage for **M1 — Ingestion & parsing** has begun, and this is
its first task: **T1, Bootstrap packaging + repo skeleton**. The chain to here:
CLARIFY fixed the contract ([`spec.md`](../../specs/2026-06-04-ingestion-parsing/spec.md)),
PLAN fixed the design ([`plan.md`](../../specs/2026-06-04-ingestion-parsing/plan.md)),
TASKS cut the build into eleven ordered pieces
([`tasks.md`](../../specs/2026-06-04-ingestion-parsing/tasks.md)). T1 is the
**only task with no dependencies** — the one that creates the package the other
ten will live in. On the roadmap (`docs/roadmap.md`) M1 is still the bottom of
the dependency chain and the first application code; on the data-flow map
(`docs/architecture.md` §4) we are at the far-left box, but not yet *inside* it:

```
  ▶ ingestion (M1)  ─►  chunking (M2)  ─►  index (M3)  ─►  retrieval (M4)  ─►  agent (M5)  ─►  answer
    [ T1 builds the empty package these two streams will flow out of ]
    PDF → Elements
    XBRL → XBRLFacts
```

Why this step mattered: nothing — no contract, no extractor, no test — can be
*imported* until a package exists and installs cleanly. T1 is the "does the
ground exist" check. It writes the project's first `pyproject.toml`, stands up
the `config/` and `ingestion/` packages as empty skeletons, and proves with one
test that an editable install makes `import config` and `import ingestion`
resolve. Almost no runtime behaviour; total structural leverage. If T1 is
wrong, every later `/implement` fails at the import line.

## 2. The domain in play (teach me)

T1's "domain" is **Python packaging** — the least glamorous and most
quietly load-bearing part of the whole project. Here is the fluency, from first
principles.

**What "a package" and "importable" actually mean.** When you write `import
config`, Python walks a list of directories (`sys.path`) looking for a folder
named `config/` with an `__init__.py`, or an installed distribution that
registers that name. "Making `config` importable" therefore means one of two
things: either the folder happens to be on `sys.path` (fragile, accidental), or
a real *install* has registered it (deliberate, reproducible). T1 insists on
the second. That distinction is the spine of this whole task.

**Flat layout vs src-layout — and the bug src-layout kills.** The naive
("flat") layout puts the package folder at the repo root: `config/` sits next
to `pyproject.toml`. The problem: the repo root is almost always on `sys.path`
already (Python adds the current working directory), so `import config` works
*even if you never installed anything* — it's importing the raw folder by
accident of cwd. That feels convenient until the day your install is broken
(a missing `packages=` entry, a typo in the manifest) and your tests **still
pass**, because they were never testing the install — they were importing the
folder directly. You ship a wheel nobody can actually install. **src-layout**
fixes this by moving the packages one level down, under `src/`: `src/config/`,
`src/ingestion/`. Now the repo root no longer contains an importable `config/`,
so the *only* way `import config` succeeds is a real install that maps
`src/config` → the top-level name `config`. The test becomes honest: green means
"the install works," not "the folder is sitting right there." This is the single
most important design decision in T1, and the reason `tests/conftest.py`
deliberately refuses to touch `sys.path` (more in §4).

**Editable install — "live source, registered name."** A normal install copies
your code into `site-packages`; you'd have to reinstall after every edit —
intolerable during development. An **editable install** (`pip install -e .`, or
here `uv pip install -e .`) instead registers the package name and points it
back at your working tree (via a `.pth` file or an import hook). Result: `import
config` resolves through the install machinery (so the src-layout honesty holds),
but the code it finds is your live `src/config/` — edits are picked up with no
reinstall. Editable install is what lets src-layout be rigorous *and* ergonomic
at the same time.

**Build backend (PEP 517/518) and why hatchling.** Modern Python splits "what
my project is" (declarative metadata) from "how to turn it into a wheel" (a
**build backend**). The `[build-system]` table in `pyproject.toml` names the
backend; the installer calls it to produce the wheel. We chose **hatchling**
(Hatch's backend) over the older setuptools because it's PEP 621-native, needs
no `setup.py`/`setup.cfg` boilerplate, and makes the src-layout mapping a single
clean line — `[tool.hatch.build.targets.wheel] packages = ["src/config",
"src/ingestion"]` — which says "these two source folders become these two
top-level importable packages." That one line is the bridge from src-layout on
disk to `import config` at runtime.

**PEP 621 `[project]` metadata.** The `[project]` table is the *standardized*
(tool-agnostic) place to declare name, version, `requires-python`, and
`dependencies`. Standard means any compliant tool — uv, pip, hatchling, build —
reads the same fields; we are not locked to one vendor's config dialect. T1
declares `requires-python = ">=3.13"` (the project's floor) and the four runtime
dependencies.

**uv — the installer/resolver/locker — and the lockfile.** `uv` is a fast
Python package manager (resolver + installer + lock tool). The crucial artefact
it produces is **`uv.lock`**: a fully *resolved*, hashed, cross-platform
snapshot of the entire transitive dependency graph (here, **131 packages** —
because Arelle and Docling each drag in large subtrees). `pyproject.toml` says
"I want `docling==2.97.0`"; `uv.lock` says "…which means exactly these 131
distributions at these exact versions with these exact hashes." Committing the
lock is what makes the AC7 promise — *deterministic, rebuildable from committed
source* — real: a fresh clone resolves to the **same** graph, not "whatever was
latest the day you ran it." `pyproject.toml` is intent; `uv.lock` is the
reproducible fact.

**Dependency pinning, and why two of the four pins are exact.** Look at the
dependency list as two tiers:
- **`arelle-release==2.41.4`** and **`docling==2.97.0`** are pinned to an *exact*
  version. These are the numeric and narrative parsers. Their *output* is
  determinism-load-bearing: Arelle's iXBRL transform registry decides how a raw
  inline value becomes a signed, scaled number; Docling's layout/table model
  decides how a PDF becomes structured Elements. A silent minor-version bump
  could change a transform or a table boundary and quietly break the
  byte-identical rebuild guarantee (plan Risk (b)). So we forbid drift entirely.
- **`pydantic>=2`** and **`pydantic-settings`** are *floor* pins. Pydantic is a
  contract/validation library; its v2 API is stable and we want bug-fix
  freedom. We pin the major (>=2, because v1→v2 was a breaking rewrite) but not
  the patch.

This isn't pedantry — it's the packaging-level expression of Constitution §1.8
(reproducibility) and the spec's AC7.

**pytest configuration and the `slow` marker.** `[tool.pytest.ini_options]` in
`pyproject.toml` is where pytest reads its config. Two things here: `testpaths =
["tests"]` tells pytest where to collect (no guessing), and `markers = ["slow:
…"]` *registers* a custom marker. A pytest marker is a label you put on a test
(`@pytest.mark.slow`) to select or deselect it (`pytest -m slow`, or `-m "not
slow"`). If you use a marker without registering it, pytest emits a
`PytestUnknownMarkWarning` — and in strict setups that's an error. T1 registers
`slow` now, before any test uses it, so that the corpus-re-parsing rebuild test
in **T10** can be a first-class, deselectable `@slow` marker instead of an
"unknown marker" wart. The default per-`/implement` run stays fast by *not*
running `slow`; the heavy rebuild runs only when explicitly asked.

**Why a separate `reports/requirements.txt` is NOT folded in.** The report
renderer (`reports/render.py`, with `markdown` + `xhtml2pdf`) is doc *tooling*,
not application code. Its dependencies are deliberately kept out of the app's
`pyproject.toml` so the runtime dependency graph stays honest — the agent never
ships a PDF library. T1's notes call this out explicitly so nobody "tidies" it
together later.

## 3. The high-level view (architecture)

Map this task onto the layer diagram (`docs/architecture.md` §3, imports flow
**downward only**, §1.6):

```
      ┌─────────────────────────────────────────────┐
      │  agent / api / retrieval / index / chunking  │   (higher layers — M2+)
      └─────────────────────────────────────────────┘
                          │  imports
                          ▼
      ┌──────────────────────────┐
      │   ingestion   (T1 skeleton)│   ◄── bottom of the DATA flow (§4 far-left):
      │   PDF → Element            │       the two producer paths live here (T4/T6/T7)
      │   XBRL → XBRLFact          │
      └──────────────────────────┘
                          │  imports
                          ▼
      ┌──────────────────────────┐
      │   config      (T1 skeleton)│   ◄── bottom of the IMPORT graph (§1.6):
      │   schema / settings / log  │       imports nothing above it; hosts the
      └──────────────────────────┘       §5 typed contracts (T2/T3)
```

T1 stands up the **two lowest layers** at once, as empty skeletons:

- **`config`** is the absolute floor of the import graph. By rule (§1.6) it
  imports *nothing* above it. It will host the §5 typed contracts **`Element`**
  and **`XBRLFact`** (plus the `ElementKind` / `PeriodType` / `Entity` enums) in
  T2, and the single settings object + logging in T3. Defining the contracts
  *here* — in one place below everything — is what lets every higher layer import
  them from a single home (architecture §5).
- **`ingestion`** is the bottom of the *data* flow (§4's leftmost box). It will
  hold the two independent producer paths — the PDF path (`elements` + `sections`
  → `Element`) and the XBRL path (`xbrl` → `XBRLFact`) — kept deliberately
  separate so numbers originate only from XBRL (the §1.2 firewall). It imports
  `config` and nothing higher.

**What changed at the module boundary:** structurally, everything; behaviourally,
nothing yet. No function is defined, no contract is instantiated, no data flows.
But the *boundary itself* now exists: every later module has a package to live
in and a legal import path. The downward-only rule is set up so that the very
first real import (T2's `from config.schema import Element`) lands in the right
direction. T1 produces **none** of the §5 contracts — it builds the rooms;
T2 moves the furniture (`Element`, `XBRLFact`) in.

## 4. The drill-down (low level) — the two-level Code Walkthrough

This is the mandatory core (Constitution §2): module level, then file level.

### 4a. Module level

- **Modules touched:** `config` and `ingestion` — created, both as skeleton
  packages (a docstring-bearing `__init__.py` and nothing else).
- **Role & data-flow position:** `config` is the shared-contracts/settings floor
  beneath the whole system; `ingestion` is the first/lowest data-flow stage
  (PDF→Element, XBRL→XBRLFact). See the §3 diagram.
- **Inputs / outputs / contracts at the boundary:** none yet. T1 defines no
  functions and constructs none of the seven §5 typed contracts. Its deliverable
  is the *existence and importability* of the two packages, plus the project's
  dependency and test configuration. The contracts (`Element`, `XBRLFact`) are
  named in the package docstrings as a promise, but they arrive in T2.
- **Dependencies introduced:** the four runtime deps (`arelle-release`,
  `docling`, `pydantic`, `pydantic-settings`) declared and locked, and the dev
  dep (`pytest`). None are *imported* yet — they're declared so the locked graph
  is complete and the later tasks can `import arelle`/`import docling` without a
  packaging change.

### 4b. File level

**`pyproject.toml`** — the single declarative manifest; the heart of T1. Walk it
table by table:
- `[build-system]` → `requires = ["hatchling"]`, `build-backend =
  "hatchling.build"`. This is the PEP 517 hook: it tells any installer "to build
  me, use hatchling." Without it there is no defined way to turn the source into
  an installable wheel.
- `[project]` → PEP 621 metadata. `name = "auditagent"`, `version = "0.1.0"`,
  `requires-python = ">=3.13"`, `authors`, and the four runtime `dependencies`.
  The inline comments encode the *why* of each pin (Arelle = numeric path,
  exact-pinned for transform determinism; Docling = narrative path, exact-pinned
  for layout determinism; pydantic = the contracts/settings library). This is
  the standardized, tool-agnostic declaration of "what this project is."
- `[dependency-groups]` → `dev = ["pytest"]`. A PEP 735 dependency group keeps
  the test runner out of the *runtime* dependency set — pytest is needed to
  develop and verify, never to run the shipped agent.
- `[tool.hatch.build.targets.wheel]` → `packages = ["src/config",
  "src/ingestion"]`. The src-layout bridge: it maps the two on-disk source
  folders to the two top-level importable names. This single line is *why*
  `import config` resolves to `src/config/` after an editable install.
- `[tool.pytest.ini_options]` → `testpaths = ["tests"]` (collect from one place)
  and `markers = ["slow: …"]` (register the deselectable marker T10 will use, so
  it is never an "unknown marker" warning).

**`uv.lock`** — generated by `uv lock`, never hand-edited. It is the fully
resolved, hashed, 131-package transitive graph behind the four declared deps.
Committed (not gitignored) because it *is* the reproducibility guarantee: a
fresh clone installs the identical graph. You read `pyproject.toml` to learn
intent; you trust `uv.lock` for the exact bytes.

**`src/config/__init__.py`** — a docstring-only skeleton. The docstring declares
the layer's identity: the lowest layer (§1.6, imports nothing above it), the
future home of `config.schema` (the typed contracts `Element`/`XBRLFact` + the
enums), `config.settings` (one pydantic-settings object, the `FILINGS` map), and
`config.logging`. Its presence is what makes `config` a package; its emptiness is
correct — T1 builds the room, T2/T3 furnish it.

**`src/ingestion/__init__.py`** — a docstring-only skeleton. The docstring
declares ingestion as the bottom of the data flow and the first producer of the
typed contracts, and — importantly — names the **§1.2 structural firewall**: two
*independent* producer paths (PDF → `Element` via `elements`+`sections`; XBRL →
`XBRLFact` via `xbrl`, the sole `XBRLFact` constructor), plus `serialize` and
`pipeline`. It states the import direction (imports `config` only). Again
empty-by-design; the modules arrive in T4/T6/T7/T9/T10.

**`tests/conftest.py`** — minimal, and its *restraint* is the point. The
docstring explains the deliberate choice: conftest does **not** manipulate
`sys.path` to make `config`/`ingestion` importable. If it did, it would mask a
broken install — the test would pass on a path hack rather than on a real
editable install. By staying out of the way, it guarantees the packaging test
proves what it claims. It also notes the corpus fixtures that land later (T3
accession→path fixtures from `config.settings`; T4/T6 session-scoped parsed
fixtures so the expensive parse runs once).

**`tests/unit/test_packaging.py`** — the acceptance check; two tests:
- `test_config_and_ingestion_importable` — `importlib.import_module("config")`
  and `("ingestion")` succeed and report their own names. This is *the* T1
  acceptance criterion: it proves the editable src-layout install resolves both
  top-level imports. Because conftest adds no path hack, the only way this passes
  is a genuine install — the src-layout honesty in action.
- `test_slow_marker_registered` — reads pytest's configured `markers` and asserts
  `slow` is among them. This proves the §4 fast/slow eval tiering has its
  deselectable marker registered *now*, so T10's `@slow` rebuild test is a
  first-class citizen, not an unknown-marker warning.

**The check, run verbatim:**

```
============================= test session starts =============================
platform win32 -- Python 3.13.2, pytest-9.0.3, pluggy-1.6.0
configfile: pyproject.toml
collected 2 items

tests/unit/test_packaging.py::test_config_and_ingestion_importable PASSED [ 50%]
tests/unit/test_packaging.py::test_slow_marker_registered PASSED         [100%]

============================== 2 passed in 0.02s ==============================
```

The named acceptance check
(`test_packaging.py::test_config_and_ingestion_importable`) **passes**; the
companion marker test passes too. T1 touches none of
chunking/retrieval/agent/tools, so the §4.3 cheap-eval tier is **n/a** for this
task.

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| Package layout | **src-layout** (`src/config`, `src/ingestion`) | Flat layout (packages at repo root) | Flat lets `import config` succeed by cwd accident, masking a broken install; src-layout forces the test to prove the *install* (§2) |
| Install mode for the test | **Editable** (`uv pip install -e .`) | Reinstall on every change | Editable keeps the src-layout honesty *and* live-source ergonomics |
| Build backend | **hatchling** | setuptools (`setup.py`/`setup.cfg`) | PEP 621-native, no boilerplate, one-line src-layout package mapping |
| Installer / locker | **uv** (+ committed `uv.lock`) | pip + unpinned transitive graph | A hashed 131-pkg lock makes AC7 "rebuild from committed source" real |
| Arelle / Docling pins | **Exact (`==`)** | Floor (`>=`) or unpinned | Their transform/layout output is determinism-load-bearing (plan Risk (b)) |
| Pydantic pins | **Floor (`>=2`)** | Exact pin | Stable v2 API; want bug-fix freedom; only the v1→v2 major matters |
| `conftest.py` | **No `sys.path` hack** | Inject `src/` onto the path | A path hack would let the test pass without a real install — defeats the point |
| `slow` marker | **Register in T1** | Register when T10 needs it | Pre-registering keeps T10's `@slow` test first-class, not an unknown-marker warning |
| Report tooling deps | **Kept in `reports/requirements.txt`** | Fold into `pyproject.toml` | Doc tooling must not pollute the app's runtime dependency graph |

## 6. Open threads & what's next

**Nothing deferred from T1 itself** — it is a complete, self-contained
bootstrap. A few forward pointers worth holding:

- **The heavy graph is locked but not fully installed.** For this smoke test we
  installed only our own package editable (`--no-deps`) plus `pytest`, to avoid
  pulling Arelle's and Docling's multi-GB subtrees (Docling → torch) before any
  code needs them. The full 131-package graph is *locked* in `uv.lock` and
  installs on demand (`uv sync`) when **T4** (Arelle) and **T6** (Docling) first
  import them. T1's acceptance doesn't require them, so this is correct, not a
  shortcut.
- **The packages are skeletons by design.** `config` and `ingestion` carry only
  docstrings. The first real content is **T2** (`config.schema` — the `Element`
  and `XBRLFact` contracts), which the package docstrings already promise.
- **Markers still live elsewhere:** the §1.3 `[RATIFY]` and the architecture §7
  vendoring wording remain in the docs until **T11** promotes them — by design,
  so they land with the code that makes them true.

**Next SDD step:** `/implement T2` — define the typed contracts in
`config.schema`. I will **not** auto-invoke it; that's the lead's call. The
spec's `status` moved from `tasks` to `implement` with this task and stays there
for the rest of M1.
