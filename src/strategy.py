"""Inspection Strategy Simulator: compare hypothetical ways of spending a review / investigation budget.

All costs, budgets and capacities are HYPOTHETICAL user inputs. A strategy here is an ordering rule plus a greedy
fill under the budget and capacity limits; nothing is approved, scheduled or claimed to reduce failure risk.

Uncertainty score (documented, additive; higher = more unresolved uncertainty):
  +3 ambiguous match            +2 measurement uncertainty unknown     +2 depth missing/invalid
  +2 nominal wall thickness missing    +2 each High anomaly flag (max 4)      +1 each Medium anomaly flag (max 2)
  +1 each contradiction (max 3)        +1 single observation (new / not found later)
  +1 upper scenario reaches the demo threshold but no central projection is established
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

STRATEGIES = {
    "priority": "Priority-first: follow the Why-Inspect-First order",
    "uncertainty": "Uncertainty-first: highest uncertainty score first (priority breaks ties)",
    "balanced": "Balanced: alternate between the two lists",
}


@dataclass
class StrategyInputs:
    budget: float = 40000.0
    capacity: int = 40
    cost_engineering_review: float = 1500.0     # for Review first / Monitor findings
    cost_verification: float = 600.0            # for Verify match / data and Additional data needed
    eligible_categories: list = field(default_factory=lambda: ["Review first", "Verify match / data",
                                                               "Additional data needed", "Monitor"])


def uncertainty_scores(F: pd.DataFrame, anomalies: pd.DataFrame, contradictions: pd.DataFrame) -> pd.Series:
    hi = anomalies[anomalies["severity"] == "High"].groupby("track_id").size() if len(anomalies) else pd.Series(dtype=int)
    med = anomalies[anomalies["severity"] == "Medium"].groupby("track_id").size() if len(anomalies) else pd.Series(dtype=int)
    con = contradictions.groupby("track_id").size() if len(contradictions) else pd.Series(dtype=int)
    s = pd.Series(0.0, index=F["track_id"])
    Fi = F.set_index("track_id")
    s += (Fi["match_status"] == "AMBIGUOUS") * 3
    s += (Fi["change_class"] == "UNCERTAINTY_UNKNOWN") * 2
    s += (~np.isfinite(Fi["latest_depth_mm"])) * 2
    s += (~np.isfinite(Fi["wt_mm"])) * 2
    s += np.minimum(hi.reindex(s.index).fillna(0) * 2, 4)
    s += np.minimum(med.reindex(s.index).fillna(0), 2)
    s += np.minimum(con.reindex(s.index).fillna(0), 3)
    s += Fi["match_status"].isin(["NEW_LATER", "UNMATCHED_EARLIER"]) * 1
    s += ((Fi["forecast_status"] == "UPPER_ONLY") & (Fi["yrs_to_threshold_upper"] <= Fi["horizon_years"])) * 1
    return s.astype(float)


def simulate(F: pd.DataFrame, anomalies: pd.DataFrame, contradictions: pd.DataFrame, inp: StrategyInputs) -> dict:
    U = uncertainty_scores(F, anomalies, contradictions)
    pool = F[F["review_category"].isin(inp.eligible_categories)].copy()
    pool["uncertainty_score"] = pool["track_id"].map(U)
    pool["cost"] = np.where(pool["review_category"].isin(["Review first", "Monitor"]), inp.cost_engineering_review,
                            inp.cost_verification)
    by_priority = pool.sort_values("priority_order")["track_id"].tolist()
    by_unc = pool.sort_values(["uncertainty_score", "priority_order"], ascending=[False, True])["track_id"].tolist()
    balanced, seen = [], set()
    for a, b in zip(by_priority, by_unc):
        for t in (a, b):
            if t not in seen:
                seen.add(t)
                balanced.append(t)
    orders = {"priority": by_priority, "uncertainty": by_unc, "balanced": balanced}
    cost = dict(zip(pool["track_id"], pool["cost"]))
    results = {}
    total_unc = float(U.reindex(pool["track_id"]).sum())
    for name, order in orders.items():
        sel, spent = [], 0.0
        for t in order:
            if len(sel) >= inp.capacity:
                break
            if spent + cost[t] <= inp.budget:
                sel.append(t)
                spent += cost[t]
        S = pool.set_index("track_id")
        chosen = set(sel)
        notsel = [t for t in pool["track_id"] if t not in chosen]
        results[name] = dict(
            name=STRATEGIES[name], selected=sel, budget_used=spent, findings_covered=len(sel),
            review_first_covered=int(S.loc[sel, "review_category"].eq("Review first").sum()) if sel else 0,
            review_first_total=int(pool["review_category"].eq("Review first").sum()),
            ambiguous_remaining=int(S.loc[notsel, "match_status"].eq("AMBIGUOUS").sum()) if notsel else 0,
            quality_issues_remaining=int(anomalies[anomalies["track_id"].isin(notsel) & anomalies["severity"].isin(["High", "Medium"])].shape[0]) if len(anomalies) else 0,
            contradictions_remaining=int(contradictions["track_id"].isin(notsel).sum()) if len(contradictions) else 0,
            uncertainty_covered=float(U.reindex(sel).sum()) if sel else 0.0,
            uncertainty_remaining=float(U.reindex(notsel).sum()) if notsel else 0.0,
            uncertainty_total=total_unc,
        )
    return dict(pool=pool, results=results, scores=U)
