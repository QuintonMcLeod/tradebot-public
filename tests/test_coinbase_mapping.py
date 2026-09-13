from tradebot_sci.market.coinbase import CoinbaseMarketDataProvider


def test_coinbase_product_mapping_allows_supported_symbols():
    provider = CoinbaseMarketDataProvider()
    try:
        assert provider._product_id("BTCUSD") == "BTC-USD"  # type: ignore[attr-defined]
        assert provider._product_id("ETHUSD") == "ETH-USD"  # type: ignore[attr-defined]
        assert provider._product_id("SOLUSD") == "SOL-USD"  # type: ignore[attr-defined]
    finally:
        provider.close()

