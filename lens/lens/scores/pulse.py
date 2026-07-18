"""Pulse Score — post-purchase customer experience (blueprint/05_service_portfolio.md section 5.3 #7).

Formula (weights per CONTRACTS.md V2.4):

    value = (30*delivery_speed + 30*rto_ndr + 20*support + 20*reviews_nps) / 100

Raw metrics are trailing-6-month aggregates of the cx_facts mart (monthly
grain), normalized linearly to 0-100 between POOR (-> 0) and BEST (-> 100),
clamped. Benchmark constants are v2 stand-ins for the Punara benchmark dataset
(CONTRACTS.md V2.4 names the 5-day delivery benchmark; RTO/CSAT/NPS anchors
follow the seeder realism bar and the India D2C ICP). Support and reviews_nps
average whichever of their sub-metrics are observed; a fully unobserved
component scores 0 — no data is not good news for CX.
"""

from __future__ import annotations

from . import linear

# Median ship->deliver days; the category benchmark promise is 5 days.
DELIVERY_POOR_DAYS, DELIVERY_BEST_DAYS = 11.0, 5.0
# RTO share of shipped orders vs the COD-heavy category benchmark.
RTO_POOR, RTO_BEST = 0.20, 0.03
# Support: median resolution hours, 72h-breach share, average CSAT (1-5).
RESOLUTION_POOR_H, RESOLUTION_BEST_H = 72.0, 12.0
BREACH_POOR, BREACH_BEST = 0.30, 0.0
CSAT_POOR, CSAT_BEST = 3.0, 4.8
# Voice: average review rating (the 4.2 category benchmark scores ~71) and NPS.
RATING_POOR, RATING_BEST = 3.2, 4.6
NPS_POOR, NPS_BEST = -20.0, 70.0

WEIGHTS = {"delivery_speed": 30, "rto_ndr": 30, "support": 20, "reviews_nps": 20}


def _mean_available(parts: list[float | None]) -> float:
    seen = [p for p in parts if p is not None]
    return sum(seen) / len(seen) if seen else 0.0


def score(inputs: dict) -> tuple[float, dict]:
    """Pure. inputs (trailing-6mo cx_facts averages, None = unobserved):
    median_delivery_days, rto_rate (0-1), median_resolution_hours,
    breach_rate (0-1), avg_csat (1-5), avg_review_rating (1-5), nps (-100..100)."""
    delivery = inputs.get("median_delivery_days")
    rto = inputs.get("rto_rate")
    resolution = inputs.get("median_resolution_hours")
    breach = inputs.get("breach_rate")
    csat = inputs.get("avg_csat")
    rating = inputs.get("avg_review_rating")
    nps = inputs.get("nps")

    subs = {
        "delivery_speed": 0.0 if delivery is None else linear(float(delivery), DELIVERY_POOR_DAYS, DELIVERY_BEST_DAYS),
        "rto_ndr": 0.0 if rto is None else linear(float(rto), RTO_POOR, RTO_BEST),
        "support": _mean_available(
            [
                None if resolution is None else linear(float(resolution), RESOLUTION_POOR_H, RESOLUTION_BEST_H),
                None if breach is None else linear(float(breach), BREACH_POOR, BREACH_BEST),
                None if csat is None else linear(float(csat), CSAT_POOR, CSAT_BEST),
            ]
        ),
        "reviews_nps": _mean_available(
            [
                None if rating is None else linear(float(rating), RATING_POOR, RATING_BEST),
                None if nps is None else linear(float(nps), NPS_POOR, NPS_BEST),
            ]
        ),
    }
    value = round(sum(subs[k] * w for k, w in WEIGHTS.items()) / 100.0, 1)

    raws: dict = {
        "delivery_speed": delivery,
        "rto_ndr": rto,
        "support": resolution,
        "reviews_nps": rating,
    }
    notes = {
        "delivery_speed": (
            "no delivered orders observed; scored 0 (weight 30%)."
            if delivery is None
            else f"median {float(delivery):.1f} days ship to deliver"
            f" (0 at {DELIVERY_POOR_DAYS:.0f}d, 100 at the {DELIVERY_BEST_DAYS:.0f}d benchmark; weight 30%)."
        ),
        "rto_ndr": (
            "no shipment outcomes observed; scored 0 (weight 30%)."
            if rto is None
            else f"{float(rto):.1%} of orders RTO"
            f" (0 at {RTO_POOR:.0%}, 100 at {RTO_BEST:.0%}; weight 30%)."
        ),
        "support": (
            "no support data observed; scored 0 (weight 20%)."
            if resolution is None and breach is None and csat is None
            else "mean of observed sub-metrics: "
            + ", ".join(
                s
                for s in (
                    None if resolution is None else f"median resolution {float(resolution):.0f}h",
                    None if breach is None else f"{float(breach):.1%} breach 72h",
                    None if csat is None else f"CSAT {float(csat):.2f}",
                )
                if s
            )
            + " (weight 20%)."
        ),
        "reviews_nps": (
            "no reviews or NPS observed; scored 0 (weight 20%)."
            if rating is None and nps is None
            else "mean of observed sub-metrics: "
            + ", ".join(
                s
                for s in (
                    None if rating is None else f"avg rating {float(rating):.2f} (benchmark {4.2})",
                    None if nps is None else f"NPS {float(nps):.0f}",
                )
                if s
            )
            + " (weight 20%)."
        ),
    }
    components: dict = {}
    for k, s in subs.items():
        components[k] = round(s, 1)
        components[f"{k}_raw"] = raws[k]
        components[f"{k}_note"] = notes[k]
    components["nps_raw"] = nps
    return value, components
