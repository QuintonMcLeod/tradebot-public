import logging
import json
import time
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Iterable

from tradebot_sci.broker.execution import ExecutionOutcome, ExecutionResult, ExecutionStatus, ExecutionOutcomeType
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.broker.trade_result_store import TradeResult

logger = logging.getLogger(__name__)

PAPER_STATE_FILE = os.path.join("data", "paper_state.json")

class PaperBroker:
    """A simulated broker for local-only paper trading during Sabbath."""

    # [ANTIGRAVITY] Kraken-level trading friction for realistic paper results.
    # Taker fee: 0.40% (Kraken Pro lowest tier, <$10K 30-day volume, as of Mar 2024)
    # Half-spread: ~0.05% (typical for BTC/ETH majors on Kraken)
    # Slippage: ~0.02% (conservative estimate for moderate-size fills)
    # Total per-leg friction: ~0.47%  |  Round-trip: ~0.94%
    TAKER_FEE_PCT = float(os.getenv("PAPER_TAKER_FEE_PCT", "0.0040"))     # 0.40%
    HALF_SPREAD_PCT = float(os.getenv("PAPER_HALF_SPREAD_PCT", "0.0005"))  # 0.05%
    SLIPPAGE_PCT = float(os.getenv("PAPER_SLIPPAGE_PCT", "0.0002"))        # 0.02%
    
    def __init__(self, profile_settings, market_provider=None, trade_results=None, initial_balance=10000.0):
        self.profile = profile_settings
        self.market_provider = market_provider
        self.trade_results = trade_results
        self.positions = {} # symbol -> position_dict
        self.history = []

        # Load persisted state or fall back to initial balance
        default_balance = float(os.getenv("PAPER_BALANCE", initial_balance))
        saved = self._load_state()
        if saved:
            self.balance = saved.get("balance", default_balance)
            self.positions = saved.get("positions", {})
            logger.info(f"Restored Paper Broker: ${self.balance:.2f} balance, {len(self.positions)} open positions.")
        else:
            self.balance = default_balance
            logger.info(f"Initialized Paper Broker with ${self.balance:.2f} balance (no saved state).")
        
        # [ANTIGRAVITY FIX] Immediate reporting on startup for UI visibility
        self.summarize_pnl()
        self.refresh_account_summary()

    def _load_state(self) -> dict | None:
        """Load persisted paper state from disk."""
        try:
            if os.path.exists(PAPER_STATE_FILE):
                with open(PAPER_STATE_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"[PAPER] Failed to load saved state: {e}")
        return None

    def _save_state(self):
        """Persist current balance and positions to disk."""
        try:
            os.makedirs(os.path.dirname(PAPER_STATE_FILE), exist_ok=True)
            state = {
                "balance": self.balance,
                "positions": self.positions,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp = PAPER_STATE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, PAPER_STATE_FILE)
        except Exception as e:
            logger.warning(f"[PAPER] Failed to save state: {e}")

    def _get_current_price(self, symbol: str) -> float:
        if self.market_provider:
            try:
                ticker = self.market_provider.get_ticker(symbol)
                if ticker and ticker.last:
                    return float(ticker.last)
            except Exception as e:
                logger.warning(f"[PAPER] Could not fetch price for {symbol}: {e}")
        return 100.0 # Fallback

    def get_liquid_capital(self, symbol: str | None = None) -> float:
        return self.balance

    def get_total_balance_value(self) -> float:
        """Sum of cash + unrealized pnl of all paper positions."""
        total = self.balance
        for sym, pos in self.positions.items():
            total += pos.get("unrealized_pnl", 0.0)
        return total

    def refresh_account_summary(self) -> None:
        # [ANTIGRAVITY FIX] Standardized log format to match UI's regex (removed '(PAPER)')
        logger.info(f"[TOTAL] Liquidity available: ${self.balance:.2f}")
        logger.info(f"[CASH] Buying Power: ${self.balance:.2f}")

    def execute_decision(self, decision: AITradeDecision) -> tuple[ExecutionResult, ExecutionOutcome]:
        action = decision.action
        symbol = decision.symbol
        price = self._get_current_price(symbol)
        
        if action in {"enter_long", "enter_short"}:
            # Skip if we already have a position in this symbol
            if symbol in self.positions:
                return (
                    ExecutionResult(ExecutionStatus.STAND_ASIDE, symbol, f"Paper: already holding {symbol}"),
                    ExecutionOutcome(ExecutionOutcomeType.SKIPPED, symbol, f"Paper: duplicate entry blocked")
                )

            side = "buy" if action == "enter_long" else "sell"
            
            # [ANTIGRAVITY FIX] Dynamic Paper Sizing
            # Calculate quantity based on balance and risk_per_trade_pct
            risk_pct = getattr(decision, "risk_per_trade_pct", None) or getattr(self.profile, "risk_per_trade_pct", 0.01)
            risk_usd = self.balance * risk_pct
            
            # Use SL to determine lot size if available, else use risk_usd directly as notional
            if decision.stop_loss and abs(price - decision.stop_loss) > 1e-6:
                risk_per_unit = abs(price - decision.stop_loss)
                qty = risk_usd / risk_per_unit
            else:
                # Fallback: Treat risk_usd as the actual notional size (very conservative for paper)
                qty = risk_usd / price if price > 0 else 0
            
            # [FIX] Leverage-based sizing cap (mirrors OANDA broker L502-510)
            target_leverage = getattr(self.profile, "target_leverage", 1.0) or 1.0
            max_notional = self.balance * target_leverage
            max_qty = max_notional / price if price > 0 else 0
            if qty > max_qty and max_qty > 0:
                logger.warning(
                    f"[PAPER] [LEVERAGE CAP] {symbol}: qty {qty:.4f} -> {max_qty:.4f} "
                    f"(notional ${qty * price:,.0f} exceeds {target_leverage}x leverage cap ${max_notional:,.0f})"
                )
                qty = max_qty

            # Affordability guard: reject if notional exceeds leveraged balance
            notional = qty * price
            if notional > self.balance * max(target_leverage, 1.0) * 1.01:
                logger.warning(f"[PAPER] [BLOCKED] {symbol}: notional ${notional:,.0f} exceeds balance ${self.balance:.2f}")
                return (
                    ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, "Paper: insufficient balance"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_INSUFFICIENT_EQUITY, symbol, "Paper: insufficient balance")
                )

            if qty <= 0:
                return (
                    ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, symbol, "Paper position size too small"),
                    ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, symbol, "Paper size zero")
                )

            # [ANTIGRAVITY] Kraken-level fill simulation: adverse price + taker fee
            friction = self.HALF_SPREAD_PCT + self.SLIPPAGE_PCT
            if side == "buy":
                fill_price = price * (1 + friction)   # Buy higher
            else:
                fill_price = price * (1 - friction)   # Sell lower
            fee_usd = abs(qty * fill_price) * self.TAKER_FEE_PCT
            self.balance -= fee_usd  # Deduct taker fee immediately

            self.positions[symbol] = {
                "symbol": symbol,
                "side": "long" if side == "buy" else "short",
                "size": qty if side == "buy" else -qty,
                "qty": qty, # Explicit qty for easier math
                "entry_price": fill_price,
                "avg_price": fill_price,
                "current_price": price,
                "unrealized_pnl": 0.0,
                "pnl_pct": 0.0,
                "opened_at": datetime.now(timezone.utc).isoformat(),
                "stop_loss": getattr(decision, "stop_loss", None),
                "take_profit": getattr(decision, "take_profit", None)
            }
            logger.info(
                f"[PAPER] [FILL] {symbol} {qty:.4f} @ {fill_price:.5f} "
                f"(mid={price:.5f}, spread+slip={friction*100:.2f}%, fee=${fee_usd:.4f}, Risk=${risk_usd:.2f})"
            )
            self._save_state()
            return (
                ExecutionResult(ExecutionStatus.EXECUTED, symbol, f"Paper {action} executed"),
                ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol, f"Paper {action}")
            )

        if action in {"close_position", "flatten"}:
            if symbol in self.positions:
                pos = self.positions.pop(symbol)
                entry_p = pos["entry_price"]
                # [ANTIGRAVITY] Adverse exit fill + taker fee
                friction = self.HALF_SPREAD_PCT + self.SLIPPAGE_PCT
                pos_side = pos.get("side", "long")
                if pos_side == "long":
                    exit_p = price * (1 - friction)   # Sell lower on exit
                else:
                    exit_p = price * (1 + friction)   # Buy higher to cover short
                pnl_usd = (exit_p - entry_p) * pos["size"]
                fee_usd = abs(pos["qty"] * exit_p) * self.TAKER_FEE_PCT
                pnl_usd -= fee_usd
                self.balance += pnl_usd
                logger.info(
                    f"[PAPER] [EXIT] {symbol} @ {exit_p:.5f} | PNL: ${pnl_usd:.2f} "
                    f"(fee=${fee_usd:.4f}) (Paper Mode)"
                )
                self._save_state()
                self.refresh_account_summary() # Immediate update
                return (
                    ExecutionResult(ExecutionStatus.EXECUTED, symbol, "Paper flatten executed"),
                    ExecutionOutcome(ExecutionOutcomeType.SUCCESS_SUBMITTED, symbol, "Paper flatten")
                )
        
        return (
            ExecutionResult(ExecutionStatus.STAND_ASIDE, symbol, "Paper stand aside"),
            ExecutionOutcome(ExecutionOutcomeType.SKIPPED, symbol, "Paper stand aside")
        )

    def get_open_position_snapshot(self, symbol: str) -> dict | None:
        pos = self.positions.get(symbol)
        if pos:
            # Update current price and PNL
            price = self._get_current_price(symbol)
            pos["current_price"] = price
            pos["unrealized_pnl"] = (price - pos["entry_price"]) * pos["size"]
            pos["pnl_pct"] = (pos["unrealized_pnl"] / (pos["entry_price"] * abs(pos["size"]))) * 100
        return pos

    def list_open_position_symbols(self) -> List[str]:
        return list(self.positions.keys())

    def cancel_all_orders_for_symbol(self, symbol: str) -> None:
        pass

    def flatten_symbol(self, symbol: str) -> None:
        if symbol in self.positions:
            pos = self.positions.pop(symbol)
            price = self._get_current_price(symbol)
            pnl_usd = (price - pos["entry_price"]) * pos["size"]
            self.balance += pnl_usd
            logger.info(f"[PAPER] Flattened {symbol} (Paper Mode)")
            self._save_state()
            self.refresh_account_summary()

    def should_block_for_hold(self, symbol, decision, open_position):
        return False, None, None

    def evaluate_synthetic_stops(self, market_provider, timeframe):
        """Check SL/TP for all open paper positions against current market prices."""
        results = []
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            try:
                price = self._get_current_price(symbol)
            except Exception:
                continue

            sl = pos.get("stop_loss")
            tp = pos.get("take_profit")
            side = pos.get("side", "long")
            entry_p = pos.get("entry_price", 0)
            hit = None

            if side == "long":
                if sl and price <= sl:
                    hit = "SL"
                elif tp and tp > entry_p and price >= tp:
                    hit = "TP"
                elif tp and tp <= entry_p:
                    logger.warning(f"[PAPER] [GHOST GUARD] {symbol}: TP {tp} <= entry {entry_p} for LONG — ignoring TP")
            else:  # short
                if sl and price >= sl:
                    hit = "SL"
                elif tp and tp < entry_p and price <= tp:
                    hit = "TP"
                elif tp and tp >= entry_p:
                    logger.warning(f"[PAPER] [GHOST GUARD] {symbol}: TP {tp} >= entry {entry_p} for SHORT — ignoring TP")

            if hit:
                # [ANTIGRAVITY] Adverse exit fill + taker fee for synthetic stops
                friction = self.HALF_SPREAD_PCT + self.SLIPPAGE_PCT
                if side == "long":
                    exit_price = price * (1 - friction)   # Sell lower
                else:
                    exit_price = price * (1 + friction)   # Buy higher to cover
                pnl_usd = (exit_price - entry_p) * pos["size"]
                fee_usd = abs(pos.get("qty", abs(pos["size"])) * exit_price) * self.TAKER_FEE_PCT
                pnl_usd -= fee_usd
                pnl_pct = (pnl_usd / (entry_p * abs(pos["size"]))) * 100 if entry_p > 0 else 0.0
                self.balance += pnl_usd
                pnl_str = f"{'+' if pnl_usd >= 0 else ''}${pnl_usd:.2f}"

                logger.info(
                    f"[PAPER] [EXIT] Paper {hit}: {symbol} {pnl_str} "
                    f"(Pct={pnl_pct:.2f}%, fee=${fee_usd:.4f}) position={side.upper()} | "
                    f"Entry={entry_p:.5f} Exit={exit_price:.5f}"
                )

                # Record in TradeResultStore for pnl_stats
                if self.trade_results:
                    self.trade_results.add_result(TradeResult(
                        symbol=symbol,
                        closed_at=datetime.now(timezone.utc).isoformat(),
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_usd,
                        is_win=pnl_usd > 0,
                        tier="100%",
                        capital_at_close=self.balance
                    ))

                del self.positions[symbol]
                self._save_state()
                self.refresh_account_summary()
                results.append(ExecutionResult(
                    ExecutionStatus.EXIT_SIGNAL, symbol,
                    f"Paper {hit} exit PnL={pnl_usd:.2f}"
                ))

        return results

    def summarize_pnl(self):
        logger.info(f"Session summary: Balance=${self.balance:.2f}, Open positions={len(self.positions)}")
        self._save_state()

    def _fetch_symbol_state(self, symbol: str) -> dict:
        return {}

    def _has_active_orders_or_position(self, symbol: str, state: dict | None = None) -> bool:
        return symbol in self.positions

    def sync_profile(self, profile):
        self.profile = profile

    @property
    def position_hold_store(self):
        return None

