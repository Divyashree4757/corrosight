"""Importer for a real, openly licensed in-line inspection (ILI) dataset.

Source
------
Yarveisy, R. et al. (2021). "Dataset for: Cross-country Pipeline Inspection Data Analysis and Testing of
Probabilistic Degradation Models". Mendeley Data, V1. DOI 10.17632/c2h2jf5c54.1.
Licence: Creative Commons Attribution 4.0 (CC BY 4.0). Institutions: Memorial University of Newfoundland,
Macquarie University. https://data.mendeley.com/datasets/c2h2jf5c54

What it contains (per its README): external corrosion anomalies from four consecutive ILI runs of an
anonymised cross-country pipeline, one Excel file per run ("Year One", "Year Three", "Year Five",
"Year Seven"). The years are RELATIVE: they "do not reflect real asset age".

Columns used (README Table 3)            -> CorroSight column
  Year                                     run_id ("Y1", "Y3", ...) and a placeholder date
  GWNUM   girth weld number                joint_id ("GW<n>") and segment_id (blocks of 10 joints)
  SPD.m   feature start distance [m]       axial_position_m
  SPO.deg start circumferential [deg]      clock_position_h (= deg / 30)
  WT.mm   nominal wall thickness [mm]      nominal_wt_mm
  L.mm / W.mm   length / width [mm]        length_mm / width_mm
  MD.mm   maximum depth [mm]               depth_mm
The dataset does NOT state tool sizing uncertainty. By default depth_uncertainty_mm is left empty, so
CorroSight reports "uncertainty unknown" and makes no forecasts. `assumed_sigma_frac_wt` lets a user
enter an assumption (e.g. a vendor spec); it is then recorded in the source notes and the report.
Dates are placeholders: inspection_date = 2000-01-01 + (Year - 1) years, so ELAPSED time between runs
is correct but calendar dates are not real.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_CITATION = ("Yarveisy et al. (2021), Mendeley Data V1, DOI 10.17632/c2h2jf5c54.1, CC BY 4.0 - "
                   "real anonymised ILI data, four runs at relative years 1, 3, 5, 7")

WORD_YEARS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}

# normalised source name (lower-case, alphanumerics only) -> CorroSight field
ALIASES = {
    "year": "year",
    "gwnum": "gwnum", "girthweldnumber": "gwnum", "gw": "gwnum",
    "spdm": "spd", "spd": "spd",
    "spodeg": "spo", "spo": "spo",
    "wtmm": "wt", "wt": "wt",
    "lmm": "length", "l": "length",
    "wmm": "width", "w": "width",
    "mdmm": "depth", "md": "depth",
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _year_from_name(path: Path) -> int | None:
    stem = path.stem.lower()
    for w, n in WORD_YEARS.items():
        if re.search(rf"year[\s_\-]*{w}\b", stem):
            return n
    m = re.search(r"year[\s_\-]*(\d+)", stem)
    return int(m.group(1)) if m else None


def standardise_frame(df: pd.DataFrame, year: int | None, source_name: str,
                      assumed_sigma_frac_wt: float | None = None, pipeline_id: str = "MENDELEY-C2H2JF5C54") -> pd.DataFrame:
    """Map one run's raw table to the CorroSight schema. Raw values are copied, never altered."""
    cols = {}
    for c in df.columns:
        key = ALIASES.get(_norm(c))
        if key and key not in cols:
            cols[key] = c
    missing = [k for k in ("spd", "depth") if k not in cols]
    if missing:
        raise ValueError(f"{source_name}: required source columns not found ({missing}); columns seen: {list(df.columns)}")
    if year is None:
        if "year" not in cols:
            raise ValueError(f"{source_name}: inspection year not found in file name or a 'Year' column")
        year = int(pd.to_numeric(df[cols["year"]], errors="coerce").dropna().mode().iloc[0])

    def col(k):
        return pd.to_numeric(df[cols[k]], errors="coerce") if k in cols else pd.Series(np.nan, index=df.index)

    gw = col("gwnum")
    out = pd.DataFrame({
        "pipeline_id": pipeline_id,
        "run_id": f"Y{year}",
        "inspection_date": (pd.Timestamp("2000-01-01") + pd.DateOffset(years=year - 1)).strftime("%Y-%m-%d"),
        "observation_id": [f"Y{year}-{i + 1:05d}" for i in range(len(df))],
        "segment_id": ["S{:03d}".format(int(g // 10)) if pd.notna(g) else None for g in gw],
        "joint_id": ["GW{:d}".format(int(g)) if pd.notna(g) else None for g in gw],
        "axial_position_m": col("spd"),
        "clock_position_h": col("spo") / 30.0,
        "depth_mm": col("depth"),
        "length_mm": col("length"),
        "width_mm": col("width"),
        "nominal_wt_mm": col("wt"),
        "feature_type": "EXTERNAL METAL LOSS",
    })
    out["depth_uncertainty_mm"] = (assumed_sigma_frac_wt * out["nominal_wt_mm"]) if assumed_sigma_frac_wt else np.nan
    return out


def load_mendeley_ili(folder: str | Path, assumed_sigma_frac_wt: float | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Read every .xlsx run file in `folder` and return (combined CorroSight frame, provenance notes)."""
    folder = Path(folder)
    files = sorted(p for p in folder.rglob("*.xlsx") if not p.name.startswith("~$"))
    if not files:
        raise FileNotFoundError(f"No .xlsx files found under {folder}")
    frames, notes = [], [SOURCE_CITATION]
    for p in files:
        raw = pd.read_excel(p)
        std = standardise_frame(raw, _year_from_name(p), p.name, assumed_sigma_frac_wt)
        frames.append(std)
        notes.append(f"{p.name}: {len(raw)} rows -> run {std['run_id'].iloc[0]}")
    notes.append("inspection_date values are placeholders derived from relative inspection years; elapsed time is correct.")
    notes.append("Segments are blocks of 10 girth welds (derived); joint_id is the girth weld number.")
    if assumed_sigma_frac_wt:
        notes.append(f"ASSUMPTION: depth_uncertainty_mm = {assumed_sigma_frac_wt:g} x nominal WT (not in the source data).")
    else:
        notes.append("Source states no sizing uncertainty; depth_uncertainty_mm left empty (forecasts will not be made).")
    return pd.concat(frames, ignore_index=True), notes


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Convert the Mendeley c2h2jf5c54 ILI Excel files to a CorroSight CSV.")
    ap.add_argument("folder", help="folder containing the downloaded .xlsx files")
    ap.add_argument("--out", default="data/real_mendeley_ili.csv")
    ap.add_argument("--assume-sigma-frac-wt", type=float, default=None,
                    help="optional ASSUMED 1-sigma depth uncertainty as a fraction of WT (e.g. 0.078)")
    a = ap.parse_args()
    df, notes = load_mendeley_ili(a.folder, a.assume_sigma_frac_wt)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False)
    print("\n".join(notes))
    print(f"{len(df)} records, runs {sorted(df['run_id'].unique())} -> {a.out}")
