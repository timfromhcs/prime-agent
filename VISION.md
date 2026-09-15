# Multimodal Vision & OCR Subsystem

Prime Agent features native multimodal vision capabilities powered by `Qwen2-VL-2B-Instruct` coupled with its multimodal projector (`mmproj`), executing locally over Vulkan GPU acceleration.

---

## 1. Vision Architecture

```
Image Source (Screenshot, Document, UI Design, Diagram)
                      │
                      ▼
        Base64 Image Encoding & Preprocessing
                      │
                      ▼
       llama-server (Vulkan with --mmproj)
        Models: Qwen2-VL-2B-Instruct + mmproj
                      │
                      ▼
         Vision Processing Engine
         ├── Optical Character Recognition (OCR)
         ├── UI / Structural Element Extraction
         └── Visual Question Answering (VQA)
                      │
                      ▼
       Integration with Agent / RAG Pipeline
```

---

## 2. Capabilities

1. **Optical Character Recognition (OCR)**: Extracts formatted text, code snippets, numbers, and headers from documents, screenshots, and diagrams.
2. **Structural Element Detection**: Identifies buttons, menus, cards, and layouts in UI mockups or application windows.
3. **Multimodal RAG Indexing**: Extracts textual descriptions and key entities from visual artifacts and ingests them directly into the hybrid RAG index.
4. **Visual QA & Inspection**: Validates generated images or edited visual assets against target prompts, checking alignment, contrast, and artifacts.

---

## 3. Server Configuration & Execution

To serve multimodal vision queries, `llama-server` is launched with both the language weights and the multimodal projector:
```bash
llama-server.exe \
  -m models/vision/Qwen2-VL-2B-Instruct-Q4_K_M.gguf \
  --mmproj models/vision/mmproj-Qwen2-VL-2B-Instruct-f16.gguf \
  -ngl 99 \
  -c 2048 \
  --port 8081
```

The server exposes standard OpenAI-compatible `/v1/chat/completions` accepting `image_url` data payloads:
```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "Extract all text from this document image:"
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
      }
    }
  ]
}
```

---

## 4. Python API (`services/rag/vision_rag.py`)

```python
import asyncio
from services.rag.vision_rag import VisionRAGProcessor

async def analyze_document():
    vlm = VisionRAGProcessor()
    
    # Extract OCR and description
    analysis = await vlm.process_image("data/test_fixtures/invoice_scan.png")
    
    print("Extracted Text:", analysis["extracted_text"])
    print("Scene Description:", analysis["description"])

asyncio.run(analyze_document())
```

---

## 5. Verification & Acceptance

The vision subsystem was verified during E2E acceptance testing on synthetic high-contrast text images. The VLM successfully identified embedded tokens (`PRIME_VERIFICATION_TOKEN_7735`) with 100% character accuracy.
