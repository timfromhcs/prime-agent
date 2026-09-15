"""Model Lifecycle Manager for Local GGUF and VLM inference.

Controls local llama-server instances with memory awareness, speculative decoding,
multimodal projectors, and clean process lifecycle management.
"""

from __future__ import annotations
import asyncio
import json
import os
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import psutil

from services.rlm.winjob import WindowsJobGroup


@dataclass
class ServerInstance:
    role: str
    model_path: str
    port: int
    proc: subprocess.Popen
    backend: str
    projector_path: Optional[str] = None
    draft_path: Optional[str] = None
    started_at: float = 0.0


class ModelManager:
    """Manages discovery, loading, unloading, and routing of inference engines."""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.models_cfg: Dict[str, Any] = {}
        self.server_cfg: Dict[str, Any] = {}
        self.hw_cfg: Dict[str, Any] = {}
        self.active_servers: Dict[str, ServerInstance] = {}
        self.job_group = WindowsJobGroup("PrimeModelManagerJob")
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._load_configs()

    def _load_configs(self):
        models_file = self.config_dir / "models.json"
        if models_file.exists():
            with open(models_file, "r", encoding="utf-8") as f:
                self.models_cfg = json.load(f)

        server_file = self.config_dir / "server.json"
        if server_file.exists():
            with open(server_file, "r", encoding="utf-8") as f:
                self.server_cfg = json.load(f)

        hw_file = self.config_dir / "hardware.json"
        if hw_file.exists():
            with open(hw_file, "r", encoding="utf-8") as f:
                self.hw_cfg = json.load(f)

        # Optimal profile (written by `hcscoder optimize`) overrides server.json.
        prof_file = self.config_dir / "optimal-profile.json"
        self.active_profile = "server.json (default tuned profile)"
        if prof_file.exists():
            try:
                with open(prof_file, "r", encoding="utf-8") as f:
                    prof = json.load(f)
                for k in ("backend", "threads", "threads_draft", "context_size",
                          "gpu_layers", "gpu_layers_draft", "flash_attn",
                          "cache_type_k", "cache_type_v",
                          "cache_type_k_draft", "cache_type_v_draft",
                          "ubatch_size", "speculative_enabled",
                          "spec_draft_n_max", "spec_draft_n_min"):
                    if k in prof:
                        self.server_cfg[k] = prof[k]
                self.active_profile = f"optimal-profile.json ({prof.get('profile', '?')})"
            except Exception as e:
                print(f"[ModelManager] ignoring broken optimal-profile.json: {e}")

    def get_binary_path(self, backend: Optional[str] = None) -> str:
        b = backend or self.server_cfg.get("backend", "vulkan")
        vulkan_bin = Path("runtime/llama.cpp/vulkan/llama-server.exe")
        cpu_bin = Path("runtime/llama.cpp/cpu/llama-server.exe")
        if b == "vulkan" and vulkan_bin.exists():
            return str(vulkan_bin.resolve())
        return str(cpu_bin.resolve())

    async def ensure_server(self, role: str = "primary", port: Optional[int] = None, speculative: Optional[bool] = None) -> int:
        """Ensures a model server for the given role is active and healthy."""
        if role in self.active_servers:
            inst = self.active_servers[role]
            if inst.proc.poll() is None and self.check_health(inst.port):
                return inst.port
            else:
                self.stop_server(role)

        target_port = port or self.server_cfg.get("port", 8080)
        if role == "vision":
            target_port = 8085
        elif role == "draft" or role == "abliterated":
            target_port = 8087

        # Evict other heavyweight server if memory is tight
        avail_mb = psutil.virtual_memory().available // (1024 * 1024)
        if avail_mb < 3000 and self.active_servers:
            roles_to_stop = [r for r in self.active_servers if r != role]
            for r in roles_to_stop:
                self.stop_server(r)

        return await self.start_server(role=role, port=target_port, speculative=speculative)

    def free_port(self, port: int):
        try:
            for c in psutil.net_connections(kind="inet"):
                if c.laddr and c.laddr.port == port and c.pid:
                    try:
                        p = psutil.Process(c.pid)
                        p.terminate()
                        p.wait(timeout=2.0)
                    except Exception:
                        pass
        except Exception:
            pass

    def _build_args(self, role: str, port: int, bin_path: str, model_path: str,
                    backend: str, projector_path=None) -> tuple[list, Optional[str]]:
        """Pure arg builder (unit-tested) — returns (args, draft_path)."""
        ctx_size = self.server_cfg.get("context_size", 4096)
        args = [
            bin_path,
            "-m", model_path,
            "--port", str(port),
            "--host", "127.0.0.1",
            "-c", str(ctx_size),
            "-t", str(self.server_cfg.get("threads", 8)),
            "-ub", str(self.server_cfg.get("ubatch_size", 512)),
            "-fa", str(self.server_cfg.get("flash_attn", "auto")),
            "-ctk", str(self.server_cfg.get("cache_type_k", "f16")),
            "-ctv", str(self.server_cfg.get("cache_type_v", "f16")),
            "--no-warmup",
            "-np", "1",
            "--reasoning-budget", "0"
        ]

        if backend == "vulkan":
            args.extend(["-ngl", str(self.server_cfg.get("gpu_layers", 99))])

        if projector_path and os.path.exists(projector_path):
            args.extend(["--mmproj", projector_path])

        draft_path = None
        use_spec = self.server_cfg.get("speculative_enabled", False)
        if role == "primary" and use_spec:
            draft_cfg = self.models_cfg.get("draft")
            if draft_cfg and os.path.exists(draft_cfg["path"]):
                draft_path = draft_cfg["path"]
                args.extend([
                    "-md", draft_path,
                    "--spec-draft-n-max", str(self.server_cfg.get("spec_draft_n_max", 8)),
                    "--spec-draft-n-min", str(self.server_cfg.get("spec_draft_n_min", 2)),
                    "-td", str(self.server_cfg.get("threads_draft", 4)),
                    "-ctkd", str(self.server_cfg.get("cache_type_k_draft", "q8_0")),
                    "-ctvd", str(self.server_cfg.get("cache_type_v_draft", "q8_0")),
                ])
                if backend == "vulkan":
                    args.extend(["-ngld", str(self.server_cfg.get("gpu_layers_draft", 99))])
        return args, draft_path

    async def start_server(self, role: str = "primary", port: int = 8080, speculative: Optional[bool] = None) -> int:
        self.free_port(port)
        model_info = self.models_cfg.get(role)
        if not model_info:
            raise ValueError(
                f"Unknown model role: {role}. No model catalog loaded — "
                f"looked in {Path(self.config_dir).resolve()}. Fix: set $PRIME_HOME "
                f"to your install dir (or reinstall via the one-liner), open a NEW "
                f"terminal, and run `hcscoder doctor`.")

        model_path = model_info["path"]
        backend = self.server_cfg.get("backend", "vulkan")
        bin_path = self.get_binary_path(backend)

        if speculative is not None:
            self.server_cfg["speculative_enabled"] = speculative

        projector_path = model_info.get("projector_path")
        args, draft_path = self._build_args(role, port, bin_path, model_path, backend, projector_path)

        log_file = self.logs_dir / f"llama_server_{role}_{port}.log"
        log_fp = open(log_file, "wb", buffering=0)

        print(f"[ModelManager] profile: {self.active_profile}")
        print(f"[ModelManager] exec: {' '.join(args[1:])}")

        proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=log_fp,
            stderr=subprocess.STDOUT
        )

        if self.job_group:
            self.job_group.assign_process(proc.pid)

        inst = ServerInstance(
            role=role,
            model_path=model_path,
            port=port,
            proc=proc,
            backend=backend,
            projector_path=projector_path,
            draft_path=draft_path,
            started_at=time.time()
        )
        self.active_servers[role] = inst

        # Wait for health (up to 60s for multi-gigabyte models and projectors)
        healthy = False
        for _ in range(120):
            await asyncio.sleep(0.5)
            if proc.poll() is not None:
                raise RuntimeError(f"Server {role} failed to start. See {log_file}")
            if self.check_health(port):
                healthy = True
                break

        if not healthy:
            self.stop_server(role)
            raise TimeoutError(f"Server {role} did not become healthy on port {port}")

        return port

    def check_health(self, port: int) -> bool:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
            with urllib.request.urlopen(req, timeout=1) as resp:
                data = json.loads(resp.read().decode())
                return data.get("status") == "ok"
        except Exception:
            return False

    def stop_server(self, role: str):
        if role in self.active_servers:
            inst = self.active_servers[role]
            try:
                inst.proc.terminate()
                inst.proc.wait(timeout=3)
            except Exception:
                try:
                    inst.proc.kill()
                except Exception:
                    pass
            del self.active_servers[role]

    def shutdown(self):
        for role in list(self.active_servers.keys()):
            self.stop_server(role)
        self.job_group.close()

    def get_status(self) -> Dict[str, Any]:
        mem = psutil.virtual_memory()
        return {
            "active_servers": {
                r: {
                    "port": s.port,
                    "model": s.model_path,
                    "backend": s.backend,
                    "pid": s.proc.pid,
                    "alive": s.proc.poll() is None
                }
                for r, s in self.active_servers.items()
            },
            "available_memory_mb": mem.available // (1024 * 1024),
            "total_memory_mb": mem.total // (1024 * 1024)
        }
