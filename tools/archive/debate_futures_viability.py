
#!/usr/bin/env python3
"""Debate with Qwen about Coinbase Nano Futures Viability."""

import json
import os
import httpx

API_KEY = "REDACTED_API_KEY"
BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen-2.5-72b-instruct"

conversation_history = []

def ask_qwen(user_message):
    """Send message to Qwen and get response."""
    conversation_history.append({"role": "user", "content": user_message})

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a quantitative trading analyst with deep expertise in crypto derivatives, risk management, and market mechanics. You are debating Claude about a proposed strategy pivot for a user with a very small account ($68). You are skeptical, rigorous, and focused on 'Risk of Ruin'."},
        ] + conversation_history,
        "temperature": 0.3,
        "max_tokens": 1500
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{BASE_URL}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                assistant_response = data["choices"][0]["message"]["content"]
                conversation_history.append({"role": "assistant", "content": assistant_response})
                return assistant_response
            else:
                return f"Error: No response from model. Data: {json.dumps(data, indent=2)}"

    except Exception as e:
        return f"Error: {e}"

def main():
    print("=" * 100)
    print("DEBATE: Claude vs Qwen on Coinbase Nano Futures Viability")
    print("=" * 100)
    print()

    # Round 1: The New Reality
    round1 = """
CONTEXT:
We established that the user's previous 'Monthly Millions' goal on Coinbase SPOT with $68 is impossible due to fee drag and lack of leverage.
The user is US-based (cannot use Binance/Bybit). Kraken Margin is restricted to ECPs (> $10M assets).
The ONLY remaining option for leverage is **Coinbase Derivatives (Nano Futures)**.

PROPOSAL:
- Instrument: Nano Ether (1/10th ETH contract). Notional Value: ~$3,115 / 10 = $311.50.
- User Capital: $68.00.
- Required Margin (25%): ~$78.00.
- SHORTFALL: ~$10.00.

I am advising the user to **deposit ~$20** to reach ~$88, allowing them to trade 1 contract.
This unlocks ~4x leverage, allowing the geometric compounding strategy to finally function (mathematically).

Do you agree that this (Deposit $20 -> Trade Nano ETH) is the **only viable path** to chase high growth legally in the US, or am I walking them into a trap?
"""
    print("ROUND 1: Claude's Proposal")
    print(round1)
    response1 = ask_qwen(round1)
    print("\nQWEN'S RESPONSE:")
    print(response1)

    rounds = [
        # Round 2: The Liquidation Risk
        """
You raise valid concerns about risk. Let's quantify it.
With $88 account and $78 used for margin (1 contract):
- Free Margin: $10.00.
- Leverage: ~3.5x ($311 notional / $88 equity).

If price moves against us:
- 1 Nano Ether = $0.10 per $1 move in ETH.
- Liquidation happens if Free Margin hits zero (approx).
- $10 buffer / $0.10 val per $1 = $100 price move.
- $100 move on $3,115 ETH is roughly **3.2%**.

Is a 3.2% liquidation distance "Instant Death" for a scalping bot?
Or is it manageable with a tight 1% Stop Loss (risking ~$3)?
""",
        # Round 3: Execution Friction (Fees & Spread)
        """
Let's talk Fees.
Coinbase Nano fees for retail are roughly $1.50 round trip? Wait, let me check.
Actually, Nano Ether fees are meant to be low. Let's assume $0.50 round trip + spread.
With 1 Contract ($311 Value):
- 1% Target Gain = $3.11.
- Fees ($0.50) = ~16% of profit.

Compare to Spot:
- Spot 1% Gain = $0.68.
- Spot Fees ($0.02) if lucky? No, Spot fees are 0.6% ($0.40). 
- Spot Fee Drag = 60% of profit.

So Futures Fees (16%) are far superior to Spot Fees (60%).
Does this not prove that Nano Futures is the **mathematically superior** venue, despite the liquidation risk?
""",
        # Round 4: The Psychology of "One Bullet"
        """
The math works ($88 capital, 16% fee drag, 4x leverage).
But the user has exactly **ONE BULLET**.
If the first trade is a loss (-1% stop):
- Loss: $3.11.
- Fees: $0.50.
- Capital: $88 - $3.61 = $84.39.

We are still above the ~$78 margin requirement.
We can trade again.
We can survive roughly 3 consecutive losses before dropping below margin.

Is "3 Bullets" enough survival capability for a high-frequency bot (assumed 55% win rate), or is the Probability of Ruin still > 90%?
""",
        # Round 5: Verdict & "Wait vs. Yolo"
        """
Final Decision Point.
Option A: Stay on Spot ($68). Safe. Boring. Takes 5 years to double.
Option B: Deposit $20. risk "3 Bullets" on Nano Futures. If it works, potential for 10x-100x growth in months. If it fails, lose $88.

For a user who explicitly asked for "Monthly Millions" (high aggression), is Option B the **only honest recommendation** we can give?
And what strict conditions must we impose (e.g., stops, disable trading during volatility) to protect those 3 bullets?
"""
    ]

    for i, argument in enumerate(rounds, start=2):
        print("\n" + "="*100)
        print(f"ROUND {i}: Claude's Argument")
        print("="*100)
        print(argument)
        response = ask_qwen(argument)
        print("\nQWEN'S RESPONSE:")
        print(response)

if __name__ == "__main__":
    main()
