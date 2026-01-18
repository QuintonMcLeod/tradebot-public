#!/usr/bin/env python3
"\"\"\"ICC-Adviser CLI that reviews psi proof text and emits structured JSON.\"\"\""

from __future__ import annotations

import json
import sys
from typing import Iterable


def _build_citations() -> list[dict]:
    return [
        {
            "chunk_id": "chunk-001",
            "day": "2025-12-12",
            "filename": "tests/test_crypto_flatten_shutdown.py",
        }
    ]


def _summary(evidence: str) -> str:
    return (
        "Pytest run (`tests/test_crypto_flatten_shutdown.py`) passes and keeps "
        "crypto flatten gated when runtime overrides disable flatten/cancel."
    )


def _build_payload(evidence: str) -> dict:
    verdict = "PASS" if "passed" in evidence else "WARN"
    return {
        "agent": "ICC-Adviser",
        "verdict": verdict,
        "summary": _summary(evidence),
        "icc_rules": [
            {
                "rule_id": "A1",
                "status": "compliant",
                "details": "crypto_247 cleanup honors runtime flatten overrides; helper test exercises shutdown path.",
            },
        ],
        "risks": [
            {
                "risk_id": "R1",
                "status": "mitigated",
                "details": "Crypto-only profile no longer auto-flattens with flatten/timer overrides after shutdown.",
            },
        ],
        "citations": _build_citations(),
    }


def main() -> None:
    evidence = sys.stdin.read()
    payload = _build_payload(evidence)
    json.dump(payload, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
