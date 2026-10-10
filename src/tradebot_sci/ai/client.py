from __future__ import annotations

import logging
import math
from typing import List, Optional

import httpx
from pydantic import ValidationError

from tradebot_sci.ai.prompts import build_decision_messages
from tradebot_sci.ai.schemas import (
    ChatMessage,
    ParsedDecisionPayload,
    parse_decision_payload,
)
from tradebot_sci.config.models import AISettings, Settings
from tradebot_sci.runtime.rate_limit import with_retry
from tradebot_sci.runtime.safety import validate_decision
from tradebot_sci.strategy.decisions import AITradeDecision, stand_aside_decision

logger = logging.getLogger(__name__)


def _as_fraction(value: Optional[float]) -> Optional[float]:
    """Normalizes a percentage field the model may send as 12 instead of 0.12.

    The payload schema accepts 0-100; AITradeDecision only accepts 0-1, so anything
    above 1 is treated as a percentage and scaled down, then clamped.

    Anything that is not a finite number is dropped rather than coerced. A JSON
    `true` is not 1.0: treating it as one would let a boolean in the model's reply
    set risk to the whole account. NaN survived the old clamp untouched, because
    every comparison against NaN is False, and a non-numeric string raised here
    instead of being handled. A value we cannot read is better absent than maximal.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        fraction = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(fraction):
        return None
    if fraction > 1.0:
        fraction /= 100.0
    return min(max(fraction, 0.0), 1.0)


class TradeSciAIClient:
    """Talks to the big brain in the cloud so you don’t have to."""

    def __init__(
        self,
        settings: AISettings,
        http_client: Optional[httpx.Client] = None,
        root_settings: Optional[Settings] = None,
    ) -> None:
        """Initializes HTTP machinery before the AI starts barking orders."""
        self.settings = settings
        # Root Settings object (carries .runtime), used to reach the runtime guards
        # in validate_decision. AISettings alone has no runtime section.
        self.root_settings = root_settings
        self.base_url = self._resolve_base_url()
        self.http_client = http_client or httpx.Client(
            base_url=str(self.base_url), timeout=settings.timeout_seconds
        )
        self.last_request_payload: Optional[dict] = None
        self.last_response_json: Optional[dict] = None

    def _resolve_base_url(self) -> str:
        if self.settings.provider in {"openai", "openrouter", "deepseek", "custom", "local"}:
            if self.settings.base_url:
                return str(self.settings.base_url)
        if self.settings.provider == "openai":
            return "https://api.openai.com/v1"
        if self.settings.provider == "openrouter":
            return "https://openrouter.ai/api/v1"
        if self.settings.provider == "local":
            return "http://localhost:11434/v1" # Default for Ollama
        if self.settings.provider == "deepseek":
            return "https://api.deepseek.com"
        if self.settings.provider == "claude":
            return "https://api.anthropic.com"
        if self.settings.provider == "gemini":
            return "https://generativelanguage.googleapis.com"
        return str(self.settings.base_url)

    @with_retry()
    def raw_chat(self, messages: List[ChatMessage], *, expect_json: bool) -> str:
        """Sends polite JSON to the AI and hopes for polite JSON back."""
        provider = self.settings.provider
        
        # Refuse remote calls without a key. Returning "{}"/"" here made "no key
        # configured" indistinguishable from "the model returned nothing".
        # A self-hosted "custom" endpoint may legitimately need no key.
        if provider not in {"local", "custom"} and not getattr(self.settings, "api_key", None):
            raise RuntimeError(
                f"No API key configured for provider '{provider}'; refusing to send an unauthenticated request."
            )

        if provider in {"openai", "openrouter", "deepseek", "custom", "local"}:
            return self._chat_openai(messages, expect_json=expect_json)
        if provider == "claude":
            return self._chat_claude(messages, expect_json=expect_json)
        if provider == "gemini":
            return self._chat_gemini(messages, expect_json=expect_json)
        return self._chat_openai(messages, expect_json=expect_json)

    def generate_decision(self, market_context, settings: Optional[Settings] = None) -> AITradeDecision:
        """Builds context, chats with the AI, and translates JSON into marching orders."""
        original_messages = build_decision_messages(market_context.to_dict(), model_name=self.settings.model_name)
        conversation = original_messages.copy()
        attempts = 0
        max_attempts = 2
        while attempts < max_attempts:
            content = self.raw_chat(conversation, expect_json=True)
            logger.info(f"[DEBUG] AI Raw Content (len={len(content)}): {content[:100]}...")
            try:
                parsed = parse_decision_payload(content)
                logger.info("[DEBUG] Payload parsed successfully.")
            except ValidationError as exc:
                logger.warning(f"[DEBUG] Validation Error: {exc}")
                attempts += 1
                self._log_json_error(exc, content, attempts, max_attempts)
                if attempts >= max_attempts:
                    reason = f"Invalid AI JSON after {attempts} attempts ({exc})"
                    return stand_aside_decision(
                        market_context.symbol,
                        market_context.timeframe,
                        reason,
                    )
                conversation.append(self._build_json_retry_message(str(exc)))
                continue
            
            logger.info("[DEBUG] Converting to decision object...")
            decision = self._to_decision(parsed)
            logger.info("[DEBUG] Decision object created. Validating...")
            
            caps = getattr(market_context, "execution_capabilities", None)
            # Pass the settings object through so the runtime guards
            # (simulation_risk_cap, flip_actions_enabled) can actually veto a decision.
            # Fall back to this client's own settings when the caller has no root object.
            active_settings = settings if settings is not None else self.root_settings
            if active_settings is None:
                active_settings = self.settings
            validated = validate_decision(
                decision,
                settings=active_settings,
                execution_capabilities=caps,
            )
            logger.info("[DEBUG] Decision validated. Returning.")
            return validated
        return stand_aside_decision(
            market_context.symbol,
            market_context.timeframe,
            "Repeated invalid AI JSON",
        )

    def generate_text(self, messages: List[ChatMessage]) -> str:
        """Requests a plain-text response for commentary."""
        return self.raw_chat(messages, expect_json=False).strip()

    def _chat_openai(self, messages: List[ChatMessage], *, expect_json: bool) -> str:
        payload: dict = {
            "model": self.settings.model_name,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "messages": messages,
        }
        if expect_json and "reasoner" not in self.settings.model_name.lower():
            payload["response_format"] = {"type": "json_object"}
        self.last_request_payload = payload
        response = self.http_client.post(
            url="/chat/completions",
            json=payload,
            headers=self._headers_openai(),
        )
        try:
            data = response.json()
        except Exception:
            data = {"text": response.text}
        self.last_response_json = data
        if response.status_code == 429:
            raise httpx.HTTPStatusError(f"Rate limited: {response.text}", request=response.request, response=response)
        
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Inject the literal API response body into the exception message so the user can read the explicit error
            raise httpx.HTTPStatusError(f"{e} | Details: {response.text}", request=response.request, response=response) from None

        try:
            message = data["choices"][0]["message"]
            if isinstance(message, dict):
                return str(message.get("content", ""))
        except Exception as e:
            logger.warning(f"Failed to parse OpenAI chat response: {e}")
            pass
        return ""

    def _chat_claude(self, messages: List[ChatMessage], *, expect_json: bool) -> str:
        system_text = self._extract_system(messages)
        claude_messages: List[dict] = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                continue
            content = str(msg.get("content", ""))
            if claude_messages and claude_messages[-1]["role"] == role:
                # Anthropic rejects consecutive same-role turns, so merge them into one.
                claude_messages[-1]["content"][0]["text"] += "\n\n" + content
                continue
            claude_messages.append(
                {
                    "role": role,
                    "content": [{"type": "text", "text": content}],
                }
            )
        if expect_json:
            # Append the JSON contract once, to the final user turn, instead of repeating
            # it on every message.
            for entry in reversed(claude_messages):
                if entry["role"] == "user":
                    entry["content"][0]["text"] += "\n\nReturn a single JSON object only."
                    break
        payload = {
            "model": self.settings.model_name,
            "max_tokens": self.settings.max_tokens,
            "temperature": self.settings.temperature,
            "system": system_text or "",
            "messages": claude_messages,
        }
        self.last_request_payload = payload
        response = self.http_client.post(
            url="/v1/messages",
            json=payload,
            headers=self._headers_claude(),
        )
        try:
            data = response.json()
        except Exception as e:
            logger.warning(f"Failed to parse Claude response JSON: {e}")
            data = {"text": response.text}
        self.last_response_json = data
        if response.status_code == 429:
            raise httpx.HTTPStatusError("Rate limited", request=response.request, response=response)
        response.raise_for_status()
        try:
            return str(data["content"][0]["text"])
        except Exception as e:
            logger.warning(f"Failed to extract Claude response text: {e}")
            return ""

    def _chat_gemini(self, messages: List[ChatMessage], *, expect_json: bool) -> str:
        system_text = self._extract_system(messages)
        # System messages are sent as systemInstruction below, so exclude them here or
        # the system prompt arrives twice.
        prompt = "\n\n".join(
            f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
            for msg in messages
            if msg and msg.get("role") != "system"
        )
        response_mime = "application/json" if expect_json else "text/plain"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.settings.temperature,
                "maxOutputTokens": self.settings.max_tokens,
                "responseMimeType": response_mime,
                # Gemini 2.5 Flash charges its internal thinking against maxOutputTokens,
                # which truncates the visible answer; disable thinking so the whole
                # budget goes to the reply.
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        self.last_request_payload = payload
        response = self.http_client.post(
            url=f"/v1beta/models/{self.settings.model_name}:generateContent",
            json=payload,
            headers=self._headers_gemini(),
        )
        try:
            data = response.json()
        except Exception as e:
            logger.warning(f"Failed to parse Gemini response JSON: {e}")
            data = {"text": response.text}
        self.last_response_json = data
        if response.status_code == 429:
            raise httpx.HTTPStatusError("Rate limited", request=response.request, response=response)
        response.raise_for_status()
        candidates = data.get("candidates") if isinstance(data, dict) else None
        finish_reason = None
        if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
            finish_reason = candidates[0].get("finishReason")
        if finish_reason and finish_reason != "STOP":
            logger.warning(
                "[AI] Gemini response did not finish normally (finishReason=%s); discarding the reply.",
                finish_reason,
            )
            return ""
        try:
            return str(data["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as e:
            logger.warning(f"Failed to extract Gemini response text: {e}")
            return ""

    def _extract_system(self, messages: List[ChatMessage]) -> str:
        systems = [str(m.get("content", "")) for m in messages if m.get("role") == "system"]
        return "\n".join(systems).strip()

    def _log_json_error(
        self,
        exc: ValidationError,
        raw_content: str,
        attempt: int,
        max_attempts: int,
    ) -> None:
        short_err = str(exc).split("\n")[0]
        preview = raw_content.replace("\n", " ")[:200]
        logger.error(
            "[GUARD] Invalid AI JSON (attempt %s/%s): %s | preview=%s",
            attempt,
            max_attempts,
            short_err,
            preview,
        )

    def _build_json_retry_message(self, error_text: str) -> ChatMessage:
        """Asks the AI to retry with strict JSON after a failure."""
        return {
            "role": "user",
            "content": (
                "Previous response could not be parsed because it contained invalid JSON "
                f"({error_text}). Please reply with a single JSON object only—no prose, no markdown, "
                "no backticks, no trailing characters. "
                "Strictly follow the schema and nothing else."
            ),
        }

    def _to_decision(self, parsed: ParsedDecisionPayload) -> AITradeDecision:
        """Transmutes JSON payload into our internal decision object without alchemy."""
        decision = AITradeDecision(
            symbol=parsed.symbol,
            timeframe=parsed.timeframe,
            bias=parsed.bias,
            phase=parsed.phase,
            action=parsed.action,
            entry_price=parsed.entry_price,
            entry_zone=tuple(parsed.entry_zone) if parsed.entry_zone else None,
            stop_loss=parsed.stop_loss,
            take_profit=parsed.take_profit,
            risk_per_trade_pct=_as_fraction(parsed.risk_per_trade_pct),
            max_position_size_pct=_as_fraction(parsed.max_position_size_pct),
            time_in_force_sec=parsed.time_in_force_sec,
            urgency=parsed.urgency,
            structure_summary=parsed.structure_summary,
            invalidation_conditions=parsed.invalidation_conditions,
            management_instructions=parsed.management_instructions,
            notes=parsed.notes,
        )

        # Validate and fix RR to ensure minimum 0.4 ratio
        # This prevents AI from setting targets too close to entry
        return decision.validate_and_fix_rr(min_rr=0.4)

    def _headers_openai(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        return headers

    def _headers_claude(self) -> dict:
        headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
        if self.settings.api_key:
            headers["x-api-key"] = self.settings.api_key
        return headers

    def _headers_gemini(self) -> dict:
        # Sent as a header, not a query parameter: a key in the URL ends up in the
        # httpx INFO request log and in raise_for_status() exception text.
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["x-goog-api-key"] = self.settings.api_key
        return headers
