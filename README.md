# CorroSight by CorroGuard AI

**Uncertainty-aware pipeline-corrosion comparison, explainable review priorities and a traceable Evidence Passport.**
Prototype built for GCEM Hacks 5.0.

> CorroSight is a hackathon prototype, **not** a certified pipeline-integrity system. It does not predict failures,
> certify safety, perform remaining-strength assessments, claim standards compliance or prescribe repairs.
> Every consequential decision stays with qualified engineers. The bundled dataset is **fictional and synthetic**.

**Central idea:** CorroSight does not merely predict or prioritise. It connects inspection evidence, exposes uncertainty,
challenges its own analysis and helps humans make better-informed engineering decisions.

CorroSight answers four questions about two in-line inspection (ILI) runs of the same pipeline:

1. **What changed?** Which records in the later run are the same physical defect as records in the earlier run (Corrosion Memory Graph), and how much did each one change?
2. **How reliable is that evidence?** Measurement noise, missing inputs, ambiguous matches and invalid records are shown, never hidden (Honest AI).
3. **What should be reviewed first, and why?** Transparent rules, with condition and evidence quality kept on separate axes (Why-Inspect-First).
4. **What was decided?** A human records a status and next step; the PDF/CSV Evidence Passport preserves evidence, analysis, assumptions and decisions (Evidence-to-Action loop).

```
Inspection CSVs → Validation → Matching → Growth & uncertainty → Forecast scenarios
               → Readiness check → Review priorities → Human review → Evidence Passport (PDF + CSV)
```

---

## Quick start

### Windows PowerShell
```powershell
cd corrosight
py -3.11 -m venv .venv            # Python 3.11 or newer
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m src.synthetic_data      # optional: data/ already contains the generated demo files
python -m src.auth demo           # first time only: creates 5 demo accounts, prints random passwords once
streamlit run app.py --server.port 8502   # opens http://localhost:8502 -> sign in
```

### macOS / Linux (bash)
```bash
cd corrosight
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.synthetic_data      # optional
python -m src.auth demo           # first time only: creates 5 demo accounts, prints random passwords once
streamlit run app.py              # sign in with one of the printed accounts
```

### Tests and evaluation
```bash
python -m pytest -q                # 280 tests: modules, features, exports, sign-in / roles, headless UI of all pages
python scripts/evaluate.py         # metrics vs synthetic ground truth -> outputs/evaluation_report.json
```

No API keys, paid services or network access are needed for the demo. The assistant runs locally (rule-based);
no inspection data is sent to any external service.

**Theme:** white workspace with a navy sidebar and teal accents (set in `.streamlit/config.toml`). Charts and custom
panels follow the active theme; the dark palette is kept in `src/theme.py` if you want to switch back.

---

## Navigation (v1.0)

The left sidebar is a grouped vertical list (Streamlit `st.navigation`), one page per row, each with an icon. The
active page is marked with a teal edge. Data controls (demo / upload, runs, settings) sit below the navigation.

| Group | Pages |
|---|---|
| **Overview** | Pipeline Overview · Pipeline Health Map |
| **Inspection intelligence** | Defect History · Corrosion Event Timeline · Defect Identity Conflicts · Measurement Anomalies · Corrosion Pattern Explorer |
| **Prediction & validation** | Forecast & Priorities · What-If Analysis · Model Challenge Arena · Contradiction Finder |
| **Planning & review** | Inspection Strategy Simulator · Engineering Review Workbench · Evidence Gap Finder · Evidence & Planning (human review, passport, business value, budget planner) |
| **Trust & evidence** | Data Trust Scorecard · Evidence-Grounded Assistant · Reproducible Analysis Snapshots · Evidence Passport & Audit Trail |

Pages share one analysis, so a finding shows identical values everywhere. Buttons such as *Review in workbench* or
*Event timeline* open the same finding on another page.

### What the new pages do

| Page | What it does | Integrity safeguards |
|---|---|---|
| Pipeline Health Map | Segment heat map of findings, review load, anomaly flags and evidence gaps | "Health" = evidence and workload, not structural integrity |
| Corrosion Event Timeline | Chronological events per finding: source observations, analysis results, logged reviews, resolutions, corrections, snapshots, exports | Every event labelled *Source record*, *Derived by analysis* or *Recorded log*; revisions only from saved snapshots |
| Defect Identity Conflicts | Proposed pairing, all competing candidates, Δaxial / Δclock / Δlength / offset, reasons for and against; reviewer resolution with rationale | Algorithm result never overwritten; distance is not a probability |
| Measurement Anomalies | Explainable flags (missing, invalid, unit-suspect, duplicate, decrease beyond noise, change ≫ uncertainty, rate outlier, length inconsistency, deep vs WT): observed value, rule, reason, severity, evidence needed, next step | Flags are not corrosion events; corrections are proposals stored separately, original kept |
| Corrosion Pattern Explorer | Filters, change-along-line chart, segment comparison, documented 1-D spatial clustering, Kruskal–Wallis association test | Labelled associations, not causes; no inferred soil / pressure data |
| What-If Analysis | Re-runs the analysis with other thresholds / forecast settings and lists findings that change category; depth ±kσ sensitivity | Current analysis unchanged unless you apply the scenario |
| Model Challenge Arena | B0 pooled mean, B1 baseline, B2 global shrinkage, B3 segment shrinkage on held-out synthetic defects (group-wise split by true defect, 25 seeds): MAE, RMSE, bias, coverage, error by true-rate group, strengths / failure modes | Synthetic only; no leakage; does not change prioritisation |
| Contradiction Finder | Rules K1–K8 (high condition on ambiguous match, large change with flagged records, threshold depends on assumed rate, priority within measurement uncertainty, depth decrease, deep new detection, reviewer disagreement, reviewer vs algorithm identity) with both sides of the evidence | No single confidence score |
| Inspection Strategy Simulator | Priority-first vs uncertainty-first vs balanced under a hypothetical budget, capacity and costs; documented uncertainty score | Hypothetical; no risk-reduction claim |
| Engineering Review Workbench | Queue, evidence tabs, statuses (Awaiting Review → Additional Evidence Required → Under Review → Reviewed → Closed with Documented Rationale), reason, assignee, reopen, history | Closing needs a rationale; closing ≠ repaired; append-only log |
| Evidence Gap Finder | Gaps per finding and the data requests that unblock most findings | Missing data never treated as "no concern" |
| Data Trust Scorecard | Completeness, validity and consistency percentages by run and segment | No composite score; bands are display conventions |
| Evidence-Grounded Assistant | Answers about priorities, matches, missing inputs, forecast assumptions, verification lists, methods, snapshots, segments, contradictions, anomalies; links to findings | Local rules only, no LLM; says when evidence is insufficient |
| Reproducible Analysis Snapshots | Saves data SHA-256, runs, full config, software / algorithm versions, git commit, findings digest, per-finding results, reviews; exact replay check; compare two snapshots | Append-only; replay requires the same data |
| Evidence Passport & Audit Trail | PDF / CSV passport (now with snapshot id, anomalies, contradictions, gaps, reviewer proposals, model evaluation) and a combined audit log | States it does not certify safety or compliance |

## Demo workflow (no files needed)

1. **Sidebar → Load demo dataset.** The fictional 4.8 km pipeline (400 joints, 40 segments) with runs R2016 and R2023 loads and is analysed.
2. **1 Pipeline Overview.** Workflow strip, KPI tiles, review-priority distribution, match outcomes and a strip map of every finding. Open the *Inspection data & validation* tab to see each data-quality issue, what it does to the analysis and what to do about it. Nothing is deleted.
3. **2 Defect History.** Choose a segment. The Corrosion Memory Graph links earlier (top) and later (bottom) observations: solid = likely match, dashed amber = ambiguous, dotted = competing candidates. Select a table row to open the source records, the match rationale and every candidate pair that was considered.
4. **3 Forecast & Priorities.**
   - *Why-Inspect-First:* filter and sort the list, select a finding to see its condition indicators and evidence-quality reasons, the proposed next step, and a review form.
   - *Forecast & Honest AI:* OBSERVED, CALCULATED, PREDICTED and UNCERTAIN cards, the depth/projection chart, the population of observed rates (negative values kept), and the model comparison against hidden synthetic ground truth.
   - *Engineering readiness:* what CorroSight does and does not do, and which engineering inputs are missing per finding.
5. **4 Evidence & Planning.**
   - Record a human review (status, reviewer-selected next step, name, notes). It is saved to `outputs/review_log.json`.
   - Generate and download the PDF Evidence Passport and the findings CSV.
   - Use the hypothetical business-value calculator and the optional budget planner.
6. **Sidebar → Analysis settings.** Change any demo threshold, matching gate, alignment or forecast method (baseline / shrinkage). Every screen and export recomputes.

## Uploading your own data

Sidebar → **Upload CSV files**. Either one CSV containing several runs, or one CSV per run. If a file has no `run_id` or `inspection_date` column, enter them in the file's panel; the assignment is logged in the report. Then click **Analyse uploaded data** and pick the two runs to compare.

| Column | Required | Unit | Meaning |
|---|---|---|---|
| run_id | yes* | text | Inspection-run identifier |
| inspection_date | yes* | YYYY-MM-DD | Run date |
| observation_id | yes | text | Anomaly ID within the run |
| segment_id | yes | text | Segment identifier |
| axial_position_m | yes | m | Reported odometer distance |
| clock_position_h | yes | h (0–12) | Circumferential position |
| depth_mm | yes | mm | Reported metal-loss depth |
| length_mm, width_mm | optional | mm | Anomaly dimensions |
| nominal_wt_mm | optional | mm | Nominal wall thickness (needed for % WT) |
| depth_uncertainty_mm | optional | mm, 1σ | Tool sizing uncertainty (needed for noise tests and intervals) |
| outer_diameter_mm, smys_mpa, maop_kpa | optional | mm, MPa, kPa | Only used by the readiness checker |
| pipeline_id, joint_id, feature_type | optional | text | Identification |

\* can be entered in the UI per file. `data/inspection_2016.csv` and `data/inspection_2023.csv` are ready-made example uploads.

## Real open dataset (optional)

CorroSight can import real, anonymised ILI data published under CC BY 4.0:

> Yarveisy et al. (2021). *Dataset for: Cross-country Pipeline Inspection Data Analysis and Testing of Probabilistic
> Degradation Models.* Mendeley Data V1. DOI [10.17632/c2h2jf5c54.1](https://doi.org/10.17632/c2h2jf5c54.1).
> External corrosion anomalies from four consecutive inline inspections (relative years 1, 3, 5, 7), one Excel file per run.

1. Download the dataset from https://data.mendeley.com/datasets/c2h2jf5c54 ("Download All") and unzip it.
2. Convert it:
   ```powershell
   python -m src.importers "C:\path\to\unzipped\folder" --out data\real_mendeley_ili.csv
   ```
   Optional: `--assume-sigma-frac-wt 0.078` adds an **assumed** 1-sigma depth uncertainty (fraction of wall
   thickness), because the dataset states none. Without it, CorroSight reports "uncertainty unknown" and makes no forecasts.
3. In the app: sidebar → Upload CSV files → `data/real_mendeley_ili.csv` → Analyse, then choose two runs (e.g. Y5 → Y7).

Mapping and caveats are documented in `src/importers.py`: dates are placeholders (elapsed years are correct),
segments are blocks of 10 girth welds, clock = degrees / 30. There is no ground truth, so no accuracy metrics are shown.
Cite the dataset when you present results from it.

## PDF and CSV exports

*Evidence Passport & Audit Trail* (or *Evidence & Planning → Evidence Passport*). The PDF contains: inspection evidence and dataset SHA-256, all validation issues, matching method and outcomes, growth and forecast method and assumptions, the prioritised list, per-finding evidence sheets (source records, calculations, uncertainty, limitations, readiness, review status), the review log, configuration, limitations and a reviewer sign-off block. In v1.0 it also includes the analysis snapshot id, measurement anomaly flags, contradictions,
evidence gaps, reviewer identity resolutions, proposed (not applied) corrections and the Model Challenge Arena table.
The CSV has one row per finding with column prefixes that keep evidence types apart: `OBSERVED_`, `CALCULATED_`, `UNCERTAINTY_`, `PREDICTED_`, `SCENARIO_`, `SYSTEM_` (proposed), `REVIEWER_` (human decision) and `ANALYSIS_` (cross-checks). Both are built from the same `findings_frame()` the dashboard displays; `tests/test_reporting.py` checks they agree.

Samples: `outputs/sample_evidence_passport.pdf`, `outputs/sample_findings.csv`.

---

## Architecture

```
app.py                     entry point: theme, logo, grouped st.navigation (19 pages), sidebar data controls
ui_core.py                 shared state / helpers, sidebar controls, original four pages, shared derived evidence
views.py                   the 15 extended pages (presentation only; logic lives in src/)
assets/                    CorroSight logo (SVG)
src/
  schema.py                columns, units, AnalysisConfig (all demo thresholds), limitations text
  synthetic_data.py        seeded generator: inspections + SEPARATE ground truth
  validation.py            schema/quality checks -> annotated copy + issue table + log (no deletions)
  matching.py              Corrosion Memory Graph: alignment, gating, Hungarian one-to-one, ambiguity
  uncertainty.py           measurement-noise propagation, change classes, empirical-Bayes shrinkage
  prediction.py            observed change, annualised rate, constant-rate scenarios, threshold timing
  assessment.py            engineering-readiness checker (no remaining-strength calculation)
  prioritization.py        Why-Inspect-First rules: condition axis + evidence axis -> category
  pipeline.py              orchestration -> AnalysisResult (single source for UI and exports)
  evaluation.py            post-hoc scoring against synthetic ground truth
  reporting.py             findings_frame(), CSV and PDF Evidence Passport
  review.py                append-only human-review log (JSON), keyed by dataset fingerprint
  optimization.py          optional budget planner: exact 0/1 knapsack
  value_calculator.py      hypothetical business-value calculator
  charts.py                Plotly figures built from analysis results (theme-aware)
  theme.py                 dark + light palettes, CSS, Plotly layout, logo
  logstore.py              append-only JSON logs (resolutions, corrections, snapshots, exports)
  anomalies.py             Measurement Anomaly Detective (+ correction proposals, never applied)
  conflicts.py             Defect Identity Conflict Detector (+ reviewer resolutions)
  contradictions.py        Contradiction Finder rules K1-K8
  patterns.py              segment summaries, 1-D spatial clustering, association tests
  model_arena.py           group-wise held-out comparison of four growth estimators
  strategy.py              Inspection Strategy Simulator and uncertainty score
  gaps.py                  Evidence Gap Finder and Data Trust Scorecard
  timeline.py              Corrosion Event Timeline with event provenance
  snapshots.py             Reproducible Analysis Snapshots: save, replay, compare
  assistant.py             local rule-based evidence-grounded assistant
scripts/evaluate.py        reproducible evaluation + alignment ablation
tests/                     pytest suite (incl. Streamlit AppTest UI tests)
data/                      synthetic_inspections.csv, synthetic_ground_truth.csv, per-run example uploads
outputs/                   generated PDFs, review_log.json, evaluation_report.json, samples
```

Scalability: matching is solved per connected component of the candidate graph, so cost grows with local defect density, not with the square of the pipeline's total record count. The demo (608 records) analyses in about 2 s.

## Methods

**Validation.** Required columns, identifiers, dates, numeric types, position range, clock range, missing/zero/negative depth, depth above wall thickness, unit-suspect depth (>50 mm), invalid wall thickness, run-level unit inconsistency, missing uncertainty, exact duplicates, duplicate IDs and near-duplicates (same run, ≤0.05 m, ≤0.25 h, ≤0.3 mm depth, ≤5 mm length). Each issue has an effect and an action. Records are only excluded from the calculation they would corrupt.

**Matching.** (1) Per-segment odometer offset from unambiguous mutual-nearest anchor pairs (median; pipeline median if fewer than 3 anchors). (2) Candidates within ±1.0 m aligned and ±1.0 h. (3) Cost d² = (Δx/0.25 m)² + (Δclock/0.4 h)² + (Δlength/20 mm)². Depth is deliberately not used, so growth cannot bias the match. (4) One-to-one minimum-cost assignment (Hungarian) with an explicit "leave unmatched" option. (5) *Ambiguous* if a competing candidate is within 1.0 of the assigned distance. The agreement index exp(−d²/2) is a similarity, not a probability.

**Growth.** D = later − earlier depth; R = D / Δt (Δt from dates / 365.25). σ_D = √(u₁² + u₂²) from stated 1σ tool uncertainties; changes are classed as beyond or within k·σ (k = 2). Negative changes are kept. No interval is produced when uncertainty is unknown.

**Forecast scenarios (illustrative).** Only for likely matches with valid depths and known uncertainty. Central constant-rate projection if the increase exceeds noise; otherwise only an upper screening scenario (rate + kσ). Anomalous decreases, ambiguous matches, new and unmatched findings get "a reliable forecast cannot be established". Optional *model B*: normal–normal empirical-Bayes shrinkage of per-defect rates toward the population mean (method of moments), evaluated against the baseline rather than assumed better.

**Review priority.** Condition rules C1–C5 and evidence rules E1–E10 are listed in `src/prioritization.py`. Category = the higher of the two axes, so missing or uncertain evidence can only raise a finding. All thresholds are configurable demo assumptions.

## Evaluation results (synthetic data only)

Produced by `python scripts/evaluate.py`. The ground-truth file is read only after the analysis. Synthetic noise matches the stated uncertainty by construction, so interval coverage is optimistic. **None of this establishes real-world accuracy.**

| Metric (default settings) | Value |
|---|---|
| True cross-run pairs | 243 |
| Likely-match precision | 1.000 (212/212) |
| Ambiguous-pair precision | 1.000 (29/29) |
| Recall, likely + ambiguous | 0.992 (2 pairs missed) |
| Recall, likely only (ambiguous held back) | 0.872 |
| "New in later run" truly absent earlier | 0.989 (n = 95) |
| "Not found in later run" truly absent later | 0.957 (n = 23) |
| Rate MAE / RMSE, baseline (mm/yr, n = 195) | 0.0573 / 0.0714 |
| Rate MAE / RMSE, shrinkage model B | 0.0418 / 0.0536 |
| 2σ interval coverage, baseline / model B | 0.969 / 0.954 |

Alignment ablation (`align_runs = False`): 6 false matches and 11 missed pairs (vs 0 and 2), ambiguous precision 0.891, "not found later" precision 0.808. Odometer alignment measurably reduces mismatches on this data.

## Sign-in, roles and user management

CorroSight opens on a sign-in page. There is **no self-registration**: accounts are created by an administrator,
either on the server with the command line or in the app (User management, administrators only).

**First-time setup** (run in the project folder, with the venv active):

```bash
python -m src.auth demo            # demo: engineer, analyst, planner, manager, admin (random passwords, shown once)
# or create real accounts one by one (you are prompted for the password; it is never echoed):
python -m src.auth add a.sharma --name "A. Sharma" --role engineer --admin
python -m src.auth list            # never shows passwords or hashes
python -m src.auth reset-password a.sharma        # temporary password; change forced at next sign-in
python -m src.auth set-role a.sharma planner      # also: activate / deactivate <username>
```

Accounts are stored in `instance/users.json` (override with `CORROSIGHT_USER_DB`). Only salted PBKDF2-HMAC-SHA256
hashes are stored (390,000 iterations), never the passwords. The `instance/` folder is excluded from git.

**Roles** (one per account). User administration is a separate flag, not a role; the manager role is not an administrator.

| Capability | Integrity Engineer | Data Analyst | Planner | Operator / Asset Integrity Manager |
|---|:-:|:-:|:-:|:-:|
| View overview, findings, evidence, audit; use the assistant; load the demo dataset | yes | yes | yes | yes |
| Upload new inspection data | yes | yes | - | - |
| Change analysis settings / apply a What-If scenario | yes | yes | - | - |
| Propose measurement corrections and identity resolutions | yes | yes | - | - |
| **Record or reopen an engineering review decision** | yes | - | - | - |
| Save analysis snapshots (replay / compare: all roles) | yes | yes | - | - |
| Run planning scenarios (strategy simulator, budget planner) | yes | - | yes | view defaults only |
| Export Evidence Passport and findings CSV | yes | yes | - | yes |
| Export planning summaries | yes | - | yes | yes |
| Create / edit / deactivate users, reset passwords | admin flag only | | | |

Pages are also filtered by role (for example, the analyst has no strategy simulator and the planner has no pattern
explorer). Defaults live in `src/rbac.py`; an organisation can override them with `instance/permissions.json`
(`{"capabilities": {...}, "pages": {...}}`). The **My account** page lists exactly what the signed-in role can do.
No role authorises repairs, operating changes or safety certification; recording or viewing a decision is not approval.

**How it is enforced.** Every protected action (review, reopen, corrections, resolutions, settings, uploads, snapshots,
planning, exports, user changes) goes through `src/actions.py`, which checks the permission on the server, performs
the action and only then writes a user-attributed audit event. Hidden or disabled buttons are a convenience, not the
control; denied attempts are refused and logged as `access_denied`. Export files are never sent to the browser of a
role that may not export. The reviewer name on decisions comes from the signed-in account, not a text box.

**Sessions.** The account is re-read on every interaction, so deactivation or a role change takes effect immediately.
Sessions end after 60 minutes without activity (`CORROSIGHT_SESSION_IDLE_MINUTES`). Sign-out and sign-in clear the
whole session (loaded data, selections, assistant chat, generated PDF), so nothing carries over to the next user.
Five failed attempts lock an account for 15 minutes; the error never says whether the username exists.

**Audit log.** `outputs/audit_log.json` (append-only): event id, UTC time, user id, username, role at the time, action,
resource, details, dataset fingerprint. It records sign-in, failed sign-in, sign-out and expiry, uploads, setting
changes, corrections, resolutions, reviews, reopens, snapshots, replays, comparisons, planning runs, exports, user and
role changes, password resets and denied actions. Passwords are never logged.

**Security status: development-grade.** This is local authentication suitable for a prototype or a trusted internal
demo, not a production identity system. Not included: multi-factor authentication, single sign-on, encryption of the
data files at rest, tamper-evident (signed) audit records, persistent sessions (a browser refresh signs the user out)
and rate limiting beyond the per-account lockout. For production: serve over HTTPS behind a reverse proxy, use an
identity provider (Streamlit's `st.login` with OIDC, or the proxy), keep users, reviews and audit events in a database
with access controls and backups, and have the security design reviewed.

## Test results

`python -m pytest -q` → **280 passed** (about 85 s on Streamlit 1.66, 48 s on Streamlit 1.50). Run on Python 3.13 with two dependency sets (see `requirements.txt`).

Sign-in and access tests (`tests/test_auth_rbac.py`, `tests/test_access_ui.py`, 20 tests): valid and invalid credentials
with identical messages, no plaintext password in the store or the audit log, password policy, lockout, inactive
accounts, forced password change, default and configurable permission matrix, server-side refusal and auditing of
protected actions for unauthorised roles, admin-only user management (manager is not admin), the sign-in page is the
only thing an unauthenticated session sees (also for deep links), each role's home dashboard and navigation, a
forbidden page cannot be opened by link, disabled controls and withheld export files per role, reviews attributed to
the signed-in account, sign-out clears the session and a second user starts clean, deactivation and idle expiry sign
the user out. All existing UI tests now sign in through the real form first.

Browser check of the sign-in system (headless Chromium): sign-in page at 1440 px and 390 px with no horizontal
overflow; a deep link while signed out shows only the sign-in page and opens the requested page after sign-in; a wrong
password shows the generic message; the five demo accounts each sign in, see their own home page and 18 to 21
navigation items (administrator: User management), and sign out back to the sign-in page.
Not run on Windows in this environment; the commands above are standard but untested there.

Browser verification (headless Chromium, both Dark and Light themes): all 19 sidebar pages opened by clicking, each
showed its title with no exception or error; the sidebar has 19 vertically stacked items, 0 overlaps and 0 clipped
labels at 1440 px. A scripted cross-feature run checked: Contradiction Finder → workbench keeps the finding; review
recorded with reason; snapshot saved and *exact replay verified*; timeline shows the review and snapshot as recorded
events; identity resolution recorded; downloaded PDF contains the snapshot id, reviewer, contradictions and the
resolution; correction proposal stored with the original preserved. The assistant answer and audit-trail table were
confirmed from screenshots (the audit table renders on a canvas, so its text could not be read automatically).

v1.0 feature tests (`tests/test_features.py`): anomaly explanations and no data modification, decrease / large-change
rules and config, correction log, candidate tables and competing claims, resolutions leave matching unchanged,
contradiction rules K1/K5/K7/K8, clustering and association, leak-free reproducible model arena, snapshot replay /
compare / no overwrite / mismatch detection, assistant grounding and refusals, strategy limits and ordering, evidence
gaps and unlock counts, timeline provenance and snapshot-based revisions, review close-requires-reason / reopen /
legacy statuses, passport extras consistent between dashboard, CSV and PDF. UI tests cover all 19 pages with demo
data, four new pages with uploaded data, workbench close + reopen, snapshot save + replay, assistant, identity resolution.

Coverage includes schema and quality checks, no source modification, duplicates, small position shifts, alignment, ambiguity, unmatched/new records, one-to-one assignment, clock wrap-around, hand-calculated growth (2.0 → 2.8 mm over 7 yr = 0.114 mm/yr), negative and anomalous changes, unknown uncertainty, threshold timing, shrinkage, readiness, priority explanations, "missing data never lowers concern", CSV ↔ dashboard ↔ PDF consistency, review persistence and isolation, no hardcoded demo values with uploaded data, knapsack vs brute force (150 random cases), the value calculator, and headless UI runs of every screen, settings change, review recording, PDF generation and the planner.

## Known limitations

- Two runs are compared at a time; a third run is selectable but multi-run growth fitting is not implemented.
- Matching uses positions, clock and length only. Real alignment would use girth welds and reference features (not in the schema).
- Uncertainty covers measurement noise only: no tool-to-tool bias, matching or model-form uncertainty.
- Constant-rate projections from two points are scenarios, not predictions. Thresholds are demo assumptions.
- No remaining-strength assessment (e.g. ASME B31G family) and no failure probability.
- Users, reviews and the audit log are local JSON files (hashed passwords; no encryption at rest or audit signing).
  Development-grade sign-in: no MFA or SSO, and a browser refresh ends the session. Use an identity provider and a database in production.
- Business-value, planner and strategy-simulator numbers are hypothetical.
- The assistant is a rule-based retriever for the listed question types, not a language model; unusual phrasing may
  get the "insufficient evidence" reply.
- Snapshots store configuration and compact results, not the raw data; replay needs the same dataset loaded.
- Proposed corrections and identity resolutions are recorded but deliberately not applied to the analysis. Entries
  written before sign-in existed keep their free-text reviewer name and have no user id.
- The Model Challenge Arena needs the synthetic ground truth, so it is available only for the demo dataset.
- AppTest cannot click st.navigation links for function-based pages; UI tests open pages via a session key, and real
  clicking is verified with the browser script.
- Evaluation is on synthetic data whose generator was written by the same team.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `streamlit` not recognised | Activate the venv, or run `python -m streamlit run app.py`. |
| PowerShell blocks `Activate.ps1` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again. |
| Port 8502 busy | `streamlit run app.py --server.port 8503` |
| Demo files missing | `python -m src.synthetic_data` (the app also regenerates them on demand). |
| Upload shows "Required column missing" | Rename your columns to the schema above, or add run_id / date in the UI. |
| Start again with reviews / logs | Delete `outputs/review_log.json` and the other `outputs/*.json` logs. |
| Sidebar looks narrow / labels cut | Widen the browser window; the sidebar is 352 px and can be collapsed with « |
| `pyarrow` / `dlopen` error on macOS Anaconda | Use a clean venv: `/opt/anaconda3/bin/python -m venv .venv && .venv/bin/python -m pip install -r requirements.txt && .venv/bin/python -m streamlit run app.py` |
| Old results after editing code | Streamlit menu → *Clear cache*, then rerun. |

`docs/` contains the demo script, the requirement and judging-criteria mapping, the acceptance checklist and screenshots.
