"""Embeddings provider for Prime RAG.

Uses sentence-transformers with the verified local all-MiniLM-L6-v2 model.
"""

from __future__ import annotations
from typing import List
import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingModel:
    """Computes dense vector representations for texts."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        self.dimension = 384

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        return self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

    def embed_query(self, query: str) -> np.ndarray:
        return self._model.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]
