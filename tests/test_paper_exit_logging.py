"""Guards the [EXIT] log record against a silent %-formatting failure.

The paper broker reports every closed position by logging an [EXIT] line. The
LedgerDaemon tail-reads that log and parses those lines with RE_EXIT, so a
record that never reaches the log is a trade the ledger can never see.

Logging applies %-formatting to the message whenever extra positional arguments
are supplied. A message that contains a literal "%)" therefore raises
ValueError inside the logging machinery, and the handler prints a traceback
while dropping the record. The message is lost, no exception reaches the
caller, and the exit goes unrecorded.

These tests pin both halves of that contract: the message must be emitted, and
what is emitted must be parsed by the same regex the ledger uses.
"""

from __future__ import annotations

import ast
import datetime as _dt
import io
import logging
import os
import pathlib
import re
import sys
import types
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tradebot_sci.broker.execution import ExecutionStatus  # noqa: E402
from tradebot_sci.broker.paper_broker import PaperBroker  # noqa: E402
from tradebot_sci.market.models import Candle  # noqa: E402
from tradebot_sci.runtime.ledger_daemon import RE_EXIT  # noqa: E402
from tradebot_sci.strategy.decisions import AITradeDecision  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PAPER_BROKER = REPO_ROOT / "src" / "tradebot_sci" / "broker" / "paper_broker.py"

LOG_METHODS = {
    "debug",
    "info",
    "warning",
    "error",
    "critical",
    "exception",
}


def _excursion_str() -> str:
    """Stand-in for PaperBroker._excursion_str at a losing stop-out."""
    return "MFE=$37.40 (net $29.17) MAE=$-85.17 (net $-93.40)"


def _paper_sl_message() -> str:
    """The message the paper broker builds for a synthetic stop-out."""
    return (
        f"[PAPER] [EXIT] Paper {'SL'}: {'NZDUSD'} {'-$85.17'} "
        f"(Pct={-0.36:.2f}%) position={'LONG'} | "
        f"Entry={0.57747:.5f} Exit={0.57536:.5f} | "
        f"Duration={'7h 23m 10s'} | "
        f"Est. Spread Cost: ${8.23:.2f} | {_excursion_str()}"
    )


def _capture(logger: logging.Logger) -> tuple[io.StringIO, logging.Handler]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return stream, handler


def test_exit_message_is_emitted_and_carries_no_unformatted_percent() -> None:
    """The [EXIT] record reaches the log with its data intact."""
    logger = logging.getLogger("tradebot_sci.broker.paper_broker")
    stream, handler = _capture(logger)
    previous_propagate = logger.propagate
    logger.propagate = False
    try:
        logger.info(_paper_sl_message())
    finally:
        logger.removeHandler(handler)
        logger.propagate = previous_propagate

    emitted = stream.getvalue()
    assert "[EXIT]" in emitted, "the [EXIT] record was dropped"
    assert "NZDUSD" in emitted
    assert "-$85.17" in emitted
    assert "-0.36%" in emitted
    assert "MAE=$-85.17" in emitted


def test_passing_excursion_as_a_logging_argument_drops_the_record() -> None:
    """Documents the failure mode: a literal '%)' plus an argument loses the line.

    This is the shape the paper broker used before the fix. It is asserted here
    so the regression cannot be reintroduced as an "equivalent" refactor.
    """
    logger = logging.getLogger("tradebot_sci.broker.paper_broker")
    stream, handler = _capture(logger)
    previous_propagate = logger.propagate
    logger.propagate = False

    # Suppress the logging module's internal traceback dump for this call; the
    # point of the test is that the caller sees no error and the record is lost.
    previous_raise = logging.raiseExceptions
    logging.raiseExceptions = False
    try:
        logger.info(
            f"[PAPER] [EXIT] Paper {'SL'}: {'NZDUSD'} {'-$85.17'} "
            f"(Pct={-0.36:.2f}%) position={'LONG'} | "
            f"Est. Spread Cost: ${8.23:.2f} | ",
            _excursion_str(),
        )
    finally:
        logging.raiseExceptions = previous_raise
        logger.removeHandler(handler)
        logger.propagate = previous_propagate

    assert "[EXIT]" not in stream.getvalue(), (
        "Expected the %-formatting failure to suppress the record; if this "
        "assertion fails the failure mode has changed and the guard in "
        "paper_broker.py should be re-derived."
    )


def test_ledger_regex_parses_the_emitted_exit_line() -> None:
    """What the broker emits is what the LedgerDaemon can read."""
    match = RE_EXIT.search(_paper_sl_message())
    assert match is not None, "RE_EXIT did not match the emitted [EXIT] line"

    groups = match.groupdict()
    assert groups["symbol"] == "NZDUSD"
    assert groups["reason"] == "Paper SL"
    assert groups["pnl_sign"] == "-"
    assert groups["pnl_val"] == "85.17"
    assert groups["pct"] == "-0.36"
    assert groups["duration"].strip() == "7h 23m 10s"
    assert groups["spread"] == "8.23"
    assert groups["mfe"] == "37.40"
    assert groups["mae"] == "-85.17"


def test_no_logger_call_passes_arguments_to_a_message_with_a_bare_percent() -> None:
    """Static guard over the whole package, not just the site that was fixed.

    A logging call whose message is an f-string containing a '%' that is not a
    valid conversion specifier, and which also passes positional arguments,
    silently drops the record. Scan for that shape so a new call site cannot
    reintroduce it.
    """
    offenders: list[str] = []

    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:  # pragma: no cover - not this test's concern
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "logger"
                and func.attr in LOG_METHODS
            ):
                continue
            # Fewer than two arguments means logging performs no %-formatting,
            # so a bare '%' in the message is harmless.
            if len(node.args) < 2:
                continue
            first = node.args[0]
            if not isinstance(first, ast.JoinedStr):
                continue

            literal = "".join(
                value.value
                for value in first.values
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            )
            for index, char in enumerate(literal):
                if char != "%":
                    continue
                following = literal[index + 1] if index + 1 < len(literal) else ""
                if following in "sdrfgeExXob%":
                    continue
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{node.lineno} "
                    f"bare '%{following}' in a message that also passes arguments"
                )

    assert not offenders, (
        "logging calls that would drop their record:\n  " + "\n  ".join(offenders)
    )


# ── End-to-end: drive a real synthetic stop-out through the exit logger ────
#
# The unit tests above pin the message and the parser. This one exercises the
# actual evaluate_synthetic_stops path, because that is where the bug lived and
# nothing in the suite previously drove a position to a logged stop-out.

SYMBOL = "BTCUSD"
ENTRY = 50_000.0
STOP = 49_000.0
TARGET = 52_000.0


class _Ticker:
    def __init__(self, last: float) -> None:
        self.last = last


class _Provider:
    """Minimal market provider: a last price and one OHLC candle."""

    def __init__(self, last: float, candle: Candle) -> None:
        self._last = last
        self._candle = candle

    def get_ticker(self, symbol: str, *args, **kwargs) -> _Ticker:
        return _Ticker(self._last)

    def get_latest_candles(self, symbol: str, timeframe: str, limit: int = 200, **kwargs):
        return [self._candle]


def _broker_without_disk(balance: float = 10_000.0) -> PaperBroker:
    profile = types.SimpleNamespace(risk_per_trade_pct=0.01, target_leverage=1.0)
    original_load = PaperBroker._load_state
    original_save = PaperBroker._save_state
    PaperBroker._load_state = lambda self: None
    PaperBroker._save_state = lambda self: None
    try:
        broker = PaperBroker(profile, initial_balance=balance)
    finally:
        PaperBroker._load_state = original_load
        PaperBroker._save_state = original_save
    broker._save_state = lambda: None
    return broker


def _entry_decision() -> AITradeDecision:
    return AITradeDecision(
        symbol=SYMBOL,
        timeframe="5m",
        bias="long",
        phase="trend",
        action="enter_long",
        entry_price=ENTRY,
        entry_zone=None,
        stop_loss=STOP,
        take_profit=TARGET,
        risk_per_trade_pct=None,
        max_position_size_pct=None,
        time_in_force_sec=None,
        urgency="medium",
        structure_summary="exit logging test",
        invalidation_conditions="N/A",
        management_instructions="hold",
        notes="exit logging test",
    )


def test_real_stop_out_emits_a_parseable_exit_record() -> None:
    broker = _broker_without_disk()
    result, _outcome = broker.execute_decision(_entry_decision())
    assert result.status == ExecutionStatus.EXECUTED, "position was not opened"
    assert broker.positions, "broker reports no open position"

    # A candle whose low trades through the stop.
    candle = Candle(
        timestamp=_dt.datetime.now(_dt.timezone.utc),
        open=ENTRY,
        high=ENTRY,
        low=STOP - 50.0,
        close=STOP - 25.0,
        volume=1.0,
    )
    provider = _Provider(last=STOP - 25.0, candle=candle)

    logger = logging.getLogger("tradebot_sci.broker.paper_broker")
    stream, handler = _capture(logger)
    previous_propagate = logger.propagate
    logger.propagate = False
    previous_raise = logging.raiseExceptions
    # Without this the logging module dumps the traceback to stderr, which is
    # exactly how this failure stayed invisible in production.
    logging.raiseExceptions = False
    try:
        broker.evaluate_synthetic_stops(provider, "5m")
    finally:
        logging.raiseExceptions = previous_raise
        logger.removeHandler(handler)
        logger.propagate = previous_propagate

    emitted = stream.getvalue()
    exit_lines = [line for line in emitted.splitlines() if "[EXIT]" in line]
    assert exit_lines, (
        "the stop-out produced no [EXIT] line, so the ledger would never see "
        f"this trade. Captured output:\n{emitted}"
    )

    match = RE_EXIT.search(exit_lines[0])
    assert match is not None, f"RE_EXIT could not parse the emitted line: {exit_lines[0]}"
    assert match.group("symbol") == SYMBOL
    assert not broker.positions, "the position should have been closed"
