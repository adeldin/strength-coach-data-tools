# Expected answers for the synthetic squad

All names are made up. Codes change on every run of deidentify.py, so these are by name; the key file maps them.

## cmj_flags.py on cmj_season1.csv (ForceDecks layout, per test, inches) after `deidentify.py force_plate`
- Chosen week: 8
- Flagged in that week: Ivo Larsen (drop about 3.0 cm), Sven Quiroga (drop about 2.6 cm)
- Decoy, NOT flagged: Zane Zahra (drop 1.143 cm: past the SWC, short of k x TE)
- Not enough data: Dario Mbeki (tested in weeks 7 and 8 only)
- Reps = 2: Maya Pereira, week 6 (a note; trials are not in a per-test export)
- Duplicated test day: Lior Varga, week 7 (two rows; day excluded)
- Centimetres typed into the inches column: Joel Pereira, week 9 (excluded; day left out)
- Unreadable asymmetry value: Amara Larsen, week 5 (deidentify.py warning)
- Thresholds when the data were generated: TE 0.774 cm, SWC 1.079 cm, k x TE 1.162 cm

## cmj_flags.py on cmj_trials_season1.csv (per-trial layout, cm) after `deidentify.py force_plate_trials`
- Chosen week: 8; flagged: Ivo Larsen (3.0 cm), Sven Quiroga (2.6 cm)
- Decoy, NOT flagged: Zane Zahra (drop 1.13 cm)
- Not enough data: Dario Mbeki
- Only 2 trials: Maya Pereira, week 6
- Duplicated test day: Lior Varga, week 7 (trials 1,2,3,1,2,3; day excluded)
- Value in inches: Joel Pereira, week 9, trial 2 (excluded; day then has 2 trials)
- Thresholds when the data were generated: TE 0.782 cm, SWC 1.08 cm, k x TE 1.173 cm

## deidentify.py on season 1
- Conflicting heights: Dario Varga (184 and 192 cm) in gps_season1.csv
- Name variant pair: J. Okafor and Jamal Okafor in gps_season1.csv
- Ambiguous date: 09/10/2024 (the run stops if date_format is blank)
- Notes column naming a coach: Priya Raman in wellness_season1.csv (dropped by the default settings; warned about if kept)
- Unique goalkeeper: Sven Santos (athlete-level warning in gps and wellness; row-level warning for the week-6 injury)
- ForceDecks file: jump height converted from inches to cm, Additional Load from lb to kg, asymmetry columns split into number and side

## Season 2
- 8 players left, 8 joined (28.6% turnover). No planted problems.
