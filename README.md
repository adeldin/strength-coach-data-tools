# strength-coach-data-tools

Two small, tested Python scripts for strength and conditioning coaches who work with athlete
monitoring exports (GPS, force plate, wellness) and do not have a data scientist on staff.

- **deidentify.py** turns an export into **coded data** before it leaves your computer: it keeps only the
  columns you list, replaces names with random codes, turns dates into training weeks and session numbers,
  bands body size, groups positions, and tells you in plain English where an athlete could still be picked out.
- **cmj_flags.py** flags meaningful drops in countermovement jump (CMJ) height using a baseline, the
  squad's typical error (TE) and the smallest worthwhile change (SWC).

They accompany the article *Artificial Intelligence for the Strength Coach Without a Data Scientist*
(Strength and Conditioning Journal; citation and link to be added on publication).

**New here?** [QUICKSTART.md](QUICKSTART.md) walks you through a first successful run on a made-up squad in about 15 minutes.
To have someone check these tools for you, send them [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md).

**Three things to know before you start**

1. The de-identification script **reduces** re-identification risk. It does **not** make data anonymous.
   Someone who knows your squad may still recognise the only goalkeeper, the tallest athlete, or the
   player who was injured in week 6. Read the report it writes and act on the warnings. Its name detection
   is **not comprehensive**: it cannot find every name in free text, so read any text you choose to keep.
2. **Your institution's compliance office has the final say** on what may be shared or uploaded anywhere,
   including to an AI tool. These scripts do not change that.
3. Every number in `cmj_flags.py` (baseline length, k, the SWC multiplier, the plausible range) is an
   **adjustable choice, not a rule**. The defaults are the ones described in the article.

Both scripts use only Python itself: nothing to install beyond Python, no network calls, and your input
files are never changed. An output file that already exists is never replaced unless you add `--overwrite`.

## What this software does and does not do

**It does:** replace athlete names with codes, keep only the columns you list, turn dates into weeks and sessions, warn where an
athlete could still be picked out, and flag drops in jump height using the method in section 5.

**It does not:** make data anonymous, find every name in free text, decide anything about an athlete, or replace your compliance
office. It makes **no network connections**: both scripts use only Python's own tools for files, numbers and dates, and an automated
test fails if a network module is ever added.

**Independent review:** ChatGPT independently reviewed versions 0.3.0 and 0.4.0, and versions 0.4.0 and 0.5.0 fixed the findings. Version
1.0.0 adds documentation, a retry for locked files, a test fix and the licence. Version 1.0.0 itself has not had an independent review.

## The settings to change

For your first runs on your own per-trial jump export, change only these lines. Each setting in both scripts is
marked `# CHANGE THIS for your own data` or `# LEAVE AS IS for your first runs`.

In `deidentify.py`, at the top of SETTINGS:

```python
"season_start_date": "2024-08-05",
```

In `deidentify.py`, in the `force_plate_trials` profile:

```python
"input_file": "synthetic_data/cmj_trials_season1.csv",
"athlete_id_column": "Name",
"keep_columns": ["Name", "Date", "Test Type", "Trial", "Jump Height (cm)",
                 "Peak Power (W)", "RSI-modified", "Body Mass (kg)"],
"date_columns": ["Date"],
"date_format": "%m/%d/%Y",
```

In `cmj_flags.py`:

```python
"input_file": "coded_output/coded_cmj_trials_season1.csv",
"jump_height_column": "Jump Height (cm)",
```

The other profiles are marked the same way. Section 4 explains each setting. Your export needs columns called `Test Type`
(with the value `CMJ`) and `Trial`; if yours are called something else, section 4 covers `column_types` and `allowed_values`, and
section 5 covers the same names in `cmj_flags.py`. Before you use real data, move the key: see "Where to keep the key" in section 4.

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
2. Unzip it. You will have a folder called `strength-coach-data-tools-main`. Put it somewhere easy to find,
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

To run everything again on purpose, add `--overwrite` to each command, for example
`python deidentify.py gps --overwrite`. Without it, the scripts stop rather than replace a file you already have.
Athletes keep their codes when you do this.

## 4. Point the scripts at your own export

Open `deidentify.py` in any text editor (Notepad, TextEdit in plain-text mode, or VS Code). Everything you
need to change is in the **SETTINGS** block at the top; you do not need to read past it.

1. **Season start date**: `"season_start_date": "2024-08-05"` (year-month-day). Week 1 starts here.
2. **Pick a profile** (`gps`, `force_plate_trials`, `force_plate` or `wellness`) and set:
   - `input_file`: the path to your export, saved as CSV (in Excel: *File, Save As, CSV UTF-8*).
   - `athlete_id_column`: the heading of the column that holds the athlete's name or ID. We recommend
     **non-numeric or long athlete IDs**. A short number, like a jersey number, is hard to tell from a real
     measurement, so a copy of it can get past the checks. The report warns about numeric IDs shorter than 5 digits,
     and warns (DO NOT SHARE) when a number column holds a row's own ID in some rows.
   - `keep_columns`: the headings you want in the shared file, **spelled exactly as the export spells
     them** (spaces at the start or end do not matter). Anything not listed is dropped. Start with fewer
     columns than you think you need. If two kept columns would end up with one heading, the script stops.
   - **Column types**: every kept column is treated as a **number** unless you say otherwise. A value that is
     not a number is left blank and counted in the report, and a column of nothing but text is dropped. Use
     `column_types` for anything else: `"category"` for a short label like Training or Match. The ID, date, position,
     class year and event columns are known from their own settings.
   - `allowed_values`: every category, class year and event column needs a list of the values you permit, for example
     `"allowed_values": {"Session Type": ["Training", "Match"]}`. The script stops if the list is missing. Any other
     value is left blank and counted, and it is shown only in the PRIVATE report, because **event fields can contain
     identifying notes** ("hamstring, saw Dr Lee"). Upper and lower case do not matter.
   - `allowed_text_columns`: free text, like a notes column, is dropped unless you list it here. The report then
     warns you, because **name detection is not comprehensive**: the script looks for the IDs in your file and for
     values shaped like a name, and it can miss a nickname, a first name or a misspelling. Read every value.
   - **Units** are read from the brackets at the end of each heading: `[in]` or `(in)` is converted to cm,
     `[lb]` to kg, and the heading is renamed to match. The body-mass and height columns must carry a unit;
     if yours do not, add one to the heading in the file (for example `Body Mass [kg]`), or the script stops
     and tells you. The height column can be in cm, in or m (`[m]` is converted to cm for this column only, so
     a distance in metres is left alone). Any other height unit stops the run.
   - **Asymmetry columns** exported as text with a side letter (`6.3 L`) are split into a number and a
     `... side` column. Columns with `(Asym)` in the heading are found automatically; list others in
     `asymmetry_columns`. Values that cannot be read are left blank and counted in the report.
   - `date_columns` and `date_format`: how dates look in your file. `"%m/%d/%Y"` is `08/05/2024`,
     `"%d/%m/%Y"` is `05/08/2024`, `"%Y-%m-%d"` is `2024-08-05`. The format is required: if it is blank, the
     script stops, because a date like 03/04/2026 can be read two ways.
   - `session_column`: leave as `""` unless you test twice on one date. See "More than one session in a week" in section 5.
   - `position_column`, `class_year_column`, `height_column`, `body_mass_column`: set to `""` if your
     export does not have them.
   - `event_columns`: columns that record an injury, illness or similar event. List their values in `allowed_values`.
3. **Position groups**: `position_groups` is a coach-edited mapping from your export's position labels to broader
   groups. The script does not decide which positions belong together: you do. It warns when a position, or a
   combination of traits, leaves fewer than `minimum_group_size` athletes, and you then merge groups or drop the
   column. A position missing from the mapping is left blank and counted, and it is shown only in the PRIVATE report.
4. **Key folder**: `KEY_DO_NOT_SHARE` by default. It is the only thing that links codes back to names, so keep it off
   shared drives and out of every AI tool. Use the **same key folder** for all your exports so an athlete keeps one
   code everywhere. See "Where to keep the key" below.
5. Run `python deidentify.py gps` (or the profile you edited). Read the report: it is printed on screen
   and saved as `coded_output/deidentify_report_<file>.txt`. Details that could name someone go in a separate
   report beside the key, `PRIVATE_deidentify_report_<file>.txt`.

### A complete example of edited settings

Here is a complete SETTINGS block with one edited profile, for a Windows computer. It has every setting, so it can
replace the whole block at the top of the script as it stands; then change the values to match your own file. Three things
trip people up: every heading and path goes inside straight double quotes, every line in a list or block ends with a
comma, and each backslash in a Windows path is typed twice. On a Mac, a path looks like
`"/Users/coach/Documents/exports/jumps_fall.csv"`, with single forward slashes.

```python
SETTINGS = {
    "output_folder": "coded_output",
    "key_folder": "C:\\Users\\coach\\AthleteKey",
    "key_file": "athlete_key.csv",
    "season_start_date": "2025-08-04",
    "minimum_group_size": 5,
    "body_mass_band_kg": 5,
    "height_band_cm": 5,
    "height_tolerance_cm": 3,
    "position_groups": {
        "GK": "Goalkeeper",
        "CB": "Defender", "LB": "Defender", "RB": "Defender",
        "CM": "Midfielder", "DM": "Midfielder", "AM": "Midfielder",
        "LW": "Forward", "RW": "Forward", "ST": "Forward",
    },
    "id_aliases": {},
    "profiles": {
        "force_plate_trials": {
            "input_file": "C:\\Users\\coach\\Documents\\exports\\jumps_fall.csv",
            "athlete_id_column": "Athlete",
            "keep_columns": ["Athlete", "Test Date", "Test Type", "Trial", "Jump Height (cm)", "Body Weight [kg]"],
            "date_columns": ["Test Date"],
            "date_format": "%m/%d/%Y",
            "session_column": "",
            "column_types": {"Test Type": "category"},
            "allowed_values": {"Test Type": ["CMJ"]},
            "allowed_text_columns": [],
            "position_column": "",
            "class_year_column": "",
            "height_column": "",
            "body_mass_column": "Body Weight [kg]",
            "event_columns": [],
            "asymmetry_columns": [],
        },
    },
}
```

### Where to keep the key

Choose a folder that does **not** sync to the cloud. On Windows, OneDrive often syncs Documents and Desktop, and on a
Mac, iCloud can sync them too. So make a new folder directly in your user folder, such as `C:\Users\coach\AthleteKey`
or `/Users/coach/AthleteKey`, and check that it has no cloud icon. To check on Windows, look at the folder in File
Explorer; on a Mac, look in System Settings under your name, then iCloud, then Drive. If your institution provides
an approved secure location, use that. The script warns if the key folder's path looks like a cloud folder, but it
cannot catch every one.

The script keeps the previous key as `athlete_key_backup.csv` whenever it adds an athlete. Do not give any other file
that name: the script stops rather than replace a file that is also your input or output, or a link to another file. It checks
the key before using it, and stops if a code is blank or if an athlete or a code appears twice.

**To find an athlete's code**, open `athlete_key.csv` in the key folder on your own computer. The `original_id` column
holds the name and the `code` column holds the code. Use that code with `--explain`. Never upload this file.

The `force_plate` profile uses the **real heading row of a VALD ForceDecks CMJ export** (per test). The `gps`,
`force_plate_trials` and `wellness` profiles are **examples in the style of common systems**, not a specific
vendor's layout. All four match the synthetic files. Replace them with your own headings.

### Reading the de-identification report

There are two reports. The one in `coded_output` holds no names, IDs or free-text values. The **PRIVATE** one beside
the key holds the details that could identify someone: name variants, conflicting values and the exact groups that are too small. Never share it.

Every warning says what to do about it:

| Label | What it means |
|---|---|
| **FIX BEFORE USING RESULTS** | Something in the data is wrong or was left out. Fix the file or the settings and run again. |
| **DO NOT SHARE** | An athlete could still be identified. Do not share the file until you have dealt with it. |
| **INFORMATION ONLY** | Worth knowing. You do not have to change anything. |

- **COLUMNS**: what was kept and dropped. If a dropped column surprises you, add it to `keep_columns`.
- **ATHLETE CODES**: how many athletes, how many reused a code from the key, and how many pairs of IDs look
  like one person written two ways. The private report lists the pairs. The script never merges them itself; add
  them to `id_aliases` if they are the same person.
- **UNITS AND VALUES**: what was converted, and how many values were left blank because they were not numbers or were
  not on the column's `allowed_values` list.
- **SPREADSHEET FORMULAS**: a spreadsheet can run a text value that starts with `=`, `+`, `-` or `@` as a formula, so in text
  columns the script puts an apostrophe in front of it and says how many it changed. Number columns are left alone.
- **ID CONFLICTS**: how many IDs were recorded with two heights (or two positions, or two class years). Two people
  may share a name, or a value was mistyped. The private report has the details.
- **UNIQUENESS CHECK**: (a) trait combinations (position group + class year + body-mass band + height band) that fewer
  than `minimum_group_size` athletes share; (b) rows where week + session + position + event point to fewer than that
  many athletes. Each comes with a suggestion for a coarser grouping. Counts are **different athletes**, not rows, and
  they cover every combination as it appears in the output, so an athlete with one unusual value is counted there too.
- **VERIFICATION**: before saving anything, the script re-reads every heading and cell of its output, and stops if any
  original name or ID is still there. It runs the same check over the shareable report. An ID of 4 or more characters
  is found even inside a longer word; a shorter one only as a whole word. Common ways of writing a name are found too
  (`Lee, Ann`, `A. Lee`, `ann_lee`), but a surname or first name on its own is not. A number made only of digits is not
  looked for in the report's own counts and dates, and an ID that is one ordinary word, such as Will or Ward, can match the
  report's own wording and stop the run: use a fuller ID. If the script stops, the new file is not saved and any earlier
  file stays as it was. It also warns about values that look like a person's name in any kept text column.

Antivirus and cloud sync, such as OneDrive, can hold a new file for a moment, so if a file is locked, the script waits and tries up to
5 times over about 3 seconds. Each try first re-checks that nothing else has changed the destination. If saving still fails, the
message says the file may be locked and to close it or pause syncing. The script puts back every file it had already saved. If it
cannot, the message says exactly which files changed and where their previous versions are.

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
mean, this day's trials and mean, the drop, both thresholds, the decision) so you can check it by hand. It writes no
files, so you can run it as often as you like. To find an athlete's code, see "Where to keep the key" in section 4.

### More than one session in a week

You do not need to do anything. `deidentify.py` writes a `Week` and a `Session` column: the session number is the
date's place among the different dates in that week, across the whole file. `cmj_flags.py` treats week + session as
the test day, so **two sessions in one week are two test days**, not a duplicate. Everyone tested on the same date shares a session number.

**Two tests on one date** cannot be told apart once the date is gone, so `cmj_flags.py` reads them as a duplicated day and
leaves that day out. Keep one test per date if you can. If you really do test twice on one date, add a real session
identifier column to your export, such as AM and PM, or 1 and 2. Name it in `session_column` in `deidentify.py` and leave
it out of `keep_columns`: the two tests then get different session numbers. Do not change a date to separate two tests,
because that makes your record of when the athlete was tested wrong.

### Season 2

Use the **same key folder**, so returning athletes keep their codes. In `deidentify.py`, change `season_start_date`
(the synthetic squad's second season starts `"2025-08-04"`) and each profile's `input_file`
(for example `"synthetic_data/cmj_trials_season2.csv"`). In `cmj_flags.py`, change `input_file` to the new coded file
(`"coded_output/coded_cmj_trials_season2.csv"`). Each season gets its own baseline and thresholds, because the script
reads one file at a time. Do not combine seasons in one file: their week numbers would overlap.

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
9. The script stops, rather than guessing, if weeks or sessions are not whole numbers, if a file mixes weeks and dates,
   if two headings are the same once units are ignored, or if the `Test Type` column is missing. To turn test-type filtering
   off on purpose, set `test_type_column` to `""`.

A flag is a prompt to check in with the athlete, not a decision. The TE assumes athletes were stable across
their baseline days. An unstable baseline can distort TE **in either direction**. Up-and-down days from fatigue, injury or
learning the test can make it too large, so real drops are missed.

**A steady trend can do the opposite.** If jumps climb or fall steadily across the baseline days, TE can be misleadingly small,
so noise gets flagged: 31, 32, 33, 34 cm gives differences of 1, 1, 1, so their SD, and TE with it, is 0. The report warns (INFORMATION ONLY)
when every one of an athlete's baseline differences has the same sign. In a squad, one athlete's trend is averaged with everyone else's, but check it.

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
| Ivo Larsen | 28.56 | 24.57 | 3.99 | yes | yes | **flagged** |
| Sven Quiroga | 45.35 | 42.77 | 2.58 | yes | yes | **flagged** |
| Zane Zahra | 41.42 | 39.90 | 1.52 | yes | no | not flagged |
| Dario Mbeki | none | 38.33 | none | | | not enough data |

Zane Zahra is the reason the rule needs both thresholds: a 1.52 cm drop is bigger than the smallest worthwhile
change, but it is within what day-to-day noise can produce in this squad. Dario Mbeki was tested only in weeks 7
and 8, so there is no baseline to compare against. No other athlete drops past the SWC in week 8.

Across the whole season the script raises **30 flags** on 18 athletes, about 11% of the 270 test days after the
baseline. Only the week-8 drops of Ivo Larsen and Sven Quiroga were planted. The other 28 are ordinary noise: these
made-up jumps vary by about 4% from day to day, and at k = 1.5 some of that variation crosses the threshold. Ivo
Larsen's week-7 flag is one of them.

So some flags at this threshold will be noise, and a flag is a prompt to check in with the athlete, not a decision.
Zane Zahra escapes in week 8 only: the same athlete flags in week 10 (a 3.42 cm drop) from ordinary noise.

**Changing `k` is a trade-off.** At k = 2.0, k x TE rises to 2.90 cm and the season falls to **13 flags at k = 2.0**.
Fewer false alarms, but in week 8 only Ivo Larsen flags: Sven Quiroga's planted 2.58 cm drop is now missed. The
default stays at 1.5. Every flag at both values, with counts per week, is listed in
`expected_output/expected_answers.md`. The ForceDecks file gives slightly different numbers (28 and 12 flags)
because it stores one rounded value per test.

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
| `QUICKSTART.md` | a first successful run, about 15 minutes |
| `REVIEW_CHECKLIST.md` | a one-page request for a colleague or IT staff to check these tools |
| `verify_ivo_larsen.xlsx` | one athlete's flag and the squad's TE and SWC, as live Excel formulas to check by hand |
| `make_verify_spreadsheet.py` | rebuilds that spreadsheet; only this needs an extra package (openpyxl), and coaches never need to run it |
| `make_synthetic_squad.py` | rebuilds the made-up squad; fixed seed, identical output every time |
| `synthetic_data/` | eight CSV exports (GPS, per-trial CMJ, ForceDecks CMJ, wellness; two seasons) |
| `expected_output/` | what the scripts should find on the synthetic squad |
| `tests/` | the automated tests |
| `CITATION.cff` | how to cite |
| `LICENSE` | the MIT licence |

## Citation

Article citation and link: *to be added on publication.*

Software: see `CITATION.cff`.

## Licence

MIT. See `LICENSE`.
