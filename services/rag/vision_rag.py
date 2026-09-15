"""Vision-RAG extension for Prime Agent.

Indexes images into the hybrid RAG system by running local VLM inference
for OCR, object detection, and layout analysis, linking text to image artifacts.
"""

from __future__ import annotations
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Optional
from services.llm.client import LLMClient
from services.rag.index import HybridRAGIndex
from services.rag.parser import DocumentSection, ParsedDocument


class VisionRAG:
    """Extracts multimodal visual knowledge from images and indexes into RAG."""

    def __init__(self, rag_index: HybridRAGIndex, llm_client: LLMClient):
        self.index = rag_index
        self.llm = llm_client

    async def ingest_image(self, image_path: str, vlm_port: int = 8085) -> Dict[str, Any]:
        p = Path(image_path)
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        h = hashlib.sha256(image_bytes).hexdigest()

        # Extract OCR and Scene understanding with VLM
        prompt = (
            "Analyze this image thoroughly for technical documentation and indexing:\n"
            "1. OCR: Transcribe all visible text exactly.\n"
            "2. Description: Describe the key objects, relationships, and layout.\n"
            "3. Entities: List important entities or concepts depicted."
        )

        resp = await self.llm.chat_with_image(prompt=prompt, image_bytes=image_bytes, port=vlm_port)
        vlm_content = resp.content

        # Create virtual document
        doc = ParsedDocument(
            file_path=str(p.resolve()),
            file_name=p.name,
            file_type=p.suffix.lstrip("."),
            file_size=len(image_bytes),
            sha256=h,
            sections=[
                DocumentSection(
                    content=vlm_content,
                    section_title=f"Visual Analysis of {p.name}",
                    metadata={"is_image": True, "image_path": str(p.resolve())}
                )
            ]
        )

        # Chunk and insert into index
        new_chunks = self.index.chunker.chunk_document(doc)
        if new_chunks:
            new_texts = [c.content for c in new_chunks]
            new_emb = self.index.embedder.embed_texts(new_texts)
            to_keep = [c for c in self.index.chunks if c.file_path != doc.file_path]
            if to_keep and self.index.embeddings is not None:
                keep_indices = [i for i, c in enumerate(self.index.chunks) if c.file_path != doc.file_path]
                kept_emb = self.index.embeddings[keep_indices]
                self.index.embeddings = np.vstack([kept_emb, new_emb])
                self.index.chunks = to_keep + new_chunks
            else:
                self.index.chunks = new_chunks
                self.index.embeddings = new_emb

            self.index.tokenized_corpus = [self.index._tokenize(c.content) for c in self.index.chunks]
            self.index.bm25 = BM25Okapi(self.index.tokenized_corpus)
            self.index.save()

        return {
            "image_path": str(p.resolve()),
            "sha256": h,
            "vlm_summary": vlm_content[:200],
            "status": "indexed"
        }
