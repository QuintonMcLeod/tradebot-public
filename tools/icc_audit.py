from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.ai.schemas import ChatMessage
from tradebot_sci.config.loader import load_settings


DEFAULT_HISTORY_PATH = "data/icc_audit_history.json"


@dataclass
class AuditResult:
    raw: dict[str, Any]
    raw_reply: str | None
    extracted_score: str | None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ICC audit via internal AI with local history.")
    parser.add_argument("--history", default=os.getenv("ICC_AUDIT_HISTORY", DEFAULT_HISTORY_PATH))
    parser.add_argument("--seed-score", default=os.getenv("ICC_AUDIT_SEED_SCORE", "6/7"))
    parser.add_argument(
        "--seed-notes",
        default=os.getenv(
            "ICC_AUDIT_SEED_NOTES",
            "Previous internal audit scored 6/7 (only missing confluence/data completeness).",
        ),
    )
    parser.add_argument(
        "--what-changed",
        default=os.getenv(
            "ICC_AUDIT_WHAT_CHANGED",
            "Added confluence context (session/spread/volatility/orderbook depth) and optional VIX close via Stooq.",
        ),
    )
    args = parser.parse_args()

    history_path = Path(args.history)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history = _load_history(history_path)

    last = history[-1] if history else None
    prior_score = (last or {}).get("extracted_score") or args.seed_score
    prior_notes = (last or {}).get("notes") or args.seed_notes

    prompt = _build_prompt(prior_score=str(prior_score), prior_notes=str(prior_notes), what_changed=str(args.what_changed))
    result = _run_adviser(prompt)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prior_score": prior_score,
        "notes": prior_notes,
        "what_changed": args.what_changed,
        "extracted_score": result.extracted_score,
        "adviser_wrapper": result.raw,
        "adviser_raw_reply": result.raw_reply,
    }
    history.append(entry)
    history_path.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps({"extracted_score": result.extracted_score, "history_path": str(history_path)}, indent=2))
    return 0


def _load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        history = data if isinstance(data, list) else []
        changed = False
        for entry in history:
            if not isinstance(entry, dict):
                continue
            if entry.get("extracted_score"):
                continue
            raw_reply = entry.get("adviser_raw_reply")
            wrapper = entry.get("adviser_wrapper")
            if isinstance(wrapper, dict) and raw_reply is None:
                raw_reply = wrapper.get("raw_reply")
            if isinstance(raw_reply, str) or isinstance(wrapper, dict):
                extracted = _extract_score(wrapper if isinstance(wrapper, dict) else {}, raw_reply if isinstance(raw_reply, str) else None)
                if extracted:
                    entry["extracted_score"] = extracted
                    changed = True
        if changed:
            try:
                path.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")
            except Exception:
                pass
        return history
    except Exception:
        return []


def _build_prompt(*, prior_score: str, prior_notes: str, what_changed: str) -> str:
    # Keep it short and explicit so the agent stays on task.
    return (
        "You are the ICC Advisor agent auditing a trading bot implementation.\n"
        "You have audit history. Maintain continuity: if you change prior judgments, explain why.\n\n"
        f"Previous audit score: {prior_score}\n"
        f"Previous notes: {prior_notes}\n"
        f"Changes since last audit: {what_changed}\n\n"
        "Now re-score ONLY these 7 points and output JSON:\n"
        "1) HTF/MTF structure gate\n"
        "2) Correction+sweep+continuation gating\n"
        "3) Adds protocol\n"
        "4) Risk tiering\n"
        "5) Venue/execution constraints awareness\n"
        "6) Non-trade explainability\n"
        "7) Confluence/data completeness\n\n"
        "Output JSON keys:\n"
        "{\n"
        '  "icc_audit_score": "X/7",\n'
        '  "breakdown": [{"point": 1, "pass": true/false, "reason": "..."}, ...],\n'
        '  "top_remaining_fixes": ["...", "..."]\n'
        "}\n"
        "No prose outside JSON."
    )


def _run_adviser(prompt: str) -> AuditResult:
    settings = load_settings().ai
    client = TradeSciAIClient(settings)
    messages: list[ChatMessage] = [
        {
            "role": "system",
            "content": "You are the ICC Advisor agent auditing a trading bot implementation. Reply with JSON only.",
        },
        {"role": "user", "content": prompt},
    ]
    stdout = client.generate_text(messages)
    if not stdout:
        raise RuntimeError("commentary provider produced no output")

    wrapper = _parse_first_json(stdout)
    raw_reply = wrapper.get("raw_reply") if isinstance(wrapper, dict) else None
    extracted = _extract_score(wrapper, raw_reply)
    return AuditResult(raw=wrapper if isinstance(wrapper, dict) else {"raw": stdout}, raw_reply=raw_reply, extracted_score=extracted)


def _parse_first_json(text: str) -> dict[str, Any]:
    # Adviser often prints a JSON blob plus a trailing summary line; extract the first complete JSON object.
    start = text.find("{")
    if start == -1:
        return {"raw": text}
    depth = 0
    in_string = False
    escaped = False
    end = None
    for i, ch in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return {"raw": text}
    return json.loads(text[start:end])


def _extract_score(wrapper: dict[str, Any], raw_reply: str | None) -> str | None:
    # Prefer raw_reply structured JSON.
    for blob in (raw_reply, json.dumps(wrapper)):
        if not blob:
            continue
        try:
            parsed = json.loads(blob)
            if isinstance(parsed, dict):
                score = parsed.get("icc_audit_score")
                if isinstance(score, int):
                    return f"{score}/7"
                if isinstance(score, str) and re.match(r"^\d+/7$", score.strip()):
                    return score.strip()
        except Exception:
            pass
        match = re.search(r"(\d/7)", blob)
        if match:
            return match.group(1)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
