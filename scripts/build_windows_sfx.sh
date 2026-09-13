#!/usr/bin/env bash
#
# Build the Windows self-extracting setup executable.
#
# Produces dist/Tradebot-SCI-Setup-<version>.exe: a single file that unpacks the
# source tree and runs scripts/windows_installer.ps1.
#
# This runs on Linux — a self-extracting archive is just a small stub with a 7-Zip
# payload appended, so no Windows toolchain is involved. That is why CI can build
# it alongside the Linux AppImage.
#
# Usage:  ./scripts/build_windows_sfx.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DIST_DIR="$ROOT_DIR/dist"
VERSION="$(cat "$ROOT_DIR/VERSION" 2>/dev/null | tr -d '[:space:]')"
[ -n "$VERSION" ] || VERSION="0.0.0"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[0;33m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()    { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# 7-Zip is invoked as 7z, 7za or 7zr depending on the distribution.
SEVENZIP=""
for candidate in 7z 7za 7zr; do
    if command -v "$candidate" >/dev/null 2>&1; then SEVENZIP="$candidate"; break; fi
done
[ -n "$SEVENZIP" ] || fail "7-Zip not found. Install it with: apt-get install p7zip-full"

# The stub that gets prepended. Without it the output is a plain archive, not an .exe.
SFX_MODULE=""
for candidate in /usr/lib/p7zip/7zCon.sfx /usr/lib/7zip/7zCon.sfx /usr/share/p7zip/7zCon.sfx; do
    [ -f "$candidate" ] && { SFX_MODULE="$candidate"; break; }
done
[ -n "$SFX_MODULE" ] || fail "7-Zip SFX module (7zCon.sfx) not found — is p7zip-full installed?"

info "Building Windows self-extracting setup (v$VERSION)"
info "  7z:  $SEVENZIP"
info "  sfx: $SFX_MODULE"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# Same exclusions the public mirror uses, plus everything that only matters to a
# developer or is simply too large to ship in an installer.
info "Staging payload..."
rsync -a \
    --exclude='.git/' --exclude='.git*' \
    --exclude='node_modules/' --exclude='**/node_modules/' \
    --exclude='__pycache__/' --exclude='**/__pycache__/' \
    --exclude='*.pyc' --exclude='**/*.pyc' \
    --exclude='results/' --exclude='scratch/' --exclude='public_mirror/' \
    --exclude='data/' --exclude='logs/' --exclude='.venv/' --exclude='dist/' \
    --exclude='*.log' --exclude='install-mac.log' \
    "$ROOT_DIR/" "$STAGE/" >/dev/null

# scripts/codex is a dangling symlink to a developer's local editor extension.
# It resolves to nothing, so 7-Zip warns on it and it has no business shipping.
rm -f "$STAGE/scripts/codex"

cat > "$STAGE/setup.bat" <<'BAT'
@echo off
rem Tradebot SCI - self-extracting setup bootstrap.
rem
rem Runs from the temporary folder the self-extractor unpacked into. Copies the
rem payload somewhere permanent, then hands off to scripts\windows_installer.ps1.
setlocal

set "TARGET=%LOCALAPPDATA%\Tradebot-SCI"

echo.
echo   ============================================
echo     Tradebot SCI - Setup
echo   ============================================
echo.
echo   Installing to: %TARGET%
echo.

rem Keep an existing .env so API keys survive a re-install.
set "KEEP_ENV="
if exist "%TARGET%\.env" set "KEEP_ENV=%TEMP%\tradebot_env_backup"
if defined KEEP_ENV copy /y "%TARGET%\.env" "%KEEP_ENV%" >nul 2>&1

if not exist "%TARGET%" mkdir "%TARGET%" >nul 2>&1
if not exist "%TARGET%" (
    echo   ERROR: could not create %TARGET%
    echo.
    pause
    exit /b 1
)

echo   Copying files...
rem robocopy returns 0-7 for success; 8 or higher is a real failure.
robocopy "%~dp0." "%TARGET%" /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 >nul
if %ERRORLEVEL% GEQ 8 (
    echo   ERROR: file copy failed ^(robocopy code %ERRORLEVEL%^).
    echo.
    pause
    exit /b 1
)

if defined KEEP_ENV (
    copy /y "%KEEP_ENV%" "%TARGET%\.env" >nul 2>&1
    del "%KEEP_ENV%" >nul 2>&1
    echo   Kept your existing .env ^(API keys preserved^).
)

cd /d "%TARGET%"

echo.
echo   Running the installer...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%TARGET%\scripts\windows_installer.ps1"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo   Setup finished. Launch Tradebot SCI from the desktop shortcut.
) else (
    echo   The installer exited with code %RC%.
    echo   Read the messages above, or re-run:
    echo     powershell -ExecutionPolicy Bypass -File "%TARGET%\scripts\windows_installer.ps1"
)
echo.
pause
endlocal
BAT

# The SFX stub reads this config from the front of the archive. It must be added
# first, and RunProgram must live at the archive root.
CONFIG="$STAGE/../tb_sfx_config.txt"
printf ';!@Install@!UTF-8!\nTitle="Tradebot SCI %s Setup"\nBeginPrompt="Install Tradebot SCI %s to your user folder?"\nRunProgram="setup.bat"\n;!@InstallEnd@!\n' \
    "$VERSION" "$VERSION" > "$CONFIG"

mkdir -p "$DIST_DIR"
OUTPUT="$DIST_DIR/Tradebot-SCI-Setup-$VERSION.exe"
rm -f "$OUTPUT"

info "Compressing (this takes a minute)..."
( cd "$STAGE" && "$SEVENZIP" a "-sfx$SFX_MODULE" -mx=7 "$OUTPUT" "$CONFIG" . >/dev/null )

[ -f "$OUTPUT" ] || fail "7-Zip did not produce $OUTPUT"
success "Built: $(basename "$OUTPUT")  ($(du -h "$OUTPUT" | cut -f1))"
echo "$OUTPUT"
