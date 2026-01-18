# GEMINI: Fix Trading Bot Configuration

## Context
The trading bot has two critical bugs preventing proper trading:
1. **Capital fragmentation**: Holding 5 different symbols instead of 1 symbol with pyramids
2. **Overtrading**: Low thresholds (10.0) allowing trades without continuation

These changes have been validated by Qwen AI through comprehensive analysis.

---

## Your Task

Edit `/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/config/settings_profiles.yaml`

Find the `auto_schedule` profile and make these exact changes:

### Change 1: Increase Entry Threshold
**Line 199** - Change:
```yaml
icc_entry_score_threshold: 10.0
```
To:
```yaml
icc_entry_score_threshold: 60.0
```

### Change 2: Increase Override Threshold  
**Line 206** - Change:
```yaml
icc_high_score_override_threshold: 30.0
```
To:
```yaml
icc_high_score_override_threshold: 70.0
```

### Change 3: Add HTF Strength Requirement
**Line 196** - Change:
```yaml
icc_auto_entry_min_htf_strength: 0.0
```
To:
```yaml
icc_auto_entry_min_htf_strength: 0.5
```

### Change 4: Fix Position Limit (CRITICAL)
**Line 209** - Change:
```yaml
max_concurrent_positions: 5
```
To:
```yaml
max_concurrent_positions: 1
```

---

## After Making Changes

1. **Restart the bot**:
```bash
pkill -f tradebot
cd /home/qchan/Scripts/Trade\ by\ SCI/tradebot-sci-debug
./tradebot.sh --continuous &
```

2. **Verify config loaded**:
```bash
grep "icc_entry_score_threshold\|max_concurrent_positions" logs/tradebot.log | tail -5
```

Should show:
- icc_entry_score_threshold: 60.0
- max_concurrent_positions: 1

3. **Monitor for 24 hours** and track:
- Number of trades per day (target: 10-20)
- Position count (should be max 1 at any time)
- Verify only high-quality entries (continuation present)

---

## Success Criteria

✅ Only 1 symbol held at a time (not 5)  
✅ Pyramid entries on SAME symbol  
✅ 10-20 trades per day average  
✅ Most rejections due to "ICC score below threshold"  
✅ Trades only when score ≥ 60  

---

## If Issues Arise

- **Too many trades (>20/day)**: Raise `icc_entry_score_threshold` to 65.0
- **Too few trades (<10/day)**: Lower `icc_entry_score_threshold` to 55.0
- **Bot not starting**: Check logs for syntax errors in YAML

---

## Why These Changes Matter

**Thresholds (60.0, 70.0, 0.5)**: Enforces full ICC methodology (Indication + Correction + Continuation). Current threshold of 10.0 allows trades without continuation.

**Position limit (1)**: Trade by SCI strategy requires concentrating capital on the BEST setup with pyramids, not fragmenting across 5 mediocre setups.

Both bugs confirmed in logs - bot currently holding 5 positions (ADAUSD, DOGEUSD, SOLUSD, ATOMUSD, DOTUSD) all underwater.

---

**Complete these 4 config changes, restart the bot, and monitor results.**
