---
id: <YYYY-MM-DD>-<short-kebab-slug>
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

What the system should do once this is built. **What, NOT how.** No
file paths, no library/model names, no algorithms.

- Functional behaviors (input → output, state changes, side effects).
- Fidelity behaviors if applicable — entity scoping (Co. vs N.A.),
  period handling (instant vs duration), citation presence, validator
  outcome.
- Constraints — latency, accuracy thresholds, eval metrics that must not
  regress, what must remain unchanged.
- This section is contractual. PLAN and IMPLEMENT will reference it.

## Out of Scope

Three to five concrete things this spec is NOT doing. Things the
reader might reasonably assume are in scope.

- <thing 1>
- <thing 2>
- <thing 3>

## Open Questions

Anything the spec author can't answer alone. Each question names who
should answer it (lead, contributor, external stakeholder). These must
be resolved before the spec exits CLARIFY. Unresolved [RATIFY] items
from the constitution that this spec depends on go here.

- [ ] **Q1** (asks: <person/role>): <question>
- [ ] **Q2** (asks: <person/role>): <question>

## Acceptance Criteria

A checklist a reviewer can verify. Each item is observable and
specific. Bad: "answers are accurate." Good: "asking for JPMorgan Chase
& Co.'s FY2024 CET1 ratio returns the value from the XBRL fact store,
cited by fiscal year and fact id, within numeric tolerance of the filed
figure."

- [ ] AC1: <criterion>
- [ ] AC2: <criterion>
- [ ] AC3: <criterion>

---

<!--
Amendment block. Append below this line if the spec changes after
exiting CLARIFY. Each amendment dated and signed; do NOT silently
edit the body above.

## Amendments

### YYYY-MM-DD — <amendment label>
- What changed
- Why
- Approved by
-->
