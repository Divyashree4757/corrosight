CorroSight test files from REAL public in-line inspection (ILI) data
=====================================================================

Source (cite when presenting):
  Yarveisy, R. et al. (2021). Dataset for: Cross-country Pipeline Inspection Data Analysis and
  Testing of Probabilistic Degradation Models. Mendeley Data, V1. DOI 10.17632/c2h2jf5c54.1
  https://data.mendeley.com/datasets/c2h2jf5c54  (licence: CC BY 4.0, check the page)

  Real, anonymised external-corrosion features from four inspections of one ~260 km pipeline
  at relative years 1, 3, 5 and 7 (3,198,420 features in total).

Files
  real_ILI_section_GW5000-5049.csv   RECOMMENDED for testing and demos
      10,280 rows, 1.1 MB, girth welds 5000-5049 (about 0.6 km), all four runs.
      Analysis of Y5 -> Y7 takes about 20 seconds.
  real_ILI_large_GW5000-7714.csv     the near-50 MB file
      451,870 rows, 48.6 MB, girth welds 5000-7714 (about 35 km), all four runs.
      Within the 50 MB upload limit, but one analysis is expected to take 15-20 minutes
      and every settings change re-runs it. Not suitable for a live demo.

How the files were made (values copied, not altered)
  - Each Excel run file was read and mapped with CorroSight's importer (src/importers.py):
    run_id Y1/Y3/Y5/Y7; joint_id = girth weld number; segment = blocks of 10 girth welds;
    clock_position_h = start angle (deg) / 30; depth = MD.mm; length = L.mm; width = W.mm;
    nominal wall thickness = WT.mm (7.1 mm).
  - axial_position_m = position of the feature's upstream girth weld (median odometer position
    of that weld in the Year 7 run) + the feature's distance from that weld (RD.m).
    This weld-referenced position removes most odometer drift between runs. With raw odometer
    positions only ~4% of features matched; with weld referencing about half match "likely".
  - inspection_date values are placeholders (2000-01-01 + relative year); elapsed years are real.
  - depth_uncertainty_mm is EMPTY because the source states no tool sizing uncertainty.
    CorroSight therefore reports "uncertainty unknown" / "Additional data needed" and makes no
    forecasts. That is the correct, honest behaviour for this data.
  - There is no answer key for real data, so no accuracy figures can be shown.

How to test
  Sidebar -> Upload CSV files -> select one file -> Analyse uploaded data.
  The app compares the last two runs (Y5 -> Y7, 2 years) by default; any pair can be chosen.

Expected (recommended file, Y5 -> Y7, default settings):
  matching: 1,130 likely, 925 ambiguous, 165 not found later, 357 new later
  priorities: 1,130 additional data needed, 926 verify match / data, 518 routine, 2 monitor, 1 review first
