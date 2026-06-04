# CLARIFY checklist — six questions that must have concrete answers

Before a `spec.md` exits CLARIFY, every question below must have a
**concrete** answer. Hand-wavy answers ("the analyst", "accurate",
"soon", "some questions") trigger a follow-up. The cost of clarifying is
one conversation; the cost of building the wrong thing is days. Push.

These six map to the spec template sections, so resolving them produces
a complete spec.

---

## Q1 — Who is the user?

A specific role, named. Not "the user", not "internal users", not
"someone".

**Probes:**
- Is this an analyst asking the system financial questions? An engineer
  running the eval harness? The lead reviewing fidelity? Another
  component on the request path (e.g. the validator consuming retrieval
  output)?
- If "internal", which person or which role? Does it cross concerns
  (answer engine vs eval)?
- If multiple, which is primary and which is secondary?

**Bad:** "users will get better answers."
**Good:** "an analyst asking the CLI a single financial question about a
JPMorgan Chase & Co. 10-K. The eval engineer is a secondary user who
scores the same answers offline."

→ Goes into spec.md "Users & Use Cases."

---

## Q2 — What is the success criterion?

A single observable outcome. Past-tense, observable, measurable. The
person reading this six months from now should be able to verify it
without context.

**Probes:**
- What does the user **do differently**, or what does the system **now
  answer**, after this is built?
- What can be **measured** — a numeric match against XBRL, retrieval
  hit@k, a RAG-triad score, a latency, a test pass?
- Is there a "this clearly works" question we'd want to demo?

**Bad:** "the system is more accurate."
**Good:** "asking for JPMorgan Chase & Co.'s FY2024 CET1 ratio returns
the value from the XBRL fact store, cited by fiscal year and fact id,
within tolerance of the filed figure — and the eval's exact-match
numeric check passes on that question."

→ Goes into spec.md "Acceptance Criteria" (often as several specific
items derived from this one outcome).

---

## Q3 — What is explicitly out of scope?

At least three concrete things the user might assume are in scope but
aren't. If the author can't think of three, they haven't thought hard
enough about boundaries.

**Probes:**
- Adjacent capabilities that often come up in the same conversation but
  aren't being built here (e.g. multi-hop reasoning, a new filing year,
  a chart)?
- Entities/periods NOT being served (e.g. the N.A. subsidiary, restated
  figures)?
- Improvements to an adjacent module this work won't touch?
- "We could also do X" — write X here as not-doing.

**Bad:** "out of scope: anything not described above."
**Good:**
- "Answering for JPMorgan Chase Bank, N.A. (subsidiary) — Co. only."
- "Restated figures — original-filing source-of-truth only (§1.3)."
- "Narrative 'why' questions — this spec is numeric lookup only."
- "The chat UI — that's M9."

→ Goes into spec.md "Out of Scope."

---

## Q4 — What existing code does this touch?

Best-guess module + paths under `src/`. The author should have actually
opened the architecture doc and the candidate files before answering.
"I'm not sure" is acceptable but triggers a discovery step in PLAN —
flag it explicitly.

**Probes:**
- Reference `docs/architecture.md` §3 (Module map). Which layer does
  this live in: `ingestion`, `chunking`, `index`, `retrieval`, `agent`,
  `api`, `eval`, or `config`?
- Which typed contract in §5 does it produce or consume (Element,
  XBRLFact, Chunk, RetrievedContext, AgentState, Citation,
  TelemetryEvent)?
- Does it touch a store — Qdrant, DuckDB — or the golden set?
- Does it sit on the request path (and therefore the validator and
  citations apply) or off it (eval)?

**Bad:** "the retrieval code somewhere."
**Good:** "`src/retrieval/hybrid.py` (add the FY/entity metadata filter)
and `src/index/clients.py` (expose the filter fields on the Qdrant read
client). Produces a filtered `RetrievedContext`. On the request path."

→ Informs spec.md framing; lands in plan.md "Affected files."

---

## Q5 — What could go wrong?

Failure modes, edge cases, and especially **fidelity** risks. Apply the
project-specific lenses:

**Probes (always ask these):**
- **Financial fidelity (§1.1):** could this surface a fabricated or
  miscomputed financial fact into a user-visible answer?
- **Numbers from XBRL (§1.2):** does any figure come from a parsed table
  or LLM transcription instead of the DuckDB XBRL store? Does any
  arithmetic happen in the LLM instead of the calc tool?
- **Entity/period (§1.3):** could Co. (consolidated) and N.A.
  (subsidiary) be confused? Could a balance-sheet instant be mixed with
  a flow duration? Could a restated figure be returned when the original
  was meant?
- **Validator gate (§1.4):** does this add a claim-producing path that
  could bypass the validator edge?
- **Citations (§1.5):** could a claim ship without a citation?
- **Layer separation (§1.6):** does this require an upward import?
- **Settings (§1.7):** does this read config? Via `config.settings`?
- **Secrets (§5.1):** does this need a new secret? (It must not be
  committed.)

**Probes (AuditAgent-specific):**
- Empty/missing XBRL facts for a requested concept or year.
- A query that names no fiscal year (which FY do we answer for?).
- A dense financial table that parses poorly.
- A partial index (rebuild in progress).
- A validator that loops to max-iterations (silent-failure signal).

**Bad:** "nothing should go wrong."
**Good:** Three to five concrete failure modes with one-line expected
behavior each.

→ Lands in spec.md "Behavior" (constraints + edge-case behavior) and
plan.md "Edge Cases" / "Risks."

---

## Q6 — What would make this NOT worth doing?

What discovery during PLAN or IMPLEMENT would justify abandoning the
spec? This protects against sunk-cost pressure later.

**Probes:**
- If we discover the change requires editing X (a deprecated path, a
  constitution-violating area, a missing module dependency), do we still
  proceed?
- Is there a measurement (e.g. an eval-baseline regression that can't be
  recovered) that, if it comes back unfavorable, kills the work?
- Is this contingent on something external (an unresolved [RATIFY]
  decision, a dependency choice pending in a later module, EDGAR
  availability)?

**Bad:** "we'll definitely do this."
**Good:** "If the XBRL facts for the requested concept aren't present
for all five fiscal years, numeric lookup can't be grounded — we'd need
an ingestion spec first. Abandon and create the ingestion spec."

→ Goes into spec.md "Open Questions" if conditional, or into the spec's
"Problem" framing if it's a known constraint.

---

## Also ask, for retrieval / agent / chunking changes

If the change touches retrieval, the agent graph, chunking, or a tool,
ask: **what golden-set entries prove it?** (§4.4 — these behaviors are
not testable without a Q/A/context entry; numeric questions need
XBRL-derived ground truth.) The exact entries are authored in PLAN/TASKS,
but flag the need now so the spec's Acceptance Criteria account for it.

---

## After all six are answered

- Confirm the module this work belongs to (`module:` frontmatter): one
  of `ingestion`, `chunking`, `index`, `retrieval`, `agent`, `api`,
  `eval`, `config`, or `cross-cutting`.
- Confirm the owner (your short name).
- Confirm there's no closely-related in-flight spec under `specs/` that
  this should be merged into instead.
- Confirm no unresolved [RATIFY] item the spec depends on is being
  silently assumed — if one is, it's an Open Question.

Then write spec.md and stop. No tech, no implementation detail, no PLAN
content leaking back.
