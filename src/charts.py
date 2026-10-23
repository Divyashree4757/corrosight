"""Plotly figure builders. Every figure is drawn from AnalysisResult data (no sample data)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import theme as T

CAT_COLOURS = T.CAT_COLOURS
MATCH_COLOURS = T.MATCH_COLOURS


def _layout(fig: go.Figure, height=360, **kw) -> go.Figure:
    fig.update_layout(**T.plotly_layout(height), **kw)
    fig.update_xaxes(gridcolor=T.GRID, zeroline=False, linecolor=T.BORDER, tickfont=dict(color=T.TEXT_2),
                     title_font=dict(color=T.TEXT_2))
    fig.update_yaxes(gridcolor=T.GRID, zeroline=False, linecolor=T.BORDER, tickfont=dict(color=T.TEXT_2),
                     title_font=dict(color=T.TEXT_2))
    return fig


def category_bar(F: pd.DataFrame) -> go.Figure:
    order = list(CAT_COLOURS)
    counts = F["review_category"].value_counts().reindex(order).fillna(0).astype(int)
    fig = go.Figure(go.Bar(x=counts.values, y=counts.index, orientation="h", text=counts.values, textposition="outside",
                           cliponaxis=False,
                           marker_color=[CAT_COLOURS[c] for c in counts.index], hovertemplate="%{y}: %{x}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, max(1, counts.max()) * 1.15])
    return _layout(fig, 260, title="Review-priority distribution (findings)", showlegend=False)


def match_bar(F: pd.DataFrame) -> go.Figure:
    order = list(MATCH_COLOURS)
    counts = F["match_status_label"].value_counts().reindex(order).fillna(0).astype(int)
    fig = go.Figure(go.Bar(x=counts.index, y=counts.values, text=counts.values, textposition="outside",
                           cliponaxis=False,
                           marker_color=[MATCH_COLOURS[c] for c in counts.index], hovertemplate="%{x}: %{y}<extra></extra>"))
    fig.update_yaxes(range=[0, max(1, counts.max()) * 1.18])
    return _layout(fig, 260, title="Corrosion Memory Graph - match outcomes", showlegend=False)


def pipeline_strip(F: pd.DataFrame, length_m: float | None = None) -> go.Figure:
    """Findings along the line: x = axial position, y = clock position, colour = review category."""
    pos = F["pos_b"].where(F["pos_b"].notna(), F["pos_a"])
    clock = F["clock_b"].where(F["clock_b"].notna(), F["clock_a"])
    depth = F["latest_pct_wt"].fillna(10)
    fig = go.Figure()
    for cat, col in CAT_COLOURS.items():
        m = (F["review_category"] == cat) & pos.notna() & clock.between(0, 12)
        if not m.any():
            continue
        fig.add_trace(go.Scattergl(
            x=pos[m], y=clock[m], mode="markers", name=cat,
            marker=dict(color=col, size=np.clip(depth[m] / 3 + 4, 4, 22), line=dict(width=0.6, color=T.SURFACE),
                        opacity=0.9 if cat != "Routine review" else 0.45),
            customdata=np.stack([F.loc[m, "track_id"], F.loc[m, "match_status_label"],
                                 F.loc[m, "latest_pct_wt"].round(1).astype(str)], axis=1),
            hovertemplate="%{customdata[0]} | %{customdata[1]}<br>%{x:.1f} m, %{y:.1f} h<br>latest %{customdata[2]}% WT<extra></extra>"))
    if length_m:
        for s in np.arange(0, length_m + 1, length_m / 40 if length_m >= 400 else length_m):
            fig.add_vline(x=s, line_width=0.4, line_color="rgba(20,34,46,0.06)")
    fig.update_yaxes(title="clock (h)", range=[12.3, -0.3], tickvals=[0, 3, 6, 9, 12])
    fig.update_xaxes(title="axial position (m) - marker size ~ depth % WT")
    return _layout(fig, 380, title="Pipeline strip map - every finding, coloured by review category")


def memory_graph(F: pd.DataFrame, candidates: pd.DataFrame, x_range: tuple[float, float],
                 focus: str | None = None, run_a="earlier", run_b="later") -> go.Figure:
    """Two-lane graph: earlier observations (top), later observations (bottom), links = matching decisions."""
    lo, hi = x_range
    sub = F[(F["pos_a"].between(lo, hi)) | (F["pos_b"].between(lo, hi))]
    fig = go.Figure()
    pos_a = dict(zip(F["obs_a"], F["pos_a"]))
    pos_b = dict(zip(F["obs_b"], F["pos_b"]))
    # alternative candidate links (dotted)
    if candidates is not None and len(candidates):
        c = candidates[~candidates["assigned"]]
        c = c[c["obs_a"].map(pos_a).between(lo - 1, hi + 1)]
        xs, ys = [], []
        for r in c.itertuples():
            xs += [pos_a.get(r.obs_a), pos_b.get(r.obs_b), None]
            ys += [1, 0, None]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name="Competing candidate",
                                     line=dict(color="rgba(74,91,104,0.35)", width=1, dash="dot"), hoverinfo="skip"))
    for status, col, dash in (("Likely match", MATCH_COLOURS["Likely match"], "solid"),
                              ("Ambiguous match", MATCH_COLOURS["Ambiguous match"], "dash")):
        s = sub[sub["match_status_label"] == status]
        xs, ys = [], []
        for r in s.itertuples():
            xs += [r.pos_a, r.pos_b, None]
            ys += [1, 0, None]
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=status, line=dict(color=col, width=2, dash=dash),
                                     hoverinfo="skip"))
    lane_a = sub[sub["pos_a"].notna()]
    lane_b = sub[sub["pos_b"].notna()]
    fig.add_trace(go.Scatter(
        x=lane_a["pos_a"], y=np.ones(len(lane_a)), mode="markers", name=f"{run_a} observation",
        marker=dict(size=np.clip(lane_a["depth_a"].fillna(1) * 4 + 4, 9, 26), symbol="circle",
                    color=[MATCH_COLOURS[s] for s in lane_a["match_status_label"]], line=dict(width=1, color=T.TEXT)),
        customdata=np.stack([lane_a["track_id"], lane_a["obs_a"].astype(str), lane_a["depth_a"].round(2).astype(str),
                             lane_a["match_status_label"]], axis=1),
        hovertemplate="%{customdata[0]} | %{customdata[1]}<br>%{x:.2f} m, depth %{customdata[2]} mm<br>%{customdata[3]}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=lane_b["pos_b"], y=np.zeros(len(lane_b)), mode="markers", name=f"{run_b} observation",
        marker=dict(size=np.clip(lane_b["depth_b"].fillna(1) * 4 + 4, 9, 26), symbol="diamond",
                    color=[MATCH_COLOURS[s] for s in lane_b["match_status_label"]], line=dict(width=1, color=T.TEXT)),
        customdata=np.stack([lane_b["track_id"], lane_b["obs_b"].astype(str), lane_b["depth_b"].round(2).astype(str),
                             lane_b["match_status_label"]], axis=1),
        hovertemplate="%{customdata[0]} | %{customdata[1]}<br>%{x:.2f} m, depth %{customdata[2]} mm<br>%{customdata[3]}<extra></extra>"))
    if focus is not None and focus in set(sub["track_id"]):
        f = sub[sub["track_id"] == focus].iloc[0]
        pts = [(f["pos_a"], 1), (f["pos_b"], 0)]
        pts = [(x, y) for x, y in pts if pd.notna(x)]
        fig.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="markers", name=f"Selected {focus}",
                                 marker=dict(size=30, symbol="circle-open", color=T.TEAL, line=dict(width=2))))
    fig.update_yaxes(tickvals=[1, 0], ticktext=[run_a, run_b], range=[-0.35, 1.35])
    fig.update_xaxes(title="reported axial position (m); links drawn between reported positions", range=[lo, hi])
    return _layout(fig, 420, title="Corrosion Memory Graph - observation links across inspection runs")


def growth_chart(g: pd.Series, date_a: pd.Timestamp, date_b: pd.Timestamp, k: float, horizon: float,
                 threshold_pct: float) -> go.Figure:
    fig = go.Figure()
    xs, ys, errs, labels = [], [], [], []
    for obs, d, u, dt in ((g["obs_a"], g["depth_a"], g["u_a"], date_a), (g["obs_b"], g["depth_b"], g["u_b"], date_b)):
        if isinstance(obs, str) and pd.notna(d):
            xs.append(dt); ys.append(d); errs.append(k * u if pd.notna(u) else 0); labels.append(obs)
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers+text", name="OBSERVED depth (+/- k sigma)",
                             text=labels, textposition="top center",
                             marker=dict(size=11, color=T.TEXT, line=dict(width=1.5, color=T.TEAL)),
                             error_y=dict(type="data", array=errs, visible=True, color=T.TEXT_2, thickness=1.2)))
    end = date_b + pd.Timedelta(days=int(horizon * 365.25))
    has_up, has_c = pd.notna(g.get("proj_depth_upper_mm")), pd.notna(g.get("proj_depth_central_mm"))
    if has_up:
        base = g["proj_depth_central_mm"] if has_c else g["depth_b"]
        # shaded band = range between the central (or latest measured) value and the upper scenario
        fig.add_trace(go.Scatter(x=[date_b, end, end, date_b], y=[g["depth_b"], base, g["proj_depth_upper_mm"], g["depth_b"]],
                                 mode="lines", fill="toself", fillcolor=T.TEAL_TINT, line=dict(width=0), hoverinfo="skip",
                                 name="Scenario range (central to upper)"))
        fig.add_trace(go.Scatter(x=[date_b, end], y=[g["depth_b"], g["proj_depth_upper_mm"]], mode="lines",
                                 name="PREDICTED upper scenario", line=dict(color=T.AMBER, dash="dash", width=1.8)))
    if has_c:
        fig.add_trace(go.Scatter(x=[date_b, end], y=[g["depth_b"], g["proj_depth_central_mm"]], mode="lines",
                                 name="PREDICTED central (constant rate)", line=dict(color=T.TEAL_DARK, width=2.4)))
    if pd.notna(g.get("wt_mm")):
        thr = threshold_pct / 100 * g["wt_mm"]
        fig.add_hline(y=thr, line_color=T.CORAL, line_dash="dot",
                      annotation_text=f"demo screening threshold {threshold_pct:g}% WT = {thr:.2f} mm",
                      annotation_position="top left", annotation_font_color=T.CORAL)
    fig.update_yaxes(title="metal-loss depth (mm)", rangemode="tozero")
    return _layout(fig, 400, title="Observed depths and illustrative projection")


def rate_histogram(G: pd.DataFrame) -> go.Figure:
    g = G[(G["match_status"] == "LIKELY_MATCH") & G["rate_mm_per_yr"].notna()]
    fig = go.Figure()
    colours = T.CHANGE_COLOURS
    names = {"INCREASE_BEYOND_NOISE": "Increase beyond noise", "WITHIN_NOISE": "Within noise",
             "DECREASE_BEYOND_NOISE": "Decrease beyond noise", "UNCERTAINTY_UNKNOWN": "Uncertainty unknown"}
    for k, col in colours.items():
        s = g[g["change_class"] == k]["rate_mm_per_yr"]
        if len(s):
            fig.add_trace(go.Histogram(x=s, name=f"{names[k]} ({len(s)})", marker_color=col, xbins=dict(size=0.02),
                                       opacity=0.85))
    fig.add_vline(x=0, line_color=T.TEXT_2, line_width=1)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="annualised observed change (mm/yr) - likely matches")
    fig.update_yaxes(title="findings")
    return _layout(fig, 320, title="Observed rates: negative values kept, not clamped")


def shrinkage_scatter(G: pd.DataFrame) -> go.Figure:
    g = G[(G["match_status"] == "LIKELY_MATCH") & G["shrunk_rate_mm_per_yr"].notna()]
    fig = go.Figure(go.Scatter(x=g["rate_mm_per_yr"], y=g["shrunk_rate_mm_per_yr"], mode="markers",
                               marker=dict(color=T.TEAL, size=6, opacity=0.75), customdata=g["track_id"],
                               hovertemplate="%{customdata}<br>baseline %{x:.3f}<br>shrinkage %{y:.3f}<extra></extra>",
                               name="finding"))
    lo = float(min(g["rate_mm_per_yr"].min(), 0)) if len(g) else 0
    hi = float(g["rate_mm_per_yr"].max()) if len(g) else 1
    fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color=T.SLATE, dash="dot"), name="y = x"))
    fig.update_xaxes(title="baseline observed rate (mm/yr)")
    fig.update_yaxes(title="model B shrinkage rate (mm/yr)")
    return _layout(fig, 320, title="Model B pulls noisy two-point rates toward the population mean")


def missing_inputs_bar(counts: dict) -> go.Figure:
    if not counts:
        counts = {"(none)": 0}
    fig = go.Figure(go.Bar(x=list(counts.values()), y=list(counts.keys()), orientation="h", marker_color=T.TEAL, marker_line_color=T.TEAL, marker_line_width=1,
                           text=list(counts.values()), textposition="outside"))
    fig.update_yaxes(autorange="reversed")
    return _layout(fig, 220, title="Most common missing engineering inputs (findings)", showlegend=False)


# ---------------------------------------------------------------- figures for the extended feature pages
def health_heatmap(S: pd.DataFrame) -> go.Figure:
    """Segment x measure grid. Colour = value scaled within each row; hover shows the actual value."""
    rows = [("findings", "Findings", "{:.0f}"), ("review_first", "Review first", "{:.0f}"),
            ("max_latest_pct_wt", "Max latest depth % WT", "{:.1f}"), ("median_rate_likely", "Median rate mm/yr (likely)", "{:.3f}"),
            ("ambiguous", "Ambiguous matches", "{:.0f}"), ("flagged_records", "Flagged records", "{:.0f}"),
            ("anomaly_flags", "Anomaly flags", "{:.0f}"), ("evidence_gaps", "Evidence gaps", "{:.0f}")]
    rows = [r for r in rows if r[0] in S.columns]
    z, txt = [], []
    for col, _, f in rows:
        v = S[col].astype(float).to_numpy()
        rng = np.nanmax(v) - np.nanmin(v) if np.isfinite(v).any() else 0
        z.append(((v - np.nanmin(v)) / rng) if rng > 0 else np.zeros_like(v))
        txt.append([f.format(x) if np.isfinite(x) else "n/a" for x in v])
    fig = go.Figure(go.Heatmap(z=z, x=S["segment_id"], y=[r[1] for r in rows], text=txt, texttemplate="",
                               colorscale=[[0, T.SURFACE_2], [0.5, T.TEAL_DARK], [1, T.TEAL_LIGHT]], showscale=False,
                               xgap=2, ygap=2, hovertemplate="%{x} | %{y}: %{text}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    return _layout(fig, 360, title="Segment evidence and review load (colour scaled per row; hover for values)")


def pattern_scatter(E: pd.DataFrame, colour_by: str) -> go.Figure:
    pal = {"review_category": T.CAT_COLOURS, "match_status_label": T.MATCH_COLOURS}.get(colour_by)
    fig = go.Figure()
    for val, d in E.groupby(colour_by, observed=True, dropna=False):
        col = (pal or {}).get(val)
        fig.add_trace(go.Scattergl(x=d["position_m"], y=d["rate_mm_per_yr"], mode="markers", name=str(val),
                                   marker=dict(size=np.clip(d["latest_pct_wt"].fillna(10) / 3 + 4, 4, 20), color=col,
                                               opacity=0.8, line=dict(width=0.5, color=T.SURFACE)),
                                   customdata=np.stack([d["track_id"], d["segment_id"].astype(str)], axis=1),
                                   hovertemplate="%{customdata[0]} (%{customdata[1]})<br>%{x:.1f} m, %{y:.3f} mm/yr<extra></extra>"))
    fig.add_hline(y=0, line_color=T.TEXT_2, line_width=1)
    fig.update_xaxes(title="axial position (m)")
    fig.update_yaxes(title="observed annualised change (mm/yr)")
    return _layout(fig, 400, title="Observed change along the line (paired findings; marker size ~ depth % WT)")


def arena_bars(summary: pd.DataFrame) -> go.Figure:
    S = summary.sort_values("rmse")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=S["method_name"], y=S["mae"], name="MAE", marker_color=T.TEAL_DARK,
                         error_y=dict(type="data", array=S["mae_sd"], color=T.TEXT_2)))
    fig.add_trace(go.Bar(x=S["method_name"], y=S["rmse"], name="RMSE", marker_color=T.TEAL,
                         error_y=dict(type="data", array=S["rmse_sd"], color=T.TEXT_2)))
    fig.update_layout(barmode="group")
    fig.update_yaxes(title="rate error (mm/yr)")
    return _layout(fig, 360, title="Held-out error by method (mean over splits; bars = +/- 1 sd across splits)")


def strategy_bars(results: dict) -> go.Figure:
    names = [v["name"].split(":")[0] for v in results.values()]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=names, y=[v["review_first_covered"] for v in results.values()], name="'Review first' covered",
                         marker_color=T.CORAL))
    fig.add_trace(go.Bar(x=names, y=[v["uncertainty_covered"] for v in results.values()], name="Uncertainty score covered",
                         marker_color=T.AMBER))
    fig.add_trace(go.Bar(x=names, y=[v["ambiguous_remaining"] for v in results.values()], name="Ambiguous matches left",
                         marker_color=T.SLATE))
    fig.update_layout(barmode="group")
    return _layout(fig, 340, title="Hypothetical strategies compared (same budget and capacity)")


def pct_bars(df: pd.DataFrame, id_col: str, title: str) -> go.Figure:
    cols = [c for c in df.columns if c not in (id_col, "records")]
    fig = go.Figure()
    palette = [T.TEAL, T.BLUE, T.AMBER, T.VIOLET, T.CORAL, T.SLATE, T.TEAL_DARK, T.TEAL_LIGHT, T.TEXT_2, T.MUTED]
    for i, (_, r) in enumerate(df.iterrows()):
        fig.add_trace(go.Bar(x=cols, y=[r[c] for c in cols], name=str(r[id_col]), marker_color=palette[i % len(palette)]))
    fig.update_layout(barmode="group")
    fig.update_yaxes(title="% of records", range=[0, 105])
    return _layout(fig, 330, title=title)
