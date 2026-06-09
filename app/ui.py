"""Streamlit app — Agentic RAG chat over JPMorgan's 10-Ks + an Evaluation dashboard.

Run:  streamlit run app/ui.py   (needs OPENAI_API_KEY in env or .env)

Layout note: the views are switched with a **sidebar selector**, not `st.tabs`. That is
deliberate — `st.chat_input` only pins to the bottom of the page when it lives in the
main body; nested inside `st.tabs` it renders inline and appears to "move" as the
conversation grows. With the selector, the Chat view's input is top-level → pinned at the
bottom, with messages and the agent's thinking bubble flowing above it (a normal chat).
"""

import json
import os
from pathlib import Path

import streamlit as st

from agent import run_agent
from answer import load_corpus
from evaluate import run_eval

st.set_page_config(page_title="JPMorgan 10-K Agentic RAG", page_icon="📊", layout="wide")

if not os.getenv("OPENAI_API_KEY"):
    st.error(
        "No `OPENAI_API_KEY` found. Put it in a repo-root `.env` "
        "(`OPENAI_API_KEY=sk-...`) or the environment, then reload."
    )
    st.stop()


@st.cache_resource(show_spinner="Loading the 10-K corpus…")
def _warm():
    elements, _bm25, table = load_corpus()
    return len(elements), len({fy for (_, fy) in table})


N_ELEMENTS, N_YEARS = _warm()

st.title("📊 JPMorgan Chase 10-K — Agentic RAG")
st.caption(
    f"Agent routes between an **exact-XBRL fact tool** and a **narrative search "
    f"tool**, then a **validator** checks the figures. Corpus: {N_ELEMENTS:,} narrative "
    f"Elements + exact XBRL facts across {N_YEARS} fiscal years."
)


# ----------------------------------------------------------------- render helpers
def _render_sources(sources) -> None:
    if not sources:
        return
    with st.expander(f"Sources ({len(sources)} passages)"):
        for e in sources:
            snippet = e.text[:300].replace("<", "&lt;").replace(">", "&gt;")
            st.markdown(f"**FY{e.fiscal_year} · p.{e.page} · {e.kind.value}** — {snippet}")


def _render_agent_result(result: dict) -> None:
    st.markdown(result["answer"])
    trace = result["trace"]
    if trace:
        with st.expander(f"🛠 Agent steps — {len(trace)} tool call(s)"):
            for step in trace:
                st.markdown(f"- `{step['tool']}`  ·  `{json.dumps(step['args'])}`")
    validation = result["validation"]
    if validation["grounded"]:
        st.caption("✅ Validator: every figure stated is grounded in a tool result (exact XBRL / computed).")
    else:
        st.warning(
            "⚠️ Validator: numbers not grounded in any tool output — "
            f"{validation['ungrounded_numbers']} (possible hallucination / hand-computed)."
        )
    reflection = result.get("reflection")
    if reflection and not reflection.get("ok", True):
        st.caption(f"🔁 Self-corrected after critique — {reflection.get('issue', '')}")
    _render_sources(result["sources"])


def _load_last_report() -> dict | None:
    path = Path(__file__).resolve().parent.parent / "eval" / "last_report.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ----------------------------------------------------------------- view selector
view = st.sidebar.radio(
    "View", ["💬 Chat", "📈 Evaluation"], label_visibility="collapsed", key="view"
)


# =================================================================== Chat view
if view == "💬 Chat":
    with st.sidebar:
        st.header("Try asking")
        st.markdown(
            "- What was **net income** in 2024?\n"
            "- How did **total assets** change from 2021 to 2025?\n"
            "- What was **diluted EPS** each year?\n"
            "- What does JPMorgan say about **credit risk**?\n"
            "- What was the **share price** on a future date? *(should refuse)*"
        )
        st.divider()
        st.caption(
            "Numbers: exact `us-gaap` XBRL facts via DuckDB. "
            "Narrative: hybrid retrieval (Qdrant + BM25) over parsed FY2021-2025 Elements. "
            "Agent + validator: OpenAI tool-calling."
        )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # History renders into the main body; the chat_input below is top-level, so it stays
    # pinned to the bottom of the page with these messages flowing above it.
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                _render_agent_result(message["result"])
            else:
                st.markdown(message["content"])

    if prompt := st.chat_input("Ask about JPMorgan's 10-K…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Agent is routing tools and reading the filings…"):
                try:
                    result = run_agent(prompt)
                except Exception as exc:  # noqa: BLE001
                    result = {"answer": f"⚠️ Error: {exc}", "trace": [], "sources": [],
                              "validation": {"grounded": True, "ungrounded_numbers": []}}
            _render_agent_result(result)
        st.session_state.messages.append({"role": "assistant", "result": result})


# ============================================================= Evaluation view
else:
    st.subheader("Evaluation — does the Agentic RAG actually perform?")
    st.caption(
        "Runs the agent over a golden set and scores the RAG triad + agentic "
        "tool-use, then flags **regressions (silent failure)** vs a baseline and "
        "**data drift** in the XBRL series. Auto-triggerable: `python app/evaluate.py`."
    )
    if st.button("▶️ Run evaluation (~1–2 min)"):
        with st.spinner("Scoring the golden set end-to-end…"):
            st.session_state["eval_report"] = run_eval()

    report = st.session_state.get("eval_report") or _load_last_report()
    if not report:
        st.info("No evaluation run yet. Click **Run evaluation** above.")
    else:
        agg = report["aggregate"]
        st.caption(f"Run: {report['timestamp']} · {report['n_items']} items · {report['model']}")
        st.markdown("**RAG triad — LLM-judged**")
        triad = st.columns(3)
        triad[0].metric("Context relevance", agg.get("context_relevance"))
        triad[1].metric("Groundedness", agg.get("groundedness"))
        triad[2].metric("Answer relevance", agg.get("answer_relevance"))
        st.markdown("**Fidelity & retrieval — deterministic**")
        row1 = st.columns(5)
        row1[0].metric("Numeric exactness", agg.get("numeric_exact"))
        row1[1].metric("Retrieval hit-rate", agg.get("retrieval_hit_rate"))
        row1[2].metric("Year-scope accuracy", agg.get("year_scope_accuracy"))
        row1[3].metric("Validator pass-rate", agg.get("validator_pass_rate"))
        row1[4].metric("Tool-use accuracy", agg.get("tool_accuracy"))
        st.markdown("**Agent trajectory — LLM-judge over the tool-use path**")
        row3 = st.columns(3)
        row3[0].metric("Tool appropriateness", agg.get("tool_appropriateness"))
        row3[1].metric("Trajectory efficiency", agg.get("trajectory_efficiency"))
        row3[2].metric("Answer faithfulness", agg.get("answer_faithfulness"))

        if report["regression_alerts"]:
            st.error(f"🔴 Silent-failure / regression vs baseline: {report['regression_alerts']}")
        else:
            st.success("🟢 No regression vs baseline.")
        if report["data_drift_alerts"]:
            st.warning(
                f"🟡 Data-drift flags ({len(report['data_drift_alerts'])}): "
                + ", ".join(
                    f"{a['metric']} FY{a['from']}→FY{a['to']} {a['pct_change']:+}%"
                    for a in report["data_drift_alerts"]
                )
            )
        else:
            st.success("🟢 No data-drift flags.")

        with st.expander("Per-item results"):
            st.dataframe(
                [
                    {
                        "id": it["id"],
                        "kind": it["kind"],
                        "numeric_exact": it.get("numeric_exact"),
                        "retrieval_hit": it.get("retrieval_hit"),
                        "tool_correct": it.get("tool_correct"),
                        "ctx_rel": round(it.get("context_relevance", 0), 2),
                        "grounded": round(it.get("groundedness", 0), 2),
                        "relevant": round(it.get("relevance", 0), 2),
                        "traj_approp": round(it.get("tool_appropriateness", 0), 2),
                        "efficiency": round(it.get("efficiency", 0), 2),
                        "faithful": round(it.get("faithfulness", 0), 2),
                        "revised": it.get("revised"),
                        "tools": ",".join(it.get("tools_used", [])),
                    }
                    for it in report["items"]
                ],
                width="stretch",
            )
