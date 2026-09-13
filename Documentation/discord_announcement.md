**Tradebot SCI — Update (Sept 8–13)**

Hey everyone — the wider-universe work from last week is done, and it produced a real answer.

**📊 We found the cost problem**
• It was holding time, not the entry. Same entry, same stop, only the hold changed: 4 hours → **−3.19 pips/trade**; 24 hours → **+1.15 pips/trade**.
• 2,052 trades, 15 pairs, 3 years, the real quoted spread charged on every trade. 67% win rate, t = 3.17.
• Confirmed on a separate 26-pair set over the last 12 months (+1.31 pips, t = 2.64).
• Target moved 10 → 15 pips. The entry rule itself is unchanged — the entry was never the problem.

**📉 An honest negative result**
• Tested 32 trend/breakout rule+horizon combinations across 15 pairs and 3 years. **27 of them had zero profitable target/stop combinations out of 49.**
• Breakout entries carry no directional edge in forex at any horizon from 1 to 10 days. That family is retired. This is the verdict the wider universe was meant to produce.

**🔧 Two bugs fixed**
• **The weekend guard had never worked.** It referenced a value that doesn't exist, threw an exception, and the error was swallowed — so it let paper trades through on closed markets, where spreads run 3–5× wider. Past weekend paper fills were not tradeable prices. Fixed.
• A debug line was writing full broker API keys into the log file. Fixed to log field names only. **If you have shared logs anywhere, rotate your keys.**

**➡️ Next steps**
• The scrape strategy is paper trading now with the new settings. First entries from Monday 20:00 UTC (Sunday's window falls before the market opens).
• Stated plainly: this edge only shows in the last 18 months and is flat before that. It has earned a forward paper test, not real money.
