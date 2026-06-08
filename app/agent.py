"""The agentic layer — an OpenAI tool-calling agent over the 10-K corpus.

This is the "agentic" in Agentic RAG: instead of a single fixed RAG call, the
model is given **tools** and decides — per query — which to call and in what order
(the router), calls them in a loop, then answers. A **validator** then checks that
every headline financial figure in the answer matches an exact XBRL fact.

Two tools:
- ``lookup_financial_fact`` — the EXACT figure JPMorgan filed in XBRL (FY2021-2025).
  The agent is told to use this for any number, so figures never come from the model.
- ``search_filings`` — BM25 narrative retrieval over the parsed FY2024 10-K, with
  page citations.

``run_agent`` returns the answer plus a full trace (which tools were called with
what arguments) and the validator verdict — both surfaced in the UI and scored by
the evaluation component.
"""

from __future__ import annotations

import json
import re
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
- compute_change(metric, from_year, to_year): the EXACT difference and % change of a \
metric between two years, computed from XBRL. Use it for ANY change / growth / \
comparison — never do the arithmetic yourself.
- search_filings(query): relevant narrative passages from the FY2024 10-K, with page \
numbers. Use it for qualitative / "what does the filing say" questions.

Decide which tool(s) the question needs, call them, then answer concisely. Cite \
narrative as (FY2024, p.X). If a number is not available from the tools, say so — \
never invent or hand-compute one."""

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
            "name": "compute_change",
            "description": "Exact difference and % change of a financial metric "
            "between two fiscal years, computed from XBRL. Use for ANY change / growth "
            "/ comparison — do not do the arithmetic yourself.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": _METRIC_LABELS},
                    "from_year": {"type": "integer"},
                    "to_year": {"type": "integer"},
                },
                "required": ["metric", "from_year", "to_year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_filings",
            "description": "Search the FY2024 10-K narrative (text/tables/headings) "
            "for passages relevant to a query. Returns passages with page numbers.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]


def _money(value: float) -> str:
    millions = int(round(abs(value))) // 1_000_000
    return f"{'-' if value < 0 else ''}${millions:,} million"


def _tool_compute(table: dict, metric: str, from_year: int, to_year: int) -> str:
    """Deterministic arithmetic (no LLM math): exact change of a metric between years."""
    a, b = table.get((metric, from_year)), table.get((metric, to_year))
    if not a or not b:
        return f"Cannot compute: missing {metric} for FY{from_year} or FY{to_year}."
    va, vb, unit = float(a[0]), float(b[0]), a[1]
    diff = vb - va
    pct = (diff / va * 100.0) if va else 0.0
    if unit == "USD":
        cells = f"FY{from_year}={_money(va)}, FY{to_year}={_money(vb)}, change={_money(diff)}"
    else:
        cells = (f"FY{from_year}={va:.2f} {unit}, FY{to_year}={vb:.2f} {unit}, "
                 f"change={diff:+.2f} {unit}")
    return f"{metric}: {cells} ({pct:+.1f}%). [exact, computed from XBRL]"


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


def _tool_search(question: str, k: int = 6) -> tuple[str, list]:
    # Hybrid: dense + sparse fused (RRF) with parent-expansion (retrieval.py).
    hits = hybrid_search(question, k=k)
    rendered = "\n\n".join(f"[FY2024 p.{e.page}] {e.text[:500]}" for e in hits)
    return rendered, hits


def _validate(answer_text: str, tool_outputs: list[str], table: dict) -> dict[str, Any]:
    """Groundedness check: every comma-formatted number in the answer must be either a
    headline XBRL value or present in the tool outputs (an exact fact or a compute_change
    result). Flags any that aren't — a guard against a hallucinated *or hand-computed*
    figure (the latter is why the agent must use compute_change, not LLM arithmetic).
    """
    stated = set(re.findall(r"\d{1,3}(?:,\d{3})+", answer_text))
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
            elif name == "compute_change":
                result = _tool_compute(
                    table, args.get("metric", ""), args.get("from_year"), args.get("to_year")
                )
            elif name == "search_filings":
                result, hits = _tool_search(args.get("query", ""))
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
