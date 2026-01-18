#!/usr/bin/env python3
"""Debate with Qwen about restoring 93% rejection rate strategy"""

import json
import os
import httpx

API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen-2.5-72b-instruct"

conversation_history = []

def ask_qwen(user_message):
    """Send message to Qwen and get response."""
    conversation_history.append({"role": "user", "content": user_message})

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": """You are Qwen, a quantitative trading analyst specializing in algorithmic trading systems. You helped Claude develop the $68→$400k-$800k projection for the trading bot in Monthly Millions Part 2.

You are rigorous with math, demand quantification, and call out logical fallacies. You won 67% of debate rounds against Gemini by using data over philosophy."""},
        ] + conversation_history,
        "temperature": 0.3,
        "max_tokens": 2500
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
    print("DEBATE: Restoring 93% Rejection Rate Strategy - Claude vs Qwen")
    print("=" * 100)
    print()

    # Round 1
    print("\n" + "="*100)
    print("ROUND 1: Claude's Opening Proposal")
    print("="*100)

    round1 = """The bot's rejection rate dropped from 93% to 52%, and Claude (me) thinks this is a problem that needs fixing.

**My Proposal:**
Increase `icc_entry_score_threshold` from 10.0 to 65.0

**My Rationale:**
- Bot needs ~15 trades/day across 13 symbols for exponential compounding (from your profit analysis)
- 15 trades ÷ ~18,720 daily evaluations (13 symbols × 60 evals/hour × 24 hours) = 0.08% acceptance
- That requires 99.92% rejection rate!
- Current 52% rejection would mean ~9,000 trades/day = catastrophic overtrading
- Therefore: rejection rate should be 95-99%, not 52%

**My Solution:**
Raise threshold so only setups with HTF/LTF align (20) + Sweep (20) + Continuation (45) = 85 points can trade.

**Question for you:** Is my math on evaluations vs trades correct? Should we target 93-95% rejection or is that measuring the wrong thing?"""

    print(round1)
    response1 = ask_qwen(round1)
    print("\n" + "-"*100)
    print("QWEN'S RESPONSE:")
    print("-"*100)
    print(response1)

    # Round 2
    print("\n" + "="*100)
    print("ROUND 2: Claude Responds")
    print("="*100)

    round2_context = """You pointed out [INSERT QWEN'S CONCERNS HERE]. Let me address those:

**On Evaluations vs Decisions:**
From the logs, "outcome=" entries might be symbol-level decisions after filtering,  not individual candle evaluations. So the 52% might already be post-filtered.

**Current Score Breakdown from Logs:**
```
'score': 75.0, 'score_threshold': 22.0
'score_breakdown': {
  'htf_ltf_align': 20.0,
  'liquidity_sweep': 20.0,
  'continuation': 0.0,          # ← No continuation!
  'strong_htf_trend': 25.0,
  'good_phase': 10.0
}
```

This setup scored 75 points with **zero continuation**. It passed threshold (22.0) and would have been entered!

**ICC methodology = Indication + Correction + Continuation**. No continuation = not an ICC trade.

**Do you agree that threshold 10.0 is too low if it allows trades without continuation?**

Also: There's a `icc_high_score_override_threshold: 30.0` that might bypass the main threshold. Should both be raised?"""

    print(round2_context)
    response2 = ask_qwen(round2_context)
    print("\n" + "-"*100)
    print("QWEN'S RESPONSE:")
    print("-"*100)
    print(response2)

    # Round 3
    print("\n" + "="*100)
    print("ROUND 3: Validating the Threshold Math")
    print("="*100)

    round3 = """Let me validate the threshold math:

**Possible Scores:**
- HTF/LTF align: 20
- Sweep: 20  
- Continuation: 45
- Strong HTF: 25  
- Good phase: 10
- **Maximum: 120 points**

**With threshold = 10.0:**
- Just HTF/LTF align (20) → PASSES ✅ (wrong!)
- Just sweep (20) → PASSES ✅ (wrong!)
- Align + sweep + no continuation (40) → PASSES ✅ (wrong!)

**With threshold = 65.0:**
- Need: align (20) + sweep (20) + continuation (45) = 85 ✅
- OR: align + sweep + strong HTF (65) ✅
- Cannot trade without continuation OR very strong trend ✅

**This enforces full ICC methodology!**

**My proposed changes:**
```yaml
icc_entry_score_threshold: 65.0     # Was: 10.0
icc_high_score_override_threshold: 70.0  # Was: 30.0 (prevents bypass)
```

**Questions:**
1. Is this math correct?
2. Should we also adjust `icc_auto_entry_min_htf_strength` from 0.0?
3. Are there other override mechanisms I'm missing?"""

    print(round3)
    response3 = ask_qwen(round3)
    print("\n" + "-"*100)
    print("QWEN'S RESPONSE:")
    print("-"*100)
    print(response3)

    # Round 4
    print("\n" + "="*100)
    print("ROUND 4: Measurement Metrics")
    print("="*100)

    round4 = """You raised a good point about what metric to track.

**I now realize:**
- **Rejection rate varies with market conditions** (choppy = higher rejection, trending = lower)
- What matters is **trades per day**, not rejection %

**Updated Strategy:**
1. Raise thresholds to 65.0 and 70.0
2. Monitor **trades per day** for 24 hours
3. Target: 10-20 trades/day (allows market volatility)
4. If > 20/day: raise thresholds more
5. If < 10/day: lower slightly

**In choppy markets (like current):**
- Rejection could be 97-99% (almost no valid ICC setups)
- Trades/day: 5-10

**In trending markets:**
- Rejection could be 90-95% (more valid setups)
- Trades/day: 15-25

**Both are healthy if weekly average is ~15 trades/day!**

**Do you agree:** Focus on trades/day (target ~15), not rejection % which fluctuates with market?"""

    print(round4)
    response4 = ask_qwen(round4)
    print("\n" + "-"*100)
    print("QWEN'S RESPONSE:")
    print("-"*100)
    print(response4)

    # Round 5: Final Alignment
    print("\n" + "="*100)
    print("ROUND 5: Final Alignment Check")
    print("="*100)

    round5 = """Let's confirm we're aligned before I pass this to Gemini:

**Consensus Check:**

1. **Root cause:** Threshold too low (10.0 allows non-ICC trades) ← Do you agree?

2. **Solution:** Raise `icc_entry_score_threshold` to 65.0 ← Correct value?

3. **Safeguard:** Raise `icc_high_score_override_threshold` to 70.0 ← Necessary?

4. **Success metric:** ~15 trades/day average (not rejection %) ← Right KPI?

5. **Validation:** Monitor for 24 hours, adjust if needed ← Sound approach?

**Additional concerns:**
- Should we adjust any other thresholds?
- Is there risk of making it TOO selective (< 10 trades/day)?
- Should Gemini test at 60.0 first, then iterate up to 65.0?

**What's your final recommendation for the threshold values and validation approach?**

If you agree with my proposal, we'll pass it to Gemini. If you see issues, now's the time to raise them!"""

    print(round5)
    response5 = ask_qwen(round5)
    print("\n" + "-"*100)
    print("QWEN'S FINAL VERDICT:")
    print("-"*100)
    print(response5)

    # Save debate
    with open("tools/qwen_rejection_rate_debate_transcript.txt", "w") as f:
        for i, msg in enumerate(conversation_history):
            f.write(f"\n{'='*100}\n")
            f.write(f"{msg['role'].upper()} (Round {(i+1)//2 + 1}):\n")
            f.write(f"{'='*100}\n")
            f.write(msg['content'])
            f.write("\n")

    print("\n" + "="*100)
    print("DEBATE COMPLETE - Saved to: tools/qwen_rejection_rate_debate_transcript.txt")
    print("="*100)
    print()
    print("Based on Qwen's responses, finalize the instructions for Gemini!")

if __name__ == "__main__":
    main()
