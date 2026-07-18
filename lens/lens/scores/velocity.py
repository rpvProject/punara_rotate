"""Velocity Score — experimentation rate and rigour (blueprint/05_service_portfolio.md section 5.3 #5).

Formula (weights per CONTRACTS.md V2.4):

    value = (35*cadence + 35*validity + 30*follow_through) / 100

Raw metrics come from the experiments table (SQLite; the Loop Ledger's system
of record — fact_experiments in DuckDB is a verbatim mirror). Cadence is
measured over the trailing 6 months of data history against the 2/month tier
commitment (CONTRACTS.md V2.4). Zero concluded experiments scores validity and
follow_through 0: no experiments means no rigour, honestly.
"""

from __future__ import annotations

from . import clamp, linear

# Experiments started (concluded+running) per month, trailing 6mo, vs commitment.
CADENCE_POOR, CADENCE_COMMIT = 0.0, 2.0
# Minimum sample for a readout to count as statistically credible.
SAMPLE_MIN = 1000

WEIGHTS = {"cadence": 35, "validity": 35, "follow_through": 30}


def score(inputs: dict) -> tuple[float, dict]:
    """Pure over `queries.velocity_inputs` (CONTRACTS V2.9). inputs:
    monthly_starts (dict "YYYY-MM" -> non-draft experiments started, trailing
    window), window_months (int, 6), concluded (int), concluded_valid (int;
    significance recorded AND sample_size >= 1000), concluded_decided (int;
    decision is shipped|killed — inconclusive and undecided count against)."""
    starts = inputs.get("monthly_starts") or {}
    active = int(sum(starts.values()))
    window = float(inputs.get("window_months") or 6)
    concluded = int(inputs.get("concluded") or 0)
    valid = int(inputs.get("concluded_valid") or 0)
    decided = int(inputs.get("concluded_decided") or 0)

    cadence_per_month = active / window
    subs = {
        "cadence": linear(cadence_per_month, CADENCE_POOR, CADENCE_COMMIT),
        "validity": clamp(100.0 * valid / concluded) if concluded else 0.0,
        "follow_through": clamp(100.0 * decided / concluded) if concluded else 0.0,
    }
    value = round(sum(subs[k] * w for k, w in WEIGHTS.items()) / 100.0, 1)

    raws: dict = {
        "cadence": cadence_per_month,
        "validity": (valid / concluded) if concluded else None,
        "follow_through": (decided / concluded) if concluded else None,
    }
    notes = {
        "cadence": (
            f"{active} experiments in the trailing {window:.0f} months = {cadence_per_month:.2f}/mo"
            f" (0 at {CADENCE_POOR:.0f}, 100 at the {CADENCE_COMMIT:.0f}/mo commitment; weight 35%)."
        ),
        "validity": (
            "no concluded experiments; scored 0 (weight 35%)."
            if not concluded
            else f"{valid} of {concluded} concluded had recorded significance"
            f" and sample >= {SAMPLE_MIN} (weight 35%)."
        ),
        "follow_through": (
            "no concluded experiments; scored 0 (weight 30%)."
            if not concluded
            else f"{decided} of {concluded} concluded ended in shipped/killed (weight 30%)."
        ),
    }
    components: dict = {}
    for k, s in subs.items():
        components[k] = round(s, 1)
        components[f"{k}_raw"] = raws[k]
        components[f"{k}_note"] = notes[k]
    return value, components
