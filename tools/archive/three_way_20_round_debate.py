#!/usr/bin/env python3
"""
REAL 20-ROUND 3-WAY DEBATE: Claude vs Qwen vs Gemini
Topic: Can $68 realistically become $1M+ in 30 days?

ALL THREE AIs participate and respond to each other.
"""

import os
import httpx
import subprocess

API_KEY = os.getenv("OPENROUTER_API_KEY", "REDACTED_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1"
QWEN_MODEL = "qwen/qwen-2.5-72b-instruct"
CLAUDE_MODEL = "anthropic/claude-3.5-sonnet"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Conversation histories
qwen_history = []
claude_history = []
debate_log = []  # Full debate transcript for all participants to see

def ask_qwen(prompt, context=""):
    """Ask Qwen with full debate context."""
    full_prompt = f"{context}\n\n{prompt}" if context else prompt
    qwen_history.append({"role": "user", "content": full_prompt})

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": """You are Qwen, a quantitative trading analyst.
You value mathematical rigor and believe in following the math wherever it leads.
You previously calculated with Claude that $68 can become $716k-$2.1M in 30 days.
Now Gemini challenges this, claiming $28k-$200k is more realistic.
Defend your position with calculations. Challenge vague claims. Demand data."""},
        ] + qwen_history,
        "temperature": 0.3,
        "max_tokens": 400
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
                return f"Error: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

def ask_gemini(prompt):
    """Ask Gemini via CLI."""
    try:
        env = os.environ.copy()
        env['GEMINI_API_KEY'] = GOOGLE_API_KEY

        result = subprocess.run(
            ["/usr/local/bin/gemini", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            env=env
        )

        output = result.stdout.strip()
        lines = output.split('\n')
        filtered = [l for l in lines if not l.startswith('Both GOOGLE_API_KEY')]
        return '\n'.join(filtered).strip()
    except subprocess.TimeoutExpired:
        return "Error: Gemini timed out"
    except Exception as e:
        return f"Error: {str(e)}"

def ask_claude(prompt, context=""):
    """Ask Claude (via OpenRouter) with full debate context."""
    full_prompt = f"{context}\n\n{prompt}" if context else prompt
    claude_history.append({"role": "user", "content": full_prompt})

    payload = {
        "model": CLAUDE_MODEL,
        "messages": [
            {"role": "system", "content": """You are Claude, an AI moderator in this debate.
You started skeptical of the $68 → $1M projection but were convinced by Qwen's math.
Now Gemini challenges this. Your job: moderate, ask tough questions, and synthesize perspectives.
Keep responses concise (under 300 words)."""},
        ] + claude_history,
        "temperature": 0.7,
        "max_tokens": 400
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
                claude_history.append({"role": "assistant", "content": assistant_message})
                return assistant_message
            else:
                return f"Error: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

def get_debate_context():
    """Get recent debate history for context."""
    if len(debate_log) <= 3:
        return "\n\n".join(debate_log)
    else:
        return "\n\n".join(debate_log[-3:])  # Last 3 exchanges

def main():
    print("=" * 100)
    print("🥊 REAL 20-ROUND 3-WAY DEBATE")
    print("=" * 100)
    print("\nClaude (Moderator) vs Qwen (Math Purist) vs Gemini (Engineering Realist)")
    print("Topic: Can $68 → $1M in 30 days?")
    print("=" * 100)

    # Round 1: Opening statements
    print("\n" + "="*100)
    print("ROUND 1: Opening Statements")
    print("="*100)

    print("\n🔵 CLAUDE (Opening):")
    claude_1 = ask_claude("We're debating whether $68 can realistically become $1M in 30 days. Qwen says yes ($716k-$2.1M). Gemini says no ($28k-$200k more likely). State the core question we need to resolve.")
    print(claude_1)
    debate_log.append(f"CLAUDE: {claude_1}")

    print("\n🟡 QWEN:")
    context = get_debate_context()
    qwen_1 = ask_qwen("Give your opening position. Why do you believe $716k-$2.1M is realistic? Be specific about the math. Under 250 words.", context)
    print(qwen_1)
    debate_log.append(f"QWEN: {qwen_1}")

    print("\n🟢 GEMINI:")
    context = get_debate_context()
    gemini_prompt = f"""You are Gemini, Google's AI. You're in a debate about whether $68 can become $1M in 30 days through trading.

Context so far:
{context}

Give your opening position. Why do you believe $28k-$200k is more realistic than $716k-$2.1M? Focus on practical constraints. Under 250 words."""
    gemini_1 = ask_gemini(gemini_prompt)
    print(gemini_1)
    debate_log.append(f"GEMINI: {gemini_1}")

    # Rounds 2-19: Back and forth on specific topics
    topics = [
        ("Psychology & Automation", "Does human psychology matter for an automated bot?"),
        ("Exchange Friction", "Will Coinbase freeze accounts with rapid growth?"),
        ("Slippage Reality", "What's realistic slippage at $100k-$500k account sizes?"),
        ("Liquidity Constraints", "At what account size does liquidity become a problem?"),
        ("Variance & Risk", "How does variance affect the probability distribution?"),
        ("Historical Precedent", "Does lack of documented cases matter?"),
        ("Circuit Breakers", "Do safety mechanisms change the risk profile?"),
        ("Win Rate Assumptions", "Is 55% WR sustainable?"),
        ("Risk:Reward Ratio", "Is 1:2.5 R:R realistic or optimistic?"),
        ("Market Conditions", "How volatile does the market need to be?"),
        ("Compounding Effects", "Does geometric growth truly scale?"),
        ("Fees & Costs", "Hidden costs that weren't modeled?"),
        ("Time Constraints", "Can you really execute 12-15 trades/day?"),
        ("Position Sizing", "Is 10% risk per trade too aggressive?"),
        ("Market Impact", "At what size do your orders move the market?"),
        ("Probability Math", "Let's calculate actual probabilities"),
        ("Worst Case Scenarios", "What's the disaster probability?"),
        ("Best Case Scenarios", "What's required for $2M+?")
    ]

    for round_num, (topic, question) in enumerate(topics, start=2):
        print("\n" + "="*100)
        print(f"ROUND {round_num}: {topic}")
        print("="*100)

        # Claude poses the question
        print("\n🔵 CLAUDE:")
        context = get_debate_context()
        claude_q = ask_claude(f"Ask a tough question about: {question}. Under 150 words.", context)
        print(claude_q)
        debate_log.append(f"CLAUDE: {claude_q}")

        # Qwen responds
        print("\n🟡 QWEN:")
        context = get_debate_context()
        qwen_r = ask_qwen("Respond to Claude's question with calculations and data. Under 250 words.", context)
        print(qwen_r)
        debate_log.append(f"QWEN: {qwen_r}")

        # Gemini responds
        print("\n🟢 GEMINI:")
        context = get_debate_context()
        gemini_prompt = f"""You are Gemini in an AI debate.

Recent context:
{context}

Respond to the current question with your engineering/practical perspective. Under 250 words."""
        gemini_r = ask_gemini(gemini_prompt)
        print(gemini_r)
        debate_log.append(f"GEMINI: {gemini_r}")

        if round_num >= 20:
            break

    # Round 20: Final verdicts
    print("\n" + "="*100)
    print("ROUND 20: FINAL VERDICTS")
    print("="*100)

    print("\n🔵 CLAUDE:")
    context = get_debate_context()
    claude_final = ask_claude("After 19 rounds, what's your final probability distribution? Under 250 words.", context)
    print(claude_final)

    print("\n🟡 QWEN:")
    context = get_debate_context()
    qwen_final = ask_qwen("Give your final probability distribution. Justify each range. Under 250 words.", context)
    print(qwen_final)

    print("\n🟢 GEMINI:")
    context = get_debate_context()
    gemini_prompt = f"""After 19 rounds of debate:

Context:
{context}

Give your FINAL probability distribution for 30-day outcomes. Under 250 words."""
    gemini_final = ask_gemini(gemini_prompt)
    print(gemini_final)

    print("\n" + "="*100)
    print("🏁 20-ROUND DEBATE COMPLETE")
    print("="*100)

if __name__ == "__main__":
    main()
