#!/usr/bin/env python3
"""Ask Qwen about max_concurrent_positions setting"""

import json
import os
import httpx

API_KEY = os.getenv("OPENROUTER_API_KEY", "REDACTED_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen-2.5-72b-instruct"

def ask_qwen(message):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are Qwen, a quantitative trading analyst who helped develop the $68→$400k-$800k projection."},
            {"role": "user", "content": message}
        ],
        "temperature": 0.3,
        "max_tokens": 2000
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{BASE_URL}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            else:
                return f"Error: {data}"
    except Exception as e:
        return f"Error: {e}"

def main():
    question = """The trading bot has `max_concurrent_positions: 5` configured, meaning it can hold up to 5 positions simultaneously across 13 crypto symbols.

**Context from our profit analysis:**
- Bot needs ~15 trades/day for exponential compounding
- 10% risk per trade
- Target: $68 → $400k-$800k in 30 days

**Current config:**
```yaml
max_concurrent_positions: 5
aggressive_risk_per_trade_pct: 0.10  # 10% per trade
```

**Question:** Is holding 5 concurrent positions at 10% risk each (= 50% total capital at risk) appropriate for this strategy?

**Alternative options:**
1. Keep 5 positions (current)
2. Reduce to 3 positions (30% max exposure)
3. Increase to 7 positions (70% max exposure)

Given the high-frequency trading (15 trades/day) and the need for capital compounding, what's your recommendation for max_concurrent_positions?"""

    print("=" * 100)
    print("ASKING QWEN ABOUT MAX CONCURRENT POSITIONS")
    print("=" * 100)
    print()
    print(question)
    print()
    print("=" * 100)
    print("QWEN'S RESPONSE:")
    print("=" * 100)
    
    response = ask_qwen(question)
    print(response)
    
    with open("tools/qwen_max_positions_response.txt", "w") as f:
        f.write("QUESTION:\n")
        f.write("=" * 100 + "\n")
        f.write(question)
        f.write("\n\nQWEN'S RESPONSE:\n")
        f.write("=" * 100 + "\n")
        f.write(response)
    
    print()
    print("=" * 100)
    print("Saved to: tools/qwen_max_positions_response.txt")

if __name__ == "__main__":
    main()
