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
# 1. Detect Distribution
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="darwin"
elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    OS="windows"
elif [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    error "Cannot detect OS. /etc/os-release missing and OSTYPE unknown."
fi

info "Detected OS: $OS"

# 2. Install System Dependencies
install_sys_deps() {
    info "Installing system dependencies for $OS..."
    case "$OS" in
        ubuntu|debian|pop|mint|linuxmint)
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
        darwin)
            if ! command -v brew >/dev/null 2>&1; then
                info "Homebrew not found. Installing Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            fi
            info "Updating Homebrew..."
            brew update
            info "Installing dependencies via Homebrew..."
            brew install tmux git rsync curl wget python node
            ;;
        msys*|cygwin*|mingw*)
            info "Windows detected (Git Bash/MSYS). Assuming dependencies are managed manually or via Chocolatey/Scoop."
            info "Ensure Python 3.10+, Node.js 20+, and Git are installed."
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
        ubuntu|debian|pop|mint|linuxmint)
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
            sudo apt install -y nodejs
            ;;
        fedora)
            sudo dnf install -y nodejs
            ;;
        arch|manjaro)
            sudo pacman -S --noconfirm nodejs npm
            ;;
        darwin)
            # Already installed via brew in sys_deps, checking again just in case
            if ! command -v node >/dev/null 2>&1; then
                brew install node
            fi
            ;;
        windows)
            warn "On Windows, please install Node.js manually or via 'winget install OpenJS.NodeJS.LTS'"
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
if [ ! -d ".venv" ] || [ ! -f ".venv/bin/activate" ]; then
    info "Creating Python virtual environment..."
    # Ensure ensuring pip works
    python3 -m venv .venv || {
        error "Failed to create virtual environment. Ensure python3-venv is installed (e.g., sudo apt install python3-venv)."
    }
fi

info "Installing Python dependencies via Poetry..."
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    error "Virtual environment not found at .venv/bin/activate. Setup failed."
fi

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

    if [[ "$OS" == "darwin" ]]; then
        # Mac Shortcut (AppleScript)
        local APP_NAME="Tradebot SCI"
        local SCRIPT_PATH="$ROOT_DIR/scripts/tradebot.sh"
        local ICON_PATH="$ROOT_DIR/src/tradebot_sci/electron_gui/assets/icon.png"
        
        # Create a simple .app wrapper or just a desktop command file
        # Check if user has a Desktop
        if [ -d "$HOME/Desktop" ]; then
             cat <<EOF > "$HOME/Desktop/$APP_NAME.command"
#!/bin/bash
cd "$ROOT_DIR"
./scripts/tradebot.sh --gui
EOF
             chmod +x "$HOME/Desktop/$APP_NAME.command"
             success "Created macOS launcher on Desktop: $HOME/Desktop/$APP_NAME.command"
        else
             warn "No Desktop folder found, skipping shortcut creation."
        fi
        return
    elif [[ "$OS" == "windows" ]]; then
         warn "Desktop shortcut creation on Windows (Git Bash) is manual. Create a shortcut to 'scripts/tradebot.sh --gui'."
         return
    fi

    # Linux .desktop file
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
