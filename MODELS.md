# Local Model Catalog & Specifications

All inference in Prime Agent is powered by genuinely acquired, locally stored, and verified models. No external APIs or cloud endpoints are required.

---

## 1. Verified Model Inventory

| Role | Model Name | Format | Quantization | Size | Local Path | Verified SHA256 Hash |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary LLM** | `Qwen3-4B-Instruct` | GGUF | Q4_K_M | 2.5 GB | `models/primary/Qwen3-4B-Q4_K_M.gguf` | `f6f851777709861056efcdad3af01da38b31223a3ba26e61a4f8bf3a2195813a` |
| **Draft Speculative** | `Qwen2.5-0.5B-Instruct` | GGUF | Q4_K_M | 491 MB | `models/draft/qwen2.5-0.5b-instruct-q4_k_m.gguf` | `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db` |
| **Abliterated LLM** | `Qwen2.5-Coder-0.5B-Abliterated` | GGUF | Q4_K_M | 397 MB | `models/abliterated/Qwen2.5-Coder-0.5B-Instruct-abliterated-Q4_K_M.gguf` | `4ef305ffe4d769f9637df26d0e0d56cf4e9f2fd8284e34e2827be496c8cd0674b` |
| **Vision VLM** | `Qwen2-VL-2B-Instruct` | GGUF | Q4_K_M | 986 MB | `models/vision/Qwen2-VL-2B-Instruct-Q4_K_M.gguf` | `4ef095263343fc1237e8ca879790bb262bcf209f082e0a9bfce219b7ece55e8b` |
| **Vision Projector** | `mmproj-Qwen2-VL-2B-f16` | GGUF | F16 | 1.33 GB | `models/vision/mmproj-Qwen2-VL-2B-Instruct-f16.gguf` | `05cc3ae461a7b6aa4023312ccab549ecab77cf8677efee04f049fcbab55b8bc3` |
| **Embeddings** | `all-MiniLM-L6-v2` | PyTorch | F32 | ~90 MB | Cached local via HuggingFace | `e4ce9877abf3ed15e85c27221e24b6097edd9322` |
| **Diffusion Studio** | `tiny-sd` | PyTorch | FP16/FP32 | ~600 MB | `models/image/tiny-sd/` | Validated local diffusion checkpoints |

---

## 2. Hardware Acceleration & Runtime

### Inference Engine: `llama.cpp` (Build 10977)
- **Vulkan Binary**: `runtime/llama.cpp/vulkan/llama-server.exe`
  - Targets AMD Radeon 680M iGPU via Vulkan API (`vulkan-1.dll`).
  - Supports full layer offloading (`-ngl 99`).
- **CPU Fallback Binary**: `runtime/llama.cpp/cpu/llama-server.exe`
  - Optimized with AVX2 and FMA instructions for x86_64 host processor.

### Speculative Decoding Pipeline
The primary model (`Qwen3-4B-Instruct`) runs in tandem with the small draft model (`Qwen2.5-0.5B-Instruct`) using llama.cpp speculative decoding:
```bash
llama-server.exe \
  -m models/primary/Qwen3-4B-Q4_K_M.gguf \
  -md models/draft/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --spec-draft-n-max 8 \
  -ngl 99 \
  -ngld 99 \
  -c 4096 \
  --port 8080
```
- **Performance**:
  - Prompt prefill speed: **~90.25 tokens/second**
  - Decode speed: **~26.92 tokens/second**
  - Memory consumption: < 3.5 GB shared VRAM

---

## 3. Configuration Specification (`config/models.json`)

The platform dynamically loads model parameters and paths from `config/models.json`:
```json
{
  "primary": {
    "name": "Qwen3-4B-Instruct",
    "path": "models/primary/Qwen3-4B-Q4_K_M.gguf",
    "draft_model": "models/draft/qwen2.5-0.5b-instruct-q4_k_m.gguf",
    "context_size": 4096,
    "gpu_layers": 99,
    "temperature": 0.2
  },
  "vision": {
    "name": "Qwen2-VL-2B-Instruct",
    "path": "models/vision/Qwen2-VL-2B-Instruct-Q4_K_M.gguf",
    "mmproj": "models/vision/mmproj-Qwen2-VL-2B-Instruct-f16.gguf",
    "context_size": 2048,
    "gpu_layers": 99
  },
  "abliterated": {
    "name": "Qwen2.5-Coder-0.5B-Instruct-Abliterated",
    "path": "models/abliterated/Qwen2.5-Coder-0.5B-Instruct-abliterated-Q4_K_M.gguf",
    "context_size": 2048,
    "gpu_layers": 99
  }
}
```

---

## 4. Model Lifecycle & Port Management

The `ModelManager` class (`services/llm/model_manager.py`) manages model transitions:
- Detects stale processes holding the target port and cleanly frees sockets using `free_port(port)`.
- Monitors process stdout/stderr for HTTP server readiness.
- Automatically handles graceful termination upon agent shutdown.
