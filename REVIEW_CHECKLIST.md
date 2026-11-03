# Review request: strength-coach-data-tools

**To a colleague or IT staff member.** I would like to use these two Python scripts with athlete monitoring exports. Could you
check the five points below? It should take about 30 minutes and uses only the made-up data in the download. No real data is needed.

**Setup.** Download the release I am using (version: ______) and open a terminal in its folder. You need Python 3.10 or newer. On a
Mac, type `python3` instead of `python`. Commands are shown as Mac or Linux, then Windows PowerShell.

| # | What to check | How to check it | Result |
|---|---|---|---|
| 1 | **No network calls.** | List every import, then confirm none is a network module such as `socket`, `http`, `urllib`, `ftplib`, `smtplib` or `requests`.<br>`grep -nE "^(import\|from) " deidentify.py cmj_flags.py`<br>`Select-String -Pattern "^(import\|from) " deidentify.py,cmj_flags.py`<br>You can also turn off Wi-Fi and run item 5. | |
| 2 | **Input files are untouched.** | Take a fingerprint of the input, run the script, and take it again. The two must match.<br>`shasum -a 256 synthetic_data/cmj_trials_season1.csv`<br>`Get-FileHash synthetic_data\cmj_trials_season1.csv`<br>`python deidentify.py force_plate_trials` | |
| 3 | **Outputs contain no names or IDs.** | After item 2, run `python cmj_flags.py`. Then search the shareable folders for names from the made-up squad, such as Larsen and Okafor. Neither search should print anything. The key and PRIVATE report are in `KEY_DO_NOT_SHARE` and are meant to hold names.<br>`grep -ilE "larsen\|okafor" coded_output/* cmj_output/*`<br>`Select-String -Path coded_output\*,cmj_output\* -Pattern "larsen","okafor" -List` | |
| 4 | **Thresholds match the stated method.** | Open `verify_ivo_larsen.xlsx`. Click the green cells and compare their formulas with "What the method does" in the README. Every Match cell should say OK. Then confirm the report from item 3, in `cmj_output`, shows TE 1.45, SWC 1.07 and k x TE 2.18 cm. | |
| 5 | **The tests pass.** | `python -m unittest discover -s tests`<br>The last line should say `OK (skipped=1)`. The skipped item is a shared base class, not a missed check. | |

**Please tell me:** each result above; anything that surprised you; the version you checked; and whether you would use these
scripts on athlete data on your own computer.

**What this review does not cover.** The scripts reduce the risk of identifying an athlete, but they do not make data anonymous, and
they cannot find every name in free text. My institution's compliance office decides what may be shared.
