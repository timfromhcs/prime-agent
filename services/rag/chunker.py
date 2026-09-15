"""Structure-Aware Semantic Chunker for Prime RAG.

Splits parsed document sections into grounded chunks respecting natural boundaries
(paragraphs, code blocks, sentences) and attaching complete provenance metadata.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from services.rag.parser import ParsedDocument, DocumentSection


@dataclass
class RAGChunk:
    chunk_id: str
    file_path: str
    file_name: str
    file_type: str
    sha256: str
    section_title: str
    page_number: Optional[int]
    line_start: Optional[int]
    line_end: Optional[int]
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class SemanticChunker:
    """Chunks structured document sections preserving context and attribution."""

    def __init__(self, target_chunk_size: int = 512, chunk_overlap: int = 64):
        self.target_chunk_size = target_chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_document(self, doc: ParsedDocument) -> List[RAGChunk]:
        chunks: List[RAGChunk] = []
        chunk_idx = 0

        for sec in doc.sections:
            text = sec.content.strip()
            if not text:
                continue

            if len(text) <= self.target_chunk_size:
                chunk_id = f"{doc.sha256[:8]}_{chunk_idx}"
                chunks.append(RAGChunk(
                    chunk_id=chunk_id,
                    file_path=doc.file_path,
                    file_name=doc.file_name,
                    file_type=doc.file_type,
                    sha256=doc.sha256,
                    section_title=sec.section_title,
                    page_number=sec.page_number,
                    line_start=sec.line_start,
                    line_end=sec.line_end,
                    content=text,
                    metadata=sec.metadata
                ))
                chunk_idx += 1
            else:
                # Split by paragraphs or double newlines
                paragraphs = re.split(r"\n\s*\n", text)
                current_chunk = []
                current_len = 0

                for p in paragraphs:
                    p = p.strip()
                    if not p:
                        continue
                    if current_len + len(p) > self.target_chunk_size and current_chunk:
                        chunk_text = "\n\n".join(current_chunk)
                        chunk_id = f"{doc.sha256[:8]}_{chunk_idx}"
                        chunks.append(RAGChunk(
                            chunk_id=chunk_id,
                            file_path=doc.file_path,
                            file_name=doc.file_name,
                            file_type=doc.file_type,
                            sha256=doc.sha256,
                            section_title=sec.section_title,
                            page_number=sec.page_number,
                            line_start=sec.line_start,
                            line_end=sec.line_end,
                            content=chunk_text,
                            metadata=sec.metadata
                        ))
                        chunk_idx += 1
                        current_chunk = [p]
                        current_len = len(p)
                    else:
                        current_chunk.append(p)
                        current_len += len(p)

                if current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    chunk_id = f"{doc.sha256[:8]}_{chunk_idx}"
                    chunks.append(RAGChunk(
                        chunk_id=chunk_id,
                        file_path=doc.file_path,
                        file_name=doc.file_name,
                        file_type=doc.file_type,
                        sha256=doc.sha256,
                        section_title=sec.section_title,
                        page_number=sec.page_number,
                        line_start=sec.line_start,
                        line_end=sec.line_end,
                        content=chunk_text,
                        metadata=sec.metadata
                    ))
                    chunk_idx += 1

        return chunks
