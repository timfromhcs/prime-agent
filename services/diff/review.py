"""Safe git diff/review helpers: changed files, unified diff, revert file/hunk."""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List


def _git(cwd: str, *args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def git_status(cwd: str) -> Dict[str, Any]:
    r = _git(cwd, "status", "--short", "--branch")
    branch = ""
    files: List[Dict[str, str]] = []
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            if line.startswith("##"):
                branch = line[2:].strip()
                continue
            if len(line) >= 4:
                files.append({"xy": line[:2], "path": line[3:].strip()})
    return {"branch": branch, "files": files, "raw": r.stdout, "ok": r.returncode == 0}


def changed_files(cwd: str) -> List[Dict[str, str]]:
    r = _git(cwd, "diff", "--name-status", "HEAD")
    out: List[Dict[str, str]] = []
    if r.returncode != 0:
        # untracked fallback
        s = git_status(cwd)
        for f in s["files"]:
            out.append({"status": f["xy"].strip() or "?", "path": f["path"]})
        return out
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            out.append({"status": parts[0], "path": parts[-1]})
    # add untracked
    u = _git(cwd, "ls-files", "--others", "--exclude-standard")
    if u.returncode == 0:
        seen = {o["path"] for o in out}
        for line in u.stdout.splitlines():
            if line.strip() and line.strip() not in seen:
                out.append({"status": "??", "path": line.strip()})
    return out


def file_diff(cwd: str, path: str, staged: bool = False) -> Dict[str, Any]:
    args = ["diff", "--no-color", "-U3"]
    if staged:
        args.append("--staged")
    args += ["--", path]
    r = _git(cwd, *args)
    return {"path": path, "diff": r.stdout, "ok": r.returncode == 0}


def full_diff(cwd: str, max_chars: int = 60000) -> str:
    r = _git(cwd, "diff", "--no-color", "HEAD")
    out = r.stdout or ""
    if len(out) > max_chars:
        out = out[:max_chars] + "\n... [truncated]"
    return out


def revert_file(cwd: str, path: str) -> Dict[str, Any]:
    # safe: only tracked modifications; never delete untracked implicitly
    u = _git(cwd, "ls-files", "--others", "--exclude-standard")
    if u.returncode == 0 and path in u.stdout.split():
        return {"ok": False, "reason": "untracked file: delete manually to avoid data loss"}
    r = _git(cwd, "checkout", "--", path)
    return {"ok": r.returncode == 0, "stderr": r.stderr}
