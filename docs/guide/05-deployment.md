# 05 · Deployment — the chat UI and the baked Docker image

> Code: `app/ui.py`, `Dockerfile`, `.dockerignore`.

## The UI (Streamlit, two tabs)

`app/ui.py` is a single Streamlit app with two tabs — the demo surface and the
evidence that it works.

### 💬 Chat tab

A chat input → `run_agent(prompt)` → a rich render of *everything the agent did*, not
just the answer:

- the **answer** (markdown);
- **🛠 Agent steps** — the `trace`, each tool call with its arguments (you can watch it
  route: lookup vs search vs compute);
- the **validator verdict** — ✅ "every figure is grounded in a tool result" or a ⚠️
  warning naming the ungrounded numbers (the doc 03 firewall, made visible);
- a **🔁 self-corrected** note when the reflect→revise pass fired;
- **Sources** — the retrieved passages with `FY{year} · p.{page} · {kind}` citations.

Surfacing the trace + validator is a deliberate trust move: the user sees *why* to
believe the answer.

### 📈 Evaluation tab

Renders `eval/last_report.json` (or runs `run_eval()` live on a button): the RAG-triad
+ fidelity metrics, the trajectory metrics, the regression (🔴/🟢) and data-drift (🟡)
alerts, and a per-item table. It's the same data doc 04 produces — the dashboard just
makes it legible.

### Startup

`@st.cache_resource` warms the corpus once (`load_corpus()` → Elements + BM25 + the
facts table) and reports the Element count and number of fiscal years in the caption.
The app `st.stop()`s with a clear message if `OPENAI_API_KEY` is missing.

## The Docker image — "bake once, reuse"

The deployment rule (a project constraint): **the heavy parse/index chain runs once,
offline; its output is baked into the image; the container only serves.** No parsing,
embedding-of-corpus, or indexing happens at build *or* run time.

So the `Dockerfile` is deliberately lean:

```dockerfile
FROM python:3.13-slim
# runtime deps ONLY — note what's absent: no docling, no arelle, no torch.
# duckdb + qdrant-client are the two *embedded* stores (no server) — built from the
# baked corpus at startup (doc 07).
RUN pip install --no-cache-dir \
    streamlit openai rank-bm25 numpy pydantic pydantic-settings duckdb qdrant-client

# only the light modules the app imports …
COPY src/config /srv/src/config
COPY src/ingestion/__init__.py  /srv/src/ingestion/__init__.py
COPY src/ingestion/serialize.py /srv/src/ingestion/serialize.py   # (read_jsonl only)
COPY app /srv/app
# … and the pre-built corpus, baked in (Elements + XBRL facts + .npy embeddings)
COPY data/derived/ingestion /srv/data/derived/ingestion

ENV PYTHONPATH=/srv/src
ENV AUDITAGENT_PROJECT_ROOT=/srv
EXPOSE 8501
CMD ["streamlit", "run", "app/ui.py", "--server.address=0.0.0.0", "--server.port=8501"]
```

Why this matters:

- **Lean & fast** — the image excludes the multi-GB ML parsing stack (Docling, Arelle,
  torch). It carries data, not machinery.
- **Reproducible** — the served corpus is a fixed artifact; two runs answer identically.
- **The embeddings are baked too** — the `.npy` caches ship in the image, so the
  container never re-embeds the *corpus*; it only embeds each *query* at request time
  (which is why it still needs the OpenAI key at runtime).
- **The stores are built at startup, embedded** — DuckDB loads the facts JSONL and Qdrant
  loads the sub-chunk `.npy` **in-process** (no server, ~15 s on first use), so the
  two-store architecture (doc 07) keeps the single-container model intact.
- `.dockerignore` keeps the build context tiny — it drops `.venv`, `.git`, `data/SEC`
  (raw filings), `tests`, `docs`, `reports`, and **`.env`** (the key is never baked).

## Build & run

```bash
# from the repo root, with the corpus present at data/derived/ingestion/
docker build -t jpm-10k-demo .

# the key is passed at RUN time (never built in) via --env-file
docker run --rm -p 8501:8501 --env-file .env jpm-10k-demo
# → open http://localhost:8501
```

**Verified:** the image builds, the container serves (`/_stcore/health` → HTTP 200), and
both embedded stores work in-container (`load_corpus` → DuckDB 17,009 Elements / 5 FY;
`build_index` → Qdrant 17,009).

→ Next: [06 · Decisions & lessons](06-decisions-and-lessons.md) — the why behind the how.
