"""Streamlit app — Agentic RAG chat over JPMorgan's 10-Ks + an Evaluation dashboard.

Run:  streamlit run app/ui.py   (needs OPENAI_API_KEY in env or .env)
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

chat_tab, eval_tab = st.tabs(["💬 Chat", "📈 Evaluation"])


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


# ----------------------------------------------------------------- Chat tab
with chat_tab:
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
            "Numbers: exact `us-gaap` XBRL facts via a tool. "
            "Narrative: hybrid retrieval over parsed FY2021-2025 Elements. "
            "Agent + validator: OpenAI tool-calling."
        )

    if "messages" not in st.session_state:
        st.session_state.messages = []

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


# ----------------------------------------------------------- Evaluation tab
def _load_last_report() -> dict | None:
    path = Path(__file__).resolve().parent.parent / "eval" / "last_report.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


with eval_tab:
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
        st.markdown("**Answer quality — RAG triad + numeric fidelity**")
        row1 = st.columns(3)
        row1[0].metric("Numeric exactness", agg.get("numeric_exact"))
        row1[1].metric("Retrieval hit-rate", agg.get("retrieval_hit_rate"))
        row1[2].metric("Validator pass-rate", agg.get("validator_pass_rate"))
        row2 = st.columns(3)
        row2[0].metric("Groundedness", agg.get("groundedness"))
        row2[1].metric("Answer relevance", agg.get("answer_relevance"))
        row2[2].metric("Tool-use accuracy", agg.get("tool_accuracy"))
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
                use_container_width=True,
            )
