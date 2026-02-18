# Tradebot SCI — Versioning Policy

**Current Version:** Beta 2.8.0

## Scheme

```
Beta MAJOR.MINOR.PATCH
       │     │     │
       │     │     └─ Incremented on every update/fix (0–99)
       │     └────── Incremented when PATCH reaches 100 (resets PATCH to 0)
       └──────────── Reserved for major rewrites or breaking changes
```

## Rules

1. **Every code change** (bugfix, feature, tweak) → bump `PATCH` by 1
2. **When PATCH reaches 100** → reset to `0`, bump `MINOR` by 1
   - Example: `2.8.99` → next update → `2.9.0`
3. **MAJOR** is only bumped for full rewrites or breaking architecture changes
4. The version lives in `pyproject.toml` → `version = "X.Y.Z"`
5. The "Beta" prefix stays until the system is considered production-stable

## Version History

| Version | Date | Summary |
|---------|------|---------|
| 2.8.0 | 2026-02-18 | Capital semantics fix, AI Commentary overhaul, Churn Burner fix, Decisions Panel reorder, Session Lockout commentary gating |
