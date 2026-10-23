import pandas as pd

from conftest import make_records
from src.schema import AnalysisConfig
from src.synthetic_data import generate
from src.validation import validate


def codes(v):
    return set(v.issues["code"])


def test_missing_required_column_blocks_analysis():
    df = make_records([dict(axial_position_m=10, depth_mm=1.0)]).drop(columns=["depth_mm"])
    v = validate(df)
    assert v.blocking
    assert "SCHEMA_MISSING_COLUMN" in codes(v)
    assert v.issues.loc[0, "field"] == "depth_mm"


def test_source_data_never_modified():
    df = make_records([dict(axial_position_m=10, depth_mm=-1.0), dict(axial_position_m=20, depth_mm="abc")])
    before = df.copy()
    v = validate(df)
    pd.testing.assert_frame_equal(df, before)
    assert len(v.data) == len(df)  # nothing deleted


def test_missing_and_invalid_measurements_are_flagged_not_dropped():
    df = make_records([
        dict(axial_position_m=10, depth_mm=None),          # missing depth
        dict(axial_position_m=20, depth_mm=-0.5),          # negative
        dict(axial_position_m=30, depth_mm=12.0),          # > WT (10)
        dict(axial_position_m=40, depth_mm=2500),          # unit suspect
        dict(axial_position_m=50, depth_mm=2.0, nominal_wt_mm=0),   # zero WT
        dict(axial_position_m=60, depth_mm="2,5"),         # non-numeric
        dict(axial_position_m=70, depth_mm=2.0, clock_position_h=14.5),
        dict(axial_position_m=None, depth_mm=2.0),
    ])
    v = validate(df)
    c = codes(v)
    for code in ["MISSING_DEPTH", "NON_POSITIVE_DEPTH", "DEPTH_EXCEEDS_WT", "DEPTH_UNIT_SUSPECT",
                 "INVALID_WALL_THICKNESS", "NON_NUMERIC", "INVALID_CLOCK", "MISSING_POSITION"]:
        assert code in c, code
    d = v.data
    assert len(d) == 8
    assert d["depth_valid"].tolist() == [False, False, False, False, True, False, True, True]
    assert d.loc[4, "wt_valid"] == False  # noqa: E712
    assert d.loc[7, "match_eligible"] == False  # noqa: E712
    # every issue explains effect and action
    assert v.issues["effect"].str.len().min() > 0 and v.issues["action"].str.len().min() > 0


def test_missing_wall_thickness_and_uncertainty_reported():
    df = make_records([dict(axial_position_m=10, depth_mm=1.0, nominal_wt_mm=None, depth_uncertainty_mm=None)])
    v = validate(df)
    assert {"MISSING_WALL_THICKNESS", "MISSING_UNCERTAINTY"} <= codes(v)
    assert "NOT lowered" in v.issues.set_index("code").loc["MISSING_WALL_THICKNESS", "effect"]


def test_exact_and_near_duplicates_flagged_and_excluded_from_matching_only():
    rows = [dict(axial_position_m=10.0, depth_mm=1.0), dict(axial_position_m=10.01, depth_mm=1.1),
            dict(axial_position_m=50.0, depth_mm=1.0)]
    df = make_records(rows)
    df = pd.concat([df, df.iloc[[2]]], ignore_index=True)  # exact duplicate of row 3
    v = validate(df, AnalysisConfig())
    assert {"EXACT_DUPLICATE", "POSSIBLE_DUPLICATE"} <= codes(v)
    d = v.data
    assert len(d) == 4
    assert d["match_eligible"].tolist() == [True, False, True, False]
    assert d.loc[1, "duplicate_of"] == "R1-001"


def test_distinct_clustered_defects_not_called_duplicates():
    rows = [dict(axial_position_m=10.0, depth_mm=1.0, length_mm=20),
            dict(axial_position_m=10.03, depth_mm=1.1, length_mm=60)]  # very different length
    v = validate(make_records(rows))
    assert "POSSIBLE_DUPLICATE" not in codes(v)


def test_invalid_date_and_position_range():
    df = make_records([dict(axial_position_m=9999, depth_mm=1.0), dict(axial_position_m=5, depth_mm=1.0)])
    df.loc[1, "inspection_date"] = "not a date"
    v = validate(df, pipeline_length_m=4800)
    assert {"INVALID_POSITION", "INVALID_DATE"} <= codes(v)


def test_synthetic_data_is_reproducible_and_ground_truth_separate():
    a, ga = generate()
    b, gb = generate()
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(ga, gb)
    assert not any(c.startswith("true_") or c.startswith("_") for c in a.columns)
    assert a["segment_id"].nunique() == 40
    assert set(a["run_id"]) == {"R2016", "R2023"}
    assert {"DUPLICATE", "CORRUPTED", "SPURIOUS", "TRUE"} <= set(ga["record_kind"])
