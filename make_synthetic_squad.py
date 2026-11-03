"""
make_synthetic_squad.py  -  build the made-up soccer squad used to demonstrate and test the two scripts.

Nothing here is real. Names come from a fixed list and are combined at random; any match with a real
person is a coincidence. The random seed is fixed, so running this again produces identical files.

It writes, to synthetic_data/ (28 players, 14 weeks per season; 8 players replaced in season 2 = 29% turnover):
    gps_season1.csv / gps_season2.csv              example GPS layout
    wellness_season1.csv / wellness_season2.csv    example wellness layout
    cmj_season1.csv / cmj_season2.csv              REAL VALD ForceDecks layout: one row per test, Reps column,
                                                   jump height in INCHES, asymmetry values like "6.3 L",
                                                   countermovement depth negative
    cmj_trials_season1.csv / cmj_trials_season2.csv   example per-trial layout: one row per jump, in cm
and, to expected_output/:
    expected_answers.json / expected_answers.md    every planted problem and the expected flags, by player name

Planted de-identification problems (season 1):
    - one player name recorded with two heights 8 cm apart (two people under one name, or a typo)
    - the pair "J. Okafor" / "Jamal Okafor"  (a name variant)
    - dates written month/day/year, including 09/10/2024, which reads two ways if no format is set
    - a wellness Notes column that mentions a (made-up) coach by name
    - one goalkeeper, unique on position
    - one asymmetry value that cannot be read ("n/a") in the ForceDecks file
Planted CMJ problems (season 1, in BOTH force plate files unless stated):
    - one player with only 2 trials (per-trial file) / Reps = 2 (ForceDecks file) on one test day
    - one player whose test day was entered twice
    - one value in the wrong unit: inches typed into the cm file; centimetres typed into the inches file
    - in week 8, EXACTLY two players drop enough to flag; one decoy drops past the SWC but not past
      k x TE; one player has too few baseline days

Jump height varies from day to day by about 4% of each player's mean, in every week. With that much noise,
ordinary days in the other weeks sometimes cross the threshold too. Only week 8 is engineered.

Run:  python make_synthetic_squad.py
"""

import csv
import json
import math
import os
import random
import statistics
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmj_flags  # noqa: E402  (used to compute the real thresholds so the plants are exact)

SEED = 20240805
OUT = os.path.join(HERE, "synthetic_data")
EXPECTED = os.path.join(HERE, "expected_output")
SEASONS = {1: date(2024, 8, 5), 2: date(2025, 8, 4)}
WEEKS = 14
CHOSEN_WEEK = 8
BASELINE_DAYS = 4
IN = 2.54   # cm per inch
DAY_TO_DAY_CV = 0.04     # day-to-day variation of a test-day value, as a share of the player's mean
TRIAL_NOISE_CM = 0.8     # SD of one jump around that day's true height
DECOY_MARGIN_CM = 0.3    # the decoy's drop stays at least this far from both the SWC and k x TE
COMPARISON_K = 2.0       # the expected answers also list the flags at this k, for comparison only

FIRST = ["Amara", "Bence", "Carla", "Dario", "Elin", "Farid", "Greta", "Hana", "Ivo", "Jamal", "Kaia", "Luca",
         "Mira", "Nadia", "Oskar", "Pia", "Quentin", "Rosa", "Sven", "Tomas", "Uma", "Vera", "Wim", "Yara",
         "Zane", "Anouk", "Bruno", "Cleo", "Dev", "Esme", "Fynn", "Gia", "Hugo", "Ines", "Joel", "Kito",
         "Lior", "Maya", "Nico", "Orla"]
LAST = ["Okafor", "Lindqvist", "Moreau", "Baptiste", "Kowalski", "Haddad", "Nakamura", "Petrov", "Silva",
        "Mensah", "Varga", "Castillo", "Eriksen", "Fontaine", "Giordano", "Horvat", "Ibarra", "Jansen",
        "Keita", "Larsen", "Mbeki", "Novak", "Oduya", "Pereira", "Quiroga", "Rahimi", "Santos", "Tanaka",
        "Ustinov", "Vieira", "Weber", "Yilmaz", "Zahra", "Abara", "Brandt", "Chen", "Dlamini", "Eze"]
POSITIONS = ["GK"] + ["CB"] * 5 + ["LB", "RB", "LB", "RB", "DM"] + ["CM"] * 6 + ["AM"] * 3 + ["LW", "RW", "LW", "RW"] + ["ST"] * 4   # 28
CLASS_YEARS = ["Freshman", "Sophomore", "Junior", "Senior"]
SESSION_DAYS = {0: "Training", 2: "Training", 4: "Training", 5: "Match"}   # Mon, Wed, Fri, Sat
WELLNESS_DAYS = [0, 1, 2, 3, 4]

# Example layouts (not a specific vendor), matching the example profiles in deidentify.py SETTINGS
GPS_COLS = ["Player Name", "Jersey Number", "Date", "Session Type", "Position", "Class Year", "Height (cm)",
            "Body Mass (kg)", "Total Distance (m)", "High Speed Running (m)", "Sprint Distance (m)",
            "Max Velocity (km/h)", "Player Load", "Accelerations", "Decelerations", "Duration (min)", "Device ID"]
TRIAL_COLS = ["Name", "Date", "Test Type", "Trial", "Jump Height (cm)", "Peak Power (W)", "RSI-modified",
              "Contraction Time (ms)", "Body Mass (kg)"]
WELL_COLS = ["Athlete", "Date", "Position", "Sleep Hours", "Sleep Quality (1-5)", "Fatigue (1-5)", "Soreness (1-5)",
             "Stress (1-5)", "Mood (1-5)", "Injury/Illness", "Notes"]
# REAL layout: the header row of a VALD ForceDecks CMJ export, exactly as exported (several headings end in a space)
FORCEDECKS_COLS = ["Name", "ExternalId", "Test Type", "Date", "Time", "BW [KG]", "Reps", "Tags", "Additional Load [lb]",
                   "Jump Height (Imp-Mom) in Inches [in] ", "RSI-modified [m/s] ", "Peak Landing Force [N] ",
                   "Peak Power / BM [W/kg] ", "Concentric RFD [N/s] (L)", "Concentric Peak Force [N] (L)",
                   "Concentric Peak Force [N] (R)", "Peak Landing Force [N] (L)", "Peak Landing Force [N] (R)",
                   "Concentric Duration [ms] ", "Concentric Impulse [N s] ", "Concentric Mean Force [N] ",
                   "Countermovement Depth [cm] ", "Contraction Time:Eccentric Duration [%] ", "Eccentric Duration [ms] ",
                   "Flight Time:Contraction Time ", "Concentric Impulse % (Asym) (%)", "Peak Landing Force % (Asym) (%)",
                   "Eccentric Deceleration RFD [N/s] ", "Eccentric Deceleration Mean Force [N] "]


def mdy(d):
    return d.strftime("%m/%d/%Y")


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)


def make_roster(rng, n, used_names):
    players = []
    pos = list(POSITIONS[:n])
    for i in range(n):
        while True:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if name not in used_names:
                used_names.add(name)
                break
        players.append({
            "name": name, "jersey": i + 1, "position": pos[i], "class_year": rng.choice(CLASS_YEARS),
            "height": rng.randint(160, 190), "mass": round(rng.uniform(55, 85), 1),
            "jump": round(rng.uniform(28, 46), 1),            # true CMJ height, cm
            "fitness": rng.uniform(0.85, 1.15),
        })
    return players


def gps_rows(rng, players, start, plants):
    rows = []
    for w in range(1, WEEKS + 1):
        for dow, stype in SESSION_DAYS.items():
            d = start + timedelta(days=7 * (w - 1) + dow)
            for p in players:
                name = p["name"]
                height = p["height"]
                if plants and name == plants["conflict"] and w in (3, 9, 12):
                    height = p["height"] + 8                      # the conflicting height
                if plants and name == plants["variant_full"] and w in (2, 5, 11):
                    name = plants["variant_short"]                # "J. Okafor"
                match = stype == "Match"
                dist = (9000 if match else 5500) * p["fitness"] * rng.uniform(0.85, 1.15)
                rows.append([name, p["jersey"], mdy(d), stype, p["position"], p["class_year"], height, p["mass"],
                             round(dist), round(dist * rng.uniform(0.07, 0.13)), round(dist * rng.uniform(0.01, 0.04)),
                             round(rng.uniform(26, 33), 1), round(dist / 10 * rng.uniform(0.9, 1.1)),
                             rng.randint(20, 60), rng.randint(20, 60), 95 if match else rng.randint(60, 90),
                             f"GPS-{p['jersey']:02d}"])
    return rows


def wellness_rows(rng, players, start, plants):
    rows = []
    events = {}
    if plants:
        events = {(plants["unique_gk"], 6): "Injury", (players[5]["name"], 4): "Illness", (players[9]["name"], 4): "Illness",
                  (players[12]["name"], 10): "Injury", (players[14]["name"], 10): "Injury", (players[20]["name"], 10): "Injury"}
    for w in range(1, WEEKS + 1):
        for dow in WELLNESS_DAYS:
            d = start + timedelta(days=7 * (w - 1) + dow)
            for p in players:
                ev = events.get((p["name"], w), "") if dow == 0 else ""
                note = ""
                if plants and p["name"] == plants["notes_player"] and w in (5, 8) and dow == 2:
                    note = f"Spoke with Coach {plants['fake_coach']} about sleep"
                rows.append([p["name"], mdy(d), p["position"], round(rng.uniform(5.5, 9), 1), rng.randint(2, 5),
                             rng.randint(1, 5), rng.randint(1, 5), rng.randint(1, 5), rng.randint(2, 5), ev, note])
    return rows


# ------------------------------------------------------------------ CMJ data

def exact_trials(target_mean):
    """Three one-decimal trial values whose mean is as close as possible to target_mean (within 0.02 cm)."""
    base = round(target_mean, 1)
    best = None
    for offs in ((-0.1, 0, 0.1), (0, 0, 0), (0, 0, 0.1), (-0.1, 0, 0), (0, 0.1, 0.1), (-0.1, -0.1, 0), (-0.1, 0.1, 0.1), (-0.1, -0.1, 0.1)):
        trial = [round(base + o, 1) for o in offs]
        err = abs(statistics.fmean(trial) - target_mean)
        if best is None or err < best[0]:
            best = (err, trial)
    return best[1]


METHOD = {"baseline_days": BASELINE_DAYS, "k": 1.5, "expected_trials_per_day": 3, "swc_multiplier": 0.2, "individual_te": False}


def thresholds(data):
    """Squad thresholds for {name: {week: [values in cm]}}, computed with cmj_flags' own method."""
    _, squad, _, athletes = cmj_flags.analyse({n: {w: list(v) for w, v in d.items()} for n, d in data.items()}, METHOD)
    return squad, {n: a["baseline_mean"] for n, a in athletes.items() if a["enough"]}


def draw_day(rng, p):
    """One test day of 3 trials. The day's true height moves enough that the mean of 3 trials varies by DAY_TO_DAY_CV."""
    day_sd = math.sqrt((DAY_TO_DAY_CV * p["jump"]) ** 2 - TRIAL_NOISE_CM ** 2 / 3)
    day_true = p["jump"] + rng.gauss(0, day_sd)
    return [round(day_true + rng.gauss(0, TRIAL_NOISE_CM), 1) for _ in range(3)]


def trial_data(rng, players, plants):
    """Per-trial jump heights in cm: {name: {week: [3 trials]}}. Week CHOSEN_WEEK is engineered when plants are given."""
    jumps = {}
    for p in players:
        jumps[p["name"]] = {w: draw_day(rng, p) for w in range(1, BASELINE_DAYS + 1)}
    est = {p["name"]: p["jump"] for p in players}
    squad = None
    if plants:
        squad, est = thresholds({n: d for n, d in jumps.items() if n != plants["not_enough"]})
        plants["decoy_drop"] = round((squad["swc"] + squad["k_te"]) / 2, 2)
    for p in players:
        name = p["name"]
        for w in range(BASELINE_DAYS + 1, WEEKS + 1):
            if plants and name == plants["not_enough"]:
                continue
            if plants and w == CHOSEN_WEEK and (name in plants["flagged"] or name == plants["decoy"]):
                drop = plants["decoy_drop"] if name == plants["decoy"] else plants["flag_drops"][plants["flagged"].index(name)]
                jumps[name][w] = exact_trials(est[name] - drop)
                continue
            jumps[name][w] = draw_day(rng, p)
            while plants and w == CHOSEN_WEEK and est[name] - statistics.fmean(jumps[name][w]) > squad["swc"] - DECOY_MARGIN_CM:
                jumps[name][w] = draw_day(rng, p)      # in the chosen week only the planted players drop past the SWC
    if plants:
        ne = plants["not_enough"]
        jumps[ne] = {7: jumps[ne][1], 8: jumps[ne][2]}                     # tested only in weeks 7 and 8
    return jumps


def align_decoy_trials(jumps, decoy, target):
    """Set the decoy's trials so its drop in the per-trial file equals target to 0.01 cm, the drop in the per-test file.
    The per-test file can only move in steps of 0.1 inch, so the per-trial file is the one that follows."""
    steps = [i / 10 for i in range(-4, 5)]
    for nudge in sorted(steps, key=abs):
        week1 = [round(jumps[decoy][1][0] + nudge, 1)] + jumps[decoy][1][1:]
        days = [week1] + [jumps[decoy][w] for w in range(2, BASELINE_DAYS + 1)]
        baseline = statistics.fmean(statistics.fmean(d) for d in days)
        centre = round(baseline - target, 1)
        for a in steps:
            for b in steps:
                trials = [round(centre + a, 1), centre, round(centre + b, 1)]
                if round(baseline - statistics.fmean(trials), 2) == round(target, 2):
                    jumps[decoy][1], jumps[decoy][CHOSEN_WEEK] = week1, trials
                    return
    raise RuntimeError("could not match the decoy's drop across the two force plate files")


def trial_rows(rng, players, start, jumps, plants):
    """The per-trial file (cm), with its own planted problems."""
    j = {n: {w: list(t) for w, t in d.items()} for n, d in jumps.items()}
    dup = plants["duplicated_day"] if plants else None
    if plants:
        j[plants["two_trials"]][6] = j[plants["two_trials"]][6][:2]
        j[dup][7] = j[dup][7] * 2
        inch = j[plants["inches"]][9]
        inch[1] = round(inch[1] / IN, 1)                                    # typed in inches
    rows = []
    mass = {p["name"]: p["mass"] for p in players}
    for name, weeks in j.items():
        for w in sorted(weeks):
            d = start + timedelta(days=7 * (w - 1) + 1)                    # Tuesdays
            for i, h in enumerate(weeks[w]):
                trial_no = (i % 3) + 1 if (name == dup and w == 7) else i + 1
                rows.append([name, mdy(d), "CMJ", trial_no, h, round(mass[name] * h * 1.9 + rng.uniform(-80, 80)),
                             round(h / rng.uniform(600, 800), 3), rng.randint(550, 850), mass[name]])
    return rows


def to_coded_cm(inches):
    """An inch value as it appears in the coded file: deidentify.py rounds its conversions to 2 decimals."""
    return round(inches * IN, 2)


def forcedecks_values(rng, jumps, plants):
    """Per-test values in INCHES (one decimal): {name: {week: inches}}. The decoy is tuned so that, after
    conversion back to cm, its week-8 drop sits between the SWC and k x TE despite the coarser rounding."""
    vals = {n: {w: round(statistics.fmean(t) / IN, 1) for w, t in d.items()} for n, d in jumps.items()}
    if not plants:
        return vals, None
    decoy = plants["decoy"]
    for _ in range(60):
        cm = {n: {w: [to_coded_cm(v)] for w, v in d.items() if n != decoy or w != CHOSEN_WEEK} for n, d in vals.items()}
        squad, est = thresholds(cm)
        target = (squad["swc"] + squad["k_te"]) / 2
        v = round((est[decoy] - target) / IN, 1)
        drop = est[decoy] - to_coded_cm(v)
        if squad["swc"] + DECOY_MARGIN_CM <= drop <= squad["k_te"] - DECOY_MARGIN_CM:
            vals[decoy][CHOSEN_WEEK] = v
            break
        # nudge one baseline day of the decoy by 0.1 in (moves its baseline mean by 0.0635 cm) and try again
        vals[decoy][1] = round(vals[decoy][1] + (0.1 if drop < target else -0.1), 1)
    else:
        raise RuntimeError("could not tune the decoy for the per-test file")
    cm = {n: {w: [to_coded_cm(v)] for w, v in d.items()} for n, d in vals.items()}
    squad, est = thresholds(cm)
    plants["thresholds_forcedecks"] = {k: round(v, 3) for k, v in squad.items() if isinstance(v, float)}
    plants["decoy_drop_forcedecks"] = round(est[decoy] - to_coded_cm(vals[decoy][CHOSEN_WEEK]), 2)
    plants["flag_drops_forcedecks"] = [round(est[n] - to_coded_cm(vals[n][CHOSEN_WEEK]), 2) for n in plants["flagged"]]
    return vals, squad


def forcedecks_rows(rng, players, start, vals, plants):
    """One row per test in the real ForceDecks layout. Reps, asymmetry text, negative depth."""
    rows = []
    mass = {p["name"]: p["mass"] for p in players}
    for name, weeks in vals.items():
        for w in sorted(weeks):
            d = start + timedelta(days=7 * (w - 1) + 1)
            copies = 2 if (plants and name == plants["duplicated_day"] and w == 7) else 1
            reps = 2 if (plants and name == plants["two_trials"] and w == 6) else 3
            v = weeks[w]
            if plants and name == plants["inches"] and w == 9:
                v = round(v * IN, 1)                                       # centimetres typed into the inches column
            for c in range(copies):
                h_cm = v * IN
                bw = mass[name]
                asym1 = f"{rng.uniform(0.5, 12):.1f} {rng.choice('LR')}"
                asym2 = f"{rng.randint(1, 30)} {rng.choice('LR')}"
                if plants and name == plants["asym_unreadable"] and w == 5:
                    asym1 = "n/a"
                hour = rng.randint(1, 5)
                rows.append([name, "", "CMJ", mdy(d), f"{hour}:{rng.randint(0, 59):02d} PM", bw, reps, "", 0, v,
                             round(rng.uniform(0.2, 0.6), 2), round(bw * rng.uniform(30, 45)), round(h_cm * rng.uniform(1.3, 1.6), 1),
                             rng.randint(1, 9), round(bw * rng.uniform(10, 13)), round(bw * rng.uniform(10, 13)),
                             round(bw * rng.uniform(15, 25)), round(bw * rng.uniform(15, 25)), rng.randint(240, 330),
                             round(bw * rng.uniform(2.0, 2.6), 1), round(bw * rng.uniform(16, 19)),
                             round(-rng.uniform(20, 36), 1), round(rng.uniform(120, 170), 1), rng.randint(500, 700),
                             round(rng.uniform(0.4, 0.7), 2), asym1, asym2, round(bw * rng.uniform(50, 70)),
                             round(bw * rng.uniform(13, 16), 1)])
    return rows


def season_flags(data, k):
    """Every flag in {name: {week: [values]}}, worked out here with plain arithmetic instead of cmj_flags, so the
    tests compare the script against an independent calculation of the method."""
    days = {n: [(w, statistics.fmean(d[w])) for w in sorted(d)] for n, d in data.items() if len(d) >= BASELINE_DAYS}
    baseline = {n: statistics.fmean(v for _, v in d[:BASELINE_DAYS]) for n, d in days.items()}
    diffs = [b[1] - a[1] for d in days.values() for a, b in zip(d[:BASELINE_DAYS - 1], d[1:BASELINE_DAYS])]
    te = statistics.stdev(diffs) / math.sqrt(2)
    swc = METHOD["swc_multiplier"] * statistics.stdev(baseline.values())
    flags = []
    for n, d in days.items():
        for w, v in d[BASELINE_DAYS:]:
            drop = baseline[n] - v
            if drop > swc and drop > k * te:
                flags.append({"player": n, "week": w, "drop_cm": round(drop, 2)})
    return sorted(flags, key=lambda f: (f["week"], f["player"]))


def trials_after_exclusions(jumps, plants):
    """The per-trial data as cmj_flags.py uses it: the duplicated day and the value in inches left out."""
    data = {n: {w: list(t) for w, t in d.items()} for n, d in jumps.items()}
    data[plants["two_trials"]][6] = data[plants["two_trials"]][6][:2]
    del data[plants["duplicated_day"]][7]
    del data[plants["inches"]][9][1]
    return data


def forcedecks_after_exclusions(vals, plants):
    """The per-test data as cmj_flags.py uses it: the duplicated day and the centimetres-in-inches value left out."""
    data = {n: {w: [to_coded_cm(v)] for w, v in d.items()} for n, d in vals.items()}
    del data[plants["duplicated_day"]][7]
    del data[plants["inches"]][9]
    return data


# ------------------------------------------------------------------ main

def flags_per_week(flags):
    weeks = sorted({f["week"] for f in flags})
    return {str(w): sum(f["week"] == w for f in flags) for w in weeks}


def flag_answers(data, decoy):
    """Every flag at the default k, and at k = 2.0 for comparison."""
    flags = season_flags(data, METHOD["k"])
    flags_k2 = season_flags(data, COMPARISON_K)
    return {"season_flags": flags, "flags_per_week": flags_per_week(flags),
            "comparison_k": COMPARISON_K, "season_flags_comparison_k": flags_k2,
            "flags_per_week_comparison_k": flags_per_week(flags_k2),
            "decoy_flags_in_other_weeks": [f for f in flags if f["player"] == decoy]}


def flag_list(flags):
    return "; ".join(f"week {f['week']} {f['player']} {f['drop_cm']} cm" for f in flags)


def week_counts(per_week):
    return ", ".join(f"week {w}: {n}" for w, n in per_week.items())


def flag_lines(a):
    """The season-wide lines of the expected answers for one force plate file."""
    k1, k2 = a["season_flags"], a["season_flags_comparison_k"]
    first, second = a["flagged_in_chosen_week"]
    wk = a["chosen_week"]
    in_week_k2 = [f["player"] for f in k2 if f["week"] == wk]
    assert in_week_k2 == [first], in_week_k2
    other = "; ".join(f"week {f['week']}, {f['drop_cm']} cm" for f in a["decoy_flags_in_other_weeks"])
    return [f"- At k = 1.5 (the default): both planted athletes flag in week {wk}. At k = {a['comparison_k']} (comparison only): only {first} flags in week {wk}; "
            f"{second}'s drop is short of k x TE.",
            f"- The decoy escapes in week {wk} only. At k = 1.5 it flags from ordinary noise in: {other}.",
            f"- Season total at k = 1.5: {len(k1)} flags. Per week: {week_counts(a['flags_per_week'])}",
            f"- Season total at k = {a['comparison_k']}: {len(k2)} flags. Per week: {week_counts(a['flags_per_week_comparison_k'])}",
            f"- Every flag at k = 1.5: " + flag_list(k1),
            f"- Every flag at k = {a['comparison_k']}: " + flag_list(k2)]


def main(out_dir=None, expected_dir=None):
    OUT, EXPECTED = out_dir or globals()["OUT"], expected_dir or globals()["EXPECTED"]
    rng = random.Random(SEED)
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(EXPECTED, exist_ok=True)
    used = set()
    s1 = make_roster(rng, 28, used)
    gk = next(p for p in s1 if p["position"] == "GK")
    okafor = next((p for p in s1 if p["position"] != "GK" and p["name"] == "Jamal Okafor"), None)
    if okafor is None:                                   # make sure the variant pair exists
        okafor = s1[3]
        used.discard(okafor["name"])
        okafor["name"] = "Jamal Okafor"
        used.add("Jamal Okafor")
    outfield = [p for p in s1 if p is not gk and p is not okafor]
    # the wrong-unit plant must be a player who jumps under 38 cm: 38 cm is 15 inches, and the default plausible
    # range starts at 15 cm, so a higher jump typed in inches would pass the range check (a real limitation)
    low_jumper = next((p for p in outfield[9:] if p["jump"] < 36), outfield[9])
    low_jumper["jump"] = min(low_jumper["jump"], 35.0)
    plants = {
        "conflict": outfield[0]["name"], "variant_full": okafor["name"], "variant_short": "J. Okafor",
        "unique_gk": gk["name"], "notes_player": outfield[1]["name"], "fake_coach": "Priya Raman",
        "ambiguous_date": "09/10/2024",
        "flagged": [outfield[2]["name"], outfield[3]["name"]], "flag_drops": [4.0, 2.6],   # 4.0 flags at k = 1.5 and k = 2.0; 2.6 flags at k = 1.5 only
        "decoy": outfield[4]["name"], "not_enough": outfield[5]["name"],
        "two_trials": outfield[6]["name"], "duplicated_day": outfield[7]["name"], "inches": low_jumper["name"],
        "asym_unreadable": outfield[10]["name"],
    }
    write_csv(os.path.join(OUT, "gps_season1.csv"), GPS_COLS, gps_rows(rng, s1, SEASONS[1], plants))
    write_csv(os.path.join(OUT, "wellness_season1.csv"), WELL_COLS, wellness_rows(rng, s1, SEASONS[1], plants))
    jumps1 = trial_data(rng, s1, plants)
    fd1, _ = forcedecks_values(rng, jumps1, plants)
    align_decoy_trials(jumps1, plants["decoy"], plants["decoy_drop_forcedecks"])
    squad1, est1 = thresholds(jumps1)
    plants["thresholds_trials"] = {k: round(v, 3) for k, v in squad1.items() if isinstance(v, float)}
    plants["decoy_drop"] = plants["decoy_drop_forcedecks"]
    plants["flag_drops"] = [round(est1[n] - statistics.fmean(jumps1[n][CHOSEN_WEEK]), 2) for n in plants["flagged"]]
    write_csv(os.path.join(OUT, "cmj_trials_season1.csv"), TRIAL_COLS, trial_rows(rng, s1, SEASONS[1], jumps1, plants))
    write_csv(os.path.join(OUT, "cmj_season1.csv"), FORCEDECKS_COLS, forcedecks_rows(rng, s1, SEASONS[1], fd1, plants))

    # season 2: 8 of 28 leave (29%), 8 join; no plants
    leavers = rng.sample(s1, 8)
    s2 = [dict(p) for p in s1 if p not in leavers]
    for p in s2:
        p["class_year"] = CLASS_YEARS[min(CLASS_YEARS.index(p["class_year"]) + 1, 3)]
    joiners = make_roster(rng, 8, used)
    for j, leaver in zip(joiners, leavers):
        j["position"], j["jersey"] = leaver["position"], leaver["jersey"]
    s2 += joiners
    write_csv(os.path.join(OUT, "gps_season2.csv"), GPS_COLS, gps_rows(rng, s2, SEASONS[2], None))
    write_csv(os.path.join(OUT, "wellness_season2.csv"), WELL_COLS, wellness_rows(rng, s2, SEASONS[2], None))
    jumps2 = trial_data(rng, s2, None)
    write_csv(os.path.join(OUT, "cmj_trials_season2.csv"), TRIAL_COLS, trial_rows(rng, s2, SEASONS[2], jumps2, None))
    fd2, _ = forcedecks_values(rng, jumps2, None)
    write_csv(os.path.join(OUT, "cmj_season2.csv"), FORCEDECKS_COLS, forcedecks_rows(rng, s2, SEASONS[2], fd2, None))

    common = {
        "chosen_week": CHOSEN_WEEK,
        "flagged_in_chosen_week": plants["flagged"],
        "decoy_not_flagged": plants["decoy"],
        "not_enough_data": plants["not_enough"],
        "duplicated_test_day": {"player": plants["duplicated_day"], "week": 7},
    }
    answers = {
        "note": "All names are made up. Codes are random on every deidentify.py run, so answers are given by name; "
                "look the name up in KEY_DO_NOT_SHARE/athlete_key.csv to find its code.",
        "season1": {
            "season_start_date": SEASONS[1].isoformat(), "weeks": WEEKS, "players": 28,
            "cmj_forcedecks": common | {
                "file": "cmj_season1.csv", "layout": "VALD ForceDecks, one row per test, jump height in inches",
                "planted_drops_cm": plants["flag_drops_forcedecks"], "decoy_drop_cm": plants["decoy_drop_forcedecks"],
                **flag_answers(forcedecks_after_exclusions(fd1, plants), plants["decoy"]),
                "reps_2": {"player": plants["two_trials"], "week": 6},
                "cm_typed_into_inches_column": {"player": plants["inches"], "week": 9},
                "unreadable_asymmetry_value": {"player": plants["asym_unreadable"], "week": 5, "column": "Concentric Impulse % (Asym) (%)"},
                "thresholds_at_generation_cm": plants["thresholds_forcedecks"],
            },
            "cmj_trials": common | {
                "file": "cmj_trials_season1.csv", "layout": "example per-trial layout, one row per jump, cm",
                "planted_drops_cm": plants["flag_drops"], "decoy_drop_cm": plants["decoy_drop"],
                **flag_answers(trials_after_exclusions(jumps1, plants), plants["decoy"]),
                "two_trials_only": {"player": plants["two_trials"], "week": 6},
                "value_in_inches": {"player": plants["inches"], "week": 9, "trial": 2},
                "thresholds_at_generation_cm": plants["thresholds_trials"],
            },
            "deidentify": {
                "conflicting_heights": {"player": plants["conflict"], "heights_cm": [outfield[0]["height"], outfield[0]["height"] + 8],
                                        "weeks_with_second_height": [3, 9, 12]},
                "name_variant_pair": [plants["variant_short"], plants["variant_full"]],
                "ambiguous_date_present": plants["ambiguous_date"],
                "notes_column_with_a_name": {"column": "Notes", "file": "wellness_season1.csv", "name": plants["fake_coach"]},
                "unique_goalkeeper": plants["unique_gk"],
                "goalkeeper_injury_week": 6,
                "columns_to_drop_examples": ["Jersey Number", "Device ID", "Notes"],
            },
        },
        "season2": {"season_start_date": SEASONS[2].isoformat(), "players": 28,
                    "left_after_season1": sorted(p["name"] for p in leavers),
                    "joined_in_season2": sorted(p["name"] for p in joiners),
                    "turnover_percent": round(100 * 8 / 28, 1), "planted_problems": "none"},
    }
    with open(os.path.join(EXPECTED, "expected_answers.json"), "w", newline="\n", encoding="utf-8") as f:
        json.dump(answers, f, indent=2)
    fdk, tr, d = answers["season1"]["cmj_forcedecks"], answers["season1"]["cmj_trials"], answers["season1"]["deidentify"]
    md = ["# Expected answers for the synthetic squad", "",
          "All names are made up. Codes change on every run of deidentify.py, so these are by name; the key file maps them.", "",
          "Jump height varies by about 4% from day to day in every week, so ordinary days in other weeks can also be flagged.",
          "Only week 8 is engineered; the lists below are for that week, followed by every flag in the season.", "",
          "## cmj_flags.py on cmj_trials_season1.csv (per-trial layout, cm, the default) after `deidentify.py force_plate_trials`",
          f"- Chosen week: {tr['chosen_week']}; flagged: {tr['flagged_in_chosen_week'][0]} ({tr['planted_drops_cm'][0]} cm), "
          f"{tr['flagged_in_chosen_week'][1]} ({tr['planted_drops_cm'][1]} cm)",
          f"- Decoy, NOT flagged: {tr['decoy_not_flagged']} (drop {tr['decoy_drop_cm']} cm: past the SWC, short of k x TE)",
          f"- Not enough data: {tr['not_enough_data']} (tested in weeks 7 and 8 only)",
          f"- Only 2 trials: {tr['two_trials_only']['player']}, week 6",
          f"- Duplicated test day: {tr['duplicated_test_day']['player']}, week 7 (trials 1,2,3,1,2,3; day excluded)",
          f"- Value in inches: {tr['value_in_inches']['player']}, week 9, trial 2 (excluded; day then has 2 trials)",
          f"- Thresholds when the data were generated: TE {tr['thresholds_at_generation_cm']['te']} cm, "
          f"SWC {tr['thresholds_at_generation_cm']['swc']} cm, k x TE {tr['thresholds_at_generation_cm']['k_te']} cm",
          *flag_lines(tr),
          "", "## cmj_flags.py on cmj_season1.csv (ForceDecks layout, per test, inches, the second option) after `deidentify.py force_plate`",
          f"- Chosen week: {fdk['chosen_week']}; flagged: {fdk['flagged_in_chosen_week'][0]} ({fdk['planted_drops_cm'][0]} cm), "
          f"{fdk['flagged_in_chosen_week'][1]} ({fdk['planted_drops_cm'][1]} cm)",
          f"- Decoy, NOT flagged: {fdk['decoy_not_flagged']} (drop {fdk['decoy_drop_cm']} cm: past the SWC, short of k x TE)",
          f"- Not enough data: {fdk['not_enough_data']} (tested in weeks 7 and 8 only)",
          f"- Reps = 2: {fdk['reps_2']['player']}, week 6 (a note; trials are not in a per-test export)",
          f"- Duplicated test day: {fdk['duplicated_test_day']['player']}, week 7 (two rows; day excluded)",
          f"- Centimetres typed into the inches column: {fdk['cm_typed_into_inches_column']['player']}, week 9 (excluded; day left out)",
          f"- Unreadable asymmetry value: {fdk['unreadable_asymmetry_value']['player']}, week 5 (deidentify.py warning)",
          f"- Thresholds when the data were generated: TE {fdk['thresholds_at_generation_cm']['te']} cm, "
          f"SWC {fdk['thresholds_at_generation_cm']['swc']} cm, k x TE {fdk['thresholds_at_generation_cm']['k_te']} cm",
          *flag_lines(fdk),
          "", "## deidentify.py on season 1",
          f"- Conflicting heights: {d['conflicting_heights']['player']} ({d['conflicting_heights']['heights_cm'][0]} and "
          f"{d['conflicting_heights']['heights_cm'][1]} cm) in gps_season1.csv",
          f"- Name variant pair: {d['name_variant_pair'][0]} and {d['name_variant_pair'][1]} in gps_season1.csv",
          f"- Ambiguous date: {d['ambiguous_date_present']} (the run stops if date_format is blank)",
          f"- Notes column naming a coach: {d['notes_column_with_a_name']['name']} in wellness_season1.csv (dropped by the default settings; "
          f"warned about if kept)",
          f"- Unique goalkeeper: {d['unique_goalkeeper']} (athlete-level warning in gps and wellness; row-level warning for the week-6 injury)",
          "- ForceDecks file: jump height converted from inches to cm, Additional Load from lb to kg, asymmetry columns split into number and side",
          "", "## Season 2", f"- {len(answers['season2']['left_after_season1'])} players left, {len(answers['season2']['joined_in_season2'])} joined "
          f"({answers['season2']['turnover_percent']}% turnover). No planted problems."]
    with open(os.path.join(EXPECTED, "expected_answers.md"), "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"Wrote 8 files to {OUT} and the expected answers to {EXPECTED}.")
    print(f"Per-trial thresholds: {plants['thresholds_trials']}; decoy drop {plants['decoy_drop']} cm")
    print(f"ForceDecks thresholds: {plants['thresholds_forcedecks']}; decoy drop {plants['decoy_drop_forcedecks']} cm")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the data files here instead of synthetic_data/")
    ap.add_argument("--expected", help="write the expected answers here instead of expected_output/")
    a = ap.parse_args()
    main(a.out, a.expected)
