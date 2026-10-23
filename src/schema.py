"""Data schema, units and analysis configuration.

All lengths/positions are in metres (m) for axial position and millimetres (mm) for
defect dimensions and wall thickness. Clock position is in hours on a 12-hour clock
(0 <= h < 12; 12:00 is written as 0 or 12).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# --------------------------------------------------------------------------------------
# Column definitions
# --------------------------------------------------------------------------------------

REQUIRED_COLUMNS = [
    "run_id",
    "inspection_date",
    "observation_id",
    "segment_id",
    "axial_position_m",
    "clock_position_h",
    "depth_mm",
]

OPTIONAL_COLUMNS = [
    "pipeline_id",
    "joint_id",
    "length_mm",
    "width_mm",
    "nominal_wt_mm",
    "depth_uncertainty_mm",
    "outer_diameter_mm",
    "smys_mpa",
    "maop_kpa",
    "feature_type",
]

NUMERIC_COLUMNS = [
    "axial_position_m",
    "clock_position_h",
    "depth_mm",
    "length_mm",
    "width_mm",
    "nominal_wt_mm",
    "depth_uncertainty_mm",
    "outer_diameter_mm",
    "smys_mpa",
    "maop_kpa",
]

COLUMN_DOCS = {
    "pipeline_id": ("text", "Pipeline identifier", "identifier"),
    "run_id": ("text", "Inspection-run identifier", "identifier"),
    "inspection_date": ("YYYY-MM-DD", "Date of the inspection run", "recorded"),
    "observation_id": ("text", "Unique ID of the reported anomaly within the run", "identifier"),
    "segment_id": ("text", "Pipeline segment (S01..S40 in demo data)", "identifier"),
    "joint_id": ("text", "Pipe joint identifier (J0001..J0400 in demo data)", "identifier"),
    "axial_position_m": ("m", "Reported axial (odometer) distance from launcher", "measured"),
    "clock_position_h": ("h", "Circumferential clock position, 0-12 h", "measured"),
    "depth_mm": ("mm", "Reported metal-loss depth", "measured"),
    "length_mm": ("mm", "Reported axial length of the anomaly", "measured"),
    "width_mm": ("mm", "Reported circumferential width of the anomaly", "measured"),
    "nominal_wt_mm": ("mm", "Nominal (design) wall thickness at the anomaly", "design / assumed"),
    "depth_uncertainty_mm": ("mm", "Stated 1-sigma depth measurement uncertainty", "tool specification / assumed"),
    "outer_diameter_mm": ("mm", "Nominal outer diameter", "design"),
    "smys_mpa": ("MPa", "Specified minimum yield strength (pipe grade)", "design"),
    "maop_kpa": ("kPa", "Maximum allowable operating pressure", "operating"),
    "feature_type": ("text", "Anomaly classification reported by the vendor", "recorded"),
}

MATCH_STATUSES = {
    "LIKELY_MATCH": "Likely match",
    "AMBIGUOUS": "Ambiguous match",
    "UNMATCHED_EARLIER": "Not found in later run",
    "NEW_LATER": "New in later run",
    "EXCLUDED": "Excluded from matching",
}


@dataclass(frozen=True)
class AnalysisConfig:
    """User-adjustable analysis settings.

    Every threshold below is an ILLUSTRATIVE DEMO ASSUMPTION, not an industry standard
    or a validated engineering limit. They exist so that the review rules are explicit
    and can be changed by a qualified user.
    """

    # --- matching (spatial gates and scale factors) ---
    pos_gate_m: float = 1.0          # max |aligned axial difference| to be a candidate
    clock_gate_h: float = 1.0        # max circular clock difference to be a candidate
    pos_scale_m: float = 0.25        # scale used to normalise axial differences in the cost
    clock_scale_h: float = 0.40      # scale used to normalise clock differences in the cost
    length_scale_mm: float = 20.0    # scale used for (optional) length agreement in the cost
    ambiguity_margin: float = 1.0    # if an alternative candidate's cost is within this margin -> ambiguous
    align_runs: bool = True          # estimate a per-segment odometer offset before matching

    # --- validation ---
    near_duplicate_pos_m: float = 0.05
    near_duplicate_clock_h: float = 0.25
    near_duplicate_depth_mm: float = 0.30
    near_duplicate_length_mm: float = 5.0
    suspicious_rate_mm_per_yr: float = 0.60  # |annualised change| above this is flagged as suspicious

    # --- review rules (demo assumptions) ---
    depth_review_pct_wt: float = 40.0        # latest depth >= this % of nominal WT -> condition trigger
    rate_review_mm_per_yr: float = 0.20      # growth beyond noise AND rate >= this -> condition trigger
    screening_threshold_pct_wt: float = 50.0  # projection threshold used for "time to screening threshold"
    forecast_horizon_years: float = 5.0      # projection horizon after the later inspection
    noise_k: float = 2.0                      # k in "change exceeds k * combined sigma"

    # --- forecasting ---
    forecast_method: str = "baseline"  # "baseline" (per-defect observed rate) or "shrinkage" (empirical Bayes)

    def to_dict(self) -> dict:
        return asdict(self)


DEMO_ASSUMPTION_NOTE = (
    "Thresholds are illustrative demo assumptions chosen to make the review rules explicit. "
    "They are not industry standards, code limits or validated engineering criteria."
)

LIMITATIONS = [
    "CorroSight is a hackathon prototype, not a certified pipeline-integrity system.",
    "Review priorities are rule-based recommendations for further human review, not risk "
    "classifications, failure probabilities or repair decisions.",
    "No remaining-strength (e.g. ASME B31G family) assessment is performed. The readiness "
    "checker only reports which inputs are available or missing.",
    "Growth estimates from two inspections cannot establish a long-term trend; constant-rate "
    "projections are illustrative scenarios, not predictions of future corrosion.",
    "Uncertainty intervals include only stated depth measurement uncertainty (assumed 1-sigma, "
    "independent, unbiased, Gaussian). Matching, sizing-bias and model-form uncertainty are not included.",
    "Time to a screening threshold is not a repair deadline.",
    "Demo results come from a synthetic, fictional dataset and do not demonstrate real-world accuracy.",
    "All consequential decisions require review and approval by qualified engineers. The application "
    "never approves repairs, work orders or changes to operating conditions.",
]
