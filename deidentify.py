"""
deidentify.py  -  turn an athlete monitoring export into CODED data before it leaves your computer.

What it does, in order:
  1. Keeps only the columns you list below. Every other column is dropped.
  2. Replaces each athlete's name or ID with a random code (for example ATH-K7Q2MX) and writes
     the name-to-code key to a SEPARATE folder that you must keep private.
  3. Reads the unit in each heading's brackets, converts inches to cm and pounds to kg, and renames
     the heading to match.
  4. Converts dates into training week numbers counted from your season start date.
  5. Replaces body mass and height with bands (for example "70-75 kg"), positions with groups, and
     splits asymmetry values like "6.3 L" into a number and a side.
  6. Checks whether any athlete, or any row, could still be picked out, and says so in plain English.
  7. Re-reads the finished file and stops if any original name or ID is still in it.
  8. Writes a report of everything it did.

The result is CODED data, not anonymous data. Someone who knows the squad may still recognise an
athlete from a rare position, an unusual body size, or an injury in a known week. Read the report
and act on its warnings before you share anything. Your institution's compliance office has the
final say on what may be shared.

How to run it (from the folder that holds this file):
    python deidentify.py gps
    python deidentify.py force_plate
    python deidentify.py force_plate_trials
    python deidentify.py wellness
Add "--input some_file.csv" to code a different file with the same settings.

Needs Python 3.10 or newer. Uses nothing outside Python's own standard library. Makes no network calls.
Never changes or overwrites your input file.
"""

SCRIPT_VERSION = "0.2.0"

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

    # Positions as they appear in your export, and the broader group each becomes. Positions that
    # are not listed here are kept as they are and reported. Edit freely.
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
            # "%Y-%m-%d" is 2024-08-05. Leave as "" only if you are sure no date could be read two ways.
            "date_format": "%m/%d/%Y",
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
        # is exported in inches; the script converts it to cm and renames the heading.
        "force_plate": {
            "input_file": "synthetic_data/cmj_season1.csv",
            "athlete_id_column": "Name",
            "keep_columns": ["Name", "Date", "Test Type", "BW [KG]", "Reps", "Additional Load [lb]",
                             "Jump Height (Imp-Mom) in Inches [in]", "RSI-modified [m/s]",
                             "Peak Power / BM [W/kg]", "Countermovement Depth [cm]",
                             "Concentric Impulse % (Asym) (%)", "Peak Landing Force % (Asym) (%)"],
            "date_columns": ["Date"],
            "date_format": "%m/%d/%Y",
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
import sys
from collections import Counter, defaultdict
from datetime import date, datetime

CODE_PREFIX = "ATH-"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O or 1/I, so codes are easy to read aloud
CODE_LENGTH = 6
NAME_SHAPED = re.compile(r"\b[A-Z][a-z]{1,}(?:\s[A-Z]\.?)?\s[A-Z][a-z]{1,}\b|\b[A-Z]\.\s?[A-Z][a-z]{1,}\b")
ASYM_VALUE = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*([LRlr])\s*$")

# units the script understands, as they appear inside [...] or (...) at the end of a heading
LENGTH_UNITS = {"cm": ("cm", 1.0), "in": ("cm", 2.54), "inch": ("cm", 2.54), "inches": ("cm", 2.54), "mm": ("cm", 0.1), "m": ("m", 1.0)}
MASS_UNITS = {"kg": ("kg", 1.0), "lb": ("kg", 0.45359237), "lbs": ("kg", 0.45359237)}
OTHER_UNITS = {"n", "w", "w/kg", "m/s", "n/s", "ms", "s", "%", "n s", "km/h", "min"}
UNIT_GROUP = re.compile(r"[\[(]([^\[\]()]+)[\])]")


class StopRun(Exception):
    """Raised when the script must stop. The message is written for the coach."""


# ------------------------------------------------------------------ small helpers

def norm(text):
    """Lower-case, single-spaced version of a value, for comparisons only."""
    return " ".join(str(text).split()).casefold()


def to_float(text):
    try:
        return float(str(text).strip())
    except ValueError:
        return None


def band_label(value, width, unit):
    lower = math.floor(value / width) * width
    fmt = (lambda x: str(int(x))) if float(width).is_integer() else (lambda x: f"{x:g}")
    return f"{fmt(lower)}-{fmt(lower + width)} {unit}"


def new_code(existing):
    while True:
        code = CODE_PREFIX + "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code not in existing:
            return code


def mode(values):
    """The most common value in a list, ignoring blanks."""
    values = [v for v in values if v != ""]
    return Counter(values).most_common(1)[0][0] if values else ""


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


# ------------------------------------------------------------------ dates

COMMON_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y", "%d/%m/%y", "%d-%m-%Y", "%Y/%m/%d"]


def parse_dates(values, date_format, column, report):
    """Return a list of date objects (or None for blanks). Stops on any value that does not fit."""
    out, bad = [], []
    if date_format:
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
    # No format given: every value must be readable in exactly one way.
    ambiguous = []
    for i, raw in enumerate(values):
        raw = str(raw).strip()
        if raw == "":
            out.append(None)
            continue
        readings = set()
        for fmt in COMMON_FORMATS:
            try:
                readings.add(datetime.strptime(raw, fmt).date())
            except ValueError:
                pass
        if len(readings) == 1:
            out.append(readings.pop())
        elif len(readings) == 0:
            bad.append(i + 2)
        else:
            ambiguous.append((i + 2, raw))
    if ambiguous:
        r, v = ambiguous[0]
        raise StopRun(f"Column '{column}': {len(ambiguous)} date(s) could be read two ways (row {r}: '{v}' "
                      f"could be month/day or day/month). Set date_format in SETTINGS and run again.")
    if bad:
        raise StopRun(f"Column '{column}': {len(bad)} date(s) could not be read (rows {bad[:8]}). "
                      f"Set date_format in SETTINGS.")
    report.append(f"  date_format was blank; every date in '{column}' could be read only one way, so it was used as read.")
    return out


def week_number(d, season_start):
    return (d - season_start).days // 7 + 1


# ------------------------------------------------------------------ the key

def load_key(path):
    key = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key[row["original_id"]] = row["code"]
    return key


def save_key(path, key):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["original_id", "code", "first_coded"])
        for original, code in sorted(key.items(), key=lambda kv: kv[1]):
            w.writerow([original, code, date.today().isoformat()])


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


def smallest_group(rows_by_athlete, trait_names, minimum):
    """rows_by_athlete: {code: {trait: value}}. Returns (groups below minimum, size of the smallest group)."""
    groups = defaultdict(set)
    for code, traits in rows_by_athlete.items():
        groups[tuple(traits.get(t, "") for t in trait_names)].add(code)
    small = {combo: codes for combo, codes in groups.items() if len(codes) < minimum}
    smallest = min((len(c) for c in groups.values()), default=0)
    return small, smallest


def suggest_coarser(rows_by_athlete, trait_names, minimum):
    """The fewest traits that, if dropped from the shared file, leave every group at or above the minimum."""
    from itertools import combinations
    for n_drop in range(1, len(trait_names)):
        for dropped in combinations(trait_names, n_drop):
            remaining = [x for x in trait_names if x not in dropped]
            small, _ = smallest_group(rows_by_athlete, remaining, minimum)
            if not small:
                return (f"share only {', '.join(remaining)} (drop {', '.join(dropped)}) and no group is under {minimum}")
    singles = []
    for t in trait_names:
        small, smallest = smallest_group(rows_by_athlete, [t], minimum)
        singles.append(f"{t} alone leaves a group of {smallest}")
    return ("even one trait on its own is not enough: " + "; ".join(singles)
            + ". Merge the rare values (a rare position into a broader group, a sparse band into its neighbour) "
              "or drop every trait column")


# ------------------------------------------------------------------ reading

def read_export(path):
    """Rows as dicts keyed by STRIPPED headings. Returns (headers, rows, how many headings were trimmed)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_headers = reader.fieldnames or []
        raw_rows = list(reader)
    headers = [h.strip() for h in raw_headers]
    trimmed = sum(1 for a, b in zip(raw_headers, headers) if a != b)
    rows = [{h: (r.get(rh) or "") for rh, h in zip(raw_headers, headers)} for r in raw_rows]
    return headers, rows, trimmed


# ------------------------------------------------------------------ the run

def run(settings, profile_name, input_override=None, output_override=None, key_override=None):
    """Code one export. Returns a dict with the output path, key path, report lines and check results."""
    report = [f"deidentify.py version {SCRIPT_VERSION}   run on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
              "Output is CODED data, not anonymous data. Review the warnings below before sharing.", ""]
    if profile_name not in settings["profiles"]:
        raise StopRun(f"No profile called '{profile_name}'. Profiles in SETTINGS: {', '.join(settings['profiles'])}.")
    p = {k: ([x.strip() for x in v] if isinstance(v, list) else v.strip() if isinstance(v, str) else v)
         for k, v in settings["profiles"][profile_name].items()}
    input_file = input_override or p["input_file"]
    output_folder = output_override or settings["output_folder"]
    key_folder = key_override or settings["key_folder"]
    key_path = os.path.join(key_folder, settings["key_file"])
    output_file = os.path.join(output_folder, "coded_" + os.path.basename(input_file))
    report_file = os.path.join(output_folder, "deidentify_report_" + os.path.splitext(os.path.basename(input_file))[0] + ".txt")
    minimum = int(settings["minimum_group_size"])

    # ---- safety: never write over an input, never put the key with the output
    abs_in = os.path.abspath(input_file)
    for out in (output_file, report_file, key_path):
        if os.path.abspath(out) == abs_in:
            raise StopRun(f"Refusing to run: '{out}' is the input file. Choose a different output folder.")
    if os.path.abspath(output_folder) == os.path.dirname(abs_in):
        raise StopRun("Refusing to run: output_folder is the folder that holds the input file. Use a new folder.")
    if os.path.abspath(key_folder).startswith(os.path.abspath(output_folder) + os.sep) or \
            os.path.abspath(key_folder) == os.path.abspath(output_folder):
        raise StopRun("Refusing to run: the key folder must not be inside the output folder.")
    if not os.path.exists(input_file):
        raise StopRun(f"Input file not found: {input_file}")

    headers, rows, trimmed = read_export(input_file)
    report.append(f"Input: {input_file}  ({len(rows)} rows, {len(headers)} columns)")
    if trimmed:
        report.append(f"  {trimmed} heading(s) had spaces at the start or end; those spaces were removed.")
    if len(set(headers)) != len(headers):
        raise StopRun("The input has two columns with the same heading. Rename one and run again.")

    id_col = p["athlete_id_column"]
    keep = list(p["keep_columns"])
    missing = [c for c in keep + [id_col] if c not in headers]
    if missing:
        raise StopRun(f"These columns are in SETTINGS but not in the file: {missing}. Headings must match exactly "
                      f"(spaces at the ends are ignored). The file's headings are: {headers}")
    if id_col not in keep:
        keep.insert(0, id_col)
    dropped = [h for h in headers if h not in keep]
    report += ["", "COLUMNS", f"  kept ({len(keep)}): {', '.join(keep)}",
               f"  dropped ({len(dropped)}): {', '.join(dropped) if dropped else '(none)'}"]

    # ---- athlete IDs -> codes
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
    if blank_id:
        report.append(f"  WARNING: {blank_id} row(s) had a blank '{id_col}' and were left out.")
    original_ids = sorted({r[id_col] for r in kept_rows})
    key = load_key(key_path)
    reused = sum(1 for i in original_ids if i in key)
    for i in original_ids:
        if i not in key:
            key[i] = new_code(set(key.values()))
    save_key(key_path, key)
    report += ["", "ATHLETE CODES",
               f"  {len(original_ids)} athletes in this file: {reused} already had a code in the key, "
               f"{len(original_ids) - reused} received a new one.",
               f"  key written to: {key_path}   (keep this private; never upload it)"]
    variants = likely_name_variants(original_ids)
    if variants:
        report.append(f"  WARNING: {len(variants)} pair(s) of IDs look like the same person written two ways. "
                      f"Each got its OWN code. If they are one athlete, add them to id_aliases in SETTINGS and run again:")
        for a, b in variants:
            report.append(f"      '{a}'  and  '{b}'")

    # ---- units: read from the headings, convert inches -> cm and pounds -> kg
    h_col, m_col = p.get("height_column", ""), p.get("body_mass_column", "")
    renamed = {}
    conversions = {}
    report += ["", "UNITS"]
    for col in keep:
        if col == id_col:
            continue
        u = unit_of(col)
        if col == m_col and u not in MASS_UNITS:
            raise StopRun(f"body_mass_column '{col}' has no mass unit in its heading. Add [kg] or [lb] to the heading in the "
                          f"file (or set body_mass_column to '' if you do not want it banded).")
        if col == h_col and u not in LENGTH_UNITS:
            raise StopRun(f"height_column '{col}' has no length unit in its heading. Add [cm] or [in] to the heading in the "
                          f"file (or set height_column to '' if you do not want it banded).")
        table = LENGTH_UNITS if u in LENGTH_UNITS else MASS_UNITS if u in MASS_UNITS else None
        if table and table[u][1] != 1.0:
            new_unit, factor = table[u]
            bad = 0
            for r in kept_rows:
                v = to_float(r[col])
                if v is None:
                    bad += str(r[col]).strip() != ""
                    continue
                r[col] = fmt_number(v * factor)
            renamed[col] = converted_header(col, u, new_unit)
            conversions[col] = (u, new_unit)
            report.append(f"  '{col}': values read in {u} and converted to {new_unit} (x {factor}); heading becomes '{renamed[col]}'."
                          + (f" WARNING: {bad} value(s) were not numbers and were left blank." if bad else ""))
    if not conversions:
        report.append("  no conversions needed: every unit-bearing heading is already in cm, kg or another unit the script leaves alone.")

    # ---- dates -> weeks
    season_start = datetime.strptime(settings["season_start_date"], "%Y-%m-%d").date()
    week_cols = {}
    report += ["", "DATES"]
    for col in p["date_columns"]:
        if col not in keep:
            continue
        dates = parse_dates([r[col] for r in kept_rows], p["date_format"], col, report)
        weeks = [week_number(d, season_start) if d else "" for d in dates]
        early = sum(1 for w in weeks if w != "" and w < 1)
        week_cols[col] = weeks
        span = [w for w in weeks if w != ""]
        report.append(f"  '{col}' -> 'Week' (week 1 starts {season_start}); {len(span)} dates converted, "
                      f"weeks {min(span) if span else '-'} to {max(span) if span else '-'}.")
        if early:
            report.append(f"  WARNING: {early} date(s) fall before season_start_date and have week numbers of 0 or less.")

    # ---- conflicts: one ID, two heights (on the converted values, before banding)
    pos_col, cls_col = p.get("position_column", ""), p.get("class_year_column", "")
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
            r[pos_col] = groups_map.get(raw, raw)
        if h_col and h_col in keep:
            v = to_float(r[h_col])
            r[h_col] = band_label(v, float(settings["height_band_cm"]), "cm") if v is not None else ""
        if m_col and m_col in keep:
            v = to_float(r[m_col])
            r[m_col] = band_label(v, float(settings["body_mass_band_kg"]), "kg") if v is not None else ""
    if pos_col and pos_col in keep:
        report.append(f"  '{pos_col}' replaced by position groups from SETTINGS.")
        if unknown_pos:
            report.append(f"  NOTE: positions not in position_groups were kept as written: "
                          + ", ".join(f"'{k}' ({n} rows)" for k, n in unknown_pos.most_common()))
    for col, width, unit in ((h_col, settings["height_band_cm"], "cm"), (m_col, settings["body_mass_band_kg"], "kg")):
        if col and col in keep:
            report.append(f"  '{renamed.get(col, col)}' replaced by {width} {unit} bands.")
    asym_cols = [c for c in keep if c != id_col and ("(asym)" in c.casefold() or c in p.get("asymmetry_columns", []))]
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
        report.append(f"  '{col}' split into a number and a '{col} side' column (L or R).")
        if asym_bad[col]:
            report.append(f"  WARNING: {len(asym_bad[col])} value(s) in '{col}' could not be read as a number plus L or R "
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
    if conflicts:
        report.append(f"  WARNING: {len(conflicts)} ID(s) carry conflicting fixed traits. Two people may share one ID, "
                      f"or a value was mistyped. Shown by code; look the code up in the key:")
        for i, hs in sorted(conflicts.items(), key=lambda kv: key[kv[0]]):
            nums = sorted(x for x in hs if isinstance(x, float))
            words = sorted(x for x in hs if isinstance(x, str))
            detail = (f"heights {nums}" if nums else "") + ("; " if nums and words else "") + "; ".join(words)
            report.append(f"      {key[i]}: {detail}")
    else:
        report.append("  none found.")

    # ---- uniqueness, counting DIFFERENT athletes
    trait_cols = [c for c in (pos_col, cls_col, m_col, h_col) if c and c in keep]
    per_athlete = defaultdict(lambda: defaultdict(list))
    for r in kept_rows:
        for c in trait_cols:
            per_athlete[key[r[id_col]]][c].append(str(r[c]).strip())
    athlete_traits = {code: {c: mode(vals) for c, vals in d.items()} for code, d in per_athlete.items()}
    label = lambda c: renamed.get(c, c)
    report += ["", f"UNIQUENESS CHECK  (minimum group size {minimum}; counts DIFFERENT athletes, not rows)"]
    checks = {"athlete_level_small_groups": {}, "row_level_small_groups": [], "trait_columns": [label(c) for c in trait_cols]}
    if trait_cols:
        small, smallest = smallest_group(athlete_traits, trait_cols, minimum)
        checks["athlete_level_small_groups"] = {" | ".join(k): sorted(v) for k, v in small.items()}
        report.append(f"  (a) Athlete level, on {', '.join(label(c) for c in trait_cols)}: smallest group has {smallest} athlete(s).")
        if small:
            report.append(f"      WARNING: {len(small)} combination(s) of traits are shared by fewer than {minimum} athletes, "
                          f"covering {sum(len(v) for v in small.values())} athlete(s). Anyone who knows the squad could pick them out:")
            for combo, codes in sorted(small.items(), key=lambda kv: len(kv[1])):
                report.append(f"        {len(codes)} athlete(s): " + ", ".join(f"{label(c)}={v or '(blank)'}" for c, v in zip(trait_cols, combo)))
            report.append(f"      Suggestion: {suggest_coarser(athlete_traits, trait_cols, minimum)}.")
        else:
            report.append(f"      OK: every combination of traits is shared by at least {minimum} athletes.")
    else:
        report.append("  (a) Athlete level: no trait columns kept, so nothing to check.")

    event_cols = [c for c in p.get("event_columns", []) if c in keep]
    row_cols = (["Week"] if week_cols else []) + ([pos_col] if pos_col and pos_col in keep else []) + event_cols
    if event_cols and week_cols:
        first_week_col = next(iter(week_cols))
        combos = defaultdict(set)
        for idx, r in enumerate(kept_rows):
            if not any(str(r[c]).strip() for c in event_cols):
                continue    # no event in this row
            combo = (week_cols[first_week_col][idx],) + tuple(str(r[c]).strip() for c in row_cols[1:])
            combos[combo].add(key[r[id_col]])
        small_rows = {k: v for k, v in combos.items() if len(v) < minimum}
        checks["row_level_small_groups"] = [dict(zip(row_cols, k)) | {"athletes": len(v)} for k, v in small_rows.items()]
        report.append(f"  (b) Row level, on {', '.join(row_cols)} for rows with an event entry: "
                      f"{len(combos)} combination(s) found.")
        if small_rows:
            report.append(f"      WARNING: {len(small_rows)} combination(s) point to fewer than {minimum} athletes:")
            for k, v in sorted(small_rows.items(), key=lambda kv: (len(kv[1]), str(kv[0]))):
                report.append(f"        {len(v)} athlete(s): " + ", ".join(f"{c}={x or '(blank)'}" for c, x in zip(row_cols, k)))
            report.append("      Suggestion: report events by month or by 4-week block instead of week, drop the position "
                          "from the shared file, or describe the event more broadly (for example 'injury' only).")
        else:
            report.append(f"      OK: every event combination is shared by at least {minimum} athletes.")
    else:
        report.append("  (b) Row level: no event columns kept (or no date column), so nothing to check.")

    # ---- write the coded file
    os.makedirs(output_folder, exist_ok=True)
    out_cols = []            # (output heading, source key in the row dicts, kind)
    for c in keep:
        if c == id_col:
            out_cols.append(("Athlete Code", c, "code"))
        elif c in week_cols:
            out_cols.append(("Week", c, "week"))
        else:
            out_cols.append((renamed.get(c, c), c, "value"))
            if c in asym_cols:
                out_cols.append((c + " side", c + " side", "value"))
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([h for h, _, _ in out_cols])
        for idx, r in enumerate(kept_rows):
            w.writerow([key[r[src]] if kind == "code" else week_cols[src][idx] if kind == "week" else r.get(src, "")
                        for _, src, kind in out_cols])

    # ---- verify: no original ID anywhere in the output
    report += ["", "VERIFICATION"]
    targets = {norm(i) for i in original_ids} | {norm(i) for i in settings.get("id_aliases", {})}
    leaks = 0
    name_hits = defaultdict(list)
    with open(output_file, newline="", encoding="utf-8") as f:
        for row_num, row in enumerate(csv.DictReader(f), start=2):
            for col, cell in row.items():
                cell_n = norm(cell)
                if cell_n in targets or any(len(t) >= 4 and t in cell_n for t in targets):
                    leaks += 1
                if col != "Athlete Code" and NAME_SHAPED.search(str(cell)):
                    name_hits[col].append(row_num)
    if leaks:
        os.remove(output_file)
        raise StopRun(f"VERIFICATION FAILED: {leaks} cell(s) in the output still contained an original ID. "
                      f"The output file was deleted. Check the kept columns for one that repeats the athlete's name.")
    report.append(f"  OK: the output was re-read and none of the {len(original_ids)} original IDs appears in it.")
    if name_hits:
        report.append("  WARNING: some kept values look like a person's name (two capitalised words, or an initial and "
                      "a surname). Check these cells before sharing; a coach's or physio's name is still a name:")
        for col, rs in name_hits.items():
            report.append(f"      column '{col}': {len(rs)} cell(s), rows {rs[:10]}{'...' if len(rs) > 10 else ''}")
    report += ["", f"Coded file: {output_file}", f"This report: {report_file}", "",
               "Remaining risk must be reviewed by a person. This script reduces re-identification risk; "
               "it does not make data anonymous."]
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    return {"output_file": output_file, "report_file": report_file, "key_path": key_path,
            "report": report, "checks": checks, "conflicts": {key[i]: sorted(map(str, v)) for i, v in conflicts.items()},
            "name_variants": variants, "name_shaped": dict(name_hits), "rows": len(kept_rows),
            "conversions": conversions, "renamed": renamed, "asymmetry_unparsed": {k: v for k, v in asym_bad.items() if v},
            "output_headers": [h for h, _, _ in out_cols]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Code an athlete monitoring export. Settings are at the top of this file.")
    ap.add_argument("profile", help="which block of SETTINGS to use: " + ", ".join(SETTINGS["profiles"]))
    ap.add_argument("--input", help="code this file instead of the profile's input_file")
    ap.add_argument("--output-folder", help="write here instead of SETTINGS output_folder")
    ap.add_argument("--key-folder", help="key folder instead of SETTINGS key_folder")
    ap.add_argument("--settings-json", help="a JSON file whose values replace the matching SETTINGS entries")
    a = ap.parse_args(argv)
    settings = json.loads(json.dumps(SETTINGS))   # a copy, so edits never touch the block above
    if a.settings_json:
        with open(a.settings_json, encoding="utf-8") as f:
            settings.update(json.load(f))
    try:
        result = run(settings, a.profile, a.input, a.output_folder, a.key_folder)
    except StopRun as e:
        print(f"STOPPED: {e}")
        return 1
    print("\n".join(result["report"]))
    warnings = sum(1 for line in result["report"] if "WARNING" in line)
    print(f"\nDone. {warnings} warning(s) to review. Output is coded data, not anonymous data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
