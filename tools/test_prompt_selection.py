#!/usr/bin/env python3
"""Test that the correct prompt is selected based on model name."""

from tradebot_sci.ai.prompts import _select_system_prompt, SYSTEM_PROMPT_GENERIC, SYSTEM_PROMPT_QWEN

def test_prompt_selection():
    """Test prompt selection logic."""

    print("=" * 80)
    print("Testing AI Prompt Selection Logic")
    print("=" * 80)

    # Test cases: (model_name, expected_prompt_type)
    test_cases = [
        ("qwen/qwen-turbo", "QWEN"),
        ("qwen/qwen-2.5-72b", "QWEN"),
        ("Qwen/Qwen-Turbo", "QWEN"),  # Case insensitive
        ("gpt-4", "GENERIC"),
        ("gpt-4o", "GENERIC"),
        ("claude-3-opus", "GENERIC"),
        ("deepseek-chat", "GENERIC"),
        ("gemini-pro", "GENERIC"),
        ("", "GENERIC"),  # Empty model name
    ]

    print("\nTest Cases:")
    print("-" * 80)

    all_passed = True
    for model_name, expected_type in test_cases:
        selected_prompt = _select_system_prompt(model_name)

        if expected_type == "QWEN":
            expected_prompt = SYSTEM_PROMPT_QWEN
            prompt_name = "QWEN (optimized)"
        else:
            expected_prompt = SYSTEM_PROMPT_GENERIC
            prompt_name = "GENERIC (full ICC)"

        passed = selected_prompt == expected_prompt
        status = "✓ PASS" if passed else "✗ FAIL"

        print(f"{status} | Model: {model_name:25s} → {prompt_name}")

        if not passed:
            all_passed = False

    print("-" * 80)

    # Show prompt size comparison
    print("\nPrompt Size Comparison:")
    print(f"  GENERIC prompt: {len(SYSTEM_PROMPT_GENERIC)} chars (~{len(SYSTEM_PROMPT_GENERIC.split())} tokens)")
    print(f"  QWEN prompt:    {len(SYSTEM_PROMPT_QWEN)} chars (~{len(SYSTEM_PROMPT_QWEN.split())} tokens)")
    savings = len(SYSTEM_PROMPT_GENERIC) - len(SYSTEM_PROMPT_QWEN)
    savings_pct = (savings / len(SYSTEM_PROMPT_GENERIC)) * 100
    print(f"  Savings:        {savings} chars (~{savings_pct:.1f}% reduction)")

    # Show estimated cost savings
    avg_tokens_saved = len(SYSTEM_PROMPT_GENERIC.split()) - len(SYSTEM_PROMPT_QWEN.split())
    cost_per_call_saved = avg_tokens_saved * 0.00000005  # Qwen input token cost
    monthly_calls = 4400  # From hybrid cache estimate
    monthly_savings = cost_per_call_saved * monthly_calls

    print(f"\nEstimated Cost Savings (Qwen Turbo):")
    print(f"  Tokens saved per call: ~{avg_tokens_saved}")
    print(f"  Cost saved per call:   ${cost_per_call_saved:.8f}")
    print(f"  Monthly savings:       ${monthly_savings:.4f} (at {monthly_calls} calls/month)")

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ All tests PASSED!")
    else:
        print("❌ Some tests FAILED!")
    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    import sys
    success = test_prompt_selection()
    sys.exit(0 if success else 1)
