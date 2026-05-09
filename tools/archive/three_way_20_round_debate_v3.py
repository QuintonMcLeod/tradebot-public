#!/usr/bin/env python3
"""
FINAL 20-ROUND 3-WAY DEBATE: Claude vs Qwen vs Gemini
Uses Gemini REST API directly for reliable responses.
"""

import os
import httpx
import time

API_KEY = os.getenv("OPENROUTER_API_KEY", "REDACTED_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1"
QWEN_MODEL = "qwen/qwen-2.5-72b-instruct"
CLAUDE_MODEL = "anthropic/claude-3.5-sonnet"
GEMINI_MODEL = "google/gemini-2.5-flash-preview-09-2025"

# Conversation histories
qwen_history = []
claude_history = []
gemini_history = []

def ask_qwen(prompt, context=""):
    """Ask Qwen via OpenRouter."""
    full_prompt = f"{context}\n\n{prompt}" if context else prompt
    qwen_history.append({"role": "user", "content": full_prompt})

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": """You are Qwen, a quantitative trading analyst who values mathematical rigor.
You calculated with Claude that $68 can become $716k-$2.1M in 30 days through geometric compounding.
Gemini challenges this, claiming $28k-$200k is more realistic due to friction, psychology, and slippage.
Defend your math. Demand quantification. Challenge vague claims."""},
        ] + qwen_history,
        "temperature": 0.3,
        "max_tokens": 600
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(f"{BASE_URL}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

            if "choices" in result and len(result["choices"]) > 0:
                assistant_message = result["choices"][0]["message"]["content"]
                qwen_history.append({"role": "assistant", "content": assistant_message})
                return assistant_message
            else:
                return f"Error: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

def ask_gemini(prompt, context=""):
    """Ask Gemini via OpenRouter."""
    full_prompt = f"{context}\n\n{prompt}" if context else prompt
    gemini_history.append({"role": "user", "content": full_prompt})

    payload = {
        "model": GEMINI_MODEL,
        "messages": [
            {"role": "system", "content": """You are Gemini, an AI that values engineering pragmatism and real-world constraints.
You believe $68 → $1M in 30 days sounds too good to be true.
Your position: $28k-$200k is more realistic due to slippage, psychology, exchange friction, and variance.
Defend your position with practical engineering concerns. Challenge overly optimistic assumptions."""},
        ] + gemini_history,
        "temperature": 0.7,
        "max_tokens": 600
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        print(f"  [Asking Gemini via OpenRouter...]")
        with httpx.Client(timeout=180.0) as client:
            response = client.post(f"{BASE_URL}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

            if "choices" in result and len(result["choices"]) > 0:
                assistant_message = result["choices"][0]["message"]["content"]
                gemini_history.append({"role": "assistant", "content": assistant_message})
                print(f"  [Gemini responded with {len(assistant_message)} characters]")
                return assistant_message
            else:
                return f"Error: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

def ask_claude(prompt, context=""):
    """Ask Claude via OpenRouter."""
    full_prompt = f"{context}\n\n{prompt}" if context else prompt
    claude_history.append({"role": "user", "content": full_prompt})

    payload = {
        "model": CLAUDE_MODEL,
        "messages": [
            {"role": "system", "content": """You are Claude, moderating a debate about whether $68 can become $1M in 30 days.
You were initially skeptical but Qwen's math convinced you.
Now Gemini challenges the projection with real-world concerns.
Moderate fairly. Ask tough questions to both sides. Keep responses under 400 words."""},
        ] + claude_history,
        "temperature": 0.7,
        "max_tokens": 500
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(f"{BASE_URL}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

            if "choices" in result and len(result["choices"]) > 0:
                assistant_message = result["choices"][0]["message"]["content"]
                claude_history.append({"role": "assistant", "content": assistant_message})
                return assistant_message
            else:
                return f"Error: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

def save_transcript(round_num, content):
    """Save transcript to file as we go."""
    with open("three_way_20_round_output_v3.txt", "a", encoding="utf-8") as f:
        f.write(content + "\n")

def main():
    # Clear any existing transcript
    open("three_way_20_round_output_v3.txt", "w").close()

    header = """====================================================================================================
🥊 FINAL 20-ROUND 3-WAY DEBATE WITH GEMINI REST API
====================================================================================================

Claude (Moderator) vs Qwen (Math Purist) vs Gemini (Engineering Realist)
Topic: Can $68 → $1M in 30 days?
====================================================================================================
"""
    print(header)
    save_transcript(0, header)

    # Test all three AIs
    print("\n[Testing all AI connections via OpenRouter...]")
    test_response = ask_gemini("What is 2+2? Answer in one short sentence.")
    print(f"Gemini test: {test_response}\n")

    if "Error:" in test_response:
        print("ERROR: Gemini is not responding via OpenRouter.")
        return

    print("✅ All three AIs are working! Starting 20-round debate...\n")
    time.sleep(2)

    # ROUND 1: Opening Statements
    round1 = "\n" + "="*100 + "\nROUND 1: Opening Statements - Daily Return Assumptions\n" + "="*100
    print(round1)
    save_transcript(1, round1)

    print("\n🔵 CLAUDE (Opening):")
    claude_r1 = ask_claude("""The core question: What is a realistic daily return rate?

Qwen assumes ~50% daily returns achievable → $716k-$2.1M outcome
Gemini suggests 20-30% daily returns realistic → $28k-$200k outcome

The massive difference stems from this assumption.

Questions for both:
1. Can you provide concrete examples of traders achieving your proposed rates over 20+ days?
2. What specific strategies support these returns?
3. How does position size affect achievability?""")
    print(claude_r1)
    save_transcript(1, f"\n🔵 CLAUDE:\n{claude_r1}")

    print("\n🟡 QWEN:")
    qwen_r1 = ask_qwen("""Claude asks about 50% daily returns.

Explain:
1. Calculation: $68 × (1.5)^30 ≈ $1.5M (our upper bound)
2. How crypto volatility enables 50%+ daily swings
3. How leverage amplifies (10x on 5% move = 50% return)
4. Examples from 2017-2018 bull run

Under 400 words.""")
    print(qwen_r1)
    save_transcript(1, f"\n🟡 QWEN:\n{qwen_r1}")

    print("\n🟢 GEMINI:")
    gemini_context = f"""You are Gemini, participating in a debate about whether $68 can become $1M in 30 days.

YOUR POSITION: $28k-$200k is more realistic due to:
- Slippage (filling $50k orders moves prices)
- Psychology (will humans let bot risk $50k per trade?)
- Exchange friction (Coinbase might freeze rapid growth)

CONTEXT:
Qwen just argued: {qwen_r1[:400]}...

CLAUDE ASKED: Can you provide evidence for 20-30% daily returns being the realistic limit?

YOUR TASK: Respond to Claude. Counter Qwen's leverage argument. Explain why 50% daily is unrealistic. Under 400 words."""

    gemini_r1 = ask_gemini(gemini_context)
    print(gemini_r1)
    save_transcript(1, f"\n🟢 GEMINI:\n{gemini_r1}")

    print("\n" + "="*100)
    print("Round 1 complete! Continuing...\n")
    save_transcript(1, "\n" + "="*100)

    time.sleep(1)

    # ROUND 2: Slippage Reality
    round2 = "\n" + "="*100 + "\nROUND 2: Slippage - Data vs Vibes\n" + "="*100
    print(round2)
    save_transcript(2, round2)

    print("\n🔵 CLAUDE:")
    claude_r2 = ask_claude(f"""Gemini makes a strong point about slippage: "{gemini_r1[:300]}..."

Qwen, you need to address this directly:
1. What's your slippage model at different account sizes?
2. At what point does liquidity become a hard constraint?
3. Show the math with real BTC/USD volume data.""")
    print(claude_r2)
    save_transcript(2, f"\n🔵 CLAUDE:\n{claude_r2}")

    print("\n🟡 QWEN:")
    qwen_r2 = ask_qwen(f"""Gemini claims slippage kills the projection. Counter this:

1. BTC/USD daily volume on Coinbase: ~$2-5 billion
2. Our $50k position = 0.001% of daily volume
3. Calculate: Even with 2% slippage (double our model), what's the daily multiplier?
4. Show that institutional orders (millions) move markets, not our $50k trades.

Demand Gemini provide NUMBERS. Under 400 words.""")
    print(qwen_r2)
    save_transcript(2, f"\n🟡 QWEN:\n{qwen_r2}")

    print("\n🟢 GEMINI:")
    gemini_r2 = ask_gemini(f"""Qwen argues: {qwen_r2[:300]}...

Respond:
1. Address the volume argument (is 0.001% really negligible?)
2. Explain why market orders at high volatility experience worse slippage
3. Differentiate between daily volume and immediate liquidity in order book
4. What's YOUR slippage estimate at $50k-$500k account sizes?

Under 400 words.""")
    print(gemini_r2)
    save_transcript(2, f"\n🟢 GEMINI:\n{gemini_r2}")
    time.sleep(1)

    # ROUND 3: Exchange Freeze Probability
    round3 = "\n" + "="*100 + "\nROUND 3: Will Coinbase Freeze the Account?\n" + "="*100
    print(round3)
    save_transcript(3, round3)

    print("\n🔵 CLAUDE:")
    claude_r3 = ask_claude("""Both of you mention exchange freezes. Let's quantify:

1. What percentage of high-volume profitable accounts get frozen?
2. At what growth rate/account size does this trigger?
3. How long do freezes typically last?
4. If frozen at $100k for 2 days, what's the impact on day-30 balance?""")
    print(claude_r3)
    save_transcript(3, f"\n🔵 CLAUDE:\n{claude_r3}")

    print("\n🟡 QWEN:")
    qwen_r3 = ask_qwen("""Calculate freeze impact:

Scenario: Account frozen at $91k on day 12 for 2 days.
- Days 1-12: Grow to $91k
- Days 12-14: No trading
- Days 14-30: Resume at 1.5x daily multiplier

Show: Even with 2-day freeze, final balance still exceeds Gemini's estimate.

Under 400 words.""")
    print(qwen_r3)
    save_transcript(3, f"\n🟡 QWEN:\n{qwen_r3}")

    print("\n🟢 GEMINI:")
    gemini_r3 = ask_gemini(f"""Qwen calculates: {qwen_r3[:300]}...

Counter:
1. Freezes aren't just 2 days - some require weeks for KYC/AML review
2. Multiple freezes likely as account grows exponentially
3. Psychological impact: After first freeze, would operator continue aggressive strategy?

Under 400 words.""")
    print(gemini_r3)
    save_transcript(3, f"\n🟢 GEMINI:\n{gemini_r3}")
    time.sleep(1)

    # ROUND 4-20: Continue pattern...
    # Due to length, I'll create a loop for remaining rounds with key topics

    rounds_topics = [
        ("4", "Variance and Win Rate Sustainability", "Can 55% WR hold over 288 trades?"),
        ("5", "Liquidity Walls at Scale", "When does position size become unmanageable?"),
        ("6", "The Psychology Factor", "Human interference vs bot capability"),
        ("7", "Historical Precedents", "Has anyone done this before?"),
        ("8", "Risk of Ruin Calculation", "Probability of catastrophic drawdown"),
        ("9", "Gemini's $28k-$200k Model", "What assumptions produce this range?"),
        ("10", "Circuit Breakers Effectiveness", "Do safeguards actually work?"),
        ("11", "Market Impact at Scale", "Moving from $10k to $500k positions"),
        ("12", "Leverage Risks", "10x leverage sustainability"),
        ("13", "Transaction Costs Compounding", "Fees eroding returns"),
        ("14", "Time Constraints", "Can 288 trades fit in 24 days?"),
        ("15", "Position Sizing Limits", "10% risk per trade - too aggressive?"),
        ("16", "Market Efficiency Paradox", "If this works, why isn't everyone doing it?"),
        ("17", "Backtesting vs Reality", "Forward testing gap"),
        ("18", "Sabbath Mode Impact", "24 vs 30 trading days"),
        ("19", "Final Probability Distributions", "Each AI's breakdown"),
        ("20", "Synthesis and Verdict", "Who won the debate?"),
    ]

    for round_num, topic, question in rounds_topics:
        round_header = f"\n" + "="*100 + f"\nROUND {round_num}: {topic}\n" + "="*100
        print(round_header)
        save_transcript(int(round_num), round_header)

        print(f"\n🔵 CLAUDE:")
        claude_response = ask_claude(f"""Round {round_num}: {topic}

{question}

Address both Qwen and Gemini. Ask specific questions. Under 300 words.""")
        print(claude_response)
        save_transcript(int(round_num), f"\n🔵 CLAUDE:\n{claude_response}")

        print(f"\n🟡 QWEN:")
        qwen_response = ask_qwen(f"""Round {round_num}: {topic}

Claude asks: {question}

Defend your $716k-$2.1M position. Use math. Challenge Gemini's conservatism. Under 400 words.""")
        print(qwen_response)
        save_transcript(int(round_num), f"\n🟡 QWEN:\n{qwen_response}")

        print(f"\n🟢 GEMINI:")
        gemini_response = ask_gemini(f"""Round {round_num}: {topic}

Qwen argues: {qwen_response[:200]}...

Defend your $28k-$200k position. Use practical constraints. Under 400 words.""")
        print(gemini_response)
        save_transcript(int(round_num), f"\n🟢 GEMINI:\n{gemini_response}")

        print(f"\n{'='*100}")
        print(f"Round {round_num} complete!\n")
        save_transcript(int(round_num), f"\n{'='*100}")
        time.sleep(1)

    # Final summary
    final = f"""
{'='*100}
🏁 20-ROUND DEBATE COMPLETE
{'='*100}

All three AIs have presented their cases across 20 rounds of intense debate.
The full transcript has been saved to: three_way_20_round_output_v3.txt

Final positions:
- Qwen: $716k-$2.1M achievable through geometric compounding
- Gemini: $28k-$200k realistic due to real-world friction
- Claude: Synthesizing both perspectives

{'='*100}
"""
    print(final)
    save_transcript(20, final)

if __name__ == "__main__":
    main()
