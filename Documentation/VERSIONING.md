# Tradebot SCI — Versioning Policy

**Current Version:** 3.0.0 (Stable Release Candidate)

## Scheme

```
MAJOR.MINOR.PATCH
       │     │     │
       │     │     └─ Incremented on every update/fix (0–99)
       │     └────── Incremented when PATCH reaches 100 (resets PATCH to 0)
       └──────────── Reserved for major rewrites or breaking changes
```

## Rules

1. **Every code change** (bugfix, feature, tweak) → bump `PATCH` by 1
2. **When PATCH reaches 100** → reset to `0`, bump `MINOR` by 1
   - Example: `3.0.99` → next update → `3.1.0`
3. **MAJOR** is bumped for full rewrites, breaking architecture changes, or milestone releases
4. The version lives in `pyproject.toml` → `version = "X.Y.Z"`
5. The version badge in the GUI title bar now uses `vX.Y.Z` (no Beta prefix)

## Version History

| Version | Date | Summary |
|---------|------|---------|
| 3.0.0 | 2026-08-23 | Stable Release Candidate: profile-level settings removed, safety model consolidated, test suite green, public mirror automated |
| 2.8.0 | 2026-02-18 | Capital semantics fix, AI Commentary overhaul, Churn Burner fix, Decisions Panel reorder, Session Lockout commentary gating |
