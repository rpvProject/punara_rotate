# ADR-002: Phase-2 ML stack — scipy-fit BG/NBD in-repo, sklearn for churn

**Status:** accepted · **Date:** 2026-07-17

## Context

CONTRACTS.md V2.3 requires nightly batch predictions: BG/NBD + Gamma-Gamma
(p_alive, expected 90-day orders, 12-month LTV in integer paise) plus
churn-risk bands, deterministic, Windows-native (no Docker, no compilers).

## Decision

- **BG/NBD + Gamma-Gamma implemented in-repo** (`lens/lens/ml/bgnbd.py`),
  fit via `scipy.optimize` (Nelder-Mead, fixed deterministic starts, small L2
  penalty to block the flat (a,b)→∞ / q→∞ ridges). The `lifetimes` package
  was rejected: unmaintained, pins old numpy/pandas.
- **Churn classifier:** `sklearn.ensemble.HistGradientBoostingClassifier`
  (`random_state=0`, leakage-safe time-split features, AUC gate 0.65 with a
  p_alive-quantile fallback). **xgboost rejected:** native-DLL install
  friction on Windows for zero v2 gain over sklearn's HGB.
- New runtime deps: `scipy`, `scikit-learn` (both pure `pip install` wheels
  on Windows; already in `lens/pyproject.toml`).

## Consequences

- Zero native build steps; the whole pipeline stays `pip install -e`.
- Model math carries Fader-Hardie citations in-source and is covered by
  parameter-recovery tests (`tests/test_ml.py`).
- If feature-based churn ever outgrows HGB, xgboost slots in behind
  `lens/lens/ml/churn.py`'s `train()` seam without touching the engine.
