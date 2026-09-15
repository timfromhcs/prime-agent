"""Hybrid RAG Index for Prime Agent.

Combines dense vector search (cosine similarity) with lexical BM25 search,
supports on-disk persistence, incremental document ingestion, and evidence packaging.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from rank_bm25 import BM25Okapi

from services.rag.chunker import RAGChunk, SemanticChunker
from services.rag.embeddings import EmbeddingModel
from services.rag.parser import DocumentParser, ParsedDocument
from services.rag.reranker import EvidencePack, EvidenceReranker


class HybridRAGIndex:
    """Manages document ingestion, dual-index storage, and hybrid retrieval."""

    def __init__(
        self,
        index_file: str = "data/indexes/rag_index.json",
        embedding_model: Optional[EmbeddingModel] = None,
        chunk_size: int = 512,
        chunk_overlap: int = 64
    ):
        self.index_file = Path(index_file)
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        self.parser = DocumentParser()
        self.chunker = SemanticChunker(target_chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.embedder = embedding_model or EmbeddingModel()
        self.reranker = EvidenceReranker()

        self.chunks: List[RAGChunk] = []
        self.embeddings: Optional[np.ndarray] = None
        self.bm25: Optional[BM25Okapi] = None
        self.tokenized_corpus: List[List[str]] = []
        self._load()

    def _tokenize(self, text: str) -> List[str]:
        return [w.lower() for w in text.split() if len(w) > 1]

    def _load(self):
        if not self.index_file.exists():
            return
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_chunks = data.get("chunks", [])
            self.chunks = [RAGChunk(**c) for c in raw_chunks]

            raw_emb = data.get("embeddings")
            if raw_emb:
                self.embeddings = np.array(raw_emb, dtype=np.float32)

            self.tokenized_corpus = [self._tokenize(c.content) for c in self.chunks]
            if self.tokenized_corpus:
                self.bm25 = BM25Okapi(self.tokenized_corpus)
        except Exception as e:
            print(f"[RAG] Warning loading index: {e}")

    def save(self):
        data = {
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "file_path": c.file_path,
                    "file_name": c.file_name,
                    "file_type": c.file_type,
                    "sha256": c.sha256,
                    "section_title": c.section_title,
                    "page_number": c.page_number,
                    "line_start": c.line_start,
                    "line_end": c.line_end,
                    "content": c.content,
                    "metadata": c.metadata
                }
                for c in self.chunks
            ],
            "embeddings": self.embeddings.tolist() if self.embeddings is not None else [],
            "total_chunks": len(self.chunks)
        }
        temp_file = self.index_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(self.index_file)

    def ingest_file(self, file_path: str) -> Dict[str, Any]:
        """Ingests a file, extracts sections, chunks, embeds, and updates BM25."""
        parsed_doc = self.parser.parse(file_path)

        # Remove previous chunks for this file if re-indexing
        to_keep = [c for c in self.chunks if c.file_path != parsed_doc.file_path]
        new_chunks = self.chunker.chunk_document(parsed_doc)
        if not new_chunks:
            return {"file": file_path, "status": "skipped", "chunks": 0}

        new_texts = [c.content for c in new_chunks]
        new_emb = self.embedder.embed_texts(new_texts)

        if to_keep and self.embeddings is not None:
            keep_indices = [i for i, c in enumerate(self.chunks) if c.file_path != parsed_doc.file_path]
            kept_emb = self.embeddings[keep_indices]
            self.embeddings = np.vstack([kept_emb, new_emb])
            self.chunks = to_keep + new_chunks
        else:
            self.chunks = new_chunks
            self.embeddings = new_emb

        self.tokenized_corpus = [self._tokenize(c.content) for c in self.chunks]
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        self.save()

        return {
            "file": file_path,
            "status": "ingested",
            "chunks_added": len(new_chunks),
            "total_index_chunks": len(self.chunks),
            "sha256": parsed_doc.sha256
        }

    def ingest_directory(self, dir_path: str) -> List[Dict[str, Any]]:
        results = []
        p = Path(dir_path)
        supported_exts = {".md", ".txt", ".pdf", ".docx", ".py", ".ts", ".js", ".json", ".html"}
        for f in p.rglob("*"):
            if f.is_file() and f.suffix.lower() in supported_exts:
                try:
                    res = self.ingest_file(str(f))
                    results.append(res)
                except Exception as e:
                    results.append({"file": str(f), "status": "error", "error": str(e)})
        return results

    def search(self, query: str, top_k: int = 3) -> EvidencePack:
        """Executes hybrid retrieval: dense cosine similarity + BM25Okapi + fusion."""
        if not self.chunks or self.embeddings is None:
            return EvidencePack(query=query, items=[], total_retrieved=0)

        # 1. Dense retrieval
        q_emb = self.embedder.embed_query(query)
        # Cosine similarity: dot product since vectors are normalized
        dense_scores = np.dot(self.embeddings, q_emb)
        top_dense_indices = np.argsort(dense_scores)[::-1][: top_k * 3]
        dense_candidates: List[Tuple[RAGChunk, float]] = [
            (self.chunks[i], float(dense_scores[i])) for i in top_dense_indices
        ]

        # 2. BM25 retrieval
        bm25_candidates: List[Tuple[RAGChunk, float]] = []
        if self.bm25:
            tokens = self._tokenize(query)
            if tokens:
                bm25_scores = self.bm25.get_scores(tokens)
                top_bm25_indices = np.argsort(bm25_scores)[::-1][: top_k * 3]
                bm25_candidates = [
                    (self.chunks[i], float(bm25_scores[i])) for i in top_bm25_indices
                ]

        # 3. Fuse & Rerank
        return self.reranker.fuse_and_rerank(
            query=query,
            dense_candidates=dense_candidates,
            bm25_candidates=bm25_candidates,
            top_k=top_k
        )
