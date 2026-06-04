# AGENTS.md — AuditAgent

Canonical entry point for any coding agent working on this project.
Tool-agnostic: read this regardless of whether you are Claude Code,
Cursor, Aider, Continue, Copilot, or anything else.

Tool-specific wiring (slash commands, sub-agents, skills) lives in
`.claude/`, `.cursor/`, etc. Those are thin shims that point back at this
file and the contents of `.agent/`.

---

## Project One-Liner

An **Agentic RAG** system that answers questions about **JPMorgan Chase &
Co.** 10-K filings (FY2021–FY2025) with high financial accuracy, paired
with a decoupled **evaluation** harness that measures retrieval quality,
agent behavior, and drift over time. Local-first. A chat UI and cloud
deployment come last, after the core modules work.

This project is run with the same Spec-Driven Development (SDD) discipline
as the sibling RFI project, with one project-specific addition: a
**Reporting Protocol** (see below) that produces a module-then-file code
walkthrough after every implemented task.

---

## The Two Coupled Domains

AuditAgent is two systems that share a corpus and a telemetry stream:

1. **Agentic RAG** — the answer engine. Ingest → chunk/enrich → index →
   retrieve → a LangGraph agent (router → tools → validator) → cited
   answer. The dominant value is **financial fidelity**: numbers are
   right, entities are not confused, periods are correct, every claim is
   cited.
2. **Evaluation** — the trust engine. A golden test set, the RAG triad
   (context relevance, groundedness/faithfulness, answer relevance),
   agent-loop metrics (tool-call accuracy, trajectory efficiency), and
   automated drift + silent-failure detection. It tells us **which stage
   failed**, not just that an answer was wrong.

---

## Where To Start

Read these in order before doing any work:

1. **`docs/constitution.md`** — the principles this project does not
   violate. Every plan is checked against it.
2. **`docs/architecture.md`** — the target-state map: ratified stack,
   module boundaries, and data flow.
3. **`docs/roadmap.md`** — the module breakdown (M0–M10) and which spec
   implements each module. This is the durable project tracker.

If a spec is in flight, also read its folder under `specs/`.

---

## Repo Layout

Unlike RFI (a parent repo over two child repos), AuditAgent is a **single
repo**: SDD artifacts and source code live together.

```
AuditAgent/
├── AGENTS.md              ← you are here
├── CLAUDE.md              ← thin shim → AGENTS.md
├── README.md
├── .gitattributes         ← Git LFS: *.pdf
├── .gitignore
├── docs/
│   ├── constitution.md    ← the law
│   ├── architecture.md    ← target-state map
│   ├── roadmap.md         ← M0–M10 module tracker
│   └── source-plan.pdf    ← genesis/provenance: the original plan (Git LFS)
├── specs/                 ← one folder per feature: YYYY-MM-DD-<slug>/
│   └── <slug>/
│       ├── spec.md        ← CLARIFY
│       ├── plan.md        ← PLAN
│       ├── tasks.md       ← TASKS
│       └── evaluate.md    ← EVALUATE record
├── .agent/                ← agent-agnostic source of truth
│   ├── commands/          ← spec, plan, tasks, implement, evaluate
│   └── agents/            ← spec-reviewer, implementer
├── .claude/               ← Claude Code wiring (thin shims → .agent/)
│
├── data/
│   └── SEC/10-K Filings/yearly/   ← raw PDFs (Git LFS), + XBRL once pulled
│
└── src/                   ← application code (created module by module)
    ├── ingestion/         ← M1: PDF + XBRL → normalized elements
    ├── chunking/          ← M2: parent/child, table-to-text, metadata
    ├── index/             ← M3: Qdrant vectors + DuckDB facts builders
    ├── retrieval/         ← M4: hybrid search + rerank + parent expansion
    ├── agent/             ← M5: LangGraph router, tools, validator
    ├── api/               ← M6: chat surface
    ├── eval/              ← M7/M8: golden set, metrics, drift, scheduler
    └── config/            ← settings, logging, schema
```

The exact `src/` shape is ratified in `docs/architecture.md` and may be
refined per module spec. Do not invent a new top-level folder without a
spec.

---

## Ratified Decisions

These forks were settled at kickoff (2026-06-04). They are recorded here
and in `docs/architecture.md`. Changing one is a constitution-level change
(spec + lead approval), not a casual edit.

| Decision | Choice |
|---|---|
| Version control | One git repo here; **Git LFS** versions the 10-K PDFs |
| Models | **Hybrid** — local/open embeddings + a cloud LLM for generation & validation |
| Numeric ground truth | **EDGAR XBRL** facts alongside the PDFs (machine-readable figures) |
| Orchestration | **LangGraph** (consistent with RFI) |
| Vector store | **Qdrant** (Docker, local) |
| Structured store | **DuckDB** over XBRL facts |

Still open (pinned in the relevant module's plan): exact embedding model,
exact cloud LLM provider, parser (Docling vs Unstructured), the
restatement source-of-truth default (see Constitution §1.3).

---

## The SDD Workflow

The state machine for any non-trivial change (identical to RFI, minus the
two-repo split):

```
   CLARIFY  ─►  PLAN  ─►  TASKS  ─►  IMPLEMENT (one task)  ─►  EVALUATE
   /spec       /plan      /tasks     /implement                  │
       ▲                                                          │
       └─────────────── if evaluate fails ────────────────────────┘
```

1. **CLARIFY** (`/spec`) — six clarifying questions, then
   `specs/<dated-slug>/spec.md`. Problem, users, behavior (what, not how),
   out-of-scope, open questions, acceptance criteria. **Tech choices are
   forbidden here.**
2. **PLAN** (`/plan`) — reads the confirmed spec + constitution +
   architecture + actual code; writes `plan.md`. Auto-spawns the
   `spec-reviewer`.
3. **TASKS** (`/tasks`) — decomposes the plan into PR-sized, independently
   testable tasks with named files and one-line acceptance checks.
4. **IMPLEMENT** (`/implement T<N>`) — ONE task. Make the change, run its
   acceptance check, **produce the Code Walkthrough** (see below), propose
   a commit ending `Spec: <id>`, wait for approval, commit, STOP. Never
   pushes. Never bundles tasks.
5. **EVALUATE** (`/evaluate <slug>`) — walks the checklist (including the
   **eval-regression gate** for retrieval/agent changes), writes
   `evaluate.md`, bumps to `done` on PASS.

**Rule:** any change that touches behavior, data, the agent graph, or the
eval harness needs a spec before code. Pure typo/comment/dep-pin fixes are
exempt.

---

## The Reporting Protocol (project-specific, non-negotiable)

The lead needs **complete fluency** on every line written, to present the
system at any granularity. Therefore every `/implement` ends with a **Code
Walkthrough** at two levels:

- **Module level** — which module the task belongs to, its role, where it
  sits in the architecture/data-flow, and what changed at the module
  boundary (inputs/outputs/contracts).
- **File level** — each file and function touched: what it does and *why*
  it exists, in plain language a reviewer can re-present.

A task is not "done" until its walkthrough exists. This is encoded in
`docs/constitution.md` §2 and in `.agent/commands/implement.md`.

---

## Commands, Sub-Agents, Skills

Ported from RFI and adapted for the single repo + the two project-specific
additions (Reporting Protocol, eval-regression gate).

| Command | When | Writes |
|---|---|---|
| `/spec` | Start a feature/bug/design change | `specs/<slug>/spec.md` |
| `/plan` | Spec confirmed | `specs/<slug>/plan.md` |
| `/tasks` | Plan confirmed | `specs/<slug>/tasks.md` |
| `/implement T<N>` | Execute ONE task + Code Walkthrough | code in `src/`, `tasks.md` |
| `/evaluate <slug>` | All tasks done; the gate to `done` | `specs/<slug>/evaluate.md` |

| Sub-agent | Purpose |
|---|---|
| `spec-reviewer` | Critiques spec/plan vs constitution. Read-only. |
| `implementer` | One task, run check, walkthrough, propose commit, stop. |

---

## Project-Specific Gotchas

Read before touching code.

### Entity precision is a fidelity issue
"Chase" colloquially means the registrant **JPMorgan Chase & Co.**
(consolidated, ticker JPM) — **not** the subsidiary **JPMorgan Chase Bank,
N.A.** Every financial claim is scoped to an entity. See Constitution §1.3.

### Periods and restatements
Each 10-K restates 2–3 prior fiscal years; a figure can differ across
filings. The source-of-truth-per-fiscal-year policy is a ratified decision
(Constitution §1.3) — do not pick numbers ad hoc.

### Numbers come from XBRL, not the LLM
The calc/numeric path reads figures from the DuckDB XBRL fact store, never
from a number an LLM read off a parsed table. LLM transcription of a figure
is itself a hallucination vector. See Constitution §1.2.

### Commit format
Every commit produced under a spec ends with `Spec: <YYYY-MM-DD-slug>`. The
PDFs are LFS-tracked — ensure `git lfs` is installed before cloning fresh.

### Secrets
Cloud LLM API keys live in `.env` (gitignored) — **never** committed.
Unlike RFI, this repo starts clean; keep it that way. See Constitution §5.1.
