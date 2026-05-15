#!/usr/bin/env bash
set -euo pipefail

# Tradebot SCI - Universal Installer
# Supports: Ubuntu/Debian, Fedora, Arch Linux

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_FILE="$ROOT_DIR/install.log"
> "$LOG_FILE"

echo -e "${CYAN}${BOLD}"
cat << "EOF"
  _______            _      _           _      _____  _____ _____ 
 |__   __|          | |    | |         | |    / ____|/ ____|_   _|
    | |_ __ __ _  __| | ___| |__   ___ | |_  | (___ | |      | |  
    | | '__/ _` |/ _` |/ _ \ '_ \ / _ \| __|  \___ \| |      | |  
    | | | | (_| | (_| |  __/ |_) | (_) | |_   ____) | |____ _| |_ 
    |_|_|  \__,_|\__,_|\___|_.__/ \___/ \__| |_____/ \_____|_____|
EOF
echo -e "${NC}"
echo -e "              ${BOLD}Universal Installer v1.0${NC}"
echo -e "              Logging output to: ${YELLOW}install.log${NC}\n"

info() { echo -e "${CYAN}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    tput civis || true # hide cursor if possible
    while kill -0 $pid 2>/dev/null; do
        local temp=${spinstr#?}
        printf " ${MAGENTA}%c${NC}  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b"
    done
    printf "    \b\b\b\b"
    tput cnorm || true # restore cursor
    wait $pid
    return $?
}

run_with_spinner() {
    local msg="$1"
    shift
    echo -ne "  ${CYAN}→${NC} $msg... "
    "$@" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    if spinner $pid; then
        echo -e "\r  ${GREEN}✓${NC} $msg      "
    else
        echo -e "\r  ${RED}✗${NC} $msg      "
        echo -e "    ${RED}Error: Check install.log for details.${NC}"
        exit 1
    fi
}

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

# Ask for sudo upfront to prevent background processes hanging on password prompts
if [ "$OS" != "windows" ] && [ "$OS" != "darwin" ]; then
    info "Requesting administrator privileges for installation..."
    sudo -v || error "Administrator privileges required to install dependencies."
    # Keep sudo alive until script exits
    while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &
fi

# 2. Install System Dependencies
install_sys_deps() {
    echo ""
    info "Installing system dependencies for $OS..."
    case "$OS" in
        ubuntu|debian|pop|mint|linuxmint)
            # Find the actual Ubuntu base version (e.g. 22.04 or 24.04)
            # Mint Vera/Victoria are based on 22.04, Mint Wilma is 24.04
            OS_VER="0.0"
            if command -v lsb_release >/dev/null 2>&1; then
                OS_VER=$(lsb_release -rs)
                # If Mint, lsb_release -rs returns things like '21.3'. We need the upstream version.
                if [ "$OS" = "linuxmint" ] || [ "$OS" = "mint" ]; then
                     OS_CODENAME=$(lsb_release -cs)
                     case "$OS_CODENAME" in
                         vera|victoria|virginia) OS_VER="22.04" ;;
                         wilma) OS_VER="24.04" ;;
                     esac
                fi
            elif [ -f /etc/os-release ]; then
                # Handle Debian/Pop by extracting VERSION_ID
                OS_VER=$(grep -oP '(?<=VERSION_ID=")\d+\.\d+' /etc/os-release || echo "0.0")
            fi

            # Ubuntu 24.04+ (Noble Numbat) and 24.10+ (Questing Quail) include Python 3.12 natively.
            # Adding deadsnakes on Questing breaks apt because there is no Release file.
            # We ONLY add the PPA if the version is < 24.04. Debian sid/bullseye might not have it either.
            # Using basic float comparison with awk
            NEEDS_PPA=$(awk -v ver="$OS_VER" 'BEGIN { print (ver > 0.0 && ver < 24.04) ? 1 : 0 }')

            # Also force add it if it's explicitly older Ubuntu e.g '20.04' or '22.04'
            if [ "$OS" = "ubuntu" ] || [ "$OS" = "pop" ]; then
                 if [[ "$OS_VER" == "22.04" ]] || [[ "$OS_VER" == "20.04" ]]; then NEEDS_PPA=1; fi
                 if [[ "$OS_VER" == "24.04" ]] || [[ "$OS_VER" == "24.10" ]]; then NEEDS_PPA=0; fi
            fi

            # Keep silent if possible, catch errors
            if ! command -v add-apt-repository >/dev/null 2>&1; then
                run_with_spinner "Adding repo tools" sudo apt install -y software-properties-common
            fi

            # Check if Python 3.11 is natively available BEFORE forcing PPA
            if apt-cache show python3.11 >/dev/null 2>&1; then
                NEEDS_PPA=0
            fi

            # Add PPA if necessary and not already present
            if [ "$NEEDS_PPA" = "1" ] && [ "$OS" != "debian" ]; then
                if ! grep -q "deadsnakes/ppa" /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; then
                     run_with_spinner "Adding Python PPA" sudo add-apt-repository -y ppa:deadsnakes/ppa
                fi
            else
                info "Skipping deadsnakes PPA (OS has native Python 3.11/3.12)"
                if grep -q "deadsnakes/ppa" /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; then
                    run_with_spinner "Removing unsupported Python PPA" sudo add-apt-repository -y --remove ppa:deadsnakes/ppa
                fi
            fi
            
            # Handle Ubuntu 24.04+ t64 package rename
            if apt-cache show libasound2t64 >/dev/null 2>&1; then
                ALSA_PKG="libasound2t64"
                ATK_PKG="libatk-bridge2.0-0t64"
            else
                ALSA_PKG="libasound2"
                ATK_PKG="libatk-bridge2.0-0"
            fi

            if [ "$NEEDS_PPA" = "1" ]; then
                PYTHON_PKG="python3.11 python3.11-venv python3.11-dev"
            else
                PYTHON_PKG="python3 python3-venv python3-dev"
            fi

            run_with_spinner "Updating package lists" bash -c "sudo apt update || true"
            run_with_spinner "Installing system packages" sudo apt install -y tmux git rsync curl wget build-essential $PYTHON_PKG libnss3 $ATK_PKG libxss1 $ALSA_PKG libgbm1
            ;;
        fedora)
            run_with_spinner "Installing Fedora packages" sudo dnf install -y tmux git rsync curl wget gcc python3-devel python3-pip nss at-spi2-atk libXScrnSaver alsa-lib mesa-libgbm
            ;;
        arch|manjaro)
            run_with_spinner "Installing Arch packages" sudo pacman -Syu --noconfirm tmux git rsync curl wget base-devel python nss at-spi2-atk libxss alsa-lib mesa
            ;;
        darwin)
            if ! command -v brew >/dev/null 2>&1; then
                if [ -x /opt/homebrew/bin/brew ]; then
                    eval "$(/opt/homebrew/bin/brew shellenv)"
                elif [ -x /usr/local/bin/brew ]; then
                    eval "$(/usr/local/bin/brew shellenv)"
                fi
            fi

            if ! command -v brew >/dev/null 2>&1; then
                info "Homebrew not found. Installing Homebrew..."
                echo -ne "  ${CYAN}→${NC} Running Homebrew installer (non-interactive)... "
                NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" >> "$LOG_FILE" 2>&1 || true
                echo -e "\r  ${GREEN}✓${NC} Running Homebrew installer (non-interactive)      "
                
                if [ -x /opt/homebrew/bin/brew ]; then
                    eval "$(/opt/homebrew/bin/brew shellenv)"
                elif [ -x /usr/local/bin/brew ]; then
                    eval "$(/usr/local/bin/brew shellenv)"
                fi
            fi
            SHELL_PROFILE="$HOME/.zprofile"
            if ! grep -q 'brew shellenv' "$SHELL_PROFILE" 2>/dev/null; then
                echo '' >> "$SHELL_PROFILE"
                if [ -x /opt/homebrew/bin/brew ]; then
                    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$SHELL_PROFILE"
                else
                    echo 'eval "$(/usr/local/bin/brew shellenv)"' >> "$SHELL_PROFILE"
                fi
            fi
            run_with_spinner "Updating Homebrew" brew update
            run_with_spinner "Installing Mac apps" brew install tmux git rsync curl wget python@3.12 node
            ;;
        msys*|cygwin*|mingw*|windows)
            info "Windows detected. Please manually install dependencies."
            ;;
        *)
            warn "Unsupported distribution '$OS'. Please install tmux, git, and python3-dev manually."
            ;;
    esac
}

install_sys_deps

# 3. Check/Install Node.js (Required for GUI)
echo ""
if ! command -v node >/dev/null 2>&1; then
    info "Installing Node.js 20 (LTS)..."
    case "$OS" in
        ubuntu|debian|pop|mint|linuxmint)
            run_with_spinner "Downloading NodeSource" bash -c "curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
            run_with_spinner "Installing Node.js pkg" sudo apt install -y nodejs
            ;;
        fedora)
            run_with_spinner "Installing Node.js pkg" sudo dnf install -y nodejs
            ;;
        arch|manjaro)
            run_with_spinner "Installing Node.js pkg" sudo pacman -S --noconfirm nodejs npm
            ;;
        darwin)
            if ! command -v node >/dev/null 2>&1; then
                run_with_spinner "Installing Node via brew" brew install node
            fi
            ;;
        windows)
            warn "On Windows, please install Node.js manually: winget install OpenJS.NodeJS.LTS"
            ;;
    esac
else
    success "Node.js $(node -v) verified."
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

# Detect Python user bin path (macOS uses ~/Library/Python/X.Y/bin, Linux uses ~/.local/bin)
PY_VER=$($PYTHON_EXEC -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "3.12")
if [[ "$OS" == "darwin" ]]; then
    PY_USER_BIN="$HOME/Library/Python/$PY_VER/bin"
else
    PY_USER_BIN="$HOME/.local/bin"
fi
export PATH="$PY_USER_BIN:$HOME/.local/bin:$PATH"

# Check if already installed
if [ -f "$PY_USER_BIN/poetry" ] || [ -f "$HOME/.local/bin/poetry" ]; then
    info "Poetry found. Adding to PATH..."
elif command -v poetry >/dev/null 2>&1; then
    info "Poetry $(poetry --version) already installed."
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
    info "Poetry not found. Installing Poetry..."
    
    # Ensure pip is available
    if ! "$PYTHON_EXEC" -m pip --version >/dev/null 2>&1; then
         run_with_spinner "Installing core Python pip" bash -c 'case "$OS" in
            ubuntu|debian|pop|mint|linuxmint) sudo apt install -y python3-pip ;;
            fedora) sudo dnf install -y python3-pip ;;
            arch|manjaro) sudo pacman -S --noconfirm python-pip ;;
            darwin) "$PYTHON_EXEC" -m ensurepip --upgrade || true ;;
            windows) "$PYTHON_EXEC" -m ensurepip --upgrade --default-pip ;;
         esac'
    fi

    # Install poetry — handling modern distros smoothly
    run_with_spinner "Installing Poetry package manager" bash -c '
        if command -v pipx >/dev/null 2>&1; then
            pipx install poetry || true
        elif apt-cache show pipx >/dev/null 2>&1; then
            sudo apt install -y pipx && pipx install poetry || true
        fi
        if ! command -v poetry >/dev/null 2>&1; then
            "$PYTHON_EXEC" -m pip install --user --break-system-packages poetry || \
            "$PYTHON_EXEC" -m pip install --user poetry || \
            "$PYTHON_EXEC" -m pip install poetry || true
        fi
    '
    
    export PATH="$PY_USER_BIN:$HOME/.local/bin:$PATH"
    
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

    # Persist PATH to shell profile
    if [[ "$OS" == "darwin" ]]; then
        # macOS defaults to zsh
        SHELL_RC="$HOME/.zprofile"
        PATH_LINE="export PATH=\"$PY_USER_BIN:\$HOME/.local/bin:\$PATH\""
    else
        SHELL_RC="$HOME/.bashrc"
        PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
    fi
    touch "$SHELL_RC"
    if ! grep -q '.local/bin' "$SHELL_RC" 2>/dev/null; then
        echo "$PATH_LINE" >> "$SHELL_RC"
    fi
fi

if ! command -v poetry >/dev/null 2>&1; then
    warn "Poetry could not be found on PATH. Attempting to locate it..."
    # Last resort: search common locations
    for candidate in "$PY_USER_BIN/poetry" "$HOME/.local/bin/poetry" /usr/local/bin/poetry; do
        if [ -f "$candidate" ]; then
            info "Found poetry at $candidate"
            export PATH="$(dirname "$candidate"):$PATH"
            break
        fi
    done
fi

# 5. Application Initialization
echo ""
info "Initializing application environment..."

# Python venv and dependencies
ACTIVATE_SCRIPT=".venv/bin/activate"
if [ -f ".venv/Scripts/activate" ]; then
    ACTIVATE_SCRIPT=".venv/Scripts/activate"
fi

if [ ! -d ".venv" ] || [ ! -f "$ACTIVATE_SCRIPT" ]; then
    run_with_spinner "Creating Python virtual environment" "$PYTHON_EXEC" -m venv .venv
    if [ -f ".venv/Scripts/activate" ]; then
        ACTIVATE_SCRIPT=".venv/Scripts/activate"
    fi
fi

if [ -f "$ACTIVATE_SCRIPT" ]; then
    source "$ACTIVATE_SCRIPT"
else
    error "Virtual environment activation script not found ($ACTIVATE_SCRIPT). Setup failed."
fi

POETRY_BIN="poetry"
if [ -f "$HOME/.local/bin/poetry" ]; then POETRY_BIN="$HOME/.local/bin/poetry"; fi

$POETRY_BIN env use "$PYTHON_EXEC" >> "$LOG_FILE" 2>&1 || true

run_with_spinner "Syncing poetry.lock dependencies" $POETRY_BIN lock
run_with_spinner "Installing Python dependencies (GUI build)" bash -c "$POETRY_BIN install --with gui || $POETRY_BIN install"

run_with_spinner "Installing broker integrations" pip install oandapyV20 --quiet

run_with_spinner "Installing Electron GUI dependencies" bash -c "cd src/tradebot_sci/electron_gui && npm install"

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
