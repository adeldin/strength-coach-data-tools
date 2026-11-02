"""
cmj_flags.py  -  flag meaningful drops in countermovement jump (CMJ) height, one athlete at a time.

The method, step by step:
  1. Read a CMJ export with one row per trial: athlete code, test day (a date or a week number),
     trial number, jump height in cm. The coded file written by deidentify.py works as it is.
  2. Test-day value = the mean of that athlete's valid trials on that day.
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
    python cmj_flags.py --input coded_output/coded_cmj_season1.csv
    python cmj_flags.py --explain ATH-K7Q2MX        (one athlete's calculation, step by step)

Needs Python 3.10 or newer. Standard library only. No network calls. Never changes the input file.
"""

SCRIPT_VERSION = "0.1.0"

# =====================================================================================================
# SETTINGS  -  edit these.
# =====================================================================================================

SETTINGS = {
    # The file to read. The coded file from deidentify.py is the usual input.
    "input_file": "coded_output/coded_cmj_season1.csv",
    # Where the results CSV and the report go. Created if missing. Must not be the input's folder.
    "output_folder": "cmj_output",

    # Column headings, spelled exactly as they appear in the file.
    "athlete_column": "Athlete Code",
    "day_column": "Week",                 # a week number, or a date
    "day_format": "",                     # leave "" for week numbers or year-month-day dates;
                                          # set e.g. "%m/%d/%Y" if the day column holds dates like 08/05/2024
    "trial_column": "Trial",
    "jump_height_column": "Jump Height (cm)",
    "test_type_column": "Test Type",      # "" if there is no such column
    "test_type_value": "CMJ",             # only rows with this test type are used ("" = use every row)

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
}

# =====================================================================================================
# The code.
# =====================================================================================================

import argparse
import csv
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime


class StopRun(Exception):
    pass


def to_float(text):
    try:
        return float(str(text).strip())
    except ValueError:
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
    """Returns (trials, exclusions, counts). trials: {athlete: {day: [heights]}} after exclusions."""
    s = settings
    path = s["input_file"]
    if not os.path.exists(path):
        raise StopRun(f"Input file not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)
    need = [s["athlete_column"], s["day_column"], s["trial_column"], s["jump_height_column"]]
    if s["test_type_column"]:
        need.append(s["test_type_column"])
    missing = [c for c in need if c not in headers]
    if missing:
        raise StopRun(f"These columns are in SETTINGS but not in the file: {missing}. Headings must match exactly.")

    raw = defaultdict(lambda: defaultdict(list))     # athlete -> day -> [(trial, height, row_num)]
    exclusions = []
    n_rows = 0
    for row_num, r in enumerate(rows, start=2):
        if s["test_type_column"] and s["test_type_value"] and \
                str(r[s["test_type_column"]]).strip().casefold() != s["test_type_value"].casefold():
            continue
        n_rows += 1
        ath = str(r[s["athlete_column"]]).strip()
        day = day_key(r[s["day_column"]], s["day_format"])
        h = to_float(r[s["jump_height_column"]])
        if not ath or day is None or h is None:
            exclusions.append((ath or "(blank)", str(r[s["day_column"]]), f"row {row_num}: blank or unreadable athlete, day or jump height"))
            continue
        raw[ath][day].append((str(r[s["trial_column"]]).strip(), h, row_num))

    trials = defaultdict(dict)
    lo, hi = float(s["plausible_min_cm"]), float(s["plausible_max_cm"])
    for ath, days in raw.items():
        for day, items in days.items():
            trial_ids = [t for t, _, _ in items]
            dup = len(trial_ids) != len(set(trial_ids)) or len(items) > 2 * int(s["expected_trials_per_day"]) - 1
            if dup:
                exclusions.append((ath, str(day), f"duplicated test day: {len(items)} trials with trial numbers "
                                                  f"{sorted(trial_ids)}; the whole day is left out until resolved"))
                continue
            good = []
            for t, h, row_num in items:
                if lo <= h <= hi:
                    good.append(h)
                else:
                    note = "looks like inches (x 2.54 would be plausible)" if lo <= h * 2.54 <= hi else "outside the plausible range"
                    if s["exclude_implausible"]:
                        exclusions.append((ath, str(day), f"trial {t} = {h} cm (row {row_num}): {note}; left out"))
                    else:
                        exclusions.append((ath, str(day), f"trial {t} = {h} cm (row {row_num}): {note}; KEPT because exclude_implausible is False"))
                        good.append(h)
            if good:
                trials[ath][day] = good
            else:
                exclusions.append((ath, str(day), "no usable trials on this day; day left out"))
    counts = {"rows_read": n_rows, "athletes": len(trials),
              "test_days": sum(len(d) for d in trials.values()),
              "trials": sum(len(v) for d in trials.values() for v in d.values())}
    return trials, exclusions, counts


# ------------------------------------------------------------------ the method

def analyse(trials, settings):
    """Returns the per-athlete results and the squad thresholds."""
    n_base = int(settings["baseline_days"])
    k = float(settings["k"])
    expected = int(settings["expected_trials_per_day"])
    warnings = []
    athletes = {}
    for ath, days in trials.items():
        ordered = sorted(days)
        day_means = {d: statistics.fmean(days[d]) for d in ordered}
        for d in ordered:
            if len(days[d]) < expected:
                warnings.append((ath, str(d), f"only {len(days[d])} trial(s) on this day (expected {expected})"))
            if len(days[d]) >= 2:
                mid = statistics.median(days[d])
                frac = float(settings.get("within_day_warning_fraction", 0.30))
                odd = [h for h in days[d] if mid and abs(h - mid) / mid > frac]
                if odd:
                    warnings.append((ath, str(d), f"trial value(s) {odd} differ from the day's middle value ({mid:.1f} cm) by more than "
                                                  f"{int(frac * 100)}%; check for a typing error or a value in inches (kept in the calculation)"))
        base_days = ordered[:n_base]
        enough = len(base_days) >= n_base
        base_mean = statistics.fmean(day_means[d] for d in base_days) if enough else None
        diffs = [day_means[base_days[i + 1]] - day_means[base_days[i]] for i in range(len(base_days) - 1)] if enough else []
        athletes[ath] = {"days": ordered, "trials": days, "day_means": day_means, "baseline_days": base_days,
                         "baseline_mean": base_mean, "baseline_diffs": diffs, "enough": enough}

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
            row = {"athlete": ath, "day": d, "test_day_value": round(val, 2), "trials": len(a["trials"][d]),
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

def write_outputs(settings, results, squad, warnings, exclusions, counts, input_file):
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
    with open(results_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["athlete_code", "test_day", "test_day_value_cm", "trials", "baseline_cm", "drop_cm", "swc_cm", "k_x_te_cm", "status"])
        for r in results:
            w.writerow([r["athlete"], r["day"], r["test_day_value"], r["trials"],
                        "" if r["baseline"] is None else r["baseline"], "" if r["drop"] is None else r["drop"],
                        "" if r["swc"] is None else r["swc"], "" if r["k_te"] is None else r["k_te"], r["status"]])

    fmt = lambda x: "not available" if x is None else f"{x:.2f} cm"
    flags = [r for r in results if r["status"] == "FLAG"]
    not_enough = sorted({r["athlete"] for r in results if r["status"] == "not enough data"})
    lines = [f"cmj_flags.py version {SCRIPT_VERSION}   run on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"Input: {input_file}", "",
             "WHAT WAS READ",
             f"  {counts['rows_read']} rows -> {counts['athletes']} athletes, {counts['test_days']} test days, "
             f"{counts['trials']} trials after exclusions.",
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


def explain(code, athletes, squad, settings):
    """One athlete's calculation, step by step, so a coach can check it by hand."""
    if code not in athletes:
        return [f"No athlete with code '{code}' in the file."]
    a = athletes[code]
    out = [f"EXPLAIN {code}", f"  Test days ({len(a['days'])}): {', '.join(str(d) for d in a['days'])}"]
    if not a["enough"]:
        out.append(f"  Fewer than {settings['baseline_days']} test days, so: not enough data. No flag can be raised.")
        return out
    out.append(f"  Baseline days (first {settings['baseline_days']}):")
    for d in a["baseline_days"]:
        tr = ", ".join(f"{h:.1f}" for h in a["trials"][d])
        out.append(f"    day {d}: trials {tr}  -> day mean {a['day_means'][d]:.2f} cm")
    out.append(f"  Baseline mean = {a['baseline_mean']:.2f} cm")
    out.append("  Consecutive-day differences in the baseline: " + ", ".join(f"{x:+.2f}" for x in a["baseline_diffs"])
               + f"   (these feed the {a['te_source']} TE)")
    out.append(f"  TE used = {a['te']:.2f} cm ({a['te_source']}); k x TE = {settings['k']} x {a['te']:.2f} = {settings['k'] * a['te']:.2f} cm; "
               f"SWC = {squad['swc']:.2f} cm")
    out.append("  Later test days:")
    for d in a["days"][len(a["baseline_days"]):]:
        tr = ", ".join(f"{h:.1f}" for h in a["trials"][d])
        val = a["day_means"][d]
        drop = a["baseline_mean"] - val
        over_swc = drop > squad["swc"]
        over_kte = drop > settings["k"] * a["te"]
        verdict = "FLAG" if (over_swc and over_kte) else "no flag"
        out.append(f"    day {d}: trials {tr} -> mean {val:.2f}; drop = {a['baseline_mean']:.2f} - {val:.2f} = {drop:+.2f} cm; "
                   f"> SWC? {'yes' if over_swc else 'no'}; > k x TE? {'yes' if over_kte else 'no'}  => {verdict}")
    return out


def run(settings, explain_code=None):
    trials, exclusions, counts = read_trials(settings)
    if not trials:
        raise StopRun("No usable rows were read. Check the column settings and the test_type_value.")
    results, squad, warnings, athletes = analyse(trials, settings)
    results_file, report_file, lines = write_outputs(settings, results, squad, warnings, exclusions, counts, settings["input_file"])
    out = {"results": results, "squad": squad, "warnings": warnings, "exclusions": exclusions, "counts": counts,
           "results_file": results_file, "report_file": report_file, "report": lines, "athletes": athletes}
    if explain_code:
        out["explain"] = explain(explain_code, athletes, squad, settings)
    return out


def main(argv=None):
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
