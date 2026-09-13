from tradebot_sci.runtime.loop import _flatten_symbols_at_shutdown, _should_flatten_symbol


class RuntimeStub:
    """Minimal runtime stub to control flatten flags."""

    def __init__(self) -> None:
        self.flatten_on_exit = True
        self.intraday_flatten = False


def test_crypto_profile_skips_flatten_on_shutdown() -> None:
    runtime = RuntimeStub()
    runtime.flatten_on_exit = False
    runtime.intraday_flatten = False
    assert not _should_flatten_symbol(
        "BTCUSD",
        "crypto_247",
        runtime,
        crypto_only_profile=True,
    ), "crypto_247 should skip flatten when runtime overrides disable flatten/cancel"


def test_runtime_flatten_disabled_blocks_all_symbols() -> None:
    runtime = RuntimeStub()
    runtime.flatten_on_exit = False
    runtime.intraday_flatten = False
    assert not _should_flatten_symbol(
        "SPY",
        "crypto_247",
        runtime,
        crypto_only_profile=False,
    ), "Disabling runtime flatten flags should block flatten for any symbol"


class ExecutorStub:
    def __init__(self) -> None:
        self.flatten_calls: list[str] = []

    def flatten_symbol(self, symbol: str) -> None:
        self.flatten_calls.append(symbol)


def test_shutdown_cleanup_skips_crypto_flatten() -> None:
    runtime = RuntimeStub()
    runtime.flatten_on_exit = False
    runtime.intraday_flatten = False
    executor = ExecutorStub()
    flattened = _flatten_symbols_at_shutdown(
        ["BTCUSD"],
        "crypto_247",
        runtime,
        crypto_only_profile=True,
        executor=executor,
    )
    assert flattened == []
    assert executor.flatten_calls == [], "flatten_symbol should not be invoked for crypto-only profile"
