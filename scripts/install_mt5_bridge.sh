#!/bin/bash
# Tradebot SCI - Automated MT5 ZeroMQ Bridge Installer
# This script locates your MT5 installation within Wine, injects the ZMQ bridge, and compiles it.

echo "===================================================="
echo "    Tradebot SCI MT5 ZMQ Bridge Auto-Installer"
echo "===================================================="

# Check if wine is installed
if ! command -v wine &> /dev/null; then
    echo "[!] Wine is not installed. Please install wine to proceed."
    exit 1
fi

# Check for custom WINEPREFIX
WINE_PREFIX_DIR="${WINEPREFIX:-$HOME/.wine}"
WINE_C_DRIVE="$WINE_PREFIX_DIR/drive_c"

if [ ! -d "$WINE_C_DRIVE" ]; then
    echo "[!] Could not find Wine C: drive at $WINE_C_DRIVE"
    echo "    If you are using a custom WINEPREFIX, please run the script like:"
    echo "    WINEPREFIX=~/.wine64 ./scripts/install_mt5_bridge.sh"
    exit 1
fi

echo "[*] Searching for MetaTrader 5 Terminal Data Folder..."
# Terminal data folders are located in AppData/Roaming/MetaQuotes/Terminal/ or Program Files natively
TERMINAL_DIR=$(find "$WINE_C_DRIVE" -type d -name "MQL5" 2>/dev/null | grep -i "MetaTrader" | head -n 1)

if [ -z "$TERMINAL_DIR" ]; then
    echo "[!] Could not locate MetaTrader 5 'MQL5' data folder."
    echo "    Make sure you have launched MT5 at least once after installing!"
    exit 1
fi

echo "[*] Found MT5 Data Folder: $TERMINAL_DIR"

# 1. Copy Files
echo "[*] Injecting MT5 ZeroMQ EA and Libraries..."
cp -r tools/mt5/mql-zmq/Include/* "$TERMINAL_DIR/Include/"
cp tools/mt5/MQL5/Experts/Tradebot_ZMQ_Bridge.mq5 "$TERMINAL_DIR/Experts/"
cp tools/mt5/mql-zmq/Library/MT5/*.dll "$TERMINAL_DIR/Libraries/"

echo "[+] Files successfully injected."

# 2. Compile via MetaEditor CLI
echo "[*] Locating MetaEditor..."
METAEDITOR_PATH=$(find "$WINE_C_DRIVE" -type f -iname "metaeditor64.exe" | head -n 1)

if [ -z "$METAEDITOR_PATH" ]; then
    echo "[!] Could not find metaeditor64.exe!"
    exit 1
fi

echo "[*] Found MetaEditor at: $METAEDITOR_PATH"
echo "[*] Compiling Tradebot_ZMQ_Bridge.mq5 silently..."

# Convert paths to wine format for the compiler
WINE_TERMINAL_DIR=$(winepath -w "$(dirname "$TERMINAL_DIR")")

# Note: MetaEditor CLI uses /compile
WINEDEBUG=-all wine "$METAEDITOR_PATH" /compile:"$WINE_TERMINAL_DIR\\MQL5\\Experts\\Tradebot_ZMQ_Bridge.mq5" /log

# 3. Automate MT5 Application Settings
TERMINAL_CONFIG="$(dirname "$TERMINAL_DIR")/Config/terminal.ini"
if [ -f "$TERMINAL_CONFIG" ]; then
    echo "[*] Automating MT5 Global Expert Settings..."
    
    # Since terminal.ini might be UTF-16LE, convert it to UTF-8 for sed to work
    iconv -f UTF-16LE -t UTF-8 "$TERMINAL_CONFIG" > "${TERMINAL_CONFIG}.utf8"
    
    # Check "Allow automated trading" and "Allow DLL imports"
    sed -i 's/AllowDllImport=0/AllowDllImport=1/g' "${TERMINAL_CONFIG}.utf8"
    sed -i 's/AllowDllImport=2/AllowDllImport=1/g' "${TERMINAL_CONFIG}.utf8"
    sed -i 's/Enabled=0/Enabled=1/g' "${TERMINAL_CONFIG}.utf8"
    sed -i 's/Enabled=2/Enabled=1/g' "${TERMINAL_CONFIG}.utf8"
    
    # If the flags literally don't exist under [Experts], append them
    if ! grep -q "AllowDllImport=" "${TERMINAL_CONFIG}.utf8"; then
        sed -i '/^\[Experts\]/a AllowDllImport=1' "${TERMINAL_CONFIG}.utf8"
    fi
     if ! grep -q "Enabled=" "${TERMINAL_CONFIG}.utf8"; then
        sed -i '/^\[Experts\]/a Enabled=1' "${TERMINAL_CONFIG}.utf8"
    fi
    
    # Convert back to UTF-16LE
    iconv -f UTF-8 -t UTF-16LE "${TERMINAL_CONFIG}.utf8" > "$TERMINAL_CONFIG"
    rm "${TERMINAL_CONFIG}.utf8"
    echo "[+] Configuration updated cleanly."
fi

# Check if EX5 was generated
if [ -f "$TERMINAL_DIR/Experts/Tradebot_ZMQ_Bridge.ex5" ]; then
    echo "===================================================="
    echo "[SUCCESS] ZeroMQ Bridge Installed & Compiled Smoothly!"
    echo "Terminal Settings have been automatically configured."
    echo ""
    echo "FINAL STEP:"
    echo "1. Boot up MetaTrader 5."
    echo "2. Open an ACTIVE chart (e.g., right click EURUSD.pro -> Chart Window)"
    echo "3. Drag 'Tradebot_ZMQ_Bridge' from the Navigator onto that chart and hit OK."
    echo "===================================================="
else
    echo "===================================================="
    echo "[FAILED] MetaEditor failed to compile the EA."
    echo "Check the compilation log in the Experts folder."
    echo "===================================================="
    exit 1
fi
