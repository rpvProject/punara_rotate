"""Autopilot Score — automation coverage (blueprint/05_service_portfolio.md section 5.3 #6).

Formula (weights per CONTRACTS.md V2.4):

    value = (50*moment_coverage + 30*automated_revenue_share + 20*flow_performance) / 100

moment_coverage weights the six canonical v2 lifecycle moments by value (the
canon names 12 moments; v2 tracks the six in automation_facts). The seed
covers exactly three (welcome/post_purchase/winback via KLF-01/02/03), so the
component reads 60, not 100 — by design (CONTRACTS.md V2.5). Attribution
splits flow vs manual blast on dim_campaigns.campaign_type; the raw revenue
inputs come from the automation_facts and campaign_roi marts.
"""

from __future__ import annotations

from . import linear

# Value weights for the six canonical v2 moments (sum 100). Welcome and winback
# are the classic highest-value automations; COD confirmation is India-specific
# RTO defense; abandoned checkout converts but cannibalizes most.
MOMENT_WEIGHTS = {
    "welcome": 25,
    "winback": 20,
    "post_purchase": 15,
    "replenishment": 15,
    "cod_confirmation": 15,
    "abandoned_checkout": 10,
}
# Flow-attributed share of ALL message-attributed revenue.
AUTO_REV_POOR, AUTO_REV_BEST = 0.05, 0.50
# Flow revenue-per-message over campaign revenue-per-message; parity means the
# automations add nothing over blasts, 3x is compounding.
FLOW_RATIO_POOR, FLOW_RATIO_BEST = 1.0, 3.0

WEIGHTS = {"moment_coverage": 50, "automated_revenue_share": 30, "flow_performance": 20}


def score(inputs: dict) -> tuple[float, dict]:
    """Pure over `queries.autopilot_inputs` (CONTRACTS V2.9). inputs:
    moments (list[dict] with "moment"/"covered" keys, automation_facts rows),
    automated_revenue_share (0-1, None = no message-attributed revenue -> 0),
    flow_revenue_per_send_paise / campaign_revenue_per_send_paise (revenue per
    message; flow None/0 -> 0, campaign None/0 with flows sending -> 100: no
    blasts to beat)."""
    covered = {m["moment"] for m in (inputs.get("moments") or ()) if m.get("covered")}
    share = inputs.get("automated_revenue_share")
    flow_rpm = inputs.get("flow_revenue_per_send_paise")
    campaign_rpm = inputs.get("campaign_revenue_per_send_paise")

    coverage_sub = float(sum(w for m, w in MOMENT_WEIGHTS.items() if m in covered))
    share_sub = 0.0 if share is None else linear(float(share), AUTO_REV_POOR, AUTO_REV_BEST)
    ratio = None
    if not flow_rpm:
        perf_sub = 0.0
    elif not campaign_rpm:
        perf_sub = 100.0
    else:
        ratio = float(flow_rpm) / float(campaign_rpm)
        perf_sub = linear(ratio, FLOW_RATIO_POOR, FLOW_RATIO_BEST)

    subs = {
        "moment_coverage": coverage_sub,
        "automated_revenue_share": share_sub,
        "flow_performance": perf_sub,
    }
    value = round(sum(subs[k] * w for k, w in WEIGHTS.items()) / 100.0, 1)

    uncovered = [m for m in MOMENT_WEIGHTS if m not in covered]
    raws: dict = {
        "moment_coverage": sorted(covered & set(MOMENT_WEIGHTS)),
        "automated_revenue_share": share,
        "flow_performance": ratio,
    }
    notes = {
        "moment_coverage": (
            f"{len(covered & set(MOMENT_WEIGHTS))} of {len(MOMENT_WEIGHTS)} canonical moments covered"
            f" (value-weighted); uncovered: {', '.join(uncovered) or 'none'} (weight 50%)."
        ),
        "automated_revenue_share": (
            "no message-attributed revenue observed; scored 0 (weight 30%)."
            if share is None
            else f"{float(share):.1%} of message-attributed revenue is flow-attributed"
            f" (0 at {AUTO_REV_POOR:.0%}, 100 at {AUTO_REV_BEST:.0%}; weight 30%)."
        ),
        "flow_performance": (
            "no measurable flow sends; scored 0 (weight 20%)."
            if not flow_rpm
            else "flows send but there are no manual blasts to beat; scored 100 (weight 20%)."
            if not campaign_rpm
            else f"flow revenue-per-message is {ratio:.2f}x campaigns'"
            f" (0 at {FLOW_RATIO_POOR:.0f}x parity, 100 at {FLOW_RATIO_BEST:.0f}x; weight 20%)."
        ),
    }
    components: dict = {}
    for k, s in subs.items():
        components[k] = round(s, 1)
        components[f"{k}_raw"] = raws[k]
        components[f"{k}_note"] = notes[k]
    return value, components
