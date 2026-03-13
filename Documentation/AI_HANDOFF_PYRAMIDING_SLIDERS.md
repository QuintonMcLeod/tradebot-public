# AI Handoff — Pyramiding Sliders and Configuration Mapping

> [!CAUTION]
> **READ THIS ENTIRE DOCUMENT** before doing anything. The user has aborted the previous AI session because the Pyramiding GUI sliders and profile configuration mappings were not behaving as expected.

---

## 1. Context and Objective
The user's objective was to ensure the "First Pyramid Size" and "Pyramid Trigger Level" sliders in the Electron GUI (`settings_integrated.js`) correctly save, load, and apply their values to the active bot profile.

The user reported:
- The sliders and toggles would revert to defaults instead of saving to the config.
- The "First Pyramid Size" was capped at 50% instead of allowing 100%.
- "Pyramid on Winners" toggle and trigger levels were defaulting improperly.
- Potential conflict with the "Profit Buffer" setting.

### Conversation ID
`4d47b99c-1ee9-426e-8db0-96e71c0b03ca`

---

## 2. What Was Done This Session

### 1. Electron GUI (`settings_integrated.js`)
- Fixed UI DOM element IDs to match uppercase `CONFIG_MAP` keys (e.g., `CONDUCTOR_PYRAMID_ENABLED`).
- Adjusted `createSliderCard` bounds logic for percentage sliders so HTML inputs aren't clamped prematurely (First Pyramid Size can now go up to 100%).
- Refactored `getValue` to prioritize active profile overrides from `config.json` instead of falling back to global visual defaults, mirroring the architecture of the "Lock-In" slider.
- Removed deprecated `profilesModule` direct saving intercepts, migrating Pyramiding settings to use standard global config `updateValue` workflows.

### 2. Backend Config Loader (`tradebot_sci/config/loader.py`)
- **CRITICAL FIX**: Discovered that the config promotion loop inside `loader.py` only looked at `TradingProfileSettings` model fields. Since `conductor_pyramid_start_r` and `conductor_pyramid_first_pct` live inside `PerformanceSettings`, the loader was silently dropping the user's GUI overrides on boot.
- Added `SafetySettings`, `PerformanceSettings`, and `RiskSettings` fields to `_profile_fields` in `loader.py`. Tested and verified that `config.json["global"]` Pyramiding overrides now successfully promote into the active `forex_continuous` profile.

### 3. Strategy Logging (`tradebot_sci/strategy/variants/forex_conductor.py`)
- Added an `INFO` console log inside `ForexConductorStrategy.__init__` to explicitly print the loaded Pyramiding Trigger R and First Pct. This allows the user/AI to tail the log and prove the correct values are being loaded.

---

## 3. What the Next AI Needs To Do

### Immediate: Verify the Frontend Sliders
1. **The User aborted because they felt the previous AI was hallucinating.** The GUI might still not be reflecting the saved `config.json` state accurately. 
2. Launch the Electron app (`npm exec electron ./src/tradebot_sci/electron_gui/main.js`) or inspect how `settings_integrated.js` populates values on load. Ensure that `getValue()` is actually firing correctly for the Pyramid elements.
3. Verify if there is any hardcoded clamp or event listener still restricting "First Pyramid Size" in the UI.

### Medium Term: Investigate Profit Buffer Conflict
4. The user asked: *"Also, does this conflict with Profit Buffer? If so, figure that mess out"*.
5. In `forex_conductor.py`, check how `conductor_pyramid_start_r` interacts with `PYRAMID_PROFIT_BUFFER_PCT` (if at all). Determine if Pyramiding overrides or conflicts with the existing Profit Buffer logic, and explain this clearly to the user or patch it if it's broken.

### Files to Review
| File | Focus |
|---|---|
| `src/tradebot_sci/electron_gui/settings_integrated.js` | Slider boundaries, `getValue()`, `updateValue()`, `CONFIG_MAP` |
| `src/tradebot_sci/config/loader.py` | Variables promotion loop (`_profile_fields`) |
| `src/tradebot_sci/strategy/variants/forex_conductor.py` | How Pyramiding settings interact with trade risk and milestones |

---
