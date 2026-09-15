# Hybrid RAG Subsystem

The Prime Agent Retrieval-Augmented Generation (RAG) subsystem implements a hybrid retrieval engine combining dense semantic vector embeddings, BM25Okapi sparse keyword search, Reciprocal Rank Fusion (RRF) reranking, and multimodal vision indexing.

---

## 1. Architecture Overview

```
Document Sources (PDF, DOCX, MD, HTML, Code, Images)
                        │
                        ▼
           Unified Document Parser (services/rag/parser.py)
                        │
                        ▼
         Semantic Boundary Chunker (services/rag/chunker.py)
           ├── Markdown Headings & Code Blocks
           └── Overlap Preservation
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
Dense Embeddings Vectorizer   Sparse BM25 Inverted Index
(all-MiniLM-L6-v2)             (BM25Okapi Token Frequency)
         │                             │
         └──────────────┬──────────────┘
                        ▼
           Reciprocal Rank Fusion Reranker (services/rag/reranker.py)
                        │
                        ▼
            Structured Evidence Pack (Citations, Scores, Content)
```

---

## 2. Component Breakdown

### 2.1 Unified Parser (`services/rag/parser.py`)
Extracts text and metadata from heterogeneous local formats:
- **Markdown / Text / Source Code**: Parsed with line numbers and structural context.
- **PDF**: Uses `pypdf` to extract text per page with layout retention.
- **DOCX**: Uses `python-docx` for section and paragraph extraction.
- **HTML**: Uses `BeautifulSoup4` with script/style stripping.
- **Images**: Automatically routed through the VLM Vision Pipeline for OCR and scene caption extraction.

### 2.2 Semantic Chunker (`services/rag/chunker.py`)
- **Structure-Aware**: Rather than naive character slicing, chunks are segmented along natural markdown headers (`#`, `##`, `###`), function/class declarations, and paragraphs.
- **Configurable Sizing**: Defaults to target chunk size of 512 tokens with 64 token overlapping windows to ensure boundary continuity.

### 2.3 Dense Vector Embeddings (`services/rag/embeddings.py`)
- **Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Footprint**: Lightweight 384-dimensional dense vectors running locally on CPU.
- **Normalization**: L2-normalized embeddings for fast cosine distance calculation via dot products.

### 2.4 Sparse Keyword Search (`services/rag/index.py`)
- **Algorithm**: `rank_bm25.BM25Okapi`
- **Tokenizer**: Custom case-folded word tokenizer with punctuation stripping.
- **Strength**: Excels at exact symbol matches, function names, error codes, and unique identifiers where dense semantic models may lose specificity.

### 2.5 Reciprocal Rank Fusion Reranker (`services/rag/reranker.py`)
Combines dense and sparse ranked lists using standard RRF:
$$RRF\_Score(d) = \sum_{m \in \{dense, bm25\}} \frac{1}{k + rank_m(d)}$$
where $k = 60$.

This eliminates the need for score calibration across heterogeneous retrieval algorithms and yields higher precision on complex technical queries.

---

## 3. Vision RAG Integration (`services/rag/vision_rag.py`)

Visual documents (diagrams, architecture charts, receipts, screenshots) are ingested into the RAG index through a two-stage process:
1. The image is passed to `Qwen2-VL-2B-Instruct` via the multimodal projector to extract OCR text, tabular data, and visual descriptions.
2. The resulting textual representation is embedded into the dense/sparse index with citations pointing to the original image artifact path (`data/artifacts/...`).

---

## 4. Usage Examples

### Ingesting Files or Directories via CLI:
```powershell
# Ingest single file
.\prime.ps1 rag ingest "data/documents/agent_spec.md"

# Ingest entire directory
.\prime.ps1 rag ingest "docs/"
```

### Searching from Python:
```python
from services.rag.index import HybridRAGIndex

index = HybridRAGIndex()
pack = index.search("How does the harness manage rollback?", top_k=3)

for item in pack.items:
    print(f"[{item.citation}] (Score: {item.score:.4f})")
    print(item.content)
```
