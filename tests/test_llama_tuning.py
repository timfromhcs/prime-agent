"""llama.cpp hardware-tuning tests: arg builder + profile override (no GPU needed)."""

from services.llm.model_manager import ModelManager


def test_build_args_has_tuning_flags():
    m = ModelManager()
    args, draft = m._build_args(
        role="primary", port=8080,
        bin_path="runtime/llama.cpp/vulkan/llama-server.exe",
        model_path="models/primary/Qwen3-4B-Q4_K_M.gguf",
        backend="vulkan",
    )
    joined = " ".join(args)
    for flag in ["-fa on", "-ctk q8_0", "-ctv q8_0", "-md", "--spec-draft-n-max 8",
                 "--spec-draft-n-min 2", "-ngl 99", "-ngld 99",
                 "-ctkd q8_0", "-ctvd q8_0"]:
        assert flag in joined, f"missing: {flag}"
    assert draft and draft.endswith(".gguf")


def test_build_args_no_spec_when_disabled():
    m = ModelManager()
    m.server_cfg["speculative_enabled"] = False
    args, draft = m._build_args(
        role="primary", port=8080, bin_path="x", model_path="y", backend="vulkan")
    assert "-md" not in args and draft is None


def test_optimal_profile_overrides_server_cfg(tmp_path):
    import json
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "models.json").write_text("{}", encoding="utf-8")
    (cfg / "server.json").write_text('{"cache_type_k": "f16"}', encoding="utf-8")
    (cfg / "hardware.json").write_text("{}", encoding="utf-8")
    (cfg / "optimal-profile.json").write_text(
        json.dumps({"profile": "T", "cache_type_k": "q4_0"}), encoding="utf-8")
    m = ModelManager(config_dir=str(cfg))
    assert m.server_cfg["cache_type_k"] == "q4_0"
    assert "optimal-profile" in m.active_profile
