"""Gravity Score — retention strength (blueprint/05_service_portfolio.md section 5.3 #2).

Formula (weights per CONTRACTS.md section 2.4):

    value = (40*repeat_rate_90d + 25*repurchase_latency
             + 25*cohort_decay + 10*repeat_revenue_share) / 100

Each component is a raw metric normalized linearly to 0-100 between POOR (-> 0)
and BEST (-> 100), clamped. Benchmark constants are v0 stand-ins for the Punara
benchmark dataset, anchored to the seeder realism bar (CONTRACTS.md section 2.1:
repeat rate 25-35%) and the Indian beauty/personal-care ICP (_canon.md section 6).
"""

from __future__ import annotations

from . import linear

# Share of customers whose second order lands within 90 days of their first.
REPEAT_RATE_POOR, REPEAT_RATE_BEST = 0.05, 0.35
# Median days from first to second order; beauty/personal-care replenishment
# cycles run 30-60 days, so 40d compounds and 120d is an acquisition treadmill.
LATENCY_POOR_DAYS, LATENCY_BEST_DAYS = 120.0, 40.0
# Average month-3 cohort retention (cohort_retention mart, months_since = 3).
M3_RETENTION_POOR, M3_RETENTION_BEST = 0.04, 0.25
# Repeat revenue share of trailing-12-month revenue (executive_kpis mart).
REPEAT_REV_POOR, REPEAT_REV_BEST = 0.10, 0.45

WEIGHTS = {
    "repeat_rate_90d": 40,
    "repurchase_latency": 25,
    "cohort_decay": 25,
    "repeat_revenue_share": 10,
}


def score(inputs: dict) -> tuple[float, dict]:
    """Pure. inputs: repeat_rate_90d (0-1), median_repurchase_days (None = no
    repeat purchases, scored 0), avg_m3_retention (0-1), repeat_revenue_share (0-1)."""
    rr = float(inputs.get("repeat_rate_90d") or 0.0)
    lat = inputs.get("median_repurchase_days")
    m3 = float(inputs.get("avg_m3_retention") or 0.0)
    rrs = float(inputs.get("repeat_revenue_share") or 0.0)

    subs = {
        "repeat_rate_90d": linear(rr, REPEAT_RATE_POOR, REPEAT_RATE_BEST),
        "repurchase_latency": 0.0 if lat is None else linear(float(lat), LATENCY_POOR_DAYS, LATENCY_BEST_DAYS),
        "cohort_decay": linear(m3, M3_RETENTION_POOR, M3_RETENTION_BEST),
        "repeat_revenue_share": linear(rrs, REPEAT_REV_POOR, REPEAT_REV_BEST),
    }
    value = round(sum(subs[k] * w for k, w in WEIGHTS.items()) / 100.0, 1)

    raws: dict = {
        "repeat_rate_90d": rr,
        "repurchase_latency": lat,
        "cohort_decay": m3,
        "repeat_revenue_share": rrs,
    }
    notes = {
        "repeat_rate_90d": (
            f"{rr:.1%} of customers reorder within 90 days"
            f" (0 at {REPEAT_RATE_POOR:.0%}, 100 at {REPEAT_RATE_BEST:.0%}; weight 40%)."
        ),
        "repurchase_latency": (
            "no second orders observed; scored 0 (weight 25%)."
            if lat is None
            else f"median {float(lat):.0f} days to the second order"
            f" (0 at {LATENCY_POOR_DAYS:.0f}d, 100 at {LATENCY_BEST_DAYS:.0f}d; weight 25%)."
        ),
        "cohort_decay": (
            f"average month-3 cohort retention {m3:.1%}"
            f" (0 at {M3_RETENTION_POOR:.0%}, 100 at {M3_RETENTION_BEST:.0%}; weight 25%)."
        ),
        "repeat_revenue_share": (
            f"{rrs:.1%} of trailing-12m revenue is repeat"
            f" (0 at {REPEAT_REV_POOR:.0%}, 100 at {REPEAT_REV_BEST:.0%}; weight 10%)."
        ),
    }
    components: dict = {}
    for k, s in subs.items():
        components[k] = round(s, 1)
        components[f"{k}_raw"] = raws[k]
        components[f"{k}_note"] = notes[k]
    return value, components
