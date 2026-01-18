#!/usr/bin/env python3
"""List available products from Coinbase Exchange API."""

import httpx
import json

def list_products():
    url = "https://api.exchange.coinbase.com/products"
    headers = {"Accept": "application/json", "User-Agent": "TradeBot/1.0"}
    
    try:
        print(f"Fetching products from {url}...")
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            products = resp.json()
            
        print(f"Found {len(products)} total products.")
        
        # Filter for USDT and USD pairs
        usdt_pairs = []
        usd_pairs = []
        
        for p in products:
            if p["quote_currency"] == "USDT":
                usdt_pairs.append(p["base_currency"])
            elif p["quote_currency"] == "USD":
                usd_pairs.append(p["base_currency"])
                
        usdt_pairs = sorted(list(set(usdt_pairs)))
        usd_pairs = sorted(list(set(usd_pairs)))
        
        print("\n=== USDT Pairs (Available for trading) ===")
        print(", ".join(usdt_pairs))
        
        print("\n=== USD Pairs (Often mapped to USDT) ===")
        print(", ".join(usd_pairs[:50]) + "...") # Truncate to avoid spamming
        
    except Exception as e:
        print(f"Error fetching products: {e}")

if __name__ == "__main__":
    list_products()
