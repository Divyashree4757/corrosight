# CorroSight v1.0: three-minute demonstration script

Every step uses working features. Finding IDs come from the bundled demo dataset at default settings (seed 20261023);
if settings change, IDs and counts change with them. Backup screenshots are in `docs/screenshots/`,
and a sample report is in `outputs/sample_evidence_passport.pdf`.

**Before you start:** once, run `python -m src.auth demo` and keep the printed passwords. Then run `streamlit run app.py`,
open http://localhost:8502 and sign in as `engineer` (the demo records review decisions, which only the Pipeline
Integrity Engineer may do). Optionally delete `outputs/*.json` so the logs start empty.

*Optional 20-second role close:* sign out and sign in as `manager`. Home shows review progress and recent activity, the
Evidence Passport can be exported, but "Record review decision" is disabled with the reason shown. Viewing is
oversight, not approval.

---

### 0:00–0:25 · The problem
**Say:** "Two inspection runs, seven years apart, hundreds of corrosion records each. Positions drift, sizing differs,
records are missing or duplicated. Which records are the same defect, what changed, how sure are we, what should
engineers look at first, and can we prove how we got there?"

**Do:** Click **Load demo dataset**. Point at the grouped sidebar (Overview → Trust & evidence) and the workflow strip.

### 0:25–0:55 · Evidence, not just numbers
**Do:** Open **Pipeline Health Map** (segment heat map), then **Defect Identity Conflicts** (*Ambiguous* filter, first
row). **Say:** "Each candidate pairing is listed with reasons for and against. The reviewer can propose a different
resolution, but it's stored separately: the algorithm's result is never overwritten."

### 0:55–1:25 · CorroSight challenges itself
**Do:** Open **Contradiction Finder**. **Say:** "Here the evidence disagrees. This finding is 'Review first', yet its
depth sits within its own measurement uncertainty of the threshold. Both sides are shown, plus what would resolve it.
There is no single confidence score." Then open **Measurement Anomalies**: "Flags explain the observed value, the
rule, why it was flagged, and the evidence needed. A flag isn't a corrosion event, and originals are never changed."

### 1:25–1:55 · Honest prediction
**Do:** Open **Model Challenge Arena**. **Say:** "Four estimators on held-out synthetic defects, split by defect so
there's no leakage. Shrinkage cuts error from about 0.073 to 0.056 mm/yr, on synthetic data only. We show where each
method fails." Optionally open **What-If Analysis**, lower the depth threshold to 30% and run the scenario: "These
findings would change category."

### 1:55–2:30 · Human decision and traceability
**Do:** In **Contradiction Finder** click **Workbench** on the first card. The same finding opens. Fill **Reason**, set a
status, **Record review decision**. Open **Reproducible Analysis Snapshots** → **Save snapshot** → **Replay** →
*Exact replay verified*. Open **Corrosion Event Timeline**: the review and the snapshot appear as recorded events next
to the source observations.

### 2:30–3:00 · Ask and export
**Do:** **Evidence-Grounded Assistant** → *Why was T0177 prioritised?* (grounded answer with rules), then type *What is
the failure pressure?* ("insufficient evidence"). **Say:** "No language model and no external service. It answers only
from the analysis, and says so when it can't." Finish on **Evidence Passport & Audit Trail**: generate the PDF and
show the snapshot id, review and contradictions inside it, plus the audit trail. **Close:** "CorroSight connects
evidence, exposes uncertainty, challenges its own analysis, and leaves the decision with engineers."

---

**If something fails live:** use `docs/screenshots/*.png` and `outputs/sample_evidence_passport.pdf`.
