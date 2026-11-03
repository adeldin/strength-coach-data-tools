# Expected answers for the synthetic squad

All names are made up. Codes change on every run of deidentify.py, so these are by name; the key file maps them.

Jump height varies by about 4% from day to day in every week, so ordinary days in other weeks can also be flagged.
Only week 8 is engineered; the lists below are for that week, followed by every flag in the season.

## cmj_flags.py on cmj_trials_season1.csv (per-trial layout, cm, the default) after `deidentify.py force_plate_trials`
- Chosen week: 8; flagged: Ivo Larsen (3.99 cm), Sven Quiroga (2.58 cm)
- Decoy, NOT flagged: Zane Zahra (drop 1.52 cm: past the SWC, short of k x TE)
- Not enough data: Dario Mbeki (tested in weeks 7 and 8 only)
- Only 2 trials: Maya Pereira, week 6
- Duplicated test day: Lior Varga, week 7 (trials 1,2,3,1,2,3; day excluded)
- Value in inches: Joel Pereira, week 9, trial 2 (excluded; day then has 2 trials)
- Thresholds when the data were generated: TE 1.452 cm, SWC 1.071 cm, k x TE 2.178 cm
- At k = 1.5 (the default): both planted athletes flag in week 8. At k = 2.0 (comparison only): only Ivo Larsen flags in week 8; Sven Quiroga's drop is short of k x TE.
- The decoy escapes in week 8 only. At k = 1.5 it flags from ordinary noise in: week 10, 3.42 cm.
- Season total at k = 1.5: 30 flags. Per week: week 5: 2, week 6: 3, week 7: 2, week 8: 2, week 9: 4, week 10: 6, week 11: 2, week 12: 5, week 13: 1, week 14: 3
- Season total at k = 2.0: 13 flags. Per week: week 6: 1, week 8: 1, week 9: 3, week 10: 3, week 11: 1, week 12: 1, week 13: 1, week 14: 2
- Every flag at k = 1.5: week 5 Lior Weber 2.38 cm; week 5 Maya Pereira 2.84 cm; week 6 Amara Okafor 3.83 cm; week 6 Oskar Oduya 2.63 cm; week 6 Tomas Okafor 2.62 cm; week 7 Ivo Larsen 2.59 cm; week 7 Quentin Ustinov 2.33 cm; week 8 Ivo Larsen 3.99 cm; week 8 Sven Quiroga 2.58 cm; week 9 Amara Castillo 3.18 cm; week 9 Amara Larsen 3.35 cm; week 9 Amara Okafor 3.13 cm; week 9 Sven Quiroga 2.28 cm; week 10 Amara Okafor 2.83 cm; week 10 Ines Oduya 3.02 cm; week 10 Pia Tanaka 2.97 cm; week 10 Sven Quiroga 2.45 cm; week 10 Yara Ustinov 2.43 cm; week 10 Zane Zahra 3.42 cm; week 11 Amara Larsen 2.28 cm; week 11 Amara Okafor 4.27 cm; week 12 Amara Larsen 3.12 cm; week 12 Jamal Okafor 2.23 cm; week 12 Joel Pereira 2.22 cm; week 12 Lior Varga 2.89 cm; week 12 Maya Pereira 2.71 cm; week 13 Esme Yilmaz 4.17 cm; week 14 Amara Castillo 2.78 cm; week 14 Ines Oduya 3.09 cm; week 14 Jamal Okafor 3.63 cm
- Every flag at k = 2.0: week 6 Amara Okafor 3.83 cm; week 8 Ivo Larsen 3.99 cm; week 9 Amara Castillo 3.18 cm; week 9 Amara Larsen 3.35 cm; week 9 Amara Okafor 3.13 cm; week 10 Ines Oduya 3.02 cm; week 10 Pia Tanaka 2.97 cm; week 10 Zane Zahra 3.42 cm; week 11 Amara Okafor 4.27 cm; week 12 Amara Larsen 3.12 cm; week 13 Esme Yilmaz 4.17 cm; week 14 Ines Oduya 3.09 cm; week 14 Jamal Okafor 3.63 cm

## cmj_flags.py on cmj_season1.csv (ForceDecks layout, per test, inches, the second option) after `deidentify.py force_plate`
- Chosen week: 8; flagged: Ivo Larsen (3.93 cm), Sven Quiroga (2.67 cm)
- Decoy, NOT flagged: Zane Zahra (drop 1.52 cm: past the SWC, short of k x TE)
- Not enough data: Dario Mbeki (tested in weeks 7 and 8 only)
- Reps = 2: Maya Pereira, week 6 (a note; trials are not in a per-test export)
- Duplicated test day: Lior Varga, week 7 (two rows; day excluded)
- Centimetres typed into the inches column: Joel Pereira, week 9 (excluded; day left out)
- Unreadable asymmetry value: Amara Larsen, week 5 (deidentify.py warning)
- Thresholds when the data were generated: TE 1.446 cm, SWC 1.071 cm, k x TE 2.169 cm
- At k = 1.5 (the default): both planted athletes flag in week 8. At k = 2.0 (comparison only): only Ivo Larsen flags in week 8; Sven Quiroga's drop is short of k x TE.
- The decoy escapes in week 8 only. At k = 1.5 it flags from ordinary noise in: week 10, 3.3 cm.
- Season total at k = 1.5: 28 flags. Per week: week 5: 2, week 6: 3, week 7: 2, week 8: 2, week 9: 3, week 10: 6, week 11: 1, week 12: 5, week 13: 1, week 14: 3
- Season total at k = 2.0: 12 flags. Per week: week 6: 1, week 8: 1, week 9: 3, week 10: 1, week 11: 1, week 12: 2, week 13: 1, week 14: 2
- Every flag at k = 1.5: week 5 Lior Weber 2.35 cm; week 5 Maya Pereira 2.73 cm; week 6 Amara Okafor 3.74 cm; week 6 Oskar Oduya 2.73 cm; week 6 Tomas Okafor 2.73 cm; week 7 Ivo Larsen 2.66 cm; week 7 Quentin Ustinov 2.22 cm; week 8 Ivo Larsen 3.93 cm; week 8 Sven Quiroga 2.67 cm; week 9 Amara Castillo 3.17 cm; week 9 Amara Larsen 3.43 cm; week 9 Amara Okafor 3.23 cm; week 10 Amara Okafor 2.73 cm; week 10 Ines Oduya 2.85 cm; week 10 Pia Tanaka 2.86 cm; week 10 Sven Quiroga 2.41 cm; week 10 Yara Ustinov 2.48 cm; week 10 Zane Zahra 3.3 cm; week 11 Amara Okafor 4.25 cm; week 12 Amara Larsen 3.17 cm; week 12 Joel Pereira 2.22 cm; week 12 Lior Varga 2.98 cm; week 12 Maya Pereira 2.73 cm; week 12 Tomas Okafor 2.23 cm; week 13 Esme Yilmaz 4.2 cm; week 14 Amara Castillo 2.67 cm; week 14 Ines Oduya 3.11 cm; week 14 Jamal Okafor 3.62 cm
- Every flag at k = 2.0: week 6 Amara Okafor 3.74 cm; week 8 Ivo Larsen 3.93 cm; week 9 Amara Castillo 3.17 cm; week 9 Amara Larsen 3.43 cm; week 9 Amara Okafor 3.23 cm; week 10 Zane Zahra 3.3 cm; week 11 Amara Okafor 4.25 cm; week 12 Amara Larsen 3.17 cm; week 12 Lior Varga 2.98 cm; week 13 Esme Yilmaz 4.2 cm; week 14 Ines Oduya 3.11 cm; week 14 Jamal Okafor 3.62 cm

## deidentify.py on season 1
- Conflicting heights: Dario Varga (184 and 192 cm) in gps_season1.csv
- Name variant pair: J. Okafor and Jamal Okafor in gps_season1.csv
- Ambiguous date: 09/10/2024 (the run stops if date_format is blank)
- Notes column naming a coach: Priya Raman in wellness_season1.csv (dropped by the default settings; warned about if kept)
- Unique goalkeeper: Sven Santos (athlete-level warning in gps and wellness; row-level warning for the week-6 injury)
- ForceDecks file: jump height converted from inches to cm, Additional Load from lb to kg, asymmetry columns split into number and side

## Season 2
- 8 players left, 8 joined (28.6% turnover). No planted problems.
