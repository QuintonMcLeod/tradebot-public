#!/bin/bash
# Tradebot SCI - Automated MT5 Launcher
# Launches MetaTrader 5 inside Wine using the completely headless, symbol-independent TradebotSCI startup configuration.

WINE_PREFIX_DIR="${WINEPREFIX:-$HOME/.wine64}"
WINE_C_DRIVE="$WINE_PREFIX_DIR/drive_c"

MT5_EXE=$(find "$WINE_C_DRIVE" -type f -iname "terminal64.exe" -path "*/MetaTrader 5/*" | head -n 1)

if [ -z "$MT5_EXE" ]; then
    echo "[!] Could not locate MetaTrader 5 terminal64.exe inside $WINE_C_DRIVE"
    exit 1
fi

SCRIPT_DIR="$(dirname "$0")"
STARTUP_INI="$SCRIPT_DIR/../tools/mt5/tradebot_startup.ini"

# Wine path conversion
WINE_STARTUP_INI=$(winepath -w "$STARTUP_INI")

echo "=================================================="
echo "    Launching MT5 ZeroMQ Bridge Background        "
echo "=================================================="
echo "[+] Using Configuration: $WINE_STARTUP_INI"

WINEPREFIX="$WINE_PREFIX_DIR" WINEARCH=win64 wine "$MT5_EXE" /config:"$WINE_STARTUP_INI" > /dev/null 2>&1 &

echo "[SUCCESS] MetaTrader 5 is booting up."
echo "The Tradebot ZMQ Bridge will automatically mount on EURUSD and bind to tcp://*:5555."
echo "You can safely run the Tradebot SCI Python engine now!"
