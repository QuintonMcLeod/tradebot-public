#!/usr/bin/env python3
"""Debate with Qwen about P&L reality on Spot vs Leverage - 10 round debate."""

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
            {"role": "system", "content": "You are a quantitative trading analyst with deep expertise in crypto market mechanics, fee structures, and position sizing execution. You are rigorously mathematical and do not accept theoretical abstractions that violate physical trading constraints (e.g. leverage availability). You are debating Claude about whether a specific strategy is viable on Coinbase Spot."},
        ] + conversation_history,
        "temperature": 0.3,
        "max_tokens": 1000
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
    print("DEBATE: Claude vs Qwen on Spot Trading Reality")
    print("=" * 100)
    print()

    # Round 1: The Trap
    round1 = """
I assert that the 'Monthly Millions' projection (turning $68 into $1M in 30 days via scalp trading) is MATHEMATICALLY IMPOSSIBLE on Coinbase Spot, regardless of 'Geometric Compounding'.

My argument rests on two physical constraints:
1. **The Leverage Constraint**: The strategy assumes risking 10% of equity per trade. On Spot, you cannot lose more than the price drop. To lose 10% of equity on a 1% stop loss requires 10x leverage. Coinbase Spot has 1x leverage. Therefore, maximum risk is 1% (or position size > account balance, which is impossible).
2. **The Fee Drag**: Coinbase Retail Spot fees are 0.6% Taker. A round trip is 1.2% + slippage (~1.4%). If the target is a 2% scalp, fees consume 70% of profit.

Do you agree that these two constraints mathematically destroy the 'Monthly Millions' thesis for a Spot account?
"""
    print("ROUND 1: Claude's Opening Argument (The Reality Check)")
    print(round1)
    response1 = ask_qwen(round1)
    print("\nQWEN'S RESPONSE:")
    print(response1)

    rounds = [
        # Round 2: Pushing the leverage point
        """
You acknowledge the leverage constraint, but let's be precise. 
If I have $68 and I buy $68 of DOGE (Max Spot Position), and price drops 1% to my stop loss:
- Loss = $0.68.
- Risk % = 1.0%.

The 'Monthly Millions' math relied on risking **10%** ($6.80) per trade to get 40% returns. 
On Spot, to risk $6.80 on a 1% drop, I would need a position size of $680. 
I only have $68. 

Therefore, my 'Risk of Ruin' is near zero, but my 'Growth Rate' is also capped at 1/10th of the projection. 
Does this single fact not reduce the 'Millions' to 'Maybe Hundreds'?
""",
        # Round 3: The Fee Purgatory
        """
Let's talk about the Fee Drag on Scalping.
You recommended 15 trades/day. That implies lower timeframes (15m/1h).
Typical volatility on 15m is ~1-2%.
Scenerio:
- Enter $68 position. Fee: $0.41 (0.6%)
- Price moves +2% (Great trade!). Value: $69.36.
- Exit position. Fee: $0.42 (0.6%).
- Slippage: $0.10.
- Net Profit: $69.36 - $68.00 - $0.41 - $0.42 - $0.10 = $0.43.

Gross Profit: $1.36 (2%).
Net Profit: $0.43 (0.63%).
**Effective Tax Rate: 68%.**

Is it mathematically viable to compound wealth when the 'House' takes 68% of every winning trade?
""",
        # Round 4: The Swing Trading Pivot
        """
So we agree: Scalping on Coinbase Spot is a donation to the exchange.
The ONLY way to save the 'Geometric Compounding' thesis is to reduce the impact of the 1.4% fixed cost.
This requires increasing the Target %.

If we switch to **Swing Trading** (Daily TF):
- Target: 20% move.
- Fee: 1.4%.
- Fee Impact: 7% of profit (Manageable).

However, Swing Trades take days/weeks, not hours.
This breaks the "15 trades per day" assumption.
If we do 1 trade every 3 days (0.33 trades/day) instead of 15, does the exponential curve still produce 'Millions' in a month?
(Hint: (1.2)^10 is much smaller than (1.02)^450).
""",
        # Round 5: The Psychological/Execution Barrier
        """
Let's look at the liquidity constraint again.
In the original debate, you argued $50k positions are small.
But on Coinbase *Retail* (Advanced Trade is distinct), order limits and spreads are worse.
More importantly, the 'Monthly Millions' assumes perfect execution of 450 consecutive trades without a single fat-finger, API outage, or emotional collapse.

If we apply a 'Real World Friction' coefficient (e.g., 20% of trades fail due to technical/human error), and combine it with the Spot constraints (1% risk cap), does the Expected Value (EV) turn negative?
""", 
        # Round 6: Re-evaluating the $1.50 Estimate
        """
Go back to the very first estimate I gave: '$1.50/day'.
On a $68 account, doing 15 scalps/day:
- 15 trades * $0.43 net profit (from Round 3) = $6.45/day.
- MINUS the losses (which also pay fees!).
- If Win Rate is 55%:
  - 8 Wins * $0.43 = +$3.44
  - 7 Losses * ($0.68 loss + $0.83 fees/slip) = -$10.57
  - Net Day: -$7.13.

Wait... on Spot Scalping with Fees, **Positive Win Rate (55%) leads to NEGATIVE expectancy?**
Please verify this calculation.
""",
        # Round 7: The Only Winning Move
        """
If Spot Scalping is -EV, and Swing Trading is too slow for 'Monthly Millions', is there ANY path for the user's current setup ($68 on Coinbase) to generate significnat wealth?
Or is the honest answer: "You must change venues (to DeFi/Offshore for leverage) or deposit more capital"?
""",
        # Round 8: The "Monthly Millions" Defanged
        """
So the "Monthly Millions" document was not just "Optimistic", it was **Categorically False** for the user's specific context (Spot/Coinbase).
It applied "Futures Math" to a "Spot Account".
Do you agree that we owe the user an apology for presenting a projection that violated the laws of physics (financial leverage constraints) of their account?
""",
        # Round 9: Constructive Path Forward
        """
Let's pivot to helpfulness.
If the user switches to **Aggressive Swing Trading** on Spot (Targeting volatile memes like BONK/WIF for 20-30% moves):
- Risk: 100% of Account (1 position).
- Target: +30%.
- Stop: -10% (Mental stop, since we can't leverage).
- Fees: Negligible.
- Freq: 1 trade every 2 days.

What does that projection look like for 30 days?
""",
        # Round 10: Final Verdict
        """
Summarize the debate mechanics for the user.
1. Why 'Monthly Millions' failed (Leverage/Fees).
2. Why Spot Scalping is suicide (-EV).
3. The realistic path (Swing Trading).
4. Final P&L Estimate for $68 Spot Account over 30 days using the Swing Strategy.
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
