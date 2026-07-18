"""Flow Score — lifecycle movement health (blueprint/05_service_portfolio.md section 5.3 #3).

Formula (weights per CONTRACTS.md section 2.4):

    value = (35*stage_distribution + 30*new_to_active_velocity
             + 25*slipping_to_dormant_leak + 10*reactivation_rate) / 100

Raw metrics come from the dim_customers / retention_facts marts and are
normalized linearly to 0-100 between POOR (-> 0) and BEST (-> 100), clamped.
Benchmark constants are v0 stand-ins for the Punara benchmark dataset,
consistent with the lifecycle-stage rules in CONTRACTS.md section 2.2.
"""

from __future__ import annotations

from . import linear

# Share of ever-purchased customers currently in a healthy stage (active|loyal).
HEALTHY_POOR, HEALTHY_BEST = 0.08, 0.40
# Share of customers acquired 3-6 months ago who reached a second order.
N2A_POOR, N2A_BEST = 0.05, 0.30
# Of customers 'slipping' three months ago, share now dormant|lost (lower is better).
SLIP_POOR, SLIP_BEST = 0.95, 0.50
# Of customers 'dormant' three months ago, share now back in new|active|loyal.
REACT_POOR, REACT_BEST = 0.0, 0.12

WEIGHTS = {
    "stage_distribution": 35,
    "new_to_active_velocity": 30,
    "slipping_to_dormant_leak": 25,
    "reactivation_rate": 10,
}


def score(inputs: dict) -> tuple[float, dict]:
    """Pure. inputs: healthy_stage_share (0-1), new_to_active_rate (0-1),
    slipping_to_dormant_rate (0-1 or None = no slipping cohort observed),
    reactivation_rate (0-1 or None = no dormant cohort observed).
    None rates score 100: no cohort at risk means no observed leak."""
    healthy = float(inputs.get("healthy_stage_share") or 0.0)
    n2a = float(inputs.get("new_to_active_rate") or 0.0)
    slip = inputs.get("slipping_to_dormant_rate")
    react = inputs.get("reactivation_rate")

    subs = {
        "stage_distribution": linear(healthy, HEALTHY_POOR, HEALTHY_BEST),
        "new_to_active_velocity": linear(n2a, N2A_POOR, N2A_BEST),
        "slipping_to_dormant_leak": 100.0 if slip is None else linear(float(slip), SLIP_POOR, SLIP_BEST),
        "reactivation_rate": 100.0 if react is None else linear(float(react), REACT_POOR, REACT_BEST),
    }
    value = round(sum(subs[k] * w for k, w in WEIGHTS.items()) / 100.0, 1)

    raws: dict = {
        "stage_distribution": healthy,
        "new_to_active_velocity": n2a,
        "slipping_to_dormant_leak": slip,
        "reactivation_rate": react,
    }
    notes = {
        "stage_distribution": (
            f"{healthy:.1%} of customers are active or loyal"
            f" (0 at {HEALTHY_POOR:.0%}, 100 at {HEALTHY_BEST:.0%}; weight 35%)."
        ),
        "new_to_active_velocity": (
            f"{n2a:.1%} of customers acquired 3-6 months ago reached a second order"
            f" (0 at {N2A_POOR:.0%}, 100 at {N2A_BEST:.0%}; weight 30%)."
        ),
        "slipping_to_dormant_leak": (
            "no slipping customers three months ago; no leak observed (weight 25%)."
            if slip is None
            else f"{float(slip):.1%} of slipping customers went dormant or lost in 3 months"
            f" (0 at {SLIP_POOR:.0%}, 100 at {SLIP_BEST:.0%}; weight 25%)."
        ),
        "reactivation_rate": (
            "no dormant customers three months ago; nothing to reactivate (weight 10%)."
            if react is None
            else f"{float(react):.1%} of dormant customers came back in 3 months"
            f" (0 at {REACT_POOR:.0%}, 100 at {REACT_BEST:.0%}; weight 10%)."
        ),
    }
    components: dict = {}
    for k, s in subs.items():
        components[k] = round(s, 1)
        components[f"{k}_raw"] = raws[k]
        components[f"{k}_note"] = notes[k]
    return value, components
