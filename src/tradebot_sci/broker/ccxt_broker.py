from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import ccxt  # type: ignore

from tradebot_sci.broker.execution import ExecutionOutcome, ExecutionOutcomeType, ExecutionResult, ExecutionStatus
from tradebot_sci.config.models import TradingProfileSettings
from tradebot_sci.market.models import Ticker
from tradebot_sci.broker.position_hold_store import PositionHoldStore
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.market.symbols import AssetClass, SYMBOL_METADATA
from tradebot_sci.strategy.icc_signals import last_structure_range

logger = logging.getLogger(__name__)


def _parse_symbol_map(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    mapping: dict[str, str] = {}
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        left, right = chunk.split(":", 1)
        mapping[left.strip().upper()] = right.strip()
    return mapping


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _LocalOrder:
    order_id: str
    symbol: str
    created_at: float
    client_order_id: str | None = None


class CCXTExchangeBroker:
    """A real exchange broker implemented via ccxt.

    This is wired under `market.exchange_provider=alternative` + `market.alternative_broker=ccxt`.
    """

    def __init__(self, profile: TradingProfileSettings, position_hold_store_path: str | None = None, default_type: str | None = None) -> None:
        self.profile = profile
        # Auto-detect futures mode if profile name suggests it, unless explicitly overridden
        if default_type is None:
            if (os.getenv("PROFILE_NAME") or "").strip().lower() == "coinbase_futures":
                default_type = "future"
            elif (os.getenv("ALTERNATIVE_MARKET_DATA") or "").strip().lower() == "coinbase_futures":
                default_type = "future"
        
        self.default_type = default_type
        self.capital_exhausted = False
        self.position_hold_store = None
        if position_hold_store_path:
            self.position_hold_store = PositionHoldStore(position_hold_store_path)
        self.exchange_id = (os.getenv("CCXT_EXCHANGE") or "").strip()
        if not self.exchange_id:
            raise ValueError("CCXT_EXCHANGE is required when market.alternative_broker=ccxt")

        self.symbol_map = {
            # Coinbase expects USD pairs (e.g. LTC/USD), not USDT, for most major cryptos
            # Coinbase: USDT pairs for stablecoin trading, USD for fiat trading
            **{"BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD", "SOLUSD": "SOL/USD", "LTCUSD": "LTC/USD"},
            **{
                "BTCUSDT": "BTC/USDT", "ETHUSDT": "ETH/USDT", "SOLUSDT": "SOL/USDT", "LTCUSDT": "LTC/USDT", "DOGEUSDT": "DOGE/USDT",
                "XRPUSDT": "XRP/USDT", "ADAUSDT": "ADA/USDT", "LINKUSDT": "LINK/USDT", "POLUSD": "POL/USD",
                "AVAXUSDT": "AVAX/USDT", "SHIBUSDT": "SHIB/USDT", "NEARUSDT": "NEAR/USDT", "DOTUSDT": "DOT/USDT",
                "ATOMUSDT": "ATOM/USDT",
            },
            # [ANTIGRAVITY FIX] Add USD pairs for efficient trading (Coinbase)
            **{
                "DOGEUSD": "DOGE/USD", "ADAUSD": "ADA/USD", "XRPUSD": "XRP/USD", "LINKUSD": "LINK/USD",
                "AVAXUSD": "AVAX/USD", "SHIBUSD": "SHIB/USD", "NEARUSD": "NEAR/USD", "DOTUSD": "DOT/USD",
                "ATOMUSD": "ATOM/USD",
                "ETP-20DEC30-CDE": "ETP-20DEC30-CDE", "BIP-20DEC30-CDE": "BIP-20DEC30-CDE",
                "CDENGS/USD:USD-260127": "CDENGS/USD:USD-260127",
                # US Nano Futures (Front Month: Jan 2026)
                "BTC/USD:USD-260130": "BTC/USD:USD-260130",
                "ETH/USD:USD-260130": "ETH/USD:USD-260130",
                "SOL/USD:USD-260130": "SOL/USD:USD-260130",
                "LTC/USD:USD-260130": "LTC/USD:USD-260130",
                "DOGE/USD:USD-260130": "DOGE/USD:USD-260130",
                "AVAX/USD:USD-260130": "AVAX/USD:USD-260130",
                "LINK/USD:USD-260130": "LINK/USD:USD-260130",
                "SHIB/USD:USD-260130": "SHIB/USD:USD-260130",
                "ADA/USD:USD-260130": "ADA/USD:USD-260130",
            },
            **{"USDTUSD": "USDT/USD"}, # For tracking value of USDT itself
            **{
                # Gemini specific mappings (Standard and common)
                "BTCUSD": "BTC/USD", "ETHUSD": "ETH/USD", "SOLUSD": "SOL/USD", "LTCUSD": "LTC/USD",
                "XRPUSD": "XRP/USD", "ADAUSD": "ADA/USD", "LINKUSD": "LINK/USD", "DOGEUSD": "DOGE/USD",
                "AVAXUSD": "AVAX/USD", "SHIBUSD": "SHIB/USD", "NEARUSD": "NEAR/USD", "DOTUSD": "DOT/USD",
                "PEPEUSD": "PEPE/USD", "FETUSD": "FET/USD", "GRTUSD": "GRT/USD",
                "USDPUSD": "USDP/USD", # Gemini's stablecoin
            },
            **{
                # Kraken specific mappings
                "XBTUSD": "BTC/USD", "XBTEUR": "BTC/EUR",
                "ETHXBT": "ETH/BTC", "XRPXBT": "XRP/BTC",
                "USDTZUSD": "USDT/USD",
            },
            **_parse_symbol_map(os.getenv("CCXT_SYMBOL_MAP")),
        }

        self._exchange = self._build_exchange()
        self._local_orders: dict[str, _LocalOrder] = {}
        self._consecutive_errors = 0
        self._last_error_ts: float | None = None
        self._scale_in_counts: dict[str, int] = {}
        self._dust_warned: set[str] = set()  # Track which symbols we've warned about being dust

    @property
    def exchange(self) -> ccxt.Exchange:
        return self._exchange

    @property
    def symbol_map_data(self) -> dict[str, str]:
        return self.symbol_map

    def _is_crypto(self, symbol: str) -> bool:
        meta = SYMBOL_METADATA.get(symbol.upper())
        if not meta:
            return symbol.upper() in self.symbol_map
        return meta.asset_class == AssetClass.CRYPTO

    def _get_allowed_exchange_symbols(self) -> set[str]:
        if not self.profile.symbols:
            return set()
        allowed = set()
        for sym in self.profile.symbols:
            allowed.add(self.symbol_map.get(sym.upper(), sym))
        return allowed

    def _is_known_exchange_symbol(self, symbol: str) -> bool:
        try:
            if not self._exchange.markets:
                self._exchange.load_markets()
            return symbol in self._exchange.markets
        except Exception:
            return False

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        if not self._is_crypto(symbol):
            return
        logger.info(f"[CCXT] cancel_all_orders_for_symbol {symbol}...")
        sym = self._map_symbol(symbol)
        try:
            # [ANTIGRAVITY FIX] Robust cancel_all with manual fallback
            try:
                if hasattr(self._exchange, "cancel_all_orders") and self.exchange_id != "coinbase":
                     self._exchange.cancel_all_orders(sym)
                else:
                     raise NotImplementedError("Manual fallback required")
            except Exception:
                logger.debug(f"[CCXT] cancel_all_orders not supported or failed for {sym}, manual cancel...")
                for order in self._exchange.fetch_open_orders(sym):
                    self._exchange.cancel_order(order["id"], sym)
                    logger.info(f"[CCXT] Manually cancelled order {order['id']} for {symbol}")
        except Exception as exc:
            logger.warning("[CCXT] cancel_all_orders_for_symbol failed symbol=%s (%s)", sym, exc)

    def get_execution_capabilities(self, symbol: str) -> dict:
        default_type = (os.getenv("CCXT_DEFAULT_TYPE") or "spot").lower()
        supports_short = default_type in {"future", "swap", "option", "margin"}
        return {
            "venue": "CCXT",
            "venue_name": "CCXT",
            "asset_class": "crypto",
            "exchange": self.exchange_id,
            "long_only": not supports_short,
            "supports_short": supports_short,
            "supports_bracket_children": False,
            "supports_native_brackets": False,
            "supports_native_stops": True,  # We will implement this
            "requires_synthetic_stops": False, # We prefer native stops
        }

    def flatten_symbol(self, symbol: str) -> None:
        if not self._is_crypto(symbol):
            return
        sym = self._map_symbol(symbol)
        
        # Use snapshot to determine size and direction
        pos = self.get_open_position_snapshot(symbol)
        if not pos:
            return
            
        size = float(pos.get("size", 0.0))
        if abs(size) == 0:
            return
            
        side = "sell" if size > 0 else "buy"
        qty = abs(size)
        
        try:
            # [ANTIGRAVITY FIX] Cancel all orders first to release locked balance (e.g. Stop Loss)
            logger.info(f"[CCXT] Cancelling all orders for {sym} before flattening.")
            try:
                self.cancel_all_orders_for_symbol(symbol)
            except Exception as e:
                logger.warning(f"[CCXT] Failed to cancel orders during flatten for {symbol}: {e}")

            logger.info(f"[CCXT] Flattening {symbol}: {side} {qty}")
            # Use 'market' order to close
            # For futures, sometimes 'reduceOnly': True is needed in params
            params = {}
            default_type = (os.getenv("CCXT_DEFAULT_TYPE") or "spot").lower()
            if default_type in {"future", "swap"} and self._exchange.id != "coinbase":
                params["reduceOnly"] = True

            self._exchange.create_order(sym, "market", side, qty, None, params)
            
            # [ANTIGRAVITY FIX] Clear Position from Store
            if self.position_hold_store:
                self.position_hold_store.remove(decision.symbol if 'decision' in locals() else symbol)
        except Exception as exc:
            # Check if it's a dust position error (minimum amount)
            exc_str = str(exc).lower()
            if "minimum" in exc_str or "must be greater" in exc_str:
                # Only warn once per symbol for dust position errors
                if symbol.upper() not in self._dust_warned:
                    logger.warning("[CCXT] flatten_symbol failed symbol=%s qty=%.8f (%s)", sym, qty, exc)
                    self._dust_warned.add(symbol.upper())
            else:
                # Always log non-dust errors
                logger.warning("[CCXT] flatten_symbol failed symbol=%s qty=%.8f (%s)", sym, qty, exc)

    def list_open_position_symbols(self) -> set[str]:
        """Returns a set of canonical symbols (e.g. BTCUSD) that have open positions > 0."""
        open_symbols = set()
        try:
            # 1. Check Futures/Swap Positions
            if self._exchange.has.get('fetchPositions', False):
                try:
                    positions = self._exchange.fetch_positions()
                    for p in positions:
                        if abs(float(p.get("contracts") or 0)) > 0:
                            # Reverse map symbol
                            raw_sym = p.get("symbol")
                            for k, v in self.symbol_map.items():
                                if v == raw_sym:
                                    open_symbols.add(k)
                                    break
                except Exception as e:
                    logger.warning(f"[CCXT] fetch_positions failed for {self.exchange_id}: {e}")

            # 2. Check Spot Balances
            try:
                bal = self._exchange.fetch_balance()
                total = bal.get("total", {})
                
                # Filter out Quote Currencies (Cash) from being treated as "Positions"
                ignored_currencies = {"USD", "USDT", "USDC", "DAI", "FDUSD", "EUR", "GBP"}
                
                for currency, amount in total.items():
                    amount_float = float(amount or 0)
                    if amount_float <= 1e-8 or currency in ignored_currencies:
                        continue
                    
                    # Try to map back to a canonical symbol (e.g. BTC -> BTCUSD)
                    found = False
                    for k, v in self.symbol_map.items():
                        # Direct mapping if v is just the currency (e.g. 'BTC')
                        if v == currency:
                            open_symbols.add(k)
                            found = True
                            break
                    
                    if not found:
                        for k in self.symbol_map.keys():
                            if k.startswith(currency) and k.endswith("USD"):
                                open_symbols.add(k)
                                found = True
                                break
                    if not found:
                         # Fallback to currency+USD if no map
                         open_symbols.add(f"{currency}USD")
            except Exception as e:
                logger.warning(f"[CCXT] fetch_balance failed for {self.exchange_id}: {e}")

            # 3. Discovery from Orders (Fallback for private sub-accounts)
            try:
                allowed_exchange_symbols = self._get_allowed_exchange_symbols()
                # Use a specific symbol if possible or catch failures early
                open_orders = []
                try:
                    open_orders = self._exchange.fetch_open_orders(None)
                except Exception as e:
                    logger.debug(f"[CCXT] fetch_open_orders(None) failed for {self.exchange_id}: {e}")
                
                for o in open_orders:
                    cand = o.get("symbol")
                    if not cand:
                        continue
                    if allowed_exchange_symbols and cand not in allowed_exchange_symbols:
                        continue
                    
                    mapped_already = False
                    for k, v in self.symbol_map.items():
                        if v == cand:
                            open_symbols.add(k)
                            mapped_already = True
                            break
                    
                    if not mapped_already:
                        sys_sym = cand.replace("/", "").replace("-", "").upper()
                        # Only add if it looks like a valid trading pair
                        if "USD" in sys_sym:
                            self.symbol_map[sys_sym] = cand
                            open_symbols.add(sys_sym)
            except Exception as e:
                logger.debug(f"[CCXT] Discovery from orders failed: {e}")

            # 4. Check Position Hold Store (Fallback for all)
            if self.position_hold_store:
                try:
                    for k in self.position_hold_store.load_all().keys():
                        # Only add if we have a non-zero size in the store
                        record = self.position_hold_store.get(k)
                        if record and record.size and abs(record.size) > 0:
                            open_symbols.add(k.upper())
                except Exception as e:
                    logger.debug(f"[CCXT] Discovery from hold store failed: {e}")
        except Exception as e:
            logger.warning(f"[CCXT] list_open_position_symbols failed: {e}")
        
        logger.debug(f"[CCXT] Discovered open symbols: {open_symbols}")
        return open_symbols

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        # logger.debug(f"[CCXT] Checking snapshot for {symbol}...")
        if not self._is_crypto(symbol):
            return None
            
        sym = self._map_symbol(symbol)
        
        # [ANTIGRAVITY FIX] Ignore symbols not supported by the exchange to silence noisy "Symbol not found" warnings.
        if not self._is_known_exchange_symbol(sym):
            return None
        
        from tradebot_sci.market.symbols import is_coinbase_derivative
        is_future = is_coinbase_derivative(symbol)
        
        size = 0.0
        avg_price = None
        unrealized_pnl = 0.0
        pnl_pct = 0.0
        current_price = None
        
        try:
            # If it's a future, we use fetch_positions if available
            if is_future and self._exchange.has.get('fetchPositions', False):
                try:
                    positions = self._exchange.fetch_positions([sym])
                    # Find matching position
                    # Note: CCXT 4.x returns a list. Filter by symbol.
                    target = next((p for p in positions if p.get('symbol') == sym), None)
                    if target:
                        contracts = float(target.get('contracts') or 0.0)
                        side = str(target.get('side') or 'long')
                        size = contracts if side == 'long' else -contracts
                        avg_price = float(target.get('entryPrice') or 0.0)
                        unrealized_pnl = float(target.get('unrealizedPnl') or 0.0)
                        pnl_pct = float(target.get('percentage') or 0.0)
                except Exception as e:
                    logger.warning(f"[CCXT] Snapshot fetch_positions failed for {sym} on {self.exchange_id}: {e}")
            else:
                # Spot: fetch_balance
                base = sym.split("/")[0] if "/" in sym else sym
                try:
                    bal = self._exchange.fetch_balance()
                    total = bal.get("total", {})
                    size = float(total.get(base, 0.0))
                except Exception as e:
                    logger.warning(f"[CCXT] Snapshot fetch_balance failed for {sym} on {self.exchange_id}: {e}")
                    size = 0.0

                # [FIX] Define min_amount BEFORE checking it!
                min_amount = None
                if sym in self._exchange.markets:
                    market = self._exchange.markets[sym]
                    limits = market.get("limits", {})
                    amount_limits = limits.get("amount", {})
                    min_amount = float(amount_limits.get("min", 0.0) or 0.0)

                # Fallback to configured quantity step if API limit is missing
                if min_amount is None or min_amount == 0.0:
                     # 'symbol' is the internal key (e.g. DOGEUSDT), which is used in crypto_qty_steps
                    qty_steps = getattr(self.profile, "crypto_qty_steps", {})
                    min_amount = float(qty_steps.get(symbol, 0.0) or 0.0)

                # [ANTIGRAVITY FIX] Track dust positions for management
                if min_amount is not None and min_amount > 0 and abs(size) > 0 and abs(size) < min_amount:
                   # Only warn once per symbol to avoid log spam
                   if symbol.upper() not in self._dust_warned:
                       logger.warning(f"[CCXT] Position {sym} below minimum tradeable size: {size} < {min_amount} (cannot scale)")
                       self._dust_warned.add(symbol.upper())

                # [ANTIGRAVITY FIX] Coinbase "Hidden Balance" Fallback
                # If size is 0, we check if it's locked by open orders.
                if abs(size) == 0 and "coinbase" in self.exchange_id:
                    try:
                        orders = self._exchange.fetch_open_orders(sym)
                        for o in orders:
                            # Look for STOP orders
                            is_stop = o.get("type") in ("stop", "stop_market", "stop_limit") or o.get("info", {}).get("stop_price")
                            if not is_stop:
                                 if o.get("info", {}).get("order_configuration", {}).get("stop_limit_stop_limit_gtc"):
                                     is_stop = True
                            
                            if is_stop:
                                size = float(o.get("amount", 0.0))
                                logger.info(f"[CCXT] Detected hidden balance for {symbol} locked in stop {o['id']}: {size}")
                                break
                        
                        # If still 0, check position_hold_store record fallback
                        if abs(size) == 0 and self.position_hold_store:
                            record = self.position_hold_store.get(symbol)
                            if record and record.size:
                                size = record.size
                                logger.info(f"[CCXT] Using record fallback size for {symbol}: {size}")
                    except Exception as e:
                        logger.warning(f"[CCXT] Hidden balance check failed for {symbol}: {e}")

            # Fallback PnL calculation if missing from exchange or for spot
            if abs(size) > 0:
                ticker = self._safe_fetch_ticker(sym)
                if ticker:
                    current_price = ticker.last
                
                # Restore entry price from store if missing
                avg_p = avg_price
                record = self.position_hold_store.get(symbol) if self.position_hold_store else None
                if (not avg_p or avg_p == 0) and record and record.entry_price:
                    avg_p = record.entry_price
                    logger.debug(f"[CCXT] Restored entry_price {avg_p} from store for {symbol}")
                
                # Recover from trades if still missing
                if (not avg_p or avg_p == 0):
                    rec_p = self._recover_entry_price_from_trades(sym)
                    if rec_p:
                        avg_p = rec_p
                        logger.info(f"[CCXT] Recovered entry_price {avg_p} from recent trades for {symbol}")
                        if self.position_hold_store:
                            self.position_hold_store.upsert(symbol, _utc_now(), entry_price=avg_p, size=size)
                
                avg_price = avg_p
                
                if avg_p and avg_p > 0 and current_price:
                    unrealized_pnl = (current_price - avg_p) * size
                    # Side-aware PnL %
                    if size > 0:
                        pnl_pct = (current_price / avg_p - 1.0) * 100.0
                    else:
                        pnl_pct = (1.0 - current_price / avg_p) * 100.0
                
            logger.debug(f"[CCXT] Snapshot {sym} | Size={size} | Entry={avg_price} | Last={current_price} | PnL={unrealized_pnl:.2f} ({pnl_pct:.2f}%)")
        except Exception as e:
            logger.error(f"[CCXT] Snapshot fetch failed for {symbol}: {e}", exc_info=True)
            return None
            
        if abs(size) == 0:
            # [ANTIGRAVITY FIX] Reconcile Ghost Positions
            # If size is 0 but we have a record in the store, purge it.
            if self.position_hold_store and self.position_hold_store.get(symbol):
                logger.info(f"[CCXT] Reconciling ghost position for {symbol}: Record exists but balance/orders are zero. Purging record.")
                self.position_hold_store.remove(symbol)
                
            self._scale_in_counts[symbol.upper()] = 0
            return None
            
        return {
            "symbol": symbol.upper(),
            "side": "long" if size > 0 else "short",
            "direction": "long" if size > 0 else "short",
            "size": size,
            "avg_price": avg_price,
            "entry_price": avg_price,
            "stop_loss": float(record.stop_loss) if record and record.stop_loss else None,
            "take_profit": float(record.take_profit) if record and record.take_profit else None,
            "unrealized_pnl": unrealized_pnl,
            "pnl_pct": pnl_pct,
            "scale_ins_taken": int(self._scale_in_counts.get(symbol.upper(), 0)),
            "max_scale_ins_per_leg": int(os.getenv("MAX_SCALE_INS_PER_LEG") or 2),
            "htf_neutral_bars": 0,
            "pyramid_count": 1,
            "htf_neutral_bars": 0,
            "pyramid_count": 1,
            # [ANTIGRAVITY FIX] Enhanced Dust Check: Qty < Min OR Value < $2.50
            "is_dust": (
                (min_amount is not None and min_amount > 0 and abs(size) < min_amount) or
                (current_price is not None and (abs(size) * current_price) < 2.50)
            ),
        }

    def _get_quote_currency(self, symbol: str) -> str:
        """Determine quote currency for a symbol (e.g. BTC/USD -> USD)."""
        try:
            sym = self._map_symbol(symbol)
            # Handle standard CCXT slash symbols
            if "/" in sym:
                # Handle cases like XRP/USD:USD-301220
                if ":" in sym:
                   # Extract the part before the first colon but after the slash
                   match_part = sym.split(":")[0]
                   return match_part.split("/")[1]
                return sym.split("/")[1]
            
            # Handle colon-only if slash missing (unlikely in CCXT but safe)
            if ":" in sym:
                 return sym.split(":")[0].split("-")[0][-3:]

            # Fallback heuristics
            upper_sym = symbol.upper()
            if upper_sym.endswith("USDT"): return "USDT"
            if upper_sym.endswith("USDC"): return "USDC"
            if upper_sym.endswith("USD"): return "USD"
        except Exception:
            pass
        return "USD" # Default

    def _is_permission_denied(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return "permission_denied" in msg or "not allowed to trade futures" in msg

    def _is_insufficient_funds(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            "insufficient_fund" in msg
            or "insufficient funds" in msg
            or "preview_insufficient_funds_for_futures" in msg
        )

    def _extract_balance_amount(self, bal: dict, quote: str) -> float:
        # Standard CCXT extraction
        free = bal.get("free") or {}
        amount = float(free.get(quote, 0.0) or 0.0)
        if amount:
            return amount
        total = bal.get("total") or {}
        amount = float(total.get(quote, 0.0) or 0.0)
        if amount:
            return amount
            
        # [ANTIGRAVITY FIX] Coinbase Futures-specific extraction from 'info' object
        # Coinbase Advanced Trade doesn't always populate free/total for futures in fetch_balance
        if "info" in bal and "balance_summary" in bal["info"]:
            summary = bal["info"]["balance_summary"]
            # Prioritize Buying Power (Margin Available)
            for key in ["futures_buying_power", "available_margin", "total_usd_balance"]:
                if key in summary:
                    val_dict = summary[key]
                    if val_dict.get("currency") == quote:
                        return float(val_dict.get("value", 0.0) or 0.0)
                        
        return 0.0

    def _fetch_balance_for_type(self, balance_type: str) -> dict | None:
        try:
            return self._exchange.fetch_balance({"type": balance_type})
        except Exception:
            return None

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        """Return available Quote Currency balance for trading.
        
        Args:
            symbol: The symbol we intend to trade (e.g. BTCUSD). 
                   Used to determine if we need USD, USDT, or USDC balance.
        """
        try:
            balances = []
            try:
                default_bal = self._exchange.fetch_balance()
                balances.append(default_bal)
            except Exception as e:
                logger.warning(f"[CCXT] fetch_balance(default) failed: {e}")

            dtype = (self.default_type or os.getenv("CCXT_DEFAULT_TYPE") or "spot").lower()
            if dtype in {"future", "swap", "option", "margin"}:
                for balance_type in ("future", "swap", "derivatives", "contract", "futures"):
                    try:
                        bal = self._fetch_balance_for_type(balance_type)
                        if bal:
                            balances.append(bal)
                    except Exception as e:
                        logger.debug(f"[CCXT] fetch_balance({balance_type}) failed: {e}")
            
            target_quote = "USD"
            if symbol:
                target_quote = self._get_quote_currency(symbol)

            amount = 0.0
            found_types = []
            for i, bal in enumerate(balances):
                val = self._extract_balance_amount(bal, target_quote)
                # Fallback: Check USDC if the target is USD and we have 0
                if val <= 0 and target_quote == "USD":
                    val = self._extract_balance_amount(bal, "USDC")
                
                # [ANTIGRAVITY FIX] Fallback: Check USD if target is USDC (Coinbase Collateral)
                if val <= 0 and target_quote == "USDC":
                    val = self._extract_balance_amount(bal, "USD")
                
                if val > 0:
                    found_types.append(f"idx_{i}:${val:.2f}")
                amount = max(amount, val)
            
            if found_types:
                logger.info(f"[CCXT] get_liquid_capital({symbol}) -> sources: {', '.join(found_types)} | winner=${amount:.2f}")
            else:
                logger.debug(f"[CCXT] get_liquid_capital({symbol}) -> no {target_quote} (or USDC) found in {len(balances)} balance objects")

            # [ANTIGRAVITY FIX] Reset latch if we have funds
            if amount >= 1.10:
                if self.capital_exhausted:
                    logger.info(f"[CCXT] Capital recovered: ${amount:.2f} available. Unlatching guard.")
                self.capital_exhausted = False
            
            return amount
            
        except Exception as exc:
            logger.warning("[CCXT] get_liquid_capital failed: %s", exc)
            return 0.0


    def update_position_metadata(self, symbol: str, snapshot) -> None:
        """Update trailing stop metadata for open positions."""
        if not self.position_hold_store or not snapshot:
            return
        if not getattr(self.profile, "trailing_stop_enabled", False):
            return
        record = self.position_hold_store.get(symbol)
        if not record or not record.entry_price or not record.size:
            return
        current_price = None
        if snapshot.candles:
            current_price = float(snapshot.candles[-1].close)
        if not current_price or current_price <= 0:
            return
        direction = "long" if record.size > 0 else "short"
        entry_price = float(record.entry_price)
        if direction == "long":
            profit_pct = (current_price / entry_price - 1.0) * 100.0
        else:
            profit_pct = (1.0 - current_price / entry_price) * 100.0
        min_profit_pct = float(getattr(self.profile, "trailing_stop_min_profit_pct", 1.0))
        if profit_pct < min_profit_pct:
            return

        htf_candles = snapshot.htf_candles or snapshot.candles
        if not htf_candles:
            return
        swing_lookback = int(getattr(self.profile, "trend_swing_lookback", 2))
        struct_range = last_structure_range(htf_candles, swing_lookback=swing_lookback)
        if not struct_range:
            return
        last_high, last_low = struct_range
        new_stop = float(last_low if direction == "long" else last_high)
        if new_stop <= 0:
            return
        current_stop = float(record.stop_loss or 0.0)
        # Only tighten the stop in the profit direction and avoid immediate triggers.
        if direction == "long":
            if new_stop <= current_stop or new_stop >= current_price:
                return
            if current_stop > 0 and (new_stop - current_stop) / current_stop < 0.001:
                return
        else:
            if (current_stop > 0 and new_stop >= current_stop) or new_stop <= current_price:
                return
            if current_stop > 0 and (current_stop - new_stop) / current_stop < 0.001:
                return

        pos = self.get_open_position_snapshot(symbol)
        if not pos or pos.get("is_dust", False):
            return
        qty = abs(float(pos.get("size", 0.0)))
        if qty <= 0:
            return

        try:
            sym = self._map_symbol(symbol)
            try:
                open_orders = self._exchange.fetch_open_orders(sym)
                for o in open_orders:
                    is_stop = o.get("type") in ("stop", "stop_market", "stop_limit") or o.get("info", {}).get("stop_price")
                    if not is_stop and "coinbase" in self.exchange_id:
                        if o.get("info", {}).get("order_configuration", {}).get("stop_limit_stop_limit_gtc"):
                            is_stop = True
                    if is_stop:
                        self._exchange.cancel_order(o["id"], sym)
                        logger.info(f"[CCXT] Cancelled existing stop {o['id']} for trailing update.")
            except Exception as e:
                logger.warning(f"[CCXT] Failed to cancel existing stops for trailing update: {e}")

            stop_side = "sell" if direction == "long" else "buy"
            stop_params = {"stopPrice": new_stop}
            order_type = "stop_market"
            limit_price = None
            if "coinbase" in self.exchange_id.lower():
                order_type = "limit"
                raw_limit = new_stop * 0.95 if stop_side == "sell" else new_stop * 1.05
                limit_price = float(self._exchange.price_to_precision(sym, raw_limit))
                stop_params["stop_price"] = self._exchange.price_to_precision(sym, new_stop)
                stop_params["stop_direction"] = "STOP_DIRECTION_STOP_DOWN" if stop_side == "sell" else "STOP_DIRECTION_STOP_UP"

            stop_qty = float(self._exchange.amount_to_precision(sym, qty))
            self._exchange.create_order(sym, order_type, stop_side, stop_qty, limit_price, stop_params)
            logger.info(f"[CCXT] Trailing SL updated for {symbol}: {current_stop} -> {new_stop} (qty={stop_qty})")
            self.position_hold_store.upsert(symbol, _utc_now(), stop_loss=new_stop, entry_price=entry_price, size=record.size)
        except Exception as exc:
            logger.warning(f"[CCXT] Failed to update trailing stop for {symbol}: {exc}")

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        # Kill-switch check
        if self._consecutive_errors >= 5:
            if self._last_error_ts and (time.time() - self._last_error_ts) >= 300:
                logger.warning("[CCXT] Kill-switch cooldown elapsed; resetting consecutive error counter.")
                self._consecutive_errors = 0
            else:
                return (
                    ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "kill-switch: too many errors"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "kill-switch"),
                )

        # Passthrough actions
        if decision.action in {"stand_aside", "hold"}:
            return (
                ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "stand aside"),
                ExecutionOutcome(ExecutionOutcomeType.SKIPPED, decision.symbol, "stand aside"),
            )

        # Handle Flips (Atomic Flatten + New Entry)
        action = decision.action
        if action == "flip_to_short":
             self.flatten_symbol(decision.symbol)
             action = "enter_short"
        elif action == "flip_to_long":
             self.flatten_symbol(decision.symbol)
             action = "enter_long"

        # Determine direction and validation
        default_type = (os.getenv("CCXT_DEFAULT_TYPE") or "spot").lower()
        provider = (os.getenv("EXCHANGE_PROVIDER") or settings.market.exchange_provider or "").strip().lower()
        broker_mode = (os.getenv("BROKER_MODE") or settings.market.broker_mode or "").strip().lower()
        profile_name = (os.getenv("PROFILE_NAME") or "").strip().lower()
        alt_md = (os.getenv("ALTERNATIVE_MARKET_DATA") or "").strip().lower()
        is_future = (default_type in {"future", "swap"} or provider == "coinbase_futures" or broker_mode == "coinbase_futures" or profile_name == "coinbase_futures" or alt_md == "coinbase_futures")
        
        if action == "enter_short" and not is_future:
            return (
                ExecutionResult(ExecutionStatus.UNSUPPORTED_SYMBOL_CONFIG, decision.symbol, "short not supported in spot mode"),
                ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, "short not supported in spot mode"),
            )

        # Map logic
        sym = self._map_symbol(decision.symbol)
        side = "buy"
        if action in {"enter_short"}:
             side = "sell"
        elif action == "enter_long":
             side = "buy"
        elif action == "scale_in":
             # Scale in direction depends on existing position
             pos = self.get_open_position_snapshot(decision.symbol)
             if pos and pos.get("is_dust", False):
                logger.info(f"[DUST] Ignoring scale_in for {decision.symbol} (size={pos.get('size')}) as it's a dust position.")
                return (
                    ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "dust position, cannot scale in"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "dust position"),
                )
             if pos and pos.get("side") == "short":
                 side = "sell"
             else:
                 side = "buy"

        # Scale Out logic
        if action == "scale_out":
            pos = self.get_open_position_snapshot(decision.symbol)
            if not pos:
                return (
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "no position to scale out"),
                    ExecutionOutcome(ExecutionOutcomeType.SKIPPED, decision.symbol, "no position"),
                )
            # Close 50%
            size = float(pos.get("size", 0.0))
            qty = abs(size) * 0.5
            close_side = "buy" if size < 0 else "sell"
            
            try:
                order = self._exchange.create_order(sym, "market", close_side, qty)
                return self._ok(decision.symbol, "scale_out market", [str(order.get("id"))])
            except Exception as e:
                logger.error(f"[CCXT] Scale Out failed: {e}")
                return (
                    ExecutionResult(ExecutionStatus.PROVIDER_ERROR, decision.symbol, f"scale_out failed: {e}"),
                    ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, f"scale_out failed: {e}"),
                )
        
        if action == "close_position":
            self.flatten_symbol(decision.symbol)
            return (
                ExecutionResult(ExecutionStatus.EXECUTED, decision.symbol, "flatten requested"),
                ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, decision.symbol, "flatten requested"),
            )

        # Entry Logic (enter_long, enter_short, scale_in)
        if action in {"enter_long", "enter_short", "scale_in"}:
            MIN_ORDER_VAL = 1.10
            if self.capital_exhausted:
                liq_cap = self.get_liquid_capital(decision.symbol)
                if liq_cap < MIN_ORDER_VAL:
                    logger.info(
                        f"[CCXT] Capital exhausted (${liq_cap:.2f} < ${MIN_ORDER_VAL:.2f}); skipping new entry."
                    )
                    return (
                        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "capital exhausted"),
                        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "capital exhausted"),
                    )
                self.capital_exhausted = False

            # [ANTIGRAVITY FIX] Query Balance First (Quote Currency Specific)
            liq_cap = self.get_liquid_capital(decision.symbol)
            if liq_cap < MIN_ORDER_VAL:
                self.capital_exhausted = True
                logger.error(f"[CCXT] Insufficient liquid capital: ${liq_cap:.2f}")
                return (
                    ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "capital exhausted"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "capital exhausted"),
                )
            
            # [ANTIGRAVITY FIX] Reset latch if we have funds
            self.capital_exhausted = False

            # [ANTIGRAVITY FIX] Risk-Based Sizing
            # 1. Determine Risk Amount from AI pct
            risk_pct = getattr(decision, "risk_per_trade_pct", 1.0) or 1.0
            fixed_risk = float(getattr(self.profile, "risk_per_trade_dollars", 0.0) or 0.0)

            # [ANTIGRAVITY FEATURE] "YOLO Ratchet": Multi-Tier Capital Scale
            # 100% (<$500), 50% (<$2k), 30% (<$100k), 10% (<$200k), 5% (>$200k)
            ratchet_enabled = getattr(self.profile, "ratchet_risk_enabled", True)
            if fixed_risk <= 0 and risk_pct >= 0.99 and ratchet_enabled:
                try:
                    old_risk = risk_pct
                    if liq_cap < 500.0:
                        risk_pct = 1.0
                    elif liq_cap < 2000.0:
                        risk_pct = 0.50
                    elif liq_cap < 100000.0:
                        risk_pct = 0.30
                    elif liq_cap < 200000.0:
                        risk_pct = 0.10
                    else:
                        risk_pct = 0.05
                    
                    if risk_pct != old_risk:
                        logger.info(f"[RISK RATCHET] Capital ${liq_cap:.2f}: Scaling risk to {risk_pct:.0%}")
                except Exception as e:
                    logger.warning(f"[RISK RATCHET] Tier logic failed: {e}. Defaulting to {risk_pct:.0%}")

            # 1. Determine Risk Amount
            if fixed_risk > 0:
                risk_amount = min(fixed_risk, liq_cap)
                risk_pct = (risk_amount / liq_cap) if liq_cap > 0 else 0.0
            else:
                risk_amount = liq_cap * risk_pct
            
            # 2. Get Price Data
            ticker = self._safe_fetch_ticker(sym)
            if not ticker or not ticker.last:
                 logger.error(f"[CCXT] No ticker data for {sym}")
                 return (
                    ExecutionResult(ExecutionStatus.PROVIDER_ERROR, decision.symbol, "no ticker data"),
                    ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, "no ticker"),
                 )
            entry_price = float(ticker.last)
            
            # 3. Calculate Position Size via Stop Distance
            stop_loss = getattr(decision, "stop_loss", 0.0) or 0.0
            
            if stop_loss <= 0.0:
                logger.warning(f"[CCXT] No stop loss provided for {sym}; defaulting to 1x risk amount sizing")
                pos_size_usd = risk_amount
            else:
                 dist = abs(entry_price - stop_loss)
                 dist_pct = dist / entry_price
                 
                 # [ANTIGRAVITY FIX] Sanity Check: Enforce minimum stop distance for sizing
                 MIN_STOP_DIST_PCT = 0.005 # 0.5%
                 if dist_pct < MIN_STOP_DIST_PCT:
                     effective_dist = entry_price * MIN_STOP_DIST_PCT
                     logger.warning(
                         f"[CCXT] Stop distance too tight ({dist_pct:.2%}); "
                         f"using min {MIN_STOP_DIST_PCT:.1%} ({effective_dist:.4f}) for sizing safety."
                     )
                     dist = effective_dist
                 
                 if dist == 0:
                     pos_size_usd = risk_amount
                 else:
                     shares = risk_amount / dist
                     pos_size_usd = shares * entry_price

            # 4. Apply Constraints (Min/Max Notional)
            min_notional = float(getattr(self.profile, "crypto_min_notional_usd", 20.0))
            max_notional = float(getattr(self.profile, "crypto_max_notional_usd", 10000.0) or 10000.0)
            
            # [ANTIGRAVITY FIX] Ensure we hit MIN even if it exceeds risk bucket
            if pos_size_usd < min_notional:
                logger.info(f"[CCXT] Boosting size to min_notional: ${pos_size_usd:.2f} -> ${min_notional:.2f}")
                pos_size_usd = min_notional
            
            pos_size_usd = min(pos_size_usd, max_notional)
            
            # [ANTIGRAVITY FIX] Balance Cap (Safety Net)
            # For Coinbase Futures, the margin is ~$85. If we have $88, we can trade 1 contract (~$300 value).
            # We bypass the 95% cap IF it's a futures contract and we are at the min_notional.
            is_futures_profile = "futures" in str(getattr(self.profile, "name", "")).lower()
            
            # [ANTIGRAVITY CONFIG] Read from profile/env, default to 0.95 (Safety)
            # If the user sets this to 0.70 in the GUI, it will be respected here.
            cfg_cap = float(getattr(self.profile, "balance_cap_pct", 0.95))
            
            safe_balance_cap = liq_cap * cfg_cap
            
            if pos_size_usd > safe_balance_cap:
                if is_futures_profile and pos_size_usd <= min_notional * 1.5:  # Allow some wiggle room for 1 contract
                    logger.info(f"[CCXT] Margin Check: Allowing ${pos_size_usd:.2f} position on ${liq_cap:.2f} balance (Futures Margin Mode)")
                else:
                    logger.warning(
                        f"[CCXT] Capping position size at safe balance limit ({cfg_cap:.0%}): "
                        f"${pos_size_usd:.2f} -> ${safe_balance_cap:.2f} (Cap=${liq_cap:.2f})"
                    )
                    pos_size_usd = safe_balance_cap
            
            # [ANTIGRAVITY FIX] Minimum Order Size Guard
            # Coinbase min is often $1.00. We set $1.10 to be safe.
            if pos_size_usd < MIN_ORDER_VAL:
                 self.capital_exhausted = True
                 # [ANTIGRAVITY FEATURE] Auto-Liquidity: Check USDT
                 if self._attempt_auto_liquidation_usdt(MIN_ORDER_VAL):
                      logger.info(f"[CCXT] Auto-liquidation successful. Retrying entry for {decision.symbol}...")
                      # Recursively retry execution with new funds
                      return self.execute_decision(decision)
                 
                 logger.warning(
                     f"[CCXT] Skipping entry for {decision.symbol}: "
                     f"Calculated size ${pos_size_usd:.2f} < Min ${MIN_ORDER_VAL} (Capital=${liq_cap:.2f})"
                 )
                 return (
                     ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "capital exhausted < min order"),
                     ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "capital exhausted"),
                 )

            # 5. Determine 'amount' for create_order
            # Standard CCXT: amount is Base Currency (Coins)
            # Coinbase Market Buy (with requiresPrice=False): amount is Cost (USD)
            qty_base = pos_size_usd / entry_price
            min_amount_limit = None
            
            # [ANTIGRAVITY FIX] Handle Futures Contract Sizing (e.g. 1 SHIB contract = 10,000 SHIB)
            if is_future:
                market = self._exchange.market(sym)
                c_size = market.get("contractSize")
                min_amount_limit = market.get("limits", {}).get("amount", {}).get("min") or 1.0
                if c_size and c_size > 1.0:
                    logger.info(f"[CCXT] Adjusting for Contract Size: {qty_base:.4f} units / {c_size} = {qty_base/c_size:.4f} contracts")
                    qty_base = qty_base / c_size
                
                # Round to integer for futures contracts (usually) and clamp to min.
                if qty_base > 0 and qty_base < min_amount_limit:
                    logger.warning(
                        f"[CCXT] Clamping {qty_base:.4f} to min contract size {min_amount_limit} for {sym}"
                    )
                    qty_base = min_amount_limit
                else:
                    # [ANTIGRAVITY FIX] Use ceil for small positions to avoid truncation to 0
                    if qty_base > 0 and qty_base < 1.0:
                         logger.info(f"[CCXT] Sizing: Rounding {qty_base:.4f} up to 1 contract for {sym}")
                         qty_base = 1.0
                    else:
                         qty_base = int(round(qty_base))
            
            send_amount = qty_base
            is_coinbase = "coinbase" in self.exchange_id.lower()
            
            if is_coinbase and side == "buy" and not is_future:
                # For Coinbase SPOT Market Buy, send Cost (USD)
                send_amount = pos_size_usd
                logger.info(f"[CCXT] Coinbase Spot Buy: Sending quote amount ${send_amount:.2f}")
            else:
                # For Futures (or entries other than buy), send Base Amount (Contracts/Coins)
                send_amount = qty_base
                logger.info(f"[CCXT] Entry: Sending base amount {send_amount} {sym} (~${pos_size_usd:.2f})")

            logger.info(
                f"[CCXT] Sizing: Cap=${liq_cap:.2f} Risk={risk_pct:.1%} (${risk_amount:.2f}) "
                f"Entry={entry_price:.4f} Stop={stop_loss:.4f} -> Size=${pos_size_usd:.2f}"
            )

            # [ANTIGRAVITY FIX] Dynamic Affordability Check (Smart Pre-Flight)
            # Prevent "INSUFFICIENT_FUNDS" by pre-calculating Margin + Fees.
            # CRITICAL: Only apply to OPENING entries (enter_long, enter_short, scale_in).
            # Closing positions (reduce_position, close_position) RELEASES margin, so never block them.
            if is_future and decision.action in {"enter_long", "enter_short", "scale_in"}:
                # 1. Estimate Margin (Coinbase Nano default is ~5x / 20%, or 25x / 4%)
                # We use 5x (20%) as the conservative baseline to ensure safety.
                leverage_safety_factor = 5.0 
                
                # [ANTIGRAVITY FIX] Handle Multipliers (Contract Size)
                # Some futures have multipliers (e.g. LTC=5, ETH=0.1).
                # Nanos: 1 Contract = Multiplier * Price.
                market_info = self._exchange.market(sym)
                c_size = market_info.get("contractSize") or 1.0
                
                # [ANTIGRAVITY CORRECTION] Use send_amount (Integer Contracts) for accuracy.
                # pos_size_usd might be $20 (min notional), but if 1 Contract = $330, send_amount will be 1.
                # We must check if we can afford the ACTUAL rounded-up contract.
                
                # send_amount is 'Quantity of Contracts' for Futures (set in line 918)
                true_notional = send_amount * entry_price * c_size
                
                est_margin_cost = true_notional / leverage_safety_factor
                
                # 2. Estimate Fees (Taker ~0.06% + Buffer -> 0.1% of Notional)
                est_fees = true_notional * 0.001
                
                # 3. Total Cash Required
                required_cash = est_margin_cost + est_fees
                
                # 4. Check Real-Time Free Balance
                # (We re-fetch specifically right before order to catch recent changes)
                try:
                    # [ANTIGRAVITY FIX] Coinbase Advanced uses SPOT wallet for Futures collateral.
                    # We must explicitly fetch type='spot' to see the funds.
                    bal_check = self._exchange.fetch_balance({'type': 'spot'})
                    
                    # Coinbase Futures uses USD or USDC collateral
                    free_collateral = float(bal_check.get("free", {}).get("USD", 0.0)) + float(bal_check.get("free", {}).get("USDC", 0.0))
                    
                    if free_collateral < required_cash:
                        logger.warning(
                            f"[CCXT] AFFORDABILITY BLOCK: Required ${required_cash:.2f} "
                            f"(Margin ${est_margin_cost:.2f} + Fees ${est_fees:.2f} for {send_amount} contracts) > Free ${free_collateral:.2f}"
                        )
                        return (
                            ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, f"unaffordable: req ${required_cash:.2f} > free ${free_collateral:.2f}"),
                            ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "insufficient funds (pre-check)"),
                        )
                    else:
                         logger.info(f"[CCXT] Affordability OK: Required ${required_cash:.2f} <= Free ${free_collateral:.2f}")

                except Exception as e:
                    logger.warning(f"[CCXT] Failed to verify affordability (blocking entry): {e}")
                    return (
                        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "affordability check failed"),
                        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "affordability check failed"),
                    )

            # Entry Execution
            try:
                # [ANTIGRAVITY FIX] Strict Min Amount Check
                # [ANTIGRAVITY FIX] Strict Min Amount Check with Safety Map
                try:
                    market = self._exchange.market(sym)
                    min_amount_limit = min_amount_limit or market.get('limits', {}).get('amount', {}).get('min')
                except Exception:
                    logger.debug(f"[CCXT] market({sym}) info missing; using fallback min amount.")
                
                min_amount_limit = min_amount_limit or (1.0 if is_future else 0.000001)
                
                if send_amount < min_amount_limit:
                    # Attempt round up if close (within 80%? No, simplistic check for now: if integer needed and > 0.5)
                     if is_future and send_amount >= 0.5 and min_amount_limit == 1.0:
                          logger.info(f"[CCXT] Sizing: Rounding {send_amount} UP to min 1.0 contract")
                          send_amount = 1.0
                     else:
                          logger.warning(f"[CCXT] Blocked Entry: Amount {send_amount} < Min {min_amount_limit} for {sym}")
                          return (
                              ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, f"amount {send_amount:.4f} < min {min_amount_limit}"),
                              ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "min quantity limit"),
                          )

                # Place Entry
                order = self._exchange.create_order(sym, "market", side, send_amount)
                self._track_local_order(sym, order)
                entry_id = str(order.get("id"))
                logger.info(f"[CCXT] Placed {side} market order {entry_id} for {send_amount} {sym}")
                
                # [ANTIGRAVITY FIX] Persist Position in Store with Entry Price
                avg_fill = float(order.get("average") or order.get("price") or 0.0)
                # [ANTIGRAVITY FIX] Persist Position in Store (will be updated again after SL check)
                avg_fill = float(order.get("average") or order.get("price") or 0.0)
                if self.position_hold_store:
                    self.position_hold_store.upsert(
                        decision.symbol, 
                        _utc_now(), 
                        stop_loss=decision.stop_loss,
                        entry_price=avg_fill,
                        take_profit=decision.take_profit,
                        size=float(order.get("filled") or 0.0) or qty_base
                    )
                
                # Stop Loss Placement (CRITICAL UPGRADE)
                if decision.stop_loss and decision.stop_loss > 0:
                    stop_side = "sell" if side == "buy" else "buy"
                    
                    # [ANTIGRAVITY FIX] Settlement Race Condition Waiter
                    # Wait for funds to settle (appear in free balance) before placing stop
                    if side == "buy" and not is_future:
                        logger.info(f"[CCXT] Waiting for {sym} settlement (up to 10s)...")
                        base_curr = decision.symbol.split('/')[0]
                        # We expect at least the filled amount to be free
                        # [ANTIGRAVITY FIX] Handle NoneType if 'filled' is None (use send_amount as fallback)
                        fill_qty = order.get("filled")
                        if fill_qty is None:
                            fill_qty = send_amount
                        expected_min = float(fill_qty) * 0.9 # 10% tolerance
                        for _ in range(5): # 5 attempts x 2s = 10s
                            try:
                                bal = self._exchange.fetch_balance()
                                free_amt = float(bal.get("free", {}).get(base_curr, 0.0))
                                if free_amt >= expected_min:
                                    logger.info(f"[CCXT] Settlement confirmed: {free_amt} {base_curr} available.")
                                    break
                            except Exception as wait_e:
                                logger.warning(f"[CCXT] Balance check failed: {wait_e}")
                            time.sleep(2.0)
                        else:
                             logger.warning(f"[CCXT] Settlement timeout. Proceeding with SL anyway (might fail).")

                    try:
                        # [ANTIGRAVITY FIX] For Scale-In (Pyramiding), we MUST consolidate stops.
                        # 1. Cancel existing stops for this symbol
                        if action == "scale_in":
                            logger.info(f"[CCXT] Scale-In detected: Cancelling existing stops for {sym} to consolidate protection.")
                            try:
                                open_orders = self._exchange.fetch_open_orders(sym)
                                for o in open_orders:
                                    # Identify Stop orders (stop_market, stop_limit, or orders with stopPrice)
                                    # Note: 'type' might be 'limit' for Coinbase stops
                                    is_stop = o.get("type") in ("stop", "stop_market", "stop_limit") or o.get("info", {}).get("stop_price")
                                    # Coinbase specific check
                                    if not is_stop and "coinbase" in self.exchange_id:
                                         if o.get("info", {}).get("order_configuration", {}).get("stop_limit_stop_limit_gtc"):
                                             is_stop = True
                                    
                                    if is_stop:
                                        self._exchange.cancel_order(o["id"], sym)
                                        logger.info(f"[CCXT] Cancelled existing stop {o['id']} for consolidation.")
                            except Exception as e:
                                logger.warning(f"[CCXT] Failed to cancel existing stops during scale-in: {e}")

                        # Attempt to place Stop Market order
                        # Common params for unified CCXT: 'stopPrice', 'triggerPrice'
                        stop_params = {
                            "stopPrice": decision.stop_loss, # Legacy/Common
                            # "reduceOnly": True, # Recommended for futures
                        }
                        if is_future:
                            stop_params["reduceOnly"] = True
                            
                        # Try 'stop_market' type first (Binance, Bybit), unless Coinbase which needs stop_limit
                        # Default to stop_market (Binance, Bybit, etc.)
                        order_type = "stop_market"
                        limit_price = None

                        # [ANTIGRAVITY FIX] Verified Coinbase Stop-Limit Parameters
                        is_coinbase = "coinbase" in self.exchange_id.lower() or "coinbase" in getattr(self._exchange, "id", "").lower()
                        
                        if is_coinbase:
                            # Coinbase Advanced requires type="limit" + stop_price in params
                            order_type = "limit"
                            # Calculate aggressive limit price (5% buffer) to ensure fill (emulate market stop)
                            raw_limit = decision.stop_loss * 0.95 if stop_side == "sell" else decision.stop_loss * 1.05
                            limit_price = float(self._exchange.price_to_precision(sym, raw_limit))
                            
                            # Update params with Coinbase-specific fields
                            stop_params["stop_price"] = self._exchange.price_to_precision(sym, decision.stop_loss)
                            stop_params["stop_direction"] = "STOP_DIRECTION_STOP_DOWN" if stop_side == "sell" else "STOP_DIRECTION_STOP_UP"
                            
                            logger.info(f"[CCXT] Coinbase SL: type=limit, stop={stop_params['stop_price']}, limit={limit_price}, dir={stop_params['stop_direction']}")

                        # [ANTIGRAVITY FIX] Correct Stop Loss Quantity
                        # 1. Start with the *current trade* filled amount
                        current_fill = order.get("filled", 0.0)
                        if not current_fill or current_fill <= 0:
                             current_fill = qty_base * 0.995 # Fallback to intended
                        
                        stop_qty = current_fill

                        # 2. If Scale-In, add existing position size to cover EVERYTHING
                        if action == "scale_in":
                            try:
                                # We need the *previous* size (before this trade update propagates entirely? or refetch?)
                                # Better to fetch fresh snapshot or use tracking
                                # But we just placed an order. The snapshot might not reflect it yet, OR it might.
                                # Let's fetch snapshot again or rely on what we know.
                                # Safest: Fetch account position size (if real-time) or estimate.
                                # Since we just placed the order, the exchange info should be mostly up to date if we fetch now.
                                # Or better: fetch_position specifically.
                                # Simplified: Use `get_open_position_snapshot` loop logic? That caches.
                                # Let's try to fetch fresh balance/position if possible.
                                # For now, let's rely on `self.get_open_position_snapshot(decision.symbol)` which called before this block?
                                # That snapshot was pre-entry.
                                pre_entry_pos = self.get_open_position_snapshot(decision.symbol)
                                pre_size = abs(float(pre_entry_pos.get("size", 0.0))) if pre_entry_pos else 0.0
                                
                                total_qty = pre_size + stop_qty
                                logger.info(f"[CCXT] Pyramiding: Consolidating Stop Size: {pre_size} (Existing) + {stop_qty} (New) = {total_qty}")
                                stop_qty = total_qty
                            except Exception as e:
                                logger.error(f"[CCXT] Failed to calculate total scale_in size: {e}")
                                # Fallback to just protecting new chunk to allow *something*
                        
                        else:
                            logger.info(f"[CCXT] Using filled amount for SL: {stop_qty:.6f}")
                        
                        # [ANTIGRAVITY FIX] Fee Buffer for Spot
                        # If spot trading, fees may be deducted from base asset (e.g. Coinbase).
                        # 'filled' reports gross amount. Verify if we need to reduce qty.
                        if not is_future and stop_side == "sell":  # Long SL on Spot
                            # Coinbase Taker Fee can be ~0.6%. Use 0.99 factor (1% buffer) to be safe.
                            reduced_qty = stop_qty * 0.99
                            logger.info(f"[CCXT] Applied spot fee buffer: {stop_qty} -> {reduced_qty} (0.99x)")
                            stop_qty = reduced_qty
                        
                        # Apply amount precision
                        stop_qty = float(self._exchange.amount_to_precision(sym, stop_qty))

                        stop_order = self._exchange.create_order(sym, order_type, stop_side, stop_qty, limit_price, stop_params)
                        self._track_local_order(sym, stop_order)
                        logger.info(f"[CCXT] Placed Consolidated Stop Loss {stop_side} ({order_type}) at {decision.stop_loss} (qty={stop_qty})")
                    except Exception as e:
                         # [ANTIGRAVITY FIX] Robust Error Handling for Stop Failures
                         logger.error(f"[CCXT] FAILED TO PLACE STOP LOSS for {decision.symbol}: {e}")
                         if not self._is_permission_denied(e):
                             self._consecutive_errors += 1
                             self._last_error_ts = time.time()
                         return (
                            ExecutionResult(ExecutionStatus.ERROR, decision.symbol, f"stop loss failed: {e}"),
                            ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, f"stop loss failed: {e}"),
                         )

                if action == "scale_in":
                    current = int(self._scale_in_counts.get(decision.symbol.upper(), 0))
                    self._scale_in_counts[decision.symbol.upper()] = current + 1
                
                # [ANTIGRAVITY FIX] Final Persistence update with protected size
                if self.position_hold_store:
                     self.position_hold_store.upsert(
                         decision.symbol,
                         _utc_now(),
                         stop_loss=decision.stop_loss,
                         entry_price=avg_fill, # Re-uses from above
                         take_profit=decision.take_profit,
                         size=stop_qty # This is the total protected size
                     )
                    
                return self._ok(decision.symbol, f"{side} market placed + SL", [entry_id])
                
            except Exception as e:
                logger.error(f"[CCXT] Entry failed: {e}")
                if not (self._is_permission_denied(e) or self._is_insufficient_funds(e)):
                    self._consecutive_errors += 1
                    self._last_error_ts = time.time()
                return (
                    ExecutionResult(ExecutionStatus.ERROR, decision.symbol, f"entry failed: {e}"),
                    ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, f"entry failed: {e}"),
                )

        return (
            ExecutionResult(ExecutionStatus.STAND_ASIDE, decision.symbol, "no execution path"),
            ExecutionOutcome(ExecutionOutcomeType.SKIPPED, decision.symbol, "no execution path"),
        )

    def should_block_for_hold(self, symbol: str, decision: AITradeDecision, open_position: dict | None) -> tuple[bool, str | None, float | None]:
        return False, None, None

    def refresh_account_summary(self) -> None:
        return

    def evaluate_synthetic_stops(self, market_provider, timeframe: str) -> Iterable[ExecutionResult]:
        # [ANTIGRAVITY UPGRADE] Order Lifecycle and Stop Loss Re-arming
        # 1. Cancel stale maker orders
        timeout = float(getattr(self.profile, "order_timeout_seconds", 30))
        now = time.time()
        results: list[ExecutionResult] = []
        for local in list(self._local_orders.values()):
            if now - local.created_at < timeout:
                continue
            try:
                self._exchange.cancel_order(local.order_id, local.symbol)
                results.append(ExecutionResult(ExecutionStatus.STAND_ASIDE, local.symbol, "maker timeout canceled"))
            except Exception as e:
                logger.error(f"Failed to cancel order {local.order_id} for {local.symbol}: {e}")
                continue
            self._local_orders.pop(local.order_id, None)
            
        # 2. Stop Loss Re-arming (Self-Healing)
        # If we have an open position but 0 working orders, we might be missing a Stop Loss.
        # This occurs if the initial SL placement failed (e.g. INSUFFICIENT_FUND).
        try:
            # We only do this check occasionally to avoid API fatigue
            if int(now) % 60 < 20: # Every ~60s (20s window)
                logger.info(f"[CCXT] Evaluation cycle: checking protection for active symbols...")
                # Iterate through active symbols that we are trading
                symbols_to_check = set(list(self.symbol_map.keys()))
                for sys_sym in symbols_to_check:
                    # [ANTIGRAVITY FIX] Ignore stablecoins and cash-like assets for protection check
                    if any(x in sys_sym.upper() for x in ("USDT", "USDC", "DAI")):
                         continue
                    if sys_sym.upper() in ("USD", "EUR", "GBP"):
                         continue
                         
                    # Skip if we already have a pending action or recent entry
                    # Actually, the loop handles the candidate cycle. Here we just want to re-arm.
                    state = self._fetch_symbol_state(sys_sym)
                    pos_size = abs(state.get("position_shares", 0))
                    
                    # [ANTIGRAVITY FIX] Robust position check for re-arm
                    if pos_size == 0 and self.position_hold_store:
                        record = self.position_hold_store.get(sys_sym)
                        if record and record.size:
                            # Might be hidden. Check if there are REALLY 0 orders.
                            if state.get("working_orders", 0) == 0:
                                # Hidden position with NO orders? That's definitely broken.
                                pos_size = record.size
                    
                    if pos_size > 0 and state.get("working_orders", 0) == 0:
                        if state.get("is_dust", False):
                            logger.debug(f"[CCXT] {sys_sym} position is dust; skipping auto-protection.")
                            continue
                        # Missing SL!
                        record = self.position_hold_store.get(sys_sym)
                        sl_price = record.stop_loss if record else None
                        
                        if sl_price and sl_price > 0:
                            logger.warning(f"[CCXT] {sys_sym} has position but 0 working orders. Re-arming SL at {sl_price}.")
                            try:
                                # Re-arm logic (re-uses existing create_order logic)
                                # Note: we need to determine the side (sell for long, buy for short)
                                # For now assume long (most common on spot)
                                side = "sell" # Placeholder, improved logic below
                                if state.get("position_shares", 0) < 0:
                                    side = "buy"
                                
                                sym = self._map_symbol(sys_sym)
                                order_type = "stop_market" 
                                limit_price = None
                                stop_params = {"stopPrice": sl_price}
                                
                                if "coinbase" in self.exchange_id.lower():
                                    order_type = "limit"
                                    raw_limit = sl_price * 0.95 if side == "sell" else sl_price * 1.05
                                    limit_price = float(self._exchange.price_to_precision(sym, raw_limit))
                                    stop_params["stop_price"] = self._exchange.price_to_precision(sym, sl_price)
                                    stop_params["stop_direction"] = "STOP_DIRECTION_STOP_DOWN" if side == "sell" else "STOP_DIRECTION_STOP_UP"

                                stop_qty = float(self._exchange.amount_to_precision(sym, abs(state.get("position_shares"))))
                                self._exchange.create_order(sym, order_type, side, stop_qty, limit_price, stop_params)
                                logger.info(f"[CCXT] Successfully re-armed SL for {sys_sym} at {sl_price} (qty={stop_qty})")
                            except Exception as re_arm_exc:
                                logger.error(f"[CCXT] Failed to re-arm SL for {sys_sym}: {re_arm_exc}")
                        else:
                            logger.warning(f"[CCXT] {sys_sym} has position but 0 working orders. Auto-placing default SL...")
                            
                            # [ANTIGRAVITY FIX] Calculate Default SL (5% risk fallback)
                            # Remove invalid self._last_ticker usage
                            # Fix: Map system symbol (ADAUSD) to exchange symbol (ADA/USD)
                            ticker = self._safe_fetch_ticker(self._map_symbol(sys_sym))
                            
                            if ticker and ticker.last:
                                last = float(ticker.last)
                                raw_size = state.get("position_shares", 0)
                                side = "buy" if raw_size < 0 else "sell" # Closing side
                                
                                # Default 5% distance
                                sl_price = last * 0.95 if side == "sell" else last * 1.05
                                
                                try:
                                    sym = self._map_symbol(sys_sym)
                                    order_type = "stop_market"
                                    limit_price = None
                                    stop_params = {"stopPrice": sl_price}
                                    
                                    if "coinbase" in self.exchange_id.lower():
                                        order_type = "limit"
                                        # Aggressive limit for stop-limit to ensure fill
                                        raw_limit = sl_price * 0.95 if side == "sell" else sl_price * 1.05
                                        limit_price = float(self._exchange.price_to_precision(sym, raw_limit))
                                        stop_params["stop_price"] = self._exchange.price_to_precision(sym, sl_price)
                                        stop_params["stop_direction"] = "STOP_DIRECTION_STOP_DOWN" if side == "sell" else "STOP_DIRECTION_STOP_UP"

                                    stop_qty = float(self._exchange.amount_to_precision(sym, abs(raw_size)))
                                    self._exchange.create_order(sym, order_type, side, stop_qty, limit_price, stop_params)
                                    logger.info(f"[CCXT] AUTO-PROTECTED {sys_sym} with SL at {sl_price} (qty={stop_qty})")
                                    
                                    # Persist this new SL so we don't drift
                                    if self.position_hold_store:
                                        self.position_hold_store.upsert(
                                            sys_sym, 
                                            _utc_now(), 
                                            stop_loss=sl_price, 
                                            size=raw_size
                                        )
                                except Exception as e:
                                    # Silence dust-related errors (min amount precision)
                                    if "minimum amount precision" in str(e) or "INSUFFICIENT" in str(e):
                                        logger.debug(f"[CCXT] Auto-protection skipped for {sys_sym} (dust/min-size): {e}")
                                    else:
                                        logger.error(f"[CCXT] Auto-protection failed for {sys_sym}: {e}")
                            else:
                                logger.warning(f"[CCXT] Could not auto-protect {sys_sym}: No ticker price.")
        except Exception as e:
            logger.error(f"[CCXT] Error in stop loss re-arming check: {e}")

        return results

    def summarize_pnl(self) -> None:
        return

    def _fetch_symbol_state(self, symbol: str) -> dict:
        if not self._is_crypto(symbol):
             return {"position_shares": 0.0, "working_orders": 0, "synthetic_stop_armed": False, "open_parent_shares": {}}
        logger.debug(f"[CCXT] _fetch_symbol_state {symbol}...")
        sym = self._map_symbol(symbol)
        open_orders = 0
        try:
            logger.debug(f"[CCXT] fetch_open_orders {sym}...")
            # Use a slightly stricter timeout here if possible, but globally set is ok
            open_orders = len(self._exchange.fetch_open_orders(sym))
            logger.debug(f"[CCXT] fetch_open_orders {sym} done. count={open_orders}")
        except Exception as e:
            logger.warning(f"[CCXT] fetch_open_orders {sym} failed: {e}")
            open_orders = 0
        pos = self.get_open_position_snapshot(symbol)
        size = float(pos.get("size", 0.0)) if pos else 0.0
        is_dust = pos.get("is_dust", False) if pos else False
        return {"position_shares": size, "working_orders": open_orders, "synthetic_stop_armed": False, "open_parent_shares": {}, "is_dust": is_dust}

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        state = state or self._fetch_symbol_state(symbol)
        # [ANTIGRAVITY FIX] If position is dust, return False so loop treats it as "available to trade" (or ignore)
        if state.get("is_dust", False):
             return False
        return abs(state.get("position_shares", 0.0)) > 0.0 or state.get("working_orders", 0) > 0

    def _map_symbol(self, symbol: str) -> str:
        key = symbol.upper()
        if key in self.symbol_map:
            res = self.symbol_map[key]
            logger.debug(f"[CCXT] mapped {symbol} -> {res}")
            return res
        
        # [ANTIGRAVITY FIX] Fallback to dynamic lookup in loaded markets
        try:
            if not self._exchange.markets:
                self._exchange.load_markets()
            if key in self._exchange.markets:
                return key # CCXT ID matches symbol name for dated futures
        except Exception:
            pass
            
        logger.warning(f"[CCXT] No mapping for {symbol}")
        raise ValueError(f"No CCXT symbol mapping for {symbol}. Set CCXT_SYMBOL_MAP.")

    def _build_exchange(self):
        cls = getattr(ccxt, self.exchange_id, None)
        if cls is None:
            raise ValueError(f"Unknown ccxt exchange '{self.exchange_id}'")
        api_key = os.getenv("CCXT_API_KEY")
        secret = os.getenv("CCXT_SECRET")
        password = os.getenv("CCXT_PASSWORD")
        enable_rate_limit = (os.getenv("CCXT_ENABLE_RATE_LIMIT", "true").lower() == "true")

        # [ANTIGRAVITY FIX] Kraken Specific Credential Mapping
        if "kraken" in self.exchange_id.lower():
            if not api_key: api_key = os.getenv("KRAKEN_API_KEY")
            if not secret: secret = os.getenv("KRAKEN_API_SECRET")
            
        options = {}
        # [ANTIGRAVITY FIX] Coinbase specific fix for market orders
        if "coinbase" in self.exchange_id.lower():
            options["createMarketBuyOrderRequiresPrice"] = False

        default_type = self.default_type or os.getenv("CCXT_DEFAULT_TYPE")
        if default_type:
            options["defaultType"] = default_type
        
        if not api_key or not secret:
            logger.warning("[CCXT] CCXT_API_KEY/SECRET missing. Running in public-only mode?")
        
        # [ANTIGRAVITY FIX] Handle escaped newlines in PEM keys (common .env issue)
        if secret and "\\n" in secret and "\n" not in secret:
             logger.info("[CCXT] Detected escaped newlines in API Secret. Normalizing...")
             secret = secret.replace("\\n", "\n")

        logger.info(f"[CCXT] Initializing exchange {self.exchange_id} (timeout=30s)...")
        ex = cls(
            {
                "apiKey": api_key,
                "secret": secret,
                "password": password,
                "enableRateLimit": enable_rate_limit,
                "timeout": 30000,  # 30 seconds timeout
                "options": options,
            }
        )
        try:
            ex.load_markets()
        except Exception as e:
            logger.warning(f"[CCXT] load_markets failed during init: {e}")
        if os.getenv("CCXT_SANDBOX", "false").lower() == "true":
            try:
                ex.set_sandbox_mode(True)
            except Exception:
                logger.warning("[CCXT] sandbox mode not supported by %s", self.exchange_id)
        
        logger.info(f"[CCXT] Loading markets for {self.exchange_id}...")
        try:
            ex.load_markets()
            logger.info(f"[CCXT] Successfully loaded {len(ex.markets)} markets.")
        except Exception as e:
            logger.error(f"[CCXT] Failed to load markets: {e}")
            raise

        return ex

    def _attempt_auto_liquidation_usdt(self, required_usd: float) -> bool:
        """Attempts to sell USDT for USD if capital is critical."""
        try:
            # 1. Check USDT Balance
            bal = self._exchange.fetch_balance()
            free_usdt = float(bal.get("free", {}).get("USDT", 0.0) or 0.0)
            
            # 2. Check minimal viable conversion (e.g. $5)
            MIN_CONVERSION = 5.0
            if free_usdt < MIN_CONVERSION:
                logger.debug(f"[CCXT] Auto-Liq: Insufficient USDT (${free_usdt}) to convert.")
                return False
                
            logger.info(f"[CCXT] Auto-Liq: Found ${free_usdt} USDT. converting to USD...")
            
            # 3. Execute Market Sell USDT/USD
            # Coinbase symbol: USDT/USD
            symbol = "USDT/USD"
            
            # Sell it all (or up to a safe chunk, e.g. 50? No, user wants capital).
            # Let's sell max available for now.
            qty = free_usdt
            
            # Sanity check symbol existence logic or just try
            order = self._exchange.create_order(symbol, "market", "sell", qty)
            logger.info(f"[CCXT] Auto-Liq: Converted {qty} USDT to USD. Order: {order.get('id')}")
            
            # Sleep briefly to allow balance update propagation?
            time.sleep(1.0)
            return True
            
        except Exception as e:
            logger.error(f"[CCXT] Auto-Liq Failed: {e}")
            return False

    def _recover_entry_price_from_trades(self, symbol: str) -> float | None:
        """Attempts to recover entry price from recent trades (last 10)."""
        try:
            if not self._exchange.has['fetchMyTrades']:
                return None
            
            # Fetch last 10 trades
            trades = self._exchange.fetch_my_trades(symbol, limit=10)
            if not trades:
                return None
            
            # Use the most recent trade's price (simple heuristic)
            last_trade = trades[-1]
            price = float(last_trade.get('price') or 0.0)
            if price > 0:
                return price
            return None
        except Exception as e:
            logger.debug(f"[CCXT] Failed to recover trades for {symbol}: {e}")
            return None

    def _safe_fetch_ticker(self, sym: str) -> Ticker | None:
        try:
            t = self._exchange.fetch_ticker(sym)
            bid = float(t.get("bid")) if t.get("bid") is not None else None
            ask = float(t.get("ask")) if t.get("ask") is not None else None
            last = float(t.get("last")) if t.get("last") is not None else None
            quote_volume = float(t.get("quoteVolume")) if t.get("quoteVolume") is not None else None
            return Ticker(symbol=sym, bid=bid, ask=ask, last=last, volume_24h_quote_usd=quote_volume)
        except Exception as exc:
            logger.debug("[CCXT] ticker fetch failed %s (%s)", sym, exc)
            # [ANTIGRAVITY FIX] Graceful fallback for Commodity Derivatives (OIL/GLD/SIL)
            # These don't support standard ticker fetches on Coinbase but we can use our record price.
            if self.position_hold_store:
                # We can't map back to the 'original' symbol easily here, but we can check the store
                # iterate through records to find matching mapped symbol
                for s, record in self.position_hold_store.load_all().items():
                    if self._map_symbol(s) == sym:
                        logger.info(f"[CCXT] Using fallback price {record.entry_price} from store for {sym}")
                        return Ticker(symbol=sym, bid=record.entry_price, ask=record.entry_price, last=record.entry_price, volume_24h_quote_usd=0)
            return None

    def _track_local_order(self, sym: str, order: dict) -> None:
        oid = str(order.get("id"))
        self._local_orders[oid] = _LocalOrder(order_id=oid, symbol=sym, created_at=time.time(), client_order_id=order.get("clientOrderId"))

    def _ok(self, symbol: str, reason: str, order_ids: list[str] | None = None):
        self._consecutive_errors = 0
        return (
            ExecutionResult(ExecutionStatus.EXECUTED, symbol, reason),
            ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol, reason, order_ids=order_ids),
        )
