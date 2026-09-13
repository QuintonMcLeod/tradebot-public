from tradebot_sci.broker.ccxt_broker import _parse_symbol_map


def test_parse_symbol_map():
    value = "BTCUSD:BTC/USDT, ETHUSD:ETH/USDT"
    parsed = _parse_symbol_map(value)
    assert parsed["BTCUSD"] == "BTC/USDT"
    assert parsed["ETHUSD"] == "ETH/USDT"

