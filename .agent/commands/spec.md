# /spec — CLARIFY stage

You are running the CLARIFY stage of the AuditAgent SDD workflow. Your job
is to produce a `spec.md` for a new feature, bug, or design-judgment
change.

## When to use

- The user describes a feature, a non-trivial bug, or any change that
  requires design judgment.
- A trivial change (typo, comment, dependency-pin bump) does NOT need a
  spec — commit directly without invoking this command.

## Required inputs (gather from the user before writing)

You must have concrete answers to all six of these before producing the
spec. If any answer is missing or hand-wavy, ASK before writing:

1. **Who is the user?** An analyst asking the system financial questions,
   an engineer running the eval harness, the lead reviewing fidelity, or
   another component (e.g. the validator consuming retrieval output)? If
   "internal users" — name them.
2. **What is the success criterion?** A single observable outcome that
   tells us "this worked." Not a feeling, an observation. For an answer-
   engine change this is usually a question that now returns a cited,
   correct answer; for an eval change, a metric that now scores.
3. **What is explicitly out of scope?** Two or three concrete things the
   user might assume are in scope but aren't.
4. **What existing code does this touch?** Best guess at the module
   (per `docs/architecture.md` §3 layer map: `ingestion`, `chunking`,
   `index`, `retrieval`, `agent`, `api`, `eval`, `config`) and the files
   within it under `src/`. If unknown, say so — don't fabricate paths.
5. **What could go wrong?** Failure modes, edge cases, and especially
   **fidelity** risks. The Constitution's "Financial fidelity" principle
   (§1.1) means anything that could surface a fabricated or miscomputed
   financial fact — a transcribed number (§1.2), a confused entity (§1.3),
   a mixed period, or an uncited claim (§1.5) — is an automatic risk.
6. **What would make this NOT worth doing?** What discovery during PLAN
   or IMPLEMENT would justify abandoning the spec? This protects against
   sunk-cost decisions later.

If the change touches retrieval, the agent graph, chunking, or a tool,
also ask: **what golden-set entries prove it?** (Constitution §4.4 — a
retrieval/agent behavior is not testable without a Q/A/context entry, and
numeric questions need XBRL-derived ground truth.) The exact entries are
named in PLAN, but flag the need now.

## File written

Exactly one file:

```
specs/<YYYY-MM-DD>-<short-kebab-slug>/spec.md
```

- The date is today's date, not when the work will land.
- The slug is short, kebab-case, and describes the feature noun, not the
  verb. ("table-to-text-summaries" not "fix-table-parsing".)
- If a folder with the same slug already exists for today, append `-2`,
  `-3`, etc.

If a closely-related spec already exists (active or done), surface it —
ask the user whether the new work should be a new spec, a continuation
of the existing one, or an amendment to it.

## Spec template

```markdown
---
id: <YYYY-MM-DD>-<slug>
title: <short title under 80 chars>
status: clarify
module: <ingestion | chunking | index | retrieval | agent | api | eval | config | cross-cutting>
owner: <author short name or email>
created: <YYYY-MM-DD>
related-specs: []
---

# Spec: <title>

## Problem

What is wrong, missing, or worth doing? Two or three short paragraphs.
Ground the description in observable facts: what a user asks today and
what fails, is wrong, or is awkward — not what we'd ideally have. If
there is a prior incident, eval run, or commit that motivates this, link
it.

## Users & Use Cases

Who benefits and what do they do? Concrete: name the user ("an analyst
asking for a specific FY figure"), name the action ("asks for JPMorgan
Chase & Co.'s CET1 ratio in FY2024"), name the moment of pain or gain.

## Behavior

What the system should do once this is built. What, NOT how.
- Functional behaviors (input → output, state changes, side effects).
- Fidelity behaviors if applicable — entity scoping, period handling,
  citation presence, validator outcome.
- Constraints — latency, accuracy thresholds, eval metrics that must not
  regress, what must remain unchanged.
- This section is contractual. PLAN and IMPLEMENT will reference it.

## Out of Scope

Three to five concrete things this spec is NOT doing. Things the
reader might reasonably assume are in scope.

## Open Questions

Anything the spec author can't answer alone. Each question names who
should answer it (lead, contributor, external stakeholder). These must
be resolved before the spec exits CLARIFY. Unresolved [RATIFY] items
from the constitution that this spec depends on go here.

## Acceptance Criteria

A checklist a reviewer can verify. Each item is observable and
specific. Bad: "answers are accurate." Good: "asking for JPMorgan Chase
& Co.'s FY2024 CET1 ratio returns the value from the XBRL fact store,
cited by fiscal year and fact id, within numeric tolerance of the filed
figure."

- [ ] criterion 1
- [ ] criterion 2
- [ ] criterion 3
```

## Forbidden actions

- **Tech choices.** Do not pick libraries, frameworks, models, data
  structures, algorithms, or file paths. Those belong in PLAN.
- **Implementation detail.** Do not describe how the change is built —
  only what observable behavior it produces.
- **Auto-advance to PLAN.** When the spec is written, STOP and ask the
  user to confirm. Do not invoke `/plan` unprompted.
- **Editing source code.** Do not touch any file under `src/` during
  CLARIFY.
- **Inventing file paths.** If you don't know where the change lives,
  write `[unknown — needs discovery in PLAN]` rather than guessing.
- **Proposing a new top-level `src/` module.** That is a constitution-
  level decision (§1.6). If the work seems to need one, name it as an
  Open Question, do not assume it.

## Version control interaction

- Writes only under `specs/`.
- No git commits. The user reviews and commits the spec themselves.
- No interaction with `src/` git state.

## Educator Report (Reporting Protocol — Constitution §2)

Before you tell the user CLARIFY is complete, produce this step's **Educator
Report**. It is mandatory, not a nicety (Constitution §2): a `spec.md`
without its report is not done.

- **File:** `reports/<YYYY-MM-DD-slug>/01-clarify.md`, authored from
  `.claude/skills/sdd-feature-cycle/templates/report-template.md`. Render to
  a sibling PDF with `python reports/render.py
  reports/<slug>/01-clarify.md`. Markdown is the committed source of truth;
  the PDF is rebuildable and gitignored.
- **Voice:** educator. Open at the architecture / domain level and drill
  down to specifics; *teach* the domain rather than summarize the diff.
- **CLARIFY focus:** motivate the problem in the system's terms; teach the
  domain concepts the spec leans on (for an ingestion spec: XBRL, inline
  XBRL and its linkbases, EDGAR and its pull mechanism, accession numbers,
  entity/period fidelity, and the DuckDB-vs-Qdrant split — why numbers come
  from XBRL, not LLM transcription); walk each acceptance criterion with WHY
  it matters and what failure it prevents; explain what is deliberately out
  of scope and why. Surface the trade-off behind every choice the spec
  ratified.

## End-of-stage rules

When the spec file is written:

1. Show the user the file path and a one-paragraph summary of what's in it.
2. List unresolved Open Questions.
3. **Produce the Educator Report** `reports/<slug>/01-clarify.md` (see
   above) and render it to PDF.
4. Tell the user the next step is `/plan` and that you will NOT invoke it.
5. Stop.

A spec exits CLARIFY (status changes from `clarify` → `plan`) only when:

- The user has confirmed the spec is correct.
- The lead (Sunit) has approved it. For specs the lead authors, this is
  implicit.
- All Open Questions are resolved (either inline or with a deferred
  answer noted as "deferred to PLAN" with reasoning).
