#!/usr/bin/env bash
# Prime Agent V3 one-line installer for Linux (no git clone needed).
#   curl -fsSL https://raw.githubusercontent.com/timfromhcs/prime-agent/main/install.sh | bash
set -euo pipefail

REPO="${REPO:-timfromhcs/prime-agent}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/prime-agent}"
SKIP_MODELS="${SKIP_MODELS:-0}"
SKIP_LLAMACPP="${SKIP_LLAMACPP:-0}"

echo "=== PRIME AGENT V3 INSTALLER (Linux) ==="

# 1. Python 3.12+
if ! command -v python3 >/dev/null; then echo "ERROR: python3 required." >&2; exit 1; fi
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ "$PYVER" < "3.12" ]]; then echo "ERROR: Python 3.12+ required (found $PYVER)." >&2; exit 1; fi
echo "[OK] Python $PYVER"

# 2. Download source (tarball, no git needed)
mkdir -p "$INSTALL_DIR"
TMP_TGZ="$(mktemp /tmp/prime-agent-src.XXXXXX.tgz)"
echo "Downloading source..."
curl -fsSL "https://codeload.github.com/${REPO}/tar.gz/${BRANCH}" -o "$TMP_TGZ"
TMP_DIR="$(mktemp -d /tmp/prime-agent-extract.XXXXXX)"
tar -xzf "$TMP_TGZ" -C "$TMP_DIR"
SRC_DIR="$(find "$TMP_DIR" -maxdepth 1 -mindepth 1 -type d | head -1)"
cp -a "$SRC_DIR"/. "$INSTALL_DIR"/
rm -rf "$TMP_DIR" "$TMP_TGZ"
echo "[OK] Source -> $INSTALL_DIR"

# 3. Virtualenv + dependencies (validates pyproject.toml)
if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  echo "Creating venv..."
  python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
"$INSTALL_DIR/.venv/bin/python" -m pip install "$INSTALL_DIR"
echo "[OK] Dependencies installed"

# 4. Binaries: GGUF models (~7.5 GB) + llama.cpp CPU build.
#    NOTE: Linux installer uses the CPU build (no GPU-vendor assumptions).
#    For CUDA/Vulkan, install llama.cpp manually into runtime/llama.cpp/.
if [[ "$SKIP_MODELS" != "1" ]]; then
  echo "Fetching GGUF models (SHA256-verified, ~7.5 GB)..."
  "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/scripts/fetch_binaries.py" --models --tiny-sd --repo-root "$INSTALL_DIR"
fi
if [[ "$SKIP_LLAMACPP" != "1" ]]; then
  echo "Fetching llama.cpp CPU runtime..."
  "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/scripts/fetch_binaries.py" --llamacpp --repo-root "$INSTALL_DIR"
fi

# 5. PATH shim
mkdir -p "$HOME/.local/bin"
ln -sf "$INSTALL_DIR/.venv/bin/hcscoder" "$HOME/.local/bin/hcscoder"
ln -sf "$INSTALL_DIR/.venv/bin/prime-agent" "$HOME/.local/bin/prime-agent"
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
  echo "[OK] Added ~/.local/bin to PATH (restart shell or: export PATH=\"\$HOME/.local/bin:\$PATH\")"
fi

# 6. Verify
echo "Running diagnostics..."
"$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/cli.py" doctor

echo ""
echo "INSTALL COMPLETE. Try:"
echo "  hcscoder              # interactive REPL"
echo "  hcscoder run \"<task>\"  # one-shot task with streaming"
echo "  hcscoder --help       # all commands (prime-agent is an alias)"
