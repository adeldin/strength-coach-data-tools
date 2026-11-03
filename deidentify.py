"""
deidentify.py  -  turn an athlete monitoring export into CODED data before it leaves your computer.

What it does, in order:
  1. Keeps only the columns you list below. Every other column is dropped.
  2. Replaces each athlete's name or ID with a random code (for example ATH-K7Q2MX) and writes
     the name-to-code key to a SEPARATE folder that you must keep private.
  3. Reads the unit in each heading's brackets, converts inches to cm and pounds to kg, and renames
     the heading to match.
  4. Converts dates into a training week number, counted from your season start date, and a session
     number within that week. Text columns are dropped unless you list them, and a category or event
     column keeps only the values you permit.
  5. Replaces body mass and height with bands (for example "70-75 kg"), positions with groups, and
     splits asymmetry values like "6.3 L" into a number and a side.
  6. Checks whether any athlete, or any row, could still be picked out, and says so in plain English.
  7. Re-reads every cell of the finished file and stops if any original name or ID is still in it.
  8. Writes a shareable report, and a PRIVATE report beside the key that can name athletes.

The result is CODED data, not anonymous data. Someone who knows the squad may still recognise an
athlete from a rare position, an unusual body size, or an injury in a known week. Read the report
and act on its warnings before you share anything. Your institution's compliance office has the
final say on what may be shared.

How to run it (from the folder that holds this file):
    python deidentify.py gps
    python deidentify.py force_plate_trials
    python deidentify.py force_plate
    python deidentify.py wellness
Add "--input some_file.csv" to code a different file with the same settings.

Needs Python 3.10 or newer. Uses nothing outside Python's own standard library. Makes no network calls.
Never changes or overwrites your input file, and never replaces an existing output unless you add --overwrite.
"""

SCRIPT_VERSION = "0.5.0"

# =====================================================================================================
# SETTINGS  -  edit these. Everything a coach needs to change is in this block.
# =====================================================================================================

SETTINGS = {
    # Where the coded files and the report go. Created if it does not exist.
    "output_folder": "coded_output",

    # Where the name-to-code KEY goes. Keep this folder off shared drives and out of any AI tool.
    # Point every export at the SAME key folder so an athlete keeps one code across GPS, force plate
    # and wellness files, and across seasons.
    "key_folder": "KEY_DO_NOT_SHARE",
    "key_file": "athlete_key.csv",

    # First day of the season, written year-month-day. Week 1 starts on this date.
    "season_start_date": "2024-08-05",

    # An athlete, or a row, is reported when fewer than this many DIFFERENT athletes share its traits.
    "minimum_group_size": 5,

    # Body mass and height are replaced by bands of this width (after conversion to kg and cm).
    "body_mass_band_kg": 5,
    "height_band_cm": 5,

    # One athlete recorded with two heights further apart than this is reported as a conflict.
    "height_tolerance_cm": 3,

    # Positions as they appear in your export, and the broader group each becomes. A position that
    # is not listed here is left blank, counted, and named only in the private report. Edit freely.
    "position_groups": {
        "GK": "Goalkeeper",
        "CB": "Defender", "LB": "Defender", "RB": "Defender", "DF": "Defender",
        "CM": "Midfielder", "DM": "Midfielder", "AM": "Midfielder", "MF": "Midfielder",
        "LW": "Forward", "RW": "Forward", "ST": "Forward", "FW": "Forward",
    },

    # If the same athlete appears under two spellings, say which is which here. The script never
    # guesses: it only lists likely variants in the report for you to decide.
    #   example: "id_aliases": {"J. Okafor": "Jamal Okafor"},
    "id_aliases": {},

    # One profile per kind of export. Spaces at the start or end of a heading are ignored, so
    # "RSI-modified [m/s] " in the export matches "RSI-modified [m/s]" here. Otherwise headings must
    # be spelled exactly as the export spells them. A column that is not in "keep_columns" is dropped.
    #
    # Every kept column has a type. The ID, date, position, class year and event columns are known from their own
    # settings. Anything else is a NUMBER unless "column_types" says otherwise: a value that is not a number is left
    # blank and counted, and a column of nothing but text is dropped. Other types you can give: "category" (a short
    # label, like Training or Match), "date", "id". Free text is dropped unless you list the column under
    # "allowed_text_columns", which adds a warning, because this script cannot find every name in free text.
    #
    # Every category, class year and event column needs its permitted values listed under "allowed_values". The script
    # stops if the list is missing. Any other value is left blank, counted, and named only in the private report,
    # because event fields especially can hold identifying notes ("hamstring, saw Dr Lee").
    #
    # "session_column" is optional: a real session identifier, like AM and PM, for days with two tests on one date.
    # Leave it out of keep_columns; it is only used to number the sessions.
    "profiles": {
        # EXAMPLE layout in the style of a GPS system export. Replace with your own headings.
        "gps": {
            "input_file": "synthetic_data/gps_season1.csv",
            "athlete_id_column": "Player Name",
            "keep_columns": ["Player Name", "Date", "Position", "Class Year", "Height (cm)",
                             "Body Mass (kg)", "Session Type", "Total Distance (m)",
                             "High Speed Running (m)", "Sprint Distance (m)", "Max Velocity (km/h)",
                             "Player Load", "Duration (min)"],
            "date_columns": ["Date"],
            # How dates are written in the export: "%m/%d/%Y" is 08/05/2024, "%d/%m/%Y" is 05/08/2024,
            # "%Y-%m-%d" is 2024-08-05. Required: the script stops if it is blank.
            "date_format": "%m/%d/%Y",
            "session_column": "",
            "column_types": {"Session Type": "category"},
            "allowed_values": {"Session Type": ["Training", "Match"],
                               "Class Year": ["Freshman", "Sophomore", "Junior", "Senior"]},
            "allowed_text_columns": [],
            "position_column": "Position",
            "class_year_column": "Class Year",
            "height_column": "Height (cm)",
            "body_mass_column": "Body Mass (kg)",
            # Columns whose entries describe an event (an injury, an illness, a return to play).
            "event_columns": [],
            # Columns holding a value and a side letter, like "6.3 L". Columns with "(Asym)" in the
            # heading are found automatically; list any others here.
            "asymmetry_columns": [],
        },
        # REAL layout: a VALD ForceDecks CMJ export (one row per test, with a Reps column). Jump height
        # is exported in inches; the script converts it to cm and renames the heading. Every metric column
        # is kept; ExternalId, Tags and Time are always dropped.
        "force_plate": {
            "input_file": "synthetic_data/cmj_season1.csv",
            "athlete_id_column": "Name",
            "keep_columns": ["Name", "Test Type", "Date", "BW [KG]", "Reps", "Additional Load [lb]",
                             "Jump Height (Imp-Mom) in Inches [in]", "RSI-modified [m/s]", "Peak Landing Force [N]",
                             "Peak Power / BM [W/kg]", "Concentric RFD [N/s] (L)", "Concentric Peak Force [N] (L)",
                             "Concentric Peak Force [N] (R)", "Peak Landing Force [N] (L)", "Peak Landing Force [N] (R)",
                             "Concentric Duration [ms]", "Concentric Impulse [N s]", "Concentric Mean Force [N]",
                             "Countermovement Depth [cm]", "Contraction Time:Eccentric Duration [%]",
                             "Eccentric Duration [ms]", "Flight Time:Contraction Time",
                             "Concentric Impulse % (Asym) (%)", "Peak Landing Force % (Asym) (%)",
                             "Eccentric Deceleration RFD [N/s]", "Eccentric Deceleration Mean Force [N]"],
            "date_columns": ["Date"],
            "date_format": "%m/%d/%Y",
            "session_column": "",
            "column_types": {"Test Type": "category"},
            "allowed_values": {"Test Type": ["CMJ"]},
            "allowed_text_columns": [],
            "position_column": "",
            "class_year_column": "",
            "height_column": "",
            "body_mass_column": "BW [KG]",
            "event_columns": [],
            "asymmetry_columns": [],
        },
        # EXAMPLE layout for a per-trial (one row per jump) force plate export in cm.
        "force_plate_trials": {
            "input_file": "synthetic_data/cmj_trials_season1.csv",
            "athlete_id_column": "Name",
            "keep_columns": ["Name", "Date", "Test Type", "Trial", "Jump Height (cm)",
                             "Peak Power (W)", "RSI-modified", "Body Mass (kg)"],
            "date_columns": ["Date"],
            "date_format": "%m/%d/%Y",
            "session_column": "",
            "column_types": {"Test Type": "category"},
            "allowed_values": {"Test Type": ["CMJ"]},
            "allowed_text_columns": [],
            "position_column": "",
            "class_year_column": "",
            "height_column": "",
            "body_mass_column": "Body Mass (kg)",
            "event_columns": [],
            "asymmetry_columns": [],
        },
        # EXAMPLE layout in the style of a wellness questionnaire export.
        "wellness": {
            "input_file": "synthetic_data/wellness_season1.csv",
            "athlete_id_column": "Athlete",
            "keep_columns": ["Athlete", "Date", "Position", "Sleep Hours", "Sleep Quality (1-5)",
                             "Fatigue (1-5)", "Soreness (1-5)", "Stress (1-5)", "Injury/Illness"],
            "date_columns": ["Date"],
            "date_format": "%m/%d/%Y",
            "session_column": "",
            "column_types": {},
            "allowed_values": {"Injury/Illness": ["Injury", "Illness"]},
            "allowed_text_columns": [],
            "position_column": "Position",
            "class_year_column": "",
            "height_column": "",
            "body_mass_column": "",
            "event_columns": ["Injury/Illness"],
            "asymmetry_columns": [],
        },
    },
}

# =====================================================================================================
# The code. You do not need to read past this line to use the script.
# =====================================================================================================

import argparse
import csv
import json
import math
import os
import re
import secrets
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime
from itertools import combinations

CODE_PREFIX = "ATH-"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O or 1/I, so codes are easy to read aloud
CODE_LENGTH = 6
NAME_SHAPED = re.compile(r"\b[A-Z][a-z]{1,}(?:\s[A-Z]\.?)?\s[A-Z][a-z]{1,}\b|\b[A-Z]\.\s?[A-Z][a-z]{1,}\b")
ASYM_VALUE = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*([LRlr])\s*$")
CLOUD_FOLDER = re.compile(r"onedrive|dropbox|icloud|google ?drive|cloudstorage|box sync", re.I)

# units the script understands, as they appear inside [...] or (...) at the end of a heading
LENGTH_UNITS = {"cm": ("cm", 1.0), "in": ("cm", 2.54), "inch": ("cm", 2.54), "inches": ("cm", 2.54), "mm": ("cm", 0.1), "m": ("m", 1.0)}
HEIGHT_UNITS = {"cm": 1.0, "in": 2.54, "inch": 2.54, "inches": 2.54, "m": 100.0}    # the height column only
MASS_UNITS = {"kg": ("kg", 1.0), "lb": ("kg", 0.45359237), "lbs": ("kg", 0.45359237)}
OTHER_UNITS = {"n", "w", "w/kg", "m/s", "n/s", "ms", "s", "%", "n s", "km/h", "min"}
UNIT_GROUP = re.compile(r"[\[(]([^\[\]()]+)[\])]")
COLUMN_TYPES = {"number", "category", "date", "id"}
KEY_COLUMNS = ("original_id", "code")

# every warning says what to do about it
FIX = "WARNING [FIX BEFORE USING RESULTS]"
NO_SHARE = "WARNING [DO NOT SHARE]"
INFO = "WARNING [INFORMATION ONLY]"
GENERATED_KINDS = {"code", "week", "session", "band", "side"}   # the script wrote these cells itself, so they cannot hold an ID
FORMULA_STARTS = ("=", "+", "-", "@")                           # a spreadsheet can run a text cell that starts with one of these
SHORT_NUMERIC_ID_DIGITS = 5


class StopRun(Exception):
    """Raised when the script must stop. The message is written for the coach."""


# ------------------------------------------------------------------ small helpers

def norm(text):
    """Lower-case, single-spaced version of a value, for comparisons only."""
    return " ".join(str(text).split()).casefold()


def to_float(text):
    """A finite number, or None. 'nan' and 'inf' are not numbers here."""
    try:
        value = float(str(text).strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def band_label(value, width, unit):
    lower = math.floor(value / width) * width
    fmt = (lambda x: str(int(x))) if float(width).is_integer() else (lambda x: f"{x:g}")
    return f"{fmt(lower)}-{fmt(lower + width)} {unit}"


def new_code(existing):
    while True:
        code = CODE_PREFIX + "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code not in existing:
            return code


def unit_of(header):
    """The unit named in the heading's last [..] or (..) group, lower-case, or '' if there is none."""
    groups = [g.strip().casefold() for g in UNIT_GROUP.findall(header)]
    for g in reversed(groups):
        if g in LENGTH_UNITS or g in MASS_UNITS or g in OTHER_UNITS:
            return g
    return ""


def converted_header(header, old_unit, new_unit):
    """Rename '[in]' to '[cm]' (or '(lb)' to '(kg)'), and drop a phrase like 'in Inches' if present."""
    out = re.sub(r"([\[(])" + re.escape(old_unit) + r"([\])])", lambda m: m.group(1) + new_unit + m.group(2), header, flags=re.I)
    out = re.sub(r"\s+in\s+inches\b", "", out, flags=re.I)
    return " ".join(out.split())


def fmt_number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".") if value is not None else ""


def scan_form(text):
    """Lower-case, with each run of spaces or punctuation made one space, so 'Okafor,Jamal' and 'okafor_jamal' read alike."""
    return " ".join(re.sub(r"[\W_]+", " ", str(text).casefold()).split())


def name_forms(raw):
    """An ID and, for a name of two or more words, the usual ways of writing it: Jamal Okafor, Okafor Jamal, J Okafor,
    Okafor J, JamalOkafor, JOkafor. A surname or first name alone is not included: Power and Long are also ordinary words."""
    parts = scan_form(raw).split()
    forms = {" ".join(parts)}
    if len(parts) >= 2 and all(x.isalpha() for x in parts):
        first, last = parts[0], parts[-1]
        forms |= {f"{first} {last}", f"{last} {first}", f"{first[0]} {last}", f"{last} {first[0]}", first + last, first[0] + last}
    return forms - {""}


def id_pattern(ids, with_letters_only=False):
    """Search this against scan_form(text). IDs and name forms of 4 or more characters match anywhere, even inside a
    longer word; shorter ones match only as whole words, so the ID 'Bo' is not found in 'both'."""
    forms = set().union(*(name_forms(i) for i in ids)) if ids else set()
    if with_letters_only:
        forms = {x for x in forms if any(c.isalpha() for c in x)}
    alternatives = [re.escape(x) if len(x) >= 4 else r"(?<!\w)" + re.escape(x) + r"(?!\w)" for x in sorted(forms, key=len, reverse=True)]
    return re.compile("|".join(alternatives)) if alternatives else re.compile(r"(?!)")


# ------------------------------------------------------------------ file safety

def same_file(a, b):
    """True when two paths reach one file, through a symlink, a hard link or a different spelling."""
    if os.path.realpath(a) == os.path.realpath(b):
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def is_inside(child, parent):
    child, parent = os.path.realpath(child), os.path.realpath(parent)
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:      # different drives on Windows
        return False


def check_output_path(path, input_file, overwrite):
    if os.path.islink(path):
        raise StopRun(f"Refusing to run: '{path}' is a symbolic link. Remove it or choose a different folder.")
    if same_file(path, input_file):
        raise StopRun(f"Refusing to run: '{path}' is the input file. Choose a different output folder.")
    if os.path.isdir(path):
        raise StopRun(f"Refusing to run: '{path}' is a folder, so a file cannot be saved under that name. Nothing was changed. Move or rename the folder.")
    if os.path.lexists(path) and not overwrite:
        raise StopRun(f"'{path}' already exists and was not changed. Move it, choose a different folder, or add --overwrite to replace it.")


def check_folder(folder):
    """The destination folder, or the nearest part of its path that exists, must be a folder this run can write in."""
    here = os.path.abspath(folder)
    while not os.path.lexists(here):
        here = os.path.dirname(here)
    if not os.path.isdir(here) or not os.access(here, os.W_OK):
        raise StopRun(f"Refusing to run: nothing can be saved in '{folder}' because '{here}' is not a folder this computer can write to. Nothing was changed.")


def check_backup_path(backup, others):
    """The key backup is replaced on every run that adds an athlete, so it must be its own ordinary file."""
    if os.path.islink(backup):
        raise StopRun(f"Refusing to run: the key backup '{backup}' is a symbolic link. Remove it or choose a different key folder.")
    if os.path.isdir(backup):
        raise StopRun(f"Refusing to run: the key backup '{backup}' is a folder. Move or rename it.")
    for other in others:
        if same_file(backup, other):
            raise StopRun(f"Refusing to run: the key backup '{backup}' is the same file as '{other}', and would replace it. Rename one of them or choose a different key folder.")
    if os.path.exists(backup) and os.stat(backup).st_nlink > 1:
        raise StopRun(f"Refusing to run: the key backup '{backup}' is a hard link to another file. Remove it or choose a different key folder.")


def write_temp(path, temps, write):
    """Write to a new temporary file beside the destination. Nothing at the destination changes yet."""
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp_", suffix=os.path.splitext(path)[1])
    temps.append(tmp)
    with os.fdopen(handle, "w", newline="", encoding="utf-8") as f:
        write(f)
    return tmp


def publish_all(moves, temps):
    """moves: [(temporary file, destination, private?)]. All of them go into place, or the earlier ones are undone and
    the stop message says exactly what happened. Each move is one step, so no file is ever left half written."""
    done = []   # (destination, temporary copy of the file it replaced, or None if it is new)
    try:
        for tmp, path, private in moves:
            if os.path.islink(path):
                raise StopRun(f"'{path}' is a symbolic link")
            saved = None
            if os.path.exists(path):
                handle, saved = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".tmp_", suffix=".previous")
                os.close(handle)
                temps.append(saved)
                shutil.copy2(path, saved)
            os.chmod(tmp, 0o600 if private else 0o644)
            os.replace(tmp, path)
            done.append((path, saved))
    except (OSError, StopRun) as e:
        stuck = []
        for path, saved in reversed(done):
            try:
                if saved:
                    os.replace(saved, path)
                else:
                    os.remove(path)
            except OSError:
                stuck.append(path + (f" (its previous version is at {saved})" if saved else " (new file)"))
                if saved:
                    temps.remove(saved)     # the coach needs this copy, so the clean-up must not remove it
        if stuck:
            raise StopRun(f"Saving failed ({e}). These files changed and could not be put back: {'; '.join(stuck)}. "
                          f"Every other file is as it was before this run.") from None
        raise StopRun(f"Saving failed ({e}). Every file is as it was before this run, and {len(done)} file(s) already saved were put back.") from None


# ------------------------------------------------------------------ dates

def parse_dates(values, date_format, column):
    """Return a list of date objects (or None for blanks). Stops on any value that does not fit."""
    if not date_format:
        raise StopRun(f"Column '{column}': date_format is blank. A date like 03/04/2026 can be read two ways, so the script "
                      f"never guesses. Set date_format in SETTINGS, for example \"%m/%d/%Y\" for 08/05/2024.")
    out, bad = [], []
    for i, raw in enumerate(values):
        raw = str(raw).strip()
        if raw == "":
            out.append(None)
            continue
        try:
            out.append(datetime.strptime(raw, date_format).date())
        except ValueError:
            bad.append(i + 2)   # +2: header row, then 1-based rows
    if bad:
        raise StopRun(f"Column '{column}': {len(bad)} date(s) do not match the date_format "
                      f"setting '{date_format}' (first few rows: {bad[:8]}). Fix the setting or the file.")
    return out


def week_number(d, season_start):
    return (d - season_start).days // 7 + 1


def session_sort(label):
    """The order of session identifiers within one date: numbers by size (2 before 10), then text (AM before PM)."""
    value = to_float(label)
    return (0, value, "") if value is not None else (1, 0.0, norm(label))


def session_numbers(dates, season_start, labels=None):
    """Each session's place among the different sessions of its week, across the whole file: 1, 2, ...
    A session is a date, plus the identifier in session_column if there is one. Everyone in the same session shares
    a number, and no calendar date is released."""
    keys = [(d, session_sort(labels[i]) if labels else (0, 0.0, "")) for i, d in enumerate(dates)]
    by_week = defaultdict(set)
    for k in keys:
        if k[0]:
            by_week[week_number(k[0], season_start)].add(k)
    order = {w: {k: i for i, k in enumerate(sorted(ks), start=1)} for w, ks in by_week.items()}
    return [order[week_number(k[0], season_start)][k] if k[0] else "" for k in keys]


# ------------------------------------------------------------------ the key

def load_key(path):
    """Returns ({original_id: code}, {original_id: first_coded}). Stops if the key cannot be trusted."""
    key, first_coded = {}, {}
    if os.path.islink(path):
        raise StopRun(f"Refusing to run: the key file '{path}' is a symbolic link.")
    if not os.path.exists(path):
        return key, first_coded
    headers, rows = read_table(path, "key file")
    if any(c not in headers for c in KEY_COLUMNS):
        raise StopRun(f"The key file '{path}' must have the columns {list(KEY_COLUMNS)}. It was not changed. Restore the backup beside it.")
    codes = set()
    for row_num, row in enumerate(rows, start=2):
        original, code = (row["original_id"] or "").strip(), (row["code"] or "").strip()
        if not original or not code:
            raise StopRun(f"The key file '{path}', row {row_num}, has a blank athlete or a blank code. It was not changed. Fix it or restore the backup beside it.")
        if original in key:
            raise StopRun(f"The key file '{path}', row {row_num}, gives one athlete a second code. It was not changed. Fix it or restore the backup beside it.")
        if code in codes:
            raise StopRun(f"The key file '{path}', row {row_num}, gives two athletes the same code. It was not changed. Fix it or restore the backup beside it.")
        codes.add(code)
        key[original] = code
        first_coded[original] = row.get("first_coded", "")
    return key, first_coded


def prepare_key(path, backup, key, first_coded, temps):
    """Check the new key on disk and copy the previous one for the backup. Returns the moves for publish_all; nothing
    at the destinations changes here."""
    today = date.today().isoformat()

    def write(f):
        w = csv.writer(f)
        w.writerow(["original_id", "code", "first_coded"])
        for original, code in sorted(key.items(), key=lambda kv: kv[1]):
            w.writerow([original, code, first_coded.get(original) or today])

    tmp = write_temp(path, temps, write)
    if load_key(tmp)[0] != key:
        raise StopRun("The new key file did not read back correctly, so it was not saved.")
    moves = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            previous = f.read()
        moves.append((write_temp(backup, temps, lambda f: f.write(previous)), backup, True))
    return moves + [(tmp, path, True)]


# ------------------------------------------------------------------ checks

def likely_name_variants(ids):
    """Pairs like ('J. Okafor', 'Jamal Okafor') or ('jamal okafor', 'Jamal Okafor'). Reported, never merged."""
    pairs = set()
    parsed = []
    for raw in ids:
        parts = norm(raw).replace(".", " ").split()
        if parts:
            parsed.append((raw, parts[0], parts[-1]))
    for i, (a, a_first, a_last) in enumerate(parsed):
        for b, b_first, b_last in parsed[i + 1:]:
            if a == b:
                continue
            if norm(a) == norm(b):
                pairs.add((a, b))
            elif a_last == b_last and a_first[0] == b_first[0] and (
                    len(a_first) == 1 or len(b_first) == 1 or a_first.startswith(b_first) or b_first.startswith(a_first)):
                pairs.add((a, b))
    return sorted(pairs)


def smallest_group(released, trait_names, minimum):
    """released: [(code, {trait: value})], one entry per row as it appears in the output. An athlete recorded with
    two values counts in both groups. Returns (groups below minimum, size of the smallest group)."""
    groups = defaultdict(set)
    for code, traits in released:
        groups[tuple(traits.get(t, "") for t in trait_names)].add(code)
    small = {combo: codes for combo, codes in groups.items() if len(codes) < minimum}
    smallest = min((len(c) for c in groups.values()), default=0)
    return small, smallest


def suggest_coarser(released, trait_names, minimum):
    """The fewest traits that, if dropped from the shared file, leave every group at or above the minimum."""
    for n_drop in range(1, len(trait_names)):
        for dropped in combinations(trait_names, n_drop):
            remaining = [x for x in trait_names if x not in dropped]
            small, _ = smallest_group(released, remaining, minimum)
            if not small:
                return (f"share only {', '.join(remaining)} (drop {', '.join(dropped)}) and no group is under {minimum}")
    singles = []
    for t in trait_names:
        small, smallest = smallest_group(released, [t], minimum)
        singles.append(f"{t} alone leaves a group of {smallest}")
    return ("even one trait on its own is not enough: " + "; ".join(singles)
            + ". Merge the rare values (a rare position into a broader group, a sparse band into its neighbour) "
              "or drop every trait column")


def verify_output(path, kinds, ids, code_to_id):
    """Re-read every physical cell of the finished file, by position.
    Returns (problems, cells that look like a name, {number column: rows repeating that row's own ID, when only some do})."""
    pattern = id_pattern(ids)
    problems = Counter()
    name_hits = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        rows = list(reader)
    if len(header) != len(kinds) or len({norm(h) for h in header}) != len(header):
        problems["headings that do not match the expected columns"] += 1
    for h in header:
        if pattern.search(scan_form(h)):
            problems["a heading contained an original ID or name"] += 1
    copies, filled = Counter(), Counter()
    for row_num, row in enumerate(rows, start=2):
        if len(row) != len(header):
            problems["rows with the wrong number of cells"] += 1
            continue
        original = code_to_id.get(row[kinds.index("code")]) if "code" in kinds else None
        if original is None:
            problems["rows without a valid athlete code"] += 1
        for i, (cell, kind) in enumerate(zip(row, kinds)):
            if kind in GENERATED_KINDS or cell == "":
                continue
            if kind == "number":
                if to_float(cell) is None:
                    problems["text left in a number column"] += 1
                filled[i] += 1
                copies[i] += to_float(original) is not None and to_float(cell) == to_float(original)
            else:
                if pattern.search(scan_form(cell)):
                    problems["cells containing an original ID"] += 1
                if NAME_SHAPED.search(cell):
                    name_hits[header[i]].append(row_num)
    partial_copies = {}
    for i, n in filled.items():     # a number column that repeats each row's own numeric ID is a copy of the ID
        if n and copies[i] == n:
            problems[f"column '{header[i]}' repeats the athlete ID"] += 1
        elif copies[i]:             # in only some rows it may be chance, so a person has to look
            partial_copies[header[i]] = copies[i]
    return problems, name_hits, partial_copies


# ------------------------------------------------------------------ reading

def read_table(path, what="input file"):
    """(headings, rows as dicts). Any file that cannot be read becomes a clear stop, not a crash."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            rows = list(reader)
    except UnicodeDecodeError:
        raise StopRun(f"The {what} '{path}' is not saved as UTF-8. In Excel: File, Save As, CSV UTF-8, then run again.") from None
    except csv.Error as e:
        raise StopRun(f"The {what} '{path}' could not be read as a CSV file ({e}).") from None
    return headers, rows


def read_export(path):
    """Rows as dicts keyed by STRIPPED headings. Returns (headers, rows, how many headings were trimmed)."""
    raw_headers, raw_rows = read_table(path)
    headers = [h.strip() for h in raw_headers]
    trimmed = sum(1 for a, b in zip(raw_headers, headers) if a != b)
    if len(set(headers)) != len(headers):
        raise StopRun("The input has two columns with the same heading. Rename one and run again.")
    rows = [{h: (r.get(rh) or "") for rh, h in zip(raw_headers, headers)} for r in raw_rows]
    return headers, rows, trimmed


# ------------------------------------------------------------------ the run

def run(settings, profile_name, input_override=None, output_override=None, key_override=None, overwrite=False):
    """Code one export. Returns a dict with the output path, key path, both reports and the check results."""
    temps = []
    try:
        return _run(settings, profile_name, input_override, output_override, key_override, overwrite, temps)
    finally:
        for tmp in temps:       # only the temporary files this run created; never a file that was already there
            if os.path.exists(tmp):
                os.remove(tmp)


def _run(settings, profile_name, input_override, output_override, key_override, overwrite, temps):
    report = [f"deidentify.py version {SCRIPT_VERSION}   run on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
              "Output is CODED data, not anonymous data. Review the warnings below before sharing.",
              "Every warning says what to do: FIX BEFORE USING RESULTS, DO NOT SHARE, or INFORMATION ONLY.", ""]
    private = ["PRIVATE - DO NOT SHARE. This report can name athletes. Keep it with the key, off shared drives and out of every AI tool.",
               f"deidentify.py version {SCRIPT_VERSION}   run on {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    if profile_name not in settings["profiles"]:
        raise StopRun(f"No profile called '{profile_name}'. Profiles in SETTINGS: {', '.join(settings['profiles'])}.")
    p = {k: ([x.strip() for x in v] if isinstance(v, list) else v.strip() if isinstance(v, str) else v)
         for k, v in settings["profiles"][profile_name].items()}
    input_file = input_override or p["input_file"]
    output_folder = output_override or settings["output_folder"]
    key_folder = key_override or settings["key_folder"]
    key_path = os.path.join(key_folder, settings["key_file"])
    stem = os.path.splitext(os.path.basename(input_file))[0]
    output_file = os.path.join(output_folder, "coded_" + os.path.basename(input_file))
    report_file = os.path.join(output_folder, f"deidentify_report_{stem}.txt")
    private_file = os.path.join(key_folder, f"PRIVATE_deidentify_report_{stem}.txt")
    backup_file = os.path.splitext(key_path)[0] + "_backup.csv"
    minimum = int(settings["minimum_group_size"])

    # ---- safety, before anything is written: never write over an input or an existing file, never put the key with the output
    if not os.path.exists(input_file):
        raise StopRun(f"Input file not found: {input_file}")
    if same_file(output_folder, os.path.dirname(os.path.abspath(input_file))):
        raise StopRun("Refusing to run: output_folder is the folder that holds the input file. Use a new folder.")
    if is_inside(key_folder, output_folder) or is_inside(output_folder, key_folder):
        raise StopRun("Refusing to run: the key folder and the output folder must be separate, and neither may be inside the other.")
    if same_file(key_path, input_file):
        raise StopRun(f"Refusing to run: '{key_path}' is the input file. Choose a different key folder.")
    if os.path.isdir(key_path):
        raise StopRun(f"Refusing to run: the key '{key_path}' is a folder. Move or rename it.")
    for folder in (output_folder, key_folder):
        check_folder(folder)
    for out in (output_file, report_file, private_file):
        check_output_path(out, input_file, overwrite)
    check_backup_path(backup_file, [input_file, output_file, report_file, private_file, key_path])
    for a, b in combinations((output_file, report_file, private_file, key_path), 2):
        if same_file(a, b):
            raise StopRun(f"Refusing to run: '{a}' and '{b}' are the same file. Choose different folders.")

    headers, rows, trimmed = read_export(input_file)
    if not rows:
        raise StopRun(f"No athlete records found in '{os.path.basename(input_file)}': the file has no rows below its headings.")
    id_col = p["athlete_id_column"]
    keep = list(p["keep_columns"])
    session_col = p.get("session_column", "")
    if session_col and session_col in keep:
        raise StopRun(f"session_column '{session_col}' is also in keep_columns. Take it out of keep_columns: it is used to number the "
                      f"sessions, and the output's Session column replaces it.")
    missing = [c for c in keep + [id_col] + ([session_col] if session_col else []) if c not in headers]
    if missing:
        raise StopRun(f"These columns are in SETTINGS but not in the file: {missing}. Headings must match exactly "
                      f"(spaces at the ends are ignored). The file's headings are: {headers}")
    if id_col not in keep:
        keep.insert(0, id_col)

    # ---- column types: anything the settings do not call something else is a number
    pos_col, cls_col = p.get("position_column", ""), p.get("class_year_column", "")
    h_col, m_col = p.get("height_column", ""), p.get("body_mass_column", "")
    declared = {k.strip(): v for k, v in p.get("column_types", {}).items()}
    bad_types = sorted({v for v in declared.values() if v not in COLUMN_TYPES})
    if bad_types:
        raise StopRun(f"column_types can only be {sorted(COLUMN_TYPES)}. Found: {bad_types}.")
    extra_ids = [c for c, t in declared.items() if t == "id" and c != id_col and c in keep]
    if extra_ids:
        raise StopRun(f"{extra_ids} are marked as ID columns, but only athlete_id_column is replaced by a code. Remove them from keep_columns.")
    date_cols = [c for c in keep if c in p.get("date_columns", []) or declared.get(c) == "date"]
    allowed_text = [c for c in p.get("allowed_text_columns", []) if c in keep]
    event_cols = [c for c in p.get("event_columns", []) if c in keep]
    category_cols = {c for c in keep if declared.get(c) == "category"} | {c for c in (pos_col, cls_col) if c} | set(event_cols)
    asym_cols = [c for c in keep if c != id_col and c not in allowed_text and ("(asym)" in c.casefold() or c in p.get("asymmetry_columns", []))]
    permitted = {k.strip(): {norm(v): str(v).strip() for v in vs} for k, vs in p.get("allowed_values", {}).items()}
    no_list = sorted(c for c in category_cols if c != pos_col and c not in allowed_text and not permitted.get(c))
    if no_list:
        raise StopRun(f"These category or event columns have no list of permitted values: {no_list}. Add each one to allowed_values in SETTINGS, "
                      f"for example \"allowed_values\": {{\"Session Type\": [\"Training\", \"Match\"]}}. Anything else in the column is then left blank, "
                      f"because these fields can hold identifying notes.")

    # ---- athlete IDs -> codes (the key file is only written once the output has passed its checks)
    aliases = {norm(k): v for k, v in settings.get("id_aliases", {}).items()}
    blank_id = 0
    kept_rows = []
    for r in rows:
        raw_id = " ".join(str(r[id_col]).split())
        if raw_id == "":
            blank_id += 1
            continue
        r = dict(r)
        r[id_col] = aliases.get(norm(raw_id), raw_id)
        kept_rows.append(r)
    if not kept_rows:
        raise StopRun(f"No athlete records found in '{os.path.basename(input_file)}': every row has a blank '{id_col}'.")
    original_ids = sorted({r[id_col] for r in kept_rows})
    all_ids = set(original_ids) | set(settings.get("id_aliases", {}))
    pattern = id_pattern(all_ids)
    if pattern.search(scan_form(os.path.basename(input_file))):
        raise StopRun("The input file's name contains an athlete ID, and the coded file is named after it. Rename the input file and run again.")

    shown = lambda h: "(a heading that contains an ID; see the private report)" if pattern.search(scan_form(h)) else h
    report.append(f"Input: {os.path.basename(input_file)}  ({len(rows)} rows, {len(headers)} columns)")
    if trimmed:
        report.append(f"  {trimmed} heading(s) had spaces at the start or end; those spaces were removed.")
    dropped = [h for h in headers if h not in keep]
    report_columns_at = len(report)
    if blank_id:
        report.append(f"  {FIX}: {blank_id} row(s) had a blank '{id_col}' and were left out.")

    key, first_coded = load_key(key_path)
    reused = sum(1 for i in original_ids if i in key)
    key_changed = False
    for i in original_ids:
        if i not in key:
            key[i] = new_code(set(key.values()))
            key_changed = True
    report += ["", "ATHLETE CODES",
               f"  {len(original_ids)} athletes in this file: {reused} already had a code in the key, "
               f"{len(original_ids) - reused} received a new one.",
               "  The key and the private report are saved in the key folder. Keep them private; never upload them."]
    short_numeric = sum(1 for i in original_ids if i.isdigit() and len(i) < SHORT_NUMERIC_ID_DIGITS)
    if short_numeric:
        report.append(f"  {INFO}: {short_numeric} athlete ID(s) are numbers shorter than {SHORT_NUMERIC_ID_DIGITS} digits, like jersey numbers. A short number is "
                      f"hard to tell from a real measurement, so a copy of one can get past the checks. Non-numeric or long IDs are safer.")
    if CLOUD_FOLDER.search(os.path.realpath(key_folder)):
        report.append(f"  {NO_SHARE}: the key folder looks like a cloud-synced folder. Move it somewhere that does not sync.")
    variants = likely_name_variants(original_ids)
    private += ["NAME VARIANTS", "  Each spelling got its OWN code. If two are one athlete, add them to id_aliases in SETTINGS and run again:"]
    private += [f"      '{a}'  and  '{b}'" for a, b in variants] or ["      none found."]
    if variants:
        report.append(f"  {FIX}: {len(variants)} pair(s) of IDs look like the same person written two ways. The pairs are in the private report.")

    # ---- values: units read from the headings, numbers checked, text removed unless the coach allowed it
    renamed = {}
    conversions = {}
    blanked = {}
    dropped_text = []
    not_permitted = {}
    report += ["", "UNITS AND VALUES"]
    for col in keep:
        if col == id_col or col in date_cols or col in asym_cols or col in allowed_text:
            continue
        if col == pos_col:
            continue        # position_groups is the permitted list for positions; handled with the traits below
        if col in category_cols:
            others = Counter()
            for r in kept_rows:
                raw = str(r[col]).strip()
                if raw and norm(raw) not in permitted[col]:
                    others[raw] += 1
                r[col] = permitted[col].get(norm(raw), "")
            if others:
                not_permitted[col] = sum(others.values())
                report.append(f"  {FIX}: {not_permitted[col]} value(s) in '{shown(col)}' are not on its allowed_values list and were left blank. "
                              f"They are listed in the private report: add any safe label to the list, and run again.")
                private += ["", f"VALUES LEFT BLANK IN '{col}' (not on its allowed_values list)"] + [f"  '{k}' ({n} rows)" for k, n in others.most_common()]
            continue
        u = unit_of(col)
        if col == m_col and u not in MASS_UNITS:
            raise StopRun(f"body_mass_column '{col}' has no mass unit in its heading. Add [kg] or [lb] to the heading in the "
                          f"file (or set body_mass_column to '' if you do not want it banded).")
        if col == h_col and u not in HEIGHT_UNITS:
            raise StopRun(f"height_column '{col}' must say cm, in or m in its heading (found '{u or 'no unit'}'). Fix the heading in the "
                          f"file (or set height_column to '' if you do not want it banded).")
        if col == h_col:
            new_unit, factor = "cm", HEIGHT_UNITS[u]
        elif u in LENGTH_UNITS:
            new_unit, factor = LENGTH_UNITS[u]
        elif u in MASS_UNITS:
            new_unit, factor = MASS_UNITS[u]
        else:
            new_unit, factor = u, 1.0
        filled = [r for r in kept_rows if str(r[col]).strip() != ""]
        not_numbers = sum(1 for r in filled if to_float(r[col]) is None)
        if filled and not_numbers == len(filled) and col not in (h_col, m_col):
            dropped_text.append(col)
            report.append(f"  {NO_SHARE}: '{shown(col)}' holds text, not numbers, so it was dropped. Text can name people. To keep it, "
                          f"list it under allowed_text_columns (or as a category in column_types) and check every value yourself.")
            continue
        for r in kept_rows:
            v = to_float(r[col])
            if v is None:
                r[col] = ""
            elif factor != 1.0:
                r[col] = fmt_number(v * factor)
            else:
                r[col] = str(r[col]).strip()
        if not_numbers:
            blanked[col] = not_numbers
            report.append(f"  {FIX}: {not_numbers} value(s) in '{shown(col)}' were not numbers and were left blank.")
        if factor != 1.0:
            renamed[col] = converted_header(col, u, new_unit)
            conversions[col] = (u, new_unit)
            report.append(f"  '{shown(col)}': values read in {u} and converted to {new_unit} (x {factor}); heading becomes '{shown(renamed[col])}'.")
    if not conversions:
        report.append("  no conversions needed: every unit-bearing heading is already in cm, kg or another unit the script leaves alone.")
    keep = [c for c in keep if c not in dropped_text]
    for c in allowed_text:
        report.append(f"  {NO_SHARE}: '{shown(c)}' is free text you chose to keep (allowed_text_columns). Read every value before sharing: "
                      f"this script cannot find every name.")
    report[report_columns_at:report_columns_at] = [
        "", "COLUMNS", f"  kept ({len(keep)}): {', '.join(shown(c) for c in keep)}",
        f"  dropped ({len(dropped) + len(dropped_text)}): {', '.join(shown(c) for c in dropped + dropped_text) or '(none)'}"]
    private += ["", "ALL COLUMN HEADINGS AS EXPORTED", "  " + ", ".join(headers)]

    # ---- dates -> weeks and sessions
    try:
        season_start = datetime.strptime(settings["season_start_date"], "%Y-%m-%d").date()
    except ValueError:
        raise StopRun(f"season_start_date '{settings['season_start_date']}' must be written year-month-day, like 2024-08-05.") from None
    week_cols, session_cols = {}, {}
    report += ["", "DATES"]
    for col in date_cols:
        dates = parse_dates([r[col] for r in kept_rows], p.get("date_format", ""), col)
        weeks = [week_number(d, season_start) if d else "" for d in dates]
        early = sum(1 for w in weeks if w != "" and w < 1)
        week_cols[col] = weeks
        session_cols[col] = session_numbers(dates, season_start, [r[session_col] for r in kept_rows] if session_col else None)
        span = [w for w in weeks if w != ""]
        report.append(f"  '{shown(col)}' -> 'Week' and 'Session' (week 1 starts {season_start}; sessions are numbered by date"
                      f"{' and ' + repr(shown(session_col)) if session_col else ''} within each week); "
                      f"{len(span)} dates converted, weeks {min(span) if span else '-'} to {max(span) if span else '-'}.")
        if early:
            report.append(f"  {INFO}: {early} date(s) fall before season_start_date and have week numbers of 0 or less.")

    # ---- conflicts: one ID, two heights (on the converted values, before banding)
    heights = defaultdict(set)
    if h_col and h_col in keep:
        for r in kept_rows:
            v = to_float(r[h_col])
            if v is not None:
                heights[r[id_col]].add(v)
    conflicts = {i: set(hs) for i, hs in heights.items() if max(hs) - min(hs) > float(settings["height_tolerance_cm"])}

    # ---- traits: bands, position groups, asymmetry split
    groups_map = settings.get("position_groups", {})
    report += ["", "TRAITS"]
    unknown_pos = Counter()
    for r in kept_rows:
        if pos_col and pos_col in keep:
            raw = str(r[pos_col]).strip()
            if raw and raw not in groups_map and raw not in groups_map.values():
                unknown_pos[raw] += 1
                raw = ""
            r[pos_col] = groups_map.get(raw, raw)
        if h_col and h_col in keep:
            v = to_float(r[h_col])
            r[h_col] = band_label(v, float(settings["height_band_cm"]), "cm") if v is not None else ""
        if m_col and m_col in keep:
            v = to_float(r[m_col])
            r[m_col] = band_label(v, float(settings["body_mass_band_kg"]), "kg") if v is not None else ""
    if pos_col and pos_col in keep:
        report.append(f"  '{shown(pos_col)}' replaced by position groups from SETTINGS.")
        if unknown_pos:
            not_permitted[pos_col] = sum(unknown_pos.values())
            report.append(f"  {FIX}: {not_permitted[pos_col]} position value(s) are not in position_groups and were left blank. "
                          f"They are listed in the private report. Add any real position to position_groups, and run again.")
            private += ["", "POSITIONS NOT IN position_groups"] + [f"  '{k}' ({n} rows)" for k, n in unknown_pos.most_common()]
    for col, width, unit in ((h_col, settings["height_band_cm"], "cm"), (m_col, settings["body_mass_band_kg"], "kg")):
        if col and col in keep:
            report.append(f"  '{shown(renamed.get(col, col))}' replaced by {width} {unit} bands.")
    asym_bad = defaultdict(list)
    for col in asym_cols:
        for idx, r in enumerate(kept_rows):
            raw = str(r[col]).strip()
            if raw == "":
                r[col], r[col + " side"] = "", ""
                continue
            m = ASYM_VALUE.match(raw)
            if m:
                r[col], r[col + " side"] = m.group(1), m.group(2).upper()
            else:
                r[col], r[col + " side"] = "", ""
                asym_bad[col].append(idx + 2)
        report.append(f"  '{shown(col)}' split into a number and a '{shown(col)} side' column (L or R).")
        if asym_bad[col]:
            report.append(f"  {FIX}: {len(asym_bad[col])} value(s) in '{shown(col)}' could not be read as a number plus L or R "
                          f"and were left blank (rows {asym_bad[col][:10]}).")
    if not any((pos_col and pos_col in keep, h_col and h_col in keep, m_col and m_col in keep, asym_cols)):
        report.append("  no trait columns in this profile.")

    fixed_conf = defaultdict(lambda: defaultdict(set))
    for r in kept_rows:
        for col in (pos_col, cls_col):
            if col and col in keep and str(r[col]).strip():
                fixed_conf[r[id_col]][col].add(str(r[col]).strip())
    for i, cols in fixed_conf.items():
        for col, vals in cols.items():
            if len(vals) > 1:
                conflicts.setdefault(i, set()).add(f"{col}: {sorted(vals)}")
    report += ["", "ID CONFLICTS"]
    private += ["", "ID CONFLICTS"]
    if conflicts:
        report.append(f"  {FIX}: {len(conflicts)} ID(s) carry conflicting fixed traits. Two people may share one ID, "
                      f"or a value was mistyped. The details are in the private report.")
        for i, hs in sorted(conflicts.items(), key=lambda kv: key[kv[0]]):
            nums = sorted(x for x in hs if isinstance(x, float))
            words = sorted(x for x in hs if isinstance(x, str))
            detail = (f"heights {nums}" if nums else "") + ("; " if nums and words else "") + "; ".join(words)
            private.append(f"  {i} ({key[i]}): {detail}")
    else:
        report.append("  none found.")
        private.append("  none found.")

    # ---- uniqueness, counting DIFFERENT athletes, on the values exactly as they appear in the output
    trait_cols = [c for c in (pos_col, cls_col, m_col, h_col) if c and c in keep]
    released = [(key[r[id_col]], {c: str(r[c]).strip() for c in trait_cols}) for r in kept_rows]
    label = lambda c: renamed.get(c, c)
    report += ["", f"UNIQUENESS CHECK  (minimum group size {minimum}; counts DIFFERENT athletes, not rows)"]
    private += ["", "UNIQUENESS CHECK: the groups that are too small"]
    checks = {"athlete_level_small_groups": {}, "row_level_small_groups": [], "trait_columns": [label(c) for c in trait_cols]}
    if trait_cols:
        small, smallest = smallest_group(released, trait_cols, minimum)
        checks["athlete_level_small_groups"] = {" | ".join(k): sorted(v) for k, v in small.items()}
        report.append(f"  (a) Athlete level, on {', '.join(shown(label(c)) for c in trait_cols)}: smallest group has {smallest} athlete(s).")
        if small:
            report.append(f"      {NO_SHARE}: {len(small)} combination(s) of traits are shared by fewer than {minimum} athletes, "
                          f"covering {len(set().union(*small.values()))} athlete(s). Anyone who knows the squad could pick them out. "
                          f"The combinations are in the private report.")
            for combo, codes in sorted(small.items(), key=lambda kv: len(kv[1])):
                private.append(f"  (a) {len(codes)} athlete(s): " + ", ".join(f"{label(c)}={v or '(blank)'}" for c, v in zip(trait_cols, combo)))
            report.append(f"      Suggestion: {suggest_coarser(released, trait_cols, minimum)}.")
        else:
            report.append(f"      OK: every combination of traits is shared by at least {minimum} athletes.")
    else:
        report.append("  (a) Athlete level: no trait columns kept, so nothing to check.")

    event_cols = [c for c in event_cols if c in keep]
    row_cols = (["Week", "Session"] if week_cols else []) + ([pos_col] if pos_col and pos_col in keep else []) + event_cols
    if event_cols and week_cols:
        first_date_col = next(iter(week_cols))
        combos = defaultdict(set)
        for idx, r in enumerate(kept_rows):
            if not any(str(r[c]).strip() for c in event_cols):
                continue    # no event in this row
            combo = (week_cols[first_date_col][idx], session_cols[first_date_col][idx]) + tuple(str(r[c]).strip() for c in row_cols[2:])
            combos[combo].add(key[r[id_col]])
        small_rows = {k: v for k, v in combos.items() if len(v) < minimum}
        checks["row_level_small_groups"] = [dict(zip(row_cols, k)) | {"athletes": len(v)} for k, v in small_rows.items()]
        report.append(f"  (b) Row level, on {', '.join(shown(c) for c in row_cols)} for rows with an event entry: "
                      f"{len(combos)} combination(s) found.")
        if small_rows:
            report.append(f"      {NO_SHARE}: {len(small_rows)} combination(s) point to fewer than {minimum} athletes. "
                          f"The combinations are in the private report.")
            for k, v in sorted(small_rows.items(), key=lambda kv: (len(kv[1]), str(kv[0]))):
                private.append(f"  (b) {len(v)} athlete(s): " + ", ".join(f"{c}={x or '(blank)'}" for c, x in zip(row_cols, k)))
            report.append("      Suggestion: report events by month or by 4-week block instead of week, drop the position "
                          "from the shared file, or describe the event more broadly (for example 'injury' only).")
        else:
            report.append(f"      OK: every event combination is shared by at least {minimum} athletes.")
    else:
        report.append("  (b) Row level: no event columns kept (or no date column), so nothing to check.")

    # ---- the coded file: first the headings, which must all be different
    out_cols = []            # (output heading, source key in the row dicts, kind)
    for c in keep:
        if c == id_col:
            out_cols.append(("Athlete Code", c, "code"))
        elif c in week_cols:
            out_cols.append(("Week", c, "week"))
            out_cols.append(("Session", c, "session"))
        elif c in (h_col, m_col):
            out_cols.append((renamed.get(c, c), c, "band"))
        elif c in allowed_text or c in category_cols:
            out_cols.append((renamed.get(c, c), c, "text"))
        else:
            out_cols.append((renamed.get(c, c), c, "number"))
            if c in asym_cols:
                out_cols.append((c + " side", c + " side", "side"))
    seen = Counter(norm(h) for h, _, _ in out_cols)
    repeated = sorted({h for h, _, _ in out_cols if seen[norm(h)] > 1})
    if repeated:
        raise StopRun(f"Two output columns would both be called {repeated}. A second column under one heading can hide values "
                      f"from every check. Drop one, or rename it in the file, and run again.")

    # ---- a text cell a spreadsheet would run as a formula gets an apostrophe in front, so it stays text
    guarded = Counter()
    for _, src, kind in out_cols:
        if kind == "text":
            for r in kept_rows:
                value = str(r[src]).strip()
                if value.startswith(FORMULA_STARTS):
                    r[src] = "'" + value
                    guarded[src] += 1
    if guarded:
        report += ["", "SPREADSHEET FORMULAS"]
        report += [f"  {INFO}: {n} value(s) in '{shown(c)}' started with =, +, - or @, which a spreadsheet can run as a formula. "
                   f"An apostrophe was added in front of each." for c, n in guarded.items()]

    def write_coded(f):
        w = csv.writer(f)
        w.writerow([h for h, _, _ in out_cols])
        for idx, r in enumerate(kept_rows):
            w.writerow([key[r[src]] if kind == "code" else week_cols[src][idx] if kind == "week"
                        else session_cols[src][idx] if kind == "session" else r.get(src, "")
                        for _, src, kind in out_cols])

    tmp_output = write_temp(output_file, temps, write_coded)

    # ---- verify: no original ID anywhere in the output, before anything is moved into place
    report += ["", "VERIFICATION"]
    code_to_id = {code: i for i, code in key.items()}
    problems, name_hits, partial_copies = verify_output(tmp_output, [k for _, _, k in out_cols], all_ids, code_to_id)
    if problems:
        details = "; ".join(f"{n} x {what}" for what, n in problems.items())
        raise StopRun(f"VERIFICATION FAILED: {details}. The new output was not saved, and no existing file was changed. "
                      f"Check the kept columns and headings for one that repeats an athlete's name or ID. A short numeric ID can match a heading "
                      f"such as 'Fatigue (1-5)': if that is the cause, use longer or non-numeric IDs.")
    report.append(f"  OK: every cell of the output was re-read and none of the {len(original_ids)} original IDs appears in it.")
    if name_hits:
        report.append(f"  {NO_SHARE}: some kept values look like a person's name (two capitalised words, or an initial and "
                      "a surname). Check these cells before sharing; a coach's or physio's name is still a name. Name detection is not comprehensive:")
        for col, rs in name_hits.items():
            report.append(f"      column '{shown(col)}': {len(rs)} cell(s), rows {rs[:10]}{'...' if len(rs) > 10 else ''}")
    for col, n in partial_copies.items():
        report.append(f"  {NO_SHARE}: in number column '{shown(col)}', {n} value(s) equal that row's own athlete ID. It may be chance, "
                      f"because real measurements can coincide, but check the column before sharing.")
    report += ["", f"Coded file: {os.path.basename(output_file)}", f"This report: {os.path.basename(report_file)}", "",
               "Remaining risk must be reviewed by a person. This script reduces re-identification risk; "
               "it does not make data anonymous."]

    # ---- the shareable report gets the same check as the coded file. An ID made only of digits is left out of this one
    # scan, because the report is full of counts and dates; the headings and file name it quotes were already checked for those.
    if id_pattern(all_ids, with_letters_only=True).search(scan_form("\n".join(report))):
        raise StopRun("The shareable report would contain an athlete's ID or name, so nothing was saved and no existing file was changed. "
                      "Check the headings and the file name. An ID that is one ordinary word, such as Will or Ward, also matches the report's "
                      "own wording: if that is the cause, use a fuller or non-word ID.")

    # ---- everything passed. Check all the moves are ready, then make them together
    key_moves = prepare_key(key_path, backup_file, key, first_coded, temps) if key_changed or not os.path.exists(key_path) else []
    tmp_report = write_temp(report_file, temps, lambda f: f.write("\n".join(report) + "\n"))
    tmp_private = write_temp(private_file, temps, lambda f: f.write("\n".join(private) + "\n"))
    publish_all(key_moves + [(tmp_output, output_file, False), (tmp_report, report_file, False), (tmp_private, private_file, True)], temps)
    return {"output_file": output_file, "report_file": report_file, "private_report_file": private_file, "key_path": key_path,
            "report": report, "private_report": private, "checks": checks,
            "conflicts": {key[i]: sorted(map(str, v)) for i, v in conflicts.items()},
            "name_variants": variants, "name_shaped": dict(name_hits), "rows": len(kept_rows),
            "conversions": conversions, "renamed": renamed, "asymmetry_unparsed": {k: v for k, v in asym_bad.items() if v},
            "blanked": blanked, "dropped_text": dropped_text, "not_permitted": not_permitted, "partial_id_copies": partial_copies,
            "formula_guarded": dict(guarded), "output_headers": [h for h, _, _ in out_cols]}


def require_python():
    if sys.version_info < (3, 10):
        print(f"STOPPED: this script needs Python 3.10 or newer, and this is Python {sys.version_info[0]}.{sys.version_info[1]}. "
              "Install the newest Python from python.org (README section 1), open a new terminal window, and try again.")
        sys.exit(1)


def main(argv=None):
    require_python()
    ap = argparse.ArgumentParser(description="Code an athlete monitoring export. Settings are at the top of this file.")
    ap.add_argument("profile", help="which block of SETTINGS to use: " + ", ".join(SETTINGS["profiles"]))
    ap.add_argument("--input", help="code this file instead of the profile's input_file")
    ap.add_argument("--output-folder", help="write here instead of SETTINGS output_folder")
    ap.add_argument("--key-folder", help="key folder instead of SETTINGS key_folder")
    ap.add_argument("--settings-json", help="a JSON file whose values replace the matching SETTINGS entries")
    ap.add_argument("--overwrite", action="store_true", help="replace this run's output files if they already exist")
    a = ap.parse_args(argv)
    settings = json.loads(json.dumps(SETTINGS))   # a copy, so edits never touch the block above
    try:
        if a.settings_json:
            with open(a.settings_json, encoding="utf-8") as f:
                settings.update(json.load(f))
        result = run(settings, a.profile, a.input, a.output_folder, a.key_folder, a.overwrite)
    except StopRun as e:
        print(f"STOPPED: {e}")
        return 1
    except (OSError, ValueError, KeyError, ZeroDivisionError) as e:
        print(f"STOPPED: a file or a setting could not be used ({e}). Nothing was replaced. If a file is open in Excel, close it and run again.")
        return 1
    print("\n".join(result["report"]))
    warnings = sum(1 for line in result["report"] if "WARNING" in line)
    print(f"\nDone. {warnings} warning(s) to review. Output is coded data, not anonymous data.")
    print(f"Key: {result['key_path']}")
    print(f"PRIVATE report, not shown here and never to be shared: {result['private_report_file']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
