"""Corrosion Pattern Explorer: observed patterns and associations in the findings (not causes).

Clustering method (documented): single-linkage, one-dimensional, gap-based grouping along the pipeline.
Findings are ordered by axial position; consecutive findings closer than `gap_m` join the same group; groups
with at least `min_size` findings are reported. Features used: axial position only. Limitations: ignores clock
position and depth; sensitive to `gap_m`; dense reporting can reflect tool sensitivity, not corrosivity.
No soil, pressure, coating or environmental data is used, because none is in the dataset.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

GROWTH_CATEGORY = {"INCREASE_BEYOND_NOISE": "Increase beyond noise", "WITHIN_NOISE": "Within noise",
                   "DECREASE_BEYOND_NOISE": "Decrease beyond noise", "UNCERTAINTY_UNKNOWN": "Uncertainty unknown",
                   "NOT_COMPUTED": "Not computed (no pair)"}


def enrich(F: pd.DataFrame) -> pd.DataFrame:
    E = F.copy()
    E["position_m"] = E["pos_b"].where(E["pos_b"].notna(), E["pos_a"])
    E["clock_h"] = E["clock_b"].where(E["clock_b"].notna(), E["clock_a"])
    E["growth_category"] = E["change_class"].map(GROWTH_CATEGORY)
    E["data_quality"] = np.where((E["flags_a"].fillna("") + E["flags_b"].fillna("")).str.len() > 0, "Flagged", "No flags")
    E["clock_band"] = pd.cut(E["clock_h"], [-0.01, 3, 6, 9, 12.01], labels=["0-3 h", "3-6 h", "6-9 h", "9-12 h"])
    return E


def segment_summary(F: pd.DataFrame) -> pd.DataFrame:
    E = enrich(F)
    E = E.assign(_rf=(E["review_category"] == "Review first").astype(int),
                 _gn=(E["change_class"] == "INCREASE_BEYOND_NOISE").astype(float),
                 _amb=(E["match_status"] == "AMBIGUOUS").astype(int),
                 _new=(E["match_status"] == "NEW_LATER").astype(int),
                 _flag=(E["data_quality"] == "Flagged").astype(int),
                 _rate=E["rate_mm_per_yr"].where(E["match_status"] == "LIKELY_MATCH"))
    out = E.groupby("segment_id", dropna=True).agg(
        findings=("track_id", "size"), review_first=("_rf", "sum"), max_latest_pct_wt=("latest_pct_wt", "max"),
        median_rate_likely=("_rate", "median"), share_growth_beyond_noise=("_gn", "mean"), ambiguous=("_amb", "sum"),
        new_detections=("_new", "sum"), flagged_records=("_flag", "sum"))
    return out.reset_index()


def spatial_clusters(F: pd.DataFrame, gap_m: float = 15.0, min_size: int = 4) -> tuple[pd.DataFrame, pd.Series]:
    E = enrich(F).dropna(subset=["position_m"])
    E = E[np.isfinite(E["position_m"])].sort_values("position_m")
    labels = pd.Series(-1, index=E.index)
    start = 0
    pos = E["position_m"].to_numpy()
    idx = E.index.to_numpy()
    groups = []
    for i in range(1, len(pos) + 1):
        if i == len(pos) or pos[i] - pos[i - 1] > gap_m:
            if i - start >= min_size:
                groups.append(idx[start:i])
            start = i
    rows = []
    for k, members in enumerate(groups, 1):
        labels[members] = k
        d = E.loc[members]
        rows.append(dict(cluster=f"G{k:02d}", start_m=d["position_m"].min(), end_m=d["position_m"].max(),
                         findings=len(d), segments=", ".join(sorted(d["segment_id"].dropna().unique())),
                         review_first=int((d["review_category"] == "Review first").sum()),
                         median_rate=d.loc[d["match_status"] == "LIKELY_MATCH", "rate_mm_per_yr"].median(),
                         max_latest_pct_wt=d["latest_pct_wt"].max(), members=", ".join(d["track_id"].head(12))
                         + (" ..." if len(d) > 12 else "")))
    return pd.DataFrame(rows), labels


def association(F: pd.DataFrame, by: str) -> dict:
    """Kruskal-Wallis test of observed rate (likely matches) across groups of `by`. Association only."""
    E = enrich(F)
    E = E[(E["match_status"] == "LIKELY_MATCH") & E["rate_mm_per_yr"].notna() & E[by].notna()]
    groups = [g["rate_mm_per_yr"].to_numpy() for _, g in E.groupby(by, observed=True) if len(g) >= 3]
    if len(groups) < 2:
        return dict(test="Kruskal-Wallis", groups=len(groups), statistic=np.nan, p_value=np.nan,
                    note="Not enough groups with at least 3 likely matches.")
    h, p = stats.kruskal(*groups)
    return dict(test="Kruskal-Wallis", groups=len(groups), statistic=float(h), p_value=float(p),
                note=("Observed rates differ across groups more than chance alone would usually produce (p < 0.05). "
                      if p < 0.05 else "No clear difference in observed rates across groups at p < 0.05. ")
                     + "This is an association in this dataset, not evidence of a cause.")
