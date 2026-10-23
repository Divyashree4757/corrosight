"""CorroSight by CorroGuard AI — pipeline-corrosion evidence and review-prioritization prototype.

This package is a hackathon prototype. It is NOT a certified pipeline-integrity system.
"""

__version__ = "1.0.0-prototype"
APP_NAME = "CorroSight by CorroGuard AI"

# Version tags for each analytical component. Bump a tag whenever that component's behaviour changes, so
# Reproducible Analysis Snapshots can show which algorithm produced a stored result.
ALGORITHM_VERSIONS = {
    "validation": "1.1",
    "matching": "1.0 (segment-aligned gating + Hungarian one-to-one)",
    "growth_uncertainty": "1.0 (2-point rate, sqrt(u1^2+u2^2))",
    "shrinkage": "1.0 (normal-normal empirical Bayes, method of moments)",
    "prioritization": "1.0 (rules C1-C5, E1-E10)",
    "readiness": "1.0",
    "anomalies": "1.0",
    "contradictions": "1.0 (rules K1-K8)",
}
