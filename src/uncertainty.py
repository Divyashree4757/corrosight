"""Documented uncertainty calculations (Honest AI).

Assumptions (stated wherever results are shown)
-----------------------------------------------
* `depth_uncertainty_mm` is the 1-sigma standard uncertainty of a single depth measurement.
* Errors of the two runs are independent, unbiased and approximately Gaussian.
* Under these assumptions the observed change D = d_later - d_earlier has standard uncertainty
  sigma_D = sqrt(u_earlier^2 + u_later^2), and the annualised rate R = D / dt has sigma_R = sigma_D / dt.
* The k-sigma interval (default k = 2, roughly 95 % under the assumptions) covers ONLY measurement noise.
  It does not include matching errors, systematic sizing bias between tools, or the fact that real growth
  need not be constant. It is therefore a lower bound on the true uncertainty.
* When either uncertainty is unknown, NO interval is produced (we never invent one).

Model B: empirical-Bayes shrinkage (optional)
---------------------------------------------
Per-defect rates from two noisy measurements are very noisy. A standard normal-normal empirical-Bayes
model treats each true rate as drawn from a population N(mu, tau^2) and each observed rate as
R_i ~ N(rate_i, sigma_i^2). Method-of-moments estimates:
    mu    = mean(R_i)
    tau^2 = max(var(R_i) - mean(sigma_i^2), floor)
Posterior for defect i: mean = mu + B_i (R_i - mu), sd = sqrt(B_i) * sigma_i, with B_i = tau^2 / (tau^2 + sigma_i^2).
It is fitted only on likely (unambiguous) matches with known uncertainty. Whether it improves on the
baseline is checked against the synthetic ground truth in src/evaluation.py - it is not assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CHANGE_CLASSES = {
    "INCREASE_BEYOND_NOISE": "Increase exceeds measurement noise",
    "WITHIN_NOISE": "Change within measurement noise",
    "DECREASE_BEYOND_NOISE": "Decrease exceeds measurement noise (anomalous)",
    "UNCERTAINTY_UNKNOWN": "Measurement uncertainty unknown",
    "NOT_COMPUTED": "Not computed",
}


def combined_sigma(u_a, u_b):
    u_a, u_b = np.asarray(u_a, dtype=float), np.asarray(u_b, dtype=float)
    out = np.sqrt(u_a ** 2 + u_b ** 2)
    return np.where((u_a > 0) & (u_b > 0), out, np.nan)


def classify_change(delta, sigma, k: float = 2.0):
    delta, sigma = np.asarray(delta, dtype=float), np.asarray(sigma, dtype=float)
    out = np.full(delta.shape, "NOT_COMPUTED", dtype=object)
    have = np.isfinite(delta)
    unk = have & ~np.isfinite(sigma)
    out[unk] = "UNCERTAINTY_UNKNOWN"
    ok = have & np.isfinite(sigma)
    out[ok & (delta > k * sigma)] = "INCREASE_BEYOND_NOISE"
    out[ok & (delta < -k * sigma)] = "DECREASE_BEYOND_NOISE"
    out[ok & (np.abs(delta) <= k * sigma)] = "WITHIN_NOISE"
    return out


@dataclass
class ShrinkageFit:
    mu: float
    tau2: float
    n: int
    fitted: bool

    def posterior(self, rate, sigma):
        rate, sigma = np.asarray(rate, dtype=float), np.asarray(sigma, dtype=float)
        if not self.fitted:
            return np.full(rate.shape, np.nan), np.full(rate.shape, np.nan)
        b = self.tau2 / (self.tau2 + sigma ** 2)
        mean = self.mu + b * (rate - self.mu)
        sd = np.sqrt(b) * sigma
        bad = ~(np.isfinite(rate) & np.isfinite(sigma))
        mean[bad] = np.nan
        sd[bad] = np.nan
        return mean, sd


def fit_shrinkage(rates, sigmas, min_n: int = 10, tau2_floor: float = 1e-4) -> ShrinkageFit:
    rates, sigmas = np.asarray(rates, dtype=float), np.asarray(sigmas, dtype=float)
    ok = np.isfinite(rates) & np.isfinite(sigmas)
    r, s = rates[ok], sigmas[ok]
    if len(r) < min_n:
        return ShrinkageFit(np.nan, np.nan, int(len(r)), False)
    mu = float(np.mean(r))
    tau2 = float(max(np.var(r, ddof=1) - np.mean(s ** 2), tau2_floor))
    return ShrinkageFit(mu, tau2, int(len(r)), True)
