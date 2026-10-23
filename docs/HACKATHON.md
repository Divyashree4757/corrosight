# CorroSight: requirements, judging criteria and acceptance status

## 1. Official problem statement

No official GCEM Hacks 5.0 technical problem statement was supplied in the project files or the conversation.
The mapping below therefore uses **the team's own project brief and master build prompt** as the requirement source.
**Unverified:** any official requirement that differs from or adds to that brief. Re-check this table against the
official statement as soon as it is available.

## 2. Requirement → implementation → verification

| # | Requirement (from project brief) | Implemented in | Verified by |
|---|---|---|---|
| R1 | Reproducible synthetic dataset (~4.8 km, 400 joints, 40 segments, two runs 7 yr apart, realistic problems) | `src/synthetic_data.py` | `test_synthetic_data_is_reproducible_and_ground_truth_separate` |
| R2 | Ground truth kept separate, never used as input | `synthetic_ground_truth.csv`, read only in `src/evaluation.py` | same test; `attach_evaluation` runs after analysis |
| R3 | Demo mode (one click) and two-CSV upload with run ID and date entry | `app.py` sidebar | `test_every_page_renders_with_demo_data`, `test_upload_style_dataset_via_session_state` |
| R4 | Validation: missing columns/values, duplicates, invalid dimensions/WT/positions/types, units, suspicious changes, missing uncertainty | `src/validation.py`, `SUSPICIOUS_CHANGE` in `src/prediction.py` | `tests/test_validation.py`, `test_suspicious_change_flagged` |
| R5 | No silent modification or deletion; log exclusions | `ValidationResult.log`, flag columns | `test_source_data_never_modified`, duplicate tests |
| R6 | Matching with documented rules, scores, ambiguity, one-to-one, inspectable rationale | `src/matching.py` | `tests/test_matching.py` (11 tests) |
| R7 | Statuses: likely, ambiguous, unmatched earlier, new later (+ excluded) | `MATCH_STATUSES` | `test_unmatched_earlier_and_new_later_are_preserved`, ambiguity test |
| R8 | Observed change, annualised rate, hand-checkable | `src/prediction.py` | `test_hand_calculated_example_from_brief` (0.8 mm / 7 yr = 0.114) |
| R9 | Negative change kept and flagged | `classify_change` | `test_negative_change_is_preserved_not_clamped`, `test_large_decrease_is_anomalous_and_not_forecast` |
| R10 | Forecast only when supported; state when not | forecast decision in `compute_growth` | `test_unknown_uncertainty_...`, `test_ambiguous_match_is_not_forecast`, `test_new_detection_has_no_rate` |
| R11 | Documented uncertainty, no invented intervals | `src/uncertainty.py` | `test_uncertainty_helpers`, coverage metric in evaluation |
| R12 | Baseline first; ML/statistics only if evaluated | baseline + empirical-Bayes model B, compared in `evaluate_growth` | `test_shrinkage_*`, `scripts/evaluate.py` |
| R13 | Explainable review priorities; condition and evidence separated; missing data never lowers concern | `src/prioritization.py` | `tests/test_assessment_prioritization.py` (`test_missing_wall_thickness_never_lowers_concern` and others) |
| R14 | Engineering readiness instead of unverified strength calculation | `src/assessment.py` | readiness tests |
| R15 | Human review: proposed vs selected step, status, timestamp, persistence, no approvals | `src/review.py` | `test_review_decisions_flow_into_exports`, `test_review_store_has_no_approval_status`, UI flow test |
| R16 | PDF + CSV Evidence Passport from real results, consistent with dashboard | `src/reporting.py` | `tests/test_reporting.py` (6 tests) |
| R17 | Business-value calculator with assumptions labelled | `src/value_calculator.py` | `test_value_calculator_*` |
| R18 | Optional budget planner, verified on small cases | `src/optimization.py` | 150 brute-force comparisons, infeasibility test, UI test |
| R19 | Four connected Streamlit screens, dark industrial design, all controls functional | `app.py`, `src/charts.py`, `.streamlit/config.toml` | `tests/test_app.py` (11 headless UI tests), screenshots |
| R20 | README with exact commands, demo script, limitations | `README.md`, `docs/` | manual review |


## 2b. v1.0 feature requirements (master development prompt) → implementation → verification

| Requirement | Implemented in | Verified by | Status |
|---|---|---|---|
| Sidebar: clean grouped vertical list, icons, active highlight, no overlap/clipping | `app.py` (st.navigation, 5 groups, 19 pages), `src/theme.py` | Browser script: 19 items, 1 column, 0 overlaps, 0 clipped (dark + light); UI tests open all 19 pages | Implemented, Tested, Demonstrated |
| Dark cinematic design system (palette as specified) + light alternative | `src/theme.py`, `.streamlit/config.toml` | Screenshots `docs/screenshots/dark|light` | Implemented, Demonstrated |
| F1 Corrosion Event Timeline with provenance | `src/timeline.py`, `views.page_timeline` | `test_timeline_provenance_and_revisions`, browser flow | Implemented, Tested, Demonstrated |
| F2 Defect Identity Conflict Detector + reviewer resolution | `src/conflicts.py`, `views.page_identity` | `test_candidate_table_shows_competing_claims`, `test_resolution_does_not_change_matching`, UI test | Implemented, Tested, Demonstrated |
| F3 Measurement Anomaly Detective + separate corrections | `src/anomalies.py`, `views.page_anomalies` | `test_anomalies_*`, `test_correction_log_keeps_original`, browser flow | Implemented, Tested, Demonstrated |
| F4 Corrosion Pattern Explorer (documented clustering, associations) | `src/patterns.py`, `views.page_patterns` | `test_spatial_clusters_and_association` | Implemented, Tested |
| F5 Model Challenge Arena (group-wise split, 4 estimators) | `src/model_arena.py`, `views.page_arena` | `test_arena_group_split_is_leak_free_and_reproducible` | Implemented, Tested |
| F6 Contradiction Finder (rules K1-K8) | `src/contradictions.py`, `views.page_contradictions` | `test_contradiction_rules_*`, `test_reviewer_disagreement_*` | Implemented, Tested, Demonstrated |
| F7 Engineering Review Workbench (statuses, reason, assignee, reopen, history) | `src/review.py`, `views.page_workbench`, `ui_core.review_form` | `test_review_reopen_and_close_rules`, `test_workbench_close_requires_reason_and_reopen` | Implemented, Tested, Demonstrated |
| F8 Reproducible Analysis Snapshots (save, replay, compare) | `src/snapshots.py`, `views.page_snapshots` | `test_snapshot_replay_and_compare`, `test_snapshot_save_and_replay`, browser flow | Implemented, Tested, Demonstrated |
| F9 Evidence-Grounded Assistant (local, admits insufficient evidence) | `src/assistant.py`, `views.page_assistant` | `test_assistant_is_grounded`, UI test, screenshot | Implemented, Tested, Demonstrated |
| F10 Inspection Strategy Simulator (priority vs uncertainty vs balanced) | `src/strategy.py`, `views.page_strategy` | `test_strategy_respects_limits_and_differs` | Implemented, Tested |
| Extra pages from the suggested hierarchy: Health Map, What-If, Evidence Gap Finder, Data Trust Scorecard, Passport & Audit Trail | `views.py`, `src/gaps.py` | UI tests (all pages), `test_gaps_and_unlock` | Implemented, Tested |
| Integration: shared identifiers, cross-page buttons, timeline/passport include reviews, resolutions, corrections, snapshots | `ui_core` (shared derived evidence, `goto`), `src/reporting.py` extras | `test_passport_extras_consistent`, browser flow (8 checks) | Implemented, Tested, Demonstrated |
| Evidence Passport extended (snapshot id, contradictions, gaps, anomalies, resolutions, model evaluation) | `src/reporting.py` | `test_passport_extras_consistent`, downloaded PDF check | Implemented, Tested, Demonstrated |
| Existing functionality preserved | unchanged `src/` analytics; original pages in `ui_core.py` | the 220 pre-v1.0 tests still pass (UI tests adapted to the new navigation) | Tested |

## 2c. Sign-in and role-based access → implementation → verification

| Requirement | Implementation | Verified by |
|---|---|---|
| Dark sign-in page, show/hide password, errors, loading state, footer | `auth_ui.login_page`, `theme.login_css` | test_access_ui (masked input, messages); browser screenshots 1440 / 390 px |
| Four stakeholder roles with own dashboards and navigation | `src/rbac.py` ROLES / PAGE_ACCESS, `views.page_home` | test_each_role_gets_its_own_home_and_navigation; browser run of 5 accounts |
| Central, configurable permissions enforced on actions | `src/rbac.py`, `src/actions.py` (check, act, audit) | test_actions_enforce_permissions_and_audit, test_permissions_are_configurable, test_role_restrictions_are_enforced_in_the_ui |
| Admin separate from manager; create, role, activate/deactivate, profile, reset password | `is_admin` flag, `auth_ui.page_users`, `python -m src.auth` | test_admin_user_management, test_admin_page_only_for_admin_and_creates_user |
| Password handling | PBKDF2-HMAC-SHA256 with salt, constant-time compare, lockout, no enumeration | test_auth_rbac (5 tests) |
| Sessions: logout clears, no bypass, expiry, no cross-user leakage | `auth_ui.session_user`, `_reset_session`, page guard in `app._page` | test_sign_out_clears_session..., test_forbidden_page..., test_expired_session..., test_deactivated_account... |
| User-attributed audit events | `src/audit.py` | test_review_is_attributed_to_signed_in_user; audit assertions in backend tests |
| No public registration; no hardcoded credentials | accounts via CLI or admin page only; demo passwords random | code review; `python -m src.auth demo` |

## 3. Judging criteria → evidence

| Round / criterion | Marks | Where CorroSight shows it |
|---|---|---|
| R2 Problem understanding & solution design | 20 | Workflow strip; scope table separating growth / threshold scenario / remaining strength / failure probability; README "Methods" |
| R2 Innovation & technical approach | 20 | Corrosion Memory Graph with odometer alignment and ambiguity; OBSERVED/CALCULATED/PREDICTED/UNCERTAIN labelling in UI and CSV; two-axis Why-Inspect-First |
| R2 Feasibility & execution plan | 10 | Working prototype; modular `src/`; per-component matching; two tested dependency sets |
| R3 Functional implementation & problem alignment | 20 | End-to-end demo in one click; upload path; every control wired (UI tests) |
| R3 Technical depth & effectiveness | 20 | Hungarian assignment, robust alignment, error propagation, empirical-Bayes model, exact knapsack |
| R3 Progress, testing & validation | 10 | 260 tests; synthetic evaluation + alignment ablation (`outputs/evaluation_report.json`) |
| Final: complete working solution | 30 | All Priority-1 items implemented and tested (checklist below) |
| Final: real-world impact & scalability | 30 | Traceable passport, review log, CSV for downstream tools; component-wise matching; business calculator (hypothetical) |
| Final: technical excellence & validation | 20 | Measured precision/recall/MAE/RMSE/coverage; honest caveats; no invented metrics |
| Final: demo effectiveness & presentation | 20 | `docs/DEMO_SCRIPT.md`, backup screenshots, sample PDF/CSV |

## 4. Final acceptance checklist

Status key: **Implemented** (code exists), **Tested** (automated test passes), **Demonstrated** (run end-to-end in a
browser in this build: Streamlit server + headless Chromium screenshots), **Planned** (not done).

| Item | Status |
|---|---|
| Application launches from a clean environment | Tested on Linux in a fresh venv with pinned older dependencies (tests pass); server launched and health-checked. Windows commands documented but **not run on Windows**. |
| Demo data loads reproducibly | Tested (identical frames on regeneration) + Demonstrated |
| CSV uploads and validation work | Implemented; validation Tested; upload path Tested via session-state UI test. The browser file-picker itself was **not** exercised automatically. |
| Matching decisions are traceable | Tested + Demonstrated (rationale, candidate table) |
| Ambiguous and unmatched observations remain visible | Tested + Demonstrated |
| Growth calculations match hand-calculated examples | Tested |
| Forecast assumptions and limitations are visible | Tested + Demonstrated |
| Review priorities have supporting explanations | Tested + Demonstrated |
| Missing data does not silently reduce apparent concern | Tested |
| Engineering-readiness checks are transparent | Tested + Demonstrated |
| PDF and CSV downloads work | Tested (bytes generated, parsed); download buttons rendered in UI |
| Exported values match the displayed analysis | Tested (CSV ↔ dashboard table ↔ PDF text) |
| Automated tests run and results documented | Tested: 260 passed on two dependency sets (README) |
| Evaluation metrics calculated, not invented | Tested; `scripts/evaluate.py` output in README |
| Demo workflow works without source-code changes | Tested (UI tests) + Demonstrated |
| README includes exact run and test commands | Implemented |
| Three-minute demonstration prepared | Implemented (`docs/DEMO_SCRIPT.md`) |
| Incomplete or unverified features identified | Implemented (README "Known limitations", this file) |

## 5. Not implemented / unverified

- External LLM integration for the assistant (intentionally not connected; local rule-based assistant instead).
- Applying reviewer corrections or identity resolutions to a re-analysis (recorded only, by design).
- Windows run of v1.0 (tested on Linux only).
- Official problem-statement requirements (statement not available).
- Multi-run (3+) growth fitting; only pairwise comparison.
- Weld-based alignment, sizing-bias correction between tools.
- Any remaining-strength method (intentionally out of scope).
- Production identity (MFA, SSO / OIDC), encrypted storage, signed audit records, database storage. Local development-grade
  sign-in with hashed passwords, four roles, enforced permissions and a user-attributed audit log is implemented.
- Validation on real operator data.

## 6. Future improvements

1. Pilot with real ILI data from an operator; recalibrate matching scales and measure real precision/recall.
2. Girth-weld and reference-feature alignment; vendor-format importers (common ILI listing formats).
3. Multi-run hierarchical Bayesian growth model with tool-bias terms; calibration checks on real repeat runs.
4. Integration of an engineer-selected, independently verified remaining-strength method behind the readiness gate.
5. Role-based review workflow with a database, signatures and an immutable audit log.
6. Cost/benefit data from real maintenance records for the planner; a GIS map view.
