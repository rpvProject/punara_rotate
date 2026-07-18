"""Punara CIQ — Customer Intelligence Quotient, full composite (Phase 2).

Canon v1 weights (_canon.md section 7 / 05_service_portfolio.md section 5.3 #1),
summing to exactly 100:

    Gravity 20 · Flow 12 · Signal 12 · Watertight 12 · Vitals 10 ·
    Velocity 10 · Pulse 10 · Autopilot 8 · Altitude 6

Partial mode (CONTRACTS.md V2.4): if any component score is unavailable, the
weights renormalize over the available ones, `coverage` reports "k/9" and
`missing` lists the absent names — the same mechanism as v0's ciq_partial
(whose history rows stay readable; the engine writes `ciq` rows now).
"""

from __future__ import annotations

from . import clamp

CANON_WEIGHTS = {
    "gravity": 20,
    "flow": 12,
    "signal": 12,
    "watertight": 12,
    "vitals": 10,
    "velocity": 10,
    "pulse": 10,
    "autopilot": 8,
    "altitude": 6,
}


def score(values: dict[str, float | None]) -> tuple[float, dict]:
    """Pure. values: score name -> 0-100 float; missing/None names are treated
    as unavailable and the composite renormalizes over the rest."""
    available = {k: float(values[k]) for k in CANON_WEIGHTS if values.get(k) is not None}
    missing = [k for k in CANON_WEIGHTS if k not in available]
    components: dict = {}
    if not available:
        components["coverage"] = "0/9"
        components["missing"] = missing
        components["note"] = "No component scores available; CIQ cannot be computed."
        return 0.0, components

    total_weight = sum(CANON_WEIGHTS[k] for k in available)
    value = round(
        clamp(sum(v * CANON_WEIGHTS[k] for k, v in available.items()) / total_weight), 1
    )
    for k, v in available.items():
        components[k] = round(v, 1)
    components["coverage"] = f"{len(available)}/{len(CANON_WEIGHTS)}"
    components["weights_renormalized"] = {
        k: round(CANON_WEIGHTS[k] * 100.0 / total_weight, 2) for k in available
    }
    components["missing"] = missing
    components["note"] = (
        "Punara CIQ: weighted composite of the nine scores with canon v1 weights"
        " (Gravity 20, Flow 12, Signal 12, Watertight 12, Vitals 10, Velocity 10,"
        " Pulse 10, Autopilot 8, Altitude 6)"
        + ("." if not missing else f"; renormalized over {len(available)}/9 — missing: {', '.join(missing)}.")
    )
    return value, components
