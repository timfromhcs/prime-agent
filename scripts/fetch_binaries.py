"""Fetch large binaries excluded from git: GGUF models, tiny-sd, llama.cpp.

Stdlib-only except --tiny-sd (needs huggingface_hub, installed via pip first).
GGUF downloads are SHA256-verified against config/models.json.
Usage: python scripts/fetch_binaries.py --all [--repo-root .]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PINNED_LLAMA_BUILD = "b10977"
LLAMA_RELEASE_BASE = "https://github.com/ggml-org/llama.cpp/releases/download"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "prime-agent-installer/3.0"})
    with urllib.request.urlopen(req) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        while True:
            chunk = r.read(4 * 1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {dest.name}: {done / 1024 / 1024:.0f}/{total / 1024 / 1024:.0f} MB", end="", flush=True)
    print()
    tmp.replace(dest)


def url_exists(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "prime-agent-installer/3.0"})
        with urllib.request.urlopen(req, timeout=20):
            return True
    except Exception:
        return False


def fetch_models(root: Path) -> bool:
    cfg = json.loads((root / "config" / "models.json").read_text(encoding="utf-8"))
    ok = True
    for role, m in cfg.items():
        repo, path = m.get("repository", ""), m.get("path", "")
        if not repo or not path:
            print(f"[{role}] embedding backend (pip package) — skipping file download")
            continue
        files = [(m["filename"], m.get("sha256", ""))]
        if m.get("projector_path"):
            files.append((Path(m["projector_path"]).name, m.get("projector_sha256", "")))
        for filename, expected in files:
            dest = root / path if filename == m["filename"] else root / m["projector_path"]
            if dest.exists() and expected and sha256_file(dest).lower() == expected.lower():
                print(f"[{role}] {filename} present + hash OK — skipping")
                continue
            url = f"https://huggingface.co/{repo}/resolve/main/{filename}"
            print(f"[{role}] downloading {url}")
            try:
                download(url, dest)
            except Exception as e:
                print(f"[{role}] FAILED: {e}")
                ok = False
                continue
            if expected:
                actual = sha256_file(dest).lower()
                if actual != expected.lower():
                    print(f"[{role}] HASH MISMATCH for {filename}")
                    ok = False
                else:
                    print(f"[{role}] {filename} hash verified")
    return ok


def fetch_tiny_sd(root: Path) -> bool:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[tiny-sd] FAILED: huggingface_hub not installed (run pip install first)")
        return False
    dest = root / "models" / "image" / "tiny-sd"
    if (dest / "model_index.json").exists() and (dest / "unet" / "diffusion_pytorch_model.safetensors").exists():
        print("[tiny-sd] present — skipping")
        return True
    print("[tiny-sd] downloading segmind/tiny-sd (~2 GB) ...")
    try:
        snapshot_download(repo_id="segmind/tiny-sd", local_dir=str(dest))
        print("[tiny-sd] done")
        return True
    except Exception as e:
        print(f"[tiny-sd] FAILED: {e}")
        return False


def _llama_asset_urls() -> list[tuple[str, str]]:
    """(target_subdir, url) candidates for this OS. Pinned build first, latest API fallback."""
    system = platform.system()
    urls: list[tuple[str, str]] = []
    if system == "Windows":
        urls = [
            ("cpu", f"{LLAMA_RELEASE_BASE}/{PINNED_LLAMA_BUILD}/llama-{PINNED_LLAMA_BUILD}-bin-win-cpu-x64.zip"),
            ("vulkan", f"{LLAMA_RELEASE_BASE}/{PINNED_LLAMA_BUILD}/llama-{PINNED_LLAMA_BUILD}-bin-win-vulkan-x64.zip"),
        ]
    elif system == "Linux":
        arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
        urls = [("cpu", f"{LLAMA_RELEASE_BASE}/{PINNED_LLAMA_BUILD}/llama-{PINNED_LLAMA_BUILD}-bin-ubuntu-{arch}.tar.gz")]
    else:
        print(f"llama.cpp: {system} not prebuilt by this script — install llama.cpp manually.")
        return []
    live = [(t, u) for t, u in urls if url_exists(u)]
    if len(live) == len(urls):
        return live
    print("Pinned llama.cpp build not reachable, querying latest release ...")
    try:
        req = urllib.request.Request("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
                                     headers={"User-Agent": "prime-agent-installer/3.0"})
        data = json.load(urllib.request.urlopen(req, timeout=30))
        assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
        want = "win" if system == "Windows" else "ubuntu"
        picked: list[tuple[str, str]] = []
        ext = ".tar.gz" if system == "Linux" else ".zip"
        for target, needle in ((("cpu", "cpu"), ("vulkan", "vulkan")) if system == "Windows" else (("cpu", "cpu"),)):
            for name, url in assets.items():
                if want in name and needle in name and name.endswith(ext) and "cuda" not in name:
                    picked.append((target, url))
                    break
        return picked
    except Exception as e:
        print(f"llama.cpp latest lookup FAILED: {e}")
        return live


def fetch_llamacpp(root: Path) -> bool:
    exe = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
    ok = True
    for target, url in _llama_asset_urls():
        dest_dir = root / "runtime" / "llama.cpp" / target
        if (dest_dir / exe).exists():
            print(f"[llama.cpp/{target}] present — skipping")
            continue
        print(f"[llama.cpp/{target}] downloading {url}")
        try:
            with tempfile.TemporaryDirectory() as td:
                arc = Path(td) / ("llama" + (".tar.gz" if url.endswith(".tar.gz") else ".zip"))
                download(url, arc)
                if arc.suffixes[-2:] == [".tar", ".gz"]:
                    with tarfile.open(arc) as t:
                        t.extractall(td)
                else:
                    with zipfile.ZipFile(arc) as z:
                        z.extractall(td)
                # find dir containing the server binary (layout varies by build)
                cands = [p.parent for p in Path(td).rglob(exe)]
                src = cands[0] if cands else Path(td)
                dest_dir.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    dst = dest_dir / item.name
                    if dst.exists():
                        (shutil.rmtree(dst) if dst.is_dir() else dst.unlink())
                    (shutil.move(str(item), str(dst)))
            print(f"[llama.cpp/{target}] installed -> {dest_dir}")
        except Exception as e:
            print(f"[llama.cpp/{target}] FAILED: {e}")
            ok = False
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--models", action="store_true")
    ap.add_argument("--tiny-sd", action="store_true")
    ap.add_argument("--llamacpp", action="store_true")
    ap.add_argument("--repo-root", default=".")
    a = ap.parse_args()
    root = Path(a.repo_root).resolve()
    results = []
    if a.all or a.models:
        results.append(("models", fetch_models(root)))
    if a.all or a.tiny_sd:
        results.append(("tiny-sd", fetch_tiny_sd(root)))
    if a.all or a.llamacpp:
        results.append(("llamacpp", fetch_llamacpp(root)))
    if not results:
        ap.print_help()
        return 2
    print("\n=== FETCH SUMMARY ===")
    rc = 0
    for name, good in results:
        print(f"  {name}: {'OK' if good else 'FAILED'}")
        rc |= 0 if good else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
