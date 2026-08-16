# ai-interview-coach -- containerized runtime image.
#
# Builds and runs the Streamlit app (frontend/app.py) with all backend
# dependencies (Groq LLM calls, faster-whisper ASR, Piper TTS, the
# sentence-transformers/chromadb RAG + scoring stack). See
# docs/deployment.md for the full run instructions, required environment
# variables, and what this image deliberately does NOT bake in (Piper
# voice model weights, the Chroma vector index) versus what it builds on
# first run.
FROM python:3.11-slim

# System libraries the Python deps below need at import/runtime, not just
# build time:
#   - libsndfile1: soundfile's backend (backend/speech/features.py's volume
#     analysis, Piper's WAV output)
#   - ffmpeg: faster-whisper/ctranslate2's audio decoding path for
#     non-WAV input formats
#   - build-essential: some sentence-transformers/chromadb transitive deps
#     compile native extensions on install if no prebuilt wheel matches
#     this base image's platform
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (separate layer from the app source)
# so `docker build` doesn't reinstall ~1GB of ML dependencies on every code
# change -- only requirements.txt edits invalidate this layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Piper voice models (data/piper_voices/) and the Chroma question-bank
# index (data/chroma_question_bank/) are both gitignored -- see
# docs/deployment.md for how they get populated on first run rather than
# being baked into the image.

ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

# GROQ_API_KEY is required at runtime (not baked into the image) -- pass it
# via `docker run -e GROQ_API_KEY=...` or a mounted .env file. See
# docs/deployment.md.
CMD ["streamlit", "run", "frontend/app.py"]
