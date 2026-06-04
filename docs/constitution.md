# Constitution — AuditAgent

Principles this project does not violate. Each is concrete and falsifiable —
a reviewer should be able to point at code and say "this violates principle
X." Vague aspirations don't belong here.

When a plan tensions with a principle, the plan's "Risks" section must name
it. When a principle has to bend, that's a constitution change — see the
last section.

Markers used below:
- **[RATIFY]** — a default I (the agent) proposed but that the lead has not
  yet confirmed. Resolve before the relevant module is implemented.

---

## 1. Architectural Principles

### 1.1 Financial fidelity is the dominant value

The system answers questions about real SEC filings. It **must not**
fabricate or miscompute a financial fact. Every numeric or factual claim is
traceable to a source — an XBRL fact, or a retrieved chunk identified by
(filing fiscal year, Item/section, page or chunk id).

This is enforced **structurally**, not by prompt-engineering goodwill:

- The agent graph routes every factual answer through a validator/critic
  edge (§1.4) before it reaches the user. The LLM cannot decide to skip it.
- Any new path that produces a user-visible financial claim **must** route
  through (or replicate) the validator. New shortcuts that bypass it are
  constitution-level changes.

This is the AuditAgent analog of RFI's "data fidelity is the dominant
value."

### 1.2 Numbers come from structured ground truth, not LLM transcription

The numeric/calc path reads figures from the **XBRL fact store** (DuckDB),
never from a number an LLM read off a parsed table or prose. The LLM may
compose the lookup (which fact, which period, which entity) and explain the
result, but it does not transcribe raw figures and does not do arithmetic
on them by itself — a deterministic tool does the math.

Rationale: a transcribed number is itself a hallucination vector. Removing
the LLM from the transcription-and-arithmetic loop removes the largest
source of financial error.

### 1.3 Entity and period disambiguation

Every financial claim is scoped to an **(entity, fiscal period)** pair.

- **Entity.** Default = **JPMorgan Chase & Co.** (the consolidated
  registrant). **JPMorgan Chase Bank, N.A.** (a subsidiary) is a *different*
  entity; figures must not be silently mixed. When a query is ambiguous, the
  system answers for the consolidated registrant and says so.
- **Period.** Balance-sheet ("as of") figures and flow ("for the year")
  figures are distinguished. The fiscal year is explicit in every answer.
- **Restatements.** Each 10-K restates 2–3 prior years and figures can
  differ across filings. **[RATIFY]** Default source-of-truth for fiscal
  year *N* = the 10-K *originally filed for* fiscal year *N* (not a later
  restatement), unless the user explicitly asks for the restated value.

### 1.4 The validator is a hard, structural gate

Before any answer leaves the agent, a validator/critic performs explicit
checks, as a non-skippable edge in the LangGraph graph:

- **Context check** — every claim in the answer is supported by retrieved
  context or an XBRL fact (no outside knowledge, no shifted decimals).
- **Entity check** — consolidated (Co.) vs subsidiary (N.A.) not confused.
- **Numeric check** — figures in the answer match the XBRL ground truth
  within tolerance; arithmetic was done by the calc tool.

A failing check loops the agent back or returns an explicit "cannot ground
this" — it never passes an unverified claim through.

### 1.5 Every claim is cited

Answers carry citations: (filing FY, Item/section, page or chunk id) for
narrative claims; the XBRL fact id for numeric claims. **No citation → no
claim.** This is both UX and the mechanism that makes groundedness
machine-checkable in evaluation.

### 1.6 Layer separation

The system is organized into layers; new code lives in **one** of them.
Imports flow **downward** only.

```
api/        ← chat surface (HTTP/WS), request/response models
agent/      ← LangGraph router, tools, validator
retrieval/  ← hybrid search, rerank, parent expansion
index/      ← Qdrant + DuckDB builders
chunking/   ← parent/child, table-to-text, metadata stamping
ingestion/  ← PDF + XBRL → normalized elements
config/     ← settings, logging, schema, cross-cutting types
eval/       ← golden set, metrics, drift, scheduler (reads telemetry; not in the request path)
```

`api/` may import `agent/`; `agent/` may not import `api/`. A function that
spans more than one layer needs a justifying note in the plan. Do not add a
new top-level module under `src/` without a spec.

### 1.7 Configuration flows through one settings module

New code reads configuration via a single `config.settings` object — never
`os.getenv` scattered through business code. API keys, model names, store
URLs, thresholds (e.g. the groundedness alert floor) live there. Tests are
exempt and may set the environment directly.

### 1.8 Source corpus is read-only at runtime

The application reads PDFs and XBRL; it does not mutate the corpus. New
filings are added by running the ingestion pipeline, not by application
code. Derived artifacts (parsed elements, indices) are rebuildable and live
under gitignored paths; they are never the source of truth.

---

## 2. The Reporting Protocol

**Every completed `/implement` task ends with a Code Walkthrough.** This is a
hard requirement unique to this project, encoding the lead's need for
complete fluency.

The walkthrough has two granularities:

1. **Module level** — which module the task belongs to, its role in the
   architecture and data flow, and what changed at the module boundary
   (inputs, outputs, contracts, dependencies).
2. **File level** — each file and function touched: what it does and *why*
   it exists, in language the lead can re-present top-down to line level.

A task whose code is written but whose walkthrough is missing is **not
done**. The walkthrough is delivered in the `/implement` response and its
substance is captured in the spec's `evaluate.md` when the spec closes.

---

## 3. Code Standards

- **Python 3.13.** Logging via `logger = logging.getLogger(__name__)`. No
  `print` for runtime output.
- **Type hints** on new public functions (parameters and return).
- **New dependencies** are named in the plan's "Risks" section before they
  are added. Favor the ratified stack (`docs/architecture.md`); a new core
  dependency that overlaps an existing one needs justification.
- **`pathlib.Path`** for filesystem paths. `config.settings` exposes the
  project roots; do not hardcode absolute paths.
- **Module organization mirrors §1.6.** No new top-level `src/` module
  without a spec.
- **Determinism where it matters.** Parsing, chunking, indexing, and the
  numeric tool are deterministic and reproducible from source. LLM calls in
  the request path are bounded and logged.

---

## 4. Testing & Evaluation Standards

### 4.1 Unit tests are feature-targeted

A failing test names exactly one feature from its name and path alone.
Generic catch-all tests are not a pattern to follow.

### 4.2 Evaluation is a first-class gate

The evaluation harness (`src/eval/`) is not an afterthought — it gates
retrieval and agent changes. A change to chunking, retrieval, the agent
graph, or a tool is **not done** until the eval suite shows **no regression
versus the last committed baseline** on the golden set (RAG triad +
agent-loop metrics). Baselines live under `eval/baselines/` and are
committed; runs under `eval/runs/` are transient.

### 4.3 Resource-intensive evaluation is tiered separately

Full-golden-set LLM-as-judge runs and re-embedding sweeps are
resource-intensive (LLM billing, compute). They are **named and queued**
for the pre-merge / scheduled gate, not run on every `/implement`. A cheap,
deterministic subset (exact-match numeric checks against XBRL, retrieval
hit@k on a small fixed set) runs per implement.

### 4.4 New behavior requires a test — and retrieval/agent behavior requires a golden-set entry

A feature spec lists the test(s) that prove it. For retrieval/agent
features, "the test" includes one or more golden-set Q/A/context entries
(with XBRL-derived ground truth for numeric questions). The test fails
before the change and passes after.

### 4.5 The full eval + unit suite is the deploy/merge gate

Before merging a module or deploying: the unit suite AND the full
golden-set evaluation must pass (no regression). This is a gate-time check,
not a per-task check.

---

## 5. Security & Privacy Non-Negotiables

### 5.1 Secrets start clean and stay clean

Cloud LLM API keys and any credentials live in `.env` (gitignored) or are
injected by the environment — **never committed to a tracked file**. Unlike
the sibling RFI repo (which carries accepted-risk committed secrets), this
repo starts clean. A committed secret is a constitution violation, not a
debt to tolerate. Provide `.env.example` with key *names* only.

### 5.2 The corpus is public, but the repo stays lean

The 10-K filings are public SEC documents — no PII concerns. But derived
caches and indices are not committed (they bloat history and are
rebuildable). Only source PDFs (LFS) and committed eval baselines belong in
git.

### 5.3 The numeric/calc tool is sandboxed

If the calc tool executes generated code, it runs in a sandbox with no
arbitrary filesystem or network access and a time/row bound. It operates
only over the XBRL fact store and the retrieved context. Code execution
without these bounds is a violation.

### 5.4 Secrets and prompts never leak into logs or telemetry

API keys, full prompts containing secrets, and raw credentials never appear
in logs or the telemetry stream. Telemetry (prompts, retrieved chunk ids,
scores) is for evaluation; scrub anything sensitive at write time.

---

## 6. Definition of Done

A change is "done" when ALL of:

1. **Spec, plan, and tasks files exist** in `specs/<dated-slug>/` and
   reflect the final state. Divergences from the plan are noted in `spec.md`
   (Open Questions or an amendment block).
2. **All tasks in `tasks.md` are checked.** Abandoned tasks are deleted with
   a note or moved to a follow-up spec.
3. **Feature-relevant tests pass** (§4.3) AND, for retrieval/agent changes,
   **the eval suite shows no regression** versus the committed baseline
   (§4.2).
4. **Constitution principles upheld.** Tensions are listed in `plan.md`
   Risks. New violations become amendments, not silent debt.
5. **The Code Walkthrough was delivered** (§2) for every implemented task.
6. **`Spec: <id>` footer** on every commit produced for this spec.
7. **Architecture or constitution updated** if behavior or a principle
   changed. The summary says explicitly which docs changed.
8. **The next-engineer test:** a teammate reading only `spec.md`, `plan.md`,
   `tasks.md`, `evaluate.md`, and the diff can understand what changed and
   why.

---

## 7. How We Change This Document

- Constitution changes require a spec + plan, like any other non-trivial
  change. The spec describes which principle is added/changed/removed and
  why.
- The lead (Sunit) must explicitly approve a constitution change before it
  lands.
- Adding a principle is the lowest-friction change. Removing or weakening
  one needs reasoning recorded in the corresponding spec — what experience
  caused the principle to be reconsidered.
- Mark superseded sections with a one-line note linking to the spec that
  changed them, rather than silently rewriting. The history of *why* is
  more valuable than the cleanliness of the document.
- Resolve every **[RATIFY]** marker before the module it governs is
  implemented.
