"""Churn classifier: leakage-safe features, time-based validation, banding.

Labels: among customers with >= 2 orders as of a cutoff, churned = no order
in the following HORIZON_DAYS. Features are built strictly from rows
timestamped BEFORE the cutoff — sub-timestamps too (a message sent before
the cutoff but opened after it does not count as an open).

Stack (ADR note): gradient-boosted trees via
``sklearn.ensemble.HistGradientBoostingClassifier``. xgboost was NOT
installed — CONTRACTS.md V2.3 records the final stack decision rejecting it
(native-DLL friction on Windows for zero gain at this scale); the
pyproject.toml dependency comment carries the same note. HGB is the same
model family and ships as a pure wheel with scikit-learn.

Banding: fixed p_alive thresholds per CONTRACTS.md V2.3
(high < 0.35 <= medium < 0.65 <= low). The classifier here is a SHADOW
diagnostic only — its time-split AUC is logged so the named upgrade path
(feature-based bands) stays measurable; it never sets bands.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

FEATURES = (
    "recency_weeks",
    "frequency",
    "monetary_paise",
    "tenure_weeks",
    "category_breadth",
    "discount_share",
    "rto_flag",
    "ticket_flag",
    "open_rate",
    "click_rate",
)
HORIZON_DAYS = 182  # ~6 months
AUC_FLOOR = 0.65  # reference line the shadow classifier's logged AUC is judged against
_MIN_LABELED = 30
_WEEK_SECONDS = 7.0 * 86400.0


def build_features(
    cutoff: datetime,
    orders: list,  # (customer_id, placed_at, total_paise, discount_paise, subtotal_paise)
    categories: list,  # (customer_id, placed_at, product_type)
    rtos: list,  # (customer_id, occurred_at)
    tickets: list,  # (customer_id, opened_at)
    messages: list,  # (customer_id, sent_at, opened_at, clicked_at)
) -> dict[int, list[float]]:
    """FEATURES vector per customer with >= 1 order before ``cutoff``.

    Inputs may span the cutoff; every row (and every sub-timestamp) on or
    after it is ignored — that is the no-leakage guarantee the tests assert.
    """
    per: dict[int, list[tuple]] = defaultdict(list)
    for cid, placed, total, disc, sub in orders:
        if placed is not None and placed < cutoff:
            per[cid].append((placed, total or 0, disc or 0, sub or 0))
    cats: dict[int, set] = defaultdict(set)
    for cid, ts, ptype in categories:
        if ts is not None and ts < cutoff:
            cats[cid].add(ptype)
    rto_set = {cid for cid, ts in rtos if ts is not None and ts < cutoff}
    ticket_set = {cid for cid, ts in tickets if ts is not None and ts < cutoff}
    sends: Counter = Counter()
    opens: Counter = Counter()
    clicks: Counter = Counter()
    for cid, sent, opened, clicked in messages:
        if sent is None or sent >= cutoff:
            continue
        sends[cid] += 1
        if opened is not None and opened < cutoff:
            opens[cid] += 1
        if clicked is not None and clicked < cutoff:
            clicks[cid] += 1

    out: dict[int, list[float]] = {}
    for cid, rows in per.items():
        rows.sort()
        first, last = rows[0][0], rows[-1][0]
        n = len(rows)
        sub_sum = sum(r[3] for r in rows)
        s = sends.get(cid, 0)
        out[cid] = [
            (cutoff - last).total_seconds() / _WEEK_SECONDS,  # recency_weeks
            float(n),  # frequency
            sum(r[1] for r in rows) / n,  # monetary_paise (avg order value)
            (cutoff - first).total_seconds() / _WEEK_SECONDS,  # tenure_weeks
            float(len(cats.get(cid, ()))),  # category_breadth
            sum(r[2] for r in rows) / sub_sum if sub_sum else 0.0,  # discount_share
            1.0 if cid in rto_set else 0.0,  # rto_flag
            1.0 if cid in ticket_set else 0.0,  # ticket_flag
            opens[cid] / s if s else 0.0,  # open_rate
            clicks[cid] / s if s else 0.0,  # click_rate
        ]
    return out


def build_labels(
    cutoff: datetime, orders: list, horizon_days: int = HORIZON_DAYS
) -> dict[int, int]:
    """1 = churned (no order in (cutoff, cutoff+horizon]), for customers with
    >= 2 orders strictly before the cutoff. Single-order customers get no
    label — churn is only defined for established repeaters."""
    end = cutoff + timedelta(days=horizon_days)
    pre: Counter = Counter()
    post: set[int] = set()
    for cid, placed, *_ in orders:
        if placed is None:
            continue
        if placed < cutoff:
            pre[cid] += 1
        elif placed <= end:
            post.add(cid)
    return {cid: (0 if cid in post else 1) for cid, n in pre.items() if n >= 2}


def train(
    feats_train: dict[int, list[float]],
    labels_train: dict[int, int],
    feats_valid: dict[int, list[float]],
    labels_valid: dict[int, int],
) -> tuple[HistGradientBoostingClassifier, float]:
    """Fit on the earlier cutoff, report AUC on the later one (time-based
    split — validation labels come from a period the model never saw).
    Raises ValueError when there is not enough labeled history to trust."""
    ids_tr = [c for c in labels_train if c in feats_train]
    ids_va = [c for c in labels_valid if c in feats_valid]
    y_tr = np.array([labels_train[c] for c in ids_tr])
    y_va = np.array([labels_valid[c] for c in ids_va])
    if (
        len(ids_tr) < _MIN_LABELED
        or len(ids_va) < _MIN_LABELED
        or np.unique(y_tr).size < 2
        or np.unique(y_va).size < 2
    ):
        raise ValueError(
            f"insufficient labeled history (train={len(ids_tr)}, valid={len(ids_va)})"
        )
    clf = HistGradientBoostingClassifier(random_state=0)  # deterministic
    clf.fit(np.array([feats_train[c] for c in ids_tr], dtype=float), y_tr)
    auc = float(
        roc_auc_score(y_va, clf.predict_proba(np.array([feats_valid[c] for c in ids_va], dtype=float))[:, 1])
    )
    return clf, auc


def bands(palive_by_cid: dict[int, float]) -> dict[int, str]:
    """high/medium/low churn-risk from p_alive at the pinned CONTRACTS V2.3
    thresholds: high < 0.35 <= medium < 0.65 <= low."""
    return {
        c: ("high" if p < 0.35 else "medium" if p < 0.65 else "low")
        for c, p in palive_by_cid.items()
    }
