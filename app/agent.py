"""The agentic layer — an OpenAI tool-calling agent over the 10-K corpus.

This is the "agentic" in Agentic RAG: instead of a single fixed RAG call, the
model is given **tools** and decides — per query — which to call and in what order
(the router), calls them in a loop, then answers. A **validator** then checks that
every headline financial figure in the answer matches an exact XBRL fact.

Three tools:
- ``lookup_financial_fact`` — the EXACT figure JPMorgan filed in XBRL (FY2021-2025).
  The agent is told to use this for any number, so figures never come from the model.
- ``compute`` — deterministic financial calculations over the figures (change,
  percent_change, cagr, average, sum, min, max, ratio, percent_of, difference) — every
  number computed in code, never LLM arithmetic.
- ``search_filings`` — hybrid (dense + sparse) narrative retrieval over the parsed
  FY2021-2025 10-Ks, with fiscal-year + page citations and optional year scoping.

``run_agent`` returns the answer plus a full trace (which tools were called with
what arguments) and the validator verdict — both surfaced in the UI and scored by
the evaluation component.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from openai import OpenAI

from answer import _HEADLINE, _MODEL, load_corpus
from retrieval import hybrid_search

_METRIC_LABELS = [label for _concept, label, _pt in _HEADLINE]

_AGENT_SYSTEM = """You are an agentic financial analyst for JPMorgan Chase & Co.'s \
10-K filings (FY2021-FY2025).

You have three tools:
- lookup_financial_fact(metric, fiscal_year?): the EXACT figure JPMorgan filed in \
XBRL. Use it for ANY financial number. Never state a figure without it.
- compute(operation, metric, ...): EXACT financial calculations done in code (never by \
you) over the metrics — change / percent_change / cagr / average / sum / min / max over \
years (metric + from_year/to_year), and ratio / percent_of / difference between two \
metrics in a year (metric, metric_b, year). Use it for ANY arithmetic — never compute \
numbers yourself.
- search_filings(query, fiscal_year?): relevant narrative passages from the 10-Ks \
(FY2021-2025), each tagged with its fiscal year and page. Pass fiscal_year to scope \
to one year's filing (e.g. a question about "the 2022 10-K"). Use it for qualitative \
/ "what does the filing say" questions.

Decide which tool(s) the question needs, call them, then answer concisely. Cite \
narrative as (FY<year>, p.X) using the year shown on the passage. If a number is not \
available from the tools, say so — never invent or hand-compute one."""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_financial_fact",
            "description": "Exact XBRL financial figure JPMorgan filed, by metric "
            "and (optionally) fiscal year. Omit fiscal_year to get all years.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": _METRIC_LABELS},
                    "fiscal_year": {
                        "type": "integer",
                        "description": "2021-2025; omit for all years",
                    },
                },
                "required": ["metric"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute",
            "description": "Deterministic financial calculation over the headline metrics "
            "(all arithmetic is done exactly in code, never by you). Pick an operation:\n"
            "• over ONE metric across years — change, percent_change, cagr (need metric + "
            "from_year + to_year); average, sum, min, max (metric; optional from_year/"
            "to_year, else all years).\n"
            "• between TWO metrics in ONE year — ratio, percent_of, difference (need "
            "metric, metric_b, year).\n"
            "Use this for ANY arithmetic — never compute a number yourself.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": [
                        "change", "percent_change", "cagr", "average", "sum", "min",
                        "max", "ratio", "percent_of", "difference"]},
                    "metric": {"type": "string", "enum": _METRIC_LABELS},
                    "metric_b": {"type": "string", "enum": _METRIC_LABELS,
                                 "description": "second metric — ratio/percent_of/difference"},
                    "year": {"type": "integer",
                             "description": "the year — ratio/percent_of/difference"},
                    "from_year": {"type": "integer"},
                    "to_year": {"type": "integer"},
                },
                "required": ["operation", "metric"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_filings",
            "description": "Search the 10-K narrative (FY2021-2025) for passages "
            "relevant to a query. Pass fiscal_year to scope to one year's filing. "
            "Returns passages tagged with fiscal year and page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "fiscal_year": {
                        "type": "integer",
                        "description": "2021-2025; omit to search all years",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


def _money(value: float) -> str:
    millions = int(round(abs(value))) // 1_000_000
    return f"{'-' if value < 0 else ''}${millions:,} million"


# compute() operations. SPAN ops run over one metric across years; PAIR ops combine two
# metrics within one year. Additive results are exact (Decimal); growth/ratios are rounded.
_SPAN_OPS = {"change", "percent_change", "cagr", "average", "sum", "min", "max"}
_PAIR_OPS = {"ratio", "percent_of", "difference"}


def _fmt(value: Decimal | float, unit: str) -> str:
    """Format a value with its unit: USD as '$N million', else 2-dp with the unit."""
    return _money(float(value)) if unit == "USD" else f"{float(value):,.2f} {unit}"


def _tool_compute(table: dict, args: dict) -> str:
    """Deterministic financial calculations over the headline facts — the no-LLM-math
    tool. Additive results (change/difference/sum/min/max) are exact (`Decimal`); growth
    and ratios (percent_change/cagr/ratio/percent_of/average) are rounded for display.
    The model only picks the operation + args; every number is computed here."""
    op = args.get("operation", "")
    metric = args.get("metric", "")

    if op in _SPAN_OPS:
        rows = sorted((fy, v[0], v[1]) for (lbl, fy), v in table.items() if lbl == metric)
        if not rows:
            return f"Cannot compute {op}: no facts for {metric!r}."
        unit = rows[0][2]
        lo, hi = args.get("from_year"), args.get("to_year")
        if op in {"change", "percent_change", "cagr"}:
            a = next((v for fy, v, _u in rows if fy == lo), None)
            b = next((v for fy, v, _u in rows if fy == hi), None)
            if a is None or b is None:
                return f"Cannot compute {op}: need {metric} for both FY{lo} and FY{hi}."
            if op == "change":
                return (f"{metric} change FY{lo}->FY{hi}: {_fmt(a, unit)} -> "
                        f"{_fmt(b, unit)} = {_fmt(b - a, unit)}. [exact, from XBRL]")
            if op == "percent_change":
                pct = float(b - a) / float(a) * 100 if a else 0.0
                return f"{metric} % change FY{lo}->FY{hi}: {pct:+.1f}%. [computed from XBRL]"
            n = hi - lo  # cagr
            if n <= 0 or a <= 0:
                return "Cannot compute CAGR: need to_year > from_year and a positive base."
            cagr = ((float(b) / float(a)) ** (1.0 / n) - 1.0) * 100
            return f"{metric} CAGR FY{lo}->FY{hi} ({n}y): {cagr:+.1f}%/yr. [computed from XBRL]"
        sel = [(fy, v) for fy, v, _u in rows
               if (lo is None or fy >= lo) and (hi is None or fy <= hi)]
        if not sel:
            return f"Cannot compute {op}: no {metric} in the requested range."
        span = f"FY{sel[0][0]}-FY{sel[-1][0]}"
        if op == "sum":
            return f"{metric} sum {span}: {_fmt(sum(v for _, v in sel), unit)}. [exact, from XBRL]"
        if op == "average":
            avg = sum(v for _, v in sel) / Decimal(len(sel))
            return f"{metric} average {span} ({len(sel)}y): {_fmt(avg, unit)}. [computed from XBRL]"
        fy, v = (min if op == "min" else max)(sel, key=lambda t: t[1])
        return f"{metric} {op} {span}: {_fmt(v, unit)} (FY{fy}). [exact, from XBRL]"

    if op in _PAIR_OPS:
        metric_b, year = args.get("metric_b", ""), args.get("year")
        a, b = table.get((metric, year)), table.get((metric_b, year))
        if not a or not b:
            return f"Cannot compute {op}: need {metric} and {metric_b} for FY{year}."
        (va, ua), (vb, ub) = a, b
        if op == "difference":
            if ua != ub:
                return f"Cannot subtract {metric} ({ua}) and {metric_b} ({ub}): different units."
            return (f"{metric} - {metric_b} (FY{year}): {_fmt(va, ua)} - {_fmt(vb, ub)} "
                    f"= {_fmt(va - vb, ua)}. [exact, from XBRL]")
        if not vb:
            return f"Cannot compute {op}: {metric_b} is zero in FY{year}."
        ratio = float(va) / float(vb)
        if op == "ratio":
            return f"{metric} / {metric_b} (FY{year}): {ratio:.3f}. [computed from XBRL]"
        return f"{metric} as % of {metric_b} (FY{year}): {ratio * 100:.1f}%. [computed from XBRL]"

    return f"Unknown operation: {op!r}."


def _tool_lookup_fact(table: dict, metric: str, fiscal_year: int | None = None) -> str:
    rows = sorted((fy, v) for (label, fy), v in table.items() if label == metric)
    if fiscal_year is not None:
        rows = [(fy, v) for fy, v in rows if fy == fiscal_year]
    if not rows:
        return f"No XBRL fact for metric={metric!r}, fiscal_year={fiscal_year}."
    parts = []
    for fy, (value, unit) in rows:
        if unit == "USD":
            parts.append(f"FY{fy}: ${int(value) // 1_000_000:,} million")
        else:
            parts.append(f"FY{fy}: {value} {unit}")
    return f"{metric} (exact, from XBRL): " + "; ".join(parts)


def _tool_search(
    question: str, k: int = 6, fiscal_year: int | None = None
) -> tuple[str, list]:
    # Hybrid: dense + sparse fused (RRF) + parent-expansion, optionally year-scoped.
    hits = hybrid_search(question, k=k, fiscal_year=fiscal_year)
    rendered = "\n\n".join(f"[FY{e.fiscal_year} p.{e.page}] {e.text[:500]}" for e in hits)
    return rendered, hits


def _validate(answer_text: str, tool_outputs: list[str], table: dict) -> dict[str, Any]:
    """Groundedness check: every financial figure in the answer — a comma-grouped amount
    ($4,002,814), a decimal / per-share value (19.75), or a percentage (18.2%) — must be
    either a headline XBRL value or present in the tool outputs (an exact fact or a
    `compute` result). Flags any that aren't — a guard against a hallucinated *or
    hand-computed* figure. (Bare integers like years/pages are intentionally not checked.)
    """
    stated = set(re.findall(r"\d{1,3}(?:,\d{3})+%?|\d+\.\d+%?|\d+%", answer_text))
    evidence = "\n".join(tool_outputs)
    known = {
        f"{int(value) // 1_000_000:,}"
        for (_label, _fy), (value, unit) in table.items()
        if unit == "USD"
    }
    ungrounded = sorted(n for n in stated if n not in known and n not in evidence)
    return {
        "grounded": not ungrounded,
        "ungrounded_numbers": ungrounded,
        "checked": sorted(stated),
    }


def _tool_loop(
    client: OpenAI, messages: list[dict], table: dict,
    trace: list, sources: list, tool_outputs: list, max_steps: int,
) -> str:
    """Run the tool-calling loop (mutating trace/sources/tool_outputs); return the answer."""
    for _step in range(max_steps):
        response = client.chat.completions.create(
            model=_MODEL, temperature=0, messages=messages, tools=_TOOLS, tool_choice="auto",
        )
        message = response.choices[0].message
        if not message.tool_calls:
            return message.content or ""
        messages.append({
            "role": "assistant", "content": message.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in message.tool_calls
            ],
        })
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            trace.append({"tool": name, "args": args})
            if name == "lookup_financial_fact":
                result = _tool_lookup_fact(table, args.get("metric", ""), args.get("fiscal_year"))
            elif name == "compute":
                result = _tool_compute(table, args)
            elif name == "search_filings":
                result, hits = _tool_search(
                    args.get("query", ""), fiscal_year=args.get("fiscal_year")
                )
                sources.extend(hits)
            else:
                result = f"unknown tool: {name}"
            tool_outputs.append(result)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
    return "I could not complete the answer within the step budget."


def _reflect(client: OpenAI, question: str, tool_outputs: list[str], answer: str) -> dict[str, Any]:
    """Self-critique (Self-RAG): is the answer grounded in the tool outputs and complete?"""
    context = "\n".join(tool_outputs)[:3000]
    try:
        resp = client.chat.completions.create(
            model=_MODEL, temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "user", "content":
                f"QUESTION:\n{question}\n\nTOOL OUTPUTS the agent gathered:\n{context}\n\n"
                f"AGENT ANSWER:\n{answer}\n\nIs the answer fully supported by the tool "
                f"outputs AND complete for the question? If a needed figure/fact is missing "
                f'or unsupported, say what to fix. Respond JSON: {{"ok": <true|false>, '
                f'"issue": "<short>"}}'}],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return {"ok": bool(data.get("ok", True)), "issue": str(data.get("issue", ""))}
    except Exception:  # noqa: BLE001 - a reflection failure must not crash the answer
        return {"ok": True, "issue": ""}


def run_agent(question: str, max_steps: int = 4, reflect: bool = True) -> dict[str, Any]:
    """The strong agent loop: route+act (tools) -> reflect -> revise if needed -> validate.

    The reflect->revise step is the Self-RAG behaviour: a critic checks the answer is
    grounded in the tool outputs and complete; if not, the agent is handed the critique
    and another turn — it can re-search with a sharper query or look up a missing fact.
    Returns the answer plus the full trace, sources, tool outputs, the reflection verdict,
    and the deterministic numeric validator result.
    """
    _elements, _bm25, table = load_corpus()
    client = OpenAI()
    messages: list[dict] = [
        {"role": "system", "content": _AGENT_SYSTEM},
        {"role": "user", "content": question},
    ]
    trace: list[dict] = []
    sources: list = []
    tool_outputs: list[str] = []

    final = _tool_loop(client, messages, table, trace, sources, tool_outputs, max_steps)

    reflection: dict[str, Any] | None = None
    if reflect and final:
        reflection = _reflect(client, question, tool_outputs, final)
        if not reflection["ok"]:
            messages.append({"role": "assistant", "content": final})
            messages.append({"role": "user", "content":
                f"A reviewer flagged an issue: {reflection['issue']}. Re-examine and improve "
                f"— call tools again (search with a sharper query, or look up the exact "
                f"figure) if needed — then give the final answer."})
            final = _tool_loop(
                client, messages, table, trace, sources, tool_outputs, max_steps
            ) or final

    return {
        "answer": final,
        "trace": trace,
        "sources": sources,
        "tool_outputs": tool_outputs,
        "reflection": reflection,
        "validation": _validate(final, tool_outputs, table),
    }
