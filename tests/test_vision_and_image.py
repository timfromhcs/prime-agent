"""Test Suite for Image Artifact Store, Visual QA, and Image Processing."""

import os
import pytest
from PIL import Image, ImageDraw
from services.image.store import ImageArtifactStore
from services.image.qa import VisualQAEngine


def test_image_artifact_cataloging(tmp_path):
    store = ImageArtifactStore(
        artifacts_dir=str(tmp_path / "artifacts"),
        catalog_path=str(tmp_path / "catalog.json")
    )

    # Create dummy image
    raw_img = tmp_path / "raw.png"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(str(raw_img))

    artifact = store.register_artifact(
        image_path=str(raw_img),
        prompt="A vibrant blue square",
        producer_agent="TestAgent"
    )

    assert artifact.artifact_id.startswith("img_")
    assert len(artifact.sha256) == 64
    assert artifact.format == "PNG"

    retrieved = store.get_artifact(artifact.artifact_id)
    assert retrieved is not None
    assert retrieved.prompt == "A vibrant blue square"


@pytest.mark.asyncio
async def test_visual_qa_structural_metrics(tmp_path):
    qa = VisualQAEngine()

    # Create test image with distinct contrast
    img_path = str(tmp_path / "test_qa.png")
    img = Image.new("RGB", (256, 256), color="white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 200, 200], fill="red")
    img.save(img_path)

    res = await qa.verify_image(img_path, prompt="A red box on a white background")
    assert res.status == "PASS"
    assert res.metrics["width"] == 256
    assert res.metrics["height"] == 256
    assert res.metrics["std_dev_contrast"] > 10.0
