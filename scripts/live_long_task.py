"""Long-horizon BUILD proof: scaffold -> test -> repair-until-green, all by the agent.

Usage: python scripts/live_long_task.py [--workdir DIR] (default: ./tmp_longhorn_task)
The agent gets max_steps=6 RLM turns. Afterwards THIS script independently runs
pytest on the agent's test file. Exit 0 only if pytest is green.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm.model_manager import ModelManager  # noqa: E402
from services.runtime.core import PrimeRuntime  # noqa: E402

PHASES = [
    ("write calculator.py with add/sub/mul/div (div raises ValueError on zero). "
     "Reply with ONLY one ```python block and no prose. Inside, use plain Python: "
     "Path(\"{workdir}/calculator.py\").write_text(...). "
     "End with WROTE:calculator.",
     "calculator.py"),
    ("write test_calc.py in {workdir} with at least 6 assert statements testing "
     "add/sub/mul/div including div-by-zero raising ValueError. "
     "Reply with ONLY one ```python block and no prose. Inside, use "
     "Path(...).write_text(...). Import calculator and pytest at the top. "
     "End with WROTE:test_calc.",
     "test_calc.py"),
    ("run pytest on {workdir}/test_calc.py from {workdir}. "
     "Reply with ONLY ```python blocks and no prose. "
     "(await bash(\"cd {workdir} && python -m pytest test_calc.py -q\")). "
     "If failures occur, fix the files and rerun until green. "
     "End with DONE:PASS only when pytest is green.",
     None),
]


async def main(workdir: str, only_phase: int = 0) -> int:
    workdir = os.path.abspath(workdir)
    os.makedirs(workdir, exist_ok=True)
    mgr = ModelManager()
    print("[1/3] server...", flush=True)
    await mgr.ensure_server("primary", port=8080)
    rt = PrimeRuntime()
    try:
        print("[2/3] agent building in phases (BUILD mode, bounded)...", flush=True)
        phases = [(i, tmpl, exp) for i, (tmpl, exp) in enumerate(PHASES, 1)
                  if only_phase == 0 or i == only_phase]
        for i, tmpl, expect_file in phases:
            task = tmpl.format(workdir=workdir)
            sess = rt.sessions.create(title=f"longhorn-p{i}", cwd=workdir, goal=task, mode="BUILD")
            res = await rt.run_task(sess.session_id, task)
            print(f"      phase {i}: ok={res.get('ok')} verification={res.get('verification')}", flush=True)
            if expect_file and not os.path.exists(os.path.join(workdir, expect_file)):
                print(f"      phase {i} FAIL: {expect_file} missing")
                return 1
        if only_phase != 0:
            print("      (single phase done)")
            return 0
        print("[3/3] independent pytest rerun...", flush=True)
        r = subprocess.run([sys.executable, "-m", "pytest", "test_calc.py", "-q"],
                           capture_output=True, text=True, timeout=180,
                           cwd=workdir)
        print("      " + (r.stdout.strip().splitlines() or [""])[-1], flush=True)
        ok = r.returncode == 0
        print("LONG-HORIZON BUILD:", "PASS" if ok else "FAIL", flush=True)
        return 0 if ok else 1
    finally:
        rt.shutdown()
        mgr.shutdown()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="./tmp_longhorn_task")
    ap.add_argument("--only-phase", type=int, default=0,
                    help="run only phase N (1-3); artifacts persist, so phases resume")
    ap.add_argument("--verify", action="store_true",
                    help="only run the independent pytest rerun (step 3/3)")
    a = ap.parse_args()
    if a.verify:
        r = subprocess.run([sys.executable, "-m", "pytest", "test_calc.py", "-q"],
                           capture_output=True, text=True, timeout=180,
                           cwd=os.path.abspath(a.workdir))
        print("      " + (r.stdout.strip().splitlines() or [""])[-1])
        print("LONG-HORIZON BUILD:", "PASS" if r.returncode == 0 else "FAIL")
        sys.exit(0 if r.returncode == 0 else 1)
    sys.exit(asyncio.run(main(a.workdir, a.only_phase)))
