"""Task-Aware Model Router for Prime Agent.

Intelligently routes agent tasks to the optimal local model:
- General Reasoning: Primary Qwen3-4B with draft speculation
- Code Generation / Diagnosis: Primary Coder
- Vision / OCR / Visual QA: Qwen2-VL-2B with multimodal projector
- Fast Helper / Summarizer: Qwen2.5-0.5B draft model
- Uncensored / Alternative: Qwen2.5-Coder-0.5B abliterated
"""

from __future__ import annotations
from typing import Any, Dict, Optional
from services.llm.model_manager import ModelManager


class ModelRouter:
    """Routes incoming tasks to suitable models based on task type and resource pressure."""

    def __init__(self, model_manager: ModelManager):
        self.manager = model_manager

    def resolve_role(self, task_type: str, hint: Optional[str] = None) -> str:
        t = task_type.lower()
        if "vision" in t or "ocr" in t or "image_inspect" in t:
            return "vision"
        if "fast" in t or "draft" in t or "quick" in t:
            return "draft"
        if "abliterated" in t or "uncensored" in t:
            return "abliterated"
        if "code" in t or "coding" in t:
            return "primary"
        return "primary"

    async def get_server_port_for_task(self, task_type: str, hint: Optional[str] = None) -> int:
        role = self.resolve_role(task_type, hint)
        return await self.manager.ensure_server(role=role)
