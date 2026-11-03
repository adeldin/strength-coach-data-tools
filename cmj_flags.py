"""
cmj_flags.py  -  flag meaningful drops in countermovement jump (CMJ) height, one athlete at a time.

The method, step by step:
  1. Read a CMJ export. Either kind works:
       per-trial   one row per jump (athlete, test day, trial number, jump height)   <- better: all checks run
       per-test    one row per test day with a Reps column (the VALD ForceDecks layout)
     The coded file written by deidentify.py works as it is. Jump height may be in cm or inches; the
     unit is read from the heading's brackets and inches are converted to cm.
  2. Test-day value = the mean of that athlete's valid trials on that day (per-trial), or the row's
     value (per-test).
  3. Baseline = the mean of each athlete's first N test days (default 4).
  4. Typical error (TE) = the day-to-day noise, pooled across the squad: collect every athlete's
     differences between consecutive baseline days, then TE = SD of those differences / sqrt(2).
  5. Smallest worthwhile change (SWC) = 0.2 x the between-athlete SD of the baseline means.
  6. A test day is FLAGGED when (baseline - test-day value) is bigger than BOTH the SWC AND k x TE
     (k defaults to 1.5). Drops only; improvements are never flagged.
  7. An athlete with fewer than N baseline days is "not enough data", never flagged.

A flag is a prompt to check in with the athlete, not a decision. The TE assumes athletes were stable
across their baseline days; if they were fatigued, injured or still learning the test, TE is inflated
and real drops are missed. Every threshold below is an adjustable choice, not a rule.

How to run it (from the folder that holds this file):
    python cmj_flags.py
    python cmj_flags.py --input coded_output/coded_cmj_trials_season1.csv
    python cmj_flags.py --explain ATH-K7Q2MX        (one athlete's calculation, step by step)

Needs Python 3.10 or newer. Standard library only. No network calls. Never changes the input file.
"""

SCRIPT_VERSION = "0.3.0"

# =====================================================================================================
# SETTINGS  -  edit these.
# =====================================================================================================

SETTINGS = {
    # The file to read. The coded file from deidentify.py is the usual input.
    "input_file": "coded_output/coded_cmj_trials_season1.csv",
    # Where the results CSV and the report go. Created if missing. Must not be the input's folder.
    "output_folder": "cmj_output",

    # Column headings. Spaces at the ends and the unit in brackets are ignored when matching, so
    # "Jump Height (Imp-Mom)" matches both "Jump Height (Imp-Mom) in Inches [in]" and
    # "Jump Height (Imp-Mom) [cm]". The unit itself is read from the file's heading.
    # These defaults fit a per-trial export (one row per jump). For a per-test export such as ForceDecks, set:
    # jump_height_column "Jump Height (Imp-Mom)", trial_column "", reps_column "Reps",
    # depth_column "Countermovement Depth". Trial-level checks cannot run on a per-test export.
    "athlete_column": "Athlete Code",
    "day_column": "Week",                 # a week number, or a date
    "day_format": "",                     # leave "" for week numbers or year-month-day dates;
                                          # set e.g. "%m/%d/%Y" if the day column holds dates like 08/05/2024
    "jump_height_column": "Jump Height (cm)",
    "trial_column": "Trial",              # per-trial exports: the trial or rep number column ("" for a per-test export)
    "reps_column": "",                    # per-test exports: the column that counts the reps in the test (e.g. "Reps")
    "test_type_column": "Test Type",      # "" if there is no such column
    "test_type_value": "CMJ",             # only rows with this test type are used ("" = use every row)
    "depth_column": "",                   # optional, e.g. "Countermovement Depth"; exported as a negative number (downward)

    # The method's numbers. Defaults are the ones described in the article.
    "expected_trials_per_day": 3,
    "baseline_days": 4,
    "swc_multiplier": 0.2,
    "k": 1.5,
    "individual_te": False,               # True: each athlete's own TE, when they have enough baseline days

    # Data checks.
    "plausible_min_cm": 15,
    "plausible_max_cm": 80,
    "exclude_implausible": True,          # values outside the range are left out of every calculation
    # A trial that differs from the middle trial of its day by more than this share is reported (not excluded).
    # Catches a value typed in inches that still falls inside the plausible range (any jump over 38 cm).
    "within_day_warning_fraction": 0.30,
    # Countermovement depth is checked on its size regardless of sign (warning only, never excluded).
    "depth_plausible_min_cm": 10,
    "depth_plausible_max_cm": 60,
}

# =====================================================================================================
# The code.
# =====================================================================================================

import argparse
import csv
import json
import math
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime

LENGTH_UNITS = {"cm": 1.0, "in": 2.54, "inch": 2.54, "inches": 2.54, "mm": 0.1}
UNIT_GROUP = re.compile(r"[\[(]([^\[\]()]+)[\])]")


class StopRun(Exception):
    pass


def to_float(text):
    try:
        return float(str(text).strip())
    except ValueError:
        return None


def unit_of(header):
    groups = [g.strip().casefold() for g in UNIT_GROUP.findall(header)]
    for g in reversed(groups):
        if g in LENGTH_UNITS or g in {"kg", "lb", "n", "w", "w/kg", "m/s", "n/s", "ms", "s", "%"}:
            return g
    return ""


def bare(header):
    """A heading without its unit group, the phrase 'in Inches', end spaces or case: used only for matching."""
    h = header.strip()
    u = unit_of(h)
    if u:
        h = re.sub(r"[\[(]\s*" + re.escape(u) + r"\s*[\])]\s*$", "", h, flags=re.I)
    h = re.sub(r"\s+in\s+inches\b", "", h, flags=re.I)
    return " ".join(h.split()).casefold()


def find_column(setting, headers, what, required=True):
    """The file's heading that matches the setting, exactly or after removing units and end spaces."""
    if not setting:
        return None
    exact = [h for h in headers if h.strip() == setting.strip()]
    if exact:
        return exact[0]
    loose = [h for h in headers if bare(h) == bare(setting)]
    if len(loose) == 1:
        return loose[0]
    if required:
        raise StopRun(f"The {what} column '{setting}' is not in the file. Headings in the file: {[h.strip() for h in headers]}")
    return None


def day_key(raw, day_format):
    """Something sortable: an int for week numbers, a date for dates. None if unreadable."""
    raw = str(raw).strip()
    if raw == "":
        return None
    if day_format:
        try:
            return datetime.strptime(raw, day_format).date()
        except ValueError:
            return None
    try:
        return int(float(raw))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def sd(values):
    return statistics.stdev(values) if len(values) >= 2 else None


# ------------------------------------------------------------------ reading and checking

def read_trials(settings):
    """Returns (trials, exclusions, counts, info). trials: {athlete: {day: [heights in cm]}} after exclusions."""
    s = settings
    path = s["input_file"]
    if not os.path.exists(path):
        raise StopRun(f"Input file not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_headers = reader.fieldnames or []
        rows = list(reader)
    headers = [h.strip() for h in raw_headers]
    rows = [{h: (r.get(rh) or "") for rh, h in zip(raw_headers, headers)} for r in rows]

    ath_col = find_column(s["athlete_column"], headers, "athlete")
    day_col = find_column(s["day_column"], headers, "test day")
    jump_col = find_column(s["jump_height_column"], headers, "jump height")
    type_col = find_column(s.get("test_type_column", ""), headers, "test type", required=False)
    trial_col = find_column(s.get("trial_column", ""), headers, "trial", required=False)
    reps_col = find_column(s.get("reps_column", ""), headers, "reps", required=False)
    depth_col = find_column(s.get("depth_column", ""), headers, "depth", required=False)
    if trial_col:
        mode = "per-trial"
    elif reps_col:
        mode = "per-test"
    else:
        raise StopRun("Could not tell whether this is a per-trial or a per-test export: neither trial_column nor "
                      f"reps_column is in the file. Set one of them in SETTINGS. Headings: {headers}")

    unit = unit_of(jump_col)
    if unit not in LENGTH_UNITS:
        raise StopRun(f"The jump height heading '{jump_col}' does not say its unit. Add [cm] or [in] to the heading in the file.")
    factor = LENGTH_UNITS[unit]
    depth_unit, depth_factor = "", 1.0
    if depth_col:
        depth_unit = unit_of(depth_col)
        if depth_unit not in LENGTH_UNITS:
            raise StopRun(f"The depth heading '{depth_col}' does not say its unit. Add [cm] or [in] to the heading, or set depth_column to ''.")
        depth_factor = LENGTH_UNITS[depth_unit]
    info = {"mode": mode, "jump_column": jump_col, "jump_unit": unit, "converted": factor != 1.0,
            "depth_column": depth_col, "depth_unit": depth_unit, "columns": dict(athlete=ath_col, day=day_col, trial=trial_col, reps=reps_col)}

    raw = defaultdict(lambda: defaultdict(list))     # athlete -> day -> [(trial label, height cm, raw value, row, reps, depth cm)]
    exclusions = []
    n_rows = 0
    for row_num, r in enumerate(rows, start=2):
        if type_col and s.get("test_type_value") and str(r[type_col]).strip().casefold() != s["test_type_value"].casefold():
            continue
        n_rows += 1
        ath = str(r[ath_col]).strip()
        day = day_key(r[day_col], s["day_format"])
        v = to_float(r[jump_col])
        if not ath or day is None or v is None:
            exclusions.append((ath or "(blank)", str(r[day_col]), f"row {row_num}: blank or unreadable athlete, day or jump height"))
            continue
        label = str(r[trial_col]).strip() if trial_col else "test"
        reps = to_float(r[reps_col]) if reps_col else None
        depth = to_float(r[depth_col]) * depth_factor if depth_col and to_float(r[depth_col]) is not None else None
        raw[ath][day].append((label, v * factor, v, row_num, reps, depth))

    trials = defaultdict(dict)
    reps_by_day, depth_warn = {}, []
    lo, hi = float(s["plausible_min_cm"]), float(s["plausible_max_cm"])
    dlo, dhi = float(s.get("depth_plausible_min_cm", 10)), float(s.get("depth_plausible_max_cm", 60))
    expected = int(s["expected_trials_per_day"])
    for ath, days in raw.items():
        for day, items in days.items():
            labels = [t for t, *_ in items]
            if mode == "per-test":
                dup = len(items) > 1
            else:
                dup = len(labels) != len(set(labels)) or len(items) > 2 * expected - 1
            if dup:
                exclusions.append((ath, str(day), f"duplicated test day: {len(items)} rows"
                                   + (f" with trial numbers {sorted(labels)}" if mode == "per-trial" else "")
                                   + "; the whole day is left out until resolved"))
                continue
            good = []
            for t, h_cm, v_raw, row_num, reps, depth in items:
                if depth is not None and not (dlo <= abs(depth) <= dhi):
                    depth_warn.append((ath, str(day), f"countermovement depth {depth:.1f} cm is outside {dlo:g} to {dhi:g} cm in size (kept; check the row)"))
                if lo <= h_cm <= hi:
                    good.append(h_cm)
                    if reps is not None:
                        reps_by_day[(ath, day)] = reps
                    continue
                if unit == "cm" and lo <= h_cm * 2.54 <= hi:
                    note = "looks like inches typed into a cm column (x 2.54 would be plausible)"
                elif unit != "cm" and lo <= v_raw <= hi:
                    note = f"looks like centimetres typed into the {unit} column (read as {h_cm:.1f} cm)"
                elif unit == "cm" and lo <= h_cm / 2.54 <= hi:
                    note = "outside the plausible range; / 2.54 would be plausible, so it may be a cm value that was typed into an inches column before conversion"
                else:
                    note = f"outside the plausible range ({h_cm:.1f} cm after conversion)" if factor != 1.0 else "outside the plausible range"
                shown = f"{v_raw:g} {unit}" if factor != 1.0 else f"{v_raw:g} cm"
                if s["exclude_implausible"]:
                    exclusions.append((ath, str(day), f"{'trial ' + t if mode == 'per-trial' else 'value'} = {shown} (row {row_num}): {note}; left out"))
                else:
                    exclusions.append((ath, str(day), f"{'trial ' + t if mode == 'per-trial' else 'value'} = {shown} (row {row_num}): {note}; KEPT because exclude_implausible is False"))
                    good.append(h_cm)
            if good:
                trials[ath][day] = good
            else:
                exclusions.append((ath, str(day), "no usable value on this day; day left out"))
    counts = {"rows_read": n_rows, "athletes": len(trials),
              "test_days": sum(len(d) for d in trials.values()),
              "trials": sum(len(v) for d in trials.values() for v in d.values())}
    info["reps_by_day"] = reps_by_day
    info["depth_warnings"] = depth_warn
    return trials, exclusions, counts, info


# ------------------------------------------------------------------ the method

def analyse(trials, settings, info=None):
    """Returns the per-athlete results and the squad thresholds."""
    info = info or {"mode": "per-trial", "reps_by_day": {}}
    n_base = int(settings["baseline_days"])
    k = float(settings["k"])
    expected = int(settings["expected_trials_per_day"])
    warnings = []
    athletes = {}
    for ath, days in trials.items():
        ordered = sorted(days)
        day_means = {d: statistics.fmean(days[d]) for d in ordered}
        for d in ordered:
            if info["mode"] == "per-trial":
                if len(days[d]) < expected:
                    warnings.append((ath, str(d), f"only {len(days[d])} trial(s) on this day (expected {expected})"))
                if len(days[d]) >= 2:
                    mid = statistics.median(days[d])
                    frac = float(settings.get("within_day_warning_fraction", 0.30))
                    odd = [round(h, 1) for h in days[d] if mid and abs(h - mid) / mid > frac]
                    if odd:
                        warnings.append((ath, str(d), f"trial value(s) {odd} cm differ from the day's middle value ({mid:.1f} cm) by more than "
                                                      f"{int(frac * 100)}%; check for a typing error or a value in inches (kept in the calculation)"))
            else:
                reps = info["reps_by_day"].get((ath, d))
                if reps is not None and reps < expected:
                    warnings.append((ath, str(d), f"the Reps column shows {reps:g} rep(s) in this test (expected {expected}); "
                                                  f"the individual trials are not in a per-test export, so this is a note only"))
        base_days = ordered[:n_base]
        enough = len(base_days) >= n_base
        base_mean = statistics.fmean(day_means[d] for d in base_days) if enough else None
        diffs = [day_means[base_days[i + 1]] - day_means[base_days[i]] for i in range(len(base_days) - 1)] if enough else []
        athletes[ath] = {"days": ordered, "trials": days, "day_means": day_means, "baseline_days": base_days,
                         "baseline_mean": base_mean, "baseline_diffs": diffs, "enough": enough}
    warnings += info.get("depth_warnings", [])

    pooled_diffs = [x for a in athletes.values() for x in a["baseline_diffs"]]
    te_pooled = (sd(pooled_diffs) / math.sqrt(2)) if len(pooled_diffs) >= 2 else None
    base_means = [a["baseline_mean"] for a in athletes.values() if a["enough"]]
    between_sd = sd(base_means)
    swc = float(settings["swc_multiplier"]) * between_sd if between_sd is not None else None
    squad = {"te": te_pooled, "swc": swc, "k": k, "k_te": (k * te_pooled) if te_pooled is not None else None,
             "between_athlete_sd": between_sd, "baseline_diffs_used": len(pooled_diffs),
             "athletes_with_full_baseline": len(base_means),
             "effective_threshold": max(swc, k * te_pooled) if (swc is not None and te_pooled is not None) else None}

    results = []
    for ath, a in sorted(athletes.items()):
        te = te_pooled
        te_source = "pooled"
        if settings["individual_te"] and len(a["baseline_diffs"]) >= 2:
            te = sd(a["baseline_diffs"]) / math.sqrt(2)
            te_source = "individual"
        a["te"], a["te_source"] = te, te_source
        for d in a["days"]:
            val = a["day_means"][d]
            n_tr = len(a["trials"][d]) if info["mode"] == "per-trial" else info["reps_by_day"].get((ath, d), "")
            row = {"athlete": ath, "day": d, "test_day_value": round(val, 2), "trials": n_tr,
                   "baseline": None, "drop": None, "swc": None, "k_te": None, "status": ""}
            if not a["enough"]:
                row["status"] = "not enough data"
            elif d in a["baseline_days"]:
                row["baseline"] = round(a["baseline_mean"], 2)
                row["status"] = "baseline"
            elif swc is None or te is None:
                row["status"] = "thresholds unavailable"
            else:
                drop = a["baseline_mean"] - val
                row.update({"baseline": round(a["baseline_mean"], 2), "drop": round(drop, 2),
                            "swc": round(swc, 2), "k_te": round(k * te, 2)})
                row["status"] = "FLAG" if (drop > swc and drop > k * te) else "no flag"
            results.append(row)
    return results, squad, warnings, athletes


# ------------------------------------------------------------------ output

def write_outputs(settings, results, squad, warnings, exclusions, counts, info, input_file):
    out_dir = settings["output_folder"]
    abs_in = os.path.abspath(input_file)
    if os.path.abspath(out_dir) == os.path.dirname(abs_in):
        raise StopRun("Refusing to run: output_folder is the folder that holds the input file. Use a new folder.")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(input_file))[0]
    results_file = os.path.join(out_dir, f"cmj_results_{stem}.csv")
    report_file = os.path.join(out_dir, f"cmj_report_{stem}.txt")
    for f in (results_file, report_file):
        if os.path.abspath(f) == abs_in:
            raise StopRun("Refusing to run: an output path equals the input path.")
    per_trial = info["mode"] == "per-trial"
    with open(results_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["athlete_code", "test_day", "test_day_value_cm", "trials" if per_trial else "reps", "baseline_cm", "drop_cm",
                    "swc_cm", "k_x_te_cm", "status"])
        for r in results:
            w.writerow([r["athlete"], r["day"], r["test_day_value"], r["trials"] if r["trials"] != "" else "",
                        "" if r["baseline"] is None else r["baseline"], "" if r["drop"] is None else r["drop"],
                        "" if r["swc"] is None else r["swc"], "" if r["k_te"] is None else r["k_te"], r["status"]])

    fmt = lambda x: "not available" if x is None else f"{x:.2f} cm"
    flags = [r for r in results if r["status"] == "FLAG"]
    not_enough = sorted({r["athlete"] for r in results if r["status"] == "not enough data"})
    lines = [f"cmj_flags.py version {SCRIPT_VERSION}   run on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"Input: {input_file}", "",
             "WHAT WAS READ",
             f"  Export type: {info['mode']} "
             + ("(one row per jump; all checks run)." if per_trial else
                "(one row per test with a Reps column). Trial-level checks could not be run: the number of trials and the "
                "spread between trials on a day are not in this kind of export. A per-trial export is better when you can get one."),
             f"  Jump height column: '{info['jump_column']}', read in {info['jump_unit']}"
             + (f" and converted to cm (x {LENGTH_UNITS[info['jump_unit']]})." if info["converted"] else "."),
             f"  {counts['rows_read']} rows -> {counts['athletes']} athletes, {counts['test_days']} test days, "
             f"{counts['trials']} {'trials' if per_trial else 'test values'} after exclusions.",
             "",
             "SQUAD THRESHOLDS",
             f"  Baseline = first {settings['baseline_days']} test days per athlete "
             f"({squad['athletes_with_full_baseline']} athletes have a full baseline).",
             f"  Typical error (TE) = {fmt(squad['te'])}  (SD of {squad['baseline_diffs_used']} consecutive-day differences / sqrt 2"
             f"{', pooled across the squad' if not settings['individual_te'] else ', pooled; individual TE used where possible'})",
             f"  Smallest worthwhile change (SWC) = {settings['swc_multiplier']} x {fmt(squad['between_athlete_sd'])} between-athlete SD = {fmt(squad['swc'])}",
             f"  k x TE = {settings['k']} x TE = {fmt(squad['k_te'])}",
             f"  Effective threshold (a drop must exceed BOTH) = {fmt(squad['effective_threshold'])}",
             "",
             f"FLAGS ({len(flags)})"]
    lines += [f"  {r['athlete']}  day {r['day']}: {r['test_day_value']:.2f} cm vs baseline {r['baseline']:.2f} cm, "
              f"drop {r['drop']:.2f} cm" for r in flags] or ["  none"]
    lines += ["", f"NOT ENOUGH DATA ({len(not_enough)} athletes with fewer than {settings['baseline_days']} baseline days)",
              "  " + (", ".join(not_enough) if not_enough else "none"),
              "", f"WARNINGS ({len(warnings)})"]
    lines += [f"  {a}  day {d}: {msg}" for a, d, msg in warnings] or ["  none"]
    lines += ["", f"EXCLUSIONS ({len(exclusions)})"]
    lines += [f"  {a}  day {d}: {msg}" for a, d, msg in exclusions] or ["  none"]
    lines += ["", "HOW TO READ THIS",
              "  A flag is a prompt to check in with the athlete, not a decision. Drops only are flagged.",
              "  TE assumes athletes were stable across their baseline days. If they were not, TE is inflated and",
              "  real drops will be missed. Missing test days stay missing; they are never treated as zero.",
              "  Every threshold is an adjustable choice in SETTINGS, not a rule.",
              "", f"Results: {results_file}", f"Report: {report_file}"]
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return results_file, report_file, lines


def explain(code, athletes, squad, settings, info):
    """One athlete's calculation, step by step, so a coach can check it by hand."""
    if code not in athletes:
        return [f"No athlete with code '{code}' in the file."]
    a = athletes[code]
    word = "trials" if info["mode"] == "per-trial" else "test value"
    out = [f"EXPLAIN {code}   (all values in cm)", f"  Test days ({len(a['days'])}): {', '.join(str(d) for d in a['days'])}"]
    if not a["enough"]:
        out.append(f"  Fewer than {settings['baseline_days']} test days, so: not enough data. No flag can be raised.")
        return out
    out.append(f"  Baseline days (first {settings['baseline_days']}):")
    for d in a["baseline_days"]:
        tr = ", ".join(f"{h:.1f}" for h in a["trials"][d])
        out.append(f"    day {d}: {word} {tr}  -> day value {a['day_means'][d]:.2f}")
    out.append(f"  Baseline mean = {a['baseline_mean']:.2f}")
    out.append("  Consecutive-day differences in the baseline: " + ", ".join(f"{x:+.2f}" for x in a["baseline_diffs"])
               + f"   (these feed the {a['te_source']} TE)")
    out.append(f"  TE used = {a['te']:.2f} ({a['te_source']}); k x TE = {settings['k']} x {a['te']:.2f} = {settings['k'] * a['te']:.2f}; "
               f"SWC = {squad['swc']:.2f}")
    out.append("  Later test days:")
    for d in a["days"][len(a["baseline_days"]):]:
        tr = ", ".join(f"{h:.1f}" for h in a["trials"][d])
        val = a["day_means"][d]
        drop = a["baseline_mean"] - val
        over_swc = drop > squad["swc"]
        over_kte = drop > settings["k"] * a["te"]
        verdict = "FLAG" if (over_swc and over_kte) else "no flag"
        out.append(f"    day {d}: {word} {tr} -> {val:.2f}; drop = {a['baseline_mean']:.2f} - {val:.2f} = {drop:+.2f}; "
                   f"> SWC? {'yes' if over_swc else 'no'}; > k x TE? {'yes' if over_kte else 'no'}  => {verdict}")
    return out


def run(settings, explain_code=None):
    trials, exclusions, counts, info = read_trials(settings)
    if not trials:
        raise StopRun("No usable rows were read. Check the column settings and the test_type_value.")
    results, squad, warnings, athletes = analyse(trials, settings, info)
    results_file, report_file, lines = write_outputs(settings, results, squad, warnings, exclusions, counts, info, settings["input_file"])
    out = {"results": results, "squad": squad, "warnings": warnings, "exclusions": exclusions, "counts": counts, "info": info,
           "results_file": results_file, "report_file": report_file, "report": lines, "athletes": athletes}
    if explain_code:
        out["explain"] = explain(explain_code, athletes, squad, settings, info)
    return out


def require_python():
    if sys.version_info < (3, 10):
        print(f"STOPPED: this script needs Python 3.10 or newer, and this is Python {sys.version_info[0]}.{sys.version_info[1]}. "
              "Install the newest Python from python.org (README section 1), open a new terminal window, and try again.")
        sys.exit(1)


def main(argv=None):
    require_python()
    ap = argparse.ArgumentParser(description="Flag meaningful CMJ drops. Settings are at the top of this file.")
    ap.add_argument("--input", help="read this file instead of SETTINGS input_file")
    ap.add_argument("--output-folder")
    ap.add_argument("--explain", metavar="ATHLETE_CODE", help="print one athlete's calculation step by step")
    ap.add_argument("--settings-json", help="a JSON file whose values replace the matching SETTINGS entries")
    a = ap.parse_args(argv)
    settings = dict(SETTINGS)
    if a.settings_json:
        with open(a.settings_json, encoding="utf-8") as f:
            settings.update(json.load(f))
    if a.input:
        settings["input_file"] = a.input
    if a.output_folder:
        settings["output_folder"] = a.output_folder
    try:
        out = run(settings, a.explain)
    except StopRun as e:
        print(f"STOPPED: {e}")
        return 1
    print("\n".join(out["report"]))
    if a.explain:
        print("\n" + "\n".join(out["explain"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
