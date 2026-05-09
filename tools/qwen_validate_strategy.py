#!/usr/bin/env python3
"""Ask Qwen to validate the rejection rate strategy - single comprehensive question"""

import json
import os
import httpx

API_KEY = os.getenv("OPENROUTER_API_KEY", "REDACTED_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen-2.5-72b-instruct"

def ask_qwen(message):
    """Single question to Qwen."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": """You are Qwen, a quantitative trading analyst. You helped Claude develop the $68→$400k-$800k projection for the trading bot. You are rigorous with math, demand quantification, and validate strategies based on data."""},
            {"role": "user", "content": message}
        ],
        "temperature": 0.3,
        "max_tokens": 3000
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
                return data["choices"][0]["message"]["content"]
            else:
                return f"Error: No response from model. Data: {json.dumps(data, indent=2)}"

    except Exception as e:
        return f"Error: {e}"

def main():
    print("=" * 100)
    print("QWEN VALIDATION: Rejection Rate Strategy (Single Comprehensive Ask)")
    print("=" * 100)
    print()

    question = """The trading bot's rejection rate dropped from 93% to 52%. I need your validation on my proposed fix.

**CONTEXT:**
- Bot needs ~15 trades/day across 13 symbols for the exponential compounding we calculated
- 15 trades ÷ 18,720 daily evaluations (13 symbols × 60 evals/hour × 24 hours) = 0.08% acceptance = 99.92% rejection needed
- Current 52% rejection would mean ~9,000 trades/day = catastrophic overtrading

**EVIDENCE FROM LOGS:**
```
'score': 75.0, 'score_threshold': 22.0
'score_breakdown': {
  'htf_ltf_align': 20.0,
  'liquidity_sweep': 20.0,
  'continuation': 0.0,          # ← NO CONTINUATION!
  'strong_htf_trend': 25.0,
  'good_phase': 10.0
}
```
This setup scored 75 points with ZERO continuation, passed threshold (22.0), and would be entered. But ICC methodology = Indication + Correction + Continuation. No continuation = not an ICC trade.

**CURRENT CONFIG:**
```yaml
icc_entry_score_threshold: 10.0
icc_high_score_override_threshold: 30.0
icc_auto_entry_min_htf_strength: 0.0
```

**MY PROPOSED FIX:**
```yaml
icc_entry_score_threshold: 65.0     # Was: 10.0
icc_high_score_override_threshold: 70.0  # Was: 30.0
# Possibly also: icc_auto_entry_min_htf_strength: 0.5 (from 0.0)
```

**RATIONALE:**
- Scoring: HTF/LTF align (20) + Sweep (20) + Continuation (45) + Strong HTF (25) + Good phase (10) = max 120
- With threshold 10.0: Just align (20) passes ❌
- With threshold 65.0: Need align+sweep+continuation (85) OR align+sweep+strong HTF (65) ✅
- This enforces full ICC methodology

**VALIDATION APPROACH:**
1. Start with threshold 60.0 (conservative test)
2. Monitor trades/day for 24 hours (NOT rejection %)
3. Target: 10-20 trades/day
4. If > 20/day: raise to 65.0
5. If < 10/day: lower to 55.0

**MY QUESTIONS FOR YOU:**
1. Is my math on 99.92% rejection correct?
2. Is threshold 65.0 the right value, or should it be higher/lower?
3. Should I also raise `icc_high_score_override_threshold` to 70.0 to prevent bypass?
4. Should I add `icc_auto_entry_min_htf_strength: 0.5` as additional protection?
5. Is "trades per day" the right success metric (vs rejection %)?
6. Is the gradual test approach (60.0 → 65.0) sound, or just go straight to 65.0?

**VALIDATE OR CRITIQUE:** 
Please provide your comprehensive assessment of this strategy. If you disagree with anything, explain why and provide the alternative calculation/threshold. If you agree, confirm the values I should pass to Gemini for implementation."""

    print("ASKING QWEN:")
    print("-" * 100)
    print(question)
    print()
    print("=" * 100)
    print("QWEN'S COMPREHENSIVE RESPONSE:")
    print("=" * 100)
    
    response = ask_qwen(question)
    print(response)
    
    # Save response
    with open("tools/qwen_validation_single_ask.txt", "w") as f:
        f.write("QUESTION:\n")
        f.write("=" * 100 + "\n")
        f.write(question)
        f.write("\n\n")
        f.write("QWEN'S RESPONSE:\n")
        f.write("=" * 100 + "\n")
        f.write(response)
    
    print()
    print("=" * 100)
    print("Saved to: tools/qwen_validation_single_ask.txt")
    print("=" * 100)

if __name__ == "__main__":
    main()
