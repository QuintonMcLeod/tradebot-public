#!/usr/bin/env python3
"""Ask Qwen about realistic 24-hour P&L with 50% risk per trade."""

import json
import os
import httpx

API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen-2.5-72b-instruct"

def ask_qwen_pnl():
    print("=" * 80)
    print("Asking Qwen about 24-hour P&L potential with 50% risk trading...")
    print("=" * 80)

    prompt = """I'm running a crypto trading bot based on the "Trade by SCI" methodology with these parameters:

**Current Configuration:**
- Starting Capital: $68 USD (in USDT/USD on Coinbase)
- Risk Per Trade: **10% per entry** (Trade by SCI default aggressive mode: 3%, but testing at 10%)
- Pyramiding: Up to 5 entries max = 50% total cumulative risk on full pyramid
- Trading Strategy: ICC methodology (Indication, Continuation, Confirmation - Inner Circle Trader concepts)
- Market: 24/7 crypto spot trading (13 symbols: BTC, ETH, SOL, DOGE, XRP, ADA, LINK, etc.)
- Win Rate Assumption: 55% (based on ICC backtests)
- Reward:Risk Ratio: 1.22:1 average
- Trading Frequency: Targeting 10 trades per day
- Timeframes: 15m HTF, 5m LTF

**IMPORTANT CONTEXT - Trade by SCI Official Risk Settings:**
From the official Trade by SCI bot documentation:

**Default Aggressive Mode Settings:**
- `PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT=0.03` (**3% per trade**)
- `PROFILE_MAX_DAILY_LOSS_PCT=0.06` (6% daily loss cap)
- `PROFILE_MAX_EXPOSURE_PCT=0.40` (40% max total exposure)
- `PROFILE_MAX_CONSECUTIVE_LOSSES=2` (blocks after 2 losses)

**ICC Risk Methodology:**
> "The bot implements ICC's signature risk approach: **10% risk per entry with 0.5% tight stops**, which naturally creates leverage through position sizing."

**"50% Risk Pyramid" Explanation:**
- **NOT 50% per single trade** (that would violate their own 3% default)
- **YES pyramiding: 5 entries × 10% each = 50% total cumulative risk**
- Full pyramid only deploys on highest-conviction A+ continuation setups
- ICC continuations are "high-probability but lumpy" - long periods of nothing, then violent expansions
- The edge comes from **never missing A+ windows** and **never bleeding during chop**

**Trade by SCI's Official 1-Month Roadmap ($980 → $30k+):**
- Week 1: $980 → $2,450 (one clean 3:1 RR trend)
- Week 2: $2,450 → $6,125 (diversified continuation capture)
- Week 3: $6,125 → $15,300 (24/7 multi-asset scanning)
- Week 4: $15,300 → $38,200 (exponential moonshot on A+ setups)

**My Analysis Says (adapted for $68 start):**
- Expected 24-hour result: $180 (+164% gain)
- Best case (90th percentile): $500-600+
- Worst case (10th percentile): $20 (-71% loss)
- 1 week median: $3,240
- 1 month median: $194,400

**CRITICAL CORRECTION - Trade by SCI's Actual Risk Settings:**
You previously assessed 50% risk per trade as "extremely aggressive" and violating Kelly Criterion (optimal 14%).

But now you know:
- **Trade by SCI's default is 3% per trade** (within Kelly range!)
- The "10% per entry" is used with tight 0.5% stops (creating leverage through position sizing)
- The "50% pyramid" means 5 separate 10% entries, not one 50% all-in
- I'm testing at 10% per entry (3.3x their conservative 3% default)

**REVISED Questions:**
1. Does knowing Trade by SCI defaults to **3% per trade** change your assessment of the methodology's credibility?
2. Is **10% per entry with pyramiding** (my test config) still "extremely aggressive" or just "moderately aggressive"?
3. With proper ICC gates and 3% default risk, is the $980 → $30k roadmap more plausible?
4. What's a realistic 24-hour P&L expectation for $68 at:
   - 3% risk per trade (Trade by SCI default)
   - 10% risk per trade (my current test)
5. Given their 6% daily loss cap and 2-loss circuit breaker, what's the TRUE ruin probability?

Be mathematically rigorous. The methodology isn't reckless gambling - it has professional risk management built in."""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a quantitative trading analyst with deep expertise in risk management, position sizing, and Monte Carlo analysis. You understand Kelly Criterion, geometric vs arithmetic returns, and ruin probability. Be mathematically rigorous and honest about risks."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 2000
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    try:
        print("\nQuerying Qwen-2.5-72B-Instruct...\n")
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{BASE_URL}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                print("=" * 80)
                print("QWEN'S ASSESSMENT:")
                print("=" * 80)
                print(f"\n{content}\n")
                print("=" * 80)

                # Save to file
                with open("qwen_pnl_assessment.txt", "w") as f:
                    f.write(content)
                print("\n[Saved to: qwen_pnl_assessment.txt]")

            else:
                print("Error: No response from model")
                print(json.dumps(data, indent=2))

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    ask_qwen_pnl()
