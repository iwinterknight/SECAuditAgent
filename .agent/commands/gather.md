# /gather — capture a fact or insight for the presentation

A lightweight capture step used **intermittently during the deep dive**. It appends one
entry to the running context file and then **returns control to the deep dive** — it must
not derail or balloon into a production. Think pit stop, not detour.

Collection file: `docs/presentation/gathered-context.md`

## Steps

1. **Get the content.**
   - If `$ARGUMENTS` is non-empty, treat it as the content to capture.
   - If empty, ask the user exactly one question — *"What should I capture? Paste the
     fact/insight, or point me at what we just covered."* — and **WAIT** for their reply.
     Do nothing else until they answer.
2. **Record faithfully, then enrich.** Capture the user's point as-is. You MAY add one
   precise detail from the current conversation (a `file:line`, a guide-doc link, the
   exact figure) **only if it sharpens and never distorts** their point. If you're unsure
   what they meant, ask before writing.
3. **Append** a new entry to `docs/presentation/gathered-context.md` (create the file with
   the header below if it doesn't exist; **never overwrite** existing entries). Number it
   as the next integer after the last `### [N]` entry already in the file.
4. **Confirm in one line** — `✅ Captured [N]: <title> — N entries so far` — and **stop**,
   so the user can keep reading. Do not summarize or re-explain.

## File header (write only when creating the file)

```
# Gathered context — JPMorgan 10-K Agentic RAG presentation

Running capture from the deep-dive sessions: one fact + its insight per entry.
Compose into a presentation-ready summary with `/collate`.

---
```

## Entry template (keep this format exactly — `/collate` parses it)

```
### [N] <short title, max ~8 words>
- **Category:** <overview | data-ingestion | xbrl | docling | retrieval | agent | evaluation | deployment | ui | decision | lesson | other>
- **Fact:** <the fact, faithfully recorded>
- **Insight:** <the "so what" — why it matters to the audience / what it demonstrates>
- **Source:** <guide doc, topic, or file:line — if known>
```

## Rules
- Append-only; one entry per invocation (unless the user clearly lists several).
- Hold the format exactly, so `/collate` can group and compose reliably.
- Capture and get back to the deep dive — brevity is the whole point.
