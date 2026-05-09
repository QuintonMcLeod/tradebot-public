#!/usr/bin/env python3
"""Test if Qwen Turbo knows ICC trading methodology."""

import json
import httpx

API_KEY = "REDACTED_API_KEY"
BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen-turbo"

def test_qwen_icc_knowledge():
    """Test Qwen's knowledge of ICC methodology."""

    # Test 1: Basic ICC knowledge
    print("=" * 80)
    print("TEST 1: Does Qwen know what ICC (Inner Circle Trader) is?")
    print("=" * 80)

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "What is the ICC trading methodology created by Michael Huddleston (The Inner Circle Trader)? Explain the TCC framework (Trend, Correction, Continuation) and how liquidity sweeps work."}
        ],
        "temperature": 0.2,
        "max_tokens": 600
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{BASE_URL}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                print(f"\nQwen's Response:\n{content}\n")

                # Check if response contains ICC-specific concepts
                icc_terms = ["liquidity", "sweep", "trend", "correction", "continuation", "ICT", "Inner Circle"]
                found_terms = [term for term in icc_terms if term.lower() in content.lower()]

                print(f"\nICC-related terms found: {found_terms}")
                print(f"Total terms matched: {len(found_terms)}/{len(icc_terms)}")

                if len(found_terms) >= 4:
                    print("\n✅ Qwen appears to have knowledge of ICC/ICT concepts!")
                else:
                    print("\n❌ Qwen's knowledge of ICC/ICT seems limited or generic.")
            else:
                print("Error: No response from model")
                print(json.dumps(data, indent=2))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Specific ICC terminology
    print("\n" + "=" * 80)
    print("TEST 2: Does Qwen understand specific ICC terms?")
    print("=" * 80)

    payload2 = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "In ICC trading, what is a 'liquidity sweep' and why is it important for identifying high-probability entries? What is the difference between an 'indication' and a 'continuation' in the TCC framework?"}
        ],
        "temperature": 0.2,
        "max_tokens": 500
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{BASE_URL}/chat/completions",
                json=payload2,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                print(f"\nQwen's Response:\n{content}\n")
            else:
                print("Error: No response from model")
                print(json.dumps(data, indent=2))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    # Test 3: Apply ICC rules to our backtest data
    print("\n" + "=" * 80)
    print("TEST 3: Apply ICC rules to our November 2024 backtest data")
    print("=" * 80)

    icc_context = (
        "We are backtesting SPY for 2024-11-11 to 2024-11-16 (week after election). "
        "We must avoid day trading and hold trades for at least 24 hours. "
        "Current signals are based on trend/sweep/continuation gates. "
        "Signal analysis (continuation-based, 24h hold) summary:\n"
        "- Total continuation signals: 181; wins: 61 (33.7%)\n"
        "- htf_strength >= 0.7: 15/75 (20.0%)\n"
        "- htf_strength < 0.7: 46/106 (43.4%)\n"
        "- phase=chop: 46/106 (43.4%)\n"
        "- phase=continuation: 15/75 (20.0%)\n"
        "- sweep=True: 6/15 (40.0%)\n"
        "- sweep=False + phase=chop: 40/91 (44.0%)\n"
        "ICC guidance from user: "
        "look for a big selloff/rally (indication), wait for correction, "
        "then enter on break of higher low/higher high; "
        "for shorts, enter on break of swing low. "
        "We need entries/exits that reflect this logic while still holding >=24h.\n"
    )

    payload3 = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": (
                    icc_context
                    + "\nGiven this data, propose concrete, programmable entry/exit rules "
                    "for ICC that would improve win rate without day trading. "
                    "Be specific about conditions (swing high/low logic, confirmation, "
                    "filters, and when to exit after >=24h)."
                ),
            }
        ],
        "temperature": 0.2,
        "max_tokens": 700,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{BASE_URL}/chat/completions",
                json=payload3,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                print(f"\nQwen's Response:\n{content}\n")
            else:
                print("Error: No response from model")
                print(json.dumps(data, indent=2))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_qwen_icc_knowledge()
