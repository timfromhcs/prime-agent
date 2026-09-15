"""Test Suite for Hybrid RAG: Parsing, Semantic Chunking, Dense+BM25, and Citations."""

import pytest
from services.rag.index import HybridRAGIndex
from services.rag.parser import DocumentParser


def test_document_parser_and_chunker(tmp_path):
    # Create deterministic markdown document
    md_file = tmp_path / "architecture.md"
    md_content = """# Prime System Architecture

## Kernel Design
The persistent Python kernel executes user cells with top-level await support.
Variables and imports remain preserved in the persistent namespace.

## Model Offloading
AMD Radeon integrated graphics utilizes Vulkan backend for acceleration.
Inference achieves over 25 tokens per second with draft model speculation.
"""
    md_file.write_text(md_content, encoding="utf-8")

    parser = DocumentParser()
    doc = parser.parse(str(md_file))
    assert doc.file_name == "architecture.md"
    assert len(doc.sections) >= 2
    assert len(doc.sha256) == 64


def test_hybrid_retrieval_and_evidence_pack(tmp_path):
    index_file = tmp_path / "test_rag.json"
    rag = HybridRAGIndex(index_file=str(index_file))

    # Ingest document
    doc_path = tmp_path / "spec.txt"
    doc_path.write_text(
        "Quantum encryption relies on quantum entanglement and photon polarization.\n"
        "Traditional encryption uses asymmetric key pairs such as RSA 4096.\n",
        encoding="utf-8"
    )
    res = rag.ingest_file(str(doc_path))
    assert res["status"] == "ingested"
    assert res["chunks_added"] >= 1

    # Query hybrid RAG
    pack = rag.search("quantum photon polarization", top_k=2)
    assert pack.total_retrieved >= 1
    top_item = pack.items[0]
    assert "quantum" in top_item.content.lower()
    assert top_item.sha256 == res["sha256"]
    assert "spec.txt" in top_item.citation
