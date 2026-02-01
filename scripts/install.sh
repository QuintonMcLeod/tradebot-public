#!/usr/bin/env bash
set -euo pipefail

# Tradebot SCI - Universal Installer
# Supports: Ubuntu/Debian, Fedora, Arch Linux

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info() { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

info "Starting Tradebot SCI Universal Installer..."

# 1. Detect Distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    error "Cannot detect Linux distribution. /etc/os-release missing."
fi

info "Detected OS: $OS"

# 2. Install System Dependencies
install_sys_deps() {
    info "Installing system dependencies for $OS..."
    case "$OS" in
        ubuntu|debian|pop|mint)
            sudo apt update
            sudo apt install -y tmux git rsync curl wget build-essential python3-dev python3-venv \
                libnss3 libatk-bridge2.0-0 libxss1 libasound2 libgbm1
            ;;
        fedora)
            sudo dnf install -y tmux git rsync curl wget gcc python3-devel python3-pip \
                nss at-spi2-atk libXScrnSaver alsa-lib mesa-libgbm
            ;;
        arch|manjaro)
            sudo pacman -Syu --noconfirm tmux git rsync curl wget base-devel python nss \
                at-spi2-atk libxss alsa-lib mesa
            ;;
        *)
            warn "Unsupported distribution '$OS'. Please install tmux, git, and python3-dev manually."
            ;;
    esac
}

install_sys_deps

# 3. Check/Install Node.js (Required for GUI)
if ! command -v node >/dev/null 2>&1; then
    info "Node.js not found. Installing Node.js 20 (LTS)..."
    case "$OS" in
        ubuntu|debian|pop|mint)
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
            sudo apt install -y nodejs
            ;;
        fedora)
            sudo dnf install -y nodejs
            ;;
        arch|manjaro)
            sudo pacman -S --noconfirm nodejs npm
            ;;
    esac
else
    info "Node.js $(node -v) already installed."
fi

# 4. Check/Install Poetry
if ! command -v poetry >/dev/null 2>&1; then
    info "Poetry not found. Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
    # Add to bashrc if not present
    if ! grep -q "export PATH=\"\$HOME/.local/bin:\$PATH\"" ~/.bashrc; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    fi
else
    info "Poetry $(poetry --version) already installed."
fi

# 5. Application Initialization
info "Initializing application environment..."

# Python venv and dependencies
if [ ! -d ".venv" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv .venv
fi

info "Installing Python dependencies via Poetry..."
source .venv/bin/activate
# We use the full path to poetry just in case it was just installed
POETRY_BIN="$HOME/.local/bin/poetry"
if [ ! -f "$POETRY_BIN" ]; then POETRY_BIN="poetry"; fi

$POETRY_BIN install --with gui

# GUI dependencies
info "Installing GUI dependencies (npm)..."
cd src/tradebot_sci/electron_gui
npm install
cd ../../..

# Configuration
if [ ! -f ".env" ]; then
    info "Creating .env from example..."
    cp .env.example .env
    warn ".env created. PLEASE EDIT IT with your API keys before running the bot."
fi

# 6. Desktop Shortcut
create_shortcut() {
    info "Creating desktop shortcut..."
    local DESKTOP_FILE="tradebot.desktop"
    local ICON_PATH="$ROOT_DIR/src/tradebot_sci/electron_gui/assets/icon.png"
    local EXEC_PATH="$ROOT_DIR/scripts/tradebot.sh --gui"
    local APP_DIR="$HOME/.local/share/applications"

    mkdir -p "$APP_DIR"

    cat <<EOF > "$APP_DIR/$DESKTOP_FILE"
[Desktop Entry]
Name=Tradebot SCI
Comment=AI-Powered Trading Assistant
Exec=$EXEC_PATH
Icon=$ICON_PATH
Terminal=false
Type=Application
Categories=Finance;Utility;
Path=$ROOT_DIR
EOF

    chmod +x "$APP_DIR/$DESKTOP_FILE"
    
    # Also copy to ~/Desktop if it exists
    if [ -d "$HOME/Desktop" ]; then
        cp "$APP_DIR/$DESKTOP_FILE" "$HOME/Desktop/"
        chmod +x "$HOME/Desktop/$DESKTOP_FILE"
        success "Shortcut created on Desktop and in Applications menu."
    else
        success "Shortcut created in Applications menu."
    fi
}

create_shortcut

# 7. Success Output
echo ""
success "Tradebot SCI Installation Complete!"
info "Next Steps:"
echo -e "  1. Edit ${YELLOW}.env${NC} with your API keys."
echo -e "  2. Launch the GUI: ${GREEN}./scripts/tradebot.sh --gui${NC}"
echo -e "  3. Or launch headless: ${GREEN}./scripts/tradebot.sh${NC}"
echo ""
