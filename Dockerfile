# JPMorgan 10-K Q&A demo — a lean image: the heavy corpus is *pre-built* and baked
# in, so the runtime needs no PDF parser (docling) or XBRL engine (arelle/torch).
FROM python:3.13-slim

WORKDIR /srv

# Runtime deps only (corpus is pre-built JSONL).
RUN pip install --no-cache-dir \
    streamlit openai rank-bm25 numpy pydantic pydantic-settings duckdb qdrant-client

# Lightweight source modules the app imports (config + ingestion.serialize) — put
# on PYTHONPATH, no package install needed. We deliberately do NOT copy the heavy
# parsers (ingestion/elements.py, xbrl.py, ...).
COPY src/config /srv/src/config
COPY src/ingestion/__init__.py /srv/src/ingestion/__init__.py
COPY src/ingestion/serialize.py /srv/src/ingestion/serialize.py
COPY app /srv/app

# Bake the parse-once derived corpus into the image (Elements + XBRL facts JSONL).
COPY data/derived/ingestion /srv/data/derived/ingestion

ENV PYTHONPATH=/srv/src
ENV AUDITAGENT_PROJECT_ROOT=/srv
ENV STREAMLIT_SERVER_HEADLESS=true

EXPOSE 8501
# OPENAI_API_KEY is provided at run time: docker run --env-file .env ...
CMD ["streamlit", "run", "app/ui.py", \
     "--server.address=0.0.0.0", "--server.port=8501"]
