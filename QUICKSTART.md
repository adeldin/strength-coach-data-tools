# Quickstart: your first successful run

About 15 minutes, and you do not need to know Python. You will run the scripts on a made-up squad, follow one made-up
athlete, Ivo Larsen, through the calculation, and check the answer yourself in a spreadsheet. No real athlete data is
involved.

## 1. Install Python (about 5 minutes, once)

Go to <https://www.python.org/downloads/>, click the yellow download button and run the installer.

- **Windows:** on the installer's first screen, tick **Add python.exe to PATH**, then click *Install Now*.
- **Mac:** click through the installer. On a Mac, type `python3` wherever this guide says `python`.

Now open a terminal, the window where you type commands. On Windows, open the Start menu, type `PowerShell` and open it.
On a Mac, open Applications, then Utilities, then Terminal. If one was already open, close it and open a new one. Type this
and press Enter:

```
python --version
```

You should see `Python 3.10` or a higher number. If you see 3.9 or an error, section 1 of the [README](README.md) has fixes.

## 2. Download the scripts (about 2 minutes)

1. On the [repository page](https://github.com/adeldin/strength-coach-data-tools), click the green **Code** button, then
   **Download ZIP**.
2. Unzip it. You will have a folder called `strength-coach-data-tools-main`. Move it to your Documents folder.
3. Open a terminal **in that folder**:
   - Windows: open the folder in File Explorer, click in the address bar, type `powershell` and press Enter.
   - Mac: open Terminal, type `cd ` with a space after it, drag the folder onto the window, and press Enter.

## 3. Replace the names with codes (1 minute)

Type this and press Enter:

```
python deidentify.py force_plate_trials
```

It reads the made-up jump file and writes a coded copy with no names in it. The end of what you see should look like this:

```text
VERIFICATION
  OK: every cell of the output was re-read and none of the 28 original IDs appears in it.

Coded file: coded_cmj_trials_season1.csv
This report: deidentify_report_cmj_trials_season1.txt

Remaining risk must be reviewed by a person. This script reduces re-identification risk; it does not make data anonymous.

Done. 1 warning(s) to review. Output is coded data, not anonymous data.
Key: KEY_DO_NOT_SHARE/athlete_key.csv
```

The 1 warning is expected. It says some body-mass bands hold too few athletes, so someone could pick them out. With real
data, you would deal with that before sharing the file.

## 4. Look for meaningful drops in jump height (1 minute)

```
python cmj_flags.py
```

Near the top you should see these lines:

```text
SQUAD THRESHOLDS
  Baseline = first 4 test days per athlete (27 athletes have a full baseline).
  Typical error (TE) = 1.45 cm  (SD of 81 consecutive-day differences / sqrt 2, pooled across the squad)
  Smallest worthwhile change (SWC) = 0.2 x 5.35 cm between-athlete SD = 1.07 cm
  k x TE = 1.5 x TE = 2.18 cm
  Effective threshold (a drop must exceed BOTH) = 2.18 cm

FLAGS (30)
```

A test day is flagged when the drop from the athlete's baseline is bigger than both the SWC and k x TE. Your flags are listed
under codes, not names. Codes are random, so yours will be different from anyone else's, but the numbers will be the same.

## 5. Follow Ivo Larsen (3 minutes)

Open `KEY_DO_NOT_SHARE/athlete_key.csv`, in Excel or any text editor. Find **Ivo Larsen** in the `original_id` column and copy
the code next to it. Close the file, then type this with your code in place of `ATH-XXXXXX`:

```
python cmj_flags.py --explain ATH-XXXXXX
```

This prints the calculation one step at a time. Part of it looks like this:

```text
  Baseline days (first 4):
    week 1 session 1: trials 31.0, 30.7, 29.8  -> day value 30.50
    week 2 session 1: trials 28.4, 28.6, 28.1  -> day value 28.37
    week 3 session 1: trials 27.0, 26.9, 26.3  -> day value 26.73
    week 4 session 1: trials 28.7, 29.3, 27.9  -> day value 28.63
  Baseline mean = 28.56
  Consecutive-day differences in the baseline: -2.13, -1.63, +1.90   (these feed the pooled TE)
  TE used = 1.45 (pooled); k x TE = 1.5 x 1.45 = 2.18; SWC = 1.07
  Later test days:
    week 7 session 1: trials 25.1, 25.8, 27.0 -> 25.97; drop = 28.56 - 25.97 = +2.59; > SWC? yes; > k x TE? yes  => FLAG
    week 8 session 1: trials 24.5, 24.6, 24.6 -> 24.57; drop = 28.56 - 24.57 = +3.99; > SWC? yes; > k x TE? yes  => FLAG
    week 9 session 1: trials 28.7, 28.8, 27.8 -> 28.43; drop = 28.56 - 28.43 = +0.12; > SWC? no; > k x TE? no  => no flag
```

Ivo's week 8 jump is 3.99 cm below his baseline. That is more than both 1.07 and 2.18, so it is flagged.

## 6. Check the answer yourself (3 minutes)

Open `verify_ivo_larsen.xlsx` in Excel. The first sheet repeats Ivo's calculation with live formulas, so you can click any
green cell to see how it is worked out. The grey cell next to it is what the script reported, and the **Match** column
should say **OK** on every line. The second sheet does the same for the squad's TE and SWC. If Excel opens the file in
Protected View, the numbers still show. Click *Enable Editing* if you want to try changing a trial.

## 7. What to do next

**For a flagged athlete, like Ivo in week 8:** a flag is a prompt to check in, not a decision. Talk to the athlete. Ask about sleep,
soreness, illness, travel, stress and recent training. Look at their other monitoring data. Retest at the next session. Do not change
training on the flag alone: at this threshold, some flags will be noise. Here Ivo's week 9 is back to 28.43 cm, close to
his baseline.

**For an athlete who is not flagged, like Zane Zahra in week 8:** repeat step 5 with Zane's code. You will see:

```text
    week 8 session 1: trials 39.5, 39.9, 40.3 -> 39.90; drop = 41.42 - 39.90 = +1.52; > SWC? yes; > k x TE? no  => no flag
```

Zane's 1.52 cm drop is bigger than the SWC but smaller than k x TE, so it is within what day-to-day noise can produce in this
squad. The number alone does not call for action: carry on as usual and keep testing. Zane does flag in week 10, with a 3.42 cm drop
that came from the noise built into these made-up jumps, which is another reason a flag is only a prompt.

**To use your own data:** the list of settings to change is at the top of the [README](README.md). Read the warnings in the report
before sharing anything, and ask your institution's compliance office what may be shared. To have someone check these tools for
you, send them [REVIEW_CHECKLIST.md](REVIEW_CHECKLIST.md).

To run a step again, add `--overwrite`, for example `python cmj_flags.py --overwrite`. Without it, the scripts stop rather than
replace a file you already have.
