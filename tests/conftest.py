import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import SourceInfo, attach_evaluation, run_analysis  # noqa: E402
from src.synthetic_data import generate  # noqa: E402


def make_records(rows, run_id="R1", date="2016-01-01", **defaults):
    """Build a raw (all-text) inspection frame from compact dicts."""
    base = dict(pipeline_id="P1", run_id=run_id, inspection_date=date, segment_id="S01", joint_id="J0001",
                clock_position_h=6.0, length_mm=30.0, width_mm=20.0, nominal_wt_mm=10.0,
                depth_uncertainty_mm=0.3, outer_diameter_mm=610.0, smys_mpa=359.0, maop_kpa=6900.0)
    base.update(defaults)
    out = []
    for i, r in enumerate(rows):
        rec = dict(base)
        rec["observation_id"] = f"{run_id}-{i + 1:03d}"
        rec.update(r)
        out.append(rec)
    return pd.DataFrame(out).astype(str).replace({"nan": None})


def two_runs(rows_a, rows_b, date_a="2016-01-01", date_b="2023-01-01"):
    a = make_records(rows_a, "RA", date_a)
    b = make_records(rows_b, "RB", date_b)
    return pd.concat([a, b], ignore_index=True)


@pytest.fixture(scope="session", autouse=True)
def isolated_outputs(tmp_path_factory):
    """Keep test runs from writing into the real outputs/ folder or review log."""
    import os
    d = tmp_path_factory.mktemp("outputs")
    os.environ["CORROSIGHT_OUTPUT_DIR"] = str(d)
    os.environ["CORROSIGHT_REVIEW_LOG"] = str(d / "review_log.json")
    os.environ["CORROSIGHT_USER_DB"] = str(d / "users.json")
    os.environ["CORROSIGHT_PBKDF2_ITERATIONS"] = "1000"      # fast hashing in tests only
    os.environ["CORROSIGHT_PERMISSIONS"] = str(d / "no_permissions_override.json")
    yield d


@pytest.fixture(scope="session")
def demo_frames():
    insp, gt = generate()
    return insp.astype(str).replace({"nan": None}), gt


@pytest.fixture(scope="session")
def demo_result(demo_frames):
    insp, gt = demo_frames
    res = run_analysis(insp, SourceInfo("Demo dataset (synthetic)", ["synthetic_inspections.csv"], True, 4800.0))
    return attach_evaluation(res, gt)


PW = "Corrosion2026x"
ACCOUNTS = (("eng", "engineer", False), ("ana", "analyst", False), ("pla", "planner", False), ("man", "manager", False),
            ("adm", "manager", True), ("locked", "analyst", False), ("gone", "planner", False))


@pytest.fixture(scope="session", autouse=True)
def accounts(isolated_outputs):
    from src.auth import UserStore
    store = UserStore()
    for name, role, admin in ACCOUNTS:
        if store.find(name) is None:
            store.create_user(name, f"Test {role}" + (" admin" if admin else ""), role, PW, is_admin=admin)
    return store


