# Hardware Optimization, Benchmarking & Multi-Tier Profiles

This document details hardware detection, runtime tuning, speculative decoding configuration, comparative benchmark metrics measured on the target host, and the multi-tier profile system.

---

## 1. Host Hardware Environment

- **Operating System**: Windows 11 Pro (10.0.26200)
- **CPU**: AMD Ryzen 7 7735HS with Radeon 680M Graphics (8 Cores, 16 Logical Threads)
- **Integrated GPU (iGPU)**: AMD Radeon 680M
  - Architecture: RDNA 2 (12 Compute Units)
  - VRAM: Shared system memory (~4 GB dynamically allocated window)
  - Driver & API: Vulkan 1.4 (`vulkan-1.dll`)
- **System Memory**: ~20 GB DDR5 RAM (~10 GB Free)
- **Storage**: Fast NVMe SSD (Drive E: ~450 GB free)

---

## 2. Comparative Benchmark Matrix

Measured using `scripts/run_benchmarks.py` on the local machine:

| Workload Configuration | Model Setup | Prompt Prefill | Generation Decode | Load Time | Memory (RAM/VRAM) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Baseline Standalone** | `Qwen3-4B-Q4_K_M` (No Draft) | **156.93 tok/s** | **26.77 tok/s** | 2.85 s | ~2.5 GB | **VERIFIED** |
| **Upgraded Speculative** | `Qwen3-4B` + `Qwen2.5-0.5B` Draft | **156.92 tok/s** | **27.02 tok/s** | 3.10 s | ~3.1 GB | **VERIFIED** |
| **Hybrid RAG Query** | Dense MiniLM + Sparse BM25 | Latency: **13.81 ms** | Recall@1: **100%** | < 0.1 s | ~150 MB | **VERIFIED** |
| **Diffusion Image Gen** | `tiny-sd` (256x256, 5 steps) | Latency: **4.12 s** | Visual QA: **PASS** | 2.10 s | ~600 MB | **VERIFIED** |
| **Diffusion Image Edit** | `tiny-sd` img2img (256x256, 4 steps) | Latency: **1.24 s** | Delta: **PASS** | Resident | ~600 MB | **VERIFIED** |

- Report records:
  - Baseline: `benchmarks/baseline.json`
  - Upgraded: `benchmarks/upgraded.json`

---

## 3. Multi-Tier Profile System (`config/profiles.json`)

To support different task demands and memory constraints, the platform defines 7 tested profiles:

### 1. `LOW_MEMORY`
- **Target**: Constrained environments (< 8 GB RAM)
- **Setup**: `Qwen3-4B-Q4_K_M`, no draft model, `-c 2048`, `q8_0` KV cache
- **Memory Footprint**: ~2.2 GB

### 2. `BALANCED` (Default Active Profile)
- **Target**: Daily driver for coding, reasoning, and research
- **Setup**: `Qwen3-4B-Q4_K_M` + `Qwen2.5-0.5B` draft (`--spec-draft-n-max 8`, `-ngld 99`), `-c 4096`, `f16` KV cache
- **Performance**: 156 tok/s prefill, 27 tok/s decode, ~3.5 GB memory

### 3. `QUALITY`
- **Target**: Deep technical reasoning requiring large context windows
- **Setup**: `Qwen3-4B-Q4_K_M` + draft model, `-c 8192`, `f16` KV cache
- **Memory Footprint**: ~4.2 GB

### 4. `LONG_CONTEXT`
- **Target**: Large codebase or multi-document ingestion
- **Setup**: `Qwen3-4B-Q4_K_M`, `-c 16384`, `q4_0` quantized KV cache
- **Memory Footprint**: ~4.8 GB

### 5. `CODING`
- **Target**: Automated programming, AST inspection, unit test loops
- **Setup**: `Qwen3-4B-Q4_K_M` + `Qwen2.5-0.5B` draft, persistent Python REPL
- **Memory Footprint**: ~3.5 GB

### 6. `VISION`
- **Target**: Document OCR, screenshot analysis, and visual question answering
- **Setup**: `Qwen2-VL-2B-Instruct` + `mmproj-Qwen2-VL-2B-Instruct-f16.gguf` on port 8085
- **Memory Footprint**: ~2.6 GB

### 7. `IMAGE`
- **Target**: On-demand text-to-image and image-to-image diffusion
- **Setup**: `tiny-sd` pipeline (CPU/Vulkan), 256x256 / 512x512 with VLM QA validation
- **Memory Footprint**: ~1.8 GB (unloaded on demand)

---

## 4. Active Optimal Profile (`config/optimal-profile.json`)

```json
{
  "selected_profile": "BALANCED",
  "profile_spec": {
    "description": "Default daily driver: full speculative acceleration on Vulkan iGPU",
    "primary_model": "models/primary/Qwen3-4B-Q4_K_M.gguf",
    "speculative_draft": "models/draft/qwen2.5-0.5b-instruct-q4_k_m.gguf",
    "spec_draft_n_max": 8,
    "backend": "vulkan",
    "context_size": 4096,
    "gpu_layers": 99,
    "threads": 8,
    "kv_cache_type": "f16",
    "estimated_ram_mb": 3500
  },
  "benchmarks": {
    "baseline_decode_tok_s": 26.77,
    "speculative_decode_tok_s": 27.02,
    "rag_latency_ms": 13.81
  }
}
```
