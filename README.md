# strength-coach-data-tools

Two small, tested Python scripts for strength and conditioning coaches who work with athlete
monitoring exports (GPS, force plate, wellness) and do not have a data scientist on staff.

- **deidentify.py** turns an export into **coded data** before it leaves your computer: it keeps only the
  columns you list, replaces names with random codes, turns dates into training weeks, bands body size,
  groups positions, and tells you in plain English where an athlete could still be picked out.
- **cmj_flags.py** flags meaningful drops in countermovement jump (CMJ) height using a baseline, the
  squad's typical error (TE) and the smallest worthwhile change (SWC).

They accompany the article *Artificial Intelligence for the Strength Coach Without a Data Scientist*
(Strength and Conditioning Journal; citation and link to be added on publication).

**Three things to know before you start**

1. The de-identification script **reduces** re-identification risk. It does **not** make data anonymous.
   Someone who knows your squad may still recognise the only goalkeeper, the tallest athlete, or the
   player who was injured in week 6. Read the report it writes and act on the warnings.
2. **Your institution's compliance office has the final say** on what may be shared or uploaded anywhere,
   including to an AI tool. These scripts do not change that.
3. Every number in `cmj_flags.py` (baseline length, k, the SWC multiplier, the plausible range) is an
   **adjustable choice, not a rule**. The defaults are the ones described in the article.

Both scripts use only Python itself: nothing to install beyond Python, no network calls, and your input
files are never changed.

---

## 1. Install Python (once)

You need Python 3.10 or newer.

**Windows**

1. Go to <https://www.python.org/downloads/> and click the yellow download button.
2. Run the installer. On the first screen **tick "Add python.exe to PATH"**, then click *Install Now*.
3. Open the Start menu, type `PowerShell`, open it, and type `python --version`. You should see
   `Python 3.1x.x`. If you see a Microsoft Store window instead, close it, restart the computer and try
   again, or reinstall with the PATH box ticked.

**Mac**

1. Go to <https://www.python.org/downloads/> and click the yellow download button (macOS).
2. Open the downloaded `.pkg` and click through the installer.
3. **Close any Terminal window you already have open**, then open a new one (Applications, Utilities,
   Terminal). A window that was open before the install keeps using the old Python.
4. Type `python3 --version`. You should see `Python 3.10` or a higher number, such as `Python 3.13.1`.

Many Macs already have an older Python (3.9) from Apple, so seeing `Python 3.9.6` means the new one is not
being used yet. Open a new Terminal window and check again. If it still says 3.9, run the installer again.
The scripts check this too: on an older Python they stop and tell you.

On a Mac, every command below is typed with `python3` instead of `python`.

## 2. Download the scripts

1. On the repository page, click the green **Code** button, then **Download ZIP**.
2. Unzip it. You will have a folder called `strength-coach-data-tools`. Put it somewhere easy to find,
   such as your Documents folder.
3. Open a terminal **in that folder**:
   - Windows: open the folder in File Explorer, click in the address bar, type `powershell` and press Enter.
   - Mac: open Terminal, type `cd ` (with a space), drag the folder onto the Terminal window, press Enter.

## 3. Run the synthetic squad first

The folder `synthetic_data/` holds a made-up 28-player soccer squad across two seasons, with problems
planted in it on purpose. Run everything on it once, so you know what good output looks like before you
touch your own data.

```
python deidentify.py gps
python deidentify.py force_plate_trials
python deidentify.py force_plate
python deidentify.py wellness
python cmj_flags.py
```

Then open `expected_output/expected_answers.md` and compare. You should see, among other things:

- the pair `J. Okafor` / `Jamal Okafor` reported as a likely name variant;
- one athlete reported with two heights 8 cm apart;
- the goalkeeper reported as a group of one, and the goalkeeper's week-6 injury as a row-level warning;
- in `cmj_flags.py`: exactly **two** athletes flagged in week 8, a third who drops past the SWC but is
  correctly **not** flagged, one athlete with "not enough data", a day with only 2 trials, a duplicated
  test day excluded, and one value excluded because it was typed in inches;
- in the ForceDecks file: jump height converted from inches to cm, "Additional Load" from lb to kg,
  asymmetry values like `6.3 L` split into a number and a side, and one unreadable asymmetry value warned about.

The made-up jumps vary by about 4% from day to day in every week, so you will also see flags in other weeks:
30 in the season. Only week 8 was built by hand. The worked example in section 5 walks through it.

`cmj_trials_season1.csv` is an example of a per-trial export (one row per jump, in cm), and `cmj_flags.py` reads
it by default. `cmj_season1.csv` uses the real VALD ForceDecks export layout (one row per test, jump height in
inches). To run the jump script on that file, see "Two kinds of export" in section 5.

Codes are random, so your codes will differ from anyone else's. To see which code belongs to which
made-up name, open `KEY_DO_NOT_SHARE/athlete_key.csv`.

To regenerate the synthetic files from scratch: `python make_synthetic_squad.py` (same files every time).

## 4. Point the scripts at your own export

Open `deidentify.py` in any text editor (Notepad, TextEdit in plain-text mode, or VS Code). Everything you
need to change is in the **SETTINGS** block at the top; you do not need to read past it.

1. **Season start date**: `"season_start_date": "2024-08-05"` (year-month-day). Week 1 starts here.
2. **Pick a profile** (`gps`, `force_plate_trials`, `force_plate` or `wellness`) and set:
   - `input_file`: the path to your export, saved as CSV (in Excel: *File, Save As, CSV UTF-8*).
   - `athlete_id_column`: the heading of the column that holds the athlete's name or ID.
   - `keep_columns`: the headings you want in the shared file, **spelled exactly as the export spells
     them** (spaces at the start or end do not matter). Anything not listed is dropped. Start with fewer
     columns than you think you need.
   - **Units** are read from the brackets at the end of each heading: `[in]` or `(in)` is converted to cm,
     `[lb]` to kg, and the heading is renamed to match. The body-mass and height columns must carry a unit;
     if yours do not, add one to the heading in the file (for example `Body Mass [kg]`), or the script stops
     and tells you.
   - **Asymmetry columns** exported as text with a side letter (`6.3 L`) are split into a number and a
     `... side` column. Columns with `(Asym)` in the heading are found automatically; list others in
     `asymmetry_columns`. Values that cannot be read are left blank and counted in the report.
   - `date_columns` and `date_format`: how dates look in your file. `"%m/%d/%Y"` is `08/05/2024`,
     `"%d/%m/%Y"` is `05/08/2024`, `"%Y-%m-%d"` is `2024-08-05`. If you leave the format blank and any date
     could be read two ways, the script stops and tells you.
   - `position_column`, `class_year_column`, `height_column`, `body_mass_column`: set to `""` if your
     export does not have them.
   - `event_columns`: columns that record an injury, illness or similar event.
3. **Position groups**: edit `position_groups` so your export's position labels map to broader groups.
4. **Key folder**: `KEY_DO_NOT_SHARE` by default. Keep it off shared drives, out of cloud sync, and out of
   every AI tool. It is the only thing that links codes back to names. Use the **same key folder** for all
   your exports so an athlete keeps one code everywhere.
5. Run `python deidentify.py gps` (or the profile you edited). Read the report: it is printed on screen
   and saved as `coded_output/deidentify_report_<file>.txt`.

The `force_plate` profile uses the **real heading row of a VALD ForceDecks CMJ export** (per test). The `gps`,
`force_plate_trials` and `wellness` profiles are **examples in the style of common systems**, not a specific
vendor's layout. All four match the synthetic files. Replace them with your own headings.

### Reading the de-identification report

- **COLUMNS**: what was kept and dropped. If a dropped column surprises you, add it to `keep_columns`.
- **ATHLETE CODES**: how many athletes, how many reused a code from the key, and any pairs of IDs that look
  like one person written two ways. The script never merges them itself; add them to `id_aliases` if they
  are the same person.
- **ID CONFLICTS**: one code recorded with two heights (or two positions, or two class years). Two people
  may share a name, or a value was mistyped.
- **UNIQUENESS CHECK**: (a) athletes who are alone, or in a group smaller than `minimum_group_size`, on
  position group + class year + body-mass band + height band; (b) rows where week + position + event
  point to fewer than that many athletes. Each comes with a suggestion for a coarser grouping. Counts are
  **different athletes**, not rows, because one athlete with 30 sessions is still one athlete.
- **VERIFICATION**: the script re-reads its own output and stops (deleting the output) if any original name
  or ID is still in it. It also warns about values that look like a person's name in any kept column.

If a warning remains that you cannot fix by dropping or coarsening a column, do not share the file.

## 5. Run the jump monitoring script

Open `cmj_flags.py` and check the SETTINGS block. The defaults read a per-trial file, the coded file from the
`force_plate_trials` profile: `coded_output/coded_cmj_trials_season1.csv`. Change `input_file` to your coded file
and the column names to match. Column names are matched without their
unit and without end spaces, so `Jump Height (Imp-Mom)` finds both the inches heading in a raw export and
the cm heading in a coded one. The unit itself is read from the file, and inches are converted to cm.

**Two kinds of export.** A **per-trial** export has one row per jump with a trial number
(`trial_column`, for example `"Trial"`). This is the default, and the better choice: the script can check how
many trials were done and whether one trial disagrees with the others.

A **per-test** export has one row per test day with a `Reps` column; this is the ForceDecks layout. **Trial-level
checks cannot run on a per-test export**, and the report says so. To use one, de-identify it with the
`force_plate` profile and set `"input_file": "coded_output/coded_cmj_season1.csv"`,
`"jump_height_column": "Jump Height (Imp-Mom)"`, `"trial_column": ""`, `"reps_column": "Reps"` and
`"depth_column": "Countermovement Depth"`.

Then:

```
python cmj_flags.py
python cmj_flags.py --explain ATH-XXXXXX
```

The second command prints one athlete's calculation step by step (baseline days and trials, baseline
mean, this day's trials and mean, the drop, both thresholds, the decision) so you can check it by hand.

### What the method does

1. Test-day value = mean of the athlete's valid trials that day (warns if fewer than `expected_trials_per_day`).
2. Baseline = mean of the athlete's first `baseline_days` test days (default 4).
3. Typical error (TE) = SD of all athletes' consecutive baseline-day differences, divided by the square
   root of 2, pooled across the squad (`individual_te: True` uses each athlete's own, when they have enough days).
4. Smallest worthwhile change (SWC) = `swc_multiplier` (default 0.2) x the between-athlete SD of baseline means.
5. A day is **flagged** when the drop from baseline exceeds **both** the SWC **and** `k` x TE (k default 1.5).
   Drops only; an improvement is never flagged.
6. Fewer than `baseline_days` test days: status "not enough data", never a flag. Missing days stay missing.
7. Duplicated test days (repeated trial numbers or twice the expected trials in a per-trial export; two rows for
   one day in a per-test export) are excluded until you fix the file. Values outside `plausible_min_cm` to
   `plausible_max_cm` (after conversion to cm) are excluded, with a note when the value looks like inches
   typed into a cm column or centimetres typed into an inches column. Every exclusion is listed in the report.
8. Countermovement depth, if present, is exported as a negative number (downward). Negative is valid; the
   script only warns when its size is outside `depth_plausible_min_cm` to `depth_plausible_max_cm`.

A flag is a prompt to check in with the athlete, not a decision. The TE assumes athletes were stable across
their baseline days; if they were fatigued, injured or still learning the test, TE is inflated and real
drops are missed.

**Known limit of the inches check.** The plausible range starts at 15 cm. A jump above 38 cm typed in inches
is 15 or more, so it passes the range check. The script therefore also warns when one trial differs from
the day's middle trial by more than 30% (`within_day_warning_fraction`), but that value stays in the
calculation until you correct the file.

### Worked example: week 8 of the synthetic squad

These numbers come from `cmj_trials_season1.csv` with the default settings. All the athletes are made up.

The squad's thresholds: TE = **1.45 cm**, SWC = **1.07 cm**, k x TE = **2.18 cm**. A drop has to exceed both the
SWC and k x TE, so the effective threshold is 2.18 cm.

| Athlete | Baseline (cm) | Week 8 (cm) | Drop (cm) | Past the SWC? | Past k x TE? | Result |
|---|---|---|---|---|---|---|
| Ivo Larsen | 28.56 | 25.57 | 2.99 | yes | yes | **flagged** |
| Sven Quiroga | 45.35 | 42.77 | 2.58 | yes | yes | **flagged** |
| Zane Zahra | 41.42 | 39.90 | 1.52 | yes | no | not flagged |
| Dario Mbeki | none | 38.33 | none | | | not enough data |

Zane Zahra is the reason the rule needs both thresholds: a 1.52 cm drop is bigger than the smallest worthwhile
change, but it is within what day-to-day noise can produce in this squad. Dario Mbeki was tested only in weeks 7
and 8, so there is no baseline to compare against. No other athlete drops past the SWC in week 8.

Across the whole season the script raises **30 flags** on 18 athletes, about 11% of the 269 test days after the
baseline. Only the week-8 drops of Ivo Larsen and Sven Quiroga were planted. The other 28 are ordinary noise: these
made-up jumps vary by about 4% from day to day, and at k = 1.5 some of that variation crosses the threshold. Ivo
Larsen's week-7 flag is one of them.

So some flags at this threshold will be noise, and a flag is a prompt to check in with the athlete, not a decision.
Raising `k` means fewer flags but more real drops missed. Every flag in the season is listed in
`expected_output/expected_answers.md`. The ForceDecks file gives slightly different numbers (28 flags) because it
stores one rounded value per test.

## 6. Running the tests yourself

```
python -m unittest discover -s tests -v
```

The tests confirm that every planted problem in the synthetic squad is caught, that every flag in the season
matches a separate calculation of the method, that the decoy is not flagged, that no original ID survives de-identification,
and that input files are never changed. GitHub Actions runs the same suite on Windows and macOS with
Python 3.10, 3.11 and 3.12 on every change.

## Files

| File | What it is |
|---|---|
| `deidentify.py` | the de-identification script (settings at the top) |
| `cmj_flags.py` | the CMJ flagging script (settings at the top) |
| `make_synthetic_squad.py` | rebuilds the made-up squad; fixed seed, identical output every time |
| `synthetic_data/` | eight CSV exports (GPS, per-trial CMJ, ForceDecks CMJ, wellness; two seasons) |
| `expected_output/` | what the scripts should find on the synthetic squad |
| `tests/` | the automated tests |
| `CITATION.cff` | how to cite |

## Citation

Article citation and link: *to be added on publication.*

Software: see `CITATION.cff`.

## Licence

To be added. Until a licence file is present, all rights are reserved.
