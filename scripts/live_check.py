"""Live LLM smoke check: server -> inference -> streaming -> bounded BUILD task.

Usage: python scripts/live_check.py [--max-steps 2]
Proves the full local loop is real: LLM -> persistent REPL -> tool result -> answer.
Exits 0 only if the agent's final answer contains RESULT:157 ((12*13)+1).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from services.agent.root_agent import PrimeAgent
from services.llm.client import LLMClient
from services.llm.model_manager import ModelManager


async def main(max_steps: int) -> int:
    mgr = ModelManager()
    print("[1/4] starting primary server (tuned: vulkan, q8_0 KV, FA on, spec draft)...", flush=True)
    t0 = time.time()
    port = await mgr.ensure_server("primary", port=8080)
    print(f"      up on {port} after {time.time() - t0:.1f}s [{mgr.active_profile}]", flush=True)

    print("[2/4] plain inference...", flush=True)
    client = LLMClient()
    r = await client.chat(
        [{"role": "user", "content": "Reply with exactly: LLAMA_OK"}],
        port=port, max_tokens=32)
    print(f"      response={r.content.strip()[:80]!r} "
          f"prefill={r.usage.prompt_tok_per_sec:.1f}tok/s decode={r.usage.decode_tok_per_sec:.1f}tok/s", flush=True)
    if "LLAMA_OK" not in r.content:
        print("      FAIL: unexpected inference response")
        mgr.shutdown()
        return 1

    print("[3/4] streaming inference...", flush=True)
    deltas = 0
    async for ev in client.chat_stream(
            [{"role": "user", "content": "Count: 1 2 3"}], port=port, max_tokens=32):
        if "delta" in ev and ev["delta"]:
            deltas += 1
    print(f"      streamed deltas: {deltas}", flush=True)
    if deltas == 0:
        print("      FAIL: no streamed deltas")
        mgr.shutdown()
        return 1

    print(f"[4/4] bounded BUILD task (max_steps={max_steps})...", flush=True)
    agent = PrimeAgent()
    try:
        turn = await agent.execute_task(
            "Compute (12*13)+1 using exactly one ```python block, "
            "then reply with RESULT:<number> and nothing else.",
            session_id="live_check",
            max_steps=max_steps,
        )
        print(f"      actions={len(turn.actions_taken)} verification={turn.verification}", flush=True)
        print(f"      answer={turn.response.strip()[:200]!r}", flush=True)
        ok = "RESULT:157" in turn.response
        print("      LIVE BUILD TASK:", "PASS" if ok else "FAIL", flush=True)
        return 0 if ok else 1
    finally:
        agent.shutdown()
        mgr.shutdown()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-steps", type=int, default=2)
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.max_steps)))
