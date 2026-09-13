#!/usr/bin/env bash
#
# Tradebot SCI — macOS installer.
#
# No Homebrew. No Xcode Command Line Tools. No sudo. Everything lands in the
# repository and in ~/.local, so nothing outside the user's home directory is
# touched and nothing has to be uninstalled afterwards.
#
# Why not Homebrew: the previous macOS path installed Homebrew (which itself
# requires the Xcode Command Line Tools GUI prompt, a sudo password and several
# minutes), then ran `brew update` and installed eight formulae, then installed
# Poetry and resolved dependencies through it. Every one of those steps is a
# place a new user can get stuck, and none of them are needed:
#
#   Python  -> uv ships a standalone CPython build. A static binary, no sudo.
#   Node    -> the official prebuilt macOS tarball, extracted into ~/.local.
#   deps    -> uv resolves and installs them in seconds.
#
# Installing this way needs no compiler, so the Xcode CLT dialog never appears.
#
# Usage:  ./scripts/install_mac.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_FILE="$ROOT_DIR/install-mac.log"
: > "$LOG_FILE"

# Python version to install. pyproject.toml requires >=3.11,<3.14, so 3.12 is the
# newest version inside the supported range.
PY_VERSION="3.12"

# Node LTS. Pinned rather than "latest" so an install is reproducible.
NODE_VERSION="22.22.0"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()    { echo -e "${RED}[ERROR]${NC} $1"; echo -e "  Full log: ${YELLOW}$LOG_FILE${NC}"; exit 1; }

# Run a command quietly, appending output to the log, with a simple progress line.
run() {
    local label="$1"; shift
    printf "  ${CYAN}→${NC} %-46s" "$label"
    if "$@" >> "$LOG_FILE" 2>&1; then
        echo -e "\r  ${GREEN}✓${NC} $label"
    else
        echo -e "\r  ${RED}✗${NC} $label"
        fail "'$label' failed — see $LOG_FILE"
    fi
}

echo -e "${CYAN}${BOLD}"
cat <<'BANNER'
  _______            _      _           _      _____  _____ _____
 |__   __|          | |    | |         | |    / ____|/ ____|_   _|
    | |_ __ __ _  __| | ___| |__   ___ | |_  | (___ | |      | |
    | | '__/ _` |/ _` |/ _ \ '_ \ / _ \| __|  \___ \| |      | |
    | | | | (_| | (_| |  __/ |_) | (_) | |_   ____) | |____ _| |_
    |_|_|  \__,_|\__,_|\___|_.__/ \___/ \__| |_____/ \_____|_____|
BANNER
echo -e "${NC}"
echo -e "        ${BOLD}macOS Installer${NC}  ${CYAN}(no Homebrew required)${NC}"
echo -e "        Logging to: ${YELLOW}install-mac.log${NC}\n"

# ── 1. Platform checks ──────────────────────────────────────────────────────

if [[ "$(uname -s)" != "Darwin" ]]; then
    fail "This installer is for macOS only. Use scripts/install.sh instead."
fi

ARCH="$(uname -m)"
case "$ARCH" in
    arm64)  NODE_ARCH="arm64" ;;   # Apple Silicon
    x86_64) NODE_ARCH="x64"   ;;   # Intel
    *)      fail "Unsupported CPU architecture: $ARCH" ;;
esac
info "macOS detected on ${BOLD}$ARCH${NC} (Node target: $NODE_ARCH)"

# curl and tar are part of macOS itself, so these always exist. Checked anyway so
# a broken PATH fails here with a clear message rather than halfway through.
for tool in curl tar; do
    command -v "$tool" >/dev/null 2>&1 || fail "'$tool' not found. It ships with macOS — check your PATH."
done

# ── 2. uv (provides Python and the package resolver) ────────────────────────

export PATH="$HOME/.local/bin:$PATH"

if command -v uv >/dev/null 2>&1; then
    success "uv already installed ($(uv --version 2>/dev/null | head -1))"
else
    info "Installing uv (standalone binary, no sudo)..."
    run "Downloading and installing uv" \
        bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null 2>&1 || fail "uv installed but not on PATH. Open a new terminal and re-run."
    success "uv installed: $(uv --version)"
fi

# ── 3. Python ───────────────────────────────────────────────────────────────

info "Installing Python $PY_VERSION (uv-managed, independent of system Python)..."
run "Installing Python $PY_VERSION" uv python install "$PY_VERSION"

if [[ -d ".venv" ]]; then
    info "Existing .venv found — reusing it."
else
    run "Creating virtual environment (.venv)" uv venv .venv --python "$PY_VERSION"
fi
success "Python environment ready"

# ── 4. Python dependencies ──────────────────────────────────────────────────
#
# numpy, requests and aiohttp are imported by src/ but are not listed under
# [tool.poetry.dependencies] — they currently arrive only as transitive
# dependencies of ccxt and friends. They are named explicitly here so the install
# cannot silently lose them when a transitive dependency changes.

info "Installing Python dependencies..."
run "Installing dependencies" uv pip install --python .venv \
    "pydantic>=2.4.2" \
    "httpx>=0.25.2" \
    "python-dotenv>=1.0.0" \
    "PyYAML>=6.0.1" \
    "tenacity>=8.2.3" \
    "ib-insync>=0.9.86" \
    "ccxt>=4.5.27" \
    "rich==13.9.4" \
    "astral>=3.2" \
    "oandapyV20>=0.7.2" \
    "six>=1.16.0" \
    "pyzmq>=27.1.0" \
    numpy requests aiohttp

# Verify the environment actually imports what the bot needs, rather than
# trusting that the install reported success.
run "Verifying imports" .venv/bin/python -c \
    "import pydantic, httpx, yaml, ccxt, zmq, requests, aiohttp, numpy, oandapyV20"

# ── 5. Node.js ──────────────────────────────────────────────────────────────

NODE_DIR="$HOME/.local/node-v$NODE_VERSION-darwin-$NODE_ARCH"
if [[ -x "$NODE_DIR/bin/node" ]]; then
    success "Node already installed ($("$NODE_DIR/bin/node" -v))"
else
    info "Installing Node.js $NODE_VERSION (official tarball, no sudo)..."
    TARBALL="node-v$NODE_VERSION-darwin-$NODE_ARCH.tar.gz"
    TMP_DIR="$(mktemp -d)"
    run "Downloading Node $NODE_VERSION" \
        curl -fsSL -o "$TMP_DIR/$TARBALL" "https://nodejs.org/dist/v$NODE_VERSION/$TARBALL"
    mkdir -p "$HOME/.local"
    run "Extracting Node" tar -xzf "$TMP_DIR/$TARBALL" -C "$HOME/.local"
    rm -rf "$TMP_DIR"
    [[ -x "$NODE_DIR/bin/node" ]] || fail "Node extraction failed — expected $NODE_DIR/bin/node"
    success "Node installed: $("$NODE_DIR/bin/node" -v)"
fi

# Expose node/npm on PATH for this shell and future shells.
export PATH="$NODE_DIR/bin:$PATH"
for rc in "$HOME/.zprofile" "$HOME/.zshrc"; do
    [[ -f "$rc" ]] || continue
    if ! grep -q "node-v$NODE_VERSION-darwin-$NODE_ARCH" "$rc" 2>/dev/null; then
        {
            echo ''
            echo "# Tradebot SCI — Node.js"
            echo "export PATH=\"$NODE_DIR/bin:\$PATH\""
        } >> "$rc"
    fi
done
info "Added Node to PATH in ~/.zprofile and ~/.zshrc"

# ── 6. Electron GUI dependencies ────────────────────────────────────────────

GUI_DIR="$ROOT_DIR/src/tradebot_sci/electron_gui"
if [[ -d "$GUI_DIR/node_modules/electron" ]]; then
    success "Electron already installed"
else
    info "Installing Electron GUI dependencies (this one takes a few minutes)..."
    run "Installing Electron and GUI packages" \
        bash -c "cd '$GUI_DIR' && '$NODE_DIR/bin/npm' install --no-audit --no-fund"
fi

# ── 7. Configuration ────────────────────────────────────────────────────────

if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
        cp .env.example .env
        warn ".env created from .env.example — add your API keys before trading."
    else
        warn "No .env.example found; create a .env manually before running."
    fi
else
    success ".env already present — left untouched"
fi

# ── 8. Desktop launcher ─────────────────────────────────────────────────────

if [[ -d "$HOME/Desktop" ]]; then
    LAUNCHER="$HOME/Desktop/Tradebot SCI.command"
    cat > "$LAUNCHER" <<EOF
#!/bin/bash
# Launches the Tradebot SCI GUI.
cd "$ROOT_DIR" || exit 1
./scripts/tradebot.sh --gui
EOF
    chmod +x "$LAUNCHER"
    success "Desktop launcher created: ${BOLD}Tradebot SCI.command${NC}"
else
    warn "No ~/Desktop folder — skipping the desktop launcher."
fi

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
success "Tradebot SCI installation complete!"
echo ""
info "Next steps:"
echo -e "  1. Add your API keys to ${YELLOW}.env${NC}"
echo -e "  2. Launch the GUI:  ${GREEN}./scripts/tradebot.sh --gui${NC}"
echo -e "  3. Or headless:     ${GREEN}./scripts/tradebot.sh${NC}"
echo ""
info "Nothing was installed outside this folder and ~/.local — no Homebrew, no sudo."
info "To start fresh, delete .venv and re-run this script."
echo ""
