"""Schema and data-quality validation.

Principles
----------
* The source data is never modified or deleted. Validation returns an *annotated working copy*
  with flag columns, plus an issue table and a transformation log.
* Every issue states what was found, what CorroSight does about it (its effect on the analysis)
  and what the user can do.
* Records with problems stay visible. They are excluded only from the specific calculation they
  would corrupt (e.g. a negative depth is excluded from growth, not from the report).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .schema import NUMERIC_COLUMNS, OPTIONAL_COLUMNS, REQUIRED_COLUMNS, AnalysisConfig

MAX_PLAUSIBLE_DEPTH_MM = 50.0   # depth above this almost certainly means wrong units
MAX_PLAUSIBLE_WT_MM = 50.0


@dataclass
class ValidationResult:
    data: pd.DataFrame                 # annotated working copy (numeric columns parsed, flags added)
    issues: pd.DataFrame               # one row per issue
    log: list[str] = field(default_factory=list)  # transformations / exclusions applied to the working copy
    blocking: bool = False             # True -> analysis cannot proceed (e.g. missing required columns)

    def counts(self) -> dict:
        if self.issues.empty:
            return {"Error": 0, "Warning": 0, "Info": 0}
        c = self.issues["severity"].value_counts().to_dict()
        return {k: int(c.get(k, 0)) for k in ("Error", "Warning", "Info")}


ISSUE_COLUMNS = ["issue_id", "severity", "code", "run_id", "observation_id", "field", "value",
                 "message", "effect", "action"]


def read_csv(source) -> pd.DataFrame:
    """Read a CSV from a path, bytes or file-like object, keeping every value as text.

    Values are kept as text so that validation can report non-numeric entries instead of
    silently coercing them.
    """
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    df = pd.read_csv(source, dtype=str, keep_default_na=True)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def check_schema(df: pd.DataFrame) -> list[str]:
    """Return the list of required columns that are missing."""
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def _circ_clock_diff(a, b):
    d = np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)) % 12.0
    return np.minimum(d, 12.0 - d)


def validate(df_raw: pd.DataFrame, config: AnalysisConfig | None = None,
             pipeline_length_m: float | None = None) -> ValidationResult:
    cfg = config or AnalysisConfig()
    issues: list[dict] = []
    log: list[str] = []

    def add(severity, code, row, fld, value, message, effect, action):
        issues.append(dict(
            severity=severity, code=code,
            run_id=None if row is None else row.get("run_id"),
            observation_id=None if row is None else row.get("observation_id"),
            field=fld, value=None if value is None or (isinstance(value, float) and np.isnan(value)) else str(value),
            message=message, effect=effect, action=action))

    # ---------------- schema ----------------
    missing = check_schema(df_raw)
    if missing:
        for col in missing:
            add("Error", "SCHEMA_MISSING_COLUMN", None, col, None,
                f"Required column '{col}' is not present in the uploaded data.",
                "Analysis cannot run.",
                f"Add a '{col}' column (see the schema table) or rename the matching column.")
        return ValidationResult(df_raw.copy(), _issues_frame(issues), log, blocking=True)

    df = df_raw.copy()
    df.insert(0, "source_row", np.arange(2, len(df) + 2))  # 1-based CSV line number (header = line 1)
    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
            log.append(f"Optional column '{col}' not supplied; treated as missing for every record.")

    # ---------------- type parsing (logged, original text retained) ----------------
    for col in NUMERIC_COLUMNS:
        original = df[col]
        parsed = pd.to_numeric(original, errors="coerce")
        bad = original.notna() & (original.astype(str).str.strip() != "") & parsed.isna()
        for i in df.index[bad]:
            add("Error", "NON_NUMERIC", df.loc[i], col, original[i],
                f"'{col}' contains a non-numeric value.",
                "Value treated as missing in the working copy; source value retained.",
                "Correct the value in the source file and re-upload.")
        if bad.any():
            log.append(f"{int(bad.sum())} non-numeric value(s) in '{col}' treated as missing in the working copy.")
        df[col] = parsed.astype(float)
    for col in ("run_id", "observation_id", "segment_id", "joint_id", "pipeline_id", "feature_type"):
        df[col] = df[col].astype("object").where(df[col].notna(), None)
        df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)

    dates = pd.to_datetime(df["inspection_date"], errors="coerce")
    df["inspection_date_parsed"] = dates

    # ---------------- identifiers and dates ----------------
    for fld in ("run_id", "observation_id", "segment_id"):
        for i in df.index[df[fld].isna() | (df[fld].astype(str).str.strip() == "")]:
            add("Error", "MISSING_ID", df.loc[i], fld, None,
                f"Record on CSV line {df.at[i, 'source_row']} has no '{fld}'.",
                "Record cannot be traced reliably; excluded from matching.",
                "Supply the identifier in the source file.")
    for i in df.index[dates.isna()]:
        add("Error", "INVALID_DATE", df.loc[i], "inspection_date", df_raw.at[i, "inspection_date"],
            "Inspection date is missing or not a valid date (expected YYYY-MM-DD).",
            "Elapsed time cannot be computed for this record; excluded from growth.",
            "Correct the inspection date.")
    for run, g in df.groupby("run_id", dropna=True):
        nd = g["inspection_date_parsed"].dropna().unique()
        if len(nd) > 1:
            add("Warning", "MULTIPLE_DATES_IN_RUN", {"run_id": run, "observation_id": None}, "inspection_date",
                ", ".join(sorted(pd.Series(nd).dt.strftime("%Y-%m-%d"))),
                f"Run {run} contains more than one inspection date.",
                "The earliest date is used as the run date.",
                "Confirm the run date with the inspection vendor.")

    # ---------------- location ----------------
    pos = df["axial_position_m"]
    loc_ok = pos.notna() & (pos >= 0)
    if pipeline_length_m:
        loc_ok &= pos <= pipeline_length_m
    for i in df.index[pos.isna()]:
        add("Error", "MISSING_POSITION", df.loc[i], "axial_position_m", None,
            "Axial position is missing.", "Excluded from matching (cannot be located); record retained.",
            "Supply the reported odometer distance.")
    bad_pos = pos.notna() & ~loc_ok
    for i in df.index[bad_pos]:
        add("Error", "INVALID_POSITION", df.loc[i], "axial_position_m", pos[i],
            f"Axial position {pos[i]:.2f} m is outside the valid range"
            + (f" (0 - {pipeline_length_m:.0f} m)." if pipeline_length_m else " (negative)."),
            "Excluded from matching; record retained.", "Check odometer reference and units.")

    clock = df["clock_position_h"]
    clock_ok = clock.notna() & (clock >= 0) & (clock <= 12)
    for i in df.index[~clock_ok]:
        add("Warning", "INVALID_CLOCK", df.loc[i], "clock_position_h", clock[i],
            "Clock position is missing or outside 0-12 h.",
            "Matching uses axial position only for this record (clock treated as unknown).",
            "Check the clock-position convention (hours vs degrees).")

    # ---------------- wall thickness ----------------
    wt = df["nominal_wt_mm"]
    wt_ok = wt.notna() & (wt > 0) & (wt <= MAX_PLAUSIBLE_WT_MM)
    miss_wt = wt.isna()
    if miss_wt.any():
        segs = sorted(df.loc[miss_wt, "segment_id"].dropna().unique())
        add("Warning", "MISSING_WALL_THICKNESS", {"run_id": None, "observation_id": None}, "nominal_wt_mm",
            f"{int(miss_wt.sum())} records",
            f"{int(miss_wt.sum())} records have no nominal wall thickness (segments: {', '.join(segs[:8])}"
            + (" ..." if len(segs) > 8 else "") + ").",
            "Depth as % of wall thickness, screening-threshold projections and engineering readiness "
            "cannot be completed for these records. They are NOT lowered in review priority.",
            "Request the nominal wall thickness from pipe-book / design records.")
    for i in df.index[wt.notna() & ~wt_ok]:
        add("Error", "INVALID_WALL_THICKNESS", df.loc[i], "nominal_wt_mm", wt[i],
            f"Nominal wall thickness {wt[i]} mm is zero, negative or implausible.",
            "Treated as unavailable for this record.", "Correct the wall thickness in the source file.")

    # ---------------- depth ----------------
    depth = df["depth_mm"]
    depth_ok = depth.notna() & (depth > 0) & (depth <= MAX_PLAUSIBLE_DEPTH_MM)
    for i in df.index[depth.isna()]:
        add("Error", "MISSING_DEPTH", df.loc[i], "depth_mm", None, "Depth is missing.",
            "Excluded from growth calculation; still eligible for location matching.",
            "Request the sizing result from the inspection vendor.")
    for i in df.index[depth.notna() & (depth <= 0)]:
        add("Error", "NON_POSITIVE_DEPTH", df.loc[i], "depth_mm", depth[i], "Depth is zero or negative.",
            "Excluded from growth calculation; still eligible for location matching.",
            "Check the sign convention and the vendor sizing record.")
    for i in df.index[depth > MAX_PLAUSIBLE_DEPTH_MM]:
        add("Error", "DEPTH_UNIT_SUSPECT", df.loc[i], "depth_mm", depth[i],
            f"Depth {depth[i]:g} mm is implausible; units may be micrometres or % wall thickness.",
            "Excluded from growth calculation; value NOT rescaled.",
            "Confirm the unit with the vendor and correct the source file.")
    exceeds = depth_ok & wt_ok & (depth > wt)
    for i in df.index[exceeds]:
        add("Error", "DEPTH_EXCEEDS_WT", df.loc[i], "depth_mm", depth[i],
            f"Depth {depth[i]:g} mm exceeds nominal wall thickness {wt[i]:g} mm.",
            "Excluded from growth calculation; flagged for review (possible sizing or data-entry error).",
            "Verify the measurement and the wall-thickness record.")
    depth_ok &= ~exceeds

    # run-level unit consistency
    run_med = df[depth_ok].groupby("run_id")["depth_mm"].median()
    if len(run_med) >= 2 and run_med.max() / max(run_med.min(), 1e-9) > 5:
        add("Warning", "INCONSISTENT_UNITS", {"run_id": None, "observation_id": None}, "depth_mm",
            ", ".join(f"{k}: {v:.2f}" for k, v in run_med.items()),
            "Median depth differs by more than 5x between runs; runs may use different units.",
            "Results may be invalid until units are confirmed.", "Confirm both runs report depth in mm.")

    for col in ("length_mm", "width_mm"):
        for i in df.index[df[col] < 0]:
            add("Error", "INVALID_DIMENSION", df.loc[i], col, df.at[i, col], f"{col} is negative.",
                "Dimension treated as unavailable.", "Correct the value in the source file.")

    # ---------------- uncertainty ----------------
    unc = df["depth_uncertainty_mm"]
    unc_ok = unc.notna() & (unc > 0)
    if (~unc_ok).any():
        add("Info", "MISSING_UNCERTAINTY", {"run_id": None, "observation_id": None}, "depth_uncertainty_mm",
            f"{int((~unc_ok).sum())} records",
            f"{int((~unc_ok).sum())} records have no stated depth measurement uncertainty.",
            "No uncertainty interval or noise test is computed for changes involving these records; "
            "they are labelled 'uncertainty unknown' (not treated as certain).",
            "Obtain the tool sizing specification from the inspection vendor.")

    # ---------------- duplicates ----------------
    excluded_reason = pd.Series([None] * len(df), index=df.index, dtype=object)
    dup_of = pd.Series([None] * len(df), index=df.index, dtype=object)
    raw_cols = [c for c in df_raw.columns]
    row_keys = df_raw[raw_cols].fillna("<NA>").astype(str).agg("|".join, axis=1).to_numpy()
    first_seen: dict[str, int] = {}
    exact = np.zeros(len(df), dtype=bool)
    for pos_i, k in enumerate(row_keys):
        if k in first_seen:
            exact[pos_i] = True
        else:
            first_seen[k] = pos_i
    exact = pd.Series(exact, index=df.index)
    for i in df.index[exact.to_numpy()]:
        first = df.index[first_seen[row_keys[df.index.get_loc(i)]]]
        dup_of[i] = df.at[first, "observation_id"]
        excluded_reason[i] = "exact duplicate row"
        add("Warning", "EXACT_DUPLICATE", df.loc[i], "(row)", f"line {df.at[i, 'source_row']}",
            f"CSV line {df.at[i, 'source_row']} is an exact copy of line {df.at[first, 'source_row']}.",
            "Second copy excluded from matching; both rows retained in the source data and report.",
            "Remove the duplicate from the source export if confirmed.")
    same_id = df.duplicated(subset=["run_id", "observation_id"], keep="first") & ~exact.to_numpy()
    for i in df.index[same_id]:
        excluded_reason[i] = "duplicate observation_id"
        add("Warning", "DUPLICATE_ID", df.loc[i], "observation_id", df.at[i, "observation_id"],
            "Observation ID is used by more than one record in the same run with different values.",
            "Later record excluded from matching; both retained.", "Resolve the conflicting records with the vendor.")

    # near-duplicates: same run, very close location and depth
    for run, g in df[loc_ok & excluded_reason.isna()].groupby("run_id"):
        g = g.sort_values("axial_position_m")
        idx = g.index.to_numpy()
        p = g["axial_position_m"].to_numpy()
        for a in range(len(idx)):
            if excluded_reason[idx[a]] is not None:
                continue
            for b in range(a + 1, len(idx)):
                if p[b] - p[a] > cfg.near_duplicate_pos_m:
                    break
                ia, ib = idx[a], idx[b]
                if excluded_reason[ib] is not None:
                    continue
                dc = _circ_clock_diff(df.at[ia, "clock_position_h"], df.at[ib, "clock_position_h"])
                dd = abs(df.at[ia, "depth_mm"] - df.at[ib, "depth_mm"])
                dl = abs(df.at[ia, "length_mm"] - df.at[ib, "length_mm"])
                if (dc <= cfg.near_duplicate_clock_h and (np.isnan(dd) or dd <= cfg.near_duplicate_depth_mm)
                        and (np.isnan(dl) or dl <= cfg.near_duplicate_length_mm)):
                    dup_of[ib] = df.at[ia, "observation_id"]
                    excluded_reason[ib] = f"possible duplicate of {df.at[ia, 'observation_id']}"
                    add("Warning", "POSSIBLE_DUPLICATE", df.loc[ib], "(record)", df.at[ib, "observation_id"],
                        f"{df.at[ib, 'observation_id']} is within {p[b] - p[a]:.3f} m, {dc:.2f} h and "
                        f"{0 if np.isnan(dd) else dd:.2f} mm depth of {df.at[ia, 'observation_id']} in the same run "
                        f"(similar length).",
                        "Excluded from matching pending review; NOT deleted. Appears in the findings list.",
                        "Confirm with the vendor whether this is a double call or two separate anomalies.")
    n_excl = int(excluded_reason.notna().sum())
    if n_excl:
        log.append(f"{n_excl} record(s) flagged as duplicates and excluded from matching (retained and reported).")

    # ---------------- flags ----------------
    df["location_valid"] = loc_ok.to_numpy()
    df["clock_valid"] = clock_ok.to_numpy()
    df["depth_valid"] = depth_ok.to_numpy() & dates.notna().to_numpy()
    df["wt_valid"] = wt_ok.to_numpy()
    df["uncertainty_known"] = unc_ok.to_numpy()
    df["duplicate_of"] = dup_of
    no_id = df["observation_id"].isna() | df["run_id"].isna()
    excluded_reason[no_id & excluded_reason.isna()] = "missing identifier"
    excluded_reason[~loc_ok & excluded_reason.isna()] = "invalid or missing location"
    df["exclusion_reason"] = excluded_reason
    df["match_eligible"] = df["exclusion_reason"].isna()
    df["depth_pct_wt"] = np.where(df["depth_valid"] & df["wt_valid"], df["depth_mm"] / df["nominal_wt_mm"] * 100, np.nan)

    # per-record issue summary for display
    iss = _issues_frame(issues)
    rec = iss.dropna(subset=["observation_id"]).groupby(["run_id", "observation_id"])["code"].apply(
        lambda s: "; ".join(sorted(set(s))))
    keys = list(zip(df["run_id"], df["observation_id"]))
    df["quality_flags"] = [rec.get(k, "") if isinstance(k[1], str) else "" for k in keys]
    df.loc[~df["uncertainty_known"], "quality_flags"] = df.loc[~df["uncertainty_known"], "quality_flags"].map(
        lambda s: (s + "; " if s else "") + "MISSING_UNCERTAINTY")
    df.loc[df["nominal_wt_mm"].isna(), "quality_flags"] = df.loc[df["nominal_wt_mm"].isna(), "quality_flags"].map(
        lambda s: (s + "; " if s else "") + "MISSING_WALL_THICKNESS")

    return ValidationResult(df, iss, log, blocking=False)


def _issues_frame(issues: list[dict]) -> pd.DataFrame:
    iss = pd.DataFrame(issues, columns=[c for c in ISSUE_COLUMNS if c != "issue_id"])
    sev_order = {"Error": 0, "Warning": 1, "Info": 2}
    if not iss.empty:
        iss = iss.sort_values(by="severity", key=lambda s: s.map(sev_order), kind="stable").reset_index(drop=True)
    iss.insert(0, "issue_id", [f"V{i + 1:03d}" for i in range(len(iss))])
    return iss
