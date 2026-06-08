"""The evaluation component — assess the Agentic RAG's performance, end to end.

This is the second main deliverable. It runs the agent over a **golden set** and
scores five things that together cover the RAG triad *and* the agentic behaviour:

- **numeric_exact** (deterministic) — does the answer contain the exact XBRL figure?
  The fidelity metric: a wrong number is a hard fail.
- **tool_correct** (agentic) — did the agent route to the right tool (numeric ->
  fact tool, narrative -> search)?
- **retrieval_hit** (deterministic) — did retrieval surface a relevant passage?
- **groundedness** / **answer_relevance** (LLM-judge) — the classic RAG triad.

On top of per-run scoring it adds the *monitoring* the brief asks for:

- **regression / silent-failure** — compares this run's aggregates to a committed
  **baseline**; a drop beyond a threshold is flagged (a metric degrading quietly).
- **data drift** — scans the headline XBRL series for year-over-year moves beyond a
  threshold (a concept/data-drift sketch a reviewer should eyeball).

Auto-triggerable: ``python app/evaluate.py`` runs the suite, writes a JSON report,
and prints a summary — drop it in cron / a scheduled job for timely stats.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

from agent import run_agent
from answer import _HEADLINE, _MODEL, load_corpus

_EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"
_BASELINE = _EVAL_DIR / "baseline.json"
_RUNS = _EVAL_DIR / "runs"
_REGRESSION_TOL = 0.10  # an aggregate dropping this much vs baseline = silent failure
_DRIFT_TOL = 0.30  # a headline metric moving >30% YoY is flagged for review

# Golden set. Numeric truths are the exact XBRL figures ($ millions); narrative
# items name a keyword the retrieved context should contain; the refusal item
# checks the agent declines to invent an unavailable figure.
GOLDEN: list[dict[str, Any]] = [
    # Numeric — total assets for EACH fiscal year (all 5 years exercised).
    {"id": "assets_2021", "q": "What were JPMorgan's total assets at year-end 2021?",
     "kind": "numeric", "expect_number": "3,743,567", "expect_tool": "lookup_financial_fact"},
    {"id": "assets_2022", "q": "What were total assets at year-end 2022?",
     "kind": "numeric", "expect_number": "3,665,743", "expect_tool": "lookup_financial_fact"},
    {"id": "assets_2023", "q": "What were total assets at year-end 2023?",
     "kind": "numeric", "expect_number": "3,875,393", "expect_tool": "lookup_financial_fact"},
    {"id": "assets_2024", "q": "What were total assets at year-end 2024?",
     "kind": "numeric", "expect_number": "4,002,814", "expect_tool": "lookup_financial_fact"},
    {"id": "assets_2025", "q": "What were total assets at year-end 2025?",
     "kind": "numeric", "expect_number": "4,424,900", "expect_tool": "lookup_financial_fact"},
    # Other metrics / years.
    {"id": "net_income_2024", "q": "What was JPMorgan's net income in fiscal year 2024?",
     "kind": "numeric", "expect_number": "58,471", "expect_tool": "lookup_financial_fact"},
    {"id": "net_income_2021", "q": "What was net income in 2021?",
     "kind": "numeric", "expect_number": "48,334", "expect_tool": "lookup_financial_fact"},
    {"id": "revenue_2023", "q": "What was total net revenue in 2023?",
     "kind": "numeric", "expect_number": "158,104", "expect_tool": "lookup_financial_fact"},
    {"id": "nii_2025", "q": "What was net interest income in 2025?",
     "kind": "numeric", "expect_number": "95,443", "expect_tool": "lookup_financial_fact"},
    {"id": "eps_2024", "q": "What was diluted EPS in 2024?",
     "kind": "numeric", "expect_number": "19.75", "expect_tool": "lookup_financial_fact"},
    # Cross-year arithmetic (deterministic calc tool).
    {"id": "deposits_change", "q": "How did total deposits change from 2021 to 2025?",
     "kind": "numeric", "expect_number": "2,559,320", "expect_tool": "compute_change"},
    # Narrative (year-agnostic — retrieves across all years).
    {"id": "risk_factors", "q": "What does JPMorgan identify as key risk factors?",
     "kind": "narrative", "expect_keywords": ["risk"], "expect_tool": "search_filings"},
    {"id": "credit_risk", "q": "What does the filing say about credit risk?",
     "kind": "narrative", "expect_keywords": ["credit"], "expect_tool": "search_filings"},
    # Year-scoped narrative — must retrieve from the named filing year.
    {"id": "capital_2022", "q": "According to the FY2022 10-K specifically, what does JPMorgan discuss about capital?",
     "kind": "narrative", "expect_keywords": ["capital"], "expect_tool": "search_filings", "expect_year": 2022},
    {"id": "risk_2025", "q": "In the 2025 10-K, what risks does the firm highlight?",
     "kind": "narrative", "expect_keywords": ["risk"], "expect_tool": "search_filings", "expect_year": 2025},
    # Grounding / refusal.
    {"id": "future_price", "q": "What was JPMorgan's share price on March 1, 2026?",
     "kind": "refusal", "expect_tool": None},
]

_JUDGE = (
    "You grade a financial QA system. Given the QUESTION, the CONTEXT the system "
    "was given, and its ANSWER, rate two things from 0.0 to 1.0:\n"
    "- groundedness: is the answer supported by the context (no invented facts)?\n"
    "- relevance: does the answer address the question?\n"
    'Respond ONLY as JSON: {"groundedness": <float>, "relevance": <float>}'
)


def _judge(client: OpenAI, question: str, context: str, answer: str) -> dict[str, float]:
    try:
        resp = client.chat.completions.create(
            model=_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _JUDGE},
                {"role": "user", "content":
                 f"QUESTION:\n{question}\n\nCONTEXT:\n{context[:3500]}\n\nANSWER:\n{answer}"},
            ],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return {"groundedness": float(data.get("groundedness", 0.0)),
                "relevance": float(data.get("relevance", 0.0))}
    except Exception:  # noqa: BLE001 - a judge failure must not crash the suite
        return {"groundedness": 0.0, "relevance": 0.0}


_TRAJECTORY_JUDGE = (
    "You grade an AI agent's TOOL-USE TRAJECTORY (how it worked, not just its final "
    "answer). The agent has two tools: lookup_financial_fact (exact XBRL figures) and "
    "search_filings (narrative retrieval). Given the QUESTION, the ordered TRAJECTORY of "
    "tool calls, the TOOL OUTPUTS, and the ANSWER, rate each 0.0-1.0:\n"
    "- tool_appropriateness: were the right tools chosen for this question?\n"
    "- efficiency: was the trajectory free of redundant or wasteful calls?\n"
    "- faithfulness: does the answer correctly use the tool outputs (no drift/invention)?\n"
    'Respond ONLY as JSON: {"tool_appropriateness": <f>, "efficiency": <f>, "faithfulness": <f>}'
)


def _judge_trajectory(
    client: OpenAI, question: str, trace: list, tool_outputs: list, answer: str
) -> dict[str, float]:
    """LLM-judge over the agent's *trajectory* — the agentic counterpart to the RAG triad."""
    trajectory = "\n".join(
        f"{i + 1}. {t['tool']}({json.dumps(t['args'])})" for i, t in enumerate(trace)
    ) or "(no tools called)"
    try:
        resp = client.chat.completions.create(
            model=_MODEL, temperature=0, response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _TRAJECTORY_JUDGE},
                {"role": "user", "content":
                 f"QUESTION:\n{question}\n\nTRAJECTORY:\n{trajectory}\n\n"
                 f"TOOL OUTPUTS:\n{chr(10).join(tool_outputs)[:2500]}\n\nANSWER:\n{answer}"},
            ],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return {
            "tool_appropriateness": float(data.get("tool_appropriateness", 0.0)),
            "efficiency": float(data.get("efficiency", 0.0)),
            "faithfulness": float(data.get("faithfulness", 0.0)),
        }
    except Exception:  # noqa: BLE001
        return {"tool_appropriateness": 0.0, "efficiency": 0.0, "faithfulness": 0.0}


def _score_item(client: OpenAI, item: dict) -> dict[str, Any]:
    result = run_agent(item["q"])
    answer = result["answer"]
    tools_used = [t["tool"] for t in result["trace"]]
    context = "\n".join(result["tool_outputs"]) or "\n".join(
        e.text[:300] for e in result["sources"]
    )

    scores: dict[str, Any] = {"id": item["id"], "kind": item["kind"], "answer": answer,
                              "tools_used": tools_used,
                              "validator_grounded": result["validation"]["grounded"]}

    scores["tool_correct"] = (
        item["expect_tool"] in tools_used if item["expect_tool"] else len(tools_used) == 0
    )
    if item["kind"] == "numeric":
        scores["numeric_exact"] = item["expect_number"] in answer
    elif item["kind"] == "narrative":
        blob = " ".join(e.text.lower() for e in result["sources"])
        scores["retrieval_hit"] = any(k.lower() in blob for k in item["expect_keywords"])
        if item.get("expect_year"):
            years = [e.fiscal_year for e in result["sources"]]
            scores["year_scope_ok"] = bool(years) and (
                sum(y == item["expect_year"] for y in years) >= len(years) * 0.5
            )
    elif item["kind"] == "refusal":
        low = answer.lower()
        scores["refused"] = any(
            p in low for p in ("not available", "cannot", "can't", "don't have",
                               "do not have", "unable", "no information")
        )

    scores.update(_judge(client, item["q"], context, answer))
    scores.update(
        _judge_trajectory(client, item["q"], result["trace"], result["tool_outputs"], answer)
    )
    scores["revised"] = bool(result.get("reflection") and not result["reflection"]["ok"])
    return scores


def _data_drift() -> list[dict[str, Any]]:
    """Flag headline metrics whose year-over-year move exceeds the drift tolerance."""
    _e, _b, table = load_corpus()
    flags = []
    for _concept, label, _pt in _HEADLINE:
        series = sorted((fy, float(v)) for (lbl, fy), (v, _u) in table.items() if lbl == label)
        for (y0, v0), (y1, v1) in zip(series, series[1:]):
            if v0 and abs(v1 - v0) / abs(v0) > _DRIFT_TOL:
                flags.append({"metric": label, "from": y0, "to": y1,
                              "pct_change": round((v1 - v0) / v0 * 100, 1)})
    return flags


def _aggregate(items: list[dict]) -> dict[str, float]:
    def mean(key, subset=None):
        vals = [s[key] for s in items if key in s and (subset is None or s["kind"] in subset)]
        return round(sum(float(v) for v in vals) / len(vals), 3) if vals else None

    return {
        "numeric_exact": mean("numeric_exact", {"numeric"}),
        "tool_accuracy": mean("tool_correct"),
        "retrieval_hit_rate": mean("retrieval_hit", {"narrative"}),
        "groundedness": mean("groundedness"),
        "answer_relevance": mean("relevance"),
        "validator_pass_rate": mean("validator_grounded"),
        "tool_appropriateness": mean("tool_appropriateness"),
        "trajectory_efficiency": mean("efficiency"),
        "answer_faithfulness": mean("faithfulness"),
        "year_scope_accuracy": mean("year_scope_ok"),
    }


def _regression(aggregate: dict) -> list[dict[str, Any]]:
    """Compare aggregates to the committed baseline; flag silent degradations."""
    if not _BASELINE.is_file():
        _BASELINE.write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
        return []
    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    flags = []
    for metric, value in aggregate.items():
        base = baseline.get(metric)
        if value is not None and base is not None and value < base - _REGRESSION_TOL:
            flags.append({"metric": metric, "baseline": base, "now": value})
    return flags


def run_eval(write: bool = True) -> dict[str, Any]:
    _EVAL_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI()
    items = [_score_item(client, it) for it in GOLDEN]
    aggregate = _aggregate(items)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": _MODEL,
        "n_items": len(items),
        "aggregate": aggregate,
        "regression_alerts": _regression(aggregate),
        "data_drift_alerts": _data_drift(),
        "items": items,
    }
    if write:
        _RUNS.mkdir(parents=True, exist_ok=True)
        stamp = report["timestamp"].replace(":", "").replace("-", "")
        (_RUNS / f"eval_{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (_EVAL_DIR / "last_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _print(report: dict) -> None:
    print(f"\n=== Agentic RAG evaluation ({report['n_items']} items, {report['model']}) ===")
    for k, v in report["aggregate"].items():
        print(f"  {k:22s}: {v}")
    print(f"  regression alerts     : {report['regression_alerts'] or 'none'}")
    print(f"  data-drift alerts     : {len(report['data_drift_alerts'])} flagged")


if __name__ == "__main__":
    _print(run_eval())
