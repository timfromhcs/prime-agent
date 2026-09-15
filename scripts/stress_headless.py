"""Headless stress: sessions, parallel PLAN runs, RAG latency, terminals, API.

Usage: python scripts/stress_headless.py [--rounds 10]
All local, no LLM server needed (PLAN mode). Exits nonzero on any failure.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.runtime.core import PrimeRuntime  # noqa: E402

FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'ok' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        FAILURES.append(name)


async def main(rounds: int) -> int:
    rt = PrimeRuntime()
    t0 = time.time()
    try:
        # 1. session lifecycle loop
        print("[1/5] session lifecycle x%d..." % rounds)
        ids = []
        for i in range(rounds):
            s = rt.sessions.create(title=f"stress-{i}", cwd=".", goal="stress", mode="PLAN")
            rt.sessions.append_message(s.session_id, "user", f"ping {i}")
            rt.sessions.log_tool(s.session_id, "stress", "completed", "x")
            rt.sessions.compact(s.session_id)
            ids.append(s.session_id)
        check("sessions created", len(ids) == rounds, f"{len(ids)}/{rounds}")
        check("export works", bool(rt.sessions.export(ids[0])))

        # 2. parallel PLAN runs (shared runtime, must not corrupt state)
        print("[2/5] %d parallel PLAN runs..." % rounds)
        async def one(i: int):
            return await rt.run_task(ids[i % len(ids)], f"stress query {i}")
        res = await asyncio.gather(*[one(i) for i in range(rounds)])
        check("all parallel ok", all(r.get("ok") for r in res),
              f"{sum(1 for r in res if r.get('ok'))}/{rounds}")
        check("modes all PLAN", all(r.get("mode") == "PLAN" for r in res if r.get("ok")))

        # 3. RAG latency distribution
        print("[3/5] RAG latency x20...")
        lat = []
        for i in range(20):
            a = time.time()
            pack = rt.rag.search(f"agent architecture test {i}", top_k=3)
            lat.append((time.time() - a) * 1000)
            if not pack.items:
                check("rag hits", False, "empty result")
                break
        else:
            check("rag hits", True, f"p50={statistics.median(lat):.1f}ms p95={sorted(lat)[int(len(lat)*0.95)]:.1f}ms")

        # 4. terminal storm
        print("[4/5] terminal x10...")
        term = rt.terminals.create(name="stress", cwd=".")
        outs = [rt.terminals.run(term.term_id, f"echo s{i}") for i in range(10)]
        check("terminals ok", all(o.get("exit_code") == 0 for o in outs))
        rt.terminals.close(term.term_id)
        check("terminal closed", term.term_id not in rt.terminals.terminals)

        # 5. event stream integrity
        print("[5/5] event log...")
        ev = rt.events_since(0)
        types = {e["type"] for e in ev["events"]}
        check("events flowing", ev["cursor"] > rounds, f"cursor={ev['cursor']}")
        check("has completions", "message.completed" in types, sorted(types)[:5])

        print(f"\nSTRESS: {rounds} rounds in {time.time()-t0:.1f}s, failures={len(FAILURES)}")
        return 1 if FAILURES else 0
    finally:
        rt.shutdown()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=10)
    sys.exit(asyncio.run(main(ap.parse_args().rounds)))
