"""Live subagent proof: spawn -> LLM execute -> collect, all real.

Usage: python scripts/live_subagents.py
Exit 0 only if the child completes and its result is collectable.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.agent.root_agent import PrimeAgent  # noqa: E402


async def main() -> int:
    agent = PrimeAgent()
    try:
        print("[1/3] root agent up (server starts on demand)...", flush=True)
        handle = agent.subagents.spawn(
            prompt="Reply with exactly: CHILD_OK",
            name="live-child", role="research")
        print(f"      spawned {handle.subagent_id}", flush=True)
        print("[2/3] executing child via local LLM...", flush=True)
        res = await agent.subagents.execute_subagent(
            handle.subagent_id,
            kernel_manager=agent.kernel_manager,
            llm_client=agent.llm_client,
            router=agent.router)
        print(f"      execute result keys: {sorted(res.keys())}", flush=True)
        print("[3/3] collect...", flush=True)
        got = agent.subagents.collect(handle.subagent_id)
        state = (got or {}).get("state", "?")
        print(f"      state={state}", flush=True)
        ok = got is not None and state in ("COMPLETED", "completed", "DONE", "done", "OK", "ok")
        print("LIVE SUBAGENT:", "PASS" if ok else f"CHECK (state={state})", flush=True)
        return 0 if ok else 1
    finally:
        agent.shutdown()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
