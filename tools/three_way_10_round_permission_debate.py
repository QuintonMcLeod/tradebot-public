#!/usr/bin/env python3
"""
10-round debate: Claude vs Qwen vs Gemini on Coinbase Futures PERMISSION_DENIED.
Uses OpenRouter for all three models.
"""

import os
import time
import httpx

API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    "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",
)
BASE_URL = "https://openrouter.ai/api/v1"
QWEN_MODEL = "qwen/qwen-2.5-72b-instruct"
CLAUDE_MODEL = "anthropic/claude-3.5-sonnet"
GEMINI_MODEL = "google/gemini-2.5-flash-preview-09-2025"

OUTPUT_FILE = "three_way_10_round_permission_debate_output.txt"

qwen_history = []
claude_history = []
gemini_history = []


def ask_model(model, history, system_prompt, user_prompt, max_tokens=600, temperature=0.6):
    history.append({"role": "user", "content": user_prompt})
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + history,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    with httpx.Client(timeout=180.0) as client:
        response = client.post(f"{BASE_URL}/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]["content"]
        history.append({"role": "assistant", "content": message})
        return message


def save_block(text):
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def main():
    open(OUTPUT_FILE, "w").close()

    header = """====================================================================================================
10-ROUND 3-WAY DEBATE: Coinbase Futures PERMISSION_DENIED
====================================================================================================
Claude (Moderator) vs Qwen (Quant Analyst) vs Gemini (Engineering Pragmatist)
Goal: Identify root cause(s), propose fixes, and prioritize verification steps.
====================================================================================================
"""
    print(header)
    save_block(header)

    base_context = (
        "Context: The bot attempts Coinbase futures trades and receives "
        "PERMISSION_DENIED. API keys show trade permissions enabled in the UI. "
        "The bot can fetch futures market data but cannot place futures orders. "
        "Logs show PERMISSION_DENIED during entry attempts. "
        "We need actionable, testable fixes."
    )
    extra_context = os.getenv("EXTRA_CONTEXT", "").strip()
    context = f"{base_context}\n\nAdditional context: {extra_context}" if extra_context else base_context

    claude_system = (
        "You are Claude, a fair moderator who forces precision. "
        "Ask for exact checks, prioritize falsifiable hypotheses, and keep responses short."
    )
    qwen_system = (
        "You are Qwen, a quantitative trading analyst. "
        "You demand evidence and propose concrete validation steps. "
        "Keep responses under 250 words."
    )
    gemini_system = (
        "You are Gemini, an engineering pragmatist. "
        "You focus on API permissions, account eligibility, and integration pitfalls. "
        "Keep responses under 250 words."
    )

    rounds = [
        "Round 1: List the top 5 likely causes for PERMISSION_DENIED in Coinbase futures, "
        "given that API keys show trade permission and market data is accessible.",
        "Round 2: Explain how portfolio scoping or account selection could cause PERMISSION_DENIED, "
        "and how to verify portfolio alignment.",
        "Round 3: Address onboarding/suitability requirements for Coinbase futures. "
        "What exact UI steps or account flags should be verified?",
        "Round 4: Clarify 'futures' vs 'future' container mismatches in API calls. "
        "Would the wrong product category trigger PERMISSION_DENIED or a different error?",
        "Round 5: Discuss legacy vs CDP API keys. "
        "How to test whether the key type is incompatible with futures trading?",
        "Round 6: Consider regional restrictions (US vs non-US) and CFM onboarding. "
        "What specific checks confirm eligibility?",
        "Round 7: What minimal API call sequence should succeed for a valid futures trader? "
        "Provide a test checklist (no code changes).",
        "Round 8: If the exchange allows viewing futures but denies trading, what escalation path "
        "or account action should be taken?",
        "Round 9: Propose the highest-confidence fix order (stepwise) and justify why it’s prioritized.",
        "Round 10: Provide a final consensus plan with concrete verification steps and expected outcomes.",
    ]

    for idx, prompt in enumerate(rounds, start=1):
        title = f"\n{'='*100}\nROUND {idx}\n{'='*100}"
        print(title)
        save_block(title)

        claude_prompt = f"{context}\n\n{prompt}\nProvide a concise moderator prompt to Qwen and Gemini."
        claude_resp = ask_model(CLAUDE_MODEL, claude_history, claude_system, claude_prompt, max_tokens=400)
        print("\n🔵 CLAUDE:")
        print(claude_resp)
        save_block(f"\n🔵 CLAUDE:\n{claude_resp}")

        qwen_prompt = f"{context}\n\n{prompt}\nBe concrete and propose verification steps."
        qwen_resp = ask_model(QWEN_MODEL, qwen_history, qwen_system, qwen_prompt, max_tokens=600, temperature=0.3)
        print("\n🟡 QWEN:")
        print(qwen_resp)
        save_block(f"\n🟡 QWEN:\n{qwen_resp}")

        gemini_prompt = f"{context}\n\n{prompt}\nProvide pragmatic fixes and checks."
        gemini_resp = ask_model(GEMINI_MODEL, gemini_history, gemini_system, gemini_prompt, max_tokens=600)
        print("\n🟢 GEMINI:")
        print(gemini_resp)
        save_block(f"\n🟢 GEMINI:\n{gemini_resp}")

        time.sleep(1)


if __name__ == "__main__":
    main()
