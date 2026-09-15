"""Application home resolution for hcscoder.

Internal resources (config/, runtime/, models/, data/, logs/, state/) anchor to
the INSTALLATION directory, never to the caller's working directory.

Priority:
  1. $PRIME_HOME (set by the installer), if it contains config/models.json
  2. Directory of the cli entry point (repo/dev checkout), if valid
  3. Current working directory (fallback; doctor reports missing resources)

User-supplied paths (--cwd, ingest paths, @file refs) are resolved against the
ORIGINAL working directory before the process anchors to the app home.
"""

from __future__ import annotations

import os
from pathlib import Path

MARKER = Path("config/models.json")


def find_app_home(cli_file: str = "", orig_cwd: str = "") -> Path:
    env = os.environ.get("PRIME_HOME", "").strip().strip('"').strip("'")
    if env and (Path(env) / MARKER).exists():
        return Path(env).resolve()
    if cli_file:
        d = Path(cli_file).resolve().parent
        if (d / MARKER).exists():
            return d
    return Path(orig_cwd or os.getcwd()).resolve()


def resolve_user_path(p: str, orig_cwd: str) -> str:
    """Resolve a user-given path against the invocation directory."""
    q = Path(p)
    if q.is_absolute():
        return str(q)
    return str((Path(orig_cwd) / q).resolve())
