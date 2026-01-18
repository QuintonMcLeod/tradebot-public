# ICC Exit Strategy Guide (For Gemini)

Purpose: Replace timer-based exits with ICC-structured exits that match the entry philosophy.

Non-negotiables:
- Remove any time-based exit ("sticky hold", timers, cooldown-based forced exit).
- Exits are structure-driven only.
- Hard stop remains the only immediate exit.

Summary Philosophy:
- If it was correct to buy, it should only sell when structure invalidates the thesis.
- Noise and minor retraces are not exits.
- Exit = Opposite ICC sequence or hard invalidation.

Exit State Machine (mirror entry logic):
- IN_TRADE: Default state after entry.
- EXIT_WATCH: Early warning; structure weakening but no exit yet.
- EXIT_ARMED: Opposite correction has formed; waiting confirmation.
- EXIT_CONFIRMED: Opposite continuation confirmed; exit now.

Immediate Exit (Hard Invalidation):
- Hard stop hit (structural invalidation level used at entry).
- HTF trend invalidation (for long: HTF prints lower low and closes below protected swing).
- Opposite-side sweep with failed reclaim + continuation against position.

ICC Exit Sequence (Long; invert for short):
1) Indication (Exit Watch)
   - LTF micro-structure breaks (LL after HL).
   - HTF/LTF alignment deteriorates (HTF long, LTF neutral/short).
   - No continuation follow-through after entry.
2) Correction (Exit Armed)
   - Price retraces into prior demand and fails to hold.
   - Rejection wicks and close below micro structure.
3) Continuation (Exit Confirmed)
   - LTF continuation against position (lower low + close below swing).
   - HTF does not re-align within the same structure window.

Noise Immunity:
- Require two consecutive closes beyond key structure, or
- A close beyond structure plus a failed retest.
- Do not exit on single wick spikes or brief flickers.
- Use ATR-scaled buffer for structure breaks (avoid noise stops).

Hold-Through-Correction Rule:
- If HTF is still aligned and only LTF is correcting, HOLD.
- No exit just because LTF is in correction.

Optional Partial Exit (if needed):
- Only after continuation extends AND a favorable liquidity sweep prints.
- Keep core position until opposite ICC completes.

Implementation Notes (where to wire):
- Remove any timer-based exit in strategy/engine/loop logic.
- Exit gating should rely on structure state transitions above.
- Use HTF structure for initial stop-loss and take-profit anchor levels.
- Use LTF only for precision entries, not for exit-level placement.
- Log reasons clearly: EXIT_WATCH, EXIT_ARMED, EXIT_CONFIRMED, HARD_INVALIDATION.

Expected Outcome:
- No more panic sells within seconds or minutes.
- Exits occur only when market structure flips or hard stop is hit.

Research Notes (supporting references):
- ICC overview notes: higher time frame levels should anchor SL/TP; manage exits by structure shifts. https://coconote.app/notes/69450552-818d-46ae-8dd3-34e426affd89
- Market structure shift guide: structure breaks signal reversals and can define exit points. https://howtotrade.com/wp-content/uploads/2023/11/Market-Structure-Shift.pdf
- Multi-timeframe trading guidance: use longer time frames to define trend, shorter to refine entries/exits. https://www.investopedia.com/articles/trading/07/timeframes.asp
