"""Corrosion Memory Graph: transparent cross-run defect matching.

Method (documented, deterministic)
----------------------------------
1. **Eligibility.** Only records that validation marked `match_eligible` take part (records with no
   location, missing IDs or flagged duplicates are kept but shown as "Excluded from matching").
2. **Run alignment (optional).** ILI odometers drift. For every segment we estimate the axial offset
   between runs as the median position difference of *unambiguous anchor pairs* (each earlier record's
   nearest later record within 2 m and 1 h, accepted only if it is mutual-nearest and no second record lies
   within 1 m). Segments with < 3 anchors use the pipeline-wide median. Only a working column is changed;
   reported positions stay untouched and both raw and aligned differences are shown.
3. **Candidate gating.** A later record is a candidate for an earlier record if
   |aligned axial difference| <= `pos_gate_m` AND circular clock difference <= `clock_gate_h`
   (clock gate skipped if either clock is invalid; a fixed penalty is then applied).
4. **Cost.** Normalised distance d with d^2 = (dx/pos_scale)^2 + (dclock/clock_scale)^2 +
   (dlength/length_scale)^2 (length term only when both lengths exist). Depth is NOT used for matching
   so that a growth (or decrease) cannot bias the match.
5. **One-to-one assignment.** Minimum-total-cost assignment (Hungarian algorithm,
   `scipy.optimize.linear_sum_assignment`) solved per connected group of candidates, with an explicit
   "leave unmatched" option costing `gate^2` per record. This prevents one-to-many matches.
6. **Ambiguity.** An assigned pair is *Ambiguous* if any competing candidate (another later record for
   the same earlier record, or vice versa) has a normalised distance within `ambiguity_margin` of the
   assigned one. Ambiguous pairs are reported as provisional and are not used for forecasts.
7. **Agreement indicator** = exp(-d^2 / 2): 1.0 means identical aligned location/size. It is a
   similarity index, NOT a probability that the match is correct.

The synthetic ground truth is never read here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from .schema import MATCH_STATUSES, AnalysisConfig

CLOCK_UNKNOWN_PENALTY = 1.0  # contribution to d^2 when a clock position is unavailable


@dataclass
class MatchResult:
    tracks: pd.DataFrame       # one row per finding (track)
    candidates: pd.DataFrame   # every gated candidate pair with its cost
    offsets: pd.DataFrame      # per-segment odometer offset used for alignment
    run_a: str
    run_b: str
    date_a: pd.Timestamp
    date_b: pd.Timestamp

    @property
    def years_between(self) -> float:
        return (self.date_b - self.date_a).days / 365.25

    def status_counts(self) -> dict:
        c = self.tracks["match_status"].value_counts().to_dict()
        return {k: int(c.get(k, 0)) for k in MATCH_STATUSES}


def clock_diff(a, b):
    d = np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)) % 12.0
    return np.minimum(d, 12.0 - d)


def run_date(df: pd.DataFrame, run_id: str) -> pd.Timestamp:
    return df.loc[df["run_id"] == run_id, "inspection_date_parsed"].min()


def estimate_offsets(A: pd.DataFrame, B: pd.DataFrame) -> pd.DataFrame:
    """Per-segment odometer offset (later minus earlier) from unambiguous anchor pairs."""
    if A.empty or B.empty:
        return pd.DataFrame(columns=["segment_id", "n_anchor_pairs", "offset_m", "source"])
    pa = A["axial_position_m"].to_numpy()
    pb = B["axial_position_m"].to_numpy()
    ca, cb = A["clock_position_h"].to_numpy(), B["clock_position_h"].to_numpy()
    order = np.argsort(pb)
    pb_s = pb[order]
    anchors = []
    for i in range(len(pa)):
        lo, hi = np.searchsorted(pb_s, pa[i] - 2.0), np.searchsorted(pb_s, pa[i] + 2.0)
        js = order[lo:hi]
        js = [j for j in js if not (np.isfinite(ca[i]) and np.isfinite(cb[j])) or clock_diff(ca[i], cb[j]) <= 1.0]
        if not js:
            continue
        dists = np.abs(pb[js] - pa[i])
        k = int(np.argmin(dists))
        j = js[k]
        if np.sum(dists < dists[k] + 1.0) > 1:   # a second record within 1 m -> not an anchor
            continue
        # mutual nearest: is i the nearest earlier record to j?
        da = np.abs(pa - pb[j])
        if int(np.argmin(da)) != i or np.sum(da < da[i] + 1.0) > 1:
            continue
        anchors.append((A["segment_id"].iloc[i], pb[j] - pa[i]))
    anc = pd.DataFrame(anchors, columns=["segment_id", "delta"])
    global_off = float(anc["delta"].median()) if len(anc) else 0.0
    segs = sorted(set(A["segment_id"].dropna()) | set(B["segment_id"].dropna()))
    rows = []
    for s in segs:
        d = anc.loc[anc["segment_id"] == s, "delta"]
        if len(d) >= 3:
            rows.append((s, len(d), float(d.median()), "segment median"))
        else:
            rows.append((s, len(d), global_off, "pipeline median (few anchors)"))
    return pd.DataFrame(rows, columns=["segment_id", "n_anchor_pairs", "offset_m", "source"])


def match_runs(data: pd.DataFrame, run_a: str, run_b: str, config: AnalysisConfig | None = None) -> MatchResult:
    cfg = config or AnalysisConfig()
    date_a, date_b = run_date(data, run_a), run_date(data, run_b)
    if pd.notna(date_a) and pd.notna(date_b) and date_b < date_a:
        run_a, run_b, date_a, date_b = run_b, run_a, date_b, date_a  # always earlier -> later

    in_a = data["run_id"] == run_a
    in_b = data["run_id"] == run_b
    A = data[in_a & data["match_eligible"]].reset_index(drop=True)
    B = data[in_b & data["match_eligible"]].reset_index(drop=True)

    # ---------------- alignment ----------------
    if cfg.align_runs:
        offsets = estimate_offsets(A, B)
    else:
        segs = sorted(set(A["segment_id"].dropna()) | set(B["segment_id"].dropna()))
        offsets = pd.DataFrame({"segment_id": segs, "n_anchor_pairs": 0, "offset_m": 0.0, "source": "alignment off"})
    off_map = dict(zip(offsets["segment_id"], offsets["offset_m"]))
    default_off = float(offsets["offset_m"].median()) if len(offsets) else 0.0
    B_off = B["segment_id"].map(off_map).fillna(default_off).to_numpy(dtype=float)
    pb_aligned = B["axial_position_m"].to_numpy() - B_off

    # ---------------- candidates ----------------
    pa = A["axial_position_m"].to_numpy()
    ca, cb = A["clock_position_h"].to_numpy(), B["clock_position_h"].to_numpy()
    va, vb = A["clock_valid"].to_numpy(), B["clock_valid"].to_numpy()
    la, lb = A["length_mm"].to_numpy(), B["length_mm"].to_numpy()
    order = np.argsort(pb_aligned)
    pbs = pb_aligned[order]
    cand = []
    for i in range(len(A)):
        lo = np.searchsorted(pbs, pa[i] - cfg.pos_gate_m)
        hi = np.searchsorted(pbs, pa[i] + cfg.pos_gate_m, side="right")
        for j in order[lo:hi]:
            dx = pb_aligned[j] - pa[i]
            clock_known = bool(va[i] and vb[j])
            dc = float(clock_diff(ca[i], cb[j])) if clock_known else np.nan
            if clock_known and dc > cfg.clock_gate_h:
                continue
            dl = lb[j] - la[i] if np.isfinite(la[i]) and np.isfinite(lb[j]) else np.nan
            d2 = (dx / cfg.pos_scale_m) ** 2
            d2 += (dc / cfg.clock_scale_h) ** 2 if clock_known else CLOCK_UNKNOWN_PENALTY
            d2 += (dl / cfg.length_scale_mm) ** 2 if np.isfinite(dl) else 0.0
            cand.append(dict(ia=i, ib=int(j), obs_a=A.at[i, "observation_id"], obs_b=B.at[j, "observation_id"],
                             d_pos_raw_m=B.at[j, "axial_position_m"] - pa[i], offset_m=B_off[j],
                             d_pos_aligned_m=dx, d_clock_h=dc, d_length_mm=dl, cost=d2, distance=np.sqrt(d2)))
    C = pd.DataFrame(cand, columns=["ia", "ib", "obs_a", "obs_b", "d_pos_raw_m", "offset_m", "d_pos_aligned_m",
                                    "d_clock_h", "d_length_mm", "cost", "distance"])

    # ---------------- one-to-one assignment per connected component ----------------
    unmatched_cost = (cfg.pos_gate_m / cfg.pos_scale_m) ** 2
    assigned: dict[int, int] = {}
    if not C.empty:
        nA, nB = len(A), len(B)
        g = coo_matrix((np.ones(len(C)), (C["ia"].to_numpy(), nA + C["ib"].to_numpy())), shape=(nA + nB, nA + nB))
        _, labels = connected_components(g, directed=False)
        C["component"] = labels[C["ia"].to_numpy()]
        for _, comp in C.groupby("component"):
            ia_u = sorted(comp["ia"].unique())
            ib_u = sorted(comp["ib"].unique())
            m, n = len(ia_u), len(ib_u)
            BIG = 1e9
            M = np.full((m + n, n + m), BIG)
            M[m:, n:] = 0.0
            for k in range(m):
                M[k, n + k] = unmatched_cost
            for k in range(n):
                M[m + k, k] = unmatched_cost
            ri = {v: k for k, v in enumerate(ia_u)}
            rj = {v: k for k, v in enumerate(ib_u)}
            for r in comp.itertuples():
                M[ri[r.ia], rj[r.ib]] = r.cost
            rows, cols = linear_sum_assignment(M)
            for r, c in zip(rows, cols):
                if r < m and c < n and M[r, c] < BIG:
                    assigned[ia_u[r]] = ib_u[c]
    C["assigned"] = [assigned.get(a) == b for a, b in zip(C["ia"], C["ib"])] if not C.empty else []

    # ---------------- build tracks ----------------
    tracks = []
    used_b = set(assigned.values())
    for i, j in assigned.items():
        row = C[(C["ia"] == i) & (C["ib"] == j)].iloc[0]
        alts = C[((C["ia"] == i) & (C["ib"] != j)) | ((C["ib"] == j) & (C["ia"] != i))].sort_values("distance")
        best_alt = alts.iloc[0] if len(alts) else None
        margin = (best_alt["distance"] - row["distance"]) if best_alt is not None else np.inf
        ambiguous = bool(margin < cfg.ambiguity_margin)
        alt_txt = "; ".join(f"{a.obs_a}->{a.obs_b} (d={a.distance:.2f})" for a in alts.head(4).itertuples())
        tracks.append(dict(
            ia=i, ib=j, match_status="AMBIGUOUS" if ambiguous else "LIKELY_MATCH",
            obs_a=row["obs_a"], obs_b=row["obs_b"], distance=row["distance"],
            agreement=float(np.exp(-row["cost"] / 2.0)), margin=margin,
            d_pos_raw_m=row["d_pos_raw_m"], offset_m=row["offset_m"], d_pos_aligned_m=row["d_pos_aligned_m"],
            d_clock_h=row["d_clock_h"], d_length_mm=row["d_length_mm"],
            n_alternatives=len(alts), alternatives=alt_txt,
            rationale=_rationale(row, best_alt, margin, ambiguous, cfg)))
    for i in range(len(A)):
        if i in assigned:
            continue
        mine = C[C["ia"] == i].sort_values("distance")
        if len(mine):
            nb = mine.iloc[0]
            why = (f"Candidate(s) existed within the gate but the one-to-one assignment gave them to better-fitting "
                   f"records (closest: {nb.obs_b}, d={nb.distance:.2f}). Possibly missed by the later tool, "
                   f"repaired, below detection, or matched incorrectly - verify.")
        else:
            why = (f"No later-run record within {cfg.pos_gate_m} m (aligned) and {cfg.clock_gate_h} h. Possibly not "
                   f"detected by the later tool, repaired/recoated, or below the reporting threshold.")
        tracks.append(dict(ia=i, ib=None, match_status="UNMATCHED_EARLIER", obs_a=A.at[i, "observation_id"],
                           obs_b=None, n_alternatives=len(mine),
                           alternatives="; ".join(f"{a.obs_b} (d={a.distance:.2f})" for a in mine.head(4).itertuples()),
                           rationale=why))
    for j in range(len(B)):
        if j in used_b:
            continue
        mine = C[C["ib"] == j].sort_values("distance")
        if len(mine):
            why = (f"Earlier candidate(s) existed (closest: {mine.iloc[0].obs_a}, d={mine.iloc[0].distance:.2f}) "
                   f"but were assigned to better-fitting later records. Could be a new defect or a mis-assignment.")
        else:
            why = ("No earlier-run record within the matching gate. Possibly a newly initiated defect, a defect "
                   "previously below the reporting threshold, or a false call - verify.")
        tracks.append(dict(ia=None, ib=j, match_status="NEW_LATER", obs_a=None, obs_b=B.at[j, "observation_id"],
                           n_alternatives=len(mine),
                           alternatives="; ".join(f"{a.obs_a} (d={a.distance:.2f})" for a in mine.head(4).itertuples()),
                           rationale=why))
    excl = data[(in_a | in_b) & ~data["match_eligible"]]
    for _, r in excl.iterrows():
        is_a = r["run_id"] == run_a
        tracks.append(dict(ia=None, ib=None, match_status="EXCLUDED",
                           obs_a=r["observation_id"] if is_a else None,
                           obs_b=None if is_a else r["observation_id"],
                           excluded_run=r["run_id"], n_alternatives=0, alternatives="",
                           rationale=f"Excluded from matching: {r['exclusion_reason']}. Record retained and reported."))

    T = pd.DataFrame(tracks)
    # attach positions for ordering and display
    sub = data[in_a | in_b]
    pos_lookup = dict(zip(zip(sub["run_id"], sub["observation_id"]), sub["axial_position_m"]))
    seg_lookup = dict(zip(zip(sub["run_id"], sub["observation_id"]), sub["segment_id"]))

    def _sort_pos(a, b):
        if isinstance(a, str):
            return pos_lookup.get((run_a, a), np.nan)
        return pos_lookup.get((run_b, b), np.nan) - off_map.get(seg_lookup.get((run_b, b)), default_off)

    T["sort_pos"] = [_sort_pos(a, b) for a, b in zip(T["obs_a"], T["obs_b"])]
    T["sort_pos"] = T["sort_pos"].fillna(np.inf)
    T = T.sort_values(["sort_pos", "match_status"]).reset_index(drop=True)
    T.insert(0, "track_id", [f"T{k + 1:04d}" for k in range(len(T))])
    T["match_status_label"] = T["match_status"].map(MATCH_STATUSES)
    for col in ("distance", "agreement", "margin", "d_pos_raw_m", "offset_m", "d_pos_aligned_m", "d_clock_h",
                "d_length_mm", "excluded_run"):
        if col not in T.columns:
            T[col] = np.nan
    T = T.drop(columns=["ia", "ib"])

    if not C.empty:
        C = C.drop(columns=["ia", "ib"])
    return MatchResult(T, C, offsets, run_a, run_b, date_a, date_b)


def _rationale(row, best_alt, margin, ambiguous, cfg) -> str:
    parts = [f"Aligned axial difference {row['d_pos_aligned_m']:+.2f} m (raw {row['d_pos_raw_m']:+.2f} m, "
             f"odometer offset {row['offset_m']:+.2f} m)"]
    parts.append(f"clock difference {row['d_clock_h']:.2f} h" if np.isfinite(row["d_clock_h"])
                 else "clock unavailable (penalty applied)")
    if np.isfinite(row["d_length_mm"]):
        parts.append(f"length difference {row['d_length_mm']:+.0f} mm")
    txt = ", ".join(parts) + f". Normalised distance d={row['distance']:.2f} (gate {cfg.pos_gate_m / cfg.pos_scale_m:.1f})."
    if best_alt is None:
        txt += " No competing candidate within the gate."
    else:
        txt += (f" Closest competing candidate {best_alt['obs_a']}->{best_alt['obs_b']} at d={best_alt['distance']:.2f} "
                f"(margin {margin:.2f}{' < ' if ambiguous else ' >= '}{cfg.ambiguity_margin:.2f}).")
    if ambiguous:
        txt += " Treated as AMBIGUOUS: pairing is provisional and needs human verification."
    return txt
