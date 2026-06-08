---
spec: 2026-06-04-ingestion-parsing
stage: implement
report: 04-implement-T8
created: 2026-06-08
---

# Educator Report — IMPLEMENT · M1 Ingestion & parsing (T8 · Firewall guard — the §1.2 structural check)

> **How to read this.** Top-down: first *where* this task sits, then the *domain*
> it encodes (the §1.2 "numbers only from XBRL" firewall, and the crucial idea
> that it is enforced as **type ownership**, not digit absence), then *why the
> check must be AST-based, not a text grep*, then the architecture view and the
> mandatory two-level **Code Walkthrough**. T8 writes no `src/` code — it adds one
> test file — so the walkthrough is of a *guard*, not a producer. By the end you
> should be able to defend why a docstring that names `XBRLFact` must NOT fail the
> test, but an `import` of it into the PDF path must.

---

## 1. Where we are (orientation)

We just finished **T8** of **M1 (Ingestion & parsing)**. The two ingest paths now
both exist: the **XBRL path** (`ingestion.xbrl`, T4) that *constructs* `XBRLFact`s,
and the **PDF path** (`ingestion.elements` T6 + `ingestion.sections` T7) that
constructs `Element`s. T8 is the **structural guard** that makes the Constitution's
most important fidelity rule — §1.2, *numbers come only from XBRL* — true *by
construction* and checked on every run, rather than trusted to code review. Where
**T5** was the first *numeric* gate (the anchor values must be exact), **T8** is
the first *structural* gate (the fact type must live in, and be touched only by,
the right code path). On the data-flow diagram it adds no box; it draws a wall
between the two left-most boxes and proves nothing crosses it.

## 2. The domain in play (teach me)

### 2.1 The §1.2 firewall — "numbers come only from XBRL"

The whole system's credibility rests on one promise: every financial *figure* it
answers with is the exact number the filer tagged in XBRL — never a number an LLM
wrote, never a number lifted off a parsed table. The mechanism that guarantees
this is a **firewall between two code paths**:

- the **XBRL path** reads machine-readable facts (with their declared scale, sign,
  unit, period) and is the *only* place an `XBRLFact` is built; and
- the **PDF path** turns prose and tables into retrievable `Element`s and **never
  produces a figure to answer with** — a number inside an `Element`'s table text
  is there for *retrieval and display*, not as a source of truth.

If those two paths ever shared the fact type — if the PDF path could mint an
`XBRLFact` — the firewall would have a hole, and a parser-misread number could
masquerade as a filed figure. T8 proves the hole doesn't exist.

### 2.2 Type ownership, not digit absence (the subtle, load-bearing point)

The naive way to "check the firewall" would be to grep the PDF path for digits and
fail if any appear. That is both **wrong and useless**: an `Element`'s `text` is a
rendered 10-K table — it is *full* of legitimate digits. The firewall is not about
the absence of numerals; it is about **who owns the fact type**. Concretely:

- the PDF path (`elements.py`, `sections.py`) must **never reference the
  `XBRLFact` type** — not import it, not name it, not construct it; and
- `XBRLFact` must have **exactly one definition site** (`config.schema`), so that
  "constructed only in the XBRL path" is even a meaningful claim — a second
  `class XBRLFact` somewhere would be a second, unguarded firewall.

This reframing — ownership of a *type*, not absence of *digits* — is what makes
the rule checkable precisely instead of by vague vigilance (plan §"firewall").

### 2.3 Why the check must be AST, not text matching

Here is the trap, and why the task specifies AST/import inspection. The docstrings
of `elements.py` and `sections.py` *deliberately name* `XBRLFact` — they teach the
firewall by saying "this module never constructs an `XBRLFact`." A plain text grep
for "XBRLFact" would match those docstrings and **false-fail** the very modules
that are correctly obeying the rule.

The fix is to look at the **abstract syntax tree**, not the text. In the AST, a
mention of `XBRLFact` inside a docstring or comment is an `ast.Constant` (a string
value); a *code reference* is an `ast.Name` (`XBRLFact`), an `ast.Attribute`
(`schema.XBRLFact`), or an `ast.alias` (in an `import`). The test counts only the
latter three. So prose that *explains* the firewall passes; code that *breaches*
it fails. Same idea for the definition check: we look for an `ast.ClassDef` named
`XBRLFact`, which a re-export or a docstring can never be.

## 3. The high-level view (architecture)

T8 adds no module and no `src/` symbol — it is a **test-only** task, a structural
assertion over the source of the `ingestion` layer and the `config.schema`
contract. Nothing in the layer map moves; what changes is that the §1.2 firewall
is now a runnable gate.

```
   config.schema  ──▶  class XBRLFact   (the one definition site)
        ▲                     │
        │ (located via config.schema.__file__ -> .../src)
        │                     │
   tests/unit/test_firewall.py
        │  (1) AST-scan src/ingestion/elements.py + sections.py
        │        -> assert NO code reference to the name "XBRLFact"
        │  (2) AST-scan all of src/**.py for `class XBRLFact`
        │        -> assert exactly one definer, and it is config/schema.py
        ▼
   pass/fail signal  (the §1.2 firewall, enforced every run)
```

- **Consumes:** `config.schema` (only to locate the source tree via its
  `__file__`) and the *source text* of the two PDF-path modules. It imports
  neither `ingestion.elements` nor `ingestion.xbrl` — it reads their files and
  parses them, so it stays fast (no Docling import) and inspects code as written.
- **Produces:** no runtime artifact — a pass/fail signal. Its "output" is the
  guarantee that the firewall holds on every run.
- **Boundary note:** the XBRL path (`ingestion.xbrl`) is intentionally *not*
  constrained — it is the sole legitimate `XBRLFact` producer.

## 4. The drill-down (low level) — the two-level Code Walkthrough

### Module level

- **Module:** `tests/unit` (a structural gate); it inspects `ingestion`'s PDF-path
  source against `config`'s ownership of `XBRLFact`. No `src/` module changed.
- **Role / data-flow position:** the executable form of Constitution §1.2 — a wall
  between the two ingest paths, checked on every run.
- **Boundary change:** none to any contract; the task adds one test file that
  *reads source* and asserts ownership. It constructs nothing and exposes no new
  symbol.

### File level

**`tests/unit/test_firewall.py`** — the firewall guard (the whole task).

- **Module docstring** — teaches the firewall, the type-ownership framing, and the
  AST-not-text rationale (so a future reader doesn't "simplify" it into a grep and
  reintroduce the false-fail).
- `_PDF_PATH_MODULES = ("elements.py", "sections.py")`, `_FACT_TYPE = "XBRLFact"`
  — the inputs as data: which modules are the guarded PDF path, and which type is
  forbidden there.
- `_code_references(source, name)` — parses a file and returns the line numbers
  where `name` appears as a **code identifier**: an `ast.Name`, an `ast.Attribute`
  (`.attr`), or an `ast.alias` (import). String constants (docstrings, comments,
  literals) are excluded by construction — this is the function that makes the
  test precise rather than a grep.
- `_classdef_files(root, class_name)` — walks every `.py` under the source root and
  returns the files that contain a `class <class_name>` (`ast.ClassDef`). Used to
  prove single ownership.
- `test_element_path_never_constructs_xbrlfact` — the named acceptance check.
  Locates the source root from `config.schema.__file__`, then asserts **(1)** the
  two PDF-path modules have zero code references to `XBRLFact`, and **(2)**
  `XBRLFact` is defined in exactly one file, `config/schema.py`. Together these
  are non-vacuous: importing the type into the PDF path fails (1); deleting or
  duplicating the type fails (2).

## 5. Decisions & trade-offs

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| What "firewall" means | **type ownership** (no `XBRLFact` in the PDF path; one definition site) | digit absence in the PDF path | `Element` table text legitimately contains digits; ownership is the real invariant (§2.2) |
| How to check references | **AST** (`Name`/`Attribute`/`alias`) | text grep for "XBRLFact" | the PDF-path docstrings name `XBRLFact` to teach the rule; a grep would false-fail them (§2.3) |
| Single ownership | assert exactly one `ast.ClassDef` named `XBRLFact`, in `config.schema` | trust there's only one | a second definition would be a second, unguarded firewall; non-vacuity also catches deletion |
| Reading the code | parse the **source files** (via `config.schema.__file__` -> `src/`) | `import` the modules and introspect | avoids importing Docling (fast), and inspects code *as written* |
| XBRL path | deliberately **unconstrained** | also forbid `XBRLFact` there | `ingestion.xbrl` is the sole legitimate producer — constraining it would break the design |
| Test shape | one named test, two structural assertions | two separate tests | the acceptance names one test; the two checks are one indivisible invariant |

## 6. Open threads & what's next

- **The firewall is now enforced.** Constitution §1.2 is no longer policy-only; any
  future change that imports `XBRLFact` into the PDF path, or adds a second
  definition of it, turns the build red. The plan's "§1.2 complies by construction"
  claim is now backed by a test.
- **No new `[RATIFY]`/`[VERIFY]` markers**; no contract touched; nothing discovered
  that splits the task (`tasks.md` "Discovered work" stays empty).
- **Next:** the high-value path remains **T9 (serialize) -> T10 (pipeline)**, which
  persists the bake-ready `data/derived/` corpus (the parse-once, Docker-ready
  artifacts the lead asked for), runs the single slow parse exactly once, and
  lights up the relocated real-corpus Item test from T7. T11 (doc-promotions) and
  the EVALUATE pass close out M1. Run `/implement T9` when ready.
