# CorroSight: second-round review script

Review: 23 October 2026, 9:00 PM, physical review by judges.
Criteria: Problem Understanding & Solution Design (20), Innovation & Technical Approach (20), Feasibility & Execution Plan (10).
Focus: the process of the project (problem, requirements, design, method, validation, plan). No live prototype demo.
Target: about 9–10 minutes, then questions. The same notes are in the PowerPoint's Presenter View.

Before you start: replace the four `[Member]` placeholders on slide 1 with your names.

---

## Slide 1: Title (about 20 seconds)

Good evening. We are [team name] and this is CorroSight by CorroGuard AI.
Pipeline operators inspect the same pipeline every few years. CorroSight connects those inspections, shows how sure we can be about every change, and explains which findings an engineer should look at first, and why.
Everything you will see runs on a fictional, synthetic pipeline. We built it that way on purpose, so we can check our answers against a known truth.

## Slide 2: Which defect is which, seven years later? (about 60 seconds) · criterion: Problem & Solution

Operators receive in-line inspection reports years apart: here 2016 and 2023 for the same pipeline. To know whether corrosion is growing you must first know which 2023 record is the same defect as which 2016 record. That is harder than it sounds, for four reasons, all taken from our dataset:
1. Positions drift. T0153 appears 0.47 m further along in 2023 purely because the tool's odometer drifted.
2. Identity is sometimes unclear. 29 pairings have a second candidate that fits almost as well.
3. Measurements are noisy. Tool uncertainty is 0.3 to 0.4 mm, so for 181 findings the change could simply be noise.
4. Data is incomplete: 20 errors and warnings, and 41 findings missing an engineering input.
Four kinds of people need the answer, and they ask the same question: what changed, how sure are we, and what should we look at first, and why. We are not claiming existing industry tools cannot do any of this; our focus is making the evidence and its uncertainty traceable.

## Slide 3: What each user needs, and the rules we set (about 60 seconds) · criterion: Problem & Solution

Before writing any code we asked who would use this and what each person needs.
The integrity engineer needs the evidence and the reason behind each finding, and a place to record a decision. The data analyst needs data problems and uncertain matches surfaced early. The planner needs to know which investigations cover the most uncertainty within a budget. The operator or manager needs progress, open issues and a traceable record.
From that we fixed five design principles that every later decision had to respect: never alter the source data; never guess a defect's identity; show uncertainty with every number and say what kind of number it is; give every priority a written reason; and let people decide while the system records. These principles are the backbone of the design.

## Slide 4: Solution design in four layers (about 60 seconds) · criterion: Problem & Solution

This is the solution design in four layers, left to right.
Input: two or more in-line inspection runs as CSV or Excel listings, plus pipe data such as wall thickness, grade and pressure.
The analysis engine, in the middle, is five explainable steps: validate the records; align the runs and match defects; calculate the observed change with its uncertainty; produce an illustrative forecast; and prioritise with named rules.
The decision workflow is where people come in: a review workbench, four roles with permission checks, and what-if and planning scenarios.
The evidence layer keeps the record: an Evidence Passport, reproducible snapshots and a user-attributed audit trail.
Running through every layer, each value carries its kind: observed, calculated, uncertain, predicted, or a human decision.

## Slide 5: How we built it: our project process (about 60 seconds) · criterion: Problem & Solution

This is how we worked, in six steps.
First we studied the domain: how in-line inspection reports record defects, and why comparing runs is hard. Then we defined requirements: the stakeholders' needs, the five principles, and just as important, what we would not claim, such as failure prediction or safety certification.
Third, we designed the data: a schema and a seeded synthetic pipeline with a hidden answer key, including realistic problems like drift, duplicates and missing values. That answer key is what lets us measure ourselves honestly.
Fourth, we built step by step: validation, matching, growth, prioritisation, each with its own tests before the next was built on top.
Fifth, we validated against the answer key and switched features off to prove their value.
Finally we added the decision layer: the review workflow, roles, audit trail, Evidence Passport and a 3D explanation.

## Slide 6: How it works, step by step (about 75 seconds) · criterion: Innovation & Technical

Eight steps, each deliberately simple and explainable.
Validation flags problems but never edits the data. Alignment estimates each segment's odometer offset from defects that clearly match. Matching uses position, clock and length, deliberately not depth, so growth cannot bias the match, and the Hungarian algorithm guarantees one-to-one pairs. When another candidate fits almost as well, we mark the pair ambiguous and refuse to forecast from it.
Change is compared against combined measurement uncertainty, square root of u1 squared plus u2 squared, at two sigma. Forecasts are constant-rate scenarios with an upper case; we also offer an empirical-Bayes shrinkage model. Prioritisation uses named rules, C for condition and E for evidence, so every category has a written reason.
On the right is one real finding, T0177, with every value labelled: observed, calculated, uncertain, predicted, and human decision, which is still empty because no engineer has reviewed it. We never mix these up.

## Slide 7: What makes the approach different (about 60 seconds) · criterion: Innovation & Technical

Six ideas make this approach different.
Uncertainty-first matching: when two pairings fit almost equally well we do not pick one silently; it stays provisional and visible.
A contradiction finder: instead of a single confidence score, the system lists where pieces of evidence disagree and what extra evidence would resolve each case.
Models that challenge themselves: several growth methods compete on held-out data, so the forecasting method is chosen on evidence, not preference.
Evidence labels on every value, an Evidence Passport that is reproducible from a snapshot, and a 3D pipeline twin that lets people who are not specialists follow the reasoning in space.

## Slide 8: How we prove it works (about 60 seconds) · criterion: Feasibility & Execution

How do we know it works? We built the test before trusting the tool.
We generate a synthetic pipeline with a hidden answer key: the true pairs and true growth rates. The analysis never sees it. Afterwards we compare: match precision and recall, growth-rate error, and whether the uncertainty intervals cover the truth. We also switch features off to measure what each adds; without odometer alignment, for example, false matches appear. And every rule has automated tests.
Early results on that synthetic data: every likely match correct, 241 of 243 true pairs recovered, and a growth-rate error of 0.042 mm per year with the shrinkage model.
To be clear, this is our own synthetic data, so it shows the method behaves as designed, not real-world accuracy. Real-data evaluation is phase 3 of our plan.

## Slide 9: Feasibility and execution plan (about 60 seconds) · criterion: Feasibility & Execution

Feasibility. On the left is the proof of concept already in place, running on an ordinary laptop: open-source Python, no paid service, and no data leaves the machine. It imports CSV files and has an importer for a public real-world inspection dataset. It has proper sign-in with hashed passwords, four roles with permissions enforced on the server, and an audit log, plus 280 automated tests.
On the right is our execution plan, and each phase has a check before we move on: stabilise, test on controlled data with known answers, evaluate on representative real data with expert-labelled pairs, get integrity engineers to review our rules, run a controlled pilot side by side with the current process, and only then address production security, governance and organisational approval.
We are explicit about the gaps: weld-based alignment, tool-bias correction and three-plus-run growth are next; remaining-strength calculation is out of scope by design. Real use needs engineering validation and approval.

## Slide 10: From Inspection Data to Traceable Engineering Decisions (about 30 seconds)

To close: CorroSight connects evidence across inspection runs, makes measurement uncertainty visible, explains why each finding is prioritised, supports rather than replaces human review, and keeps a traceable record.
In one sentence: CorroSight does not merely predict or prioritise. It connects inspection evidence, exposes uncertainty, challenges its own analysis and helps engineers make better-informed decisions.
Thank you. We are happy to take your questions.

---

## Likely judge questions

**Do you have a working system?** Yes, a working proof of concept implements this design end to end, with 280 automated tests. Today we are presenting the process and design; we can show it if you wish.

**Is this real pipeline data?** No. We used a seeded synthetic pipeline with a hidden answer key so we can measure ourselves. Evaluating on a public real in-line inspection dataset is phase 3.

**Do you predict failure or remaining life?** No. We show observed change and illustrative projections with their uncertainty. Remaining strength and failure pressure are out of scope by design and belong to validated engineering methods.

**Why not machine learning for matching?** Matching must be explainable and auditable. A normalised distance with one-to-one assignment gives a written reason for every pair, and ambiguity is flagged instead of hidden.

**What happens when a depth decreases?** We keep it, flag it if it exceeds measurement noise, and never force it to zero.

**What is the biggest risk?** Real data: odometer drift without weld references and sizing bias between inspection tools. That is why the plan goes controlled data, then expert-labelled real data, then a pilot.

**Why trust 1.000 precision?** On our own synthetic data it shows the method behaves as designed. It is not a claim of real-world accuracy, and the slide says so.

**Why Streamlit and ReportLab?** One Python codebase for analysis and interface, built and tested in hackathon time and running on a laptop; ReportLab writes the Evidence Passport PDF from the same analysis, so report and screen always agree. Production would put a full web framework and database in front of the same analysis code.
