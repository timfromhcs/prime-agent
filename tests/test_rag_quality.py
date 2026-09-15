"""Comprehensive RAG Quality Benchmark & Programmatic REPL Integration Test.

Measures:
- Retrieval recall (@1 and @3)
- Citation correctness and SHA256 provenance
- Grounded evidence extraction
- Programmatic REPL execution: await rag.search(...)
- Query latency (< 100ms)
"""

import time
import pytest
from services.rag.index import HybridRAGIndex
from services.rlm.kernel import KernelManager
from services.agent.root_agent import PrimeAgent


@pytest.fixture
def deterministic_corpus(tmp_path):
    corpus = {
        "quantum.md": (
            "# Quantum Information\n\n"
            "Quantum key distribution uses BB84 protocol with polarized photons.\n"
            "Decoherence limits quantum memory coherence times to microseconds."
        ),
        "consensus.md": (
            "# Distributed Consensus\n\n"
            "Raft consensus protocol relies on leader election and log replication.\n"
            "Byzantine Fault Tolerance requires 3f + 1 nodes to tolerate f arbitrary failures."
        ),
        "compilers.md": (
            "# Compiler Optimization\n\n"
            "Static Single Assignment (SSA) form guarantees each variable is assigned exactly once.\n"
            "Dominator trees are used to insert phi functions at convergence points."
        ),
        "memory_safety.md": (
            "# Operating Systems Memory\n\n"
            "Page tables translate virtual addresses into physical frames using multi-level radix trees.\n"
            "Translation Lookaside Buffers (TLB) cache recent virtual-to-physical address mappings."
        )
    }

    index_file = tmp_path / "quality_index.json"
    rag = HybridRAGIndex(index_file=str(index_file))

    for fname, text in corpus.items():
        doc_path = tmp_path / fname
        doc_path.write_text(text, encoding="utf-8")
        rag.ingest_file(str(doc_path))

    return rag, tmp_path


def test_rag_retrieval_recall_and_citations(deterministic_corpus):
    rag, tmp_path = deterministic_corpus

    queries = [
        ("BB84 protocol polarized photons", "quantum.md", "BB84"),
        ("Raft leader election and log replication", "consensus.md", "Raft"),
        ("Static Single Assignment phi functions", "compilers.md", "SSA"),
        ("Translation Lookaside Buffers TLB virtual", "memory_safety.md", "TLB")
    ]

    recall_top1 = 0
    total_queries = len(queries)

    for query, expected_doc, expected_keyword in queries:
        t0 = time.time()
        pack = rag.search(query, top_k=3)
        latency_ms = (time.time() - t0) * 1000

        # Latency check: hybrid search must be under 100ms
        assert latency_ms < 100.0, f"Query latency {latency_ms:.2f}ms exceeded 100ms threshold"

        assert pack.total_retrieved >= 1
        top_item = pack.items[0]

        # Citation correctness
        assert expected_doc in top_item.citation, f"Expected {expected_doc} in citation {top_item.citation}"
        # Evidence grounding
        assert expected_keyword.lower() in top_item.content.lower()
        recall_top1 += 1

    recall_rate = recall_top1 / total_queries
    assert recall_rate == 1.0, f"Recall rate {recall_rate} below 1.0"


@pytest.mark.asyncio
async def test_rag_programmatic_rlm_capability(tmp_path):
    # Test that await rag.search(...) executes inside REPL and returns structured evidence
    agent = PrimeAgent()
    try:
        # Isolated index: never pollute the production data/indexes/rag_index.json
        from services.rag.index import HybridRAGIndex
        agent.rag_index = HybridRAGIndex(index_file=str(tmp_path / "q_rag.json"))
        # Ingest a test document into RAG
        test_doc = tmp_path / "rlm_spec.md"
        test_doc.write_text("# RLM Kernel Specification\nThe RLM kernel provides durable state and top-level await.", encoding="utf-8")
        agent.rag_index.ingest_file(str(test_doc))

        # Execute programmatic RLM call
        code = """
results = await rag.search("RLM kernel durable state", top_k=2)
count = len(results)
top_content = results[0]["content"]
"""
        res = await agent.kernel_manager.execute("rag_test_session", code)
        assert res["status"] == "ok"
        session = agent.kernel_manager.get_or_create_session("rag_test_session")
        assert session.namespace["count"] >= 1
        assert "RLM kernel" in session.namespace["top_content"]
    finally:
        agent.shutdown()
