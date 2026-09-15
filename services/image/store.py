"""Image Artifact Store for Prime Agent.

Tracks all generated and edited images with unique artifact IDs, SHA-256 hashes,
generation parameters, producer metadata, and visual QA verification reports.
"""

from __future__ import annotations
import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class ImageArtifact:
    artifact_id: str
    file_path: str
    file_name: str
    format: str
    size_bytes: int
    sha256: str
    created_at: str
    model: str
    prompt: str
    producer_agent: str
    task_id: str
    qa_status: str = "PENDING"
    qa_notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ImageArtifactStore:
    """Manages storage, metadata, and provenance of visual artifacts."""

    def __init__(self, artifacts_dir: str = "data/artifacts", catalog_path: str = "data/artifacts/catalog.json"):
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_path = Path(catalog_path)
        self.artifacts: Dict[str, ImageArtifact] = {}
        self._load()

    def _load(self):
        if self.catalog_path.exists():
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.artifacts = {k: ImageArtifact(**v) for k, v in data.items()}
            except Exception as e:
                print(f"[ImageStore] Warning loading catalog: {e}")

    def save(self):
        data = {k: asdict(v) for k, v in self.artifacts.items()}
        temp_file = self.catalog_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(self.catalog_path)

    @staticmethod
    def compute_sha256(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def register_artifact(
        self,
        image_path: str,
        prompt: str,
        producer_agent: str = "ImageAgent",
        task_id: str = "default",
        model: str = "tiny-sd",
        metadata: Optional[Dict[str, Any]] = None
    ) -> ImageArtifact:
        p = Path(image_path)
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        artifact_id = f"img_{uuid4().hex[:8]}"
        target_path = self.artifacts_dir / f"{artifact_id}{p.suffix}"
        shutil.copy2(p, target_path)

        size = target_path.stat().st_size
        sha = self.compute_sha256(str(target_path))
        ts = datetime.now(timezone.utc).isoformat()

        artifact = ImageArtifact(
            artifact_id=artifact_id,
            file_path=str(target_path.resolve()),
            file_name=target_path.name,
            format=p.suffix.lstrip(".").upper(),
            size_bytes=size,
            sha256=sha,
            created_at=ts,
            model=model,
            prompt=prompt,
            producer_agent=producer_agent,
            task_id=task_id,
            metadata=metadata or {}
        )

        self.artifacts[artifact_id] = artifact
        self.save()
        return artifact

    def update_qa(self, artifact_id: str, status: str, notes: str):
        if artifact_id in self.artifacts:
            self.artifacts[artifact_id].qa_status = status
            self.artifacts[artifact_id].qa_notes = notes
            self.save()

    def get_artifact(self, artifact_id: str) -> Optional[ImageArtifact]:
        return self.artifacts.get(artifact_id)

    def list_artifacts(self) -> List[ImageArtifact]:
        return list(self.artifacts.values())
