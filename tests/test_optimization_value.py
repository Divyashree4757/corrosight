import numpy as np
import pytest

from src.optimization import brute_force, knapsack, plan
from src.value_calculator import ValueInputs, calculate


@pytest.mark.parametrize("seed", range(150))
def test_knapsack_matches_brute_force(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 10))
    costs = rng.integers(1, 20, n).tolist()
    values = rng.integers(0, 15, n).astype(float).tolist()
    cap = int(rng.integers(0, 60))
    must = [i for i in range(n) if rng.random() < 0.15]
    try:
        ref_sel, ref_v = brute_force(costs, values, cap, must)
    except ValueError:
        with pytest.raises(ValueError):
            knapsack(costs, values, cap, must)
        return
    sel, v = knapsack(costs, values, cap, must)
    assert v == pytest.approx(ref_v)
    assert sum(costs[i] for i in sel) <= cap
    assert set(must) <= set(sel)


def test_known_small_case():
    # capacity 10: best is items 1+2 (cost 4+6, value 10+9) = 19, not item 0 (cost 9, value 15)
    sel, v = knapsack([9, 4, 6], [15, 10, 9], 10)
    assert sel == [1, 2] and v == 19


def test_plan_respects_budget_and_explains(demo_result):
    p = plan(demo_result.findings, budget=20000)
    assert p.feasible and p.total_cost <= 20000
    assert p.table["decision_reason"].str.len().min() > 0
    assert p.table.loc[p.table["selected"], "assumed_cost"].sum() == p.total_cost


def test_plan_mandatory_infeasible_is_reported(demo_result):
    p = plan(demo_result.findings, budget=1000, must_include_review_first=True)
    assert not p.feasible and "Infeasible" in p.message and p.table["selected"].sum() == 0


def test_value_calculator_hand_example():
    r = calculate(ValueInputs(annual_items=400, hours_per_item=2, hourly_cost=50, reduction_fraction=0.25, annual_fee=5000))
    assert r.baseline_hours == 800 and r.hours_saved == 200
    assert r.estimated_savings == 10000 and r.net_value == 5000
    assert r.breakeven_reduction_fraction == pytest.approx(5000 / 40000)


def test_value_calculator_rejects_bad_inputs():
    with pytest.raises(ValueError):
        calculate(ValueInputs(1, 1, 1, 1.5, 0))
    with pytest.raises(ValueError):
        calculate(ValueInputs(-1, 1, 1, 0.5, 0))
