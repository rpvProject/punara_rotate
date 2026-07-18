"""Punara Lens v0 scoring package.

One module per score (gravity, flow, signal, watertight, ciq); each exposes a
pure `score(inputs: dict) -> (value, components)` that is unit-testable with
plain dicts. `engine.compute_all` gathers mart aggregates, runs the scorers,
and persists append-only `score_runs` rows.

Scoring bands (blueprint/05_service_portfolio.md section 5.3): 0-40 Leaking,
40-70 Building, 70-100 Compounding.
"""

from __future__ import annotations


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def linear(raw: float, worst: float, best: float) -> float:
    """Normalize raw to 0-100: worst -> 0, best -> 100, clamped.

    Works for lower-is-better metrics too (pass worst > best).
    """
    if worst == best:
        return 100.0
    return clamp((raw - worst) / (best - worst) * 100.0)
