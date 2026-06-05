---
spec: <YYYY-MM-DD-slug>          # back-reference to the spec folder
stage: <clarify | plan | tasks | implement | evaluate>
report: <NN-stage>               # 01-clarify, 02-plan, 03-tasks, 04-implement-T<N>, 05-evaluate
created: <YYYY-MM-DD>
---

# Educator Report — <stage, upper-case> · <spec title>

> **How to read this.** This report is written for the lead's 360°
> understanding of AuditAgent. It starts at the architecture / domain level
> and drills down to the specific files and what their code does. It teaches
> the domain — defining and motivating the terminology, not just listing the
> diff. Read it top-to-bottom to go from "why" to "how" to "exactly what."
>
> Markdown is the source of truth; the sibling `.pdf` is rendered from it by
> `reports/render.py` and is rebuildable (gitignored). Delete the prose
> guidance in this template as you fill each section.

---

## 1. Where we are (orientation)

*One short paragraph. Which SDD step just finished, for which spec/module,
and where that module sits on the roadmap (`docs/roadmap.md` M0–M10) and in
the data flow (`docs/architecture.md` §4: ingest → chunk → index → retrieve
→ agent → answer). Why this step mattered. The reader should be able to point
at the system diagram and say "we are here."*

## 2. The domain in play (teach me)

*The teaching core. Define and motivate every concept this step engaged, from
first principles — assume the reader wants fluency, not a reminder. Pull in
the standing explanations where relevant and keep them with the step that
used them:*

- *Data & sources: XBRL, inline XBRL (iXBRL) and its linkbases, EDGAR and its
  pull mechanism, accession numbers, CIK, us-gaap concept tags, period type
  (instant vs duration), entity scoping (JPMorgan Chase & Co. consolidated vs
  JPMorgan Chase Bank, N.A.), restatements.*
- *Stores & why: the DuckDB-vs-Qdrant split (exact numeric SQL vs semantic
  vector search) and why numbers come from XBRL, never LLM transcription.*
- *System design: RAG (parent/child chunking, hybrid retrieval, rerank,
  parent expansion), the LangGraph agent (router → tools → validator), the
  evaluation harness (RAG triad, agent-loop metrics, drift).*
- *Frameworks & packages: name each library this step leaned on and what it
  buys us over the alternative.*

*Only cover what this step actually touched — but cover it deeply.*

## 3. The high-level view (architecture)

*Zoom out before zooming in. Where the step's work sits in the layer map
(`docs/architecture.md` §3, downward-only imports), which typed contracts
(§5: Element, XBRLFact, Chunk, RetrievedContext, AgentState, Citation,
TelemetryEvent) it produces or consumes, and the shape of the decision space.
A diagram-in-prose of inputs → this step → outputs.*

## 4. The drill-down (low level)

*Stage-specific. Use the focus for the stage this report covers:*

- **CLARIFY** — *walk the spec: the problem in observable terms, the
  behavior contract, and each acceptance criterion with WHY it matters and
  what failure it prevents. Name what's deliberately out of scope and why.*
- **PLAN** — *walk the approach paragraph by paragraph; for every fork, the
  alternative considered and the one-line reason it lost; the constitution
  tensions in Risks; the test strategy (cheap deterministic tier vs queued
  heavy tier).*
- **TASKS** — *walk the decomposition: why these task boundaries (one concern
  each), the ordering and dependencies, and what each task's acceptance check
  decisively proves.*
- **IMPLEMENT** — *this is the two-level Code Walkthrough (Constitution §2),
  and it is mandatory:*
  - ***Module level*** — *which module, its role and data-flow position, and
    what changed at the module boundary (inputs, outputs, contracts,
    dependencies) — referencing the §5 contracts by name.*
  - ***File level*** — *each file and function touched: what it does and WHY
    it exists, in language the lead can re-present top-down to line level. An
    explanation, not a diff dump.*
- **EVALUATE** — *what was verified and the evidence: acceptance criteria
  results, the cheap-eval / golden-set outcomes, the eval-regression gate vs
  the committed baseline, and what the numbers prove (or where they fell
  short).*

## 5. Decisions & trade-offs

*A consolidated table of the forks this step took. Chosen vs rejected, with
the one-line reason. This is what the lead defends in a design discussion.*

| Decision | Chosen | Rejected alternative | Why |
|---|---|---|---|
| <fork> | <choice> | <alternative> | <one-line reason> |

## 6. Open threads & what's next

*What this step deferred (Open Questions, `[RATIFY]` / `[VERIFY:]` markers
still live), any risk being carried forward, and the next SDD step the lead
should invoke (e.g. "next: `/plan`").*
