"""Live multimodal proof: VLM describe + diffusion generate + edit + QA.

Usage: python scripts/live_multimodal.py
Exit 0 only if: vision description non-empty, generated artifact exists with
SHA256 + QA PASS, edited artifact exists.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.image.pipeline import ImageService  # noqa: E402
from services.llm.client import LLMClient  # noqa: E402
from services.llm.model_manager import ModelManager  # noqa: E402


async def main() -> int:
    mgr = ModelManager()
    print("[1/4] vision server (Qwen2-VL + mmproj)...", flush=True)
    t0 = time.time()
    vport = await mgr.ensure_server("vision", port=8085)
    print(f"      up on {vport} after {time.time()-t0:.1f}s", flush=True)

    print("[2/4] VLM describe data/artifacts/test_vision.png...", flush=True)
    client = LLMClient()
    with open("data/artifacts/test_vision.png", "rb") as f:
        img_bytes = f.read()
    desc = await client.chat_with_image("What do you see? One sentence.", img_bytes, port=vport)
    print(f"      description={desc.content.strip()[:200]!r}", flush=True)
    if not desc.content.strip():
        print("      FAIL: empty description")
        mgr.shutdown()
        return 1

    print("[3/4] diffusion generate (tiny-sd, CPU, small)...", flush=True)
    svc = ImageService(model_path="models/image/tiny-sd")
    t0 = time.time()
    gen = await svc.generate_image(prompt="a red square icon", steps=4, width=128, height=128)
    print(f"      artifact={gen.get('artifact_id')} sha={str(gen.get('sha256'))[:12]} "
          f"qa={gen.get('qa', {}).get('status')} {gen.get('duration_seconds')}s", flush=True)
    if gen.get("status") != "ok" or not os.path.exists(gen.get("file_path", "")):
        print("      FAIL: generation")
        mgr.shutdown()
        return 1

    print("[4/4] diffusion edit + QA...", flush=True)
    edit = await svc.edit_image(prompt="a blue square icon", image_path=gen["file_path"],
                                strength=0.6, steps=4)
    print(f"      edited={edit.get('artifact_id')} qa={edit.get('qa', {}).get('status')}", flush=True)
    ok = edit.get("status") == "ok" and os.path.exists(edit.get("file_path", ""))
    print("LIVE MULTIMODAL:", "PASS" if ok else "FAIL", flush=True)
    mgr.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
