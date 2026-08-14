"""
Builds and persists a Chroma vector store over data/question_bank.json's
200 job-type-segmented questions (docs/decision_log.md decisions 24-25),
embedded with the same shared model as backend/scoring/baseline.py
(backend/scoring/embedding.py) so scoring and retrieval live in one
consistent vector space.

Embeddings are always supplied explicitly (collection.add(embeddings=...),
see retriever.py's collection.query(query_embeddings=...)) rather than
relying on Chroma's own default embedding function, which would silently
swap in a different (English-only) model and break that consistency.

Usage:
    python -m backend.rag.vector_store   # (re)build the persisted index

backend/rag/retriever.py is the read path over this index.
"""
from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from backend.scoring.embedding import embed_texts
from models.question_schema import load_questions_from_json

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUESTION_BANK_PATH = _PROJECT_ROOT / "data" / "question_bank.json"
DEFAULT_PERSIST_DIR = _PROJECT_ROOT / "data" / "chroma_question_bank"
COLLECTION_NAME = "question_bank"


def _get_client(persist_dir: Path | str = DEFAULT_PERSIST_DIR) -> chromadb.ClientAPI:
    persist_dir = Path(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def build_vector_store(
    question_bank_path: Path | str = DEFAULT_QUESTION_BANK_PATH,
    persist_dir: Path | str = DEFAULT_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> Collection:
    """
    (Re)build the persisted Chroma collection from question_bank_path.

    Safe to call repeatedly -- any existing collection with the same name
    is dropped and rebuilt from scratch, so the index always reflects the
    current contents of data/question_bank.json rather than accumulating
    stale or duplicate entries across reruns.
    """
    questions = load_questions_from_json(question_bank_path)
    if not questions:
        raise ValueError(f"No questions loaded from {question_bank_path}")

    client = _get_client(persist_dir)
    try:
        client.delete_collection(collection_name)
    except Exception:  # noqa: BLE001 -- fine, means the collection didn't exist yet
        pass
    collection = client.create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

    ids = [q.question_id for q in questions]
    documents = [q.question_text for q in questions]
    metadatas = [{"job_type": q.job_type or "", "question_type": q.question_type} for q in questions]
    embeddings = embed_texts(documents)

    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings.tolist())
    logger.info("Built Chroma collection %r with %d questions at %s", collection_name, len(questions), persist_dir)
    return collection


def get_or_build_collection(
    question_bank_path: Path | str = DEFAULT_QUESTION_BANK_PATH,
    persist_dir: Path | str = DEFAULT_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> Collection:
    """Return the persisted collection, building it on first use if it doesn't exist yet or is empty."""
    client = _get_client(persist_dir)
    try:
        collection = client.get_collection(collection_name)
        if collection.count() > 0:
            return collection
    except Exception:  # noqa: BLE001 -- collection not found yet, fall through to build
        pass
    return build_vector_store(question_bank_path, persist_dir, collection_name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_vector_store()
