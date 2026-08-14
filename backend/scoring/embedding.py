"""
Shared multilingual sentence-embedding model.

Both backend/scoring/baseline.py (semantic-similarity signals for the
specificity/logical-coherence dimensions and structure-element detection)
and backend/rag/vector_store.py + backend/rag/retriever.py (question-bank
vector search) embed Chinese and English text with the exact same model, so
scores and retrieval results are computed in one shared vector space. This
module is the single place that name is spelled out and the model is
loaded, so the two call sites can never drift onto different models.

paraphrase-multilingual-MiniLM-L12-v2 was chosen specifically because it is
one model covering both Chinese and English well (this project's question
bank and candidate answers are both bilingual, see docs/decision_log.md
decision 13), rather than needing a language-specific model per language.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    """Lazily load and cache the shared embedding model (first call downloads/loads weights)."""
    global _model
    if _model is None:
        logger.info("Loading embedding model %r (first call only)", EMBEDDING_MODEL_NAME)
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Embed a batch of texts as L2-normalized vectors.

    Normalizing at embedding time means every downstream cosine-similarity
    computation collapses to a plain dot product -- see cosine_similarity()
    below.
    """
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    model = get_embedding_model()
    return model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two already-normalized embedding vectors (plain dot product)."""
    return float(np.dot(a, b))
