# Image Editing & Transformation Subsystem

Prime Agent supports instruction-guided and reference-based image modification, visual diffing, and iterative refinement.

---

## 1. Overview & Workflows

Image editing operations take an existing artifact as input, apply transformations according to agent or user instructions, and produce a new versioned artifact linked back to its progenitor.

```
Source Image (img_d32da26e.png) + Edit Instruction ("Add golden glow to central circuits")
                                    │
                                    ▼
                 Image-to-Image / Mask Pipeline
                                    │
                                    ▼
                 Transformed Image (img_6a2a0cd8.png)
                                    │
                                    ▼
                     Visual Diff & QA Validation
                 ├── Structural Similarity (SSIM)
                 ├── Color Shift & Delta E
                 └── Content Preservation Check
                                    │
                                    ▼
                     Updated Catalog & Provenance Tree
```

---

## 2. Capabilities

1. **Image-to-Image Conditioning**: Modifies style, lighting, or atmosphere while preserving compositional structure using `StableDiffusionImg2ImgPipeline`.
2. **Instruction-Guided Editing**: Accepts natural language instructions and adjusts conditioning strength (default `strength=0.65`) to balance transformation vs. source fidelity.
3. **Visual Diff Inspection**: Generates numerical diffs and delta maps highlighting modified regions.
4. **Lineage Tracking**: Every edited asset records its `parent_artifact_id` in `data/artifacts/catalog.json`, providing a full audit trail of edits.

---

## 3. Python API (`services/image/pipeline.py`)

```python
import asyncio
from services.image.pipeline import ImagePipeline

async def edit_asset():
    pipe = ImagePipeline()
    
    result = await pipe.edit_image(
        source_image_path="data/artifacts/img_d32da26e.png",
        prompt="A vibrant holographic blue version of the server rack",
        strength=0.6,
        num_inference_steps=15
    )
    
    print("New Artifact ID:", result["artifact_id"])
    print("Parent Artifact ID:", result["parent_id"])
    print("Diff Metric:", result["diff_metric"])

asyncio.run(edit_asset())
```

---

## 4. Visual Validation & Acceptance Testing

During E2E acceptance testing (Workflow E), an existing generated artifact (`img_d32da26e`) was processed through the image-to-image editing pipeline. The resulting image (`img_6a2a0cd8`) was validated:
- Source image dimensions and aspect ratios preserved.
- Mean squared difference and Laplacian edge variance confirmed distinct visual edits.
- Successfully cataloged with linked lineage in `data/artifacts/catalog.json`.
