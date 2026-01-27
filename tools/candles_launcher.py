#!/usr/bin/env python
import os
import sys
import subprocess
from tradebot_sci.config.loader import load_settings

def main():
    # Load settings to detect provider reliably
    try:
        settings = load_settings()
        provider = settings.market.exchange_provider.lower()
        alt_data = (settings.market.alternative_market_data or "").lower()
        
        # Check env overrides just in case (though settings loader handles them too)
        env_prov = os.getenv("EXCHANGE_PROVIDER", "").lower()
        env_alt = os.getenv("ALTERNATIVE_MARKET_DATA", "").lower()
        
        if env_prov: provider = env_prov
        if env_alt: alt_data = env_alt
        
        is_alternative = (provider == "alternative" or "ccxt" in provider or "gemini" in provider)
        is_coinbase = ("coinbase" in alt_data)
        
        if is_alternative or is_coinbase:
            # Launch CCXT UI
            # We construct the command carefully.
            # We remove conflicting args (key and its value)
            skip_next = False
            base_args = []
            for i, arg in enumerate(sys.argv[1:]):
                if skip_next:
                    skip_next = False
                    continue
                if arg in ("--refresh-seconds", "--interval", "--rotate-seconds"):
                    skip_next = True
                    continue
                # Handle --key=value style if present (though launcher usually gets --key value)
                if "--refresh-seconds=" in arg or "--interval=" in arg or "--rotate-seconds=" in arg:
                    continue
                base_args.append(arg)
            
            cmd = [
                sys.executable, 
                "tools/candles_ccxt_ui.py",
                "--refresh-seconds", "0.5", 
                "--interval", "0.5" # UI loop speed
            ] + base_args
            
            print(f"[LAUNCHER] Detected CCXT/Gemini/Coinbase. Launching fast UI (0.5s)...")
        else:
            # Launch IBKR UI
            cmd = [
                sys.executable, 
                "tools/candles_ibkr_ui.py"
            ] + sys.argv[1:]
            print(f"[LAUNCHER] Detected IBKR (or default). Launching standard UI...")

        subprocess.run(cmd)
        
    except Exception as e:
        print(f"[LAUNCHER] Error detecting provider: {e}")
        print("[LAUNCHER] Fallback to IBKR UI.")
        # Best effort fallback
        try:
           subprocess.run([sys.executable, "tools/candles_ibkr_ui.py"] + sys.argv[1:])
        except:
           pass

if __name__ == "__main__":
    main()
