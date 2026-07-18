"""Scores agent tests: pure scorer formulas, bounds, CIQ reweighting, and
engine persistence/hash stability.

`engine.gather_inputs` is monkeypatched in the engine tests because it reads
the DuckDB marts owned by the analytics agent (lens/olap.py, lens/marts.py),
which may not exist on disk yet. Scorers themselves are pure and need no DB.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from lens.models import Base, ScoreRun, Tenant
from lens.scores import ciq, clamp, flow, gravity, linear, signal, watertight
from lens.scores import engine as engine_mod

# --------------------------------------------------------------------- helpers


def test_linear_and_clamp() -> None:
    assert linear(0.5, 0.0, 1.0) == 50.0
    assert linear(-1.0, 0.0, 1.0) == 0.0
    assert linear(2.0, 0.0, 1.0) == 100.0
    # lower-is-better direction
    assert linear(120.0, 120.0, 40.0) == 0.0
    assert linear(40.0, 120.0, 40.0) == 100.0
    assert linear(80.0, 120.0, 40.0) == 50.0
    assert linear(5.0, 3.0, 3.0) == 100.0  # degenerate range
    assert clamp(-5.0) == 0.0 and clamp(105.0) == 100.0


# --------------------------------------------------------------------- gravity

GRAVITY_MID = {
    "repeat_rate_90d": 0.20,  # midpoint of 0.05-0.35 -> 50
    "median_repurchase_days": 80.0,  # midpoint of 120-40 -> 50
    "avg_m3_retention": 0.145,  # midpoint of 0.04-0.25 -> 50
    "repeat_revenue_share": 0.275,  # midpoint of 0.10-0.45 -> 50
}


def test_gravity_known_output() -> None:
    value, components = gravity.score(GRAVITY_MID)
    assert value == 50.0
    for name in gravity.WEIGHTS:
        assert components[name] == 50.0
        assert f"{name}_raw" in components
        assert isinstance(components[f"{name}_note"], str)


def test_gravity_bounds() -> None:
    lo, _ = gravity.score(
        {"repeat_rate_90d": 0.0, "median_repurchase_days": 999, "avg_m3_retention": 0.0, "repeat_revenue_share": 0.0}
    )
    hi, _ = gravity.score(
        {"repeat_rate_90d": 0.9, "median_repurchase_days": 1, "avg_m3_retention": 0.9, "repeat_revenue_share": 0.9}
    )
    assert lo == 0.0
    assert hi == 100.0


def test_gravity_no_repeats_scores_latency_zero() -> None:
    value, components = gravity.score({**GRAVITY_MID, "median_repurchase_days": None})
    assert components["repurchase_latency"] == 0.0
    assert components["repurchase_latency_raw"] is None
    assert value == pytest.approx(50.0 - 0.25 * 50.0, abs=0.1)


# --------------------------------------------------------------------- flow

FLOW_MID = {
    "healthy_stage_share": 0.24,  # midpoint of 0.08-0.40 -> 50
    "new_to_active_rate": 0.175,  # midpoint of 0.05-0.30 -> 50
    "slipping_to_dormant_rate": 0.725,  # midpoint of 0.95-0.50 -> 50
    "reactivation_rate": 0.06,  # midpoint of 0.0-0.12 -> 50
}


def test_flow_known_output() -> None:
    value, components = flow.score(FLOW_MID)
    assert value == 50.0
    for name in flow.WEIGHTS:
        assert components[name] == 50.0


def test_flow_missing_cohorts_score_hundred() -> None:
    value, components = flow.score(
        {**FLOW_MID, "slipping_to_dormant_rate": None, "reactivation_rate": None}
    )
    assert components["slipping_to_dormant_leak"] == 100.0
    assert components["reactivation_rate"] == 100.0
    # 35*50 + 30*50 + 25*100 + 10*100 = 67.5
    assert value == 67.5


def test_flow_bounds() -> None:
    lo, _ = flow.score(
        {"healthy_stage_share": 0, "new_to_active_rate": 0, "slipping_to_dormant_rate": 1.0, "reactivation_rate": 0.0}
    )
    hi, _ = flow.score(
        {"healthy_stage_share": 1, "new_to_active_rate": 1, "slipping_to_dormant_rate": 0.0, "reactivation_rate": 1.0}
    )
    assert lo == 0.0
    assert hi == 100.0


# --------------------------------------------------------------------- signal

SIGNAL_MID = {
    "identity_resolution_rate": 0.79,  # midpoint of 0.60-0.98 -> 50
    "field_completeness": 0.75,  # midpoint of 0.50-1.0 -> 50
    "payment_match_rate": 0.845,  # midpoint of 0.70-0.99 -> 50
    "history_months": 9.0,  # midpoint of 0-18 -> 50
}


def test_signal_known_output() -> None:
    value, components = signal.score(SIGNAL_MID)
    assert value == 50.0
    for name in signal.WEIGHTS:
        assert components[name] == 50.0


def test_signal_bounds() -> None:
    lo, _ = signal.score(
        {"identity_resolution_rate": 0, "field_completeness": 0, "payment_match_rate": 0, "history_months": 0}
    )
    hi, _ = signal.score(
        {"identity_resolution_rate": 1, "field_completeness": 1, "payment_match_rate": 1, "history_months": 24}
    )
    assert lo == 0.0
    assert hi == 100.0


# --------------------------------------------------------------------- watertight


def test_watertight_formula() -> None:
    # gross 10,00,00,000 paise; every leak at exactly half its P90 share -> all subs 50
    value, components = watertight.score(
        {
            "gross_revenue_paise": 100_000_000,
            "leak_paise": {
                "preventable_churn": 4_000_000,  # 4% vs P90 8%
                "rto_cod": 3_000_000,  # 3% vs 6%
                "failed_payments": 1_000_000,  # 1% vs 2%
                "discount_abuse": 1_500_000,  # 1.5% vs 3%
            },
        }
    )
    assert value == 50.0
    assert components["leak_total_paise"] == 9_500_000
    for leak_type in watertight.WEIGHTS:
        assert components[leak_type] == 50.0
        assert components[f"{leak_type}_paise"] > 0


def test_watertight_caps_at_p90_and_missing_leak_is_clean() -> None:
    value, components = watertight.score(
        {"gross_revenue_paise": 100_000_000, "leak_paise": {"rto_cod": 50_000_000}}  # way past P90
    )
    assert components["rto_cod"] == 0.0
    for leak_type in ("preventable_churn", "failed_payments", "discount_abuse"):
        assert components[leak_type] == 100.0
    # 40*100 + 30*0 + 15*100 + 15*100 = 70
    assert value == 70.0


def test_watertight_zero_revenue_no_observed_leak() -> None:
    value, components = watertight.score({"gross_revenue_paise": 0, "leak_paise": {}})
    assert value == 100.0
    assert components["leak_total_paise"] == 0


# --------------------------------------------------------------------- ciq


def test_ciq_reweighting() -> None:
    # equal inputs -> same value regardless of weights
    value, components = ciq.score({"gravity": 60.0, "flow": 60.0, "signal": 60.0, "watertight": 60.0})
    assert value == 60.0
    assert components["coverage"] == "4/9"
    assert sum(components["weights_renormalized"].values()) == pytest.approx(100.0, abs=0.05)
    assert set(components["missing"]) == {"vitals", "velocity", "autopilot", "pulse", "altitude"}

    # known weighted mean: (80*20 + 60*12 + 70*12 + 40*12) / 56 = 65.0
    value, _ = ciq.score({"gravity": 80.0, "flow": 60.0, "signal": 70.0, "watertight": 40.0})
    assert value == 65.0


# --------------------------------------------------------------------- engine

FIXED_INPUTS = {
    "gravity": GRAVITY_MID,
    "flow": FLOW_MID,
    "signal": SIGNAL_MID,
    "watertight": {
        "gross_revenue_paise": 100_000_000,
        "leak_paise": {"preventable_churn": 4_000_000, "rto_cod": 3_000_000},
    },
}


@pytest.fixture()
def session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Tenant(id=1, slug="t-test", name="Test Tenant"))
        s.commit()
        yield s


def test_compute_all_persists_and_hash_is_stable(session, monkeypatch) -> None:
    monkeypatch.setattr(engine_mod, "gather_inputs", lambda s, t: FIXED_INPUTS)

    runs = engine_mod.compute_all(session, tenant_id=1)
    # Phase-2 scores absent from the inputs are skipped; CIQ renormalizes (V2.4)
    assert [r.score for r in runs] == ["gravity", "flow", "signal", "watertight", "ciq"]
    assert all(r.definition_version == "v2.0" for r in runs)
    assert all(0.0 <= r.value <= 100.0 for r in runs)
    assert all(r.tenant_id == 1 for r in runs)

    by_score = {r.score: r for r in runs}
    assert by_score["gravity"].value == gravity.score(FIXED_INPUTS["gravity"])[0]
    assert by_score["watertight"].value == watertight.score(FIXED_INPUTS["watertight"])[0]
    expected_ciq, _ = ciq.score({name: by_score[name].value for name in ("gravity", "flow", "signal", "watertight")})
    assert by_score["ciq"].value == expected_ciq
    assert by_score["ciq"].components["coverage"] == "4/9"
    assert by_score["watertight"].components["leak_total_paise"] == 7_000_000

    # append-only + reproducible: second run adds 5 more rows with identical hashes
    runs2 = engine_mod.compute_all(session, tenant_id=1)
    assert session.query(ScoreRun).count() == 10
    hashes1 = {r.score: r.inputs_hash for r in runs}
    hashes2 = {r.score: r.inputs_hash for r in runs2}
    assert hashes1 == hashes2
    assert all(len(h) == 64 for h in hashes1.values())


def test_inputs_hash_key_order_independent() -> None:
    a = engine_mod.inputs_hash({"x": 1, "y": [1, 2], "z": None})
    b = engine_mod.inputs_hash({"z": None, "y": [1, 2], "x": 1})
    assert a == b
    assert a != engine_mod.inputs_hash({"x": 1, "y": [2, 1], "z": None})
