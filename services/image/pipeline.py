"""Local Diffusion Image Generation and Editing Pipeline for Prime Agent.

Provides on-demand headless text-to-image and image-to-image editing using the
verified local model in models/image/tiny-sd, with automated Visual QA and artifact management.
"""

from __future__ import annotations
import gc
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
from PIL import Image
import torch
from diffusers import AutoPipelineForImage2Image, AutoPipelineForText2Image

from services.image.qa import VisualQAEngine, VisualQAResult
from services.image.store import ImageArtifact, ImageArtifactStore


class ImageService:
    """Manages on-demand diffusion model execution, editing, and QA."""

    def __init__(
        self,
        model_path: str = "models/image/tiny-sd",
        store: Optional[ImageArtifactStore] = None,
        qa_engine: Optional[VisualQAEngine] = None
    ):
        self.model_path = model_path
        self.store = store or ImageArtifactStore()
        self.qa = qa_engine or VisualQAEngine()
        self._t2i_pipe = None
        self._i2i_pipe = None

    def _ensure_t2i_pipe(self):
        if self._t2i_pipe is None:
            self._t2i_pipe = AutoPipelineForText2Image.from_pretrained(
                self.model_path,
                torch_dtype=torch.float32
            )
            self._t2i_pipe.to("cpu")

    def _ensure_i2i_pipe(self):
        self._ensure_t2i_pipe()
        if self._i2i_pipe is None:
            self._i2i_pipe = AutoPipelineForImage2Image.from_pipe(self._t2i_pipe)

    def unload(self):
        """Unloads diffusion weights to free memory."""
        self._t2i_pipe = None
        self._i2i_pipe = None
        gc.collect()

    async def generate_image(
        self,
        prompt: str,
        steps: int = 10,
        guidance_scale: float = 7.5,
        width: int = 256,
        height: int = 256,
        seed: Optional[int] = None,
        task_id: str = "task_gen",
        producer_agent: str = "ImageAgent",
        vlm_port: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generates a new image artifact from text."""
        start_t = time.time()
        self._ensure_t2i_pipe()

        generator = None
        if seed is not None:
            generator = torch.Generator("cpu").manual_seed(seed)

        img = self._t2i_pipe(
            prompt=prompt,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            width=width,
            height=height,
            generator=generator
        ).images[0]

        temp_path = f"data/artifacts/temp_gen_{int(time.time()*1000)}.png"
        img.save(temp_path)

        # Register artifact
        artifact = self.store.register_artifact(
            image_path=temp_path,
            prompt=prompt,
            producer_agent=producer_agent,
            task_id=task_id,
            model="tiny-sd",
            metadata={"steps": steps, "guidance_scale": guidance_scale, "width": width, "height": height}
        )
        if os.path.exists(temp_path):
            os.remove(temp_path)

        # Run Visual QA
        qa_res = await self.qa.verify_image(artifact.file_path, prompt, vlm_port=vlm_port)
        self.store.update_qa(artifact.artifact_id, qa_res.status, qa_res.feedback)

        duration = time.time() - start_t
        return {
            "status": "ok",
            "artifact_id": artifact.artifact_id,
            "file_path": artifact.file_path,
            "sha256": artifact.sha256,
            "qa": {
                "status": qa_res.status,
                "score": qa_res.score,
                "feedback": qa_res.feedback
            },
            "duration_seconds": round(duration, 2)
        }

    async def edit_image(
        self,
        prompt: str,
        image_path: str,
        strength: float = 0.6,
        steps: int = 10,
        guidance_scale: float = 7.5,
        task_id: str = "task_edit",
        producer_agent: str = "ImageAgent",
        vlm_port: Optional[int] = None
    ) -> Dict[str, Any]:
        """Edits an existing image artifact using image-to-image diffusion."""
        start_t = time.time()
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Input image not found: {image_path}")

        init_img = Image.open(image_path).convert("RGB")
        self._ensure_i2i_pipe()

        edited_img = self._i2i_pipe(
            prompt=prompt,
            image=init_img,
            strength=strength,
            num_inference_steps=steps,
            guidance_scale=guidance_scale
        ).images[0]

        temp_path = f"data/artifacts/temp_edit_{int(time.time()*1000)}.png"
        edited_img.save(temp_path)

        artifact = self.store.register_artifact(
            image_path=temp_path,
            prompt=prompt,
            producer_agent=producer_agent,
            task_id=task_id,
            model="tiny-sd-img2img",
            metadata={"parent_image": image_path, "strength": strength, "steps": steps}
        )
        if os.path.exists(temp_path):
            os.remove(temp_path)

        qa_res = await self.qa.verify_image(artifact.file_path, prompt, vlm_port=vlm_port)
        self.store.update_qa(artifact.artifact_id, qa_res.status, qa_res.feedback)

        duration = time.time() - start_t
        return {
            "status": "ok",
            "artifact_id": artifact.artifact_id,
            "file_path": artifact.file_path,
            "sha256": artifact.sha256,
            "qa": {
                "status": qa_res.status,
                "score": qa_res.score,
                "feedback": qa_res.feedback
            },
            "duration_seconds": round(duration, 2)
        }
