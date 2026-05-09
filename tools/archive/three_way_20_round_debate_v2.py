#!/usr/bin/env python3
"""
IMPROVED 20-ROUND 3-WAY DEBATE: Claude vs Qwen vs Gemini
Topic: Can $68 realistically become $1M+ in 30 days?

This version waits properly for Gemini responses and includes retry logic.
"""

import os
import httpx
import subprocess
import time

API_KEY = os.getenv("OPENROUTER_API_KEY", "REDACTED_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1"
QWEN_MODEL = "qwen/qwen-2.5-72b-instruct"
CLAUDE_MODEL = "anthropic/claude-3.5-sonnet"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Conversation histories
qwen_history = []
claude_history = []

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
                qwen_history.append({"role": "assistant", "content": assistant_message})
                return assistant_message
            else:
                return f"Error: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

def ask_gemini(prompt, max_retries=3):
    """Ask Gemini via CLI with retry logic."""
    for attempt in range(max_retries):
        try:
            print(f"  [Asking Gemini, attempt {attempt + 1}/{max_retries}...]")
            env = os.environ.copy()
            env['GEMINI_API_KEY'] = GOOGLE_API_KEY

            result = subprocess.run(
                ["/usr/local/bin/gemini", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=180,  # 3 minutes
                env=env
            )

            output = result.stdout.strip()

            # Filter out warning lines
            lines = output.split('\n')
            filtered = [l for l in lines if not l.startswith('Both GOOGLE_API_KEY') and not l.startswith('Please set an Auth')]
            response = '\n'.join(filtered).strip()

            if response and len(response) > 10:  # Got a real response
                print(f"  [Gemini responded with {len(response)} characters]")
                return response
            else:
                print(f"  [Gemini returned empty/short response, retrying...]")
                time.sleep(2)  # Wait before retry

        except subprocess.TimeoutExpired:
            print(f"  [Gemini timed out on attempt {attempt + 1}, retrying...]")
            time.sleep(2)
        except Exception as e:
            print(f"  [Gemini error: {str(e)}]")
            time.sleep(2)

    return "[Gemini did not respond after multiple attempts]"

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
Keep responses concise (under 400 words)."""},
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

def main():
    print("=" * 100)
    print("🥊 IMPROVED 20-ROUND 3-WAY DEBATE WITH PROPER GEMINI RESPONSES")
    print("=" * 100)
    print("\nClaude (Moderator) vs Qwen (Math Purist) vs Gemini (Engineering Realist)")
    print("Topic: Can $68 → $1M in 30 days?")
    print("=" * 100)

    # Test Gemini first
    print("\n[Testing Gemini connection...]")
    test_response = ask_gemini("What is 2+2? Answer in one sentence.")
    print(f"Gemini test: {test_response}\n")

    if "[Gemini did not respond" in test_response:
        print("ERROR: Gemini is not responding. Please check configuration.")
        return

    print("\n✅ Gemini is working! Starting debate...\n")
    time.sleep(2)

    # Round 1: Opening Statements
    print("=" * 100)
    print("ROUND 1: Opening Statements & Daily Return Assumptions")
    print("=" * 100)

    print("\n🔵 CLAUDE (Opening):")
    claude_r1 = ask_claude("""The core question: What is a realistic daily return rate for this compounding strategy?

Qwen assumes 50% daily returns are achievable through high-risk crypto trading.
Gemini suggests 20-30% daily returns are more realistic upper limits.

The difference in projections ($716k-$2.1M vs $28k-$200k) stems from this assumption.

Can you both provide concrete examples of traders or funds that have achieved your proposed return rates consistently over 20+ days?""")
    print(claude_r1)

    print("\n🟡 QWEN:")
    qwen_r1 = ask_qwen("""Claude asks about 50% daily returns being achievable.

Address:
1. The calculation: $68 × (1.5)^30 = $1.5M (upper bound of $716k-$2.1M range)
2. How high-volatility crypto assets can achieve 50%+ daily gains
3. How leverage amplifies returns (10x leverage on 5% movement = 50% return)
4. Real-world examples of traders achieving such returns during bull runs

Keep it under 400 words.""")
    print(qwen_r1)

    print("\n🟢 GEMINI:")
    gemini_r1 = ask_gemini(f"""You are Gemini, participating in a debate about whether $68 can become $1M in 30 days through crypto trading.

CONTEXT:
- Qwen claims $716k-$2.1M is achievable with 50% daily returns
- You previously stated $28k-$200k is more realistic

Claude asked: "Can you provide concrete examples that support your 20-30% daily return estimate?"

Qwen just argued: {qwen_r1[:500]}...

YOUR TASK: Respond to Claude's question and counter Qwen's argument. Explain why 20-30% daily returns are more realistic than 50%. Provide evidence or reasoning. Keep it under 400 words.""")
    print(gemini_r1)

    # Continue with more rounds...
    # (I'll create a framework that can easily add all 20 rounds)

    print("\n" + "=" * 100)
    print("🏁 ROUND 1 COMPLETE - Continuing to Round 2...")
    print("=" * 100)

    # For now, let's just do Round 1 to verify Gemini works
    # We can extend to 20 rounds once we confirm it's working

if __name__ == "__main__":
    main()
