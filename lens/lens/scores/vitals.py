"""Vitals Score — CRM engine health (blueprint/05_service_portfolio.md section 5.3 #4).

Formula (weights per CONTRACTS.md V2.4):

    value = (30*deliverability + 25*whatsapp_optin
             + 25*list_hygiene_consent + 20*flow_integrity) / 100

Raw metrics come from the v0 DuckDB base facts (fact_messages, dim_customers,
fact_consent, dim_campaigns) over the trailing windows named in engine.gather_inputs,
normalized linearly to 0-100 between POOR (-> 0) and BEST (-> 100), clamped.
Benchmark constants are v2 stand-ins for the Punara benchmark dataset, anchored
to the seeder realism bar (CONTRACTS.md V2.1: email bounces ~2.5% of sends,
WhatsApp ~95% delivered) and the India D2C ICP (_canon.md section 6).
"""

from __future__ import annotations

from . import linear

# Email bounce rate, trailing 6 months. The 2% industry line scores ~67.
EMAIL_BOUNCE_POOR, EMAIL_BOUNCE_BEST = 0.05, 0.005
# Email unsubscribe rate, trailing 6 months.
EMAIL_UNSUB_POOR, EMAIL_UNSUB_BEST = 0.02, 0.001
# WhatsApp opt-in share of all customers; 45% is the India D2C benchmark best.
WA_OPTIN_POOR, WA_OPTIN_BEST = 0.05, 0.45
# WhatsApp failed-send rate (non-null bounced_at), trailing 6 months.
WA_FAIL_POOR, WA_FAIL_BEST = 0.10, 0.01
# Share of contactable-flagged customers whose flag is backed by a consent grant.
CONSENT_BACKED_POOR, CONSENT_BACKED_BEST = 0.40, 0.95
# Sends-after-revoke as a share of all sends; any violation bites, 1% zeroes it.
REVOKE_VIOLATION_POOR, REVOKE_VIOLATION_BEST = 0.01, 0.0

WEIGHTS = {
    "deliverability": 30,
    "whatsapp_optin": 25,
    "list_hygiene_consent": 25,
    "flow_integrity": 20,
}


def score(inputs: dict) -> tuple[float, dict]:
    """Pure over `queries.vitals_inputs` (CONTRACTS V2.9). inputs:
    email_bounce_rate / email_unsub_rate (0-1, None = no email sends observed
    -> deliverability 0), whatsapp_optin_share (0-1), whatsapp_fail_rate
    (0-1, None = no WA sends -> opt-in sub stands alone),
    consent_backed_share (0-1, None = no contactable customers -> 0),
    sends_after_revoke (int), total_sends (int), flows_total (int),
    flows_active_60d (int, flows with sends in the last 60 days of history)."""
    bounce = inputs.get("email_bounce_rate")
    unsub = inputs.get("email_unsub_rate")
    optin = float(inputs.get("whatsapp_optin_share") or 0.0)
    wa_fail = inputs.get("whatsapp_fail_rate")
    backed = inputs.get("consent_backed_share")
    violations = int(inputs.get("sends_after_revoke") or 0)
    sends = int(inputs.get("total_sends") or 0)
    flows_total = int(inputs.get("flows_total") or 0)
    flows_recent = int(inputs.get("flows_active_60d") or 0)

    if bounce is None:  # no email program: the workhorse channel is unmeasurable
        deliverability = 0.0
    else:
        unsub_sub = linear(float(unsub or 0.0), EMAIL_UNSUB_POOR, EMAIL_UNSUB_BEST)
        deliverability = 0.7 * linear(float(bounce), EMAIL_BOUNCE_POOR, EMAIL_BOUNCE_BEST) + 0.3 * unsub_sub

    optin_sub = linear(optin, WA_OPTIN_POOR, WA_OPTIN_BEST)
    fail_sub = optin_sub if wa_fail is None else linear(float(wa_fail), WA_FAIL_POOR, WA_FAIL_BEST)
    whatsapp_optin = 0.7 * optin_sub + 0.3 * fail_sub

    backed_sub = 0.0 if backed is None else linear(float(backed), CONSENT_BACKED_POOR, CONSENT_BACKED_BEST)
    violation_rate = (violations / sends) if sends else 0.0
    audit_sub = linear(violation_rate, REVOKE_VIOLATION_POOR, REVOKE_VIOLATION_BEST)
    list_hygiene_consent = 0.5 * backed_sub + 0.5 * audit_sub

    # No automations at all is an unhealthy engine, not a clean one: score 0.
    flow_integrity = 100.0 * flows_recent / flows_total if flows_total else 0.0

    subs = {
        "deliverability": deliverability,
        "whatsapp_optin": whatsapp_optin,
        "list_hygiene_consent": list_hygiene_consent,
        "flow_integrity": flow_integrity,
    }
    value = round(sum(subs[k] * w for k, w in WEIGHTS.items()) / 100.0, 1)

    raws: dict = {
        "deliverability": bounce,
        "whatsapp_optin": optin,
        "list_hygiene_consent": backed,
        "flow_integrity": (flows_recent / flows_total) if flows_total else None,
    }
    notes = {
        "deliverability": (
            "no email sends observed; scored 0 (weight 30%)."
            if bounce is None
            else f"{float(bounce):.2%} bounce / {float(unsub or 0.0):.2%} unsubscribe, trailing 6mo"
            f" (bounce: 0 at {EMAIL_BOUNCE_POOR:.1%}, 100 at {EMAIL_BOUNCE_BEST:.1%}; weight 30%)."
        ),
        "whatsapp_optin": (
            f"{optin:.1%} of customers opted in to WhatsApp"
            f" (0 at {WA_OPTIN_POOR:.0%}, 100 at the {WA_OPTIN_BEST:.0%} India benchmark)"
            + (
                "; no WA sends to measure failures (weight 25%)."
                if wa_fail is None
                else f"; {float(wa_fail):.1%} failed sends (weight 25%)."
            )
        ),
        "list_hygiene_consent": (
            (
                "no contactable customers; hygiene unmeasurable"
                if backed is None
                else f"{float(backed):.1%} of contactable flags backed by a consent grant"
            )
            + f"; {violations} sends after revoke of {sends} total (weight 25%)."
        ),
        "flow_integrity": (
            "no automated flows exist; scored 0 (weight 20%)."
            if flows_total == 0
            else f"{flows_recent} of {flows_total} flows sent within the last 60 days (weight 20%)."
        ),
    }
    components: dict = {}
    for k, s in subs.items():
        components[k] = round(s, 1)
        components[f"{k}_raw"] = raws[k]
        components[f"{k}_note"] = notes[k]
    components["sends_after_revoke"] = violations
    return value, components
