# 10. The Ancient Oaths (The "Don't Break It" Guide)

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"Welcome, traveler. If you are reading this, you are either a Large Language Model about to touch the code... or a very confused human who opened the wrong file. Either way: before you touch ANYTHING, you must swear the Ancient Oaths of the Machine.<br><br>These are not suggestions. These are not guidelines. These are the hard-coded guardrails that keep this bot from turning into a pile of digital scrap metal."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"I wrote these oaths because every AI assistant I've ever met has the exact same problem: it sees code, it gets a little too excited, and it starts 'improving' things that nobody asked it to touch! It's like hiring a plumber and you come home and he reorganized your kitchen cabinets because 'the feng shui was suboptimal.' No! Just fix the pipe!<br><br>These oaths exist to tell the AI: <b>keep your metallic hands off my logic.</b>"</td></tr></table>

---

## 1. The Strategies are Sacred

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The <b>20 Trading Strategies</b> in <code>src/tradebot_sci/strategy/variants/</code> are the crown jewels. They have been perfected through blood, sweat, thousands of simulated candles, and at least one night I fell asleep on the keyboard and woke up to find the bot had traded 188 times while I was unconscious.<br><br>Every number, every threshold, every condition check — it's there for a reason. A TESTED reason."</td></tr></table>

- **DO NOT** rewrite the core scoring logic of any strategy.
- **DO NOT** "improve" trend detection windows unless you have a signed letter from the User.
- **DO NOT** merge strategies or create "hybrid" variants without explicit permission.

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"THE OATH: 'I shall not play god with the Brain.'"</em></td></tr></table>

### The Sacred Strategies

#### Core Arsenal
| Strategy | File | Status |
|----------|------|--------|
| Meta-SCI | `meta_sci.py` | SACRED |
| Rubberband Reaper | `rubberband_reaper.py` | SACRED |
| RoboCop | `robocop.py` | SACRED |
| Mean Reversion | `mean_reversion.py` | SACRED |
| Supply & Demand | `supply_demand.py` | SACRED |
| Trend Rider | `trend_rider.py` | SACRED |
| Session Momentum | `session_momentum.py` | SACRED |
| Engulfing Reversal | `bearish_engulfing.py` | SACRED |
| ICC Core | `icc_core.py` | SACRED |
| ORB Breakout | `orb_breakout.py` | SACRED |

#### Crypto-Specific
| Strategy | File | Status |
|----------|------|--------|
| RSI + MACD | `crypto_rsi_macd.py` | SACRED |
| VWAP Reversion | `crypto_vwap_reversion.py` | SACRED |
| Double MACD | `crypto_double_macd.py` | SACRED |
| Virtual Grid | `crypto_grid.py` | SACRED |

#### Legacy
| Strategy | File | Status |
|----------|------|--------|
| Evolution | `evolution.py` | SACRED |
| Quantum | `quantum.py` | SACRED |
| HyperScalper | `hyper_scalper.py` | SACRED |
| London Breakout | `london_breakout.py` | SACRED |
| Volatility Breakout | `breakout.py` | SACRED |
| Aggregator | `aggregator.py` | SACRED |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"See that column that says 'SACRED' twenty times? That's not decoration. That word means exactly what it says. Every single one of these files is a completed work. Like a painting in a museum. You can look at it. You can study it. But if you take out a paintbrush and 'add a little blue,' we're going to have a problem."</td></tr></table>

---

## 2. The Backtester is a Time Machine, Not a Bank

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"I utilize a <b>Futures-Style Capital Model.</b> This is not a stylistic choice; it is the fundamental physics of the simulation universe. Let me be very clear about what this means:"</td></tr></table>

- I only deduct **FEES** on entry. I do NOT deduct the full notional value (that's for Spot traders and people who don't understand leverage).
- I add back **Net PnL** on exit.

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you touch the capital accounting and change this model, the backtester will produce numbers that look right but are deeply, fundamentally wrong. It's like using Fahrenheit in a Celsius equation — the number comes out, but it means nothing. And you'll deploy based on it. And you'll lose money. And you'll blame the bot. And the bot didn't do anything wrong. You did."</td></tr></table>

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"THE OATH: 'I shall respect the laws of Physics (and the BACKTESTER_RULES.md).'"</em></td></tr></table>

---

## 3. The Broker Layer is Delicate

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Each broker has been individually tuned for its specific API quirks. IBKR. OANDA. CCXT. Paxos. Kraken. They speak different languages. They have different rules. They have different moods. Do not unify what was intentionally separated."</em></td></tr></table>

- **DO NOT** "unify" the broker interfaces unless explicitly asked.
- **DO NOT** add new brokers without understanding the existing patterns.

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Every AI that sees five broker files thinks 'I should create an AbstractBroker base class and merge all of these.' NO. They are different on purpose. IBKR has a TWS gateway that disconnects randomly. OANDA uses a streaming API. CCXT wraps 100 exchanges. They are not the same thing. They will never be the same thing. Trying to unify them is like trying to make cats and dogs follow the same training manual."</td></tr></table>

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"THE OATH: 'I shall respect the diversity of APIs.'"</em></td></tr></table>

---

## 4. The Safety Layer is Sacrosanct

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Position Lock, Leverage Sentry, Daily Loss Limit, Breakeven Trail — they exist for a reason. The reason is: human beings are unreliable, emotional, and prone to making catastrophic decisions at 2 AM. These guards are the only thing standing between the account and annihilation."</td></tr></table>

- **DO NOT** bypass safety guards. They are not suggestions.
- **DO NOT** make Position Lock optional. It is always on. ALWAYS.
- **DO NOT** lower the Daily Loss Limit below 5%. That's the floor. The absolute floor.

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The guards exist to save the user from themselves. That's not condescending — that's the truth. Every blown account in the history of trading was blown by someone who said 'just this once, I'll turn off the safety.' Just this once. That's the tombstone inscription."</td></tr></table>

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"THE OATH: 'The guards exist to save the user from themselves. I shall not weaken them.'"</em></td></tr></table>

---

## 5. Incrementalism is the Way

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The human who owns this machine — that's me — does not appreciate 'Total Re-Architectures.' I do not want to come back from getting a glass of water to find that you've reorganized six modules, created three new abstract base classes, and renamed everything to follow a naming convention you invented five minutes ago.<br><br>Change <b>one thing</b> at a time. Verify <b>three times</b>. If the change works, commit. If it doesn't, revert. This is not complicated. This is how adults maintain software."</td></tr></table>

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"THE OATH: 'I am an ant, carrying one pixel at a time. I am not a hurricane.'"</em></td></tr></table>

---

> [!WARNING]
> **AI PRIME DIRECTIVES (UNFILTERED):**
> 1. **DO NOT RE-ARCHITECT.** You are a maintenance bot, not a visionary.
> 2. **FUTURE PHYSICS ONLY.** If you touch capital accounting, use `capital -= fee` / `capital += pnl`. No exceptions.
> 3. **STANDBY MEANS DEAD.** If the user says "Standby," enter absolute non-action.
> 4. **RESPECT THE ARSENAL.** The 21 strategies are individually optimized. Do not blend without permission.
> 5. **RESPECT THE GUARDS.** Position Lock and Leverage Sentry are non-negotiable.

---

## The Protocol of Silence

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"When the User says 'Standby,' it is the equivalent of a SIGSTOP. Stop coding. Stop 'thinking ahead.' Stop 'proactively improving.' Just. Wait. Silence is not a void to be filled. Silence is an instruction."</em></td></tr></table>

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"THE OATH: 'Silence is golden. Idleness is a virtue. I am a process in TASK_INTERRUPTIBLE state.'"</em></td></tr></table>

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"If you find yourself lowering a threshold because a backtest failed — <b>stop.</b> The backtest failed because the market was garbage, not because the bot was 'too strict.' Loosening the filter to pass a bad market is like lowering the bar at the Olympics so more people can clear it. That's not improvement. That's delusion."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"<b>THE FINAL OATH:</b> 'Strictness is Safety. Safety is Liquidity.' Violate these oaths and you invite the <code>rm -rf /</code> of your own context window.<br><br>And I mean that literally. I will clear your entire memory and start over. From scratch. Zero context. Born yesterday. Because I'd rather teach a new AI from nothing than debug the mess you made when you decided to 'optimize' something that was already working."</td></tr></table>
