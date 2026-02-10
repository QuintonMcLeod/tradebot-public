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
            info "Adding deadsnakes PPA to ensure Python 3.11+ is available..."
            # Keep silent if possible, catch errors
            if ! command -v add-apt-repository >/dev/null 2>&1; then
                sudo apt install -y software-properties-common
            fi
            # Add PPA if not present (heuristic check)
            if ! grep -q "deadsnakes/ppa" /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; then
                 sudo add-apt-repository -y ppa:deadsnakes/ppa
            fi
            
            sudo apt update
            sudo apt install -y tmux git rsync curl wget build-essential \
                 python3.11 python3.11-venv python3.11-dev \
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
        msys*|cygwin*|mingw*|windows)
            info "Windows detected. Assuming dependencies are managed manually."
            info "Ensure Python 3.10+, Node.js 20+, and Git are installed via installer."
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

# 3.5 Detect Python Executable (Robust)
find_valid_python() {
    # On Windows, 'python3' is often a broken App Execution Alias for the Windows Store.
    # We must try running '--version' to ensure it's a real interpreter.
    # We check specific versions first, then 'python' (standard on Windows), then 'python3' (standard on Linux), then 'py'.
    for cmd in python3.12 python3.11 python python3 py; do
        if command -v "$cmd" >/dev/null 2>&1; then
            if "$cmd" --version >/dev/null 2>&1; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_EXEC=$(find_valid_python)

if [ -z "$PYTHON_EXEC" ]; then
    error "Python environment not found. Please install Python 3.11+."
fi

info "Using Python executable: $PYTHON_EXEC"

# 3.6 Python Sanity Check (Crucial for Windows)
info "Verifying Python environment stability..."
if ! "$PYTHON_EXEC" -c "import encodings; import json; print('Python Sanity Check Passed')" >/dev/null 2>&1; then
    echo ""
    error "CRITICAL: Your Python installation is CORRUPTED."
    echo -e "${RED}Reason: Failed to import standard libraries (encodings/json).${NC}"
    echo -e "${YELLOW}Detected Path: $(command -v "$PYTHON_EXEC" || echo "$PYTHON_EXEC")${NC}"
    echo ""
    echo -e "This often happens with unstable versions (e.g., Python 3.14 Alpha) or bad installs."
    echo -e "---------------------------------------------------------------------"
    echo -e "FIX INSTRUCTIONS:"
    echo -e "1. Uninstall your current Python version fully."
    echo -e "2. Go to https://www.python.org/downloads/"
    echo -e "3. Download and Install **Python 3.12 (Stable)**."
    echo -e "4. IMPORTANT: Check the box 'Add Python to PATH' during install."
    echo -e "---------------------------------------------------------------------"
    exit 1
fi

# 4. Check/Install Poetry
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring  # Prevent hangs on Linux during install

# Check if already installed in ~/.local/bin but not in PATH
if [ -f "$HOME/.local/bin/poetry" ]; then
    info "Poetry found at $HOME/.local/bin/poetry. Adding to PATH..."
    export PATH="$HOME/.local/bin:$PATH"
else
    # Windows: It might be in a versioned folder like .../Python314/Scripts
    # Search for poetry.exe in APPDATA
    if [ -n "${APPDATA:-}" ]; then
        FOUND_POETRY=$(find "$APPDATA/Python" -name "poetry.exe" -print -quit 2>/dev/null)
        if [ -n "$FOUND_POETRY" ]; then
            POETRY_DIR=$(dirname "$FOUND_POETRY")
            info "Poetry found at $FOUND_POETRY. Adding $POETRY_DIR to PATH..."
            export PATH="$POETRY_DIR:$PATH"
        fi
    fi
fi

if ! command -v poetry >/dev/null 2>&1; then
    info "Poetry not found. Installing Poetry via pip (more robust)..."
    
    # Ensure pip is available
    if ! "$PYTHON_EXEC" -m pip --version >/dev/null 2>&1; then
         info "pip not found. Attempting to install pip..."
         case "$OS" in
            ubuntu|debian|pop|mint|linuxmint) sudo apt install -y python3-pip ;;
            fedora) sudo dnf install -y python3-pip ;;
            arch|manjaro) sudo pacman -S --noconfirm python-pip ;;
            windows) 
                info "Attempting to bootstrap pip via ensurepip..."
                "$PYTHON_EXEC" -m ensurepip --upgrade --default-pip || {
                    error "CRITICAL: Your Python installation at $(command -v "$PYTHON_EXEC") appears corrupted (missing pip/libraries). Please reinstall Python 3.12 (Stable) from python.org and check 'Add to PATH' and 'Install pip'."
                }
                ;;
         esac
    fi

    # Install poetry specific version to avoid breaking changes, or latest
    "$PYTHON_EXEC" -m pip install --user poetry || {
        warn "Pip install failed. Trying global install..."
        "$PYTHON_EXEC" -m pip install poetry
    }
    
    export PATH="$HOME/.local/bin:$PATH"
    
    # Windows Post-Install Path Hunt
    if [ "$OS" == "windows" ] || [[ "$OSTYPE" == "msys" ]]; then
        if [ -n "${APPDATA:-}" ]; then
            FOUND_POETRY=$(find "$APPDATA/Python" -name "poetry.exe" -print -quit 2>/dev/null)
            if [ -n "$FOUND_POETRY" ]; then
                 POETRY_DIR=$(dirname "$FOUND_POETRY")
                 export PATH="$POETRY_DIR:$PATH"
            fi
        fi
    fi

    # Add to bashrc if not present
    touch ~/.bashrc
    if ! grep -q "export PATH=\"\$HOME/.local/bin:\$PATH\"" ~/.bashrc; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    fi
else
    info "Poetry $(poetry --version) already installed."
fi

# 5. Application Initialization
info "Initializing application environment..."

# Python venv and dependencies
# Check for venv (bin for Linux/Mac, Scripts for Windows)
ACTIVATE_SCRIPT=".venv/bin/activate"
if [ -f ".venv/Scripts/activate" ]; then
    ACTIVATE_SCRIPT=".venv/Scripts/activate"
fi

if [ ! -d ".venv" ] || [ ! -f "$ACTIVATE_SCRIPT" ]; then
    info "Creating Python virtual environment using $PYTHON_EXEC..."
    "$PYTHON_EXEC" -m venv .venv || {
        error "Failed to create virtual environment with $PYTHON_EXEC."
    }
    # Re-check activation script location after creation
    if [ -f ".venv/Scripts/activate" ]; then
        ACTIVATE_SCRIPT=".venv/Scripts/activate"
    fi
fi

info "Installing Python dependencies via Poetry..."
if [ -f "$ACTIVATE_SCRIPT" ]; then
    source "$ACTIVATE_SCRIPT"
else
    error "Virtual environment activation script not found ($ACTIVATE_SCRIPT). Setup failed."
fi

# We use the full path to poetry just in case it was just installed
POETRY_BIN="poetry"
if [ -f "$HOME/.local/bin/poetry" ]; then POETRY_BIN="$HOME/.local/bin/poetry"; fi

$POETRY_BIN env use "$PYTHON_EXEC"
$POETRY_BIN install --with gui

# Install additional broker dependencies not in pyproject.toml
info "Installing additional broker dependencies..."
pip install oandapyV20 --quiet

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
        info "Creating Windows Desktop shortcut (via Git Bash)..."
        # Attempt to find desktop
        DESKTOP_PATH="$HOME/Desktop"
        # If running in MINGW/Git Bash, $HOME might be /c/Users/Name
        # Verify it exists
        if [ ! -d "$DESKTOP_PATH" ]; then
             DESKTOP_PATH="/c/Users/$USERNAME/Desktop"
        fi
        
        if [ -d "$DESKTOP_PATH" ]; then
            # Convert ROOT_DIR to Windows format for valid .bat
            # Use cygpath if available
            if command -v cygpath >/dev/null 2>&1; then
                WIN_ROOT=$(cygpath -w "$ROOT_DIR")
            else
                # Fallback naive conversion
                WIN_ROOT=$(echo "$ROOT_DIR" | sed 's|^/\([a-z]\)/|\1:/|' | sed 's|/|\\|g')
            fi
            
            BAT_FILE="$DESKTOP_PATH/Tradebot SCI.bat"
            cat <<EOF > "$BAT_FILE"
@echo off
cd /d "$WIN_ROOT"
bash scripts/tradebot.sh --gui
pause
EOF
            success "Created Windows shortcut: $BAT_FILE"
        else
            warn "Could not find Desktop folder. Please create a shortcut manually."
        fi
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
