@echo off
set MT5_EXE=C:\Program Files\MetaTrader 5\terminal64.exe
set STARTUP_INI=..\tools\mt5\tradebot_startup.ini

if not exist "%MT5_EXE%" (
    echo [!] Could not locate MetaTrader 5 terminal64.exe at %MT5_EXE%.
    exit /b 1
)

echo ==================================================
echo     Launching MT5 ZeroMQ Bridge Background        
echo ==================================================

start "" "%MT5_EXE%" /config:"%~dp0%STARTUP_INI%"

echo [SUCCESS] MetaTrader 5 is booting up.
exit /b 0
