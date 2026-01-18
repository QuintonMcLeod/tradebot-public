# QWEN-VALIDATED STRATEGY: Restore Healthy Rejection Rate

**Strategy Validated By**: Real Qwen API debate (5 rounds)  
**Date**: 2026-01-11  
**Status**: APPROVED - Ready for Gemini  

---

## QWEN'S FINAL CONSENSUS

After 5 rounds of debate, Qwen **AGREES** with the strategy and provides the following validated recommendations:

### ✅ **Agreed Root Cause**
Threshold of 10.0 is too low and allows trades without continuation (violates ICC methodology)

### ✅ **Validated Solution**

**Primary Changes:**
```yaml
# Test approach (Qwen recommended):
icc_entry_score_threshold: 60.0     # Start here, Was: 10.0
icc_high_score_override_threshold: 70.0  # Was: 30.0

# If still > 20 trades/day after 24h monitoring:
icc_entry_score_threshold: 65.0     # Increase to this
```

**Additional Enhancement (Qwen suggested):**
```yaml
icc_auto_entry_min_htf_strength: 0.5  # Was: 0.0
```

### ✅ **Success Metric Validated**
- **Monitor**: Trades per day (NOT rejection %)
- **Target**: 10-20 trades/day
- **Weekly average**: ~15 trades/day
- **Rejection rate will vary** (90-99% depending on market conditions - both healthy!)

### ✅ **Validation Approach Approved**
1. Set threshold to 60.0 initially
2. Monitor for 24 hours
3. Count trades/day
4. Adjust:
   - If > 20/day → raise to 65.0
   - If < 10/day → lower to 55.0
   - If 10-20/day → perfect, keep it!

---

## QWEN'S KEY INSIGHTS

### 1. **Math Validation**
Qwen confirmed:
- 15 trades/day ÷ 18,720 evals/day = 0.08% acceptance = **99.92% rejection** ✅
- Current 52% rejection = ~9,081 trades/day = catastrophic overtrading ✅
- Threshold 65.0 requires continuation OR very strong trend ✅

### 2. **Critical Catch on Override Threshold**
Qwen initially suggested:
```yaml
icc_high_score_override_threshold: 85.0  # Round 2 suggestion
```

But then agreed:
```yaml
icc_high_score_override_threshold: 70.0  # Final recommendation
```

**Why**: 70.0 prevents bypass while allowing exceptional trades with strong HTF (20+20+25=65 needs 70 override)

### 3. **HTF Strength Addition**
Qwen recommended adding:
```yaml
icc_auto_entry_min_htf_strength: 0.5
```
**Benefit**: Further enforces ICC methodology by requiring moderate-to-strong HTF trend

### 4. **Metric Shift Validated**
Qwen strongly agreed:
> "Focusing on the number of trades per day is a more robust and adaptive approach. The rejection rate can fluctuate significantly with market conditions."

**Why this matters:**
- Choppy market: 99% rejection, 5-10 trades/day ← Healthy!
- Trending market: 90-95% rejection, 15-25 trades/day ← Also healthy!
- Both average to ~15 trades/day over a week ← Perfect for compounding!

---

## FINAL INSTRUCTIONS FOR GEMINI

### Step 1: Initial Configuration
Edit `config/settings_profiles.yaml` (auto_schedule profile):

```yaml
# Line 199 - Entry threshold:
icc_entry_score_threshold: 60.0     # Was: 10.0

# Line 206 - Override threshold:
icc_high_score_override_threshold: 70.0  # Was: 30.0

# Line 196 - NEW: Add HTF strength requirement:
icc_auto_entry_min_htf_strength: 0.5  # Was: 0.0
```

### Step 2: Restart Bot
```bash
pkill -f tradebot
./tradebot.sh --continuous &
```

### Step 3: Monitor for 24 Hours

Track **trades per day** (not rejection %):
```bash
# Count total trades in latest log:
grep "outcome=success" logs/tradebot.log | wc -l
```

### Step 4: Adjust if Needed

**If > 20 trades/day:**
```yaml
icc_entry_score_threshold: 65.0  # Raise from 60.0
```

**If < 10 trades/day:**
```yaml
icc_entry_score_threshold: 55.0  # Lower from 60.0
```

**If 10-20 trades/day:**
- ✅ Perfect! No changes needed
- Continue monitoring weekly average

### Step 5: Report Back

After 24 hours, report:
1. Total trades executed
2. Trades per day average
3. Any errors or issues
4. Quality of trades (continuation present?)

---

## WHAT QWEN VALIDATED

| Item | My Proposal | Qwen's Response |
|------|-------------|-----------------|
| Root cause | Threshold 10.0 too low | ✅ Agreed |
| Main threshold | Raise to 65.0 | ✅ Agreed (test 60.0 first) |
| Override threshold | Raise to 70.0 | ✅ Agreed |
| HTF strength | Not mentioned | ✅ Suggested 0.5 |
| Success metric | Trades/day, not rejection % | ✅ Strongly agreed |
| Validation approach | Monitor 24h, adjust | ✅ Approved |

---

## DEBATE HIGHLIGHTS

### Round 1: Math Validation
**Qwen**: "Your calculations for evaluations vs. trades are correct. To achieve 15 trades/day, a rejection rate of 99.92% is necessary."

### Round 2: Continuation Requirement
**Qwen**: "A setup scoring 75 points with zero continuation is not aligned with ICC strategy and should not be entered. Threshold 10.0 is too low."

### Round 3: Threshold Math Check
**Qwen**: "Your math is correct. The new threshold of 65.0 will enforce the full ICC methodology."

### Round 4: Additional HTF Strength
**Qwen**: "Consider increasing `icc_auto_entry_min_htf_strength` to 0.5 to ensure a strong higher time frame trend."

### Round 5: Metric Agreement
**Qwen**: "Yes, focusing on trades per day is more practical and adaptive. The rejection rate will vary with market conditions - both 90% and 99% can be healthy!"

---

## READY FOR GEMINI ✅

This strategy has been validated through rigorous debate with Qwen (not simulated - real API responses).

**Consensus achieved on:**
1. Root cause identification
2. Threshold values (60.0 → 65.0 test approach)
3. Override threshold (70.0)
4. HTF strength addition (0.5)  
5. Success metrics (trades/day)
6. Validation methodology

**Pass to Gemini with confidence!**
