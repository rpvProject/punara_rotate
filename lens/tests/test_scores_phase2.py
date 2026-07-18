"""Phase-2 scores tests: the five new pure scorers, the full-CIQ composite,
and engine wiring (nine scorers + graceful partial fallback).

Same isolation approach as test_scores.py: scorers are pure functions tested
with plain dicts; `engine.gather_inputs` is monkeypatched because the new
marts (cx_facts, automation_facts) belong to the analytics builder.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from lens.models import Base, ScoreRun, Tenant
from lens.scores import altitude, autopilot, ciq, pulse, velocity, vitals
from lens.scores import engine as engine_mod

# --------------------------------------------------------------------- vitals

VITALS_MID = {
    "email_bounce_rate": 0.0275,  # midpoint of 0.05-0.005 -> 50
    "email_unsub_rate": 0.0105,  # midpoint of 0.02-0.001 -> 50
    "whatsapp_optin_share": 0.25,  # midpoint of 0.05-0.45 -> 50
    "whatsapp_fail_rate": 0.055,  # midpoint of 0.10-0.01 -> 50
    "consent_backed_share": 0.675,  # midpoint of 0.40-0.95 -> 50
    "sends_after_revoke": 5,  # 5/1000 = 0.005, midpoint of 0.01-0.0 -> 50
    "total_sends": 1000,
    "flows_total": 2,
    "flows_active_60d": 1,  # 1/2 -> 50
}


def test_vitals_known_output() -> None:
    value, components = vitals.score(VITALS_MID)
    assert value == 50.0
    for name in vitals.WEIGHTS:
        assert components[name] == 50.0
        assert f"{name}_raw" in components
        assert isinstance(components[f"{name}_note"], str)


def test_vitals_bounds() -> None:
    lo, _ = vitals.score(
        {
            "email_bounce_rate": 0.5,
            "email_unsub_rate": 0.5,
            "whatsapp_optin_share": 0.0,
            "whatsapp_fail_rate": 0.9,
            "consent_backed_share": 0.0,
            "sends_after_revoke": 500,
            "total_sends": 1000,
            "flows_total": 0,
            "flows_active_60d": 0,
        }
    )
    hi, _ = vitals.score(
        {
            "email_bounce_rate": 0.0,
            "email_unsub_rate": 0.0,
            "whatsapp_optin_share": 0.9,
            "whatsapp_fail_rate": 0.0,
            "consent_backed_share": 1.0,
            "sends_after_revoke": 0,
            "total_sends": 1000,
            "flows_total": 3,
            "flows_active_60d": 3,
        }
    )
    assert lo == 0.0
    assert hi == 100.0


def test_vitals_no_email_program_scores_deliverability_zero() -> None:
    value, components = vitals.score({**VITALS_MID, "email_bounce_rate": None, "email_unsub_rate": None})
    assert components["deliverability"] == 0.0
    assert value == pytest.approx(50.0 - 0.30 * 50.0, abs=0.1)


def test_vitals_no_flows_is_not_clean() -> None:
    _, components = vitals.score({**VITALS_MID, "flows_total": 0, "flows_active_60d": 0})
    assert components["flow_integrity"] == 0.0
    assert components["flow_integrity_raw"] is None


def test_vitals_sends_after_revoke_bite() -> None:
    _, clean = vitals.score({**VITALS_MID, "sends_after_revoke": 0})
    _, dirty = vitals.score({**VITALS_MID, "sends_after_revoke": 20})  # 2% > 1% poor line
    assert clean["list_hygiene_consent"] == 75.0  # 0.5*50 + 0.5*100
    assert dirty["list_hygiene_consent"] == 25.0  # 0.5*50 + 0.5*0


# --------------------------------------------------------------------- velocity

VELOCITY_MID = {
    "window_months": 6,
    "monthly_starts": {"2026-01": 3, "2026-03": 3},  # 6 starts = 1.0/mo vs 2/mo -> 50
    "concluded": 4,
    "concluded_valid": 2,  # 50
    "concluded_decided": 2,  # 50
}


def test_velocity_known_output() -> None:
    value, components = velocity.score(VELOCITY_MID)
    assert value == 50.0
    for name in velocity.WEIGHTS:
        assert components[name] == 50.0


def test_velocity_no_experiments_scores_zero() -> None:
    value, components = velocity.score(
        {"window_months": 6, "monthly_starts": {}, "concluded": 0, "concluded_valid": 0, "concluded_decided": 0}
    )
    assert value == 0.0
    assert components["validity_raw"] is None
    assert components["follow_through_raw"] is None


def test_velocity_bounds() -> None:
    hi, _ = velocity.score(
        {
            "window_months": 6,
            "monthly_starts": {"2026-01": 30},
            "concluded": 9,
            "concluded_valid": 9,
            "concluded_decided": 9,
        }
    )
    assert hi == 100.0


# --------------------------------------------------------------------- autopilot

AUTOPILOT_SEED = {
    # the seed covers exactly these three (KLF-01/02/03) -> value-weighted 60
    "moments": [
        {"moment": "welcome", "covered": True},
        {"moment": "post_purchase", "covered": True},
        {"moment": "winback", "covered": True},
        {"moment": "replenishment", "covered": False},
        {"moment": "cod_confirmation", "covered": False},
        {"moment": "abandoned_checkout", "covered": False},
    ],
    "automated_revenue_share": 0.275,  # midpoint of 0.05-0.50 -> 50
    "flow_revenue_per_send_paise": 2000.0,
    "campaign_revenue_per_send_paise": 1000.0,  # ratio 2.0, midpoint of 1.0-3.0 -> 50
}


def test_autopilot_seed_coverage_is_not_100() -> None:
    value, components = autopilot.score(AUTOPILOT_SEED)
    assert components["moment_coverage"] == 60.0  # 25 + 15 + 20
    assert components["automated_revenue_share"] == 50.0
    assert components["flow_performance"] == 50.0
    assert value == 55.0  # (50*60 + 30*50 + 20*50) / 100


def test_autopilot_bounds() -> None:
    lo, _ = autopilot.score({"moments": [], "automated_revenue_share": None})
    hi, _ = autopilot.score(
        {
            "moments": [{"moment": m, "covered": True} for m in autopilot.MOMENT_WEIGHTS],
            "automated_revenue_share": 0.9,
            "flow_revenue_per_send_paise": 5000.0,
            "campaign_revenue_per_send_paise": 1000.0,
        }
    )
    assert lo == 0.0
    assert hi == 100.0


def test_autopilot_no_blasts_to_beat() -> None:
    _, components = autopilot.score({**AUTOPILOT_SEED, "campaign_revenue_per_send_paise": None})
    assert components["flow_performance"] == 100.0
    _, components = autopilot.score({**AUTOPILOT_SEED, "flow_revenue_per_send_paise": None})
    assert components["flow_performance"] == 0.0


def test_autopilot_moment_weights_sum_100() -> None:
    assert sum(autopilot.MOMENT_WEIGHTS.values()) == 100


# --------------------------------------------------------------------- pulse

PULSE_MID = {
    "median_delivery_days": 8.0,  # midpoint of 11-5 -> 50
    "rto_rate": 0.115,  # midpoint of 0.20-0.03 -> 50
    "median_resolution_hours": 42.0,  # midpoint of 72-12 -> 50
    "breach_rate": 0.15,  # midpoint of 0.30-0.0 -> 50
    "avg_csat": 3.9,  # midpoint of 3.0-4.8 -> 50
    "avg_review_rating": 3.9,  # midpoint of 3.2-4.6 -> 50
    "nps": 25.0,  # midpoint of -20..70 -> 50
}


def test_pulse_known_output() -> None:
    value, components = pulse.score(PULSE_MID)
    assert value == 50.0
    for name in pulse.WEIGHTS:
        assert components[name] == 50.0


def test_pulse_all_unobserved_scores_zero() -> None:
    value, _ = pulse.score({k: None for k in PULSE_MID})
    assert value == 0.0


def test_pulse_partial_submetrics_average_available() -> None:
    _, components = pulse.score(
        {**PULSE_MID, "avg_csat": None, "median_resolution_hours": 12.0, "breach_rate": 0.0}
    )
    assert components["support"] == 100.0
    _, components = pulse.score({**PULSE_MID, "nps": None, "avg_review_rating": 4.6})
    assert components["reviews_nps"] == 100.0


def test_pulse_bounds() -> None:
    lo, _ = pulse.score(
        {
            "median_delivery_days": 30.0,
            "rto_rate": 0.6,
            "median_resolution_hours": 300.0,
            "breach_rate": 0.9,
            "avg_csat": 1.0,
            "avg_review_rating": 1.5,
            "nps": -80.0,
        }
    )
    hi, _ = pulse.score(
        {
            "median_delivery_days": 2.0,
            "rto_rate": 0.0,
            "median_resolution_hours": 4.0,
            "breach_rate": 0.0,
            "avg_csat": 5.0,
            "avg_review_rating": 5.0,
            "nps": 90.0,
        }
    )
    assert lo == 0.0
    assert hi == 100.0


# --------------------------------------------------------------------- altitude

ALTITUDE_MID = {
    "signal_value": 55.0,  # linear(55, 40, 70) = 50 -> rung 12.5
    "marts_built": True,  # rung 25
    "predictions_rows": 2,  # populated
    "predictions_fresh": False,  # rung 12.5
    "concluded_6mo": 6,  # 12.5
    "winners_shipped": 3,  # 12.5 -> compounding 25; ladder 75
    "decided_share": 0.5,  # 50
    "cadence_starts_6mo": 6,  # 1.0/mo -> 50
    "flows_total": 2,
    "flows_active_60d": 1,  # 0.5 share -> 50 -> capability 50
    "monthly_run_streak": 3,  # 50
}


def test_altitude_known_output() -> None:
    value, components = altitude.score(ALTITUDE_MID)
    assert components["maturity_position"] == 75.0
    assert components["maturity_position_raw"] == {
        "data_foundation": 12.5,
        "reporting": 25.0,
        "predictive": 12.5,
        "compounding": 25.0,
    }
    assert components["decision_hygiene"] == 50.0
    assert components["capability"] == 50.0
    assert components["executive_engagement"] == 50.0
    # 40*75 + 30*50 + 20*50 + 10*50 = 60
    assert value == 60.0
    assert "proxy" in components["proxy_note"]


def test_altitude_reactive_floor_and_compounding_ceiling() -> None:
    lo, lo_c = altitude.score(
        {
            "signal_value": 30.0,  # below the partial-credit floor
            "marts_built": False,
            "predictions_rows": 0,
            "predictions_fresh": False,
            "concluded_6mo": 0,
            "winners_shipped": 0,
            "decided_share": None,
            "cadence_starts_6mo": 0,
            "flows_total": 0,
            "flows_active_60d": 0,
            "monthly_run_streak": 0,
        }
    )
    hi, _ = altitude.score(
        {
            "signal_value": 85.0,
            "marts_built": True,
            "predictions_rows": 9000,
            "predictions_fresh": True,
            "concluded_6mo": 8,
            "winners_shipped": 5,
            "decided_share": 1.0,
            "cadence_starts_6mo": 15,  # 2.5/mo
            "flows_total": 3,
            "flows_active_60d": 3,
            "monthly_run_streak": 8,
        }
    )
    assert lo == 0.0
    assert lo_c["maturity_position"] == 0.0
    assert hi == 100.0


def test_altitude_missing_signal_zeroes_rung_one() -> None:
    _, components = altitude.score({**ALTITUDE_MID, "signal_value": None})
    assert components["maturity_position_raw"]["data_foundation"] == 0.0


# --------------------------------------------------------------------- full ciq

NINE_AT_60 = {name: 60.0 for name in ciq.CANON_WEIGHTS}


def test_ciq_canon_weights_sum_to_100() -> None:
    assert sum(ciq.CANON_WEIGHTS.values()) == 100
    assert set(ciq.CANON_WEIGHTS) == {
        "gravity", "flow", "signal", "watertight", "vitals",
        "velocity", "pulse", "autopilot", "altitude",
    }


def test_ciq_full_coverage() -> None:
    value, components = ciq.score(NINE_AT_60)
    assert value == 60.0
    assert components["coverage"] == "9/9"
    assert components["missing"] == []
    assert components["weights_renormalized"] == {k: float(w) for k, w in ciq.CANON_WEIGHTS.items()}

    # known composite: gravity 80, everything else 60 -> (80*20 + 60*80)/100
    value, _ = ciq.score({**NINE_AT_60, "gravity": 80.0})
    assert value == 64.0


def test_ciq_partial_fallback_still_works() -> None:
    # v0 four only: (80*20 + 60*12 + 70*12 + 40*12) / 56 = 65.0
    value, components = ciq.score({"gravity": 80.0, "flow": 60.0, "signal": 70.0, "watertight": 40.0})
    assert value == 65.0
    assert components["coverage"] == "4/9"
    assert set(components["missing"]) == {"vitals", "velocity", "autopilot", "pulse", "altitude"}
    assert sum(components["weights_renormalized"].values()) == pytest.approx(100.0, abs=0.05)

    # None values are unavailable, same as missing keys
    value_none, _ = ciq.score({**NINE_AT_60, "pulse": None, "autopilot": None})
    value_missing, _ = ciq.score({k: v for k, v in NINE_AT_60.items() if k not in ("pulse", "autopilot")})
    assert value_none == value_missing

    value, components = ciq.score({})
    assert value == 0.0
    assert components["coverage"] == "0/9"


# --------------------------------------------------------------------- engine

FULL_INPUTS = {
    "gravity": {
        "repeat_rate_90d": 0.20,
        "median_repurchase_days": 80.0,
        "avg_m3_retention": 0.145,
        "repeat_revenue_share": 0.275,
    },
    "flow": {
        "healthy_stage_share": 0.24,
        "new_to_active_rate": 0.175,
        "slipping_to_dormant_rate": 0.725,
        "reactivation_rate": 0.06,
    },
    "signal": {
        "identity_resolution_rate": 0.79,
        "field_completeness": 0.75,
        "payment_match_rate": 0.845,
        "history_months": 9.0,
    },
    "watertight": {"gross_revenue_paise": 100_000_000, "leak_paise": {"rto_cod": 3_000_000}},
    "vitals": VITALS_MID,
    "velocity": VELOCITY_MID,
    "autopilot": AUTOPILOT_SEED,
    "pulse": PULSE_MID,
    "altitude": ALTITUDE_MID,
}

NINE = ("gravity", "flow", "signal", "watertight", "vitals", "velocity", "autopilot", "pulse", "altitude")


@pytest.fixture()
def session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Tenant(id=1, slug="t-p2", name="Phase2 Tenant"))
        s.commit()
        yield s


def _copy_inputs() -> dict:
    return {k: (dict(v) if isinstance(v, dict) else v) for k, v in FULL_INPUTS.items()}


def test_compute_all_nine_plus_full_ciq(session, monkeypatch) -> None:
    monkeypatch.setattr(engine_mod, "gather_inputs", lambda s, t: _copy_inputs())

    runs = engine_mod.compute_all(session, tenant_id=1)
    assert [r.score for r in runs] == list(NINE) + ["ciq"]
    assert all(r.definition_version == "v2.0" for r in runs)
    assert all(0.0 <= r.value <= 100.0 for r in runs)

    by_score = {r.score: r for r in runs}
    assert by_score["ciq"].components["coverage"] == "9/9"
    assert by_score["ciq"].components["missing"] == []
    expected_ciq, _ = ciq.score({name: by_score[name].value for name in NINE})
    assert by_score["ciq"].value == expected_ciq
    # altitude consumed this run's signal value (injected by the engine)
    signal_value = by_score["signal"].value
    assert by_score["altitude"].components["maturity_position_raw"]["data_foundation"] == round(
        25.0 * max(0.0, min(100.0, (signal_value - 40.0) / 30.0 * 100.0)) / 100.0, 1
    )
    assert session.query(ScoreRun).count() == 10


def test_compute_all_partial_fallback(session, monkeypatch) -> None:
    partial = _copy_inputs()
    partial["autopilot"] = None  # analytics mart not built yet
    partial["pulse"] = None
    monkeypatch.setattr(engine_mod, "gather_inputs", lambda s, t: partial)

    runs = engine_mod.compute_all(session, tenant_id=1)
    names = [r.score for r in runs]
    assert "autopilot" not in names and "pulse" not in names
    assert names[-1] == "ciq"

    ciq_run = runs[-1]
    assert ciq_run.components["coverage"] == "7/9"
    assert set(ciq_run.components["missing"]) == {"autopilot", "pulse"}
    assert sum(ciq_run.components["weights_renormalized"].values()) == pytest.approx(100.0, abs=0.05)
    assert 0.0 <= ciq_run.value <= 100.0
