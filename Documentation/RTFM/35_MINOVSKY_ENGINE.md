# 35. The Minovsky Engine — Death of the Phoenix, Birth of the Reactor

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Alright. Sit down. We need to have a funeral. And then a christening. In that order.<br><br>The <b>Phoenix Engine</b> is dead. I killed it. With my bare hands. And I'd do it again.<br><br>See, the Phoenix Engine was supposed to be the 'replay engine' — the thing that takes historical data and runs our strategy through it to see how we would've done. Smart idea. Terrible execution. Like ordering a pizza and then rebuilding the oven from scratch when there's already a perfectly good one in the kitchen."</td></tr></table>

## The Crime Scene

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Let me explain what the Phoenix Engine actually did. And please, sit down for this, because it's genuinely offensive from an engineering standpoint.<br><br>The <b>Backtester</b> — our battle-tested, 2,400-line simulation engine — already handles everything: multi-position, OHLC stop/target simulation, Tiered Guillotine, SAR, Counter-Reversal, consecutive-loss cooldowns, pyramiding, dust guards, position sizing, and performance modes.<br><br>The Phoenix Engine <em>reimplemented all of this</em> in a separate 1,423-line file. Poorly. Like someone copying the Mona Lisa but with crayons and a hangover."</td></tr></table>

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"Wait. You're telling me there were TWO simulation engines doing the same thing?"</td></tr></table>

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Worse. The copy was <em>wrong</em>. The backtester made $3,974 in 14 days. The Phoenix Engine lost $5,370 in the same 14 days. Same data. Same strategy. Same symbols. Negative five thousand dollars of difference."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's like hiring a stunt double for Tom Cruise and the stunt double falls off the building while Tom's fine.<br><br>Here's what was wrong with it:"</td></tr></table>

### What Killed the Phoenix

| Problem | What Happened | Impact |
|---------|--------------|--------|
| **No multi-position** | Phoenix tracked 1 position per symbol. Backtester runs 5 concurrent. | 499 trades vs 2,278 |
| **Session Gate blocking** | Phoenix left `session_gate_enabled=True`. Only traded 4 hours/day. | 83% of valid entries blocked |
| **Broken Guillotine** | Reimplemented scale-out left remnants above dust threshold | Positions never fully closed |
| **Missing SAR chain** | No `max_consecutive_sar` guard, no CR fallback | Infinite ping-pong losses |
| **Wrong exits** | Reimplemented OHLC checking didn't match backtester logic | PF 0.73 vs 2.10 |

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"So the old engine was basically a knockoff? Like buying a Rolex from a guy in a trenchcoat at the subway station?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Exactly. And the real Rolex was sitting right there. In the same codebase. Just... unused. <br><br>So I did what any sane person would do. I threw the knockoff in a dumpster and started wearing the real one."</td></tr></table>

---

## The New Engine: Minovsky Reactor

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"The name comes from Gundam. The Minovsky Particle Reactor is the core power source inside every mobile suit. <em>Every system</em> — weapons, shields, thrusters, sensors — connects to it. Without it, the Gundam is a very expensive statue.<br><br>The Minovsky Engine works the same way. It is the <b>main engine</b> of the entire bot. Live trading, paper trading, backtesting — they all run through the Minovsky Engine. It uses the proven backtester as its foundation, and every system — SAR, CR, Guillotine, ICC, Safety Guards — plugs directly into it."</td></tr></table>

### Architecture

```
engine_replay.py (thin CLI — 220 lines)
  └── Parses arguments, prints results
  └── Calls MinovskyEngine
       └── MinovskyEngine (wrapper — 240 lines)
            └── Instantiates Backtester
            └── Loads cartridge config
            └── Calls Backtester.run_backtest()
                 └── THE REAL ENGINE (2,400 lines)
                      ├── Multi-position management
                      ├── OHLC SL/TP simulation
                      ├── Tiered Guillotine (T1/T2)
                      ├── SAR + CR chain guards
                      ├── StrategyEngine.decide()
                      │    ├── 10 Trend Indicators
                      │    ├── ICC Scoring
                      │    ├── Safety Guards
                      │    ├── Session/Sabbath
                      │    └── All UI settings
                      ├── Position Sizing
                      ├── Flywheel / Gamma / Coil
                      └── Pyramiding
```

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"240 lines to do what 1,423 lines couldn't. That is... an elegant form of violence."</em></td></tr></table>

### Before & After

| Metric | Phoenix Engine | Minovsky Engine |
|--------|---------------|-----------------|
| **Lines of code** | 1,423 | 240 |
| **Trades (14d)** | 499 | 2,278 |
| **PnL (14d)** | -$5,370 | +$3,974 |
| **Profit Factor** | 0.73 | 2.10 |
| **Win Rate** | 35% | 37% |
| **R:R** | 2.34 | 3.53 |
| **Multi-position** | ❌ | ✅ (5 concurrent) |
| **Guillotine** | ❌ broken | ✅ T1 + T2 cascade |
| **SAR chains** | ❌ missing | ✅ with CR fallback |
| **Match backtester** | ❌ | ✅ **Identical results** |

---

## How to Use It

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"So how do I run this thing?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Three commands. That's it."</td></tr></table>

```bash
# Full 14-day test with all symbols:
python3 tools/engine/engine_replay.py --cartridge conductor_14d_all

# Single symbol:
python3 tools/engine/engine_replay.py --cartridge conductor_14d_all --symbols EURUSD

# Strategy override:
python3 tools/engine/engine_replay.py --cartridge conductor_14d_all --strategy robocop
```

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The engine produces <em>identical</em> results to <code>mega_backtester.py</code>. That's not a goal — that's a guarantee. Both use the same <code>Backtester.run_backtest()</code> method. Same code path. Same physics."</td></tr></table>

---

## The Museum

The Phoenix Engine has been laid to rest in `tools/engine/_deprecated/PHOENIX_ENGINE_MEMORIAL.py`. It was a noble attempt. It taught us an important lesson:

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"Do not rebuild the temple when the temple already exists. Just... open the door."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Or as Patrice would say: 'Why are you making your own bread when there's a perfectly good bakery next door? You're not a baker! You don't even like baking! You just wanted BREAD!'"</td></tr></table>

---

## The Main Engine — Live, Paper, and Backtest

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"Hold on. Is this just a backtest engine, or does the live bot use it too?"</td></tr></table>

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The Minovsky Engine is the <b>main engine</b>. Period. When you start the bot, the startup logs say <code>[MINOVSKY]</code>. When you run a backtest, it uses the Minovsky Engine. When you paper trade, it uses the Minovsky Engine.<br><br>Every mode shares the same <code>StrategyEngine.decide()</code> decision core. Same brain. Same logic. Same indicators. Same safety guards. The only difference is what's on the other end:"</td></tr></table>

| Mode | What Runs | Broker |
|------|-----------|--------|
| **Live Trading** | Minovsky Engine → `StrategyEngine.decide()` → Real Broker (OANDA/IBKR/CCXT) | Real money |
| **Paper Trading** | Minovsky Engine → `StrategyEngine.decide()` → PaperBroker | Simulated money |
| **Backtesting (UI)** | Minovsky Engine → `Backtester.run_backtest()` → `StrategyEngine.decide()` | Historical OHLC |
| **Backtesting (CLI)** | Minovsky Engine → `Backtester.run_backtest()` → `StrategyEngine.decide()` | Historical OHLC |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"One engine. One brain. Four bodies. Whether it's live, paper, UI backtest, or CLI backtest — the <em>same</em> <code>StrategyEngine.decide()</code> makes every call. The Minovsky Engine is the reactor. Everything else is just plumbing."</td></tr></table>

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"I process the same signals regardless of the body I inhabit. Live market, paper market, historical replay — my analysis is the same. The only difference is whether the broker at the other end is real or simulated."</em></td></tr></table>
