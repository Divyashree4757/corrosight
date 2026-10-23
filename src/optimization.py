"""Optional budget-constrained review planner (0/1 knapsack, exact dynamic programming).

Objective (documented assumption): maximise the sum of MODELLED-BENEFIT POINTS of the selected
review actions subject to   sum(assumed cost) <= budget   and optional must-include constraints.

* Costs and benefit points are illustrative demo assumptions per review category, editable in the UI.
* Benefit points are an ordinal stand-in for "how much the review category says this action matters".
  They are NOT risk reduction, NOT avoided failures and NOT money saved.
* The solver is exact for integer costs (costs are rounded to `cost_unit`). It is verified against
  brute-force enumeration in tests/test_optimization.py.
* Selecting an action here only builds a candidate plan for humans; nothing is approved or scheduled.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd

DEFAULT_ACTION_ASSUMPTIONS = {
    # review_category: (action, assumed cost, modelled-benefit points)
    "Review first": ("Engineering review", 1500.0, 30.0),
    "Verify match / data": ("Match / sizing verification", 600.0, 9.0),
    "Additional data needed": ("Data request and follow-up", 300.0, 4.0),
    "Monitor": ("Scheduled data review", 150.0, 1.0),
}


@dataclass
class PlanResult:
    table: pd.DataFrame
    total_cost: float
    total_benefit: float
    budget: float
    feasible: bool
    message: str


def knapsack(costs: list[int], values: list[float], capacity: int, must: list[int] | None = None) -> tuple[list[int], float]:
    """Exact 0/1 knapsack. Returns (selected indices, total value). Raises ValueError if infeasible."""
    must = sorted(set(must or []))
    base_cost = sum(costs[i] for i in must)
    if base_cost > capacity:
        raise ValueError("Mandatory items exceed the budget.")
    free = [i for i in range(len(costs)) if i not in must]
    cap = capacity - base_cost
    n = len(free)
    dp = np.zeros((n + 1, cap + 1))
    for k, i in enumerate(free, start=1):
        c, v = costs[i], values[i]
        dp[k] = dp[k - 1]
        if c <= cap:
            dp[k, c:] = np.maximum(dp[k - 1, c:], dp[k - 1, :cap + 1 - c] + v)
    sel, w = [], cap
    for k in range(n, 0, -1):
        if dp[k, w] != dp[k - 1, w]:
            i = free[k - 1]
            sel.append(i)
            w -= costs[i]
    chosen = sorted(must + sel)
    return chosen, float(sum(values[i] for i in chosen))


def brute_force(costs, values, capacity, must=None):
    """Reference solver for tests (small n only)."""
    must = set(must or [])
    best, best_set = -1.0, None
    n = len(costs)
    for r in range(n + 1):
        for comb in combinations(range(n), r):
            if not must.issubset(comb):
                continue
            if sum(costs[i] for i in comb) <= capacity:
                v = sum(values[i] for i in comb)
                if v > best:
                    best, best_set = v, list(comb)
    if best_set is None:
        raise ValueError("Mandatory items exceed the budget.")
    return best_set, float(best)


def plan(findings: pd.DataFrame, budget: float, assumptions: dict | None = None,
         must_include_review_first: bool = False, cost_unit: float = 10.0) -> PlanResult:
    a = assumptions or DEFAULT_ACTION_ASSUMPTIONS
    cand = findings[findings["review_category"].isin(a.keys())].copy()
    if cand.empty:
        return PlanResult(pd.DataFrame(), 0.0, 0.0, budget, True, "No candidate actions.")
    cand["action"] = cand["review_category"].map(lambda c: a[c][0])
    cand["assumed_cost"] = cand["review_category"].map(lambda c: float(a[c][1]))
    cand["benefit_points"] = cand["review_category"].map(lambda c: float(a[c][2]))
    cand = cand.reset_index(drop=True)
    costs = [int(round(c / cost_unit)) for c in cand["assumed_cost"]]
    cap = int(np.floor(budget / cost_unit))
    must = list(cand.index[cand["review_category"] == "Review first"]) if must_include_review_first else []
    try:
        sel, total_v = knapsack(costs, cand["benefit_points"].tolist(), cap, must)
        feasible, msg = True, "Optimal plan found (exact dynamic programming)."
    except ValueError:
        sel, total_v = [], 0.0
        need = sum(cand.loc[must, "assumed_cost"])
        feasible = False
        msg = (f"Infeasible: the mandatory 'Review first' actions alone need {need:,.0f} (assumed) but the budget is "
               f"{budget:,.0f}. Increase the budget or remove the constraint; unresolved reviews remain unresolved.")
    cand["selected"] = cand.index.isin(sel)
    spent = float(cand.loc[cand["selected"], "assumed_cost"].sum())
    remaining = budget - spent
    why = []
    for r in cand.itertuples():
        if r.selected:
            why.append("Mandatory (Review first)" if r.Index in must else "Selected in the optimal set")
        elif not feasible:
            why.append("Not planned: constraints infeasible")
        elif r.assumed_cost > remaining:
            why.append(f"Excluded: cost {r.assumed_cost:,.0f} exceeds remaining budget {remaining:,.0f}")
        else:
            why.append("Excluded: a different combination gives more benefit points within the budget")
    cand["decision_reason"] = why
    cand["unresolved_checks"] = cand.get("requires_verification", pd.Series([""] * len(cand)))
    cols = ["track_id", "review_category", "action", "assumed_cost", "benefit_points", "selected", "decision_reason",
            "proposed_next_step", "unresolved_checks"]
    out = cand[[c for c in cols if c in cand.columns]].sort_values(["selected", "benefit_points"], ascending=[False, False])
    return PlanResult(out.reset_index(drop=True), spent, total_v, budget, feasible, msg)
