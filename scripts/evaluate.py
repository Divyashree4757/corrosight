"""Reproducible evaluation on the synthetic dataset.

Runs the full analysis WITHOUT ground truth, then scores it against data/synthetic_ground_truth.csv.
Also runs an ablation without odometer alignment to measure what alignment contributes.
Writes outputs/evaluation_report.json and prints a summary.

    python scripts/evaluate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import SourceInfo, attach_evaluation, run_analysis  # noqa: E402
from src.schema import AnalysisConfig  # noqa: E402
from src.synthetic_data import PIPELINE_LENGTH_M, write_demo_files  # noqa: E402
from src.validation import read_csv  # noqa: E402


def main():
    data = ROOT / "data"
    if not (data / "synthetic_inspections.csv").exists():
        write_demo_files(data)
    raw = read_csv(data / "synthetic_inspections.csv")
    gt = pd.read_csv(data / "synthetic_ground_truth.csv")
    src = SourceInfo("Demo dataset (synthetic)", ["synthetic_inspections.csv"], True, PIPELINE_LENGTH_M)

    report = {"note": "Synthetic data only. These metrics do not establish real-world accuracy."}
    for name, cfg in (("default", AnalysisConfig()), ("no_alignment", AnalysisConfig(align_runs=False))):
        res = attach_evaluation(run_analysis(raw, src, cfg), gt)
        report[name] = dict(summary=res.summary(), evaluation=res.evaluation)

    out = ROOT / "outputs" / "evaluation_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=float))

    for name in ("default", "no_alignment"):
        em = report[name]["evaluation"]["matching"]
        eg = report[name]["evaluation"]["growth"]
        mc = report[name]["summary"]["match_counts"]
        print(f"\n=== {name} ===")
        print(f"match counts: {mc}")
        print(f"true cross-run pairs: {em['true_pairs']}")
        print(f"likely precision {em['likely']['precision']:.3f} ({em['likely']['correct']}/{em['likely']['predicted_pairs']}), "
              f"ambiguous precision {em['ambiguous']['precision']:.3f} ({em['ambiguous']['correct']}/{em['ambiguous']['predicted_pairs']})")
        print(f"recall likely+ambiguous {em['recall_all_assigned']:.3f}, likely only {em['recall_likely_only']:.3f}, "
              f"false matches {em['all_assigned']['false_matches']}, missed pairs {em['missed_true_pairs']}")
        print(f"'new in later run' truly new: {em['new_later']['precision']:.3f} (n={em['new_later']['count']}); "
              f"'not found later' truly absent: {em['unmatched_earlier']['precision']:.3f} (n={em['unmatched_earlier']['count']})")
        if eg.get("n"):
            print(f"rate error on {eg['n']} correct likely pairs (mm/yr): baseline MAE {eg['baseline']['mae']:.4f} "
                  f"RMSE {eg['baseline']['rmse']:.4f}; shrinkage MAE {eg['shrinkage']['mae']:.4f} RMSE {eg['shrinkage']['rmse']:.4f}")
            print(f"{eg['k']:g}-sigma interval coverage: baseline {eg['baseline_interval_coverage']:.3f}, "
                  f"shrinkage {eg['shrinkage_interval_coverage']:.3f}")
    print(f"\nWritten: {out}")


if __name__ == "__main__":
    main()
