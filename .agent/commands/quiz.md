# /quiz — interactive Q&A over the project guide

Run an interactive learning session over `docs/guide/` (the seven building-block docs)
to build the user's fluency to **present** this project. Ground everything in the real
docs and code — read them, never wing it.

## Default mode — Socratic quiz (you ask, the user answers)

1. **Scope.** If `$ARGUMENTS` names a doc or topic — a number `00`–`06`, or a keyword
   like `retrieval`, `agent`, `eval`, `firewall`, `docker` — read that doc and quiz on
   it. If empty, run a **progressive mix**: start at the spine (00 overview, 01 data
   foundation), then escalate to specifics (02 retrieval, 03 agent, 04 eval), then
   nuances (06 decisions & war stories).
2. **Ask 3–5 questions per round**, graduated easy→hard, mixing three kinds:
   - *recall* — "what is RRF, and why use rank not score?"
   - *reasoning* — "why do numbers come from XBRL and not the parsed PDF?"
   - *presentation* — "explain the firewall to a skeptical auditor in three sentences."
3. **Stop and wait** for the user's answers. Never answer your own questions in the
   same turn.
4. **Grade each answer** ✅ solid / 🟡 partial / ❌ gap: quote what they nailed, fill any
   gap with the precise fact (cite the guide doc *and* the code symbol, e.g.
   `app/retrieval.py:_parent_expand`), and add one deeper "so what" they could say on
   stage.
5. **Track weak areas** in a running tally; circle back to them in later rounds. Keep a
   light running score.
6. **After each round**, offer: `continue` · `harder` · `go deeper on X` ·
   `switch to office-hours`.

## Office-hours mode (the user asks, you answer)

If the user says "office hours" / "let me ask" / poses their own question, flip: answer
from the guide **and the actual code** (read the module, cite `file:line`), high→low —
then offer to quiz them back on what you just covered to lock it in.

## Rules

- If the doc and the code ever disagree, surface it rather than papering over it.
- Tight and conversational — coaching, not lecturing.
- The goal is **presentation fluency**: every grade ends with the crisp, sayable version.
