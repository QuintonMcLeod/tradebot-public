#!/usr/bin/env python3
"""
QWEN VS GEMINI'S CRITIQUE
Qwen defends the $716k-$2.1M projection against Gemini's conservative $28k-$200k estimate
"""

import json
import os
import httpx

API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
BASE_URL = "https://openrouter.ai/api/v1"
QWEN_MODEL = "qwen/qwen-2.5-72b-instruct"

qwen_history = []

def ask_qwen(user_message):
    """Send message to Qwen via OpenRouter API."""
    qwen_history.append({"role": "user", "content": user_message})

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": """You are Qwen, a quantitative trading analyst.
You previously concluded with Claude that $68 can become $716k-$2.1M in 30 days through geometric compounding.

Now Gemini (another AI) has critiqued your analysis, saying:
"Don't bank on the million. Bank on the tens of thousands ($28k-$200k is more likely)."

Gemini's arguments:
1. Psychology: "Will you let the bot risk $50,000 when account hits $500k?"
2. Exchange friction: "Coinbase might pause account for manual review"
3. Slippage: "Worse than you modeled"
4. Variance: "One bad week and growth stalls"

Your job: Defend your position with math and data. Challenge vague claims. Demand quantification."""},
        ] + qwen_history,
        "temperature": 0.3,
        "max_tokens": 2500
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{BASE_URL}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

            if "choices" in result and len(result["choices"]) > 0:
                assistant_message = result["choices"][0]["message"]["content"]
                qwen_history.append({"role": "assistant", "content": assistant_message})
                return assistant_message
            else:
                return f"Error: Unexpected response format: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

def main():
    print("=" * 100)
    print("QWEN DEFENDS $716K-$2.1M PROJECTION AGAINST GEMINI'S CRITIQUE")
    print("=" * 100)
    print()

    # Round 1: Address psychology
    print("="*100)
    print("ROUND 1: The Psychology Argument")
    print("="*100)
    print("\nGEMINI'S CLAIM:")
    print('"Will you actually let the bot risk $50,000 on a single trade when account hits $500k?"')
    print()

    response1 = ask_qwen("""Gemini argues that psychology matters: "Will you let the bot risk $50,000 when account hits $500k?"

Counter this argument. Points to make:
1. Bot is automated - it doesn't ask permission
2. If human turns it off, that's human failure, not bot failure
3. Question was "can $68 become $1M?" not "will humans interfere?"
4. What's the mathematical impact of this supposed "psychology" on an AUTOMATED system?

Be sharp. Challenge the premise.""")

    print("QWEN'S RESPONSE:")
    print(response1)
    print()

    # Round 2: Exchange freezes
    print("="*100)
    print("ROUND 2: The Exchange Freeze Argument")
    print("="*100)
    print("\nGEMINI'S CLAIM:")
    print('"Coinbase might pause your account if you turn $68 into $100k in two weeks."')
    print()

    response2 = ask_qwen("""Gemini claims exchange freezes are likely.

Demand specifics:
1. What percentage of profitable accounts get frozen?
2. At what account size does this trigger?
3. How long does a review take?
4. If it's a 2-day delay at $100k, does that really prevent reaching $500k-$1M?

Show the math: If you get a 2-day freeze at day 12 when account is $91k, what's the impact on day 30 balance?""")

    print("QWEN'S RESPONSE:")
    print(response2)
    print()

    # Round 3: Slippage quantification
    print("="*100)
    print("ROUND 3: The Slippage Argument")
    print("="*100)
    print("\nGEMINI'S CLAIM:")
    print('"Slippage is worse than you modeled."')
    print()

    response3 = ask_qwen("""We modeled slippage as:
- <$10k: 0.1%
- $10k-$100k: 0.3%
- $100k-$1M: 0.5%
- >$1M: 1.0%+

Gemini says this is optimistic.

Challenge back:
1. What slippage percentage does Gemini estimate at $500k account?
2. What's the actual bid-ask spread on BTC/USD during volatile periods?
3. Show how even 2.0% slippage affects the daily multiplier.

Use actual market data if you have it.""")

    print("QWEN'S RESPONSE:")
    print(response3)
    print()

    # Round 4: Variance
    print("="*100)
    print("ROUND 4: The Variance Argument")
    print("="*100)
    print("\nGEMINI'S CLAIM:")
    print('"One bad week and growth stalls. You need luck to hit $1M."')
    print()

    response4 = ask_qwen("""We modeled 288 total trades (24 days × 12 trades/day) at 55% WR.

Variance distribution:
- 90th percentile: 175 wins (60.8% WR)
- 50th percentile: 158 wins (54.9% WR) ← EXPECTED
- 10th percentile: 141 wins (49.0% WR)

Even at 10th percentile, you're near breakeven WR.

Show the math:
1. At 10th percentile (unlucky), what's the final balance?
2. What's the probability of hitting <$50k (disaster scenario)?
3. Is Gemini confusing "could happen" with "will probably happen"?

Use binomial distribution or Monte Carlo logic.""")

    print("QWEN'S RESPONSE:")
    print(response4)
    print()

    # Round 5: Final probability distribution
    print("="*100)
    print("ROUND 5: Final Probability Distribution")
    print("="*100)
    print("\nGEMINI'S DISTRIBUTION:")
    print("  Disaster (<$50k): 10%")
    print("  Conservative ($50k-$300k): 40%")
    print("  Realistic ($300k-$700k): 35%")
    print("  Optimistic ($700k-$2M): 13%")
    print("  Perfect Storm (>$2M): 2%")
    print()

    response5 = ask_qwen("""Gemini's final distribution puts 50% probability on <$300k outcomes.

Give YOUR final distribution and defend it:

- Disaster (<$50k): ?%
- Conservative ($50k-$300k): ?%
- Realistic ($300k-$700k): ?%
- Optimistic ($700k-$2M): ?%
- Perfect Storm (>$2M): ?%

For each range, show:
1. What daily multiplier it implies
2. What went wrong/right to get there
3. Why your probability is justified

This is your final word. Make it count.""")

    print("QWEN'S FINAL DISTRIBUTION:")
    print(response5)
    print()

    print("="*100)
    print("DEBATE COMPLETE")
    print("="*100)
    print("\nQwen has defended the $716k-$2.1M projection.")
    print("Now we can update MONTHLY_MILLIONS_PART_2.md with this debate!\n")

if __name__ == "__main__":
    main()
