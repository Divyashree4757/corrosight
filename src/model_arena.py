"""Model Challenge Arena: compare growth-rate estimators on held-out synthetic defects.

Evaluation design
-----------------
* Ground truth: data/synthetic_ground_truth.csv (true defect identity and true constant growth rate). It is used
  ONLY here, after the analysis, to score estimates. It is never an input to matching or estimation.
* Records evaluated: LIKELY matches whose two records are truly the same defect, with valid depths and known
  measurement uncertainty.
* Split: group-wise by true defect id (all records of one simulated defect go to the same side), 50 % train /
  50 % test, seeded. Hyperparameters (population mean, between-defect variance, segment means) are fitted on
  the training defects only; each test defect is then estimated from its own two measurements plus those
  hyperparameters, so no test information leaks into the fit. Repeated over several seeds for stability.

Estimators
----------
B0  Pooled mean           every defect gets the training-population mean rate (reference / naive)
B1  Baseline observed     (later - earlier depth) / years, per defect (the app's baseline)
B2  Global shrinkage      empirical-Bayes normal-normal shrinkage toward the training mean (the app's model B)
B3  Segment shrinkage     like B2 but shrinks toward the training mean of the defect's segment when that segment
                          has >= `min_seg` training defects, otherwise toward the global mean

Synthetic results do not establish real-world accuracy: the generator's noise model matches the stated
uncertainty by construction, which flatters interval coverage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .uncertainty import fit_shrinkage

METHODS = {
    "B0": "Pooled mean (reference)",
    "B1": "Baseline observed rate",
    "B2": "Global shrinkage (model B)",
    "B3": "Segment shrinkage",
}
STRENGTHS = {
    "B0": ("Very stable; useful yardstick.", "Ignores each defect's own measurements, so it misses fast and inactive defects."),
    "B1": ("Unbiased if the match is right; easy to explain; uses only this defect's data.",
           "Very noisy with two measurements: noise divided by elapsed years; produces negative rates."),
    "B2": ("Reduces noise by borrowing strength from the population; usually lower error than B1.",
           "Pulls genuinely fast or inactive defects toward the average; assumes one population."),
    "B3": ("Allows local differences between segments.",
           "Needs enough defects per segment; with few, it falls back to B2 and can add variance."),
}


def evaluation_frame(growth: pd.DataFrame, gt: pd.DataFrame, run_a: str, run_b: str) -> pd.DataFrame:
    key = {(r.run_id, r.observation_id): r for r in gt.itertuples()}
    rows = []
    for r in growth[growth["match_status"] == "LIKELY_MATCH"].itertuples():
        ga, gb = key.get((run_a, r.obs_a)), key.get((run_b, r.obs_b))
        if ga is None or gb is None or ga.true_defect_id != gb.true_defect_id or ga.true_defect_id == "NONE":
            continue
        if not (np.isfinite(r.rate_mm_per_yr) and np.isfinite(r.sigma_rate_mm_per_yr)):
            continue
        rows.append(dict(track_id=r.track_id, defect=ga.true_defect_id, segment=r.segment_id, obs=r.rate_mm_per_yr,
                         sigma=r.sigma_rate_mm_per_yr, true=float(ga.true_rate_mm_per_yr)))
    return pd.DataFrame(rows)


def _estimate(train: pd.DataFrame, test: pd.DataFrame, k: float, min_seg: int) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    fit = fit_shrinkage(train["obs"], train["sigma"], min_n=5)
    mu, tau2 = (fit.mu, fit.tau2) if fit.fitted else (float(train["obs"].mean()), 1e-4)
    s = test["sigma"].to_numpy()
    o = test["obs"].to_numpy()
    est = {}
    est["B0"] = (np.full(len(test), mu), np.full(len(test), np.sqrt(tau2)))
    est["B1"] = (o, s)
    b = tau2 / (tau2 + s ** 2)
    est["B2"] = (mu + b * (o - mu), np.sqrt(b) * s)
    seg_mu = train.groupby("segment")["obs"].agg(["mean", "size"])
    m = np.array([seg_mu.at[sg, "mean"] if sg in seg_mu.index and seg_mu.at[sg, "size"] >= min_seg else mu
                  for sg in test["segment"]])
    est["B3"] = (m + b * (o - m), np.sqrt(b) * s)
    return est


def run_arena(growth: pd.DataFrame, gt: pd.DataFrame, run_a: str, run_b: str, k: float = 2.0,
              seeds: int = 25, min_seg: int = 3, test_frac: float = 0.5) -> dict:
    E = evaluation_frame(growth, gt, run_a, run_b)
    if len(E) < 20:
        return dict(ok=False, reason=f"Only {len(E)} evaluable records; at least 20 are needed.")
    defects = np.array(sorted(E["defect"].unique()))
    per_seed = []
    first_split = None
    for seed in range(seeds):
        rng = np.random.default_rng(1000 + seed)
        test_ids = set(rng.choice(defects, size=int(round(len(defects) * test_frac)), replace=False))
        tr, te = E[~E["defect"].isin(test_ids)], E[E["defect"].isin(test_ids)]
        assert not (set(tr["defect"]) & set(te["defect"]))  # group-wise split: no defect on both sides
        est = _estimate(tr, te, k, min_seg)
        for mth, (pred, sd) in est.items():
            err = pred - te["true"].to_numpy()
            per_seed.append(dict(seed=seed, method=mth, n_test=len(te), n_train=len(tr), mae=float(np.mean(np.abs(err))),
                                 rmse=float(np.sqrt(np.mean(err ** 2))), bias=float(np.mean(err)),
                                 coverage=float(np.mean(np.abs(err) <= k * sd))))
        if seed == 0:
            first_split = (tr, te, est)
    S = pd.DataFrame(per_seed)
    summary = S.groupby("method").agg(mae=("mae", "mean"), mae_sd=("mae", "std"), rmse=("rmse", "mean"),
                                      rmse_sd=("rmse", "std"), bias=("bias", "mean"), coverage=("coverage", "mean"),
                                      n_test=("n_test", "mean")).reset_index()
    summary["method_name"] = summary["method"].map(METHODS)
    wins = S.loc[S.groupby("seed")["rmse"].idxmin(), "method"].value_counts().to_dict()
    summary["lowest_rmse_in_splits"] = summary["method"].map(lambda m: int(wins.get(m, 0)))
    # error by true-rate group on the first split (where does each method do well?)
    tr, te, est = first_split
    groups = pd.cut(te["true"], [-0.001, 0.0001, 0.15, 10], labels=["inactive (true rate 0)", "slow (<0.15 mm/yr)",
                                                                       "fast (>=0.15 mm/yr)"])
    rows = []
    for mth, (pred, _) in est.items():
        err = np.abs(pred - te["true"].to_numpy())
        for gname in groups.cat.categories:
            msk = (groups == gname).to_numpy()
            if msk.any():
                rows.append(dict(method=mth, group=gname, n=int(msk.sum()), mae=float(err[msk].mean())))
    by_group = pd.DataFrame(rows).pivot(index="group", columns="method", values="mae").reset_index()
    return dict(ok=True, n_records=len(E), n_defects=len(defects), seeds=seeds, test_frac=test_frac, k=k,
                summary=summary, per_seed=S, by_group=by_group, min_seg=min_seg)
