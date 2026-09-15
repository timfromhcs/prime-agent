"""Evidence Pack and Reranking system for Prime RAG.

Combines dense vector retrieval and BM25 lexical retrieval using Reciprocal Rank Fusion (RRF),
scores chunks, and structures results into verifiable Evidence Packs with exact citations.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np
from services.rag.chunker import RAGChunk


@dataclass
class EvidenceItem:
    chunk_id: str
    file_path: str
    file_name: str
    sha256: str
    section_title: str
    page_number: Optional[int]
    line_start: Optional[int]
    line_end: Optional[int]
    content: str
    score: float
    citation: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidencePack:
    query: str
    items: List[EvidenceItem]
    total_retrieved: int

    def format_citations(self) -> str:
        lines = []
        for idx, item in enumerate(self.items, 1):
            lines.append(f"[{idx}] {item.citation} (relevance: {item.score:.3f}):")
            lines.append(f"    {item.content[:200]}...")
        return "\n".join(lines)


class EvidenceReranker:
    """Reranks candidate chunks and formats verified evidence packs."""

    def __init__(self, dense_weight: float = 0.5, bm25_weight: float = 0.5, k_rrf: int = 60):
        self.dense_weight = dense_weight
        self.bm25_weight = bm25_weight
        self.k_rrf = k_rrf

    def fuse_and_rerank(
        self,
        query: str,
        dense_candidates: List[tuple[RAGChunk, float]],
        bm25_candidates: List[tuple[RAGChunk, float]],
        top_k: int = 3
    ) -> EvidencePack:
        rrf_scores: Dict[str, float] = {}
        chunk_map: Dict[str, RAGChunk] = {}

        for rank, (chunk, score) in enumerate(dense_candidates):
            cid = chunk.chunk_id
            chunk_map[cid] = chunk
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + self.dense_weight * (1.0 / (self.k_rrf + rank + 1))

        for rank, (chunk, score) in enumerate(bm25_candidates):
            cid = chunk.chunk_id
            chunk_map[cid] = chunk
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + self.bm25_weight * (1.0 / (self.k_rrf + rank + 1))

        sorted_cids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)[:top_k]

        items: List[EvidenceItem] = []
        for cid in sorted_cids:
            chunk = chunk_map[cid]
            score = rrf_scores[cid]
            page_info = f"p.{chunk.page_number}" if chunk.page_number else (f"L{chunk.line_start}-{chunk.line_end}" if chunk.line_start else "")
            loc_str = f" ({page_info})" if page_info else ""
            citation = f"{chunk.file_name}:{chunk.section_title}{loc_str} [sha256:{chunk.sha256[:8]}]"

            items.append(EvidenceItem(
                chunk_id=chunk.chunk_id,
                file_path=chunk.file_path,
                file_name=chunk.file_name,
                sha256=chunk.sha256,
                section_title=chunk.section_title,
                page_number=chunk.page_number,
                line_start=chunk.line_start,
                line_end=chunk.line_end,
                content=chunk.content,
                score=score,
                citation=citation,
                metadata=chunk.metadata
            ))

        return EvidencePack(query=query, items=items, total_retrieved=len(items))
