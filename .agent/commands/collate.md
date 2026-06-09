# /collate — compose the gathered context into a presentation-ready summary

Reads the running capture file and synthesizes a report/summary **directly usable to
build a talk of ≤ 40 minutes**. Synthesis, not concatenation: group, dedupe, and surface
the **key insights** — the user cares about insights into the gathered material, not a
raw fact dump.

- **Spine (primary source):** `docs/presentation/gathered-context.md` — it reflects what
  the user found notable, so it sets the priorities and the narrative.
- **Enrichment (secondary):** you MAY pull accuracy/completeness from `docs/guide/*` and
  the actual code, but never bury the gathered insights under generic filler.
- **Output:** `docs/presentation/summary.md`.

## Steps

1. **Read** `docs/presentation/gathered-context.md`. If missing or empty, tell the user
   there's nothing gathered yet, point them at `/gather`, and stop.
2. **Synthesize.** Group entries by theme, merge duplicates, reconcile or surface
   contradictions, and lift the recurring/strongest points into headline insights. Fill
   obvious narrative gaps from the guide docs so the story is complete.
3. **Calibrate to ≤ 40 minutes.** Budget ~1.5–2 min/slide → roughly 15–22 slides, 6–8
   sections; cut to the strongest narrative rather than overstuffing. If `$ARGUMENTS`
   sets a different length or focus (e.g. "25 min", "focus on evaluation"), honor it.
4. **Write `docs/presentation/summary.md`** with this structure:
   - **Title + one-line thesis** — the whole project in a sentence.
   - **Executive summary** — 3–5 sentences: problem → approach → why it's trustworthy →
     result.
   - **Talk flow** — a slide-by-slide table: `# · Section · Minutes · Key points · The
     line to say`. Minutes MUST sum to ≤ the target. This is what the user turns straight
     into slides.
   - **Section detail** — per section: the key facts, the insight, and a crisp "what to
     say"; pull verbatim-worthy one-liners from the deep dive where they exist.
   - **Key insights / takeaways** — a prominent shortlist (the gathered insights,
     sharpened). This is the heart of the report.
   - **Anticipated Q&A** — likely audience questions (seed from the doubts raised during
     the deep dive) with tight answers.
   - **Appendix — gathered facts** — the raw entries verbatim, for reference.
5. **Report back:** where it wrote, the section count, the total minutes, and one line on
   what to tighten. Offer to generate a `.pptx` from it (via the pptx skill) if wanted.

## Rules
- Insight-first: every section ends with a sayable takeaway, not just data.
- Ground every claim in the gathered file + the real docs/code; if a gathered note
  conflicts with the code, flag it rather than smoothing it over.
- Read-only on `gathered-context.md` — do not modify the capture file.
