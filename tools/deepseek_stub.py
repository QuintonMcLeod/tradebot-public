#!/usr/bin/env python3
"\"\"\"Simple stub server that mimics the DeepSeek HTTP chat completions API for Q&A.""\"

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8123

DEEP_RESPONSE = {
    "verdict": "PASS",
    "confidence": 0.91,
    "icc_rules": [
        {
            "rule": "A1",
            "why_it_matters": (
                "Crypto shutdown logic now respects crypto-only profiles and runtime overrides "
                "so unwanted flattening/cancel calls never trigger."
            ),
            "citations": [
                {
                    "chunk_id": "f7c4150cbab61ded3eb6c4aefde671478ca46037c790d7cf826e37efa70976ee",
                    "day": "Day 10",
                    "filename": "Trading Course Day 10: How to Mark Up.txt",
                }
            ],
        }
    ],
    "engineering_actions": [
        {
            "priority": "P1",
            "action": (
                "Document and maintain the `_flatten_symbols_at_shutdown` helper so both "
                "run_bot and scheduled loops share the same guard logic."
            ),
            "files": ["src/tradebot_sci/runtime/loop.py"],
            "tests_to_add": ["tests/test_crypto_flatten_shutdown.py"],
        }
    ],
    "risks": [
        {
            "risk": "Crypto flatten may reappear when runtime overrides disable flatten on exit.",
            "impact": "Unwanted auto-flatten could liquidate ZEROHASH exposure overnight.",
            "mitigation": (
                "The helper honors `crypto_only` and runtime flags before calling `flatten_symbol`."
            ),
        }
    ],
    "questions_for_human": [],
}


class StubHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            self.rfile.read(length)
        response = {
            "choices": [
                {"message": {"content": json.dumps(DEEP_RESPONSE, ensure_ascii=False)}}
            ]
        }
        body = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Silence the server log output for cleanliness.
        return


def serve() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), StubHandler)
    print(f"DeepSeek stub listening on http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    serve()
