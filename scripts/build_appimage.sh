#!/usr/bin/env bash
#
# Build the Linux AppImage.
#
# Used both locally and by the GitLab CI pipeline, so the build is defined in
# exactly one place and can be reproduced on a developer machine before pushing.
#
# The packaged layout matters: electron-builder copies the repository to
# resources/app (see the extraResources entry in the GUI package.json), which is
# where main.js looks when app.isPackaged is true. Both the copy and that lookup
# depend on this script being run from the repository root.
#
# Usage:  ./scripts/build_appimage.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="$(cat "$ROOT_DIR/VERSION" 2>/dev/null | tr -d '[:space:]')"
[ -n "$VERSION" ] || VERSION="0.0.0"

GUI_DIR="$ROOT_DIR/src/tradebot_sci/electron_gui"
DIST_DIR="$ROOT_DIR/dist"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[0;33m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()    { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

[[ -d "$GUI_DIR" ]] || fail "GUI directory not found: $GUI_DIR"
command -v node >/dev/null 2>&1 || fail "node is required to build the AppImage."

info "Building Tradebot SCI AppImage"
info "  version: $(cat "$ROOT_DIR/VERSION" 2>/dev/null || echo 'unknown')"
info "  arch:    $(uname -m)"

cd "$GUI_DIR"

# In CI a lockfile makes the build reproducible; locally a plain install is more
# forgiving if the lockfile is out of date. Falls back either way.
if [[ -f package-lock.json ]]; then
    info "Installing GUI dependencies (npm ci)..."
    npm ci --no-audit --no-fund || npm install --no-audit --no-fund
else
    info "Installing GUI dependencies (npm install)..."
    npm install --no-audit --no-fund
fi

# ── Bundle uv ────────────────────────────────────────────────────────────────
# An AppImage is a read-only squashfs mount, so the virtual environment cannot live
# inside it. The app provisions one on first launch instead, and needs a package
# manager to do that. uv is a single self-contained binary that can also download
# its own CPython, so the app does not depend on whatever interpreter the
# distribution happens to ship.
UV_VERSION="${UV_VERSION:-0.12.13}"
case "$(uname -m)" in
    x86_64)         UV_TARGET="x86_64-unknown-linux-gnu" ;;
    aarch64|arm64)  UV_TARGET="aarch64-unknown-linux-gnu" ;;
    *) fail "No uv build for architecture $(uname -m)" ;;
esac
UV_VENDOR="$GUI_DIR/vendor/uv"
if [[ -x "$UV_VENDOR/uv" ]]; then
    info "uv already vendored: $("$UV_VENDOR/uv" --version)"
else
    info "Fetching uv $UV_VERSION ($UV_TARGET)..."
    UV_TMP="$(mktemp -d)"
    curl -fsSL -o "$UV_TMP/uv.tar.gz" \
        "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${UV_TARGET}.tar.gz" \
        || fail "Could not download uv ${UV_VERSION} for ${UV_TARGET}"
    tar -xzf "$UV_TMP/uv.tar.gz" -C "$UV_TMP"
    FOUND="$(find "$UV_TMP" -type f -name uv -perm -u+x | head -1)"
    [[ -n "$FOUND" ]] || fail "uv binary not found inside the downloaded archive"
    mkdir -p "$UV_VENDOR"
    cp "$FOUND" "$UV_VENDOR/uv"
    chmod 755 "$UV_VENDOR/uv"
    rm -rf "$UV_TMP"
    info "uv vendored: $("$UV_VENDOR/uv" --version)"
fi

info "Running electron-builder..."
# package.json carries its own version field, which drifts from the VERSION file the
# release process bumps. Pass VERSION through extraMetadata so the artifact is named
# for the actual release rather than a stale number baked into package.json.
npx electron-builder --linux AppImage -c.extraMetadata.version="$VERSION"

# electron-builder writes into the repository root, not into the GUI directory.
[[ -d "$DIST_DIR" ]] || fail "Expected build output at $DIST_DIR, but it does not exist."

APPIMAGE="$(ls -1 "$DIST_DIR"/*.AppImage 2>/dev/null | head -1 || true)"
[[ -n "$APPIMAGE" ]] || fail "No .AppImage produced in $DIST_DIR"
success "Built: $(basename "$APPIMAGE")  ($(du -h "$APPIMAGE" | cut -f1))"
echo "$APPIMAGE"
