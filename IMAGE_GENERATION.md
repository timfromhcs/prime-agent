# Diffusion Image Generation Subsystem

Prime Agent includes an on-demand, local image generation engine based on HuggingFace `diffusers` and the lightweight `tiny-sd` Stable Diffusion pipeline.

---

## 1. Engine Architecture

```
Agent / User Prompt ("A futuristic terminal interface on Mars")
                        │
                        ▼
       Prompt Normalization & Seeding (services/image/pipeline.py)
                        │
                        ▼
     StableDiffusionPipeline (models/image/tiny-sd)
     ├── Text Encoder: CLIPViT
     ├── UNet: Compact 4-layer latent denoiser
     └── VAE Decoder: Latent-to-RGB conversion
                        │
                        ▼
            Pillow Image Generation
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
Artifact Cataloging             Visual QA & CV Metrics
(services/image/store.py)        (services/image/qa.py)
- SHA256 Hash                    - Laplacian Edge Variance
- Metadata JSON                  - Contrast & Brightness Check
- data/artifacts/                - Color Histogram Analysis
```

---

## 2. Artifact Cataloging & Provenance (`services/image/store.py`)

Every generated or edited image is registered in the persistent artifact catalog (`data/artifacts/catalog.json`):
- **Image ID**: Unique prefixed identifier (e.g., `img_d32da26e`).
- **File Path**: Relocated into `data/artifacts/<id>.png`.
- **SHA256**: Cryptographic content hash computed immediately upon creation to detect accidental overwrites or corruption.
- **Generation Metadata**: Prompt, seed, inference steps, guidance scale, dimensions, and parent image IDs (for edits).

---

## 3. Visual Quality Assurance (`services/image/qa.py`)

To prevent blurry or blank images from being presented as valid outputs, the `VisualQA` engine computes automated computer vision metrics:
- **Sharpness / Focus**: Computes the variance of the Laplacian filter over the image matrix. Low variance indicates blurriness.
- **Contrast & Dynamic Range**: Calculates standard deviation of pixel intensity. Low values indicate washed-out or flat images.
- **Color Uniformity**: Checks color channel distributions to flag completely black, white, or monochrome error outputs.
- **Overall Score**: Normalizes metrics into a `[0.0, 1.0]` confidence score. Images below the quality threshold (`0.6`) trigger an automatic re-generation.

---

## 4. Usage Example

### Generating an Image Programmatically:
```python
import asyncio
from services.image.pipeline import ImagePipeline

async def generate():
    pipe = ImagePipeline()
    
    result = await pipe.generate_image(
        prompt="A minimalist cyberpunk laboratory server rack, cinematic lighting",
        width=256,
        height=256,
        num_inference_steps=15,
        seed=42
    )
    
    print("Artifact ID:", result["artifact_id"])
    print("Saved Path:", result["file_path"])
    print("SHA256:", result["sha256"])
    print("QA Score:", result["qa_score"])

asyncio.run(generate())
```

---

## 5. Performance Profile

- **Device**: CPU / Vulkan
- **Resolution**: 256x256 or 512x512
- **Latency**: ~10–18 seconds for 15 inference steps on AMD Ryzen 7 7735HS.
- **Storage**: ~600 MB model footprint on disk.
