"""Deterministic generator for a FICTIONAL two-run in-line-inspection (ILI) dataset.

Pipeline layout (fictional): 4.8 km, 400 joints of 12 m, 40 segments of 120 m (10 joints each).
Run 1 "R2016" on 2016-01-15 and run 2 "R2023" on 2023-01-15 (seven years apart).

The generator first simulates hidden "true" defects (location, true depth, true growth rate),
then simulates what two different inspection tools would report, including:
  * odometer drift and positional noise, clock-position noise,
  * depth-sizing noise (different per tool),
  * probability of detection (shallow defects may be missed),
  * defects that initiate between the runs (new detections),
  * tightly clustered defects (ambiguous candidate matches),
  * inactive defects (true rate = 0) whose noisy measurements produce negative changes,
  * missing values, duplicates, invalid and unit-suspicious records.

Two outputs are produced and kept strictly separate:
  * synthetic_inspections.csv      -> the ONLY file the analysis reads,
  * synthetic_ground_truth.csv     -> used ONLY by src/evaluation.py after the analysis.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

PIPELINE_ID = "CG-DEMO-24IN-01"
PIPELINE_LENGTH_M = 4800.0
N_JOINTS = 400
JOINT_LENGTH_M = 12.0
N_SEGMENTS = 40
SEGMENT_LENGTH_M = 120.0
OUTER_DIAMETER_MM = 610.0
SMYS_MPA = 359.0          # fictional design value (grade unknown for some segments, see below)
MAOP_KPA = 6900.0         # fictional design value
NO_GRADE_SEGMENTS = {20, 21, 22}  # 0-based indexes of segments S21-S23 whose pipe grade "is not on file"

RUN1 = {"run_id": "R2016", "date": "2016-01-15", "depth_sigma": 0.40, "prefix": "A16"}
RUN2 = {"run_id": "R2023", "date": "2023-01-15", "depth_sigma": 0.30, "prefix": "B23"}
YEARS_BETWEEN = (pd.Timestamp(RUN2["date"]) - pd.Timestamp(RUN1["date"])).days / 365.25

DEFAULT_SEED = 20261023


def _segment_of(pos_m: float) -> str:
    idx = int(np.clip(pos_m // SEGMENT_LENGTH_M, 0, N_SEGMENTS - 1))
    return f"S{idx + 1:02d}"


def _joint_of(pos_m: float) -> str:
    idx = int(np.clip(pos_m // JOINT_LENGTH_M, 0, N_JOINTS - 1))
    return f"J{idx + 1:04d}"


def _pod(depth_mm: np.ndarray) -> np.ndarray:
    """Illustrative probability of detection as a smooth function of true depth."""
    return 1.0 / (1.0 + np.exp(-(depth_mm - 0.55) / 0.10))


def generate(seed: int = DEFAULT_SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (inspections, ground_truth). Deterministic for a given seed."""
    rng = np.random.default_rng(seed)

    # ---------------- pipeline properties per segment ----------------
    wt_choices = np.array([7.9, 9.5, 11.1])
    seg_wt = rng.choice(wt_choices, size=N_SEGMENTS, p=[0.35, 0.45, 0.20])
    corrosivity = rng.lognormal(mean=0.0, sigma=0.35, size=N_SEGMENTS)
    hot = rng.choice(N_SEGMENTS, size=4, replace=False)          # a few more corrosive segments
    corrosivity[hot] *= 2.2

    # ---------------- hidden true defects ----------------
    n_existing, n_new, n_cluster = 300, 55, 28
    rows = []

    def make_defect(pos, clock, depth0, rate, length, width, t_init, cluster_id=None):
        seg_idx = int(np.clip(pos // SEGMENT_LENGTH_M, 0, N_SEGMENTS - 1))
        rows.append(
            dict(pos=pos, clock=clock % 12.0, depth_r1=depth0, rate=rate, length=length, width=width,
                 t_init=t_init, seg_idx=seg_idx, wt=seg_wt[seg_idx], cluster_id=cluster_id)
        )

    def draw_rate(seg_idx):
        if rng.random() < 0.35:
            return 0.0  # inactive defect
        return float(min(0.55, rng.lognormal(np.log(0.07), 0.55) * corrosivity[seg_idx]))

    for _ in range(n_existing):
        pos = rng.uniform(2.0, PIPELINE_LENGTH_M - 2.0)
        seg_idx = int(pos // SEGMENT_LENGTH_M)
        clock = rng.normal(6.0, 2.2) if rng.random() < 0.6 else rng.uniform(0, 12)
        depth0 = float(np.clip(rng.gamma(2.0, 0.07) * seg_wt[seg_idx], 0.4, 0.55 * seg_wt[seg_idx]))
        make_defect(pos, clock, depth0, draw_rate(seg_idx), rng.uniform(10, 80), rng.uniform(10, 60), 0.0)

    # clustered neighbours -> ambiguous candidates (placed close to an existing defect)
    base_idx = rng.choice(n_existing, size=n_cluster, replace=False)
    for k, b in enumerate(base_idx):
        base = rows[b]
        cid = f"C{k + 1:02d}"
        base["cluster_id"] = cid
        pos = base["pos"] + rng.choice([-1, 1]) * rng.uniform(0.15, 0.45)
        clock = base["clock"] + rng.normal(0, 0.3)
        depth0 = float(np.clip(base["depth_r1"] + rng.normal(0, 0.4), 0.5, 0.5 * base["wt"]))
        make_defect(pos, clock, depth0, draw_rate(base["seg_idx"]), rng.uniform(10, 60),
                    rng.uniform(10, 50), 0.0, cluster_id=cid)

    # defects initiating between runs (true depth at run1 = 0)
    for _ in range(n_new):
        pos = rng.uniform(2.0, PIPELINE_LENGTH_M - 2.0)
        seg_idx = int(pos // SEGMENT_LENGTH_M)
        t_init = rng.uniform(0.5, 5.5)
        rate = max(0.06, draw_rate(seg_idx)) * 1.3
        make_defect(pos, rng.uniform(0, 12), 0.0, rate, rng.uniform(10, 50), rng.uniform(10, 40), t_init)

    # a handful of fast-growing defects in corrosive segments (realistic outliers)
    for h in hot[:3]:
        pos = h * SEGMENT_LENGTH_M + rng.uniform(5, SEGMENT_LENGTH_M - 5)
        make_defect(pos, rng.normal(6, 1), 0.30 * seg_wt[h], rng.uniform(0.30, 0.45),
                    rng.uniform(40, 90), rng.uniform(30, 60), 0.0)

    truth = pd.DataFrame(rows)
    truth["true_defect_id"] = [f"D{i + 1:04d}" for i in range(len(truth))]
    truth["depth_r2"] = np.where(
        truth["t_init"] > 0,
        0.5 + truth["rate"] * (YEARS_BETWEEN - truth["t_init"]),
        truth["depth_r1"] + truth["rate"] * YEARS_BETWEEN,
    )

    # ---------------- simulate the two inspection runs ----------------
    obs = []

    def report(run, d, true_depth, pos_offset, sigma_pos, kind="TRUE"):
        reported_depth = true_depth + rng.normal(0, run["depth_sigma"])
        obs.append(
            dict(
                pipeline_id=PIPELINE_ID,
                run_id=run["run_id"],
                inspection_date=run["date"],
                axial_position_m=round(d["pos"] + pos_offset + rng.normal(0, sigma_pos), 3),
                clock_position_h=round((d["clock"] + rng.normal(0, 0.15)) % 12.0, 2),
                depth_mm=round(max(0.05, reported_depth), 2),
                length_mm=round(max(5.0, d["length"] + rng.normal(0, 5)), 1),
                width_mm=round(max(5.0, d["width"] + rng.normal(0, 5)), 1),
                nominal_wt_mm=d["wt"],
                depth_uncertainty_mm=run["depth_sigma"],
                outer_diameter_mm=OUTER_DIAMETER_MM,
                smys_mpa=np.nan if d.get("seg_idx", 0) in NO_GRADE_SEGMENTS else SMYS_MPA,
                maop_kpa=MAOP_KPA,
                feature_type="INTERNAL METAL LOSS" if 3.5 <= d["clock"] <= 8.5 else "EXTERNAL METAL LOSS",
                _true_defect_id=d["true_defect_id"],
                _true_depth=round(true_depth, 3),
                _kind=kind,
            )
        )

    for _, d in truth.iterrows():
        # run 1: only defects that already exist
        if d["t_init"] == 0 and rng.random() < _pod(np.array([d["depth_r1"]]))[0]:
            report(RUN1, d, d["depth_r1"], 0.0, 0.10)
        # run 2: odometer drift grows along the line (0.25 m -> 0.85 m)
        drift = 0.25 + 0.60 * d["pos"] / PIPELINE_LENGTH_M
        if rng.random() < _pod(np.array([d["depth_r2"]]))[0] * 0.97:
            report(RUN2, d, d["depth_r2"], drift, 0.10)

    df = pd.DataFrame(obs)

    # spurious calls in run 2 (no true defect)
    for _ in range(3):
        pos = rng.uniform(10, PIPELINE_LENGTH_M - 10)
        seg_idx = int(pos // SEGMENT_LENGTH_M)
        fake = dict(pos=pos, clock=rng.uniform(0, 12), length=15, width=12, wt=seg_wt[seg_idx],
                    true_defect_id="NONE", seg_idx=seg_idx)
        report(RUN2, fake, rng.uniform(0.7, 1.1), 0.0, 0.0, kind="SPURIOUS")
    df = pd.DataFrame(obs)

    df = df.sort_values(["run_id", "axial_position_m"]).reset_index(drop=True)
    df["segment_id"] = [_segment_of(p) for p in df["axial_position_m"]]
    df["joint_id"] = [_joint_of(p) for p in df["axial_position_m"]]
    for run in (RUN1, RUN2):
        m = df["run_id"] == run["run_id"]
        df.loc[m, "observation_id"] = [f"{run['prefix']}-{i + 1:04d}" for i in range(int(m.sum()))]

    # ---------------- inject data-quality problems (documented) ----------------
    df["depth_mm"] = df["depth_mm"].astype(float)
    df["nominal_wt_mm"] = df["nominal_wt_mm"].astype(float)
    df["depth_uncertainty_mm"] = df["depth_uncertainty_mm"].astype(float)
    df["axial_position_m"] = df["axial_position_m"].astype(float)
    df["clock_position_h"] = df["clock_position_h"].astype(float)

    r1 = df.index[df["run_id"] == RUN1["run_id"]].to_numpy()
    r2 = df.index[df["run_id"] == RUN2["run_id"]].to_numpy()
    issue_rng = np.random.default_rng(seed + 1)

    def pick(idx, n):
        return issue_rng.choice(idx, size=n, replace=False)

    corrupt = {}
    for i in pick(r2, 4):
        df.at[i, "depth_mm"] = np.nan; corrupt[i] = "missing depth"
    for i in pick(r1, 2):
        df.at[i, "depth_mm"] = np.nan; corrupt[i] = "missing depth"
    # whole segment without pipe-book wall thickness (mimics missing design data)
    df.loc[df["segment_id"] == "S17", "nominal_wt_mm"] = np.nan
    for i in pick(r1, 14):
        df.at[i, "depth_uncertainty_mm"] = np.nan
    i = pick(r2, 1)[0]; df.at[i, "depth_mm"] = -0.8; corrupt[i] = "negative depth"
    i = pick(r2, 1)[0]; df.at[i, "depth_mm"] = round(df.at[i, "nominal_wt_mm"] * 1.15, 2) if not np.isnan(df.at[i, "nominal_wt_mm"]) else 12.5; corrupt[i] = "depth exceeds wall thickness"
    i = pick(r1, 1)[0]; df.at[i, "nominal_wt_mm"] = 0.0; corrupt[i] = "zero wall thickness"
    i = pick(r2, 1)[0]; df.at[i, "axial_position_m"] = 5230.4; corrupt[i] = "position outside pipeline"
    i = pick(r1, 1)[0]; df.at[i, "axial_position_m"] = np.nan; corrupt[i] = "missing position"
    i = pick(r2, 1)[0]; df.at[i, "clock_position_h"] = 14.5; corrupt[i] = "invalid clock position"
    i = pick(r2, 1)[0]; df.at[i, "depth_mm"] = round(df.at[i, "depth_mm"] * 1000, 0) if not np.isnan(df.at[i, "depth_mm"]) else 2100.0; corrupt[i] = "depth unit error (micrometres?)"
    for i, reason in corrupt.items():
        df.at[i, "_kind"] = "CORRUPTED"
        df.at[i, "_note"] = reason

    # near-duplicate vendor double-calls in run 2 and one exact duplicate row in run 1
    dup_rows = []
    for k, i in enumerate(pick(r2, 5)):
        row = df.loc[i].copy()
        row["observation_id"] = f"{RUN2['prefix']}-D{k + 1:02d}"
        row["axial_position_m"] = round(row["axial_position_m"] + 0.012, 3)
        row["_kind"] = "DUPLICATE"
        row["_note"] = f"duplicate of {df.at[i, 'observation_id']}"
        dup_rows.append(row)
    exact = df.loc[pick(r1, 1)[0]].copy()
    exact["_kind"] = "DUPLICATE"
    exact["_note"] = "exact duplicate row"
    dup_rows.append(exact)
    df = pd.concat([df, pd.DataFrame(dup_rows)], ignore_index=True)
    df = df.sort_values(["run_id", "axial_position_m", "observation_id"], na_position="last").reset_index(drop=True)

    # ---------------- split: analysis input vs. hidden ground truth ----------------
    gt_cols = ["run_id", "observation_id", "_true_defect_id", "_true_depth", "_kind", "_note"]
    ground = df[gt_cols].rename(columns={"_true_defect_id": "true_defect_id", "_true_depth": "true_depth_mm",
                                         "_kind": "record_kind", "_note": "note"})
    ground = ground.merge(
        truth[["true_defect_id", "rate", "cluster_id", "t_init"]].rename(
            columns={"rate": "true_rate_mm_per_yr", "t_init": "true_initiation_yr_after_run1"}),
        on="true_defect_id", how="left")
    ground["note"] = ground["note"].fillna("")

    out_cols = ["pipeline_id", "run_id", "inspection_date", "observation_id", "segment_id", "joint_id",
                "axial_position_m", "clock_position_h", "depth_mm", "length_mm", "width_mm",
                "nominal_wt_mm", "depth_uncertainty_mm", "outer_diameter_mm", "smys_mpa", "maop_kpa", "feature_type"]
    inspections = df[out_cols].copy()
    return inspections, ground


def write_demo_files(data_dir: str | Path, seed: int = DEFAULT_SEED) -> dict[str, Path]:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    insp, gt = generate(seed)
    paths = {
        "combined": data_dir / "synthetic_inspections.csv",
        "ground_truth": data_dir / "synthetic_ground_truth.csv",
        "run1": data_dir / "inspection_2016.csv",
        "run2": data_dir / "inspection_2023.csv",
    }
    insp.to_csv(paths["combined"], index=False)
    gt.to_csv(paths["ground_truth"], index=False)
    insp[insp["run_id"] == RUN1["run_id"]].to_csv(paths["run1"], index=False)
    insp[insp["run_id"] == RUN2["run_id"]].to_csv(paths["run2"], index=False)
    return paths


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate the fictional CorroSight demo dataset.")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data"))
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args()
    for name, p in write_demo_files(args.out, args.seed).items():
        print(f"{name:13s} -> {p}")
