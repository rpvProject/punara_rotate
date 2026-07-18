"""BG/NBD + Gamma-Gamma, implemented in-repo (scipy.optimize MLE).

References:
- Fader, Hardie, Lee (2005), "'Counting Your Customers' the Easy Way:
  An Alternative to the Pareto/NBD Model", Marketing Science 24(2) —
  likelihood (eq. 6-7 log form), P(alive) and conditional expected
  transactions (eq. 10, via the Gaussian hypergeometric 2F1).
- Fader, Hardie (2013), "The Gamma-Gamma Model of Monetary Value" —
  likelihood and conditional expected monetary value E[M | m̄, x] (eq. 5).

The `lifetimes` package is deliberately NOT used: it is unmaintained and
pins pre-2.0 pandas / old numpy (broken on py3.12). This module is the
whole replacement — ~150 lines, scipy-only.

Units: frequency ``x`` = number of REPEAT transactions (orders - 1),
recency ``t_x`` = weeks from first to last order, age ``T`` = weeks from
first order to the analysis anchor. All in WEEKS.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln, hyp2f1

_LOG_LO, _LOG_HI = -10.0, 25.0  # log-param box: keeps exp() finite, params > 0


@dataclass(frozen=True)
class BgNbdParams:
    r: float
    alpha: float  # weeks
    a: float
    b: float


@dataclass(frozen=True)
class GammaGammaParams:
    p: float
    q: float
    v: float  # same unit as the monetary input (paise)


def _arr(*xs: object) -> tuple[np.ndarray, ...]:
    return tuple(np.asarray(x, dtype=float) for x in xs)


# ------------------------------------------------------------------ BG/NBD


_PENALTY = 1e-4  # L2 on the raw params: negligible vs the LL at any real n,
# but blocks the classic BG/NBD (a, b)->infinity ridge when dropout
# heterogeneity is weak (same device as lifetimes' penalizer_coef).


def _bgnbd_nll(log_params: np.ndarray, x: np.ndarray, t_x: np.ndarray, T: np.ndarray) -> float:
    """Penalized negative log-likelihood, FHL05 eq. 6-7 in log space."""
    r, alpha, a, b = np.exp(np.clip(log_params, _LOG_LO, _LOG_HI))
    ln_a1 = gammaln(r + x) - gammaln(r) + r * np.log(alpha)
    ln_a2 = gammaln(a + b) + gammaln(b + x) - gammaln(b) - gammaln(a + b + x)
    ln_a3 = -(r + x) * np.log(alpha + T)
    repeat = x > 0
    ln_a4 = np.full_like(ln_a3, -np.inf)
    ln_a4[repeat] = (
        np.log(a) - np.log(b + x[repeat] - 1.0) - (r + x[repeat]) * np.log(alpha + t_x[repeat])
    )
    penalty = _PENALTY * float(r * r + alpha * alpha + a * a + b * b)
    return -float(np.sum(ln_a1 + ln_a2 + np.logaddexp(ln_a3, ln_a4))) + penalty


def fit_bgnbd(x: object, t_x: object, T: object) -> BgNbdParams:
    """Penalized MLE fit of (r, alpha, a, b) over log-params (Nelder-Mead:
    4 params, derivative-free, deterministic from a fixed start)."""
    x, t_x, T = _arr(x, t_x, T)
    res = minimize(
        _bgnbd_nll,
        np.zeros(4),  # start at r=alpha=a=b=1
        args=(x, t_x, T),
        method="Nelder-Mead",
        options={"maxiter": 5000, "xatol": 1e-5, "fatol": 1e-7},
    )
    r, alpha, a, b = np.exp(np.clip(res.x, _LOG_LO, _LOG_HI))
    return BgNbdParams(float(r), float(alpha), float(a), float(b))


def p_alive(params: BgNbdParams, x: object, t_x: object, T: object) -> np.ndarray:
    """P(customer still alive | x, t_x, T), FHL05. For x == 0 the model has
    had no dropout opportunity, so P(alive) = 1 by construction."""
    x, t_x, T = _arr(x, t_x, T)
    r, alpha, a, b = params.r, params.alpha, params.a, params.b
    out = np.ones_like(T)
    repeat = x > 0
    log_ratio = (
        np.log(a)
        - np.log(b + x[repeat] - 1.0)
        + (r + x[repeat]) * (np.log(alpha + T[repeat]) - np.log(alpha + t_x[repeat]))
    )
    out[repeat] = 1.0 / (1.0 + np.exp(np.minimum(log_ratio, 700.0)))
    return out


def expected_orders(
    params: BgNbdParams, x: object, t_x: object, T: object, horizon_weeks: float
) -> np.ndarray:
    """Conditional E[# transactions in (T, T + t]] — FHL05 eq. 10.

    The denominator of eq. 10 is exactly 1 / P(alive), so this reuses
    p_alive() (one overflow guard instead of two).
    """
    x, t_x, T = _arr(x, t_x, T)
    r, alpha, a, b = params.r, params.alpha, params.a, params.b
    t = float(horizon_weeks)
    z = t / (alpha + T + t)
    hyp = hyp2f1(r + x, b + x, a + b + x - 1.0, z)
    growth = 1.0 - ((alpha + T) / (alpha + T + t)) ** (r + x) * hyp
    top = (a + b + x - 1.0) / (a - 1.0) * growth
    return np.maximum(0.0, top * p_alive(params, x, t_x, T))


# ------------------------------------------------------------- Gamma-Gamma


def _gg_nll(log_params: np.ndarray, x: np.ndarray, m: np.ndarray) -> float:
    """Penalized negative log-likelihood of mean order value m̄ given x
    orders (FH13). ``m`` arrives mean-scaled (O(1)) so the L2 penalty is
    unit-free; it blocks the q->infinity ridge when value heterogeneity is
    weak (the GG twin of the BG/NBD (a, b) ridge)."""
    p, q, v = np.exp(np.clip(log_params, _LOG_LO, _LOG_HI))
    px = p * x
    ll = (
        gammaln(px + q)
        - gammaln(px)
        - gammaln(q)
        + q * np.log(v)
        + (px - 1.0) * np.log(m)
        + px * np.log(x)
        - (px + q) * np.log(v + m * x)
    )
    return -float(np.sum(ll)) + _PENALTY * float(p * p + q * q + v * v)


def fit_gamma_gamma(x: object, m: object) -> GammaGammaParams:
    """Penalized MLE fit of (p, q, v) on REPEAT purchasers only (x >= 2
    orders, m > 0). Fit runs in mean-scaled units for conditioning; the MLE
    is scale-equivariant, so v is mapped back to the input unit (paise).

    The model assumes monetary value is independent of frequency; the engine
    checks corr(x, m̄) before trusting the fit (documented there).
    """
    x, m = _arr(x, m)
    scale = max(float(np.mean(m)), 1e-9)
    res = minimize(
        _gg_nll,
        np.log([1.0, 2.0, 1.0]),
        args=(x, m / scale),
        method="Nelder-Mead",
        options={"maxiter": 5000, "xatol": 1e-5, "fatol": 1e-7},
    )
    p, q, v = np.exp(np.clip(res.x, _LOG_LO, _LOG_HI))
    return GammaGammaParams(float(p), float(q), float(v * scale))


def expected_order_value(params: GammaGammaParams, x: object, m: object) -> np.ndarray:
    """E[M | m̄, x] = p(v + x·m̄) / (px + q - 1) — FH13 eq. 5 (shrinks the
    observed mean toward the population prior p·v/(q-1) as x falls)."""
    x, m = _arr(x, m)
    return params.p * (params.v + x * m) / (params.p * x + params.q - 1.0)
