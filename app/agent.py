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

from answer import _HEADLINE, _MODEL, _tokens, load_corpus

_METRIC_LABELS = [label for _concept, label, _pt in _HEADLINE]

_AGENT_SYSTEM = """You are an agentic financial analyst for JPMorgan Chase & Co.'s \
10-K filings (FY2021-FY2025).

You have two tools:
- lookup_financial_fact(metric, fiscal_year?): the EXACT figure JPMorgan filed in \
XBRL. Use it for ANY financial number. Never state a financial figure without it.
- search_filings(query): relevant narrative passages from the FY2024 10-K, with \
page numbers. Use it for qualitative / "what does the filing say" questions.

Decide which tool(s) the question needs (numeric, narrative, or both), call them, \
then answer concisely. Cite narrative as (FY2024, p.X). If a number is not \
available from the tools, say so — never invent one."""

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
    elements, bm25, _table = load_corpus()
    scores = bm25.get_scores(_tokens(question))
    ranked = sorted(range(len(elements)), key=lambda i: scores[i], reverse=True)[:k]
    hits = [elements[i] for i in ranked]
    rendered = "\n\n".join(f"[FY2024 p.{e.page}] {e.text[:500]}" for e in hits)
    return rendered, hits


def _validate(answer_text: str, table: dict) -> dict[str, Any]:
    """Groundedness check on headline figures: every comma-formatted number in the
    answer should match an exact XBRL headline value (in $millions). Flags any that
    don't — a guard against a hallucinated figure slipping through.
    """
    stated = set(re.findall(r"\d{1,3}(?:,\d{3})+", answer_text))
    known = {
        f"{int(value) // 1_000_000:,}"
        for (_label, _fy), (value, unit) in table.items()
        if unit == "USD"
    }
    ungrounded = sorted(stated - known)
    return {
        "grounded": not ungrounded,
        "ungrounded_numbers": ungrounded,
        "checked": sorted(stated),
    }


def run_agent(question: str, max_steps: int = 4) -> dict[str, Any]:
    """Run the tool-calling agent. Returns answer + tool trace + sources + validation."""
    _elements, _bm25, table = load_corpus()
    client = OpenAI()
    messages: list[dict] = [
        {"role": "system", "content": _AGENT_SYSTEM},
        {"role": "user", "content": question},
    ]
    trace: list[dict] = []
    sources: list = []
    tool_outputs: list[str] = []
    final = ""

    for _step in range(max_steps):
        response = client.chat.completions.create(
            model=_MODEL,
            temperature=0,
            messages=messages,
            tools=_TOOLS,
            tool_choice="auto",
        )
        message = response.choices[0].message

        if not message.tool_calls:
            final = message.content or ""
            break

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            }
        )
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            trace.append({"tool": name, "args": args})
            if name == "lookup_financial_fact":
                result = _tool_lookup_fact(
                    table, args.get("metric", ""), args.get("fiscal_year")
                )
            elif name == "search_filings":
                result, hits = _tool_search(args.get("query", question))
                sources.extend(hits)
            else:
                result = f"unknown tool: {name}"
            tool_outputs.append(result)
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": result}
            )
    else:
        final = final or "I could not complete the answer within the step budget."

    return {
        "answer": final,
        "trace": trace,
        "sources": sources,
        "tool_outputs": tool_outputs,
        "validation": _validate(final, table),
    }
