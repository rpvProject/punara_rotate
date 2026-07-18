"""Signal Score — data quality (blueprint/05_service_portfolio.md section 5.3 #8).

Formula (weights per CONTRACTS.md section 2.4):

    value = (35*identity_resolution_rate + 25*field_completeness
             + 25*cross_source_reconciliation + 15*history_depth) / 100

Signal below 40 gates everything (05_service_portfolio.md section 5.3): you
cannot model on data you cannot trust. Raw metrics are normalized linearly to
0-100 between POOR (-> 0) and BEST (-> 100), clamped. Benchmark constants are
v0 stand-ins for the Punara benchmark dataset.
"""

from __future__ import annotations

from . import linear

# Share of orders attached to a resolved customer_id (fact_orders).
IDENT_POOR, IDENT_BEST = 0.60, 0.98
# Share of customers with both phone and email on file (customer_pii, SQLite).
# BEST = 1.0: a perfect completeness sub-score means literally no gaps — this
# also keeps Signal off a flat 100 on clean-but-not-perfect books.
COMPLETE_POOR, COMPLETE_BEST = 0.50, 1.0
# Share of prepaid paid orders with a matching captured payment (Shopify vs Razorpay).
RECON_POOR, RECON_BEST = 0.70, 0.99
# Months of order history; ICP gate is >= 18 months (_canon.md section 6).
HISTORY_BEST_MONTHS = 18.0

WEIGHTS = {
    "identity_resolution_rate": 35,
    "field_completeness": 25,
    "cross_source_reconciliation": 25,
    "history_depth": 15,
}


def score(inputs: dict) -> tuple[float, dict]:
    """Pure. inputs: identity_resolution_rate (0-1), field_completeness (0-1),
    payment_match_rate (0-1), history_months (float >= 0)."""
    ident = float(inputs.get("identity_resolution_rate") or 0.0)
    complete = float(inputs.get("field_completeness") or 0.0)
    recon = float(inputs.get("payment_match_rate") or 0.0)
    months = float(inputs.get("history_months") or 0.0)

    subs = {
        "identity_resolution_rate": linear(ident, IDENT_POOR, IDENT_BEST),
        "field_completeness": linear(complete, COMPLETE_POOR, COMPLETE_BEST),
        "cross_source_reconciliation": linear(recon, RECON_POOR, RECON_BEST),
        "history_depth": linear(months, 0.0, HISTORY_BEST_MONTHS),
    }
    value = round(sum(subs[k] * w for k, w in WEIGHTS.items()) / 100.0, 1)

    raws = {
        "identity_resolution_rate": ident,
        "field_completeness": complete,
        "cross_source_reconciliation": recon,
        "history_depth": months,
    }
    notes = {
        "identity_resolution_rate": (
            f"{ident:.1%} of orders resolve to a customer"
            f" (0 at {IDENT_POOR:.0%}, 100 at {IDENT_BEST:.0%}; weight 35%)."
        ),
        "field_completeness": (
            f"{complete:.1%} of customers have both phone and email on file"
            f" (0 at {COMPLETE_POOR:.0%}, 100 at {COMPLETE_BEST:.0%}; weight 25%)."
        ),
        "cross_source_reconciliation": (
            f"{recon:.1%} of prepaid paid orders reconcile to a captured payment"
            f" (0 at {RECON_POOR:.0%}, 100 at {RECON_BEST:.0%}; weight 25%)."
        ),
        "history_depth": (
            f"{months:.0f} months of order history"
            f" (0 at 0, 100 at {HISTORY_BEST_MONTHS:.0f} months, the ICP gate; weight 15%)."
        ),
    }
    components: dict = {}
    for k, s in subs.items():
        components[k] = round(s, 1)
        components[f"{k}_raw"] = raws[k]
        components[f"{k}_note"] = notes[k]
    return value, components
