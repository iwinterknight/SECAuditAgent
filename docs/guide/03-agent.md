# 03 · The agent — routing, tools, validation, self-correction

> Code: `app/agent.py`. This is the **"agentic"** in Agentic RAG. Entry point:
> `run_agent(question) -> {answer, trace, sources, tool_outputs, reflection, validation}`.

## Plain RAG vs agentic RAG

Plain RAG is a fixed pipeline: *always* embed → retrieve → stuff → answer. That's
wrong for "what was net income in 2024?" — there's nothing to retrieve; there's a
*fact to look up*. An **agent** is given **tools** and decides, per question, which to
call and in what order. "What was net income?" → look up a fact. "What does the firm
say about credit risk?" → search narrative. "How did deposits change?" → look up two
facts *or* call the change tool. That routing is the agent's job.

## The three tools

| Tool | What it returns | Backed by |
|---|---|---|
| `lookup_financial_fact(metric, fiscal_year?)` | the **exact** XBRL figure(s) | the **DuckDB** facts store (docs 01, 07) |
| `compute(operation, metric, …)` | 10 ops — change/%/CAGR, avg/sum/min/max, ratio/%-of/difference | deterministic arithmetic in Python over DuckDB facts |
| `search_filings(query, fiscal_year?)` | narrative passages, FY+page tagged | hybrid: **Qdrant** dense + BM25 (docs 02, 07) |

Two design rules are encoded in the system prompt **and** the code:

- **Numbers only from tools.** *"Use `lookup_financial_fact` for ANY financial number.
  Never state a figure without it."* Figures come from XBRL, not the model.
- **No LLM arithmetic.** *"Use `compute` for ANY arithmetic — never do the
  arithmetic yourself."* `_tool_compute` does the subtraction and percentage in Python
  from XBRL values. LLMs are unreliable at exact arithmetic; this removes the risk
  entirely. (The validator below is what *enforces* both rules.)

`metric` is an **enum** of the eight headline labels (Total assets/liabilities/equity/
deposits, Net income, Total net revenue, Net interest income, Diluted EPS), so the
model can't ask for a metric we don't have a fact for.

## The loop (`_tool_loop`)

Standard OpenAI tool-calling, `temperature=0` (deterministic routing):

```
for step in range(max_steps):           # max_steps = 4
    response = chat.completions(tools=_TOOLS, tool_choice="auto")
    if no tool_calls:  return answer     # model is done → final text
    for each tool_call:
        run the tool, append its result as a {role: "tool"} message
    # loop: the model now sees the tool outputs and decides the next move
```

`tool_choice="auto"` is the router — the model picks. Every call is recorded in
**`trace`** (tool name + args); narrative hits accumulate in **`sources`**; every tool
result string accumulates in **`tool_outputs`** (the validator and reflector read these).

## The validator (`_validate`) — deterministic groundedness

After the answer is written, a **non-LLM** check enforces the fidelity rules:

```python
stated = set(re.findall(r"\d{1,3}(?:,\d{3})+", answer_text))   # comma-formatted numbers
known  = { headline USD values, as millions }                   # exact XBRL facts
ungrounded = [n for n in stated if n not in known and n not in "\n".join(tool_outputs)]
grounded = not ungrounded
```

Every comma-formatted figure in the answer must be **either** a known headline XBRL
value **or** literally present in a tool output (an exact lookup or a `compute`
result). Anything else is flagged `ungrounded` — which catches both a *hallucinated*
number and a *hand-computed* one (the latter is exactly why the agent must call
`compute`). This is the runtime expression of the §1.2 firewall, and the UI
shows its verdict (✅ / ⚠️) on every answer.

## Self-RAG — reflect → revise

A single pass can be shallow or miss a sub-question. After the first answer, a critic
pass (`_reflect`) asks the model, in JSON: *is this answer fully supported by the tool
outputs AND complete?* → `{ok, issue}`.

- `ok: true` → done.
- `ok: false` → the **issue is fed back** and the agent gets another `_tool_loop` turn:
  it can re-search with a sharper query or look up a missing fact, then finalize.

This is the **Self-RAG** pattern — the agent reflects on its own retrieval/answer and
revises. It's bounded (one revise pass) and fails safe: if the reflection call errors,
it defaults to `ok: true` so a critic hiccup never crashes the answer. The UI shows a
"🔁 self-corrected" note when a revise happened.

## The refusal path

The golden set includes "what was the share price on a future date?" The right answer
is **refusal**, not a guess: no tool can supply it, the system prompt says *"if a
number is not available from the tools, say so — never invent one,"* and the validator
would flag a fabricated figure anyway. Knowing the boundary of what it can answer is
part of fidelity.

## What `run_agent` returns (and why each field exists)

```python
{ "answer":       final text,
  "trace":        [{tool, args}, …],   # what it did — shown in UI, judged by eval
  "sources":      [Element, …],        # narrative passages → citations
  "tool_outputs": [str, …],            # evidence → validator + reflector read these
  "reflection":   {ok, issue} | None,  # the Self-RAG verdict
  "validation":   {grounded, ungrounded_numbers, checked} }
```

Everything the agent did is observable — which is what makes the trajectory
**evaluable** (doc 04) rather than a black box.

→ Next: [04 · Evaluation](04-evaluation.md) — how we prove all of this actually works.
