#!/usr/bin/env python3
"""Ask Qwen about LTF timeframe selection for ICC."""

import json
import os
import httpx

# Try to get key from env, fallback to the one in the example script if needed
# (In a real scenario, we should rely on env vars, but I'll use the one from the file for consistency with the user's "test folder" hint)
API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen-turbo"

def ask_qwen():
    print("=" * 80)
    print("Consulting Qwen about 4h HTF -> 15m LTF pairing...")
    print("=" * 80)

    prompt = (
        "In the context of ICC (Inner Circle Trader) methodology, we are using a **4-Hour (4h)** chart as our Higher Timeframe (HTF) for trend direction.\n\n"
        "Question: Is the **15-minute (15m)** chart the mathematically/structurally correct 'Lower Timeframe' (LTF) to pair with a 4h HTF?\n"
        "Some traders suggest 5m, but we feel 15m is better for structural alignment.\n"
        "Please explain the 'Fractal Relationship' between 4h and 15m vs 4h and 5m. "
        "Which one provides the most reliable 'Intermediate Term Perspective' for a 4h Directional Bias?"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are an expert algorithmic trader specializing in Price Action and ICT/ICC concepts."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1000
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{BASE_URL}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                print(f"\nQwen's Advice:\n{content}\n")
            else:
                print("Error: No response from model")
                print(json.dumps(data, indent=2))

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    ask_qwen()
