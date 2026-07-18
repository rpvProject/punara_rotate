"""Altitude Score — customer maturity (blueprint/05_service_portfolio.md section 5.3 #9).

HONEST PROXY: the real Altitude is a structured consultant assessment during
the Decode (org interviews + decision-log review, refreshed quarterly). Lens
cannot interview anyone, so this derives measurable system-usage proxies from
the platform itself, per CONTRACTS.md V2.4. When the questionnaire ships, it
replaces maturity_position and decision_hygiene; the proxies stay as evidence.

Formula (weights per CONTRACTS.md V2.4):

    value = (40*maturity_position + 30*decision_hygiene
             + 20*capability + 10*executive_engagement) / 100

maturity_position is the canon 4-rung ladder (reactive -> reporting ->
predictive -> compounding), 25 points per rung with partial credit:

    1. data foundation  — Signal >= 70 (partial credit from 40); you cannot
       climb on data you cannot trust.
    2. reporting        — marts + scores fresh (in-platform this is true by
       construction whenever the pipeline runs).
    3. predictive       — predictions table populated (half credit) and fresh
       within 7 days (full).
    4. compounding      — experiments concluding regularly (half) + shipped
       winners banked (half).
"""

from __future__ import annotations

from . import linear

# Rung 1: Signal at/above the canon 70 gate = full rung; partial from 40.
SIGNAL_FULL, SIGNAL_PARTIAL_FROM = 70.0, 40.0
# Rung 4: >= 6 concluded in 6 months (1/mo) and >= 3 shipped winners = full.
CONCLUDED_6MO_FULL = 6
WINNERS_FULL = 3
# Capability: sustained cadence vs the 2/mo commitment (shared with Velocity).
CADENCE_COMMIT = 2.0
# Executive engagement: consecutive monthly score recomputes; 6 months = 100.
STREAK_FULL_MONTHS = 6.0

WEIGHTS = {
    "maturity_position": 40,
    "decision_hygiene": 30,
    "capability": 20,
    "executive_engagement": 10,
}


def score(inputs: dict) -> tuple[float, dict]:
    """Pure over `queries.altitude_inputs` (CONTRACTS V2.9), plus signal_value
    (0-100, injected by compute_all from the same run, None = 0 rung). inputs:
    marts_built (bool), predictions_rows (int), predictions_fresh (bool),
    concluded_6mo (int), winners_shipped (int), decided_share (0-1 share of
    concluded with hypothesis + decision, None = 0), cadence_starts_6mo (int,
    non-draft experiments started in the trailing 6 months),
    flows_total / flows_active_60d (int), monthly_run_streak (int)."""
    signal_value = inputs.get("signal_value")
    marts_fresh = bool(inputs.get("marts_built"))
    pred_populated = int(inputs.get("predictions_rows") or 0) > 0
    pred_fresh = bool(inputs.get("predictions_fresh"))
    concluded_6mo = int(inputs.get("concluded_6mo") or 0)
    winners = int(inputs.get("winners_shipped") or 0)
    decided_share = inputs.get("decided_share")
    cadence = float(inputs.get("cadence_starts_6mo") or 0) / 6.0
    flows_total = int(inputs.get("flows_total") or 0)
    flows_share = (
        int(inputs.get("flows_active_60d") or 0) / flows_total if flows_total else None
    )
    streak = int(inputs.get("monthly_run_streak") or 0)

    rung_data = (
        0.0
        if signal_value is None
        else 25.0 * linear(float(signal_value), SIGNAL_PARTIAL_FROM, SIGNAL_FULL) / 100.0
    )
    rung_reporting = 25.0 if marts_fresh else 0.0
    rung_predictive = 25.0 if (pred_populated and pred_fresh) else 12.5 if pred_populated else 0.0
    rung_compounding = 12.5 * min(concluded_6mo / CONCLUDED_6MO_FULL, 1.0) + 12.5 * min(
        winners / WINNERS_FULL, 1.0
    )
    ladder = rung_data + rung_reporting + rung_predictive + rung_compounding

    subs = {
        "maturity_position": ladder,
        "decision_hygiene": 100.0 * float(decided_share) if decided_share is not None else 0.0,
        "capability": 0.5 * linear(cadence, 0.0, CADENCE_COMMIT)
        + 0.5 * (100.0 * float(flows_share) if flows_share is not None else 0.0),
        "executive_engagement": linear(float(streak), 0.0, STREAK_FULL_MONTHS),
    }
    value = round(sum(subs[k] * w for k, w in WEIGHTS.items()) / 100.0, 1)

    raws: dict = {
        "maturity_position": {
            "data_foundation": round(rung_data, 1),
            "reporting": round(rung_reporting, 1),
            "predictive": round(rung_predictive, 1),
            "compounding": round(rung_compounding, 1),
        },
        "decision_hygiene": decided_share,
        "capability": cadence,
        "executive_engagement": streak,
    }
    notes = {
        "maturity_position": (
            "4-rung ladder, 25 each with partial credit — proxy for the Decode"
            f" maturity interview: data foundation {rung_data:.1f} (Signal"
            f" {'-' if signal_value is None else f'{float(signal_value):.1f}'} vs the {SIGNAL_FULL:.0f} gate),"
            f" reporting {rung_reporting:.1f}, predictive {rung_predictive:.1f},"
            f" compounding {rung_compounding:.1f} (weight 40%)."
        ),
        "decision_hygiene": (
            "no concluded experiments; no decision log to audit (weight 30%)."
            if decided_share is None
            else f"{float(decided_share):.0%} of concluded experiments carry a hypothesis"
            " and a decision (weight 30%)."
        ),
        "capability": (
            f"{cadence:.2f} experiments/mo vs the {CADENCE_COMMIT:.0f}/mo commitment;"
            + (
                " no flows to keep up."
                if flows_share is None
                else f" {float(flows_share):.0%} of flows sending recently."
            )
            + " (weight 20%)."
        ),
        "executive_engagement": (
            f"{streak} consecutive months with a score recompute"
            f" (100 at {STREAK_FULL_MONTHS:.0f}; weight 10%)."
        ),
    }
    components: dict = {}
    for k, s in subs.items():
        components[k] = round(s, 1)
        components[f"{k}_raw"] = raws[k]
        components[f"{k}_note"] = notes[k]
    components["proxy_note"] = (
        "Altitude is a system-usage proxy for the Decode structured assessment;"
        " consultant questionnaire supersedes it when administered."
    )
    return value, components
