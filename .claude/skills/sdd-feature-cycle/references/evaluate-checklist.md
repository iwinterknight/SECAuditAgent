# EVALUATE checklist — the gate between IMPLEMENT and "done"

EVALUATE is mandatory. Per Constitution §6 (Definition of Done — eight
items), it is NOT enough that "tests pass." A spec is not done until
every item below is verified — including the **eval-regression gate** for
retrieval/agent/chunking changes and the **Code Walkthrough** for every
implemented task.

EVALUATE failure does NOT mean "patch the code and re-evaluate." A
failing item often means the plan was wrong, not the code. See
§"On failure" below.

This checklist maps to the eight Definition-of-Done items:

| DoD §6 item | Covered by |
|---|---|
| 1. spec/plan/tasks exist & reflect final state | Sections A, G |
| 2. all tasks checked | Section G |
| 3. feature tests pass AND (retrieval/agent) eval no-regression | Sections B, C |
| 4. constitution upheld | Section D |
| 5. Reporting Protocol: walkthroughs + per-step Educator Reports | Section F |
| 6. `Spec: <id>` footer on every commit | Section D (footer audit) |
| 7. architecture/constitution updated if changed | Section E |
| 8. next-engineer test | Section H |

---

## How to use this checklist

Walk every item in order. For each:

- **PASS** — verified, with one-line evidence.
- **FAIL** — what's wrong, in one line.
- **N/A** — only when genuinely not applicable, with one-line reason.

Append the run to `specs/<slug>/evaluate.md` — the EVALUATE record is
auditable later. Use the section tables defined in
`.agent/commands/evaluate.md`'s template. Overall:

```markdown
## EVALUATE — YYYY-MM-DD

(Sections A–H per the evaluate.md template)

**Outcome:** <PASS — bumping to done | FAIL — looping back>
**Notes:** <one-paragraph human summary>
```

---

## Section A — Acceptance Criteria

For each AC in `spec.md`, verify it's observably satisfied by the
implemented change. The AC is the contract; nothing else can stand in.

- [ ] **A.1** — Every AC item from `spec.md` Acceptance Criteria section
      maps to an EVALUATE entry with a PASS.
- [ ] **A.2** — Each AC was verified using the test or cheap-eval check
      named in `plan.md`'s Test Strategy table. (If a different
      verification was used, the deviation is noted.)
- [ ] **A.3** — No AC was silently dropped. If one was descoped, the
      spec carries an amendment block recording the descope.

---

## Section B — Tests & Evaluation

Per Constitution §4:

- [ ] **B.1** — Feature-relevant unit tests pass:
      `python -m pytest tests/unit -q` (full run is OK if the suite is
      small and fast; otherwise run only the named modules).
- [ ] **B.2** — The cheap deterministic eval tier passes if the change
      touched chunking/retrieval/agent/tools: exact-match numeric vs
      XBRL, and/or retrieval hit@k on the small fixed set (§4.3).
- [ ] **B.3** — The heavy eval tier (full-golden-set LLM-as-judge,
      re-embedding sweeps) is **named and queued** for the pre-merge /
      scheduled gate (§4.3). It does NOT need to run as part of EVALUATE;
      it needs to be listed. (Status: queued, run + passing, or N/A.)
- [ ] **B.4** — Tests AND golden-set entries required by the Test
      Strategy that did NOT exist at PLAN time DO exist now (and pass).
      New tests/entries are not optional follow-ups (§4.4).
- [ ] **B.5** — No test or golden-set entry was disabled, marked `@skip`,
      or otherwise neutered to make this work go green.

---

## Section C — Evaluation regression gate (retrieval / agent / chunking)

This is the §4.2 gate. If the change touched retrieval, the agent graph,
chunking, or a tool, a green unit suite is NOT sufficient.

- [ ] **C.1** — The full golden-set evaluation (RAG triad: context
      relevance, groundedness, answer relevance; + agent-loop metrics:
      tool-call accuracy, trajectory efficiency) shows **NO regression**
      vs the last committed baseline in `eval/baselines/`, compared
      metric-by-metric.
- [ ] **C.2** — Any intended baseline movement is an improvement, is
      recorded (which metric, why), and the committed baseline was
      updated deliberately — not silently overwritten by a transient run
      from `eval/runs/`.
- [ ] **C.3** — No silent-failure signal regressed: groundedness stays
      above the alert floor (§1.7 names it in settings); the agent does
      not newly loop to max-iterations.
- [ ] **C.4** — If the change touches none of retrieval/agent/chunking/
      tools, this section is N/A with a one-line reason.

---

## Section D — Constitution principles

Walk the principles named in `plan.md`'s Risks section AND any others the
implementation actually touched. For each, "complies / tensions mitigated
/ violates":

- [ ] **D.1** — Each principle the plan named under Risks: still complies
      (or tension still mitigated as the plan said).
- [ ] **D.2** — Principles the plan didn't name but the implementation
      actually touched: also complies. (E.g. plan didn't mention §1.7 but
      the implementation reads config — verify it goes through
      `config.settings`.)
- [ ] **D.3** — No new constitution violations introduced. Explicit
      checks for the high-risk surfaces:
      - **§1.1 / §1.2 Fidelity & XBRL:** any user-visible figure traces
        to an XBRL fact via the deterministic calc tool — no LLM
        transcription, no LLM arithmetic on figures.
      - **§1.3 Entity/period:** Co. (consolidated) vs N.A. (subsidiary)
        not confused; instant vs duration not mixed; restatement
        source-of-truth rule applied.
      - **§1.4 Validator:** the validator/critic remains a non-skippable
        edge; no new claim-producing path bypasses it.
      - **§1.5 Citations:** every user-visible claim carries a Citation
        (narrative tuple or `xbrl_fact_id`).
      - **§1.6 Layers:** no upward imports introduced (imports flow
        downward only); no new top-level `src/` module without a spec.
      - **§1.7 Settings:** new config goes through `config.settings`.
      - **§5.1 Secrets:** no new secret in `.env` or any tracked file;
        `.env.example` (if changed) carries key names only.
- [ ] **D.4** — `Spec: <id>` footer present on every commit produced
      under this spec. Run on the single trunk:
      ```
      git log -G "Spec: <id>"          # or: git log --grep="Spec: <id>"
      ```
      (One repo, one trunk — no parent/child or origin/dev vs origin/main
      split. The lead's working branch may carry extra commits — audit
      the trunk.)

---

## Section E — Documentation

Per Constitution §6.7:

- [ ] **E.1** — If a module boundary or a typed contract
      (`docs/architecture.md` §5: Element, XBRLFact, Chunk,
      RetrievedContext, AgentState, Citation, TelemetryEvent) changed,
      `architecture.md` is updated in this change. Common cases:
      - Module map (§3) — if a layer's role or dependency changed.
      - Ratified stack (§2) / Open decisions (§9) — if an open choice was
        settled (e.g. the embedding model or LLM provider was pinned).
      - Sharp edges (§10) — if a fidelity hazard was fixed or introduced.
- [ ] **E.2** — If a constitution principle was changed, weakened, or
      strengthened, `docs/constitution.md` reflects the change AND that
      change went through its own spec (Constitution §7).
- [ ] **E.3** — If a module reached its "done when" bar,
      `docs/roadmap.md` has that module's row flipped to `done` (and its
      spec folder linked).
- [ ] **E.4** — The spec summary states explicitly which docs changed
      (or "none").

---

## Section F — Reporting Protocol (Constitution §2 / §6.5)

The project's defining requirement. Answer honestly:

- [ ] **F.1** — A **Code Walkthrough** was delivered in the `/implement`
      response for EVERY implemented task (not just the last one).
- [ ] **F.2** — The walkthrough substance is captured in this
      `evaluate.md` at both granularities, so this record is the durable
      artifact:
      - **Module level** — which module(s) changed, their role and place
        in the data flow, and what changed at each module boundary
        (inputs/outputs/contracts/dependencies, referencing §5).
      - **File level** — each file and function touched: what it does and
        WHY it exists, in language the lead can re-present top-down.
- [ ] **F.3** — The per-step **Educator Reports** exist under
      `reports/<slug>/`: `01-clarify`, `02-plan`, `03-tasks`, one
      `04-implement-T<N>` per task, and `05-evaluate`. Markdown is the
      committed source of truth; the rendered PDFs are gitignored.

A spec whose tasks shipped without walkthroughs — or whose per-step
Educator Reports are missing — is NOT done.

---

## Section G — Spec folder hygiene

- [ ] **G.1** — `tasks.md`: every task is `[x]`. Tasks dropped mid-flight
      have a one-line note explaining (e.g., "moved to follow-up spec
      2026-06-12-foo") OR are deleted with reasoning in the spec
      amendment block.
- [ ] **G.2** — `tasks.md` "Discovered work" items are either handled
      (and marked done) or moved to a follow-up spec (with the spec ID
      linked).
- [ ] **G.3** — `spec.md` Open Questions are all resolved (answered
      inline) or removed (if no longer relevant). No unresolved [RATIFY]
      dependency was silently assumed.
- [ ] **G.4** — `spec.md` "Behavior" matches what was actually built. If
      the implementation diverged, an amendment block at the bottom of
      spec.md records the divergence and why.
- [ ] **G.5** — Spec frontmatter `status` is ready to bump to `done`.

---

## Section H — Next-engineer pass

The hardest section, and the most valuable. Answer honestly:

- [ ] **H.1** — A teammate who has not been in this conversation, reading
      only `spec.md`, `plan.md`, `tasks.md`, `evaluate.md`, and the diff,
      could understand WHAT was built and WHY. (Not "they could figure it
      out" — they could read it once and get it.)
- [ ] **H.2** — Variable, function, and component names match what they
      do. No "tmp", no "x2", no "newRetrieve" living next to the old
      "retrieve".
- [ ] **H.3** — Comments (where present) say WHY, not WHAT. The WHAT is in
      the code; only WHY needs explanation.
- [ ] **H.4** — No commented-out code. Dead code is deleted.
- [ ] **H.5** — Logging uses `logger = logging.getLogger(__name__)`. No
      `print` for runtime output (Constitution §3).
- [ ] **H.6** — If a `[RATIFY]` or `[VERIFY: ...]` marker was introduced
      or relied on during PLAN or IMPLEMENT, it's either resolved now or
      carried forward with a one-line note about why.

---

## On failure

If ANY item is FAIL, the spec is not done. Do not silently fix in place —
that pattern hides the failure mode.

Three explicit options for the user:

1. **Refine the implementation** (the design was right; the code missed
   something). Loop back to IMPLEMENT, picking up the relevant task or
   creating a follow-up task.

2. **Refine the plan** (the design was wrong; we built the wrong thing).
   Loop all the way back to PLAN. This is the most uncomfortable option
   and the one most often correct when several AC items fail at once, or
   when the eval-regression gate (Section C) fails because the approach
   moved a baseline metric the wrong way. Update plan.md, regenerate
   tasks.md (or amend it), re-implement what changed, re-evaluate.

3. **Refine the spec** (the requirements were wrong; we discovered
   something during implementation that invalidates the spec). Loop to
   CLARIFY. Update spec.md (with an amendment block), then re-PLAN from
   there. Use this when the failure surfaces a "we shouldn't have wanted
   this" or "the user actually wants something different."

Plus a fourth option that's sometimes correct:

4. **Abandon.** The discovery during EVALUATE shows this isn't worth
   finishing. Close the spec by appending an amendment block that names
   the abandonment reason and what state the code was left in. Status
   stays where it was; the spec is not marked `done`. Future search can
   find it by reason.

The orchestrating skill (`SKILL.md`) surfaces these four options and lets
the user choose. Don't auto-select.

---

## When EVALUATE PASSES

1. Append the EVALUATE record to `specs/<slug>/evaluate.md` (including the
   captured Code Walkthrough substance, Section F).
2. Bump `spec.md` frontmatter `status: implement` → `status: done`.
3. Note the closing date (`closed: <YYYY-MM-DD>`).
4. If a module reached its "done when" bar, flip its `docs/roadmap.md`
   row to `done` and link the spec folder.
5. Tell the user the spec is done. Do NOT auto-start a new spec.
