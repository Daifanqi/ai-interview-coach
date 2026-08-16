# Deployment

This is a source-available portfolio project (see `LICENSE` -- PolyForm
Noncommercial 1.0.0, personal/learning use only, see `docs/decision_log.md`
decision 28), not something with a hosted public demo. This document
covers running it yourself, either directly or via Docker; it deliberately
stops short of a cloud-hosting walkthrough (Streamlit Community Cloud,
etc.) -- see "Why no hosted demo" at the bottom.

## 1. Prerequisites

- Python 3.10+ (the project has been run under 3.10 and 3.13; see
  `requirements.txt`)
- A [Groq API key](https://console.groq.com) -- every LLM call in this
  project (conversation engine, follow-up scoring judge, real-time
  feedback, AI highlight pick, report generation) goes through Groq. The
  app degrades gracefully in most places when this is missing (falls back
  to rule-based scoring, skips feedback/highlights) but the core interview
  conversation itself needs it.
- ~2GB of disk for first-run downloads: the `sentence-transformers`
  embedding model, faster-whisper's ASR model, and Piper's TTS voice
  models (see step 4).

## 2. Environment variables

Copy the pattern in the project's own (gitignored) `.env` file:

```
GROQ_API_KEY=your-key-here
```

Optional overrides for the ASR model (`backend/speech/transcribe.py`),
useful if you're deploying to a machine with a GPU or want a smaller/larger
Whisper model than the `small`/CPU/`int8` default:

```
ASR_MODEL_SIZE=small       # tiny/base/small/medium/large-v3
ASR_DEVICE=cpu             # cpu or cuda
ASR_COMPUTE_TYPE=int8      # int8/float16/float32
```

`.env` is loaded automatically by every backend module that needs it
(`python-dotenv`) -- no extra wiring needed beyond creating the file.

## 3. Run locally (no Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # if you keep a template; otherwise create .env per step 2
streamlit run frontend/app.py
```

Opens on `http://localhost:8501` by default.

## 4. Run with Docker

```bash
docker build -t ai-interview-coach .
docker run -p 8501:8501 \
  -e GROQ_API_KEY=your-key-here \
  -v "$(pwd)/data:/app/data" \
  ai-interview-coach
```

The `-v "$(pwd)/data:/app/data"` mount matters for two reasons:

- **Persistence across container restarts**: `data/sessions.db` (SQLite,
  `backend/storage/db.py`/`backend/storage/user_db.py`) holds every
  session and user account. Without the mount, restarting the container
  loses all of it.
- **Avoiding repeated first-run downloads**: Piper's voice models
  (`data/piper_voices/`, ~60-120MB each, three voices) and the Chroma
  question-bank vector index (`data/chroma_question_bank/`, built from
  `data/question_bank.json` on first RAG query) are both gitignored and
  NOT baked into the image (see `.dockerignore`) -- they download/build
  into `data/` the first time they're needed. Without the volume mount,
  every fresh container pays that cost again.

First run will be noticeably slower than subsequent ones for this reason
(downloading the ~60MB `sentence-transformers` embedding model, three
Piper voice models, and embedding the 200-question bank into Chroma all
happen lazily on first use, not at build time).

## 5. Data that lives outside `data/`

Nothing else the app writes at runtime needs to persist -- `frontend/`,
`backend/`, `models/` are all static code, and `.streamlit/config.toml`
(theme) is read-only.

## 6. Why no hosted demo

Decision 45 (week 16) scoped deployment for this project to "runnable
locally/via Docker with clear instructions" rather than an actual public
hosted URL, for two reasons: (1) the project's own license (decision 28,
PolyForm Noncommercial) already rules out a public-facing product
deployment in the commercial sense a hosted demo implies, and (2) a real
hosted deployment needs an owner to provision and pay for hosting, manage
the `GROQ_API_KEY` secret in that platform's secret store, and take
responsibility for the running service (rate limits, uptime, abuse) --
decisions properly made by whoever runs this project day to day, not
baked into the repository itself. This document gives everything needed to
deploy to any platform (Streamlit Community Cloud, a VPS via the Dockerfile
above, etc.) once that decision is made.
