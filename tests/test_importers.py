"""Importer for the real Mendeley ILI dataset, tested on small files with the documented column names."""

import numpy as np
import pandas as pd
import pytest

from src.importers import _year_from_name, load_mendeley_ili, standardise_frame
from src.pipeline import SourceInfo, run_analysis


def fake_run(year, shift=0.0, grow=0.0):
    # column names exactly as listed in the dataset README (Table 3)
    return pd.DataFrame({"Year": year, "GWNUM": [10, 20, 30], "JL.m": 12.0, "RD.m": [1.0, 2.0, 3.0],
                         "SPD.m": [121.0 + shift, 242.0 + shift, 363.0 + shift], "SPO.deg": [180.0, 90.0, 270.0],
                         "WT.mm": 7.1, "L.mm": [30, 40, 50], "W.mm": [20, 25, 30],
                         "MD.mm": [1.0 + grow, 1.5 + grow, 2.0 + grow]})


def test_year_parsed_from_file_names(tmp_path):
    assert _year_from_name(tmp_path / "External Anomalies Year Three.xlsx") == 3
    assert _year_from_name(tmp_path / "year_7.xlsx") == 7
    assert _year_from_name(tmp_path / "anything.xlsx") is None


def test_mapping_and_units():
    out = standardise_frame(fake_run(5), None, "x.xlsx")
    assert out["run_id"].iloc[0] == "Y5" and out["inspection_date"].iloc[0] == "2004-01-01"
    assert out["clock_position_h"].tolist() == [6.0, 3.0, 9.0]
    assert out["joint_id"].tolist() == ["GW10", "GW20", "GW30"]
    assert out["axial_position_m"].tolist() == [121.0, 242.0, 363.0]
    assert out["depth_uncertainty_mm"].isna().all()   # never invented by default
    with_sigma = standardise_frame(fake_run(5), None, "x.xlsx", assumed_sigma_frac_wt=0.078)
    assert np.allclose(with_sigma["depth_uncertainty_mm"], 0.078 * 7.1)


def test_missing_required_source_column_is_reported():
    with pytest.raises(ValueError, match="required source columns"):
        standardise_frame(fake_run(1).drop(columns=["MD.mm"]), 1, "bad.xlsx")


def test_folder_import_runs_through_full_analysis(tmp_path):
    for y, name in ((1, "Year One"), (3, "Year Three")):
        fake_run(y, shift=0.3 * (y > 1), grow=0.6 * (y > 1)).to_excel(tmp_path / f"External Anomalies {name}.xlsx", index=False)
    df, notes = load_mendeley_ili(tmp_path, assumed_sigma_frac_wt=0.02)
    assert set(df["run_id"]) == {"Y1", "Y3"} and len(df) == 6
    assert any("10.17632/c2h2jf5c54" in n for n in notes) and any("ASSUMPTION" in n for n in notes)
    res = run_analysis(df.astype(str).replace({"nan": None}), SourceInfo("Mendeley ILI", ["a", "b"], False, notes=notes))
    assert res.ok and res.match.status_counts()["LIKELY_MATCH"] == 3
    assert np.isclose(res.match.years_between, 731 / 365.25)   # 2000-01-01 -> 2002-01-01
    assert (res.findings["delta_mm"].round(6) == 0.6).all()
