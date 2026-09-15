"""Async LLM Client for local inference.

Communicates with local llama-server instances providing structured chat completions,
multimodal vision queries, and token performance metrics.
"""

from __future__ import annotations
import base64
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import httpx


@dataclass
class CompletionUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_tok_per_sec: float = 0.0
    decode_tok_per_sec: float = 0.0


@dataclass
class LLMResponse:
    content: str
    role: str = "assistant"
    usage: CompletionUsage = field(default_factory=CompletionUsage)
    raw: Dict[str, Any] = field(default_factory=dict)


class LLMClient:
    """Async client for local OpenAI-compatible inference servers."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080/v1"):
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        port: Optional[int] = None
    ) -> LLMResponse:
        url = f"http://127.0.0.1:{port}/v1/chat/completions" if port else f"{self.base_url}/chat/completions"
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content") or msg.get("reasoning_content") or ""

        usage_data = data.get("usage", {})
        timings = data.get("timings", {})

        usage = CompletionUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            prompt_tok_per_sec=timings.get("prompt_per_second", 0.0),
            decode_tok_per_sec=timings.get("predicted_per_second", 0.0)
        )

        return LLMResponse(
            content=content,
            role=msg.get("role", "assistant"),
            usage=usage,
            raw=data
        )

    async def chat_with_image(
        self,
        prompt: str,
        image_bytes: bytes,
        port: int = 8085,
        max_tokens: int = 256
    ) -> LLMResponse:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]
            }
        ]
        return await self.chat(messages, port=port, max_tokens=max_tokens)

    async def close(self):
        pass
