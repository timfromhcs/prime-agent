"""Terminal session manager: real subprocess shells with observable output.

Each terminal session runs PowerShell (pwsh/powershell) or cmd fallback,
keeps a bounded log with command/stdout/stderr/exit/duration metadata,
and persists metadata to data/terminals/.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _detect_shell() -> List[str]:
    for exe in ("pwsh.exe", "powershell.exe"):
        if shutil.which(exe):
            return [exe, "-NoProfile", "-Command"]
    return ["cmd", "/c"]


@dataclass
class TerminalRecord:
    term_id: str
    name: str
    shell: str
    cwd: str
    created_at: float
    log: List[Dict[str, Any]] = field(default_factory=list)


class TerminalManager:
    def __init__(self, store_dir: str = "data/terminals"):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.shell_prefix = _detect_shell()
        self.terminals: Dict[str, TerminalRecord] = {}
        self._load()

    def _path(self, term_id: str) -> Path:
        return self.store_dir / f"{term_id}.json"

    def _load(self) -> None:
        for p in self.store_dir.glob("term_*.json"):
            try:
                self.terminals[p.stem] = TerminalRecord(**json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue

    def _save(self, rec: TerminalRecord) -> None:
        tmp = self._path(rec.term_id).with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(rec), indent=2), encoding="utf-8")
        tmp.replace(self._path(rec.term_id))

    def create(self, name: str = "Terminal 1", cwd: str = ".") -> TerminalRecord:
        tid = f"term_{uuid4().hex[:6]}"
        rec = TerminalRecord(term_id=tid, name=name, shell=" ".join(self.shell_prefix),
                             cwd=str(Path(cwd).resolve()), created_at=time.time())
        self.terminals[tid] = rec
        self._save(rec)
        return rec

    def list(self) -> List[TerminalRecord]:
        return list(self.terminals.values())

    def rename(self, term_id: str, name: str) -> bool:
        rec = self.terminals.get(term_id)
        if not rec:
            return False
        rec.name = name
        self._save(rec)
        return True

    def close(self, term_id: str) -> bool:
        if term_id in self.terminals:
            del self.terminals[term_id]
            try:
                self._path(term_id).unlink(missing_ok=True)
            except Exception:
                pass
            return True
        return False

    def run(self, term_id: str, command: str, timeout: int = 120) -> Dict[str, Any]:
        rec = self.terminals.get(term_id)
        if not rec:
            return {"ok": False, "reason": "unknown terminal"}
        t0 = time.time()
        try:
            r = subprocess.run(self.shell_prefix + [command], cwd=rec.cwd,
                               capture_output=True, text=True, timeout=timeout)
            entry = {"command": command, "stdout": r.stdout[-8000:],
                     "stderr": r.stderr[-8000:], "exit_code": r.returncode,
                     "duration_s": round(time.time() - t0, 2)}
        except subprocess.TimeoutExpired as e:
            entry = {"command": command, "stdout": (e.stdout or "")[-8000:] if isinstance(e.stdout, str) else "",
                     "stderr": f"timeout after {timeout}s", "exit_code": 124,
                     "duration_s": round(time.time() - t0, 2)}
        rec.log.append(entry)
        if len(rec.log) > 200:
            rec.log = rec.log[-200:]
        self._save(rec)
        return {"ok": True, **entry}
