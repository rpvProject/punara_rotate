"""Watertight Score — revenue leakage inverted (blueprint/05_service_portfolio.md section 5.3 #10).

Per leak type i (formula fixed by CONTRACTS.md section 2.4):

    share_i = leak_paise_i / gross trailing-12m revenue paise
    sub_i   = 100 * (1 - min(share_i, P90_i) / P90_i)

    value = (40*preventable_churn + 30*rto_cod
             + 15*failed_payments + 15*discount_abuse) / 100

P90_i is the 90th-percentile leakage share for the vertical; benchmark-
normalized because raw leakage runs 3-15% of revenue and an unnormalized score
would park every brand in the 85-97 band. Total leakage around 2% of revenue
scores ~90; a brand at or beyond P90 on every line scores 0. Raw paise are
always reported beside each sub-score.
"""

from __future__ import annotations

from . import clamp

# v0 P90 leakage shares of gross revenue, per leak type. Stand-ins for the
# Punara benchmark dataset, derived from the seeder realism bar (CONTRACTS.md
# section 2.1: COD share 40-60%, RTO on COD 15-25%, failed payments 3-6% of
# attempts, discount-abuse tail) for the beauty/personal-care ICP.
P90_SHARE = {
    "preventable_churn": 0.08,
    "rto_cod": 0.06,
    "failed_payments": 0.02,
    "discount_abuse": 0.03,
}

WEIGHTS = {
    "preventable_churn": 40,
    "rto_cod": 30,
    "failed_payments": 15,
    "discount_abuse": 15,
}


def score(inputs: dict) -> tuple[float, dict]:
    """Pure. inputs: gross_revenue_paise (int), leak_paise (dict leak_type ->
    paise; missing type = 0 leak observed)."""
    gross = int(inputs.get("gross_revenue_paise") or 0)
    leak_paise = dict(inputs.get("leak_paise") or {})

    components: dict = {}
    total = 0
    acc = 0.0
    for leak_type, weight in WEIGHTS.items():
        amount = int(leak_paise.get(leak_type) or 0)
        total += amount
        share = (amount / gross) if gross > 0 else 0.0
        p90 = P90_SHARE[leak_type]
        sub = clamp(100.0 * (1.0 - min(share, p90) / p90))
        acc += sub * weight
        components[leak_type] = round(sub, 1)
        components[f"{leak_type}_paise"] = amount
        components[f"{leak_type}_note"] = (
            f"{share:.2%} of trailing-12m revenue lost to {leak_type}"
            f" (0 at the {p90:.0%} P90 benchmark; weight {weight}%)."
        )
    components["leak_total_paise"] = total
    components["gross_revenue_paise"] = gross
    return round(acc / 100.0, 1), components
