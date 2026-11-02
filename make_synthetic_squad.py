"""
make_synthetic_squad.py  -  build the made-up soccer squad used to demonstrate and test the two scripts.

Nothing here is real. Names come from a fixed list and are combined at random; any match with a real
person is a coincidence. The random seed is fixed, so running this again produces identical files.

It writes, to synthetic_data/:
    gps_season1.csv, cmj_season1.csv, wellness_season1.csv     (28 players, 14 weeks)
    gps_season2.csv, cmj_season2.csv, wellness_season2.csv     (8 players replaced: 29% turnover)
and, to expected_output/:
    expected_answers.json      every planted problem and the expected flags, by player name
    expected_answers.md        the same, written out for reading

Planted de-identification problems (season 1):
    - one player name recorded with two heights 8 cm apart (two people under one name, or a typo)
    - the pair "J. Okafor" / "Jamal Okafor"  (a name variant)
    - dates written month/day/year, including 09/10/2024, which reads two ways if no format is set
    - a wellness Notes column that mentions a (made-up) coach by name
    - one goalkeeper, unique on position
Planted CMJ problems (season 1):
    - one player with only 2 trials on one test day
    - one player whose test day was entered twice (trials 1,2,3,1,2,3)
    - one trial typed in inches
    - in week 8, EXACTLY two players drop enough to flag; one decoy drops past the SWC but not past
      k x TE; one player has too few baseline days

Run:  python make_synthetic_squad.py
"""

import csv
import json
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
INJURY_WORDS = ["Injury", "Illness"]

# column layouts: examples in the style of common systems, matching the examples in deidentify.py SETTINGS
GPS_COLS = ["Player Name", "Jersey Number", "Date", "Session Type", "Position", "Class Year", "Height (cm)",
            "Body Mass (kg)", "Total Distance (m)", "High Speed Running (m)", "Sprint Distance (m)",
            "Max Velocity (km/h)", "Player Load", "Accelerations", "Decelerations", "Duration (min)", "Device ID"]
CMJ_COLS = ["Name", "Date", "Test Type", "Trial", "Jump Height (cm)", "Peak Power (W)", "RSI-modified",
            "Contraction Time (ms)", "Body Mass (kg)"]
WELL_COLS = ["Athlete", "Date", "Position", "Sleep Hours", "Sleep Quality (1-5)", "Fatigue (1-5)", "Soreness (1-5)",
             "Stress (1-5)", "Mood (1-5)", "Injury/Illness", "Notes"]


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


def cmj_rows(rng, players, start, plants):
    """Trial-level CMJ data. With plants, week CHOSEN_WEEK is engineered so the expected answers are exact."""
    trial_noise = 0.8        # cm, within a day
    day_noise = 0.7          # cm, between baseline days
    jumps = {}               # name -> {week: [trials]}
    for p in players:
        jumps[p["name"]] = {}
        for w in range(1, BASELINE_DAYS + 1):
            day_true = p["jump"] + rng.gauss(0, day_noise)
            jumps[p["name"]][w] = [round(day_true + rng.gauss(0, trial_noise), 1) for _ in range(3)]
    squad = None
    if plants:
        # estimated baselines and the real thresholds, computed with the method in cmj_flags.py
        trials = {n: {w: list(t) for w, t in d.items()} for n, d in jumps.items() if n != plants["not_enough"]}
        _, squad, _, athletes = cmj_flags.analyse(trials, {"baseline_days": BASELINE_DAYS, "k": 1.5, "expected_trials_per_day": 3,
                                                           "swc_multiplier": 0.2, "individual_te": False})
        est = {n: a["baseline_mean"] for n, a in athletes.items()}
        plants["decoy_drop"] = round((squad["swc"] + squad["k_te"]) / 2, 2)
        plants["thresholds"] = {k: round(v, 3) for k, v in squad.items() if isinstance(v, float)}
    for p in players:
        name = p["name"]
        for w in range(BASELINE_DAYS + 1, WEEKS + 1):
            if plants and name == plants["not_enough"]:
                continue
            centre = (est[name] if plants else p["jump"]) + rng.uniform(-0.3, 0.6)
            if plants and w == CHOSEN_WEEK and (name in plants["flagged"] or name == plants["decoy"]):
                drop = plants["decoy_drop"] if name == plants["decoy"] else plants["flag_drops"][plants["flagged"].index(name)]
                jumps[name][w] = exact_trials(est[name] - drop)
                continue
            jumps[name][w] = [round(centre + rng.uniform(-0.25, 0.25), 1) for _ in range(3)]
    if plants:
        ne = plants["not_enough"]
        jumps[ne] = {7: jumps[ne][1], 8: jumps[ne][2]}                     # tested only in weeks 7 and 8
        jumps[plants["two_trials"]][6] = jumps[plants["two_trials"]][6][:2]
        jumps[plants["duplicated_day"]][7] = jumps[plants["duplicated_day"]][7] * 2
        inch = jumps[plants["inches"]][9]
        inch[1] = round(inch[1] / 2.54, 1)                                   # typed in inches
    rows = []
    mass = {p["name"]: p["mass"] for p in players}
    for name, weeks in jumps.items():
        for w in sorted(weeks):
            d = start + timedelta(days=7 * (w - 1) + 1)                    # Tuesdays
            for i, h in enumerate(weeks[w]):
                trial_no = i + 1 if not (plants and name == plants["duplicated_day"] and w == 7) else (i % 3) + 1
                rows.append([name, mdy(d), "CMJ", trial_no, h, round(mass[name] * h * 1.9 + rng.uniform(-80, 80)),
                             round(h / rng.uniform(600, 800), 3), rng.randint(550, 850), mass[name]])
    return rows, squad


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
    # the inches plant must be a player who jumps under 38 cm: 38 cm is 15 inches, and the default plausible
    # range starts at 15 cm, so a higher jump typed in inches would pass the range check (a real limitation)
    low_jumper = next((p for p in outfield[9:] if p["jump"] < 36), outfield[9])
    low_jumper["jump"] = min(low_jumper["jump"], 35.0)
    plants = {
        "conflict": outfield[0]["name"], "variant_full": okafor["name"], "variant_short": "J. Okafor",
        "unique_gk": gk["name"], "notes_player": outfield[1]["name"], "fake_coach": "Priya Raman",
        "ambiguous_date": "09/10/2024",
        "flagged": [outfield[2]["name"], outfield[3]["name"]], "flag_drops": [3.0, 2.6],
        "decoy": outfield[4]["name"], "not_enough": outfield[5]["name"],
        "two_trials": outfield[6]["name"], "duplicated_day": outfield[7]["name"], "inches": low_jumper["name"],
    }
    write_csv(os.path.join(OUT, "gps_season1.csv"), GPS_COLS, gps_rows(rng, s1, SEASONS[1], plants))
    write_csv(os.path.join(OUT, "wellness_season1.csv"), WELL_COLS, wellness_rows(rng, s1, SEASONS[1], plants))
    cmj1, squad = cmj_rows(rng, s1, SEASONS[1], plants)
    write_csv(os.path.join(OUT, "cmj_season1.csv"), CMJ_COLS, cmj1)

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
    cmj2, _ = cmj_rows(rng, s2, SEASONS[2], None)
    write_csv(os.path.join(OUT, "cmj_season2.csv"), CMJ_COLS, cmj2)

    answers = {
        "note": "All names are made up. Codes are random on every deidentify.py run, so answers are given by name; "
                "look the name up in KEY_DO_NOT_SHARE/athlete_key.csv to find its code.",
        "season1": {
            "season_start_date": SEASONS[1].isoformat(), "weeks": WEEKS, "players": 28,
            "cmj": {
                "chosen_week": CHOSEN_WEEK,
                "flagged_in_chosen_week": plants["flagged"], "planted_drops_cm": plants["flag_drops"],
                "decoy_not_flagged": plants["decoy"], "decoy_drop_cm": plants["decoy_drop"],
                "not_enough_data": plants["not_enough"],
                "two_trials_only": {"player": plants["two_trials"], "week": 6},
                "duplicated_test_day": {"player": plants["duplicated_day"], "week": 7},
                "value_in_inches": {"player": plants["inches"], "week": 9, "trial": 2},
                "thresholds_at_generation_cm": plants["thresholds"],
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
    with open(os.path.join(EXPECTED, "expected_answers.json"), "w", encoding="utf-8") as f:
        json.dump(answers, f, indent=2)
    c, d = answers["season1"]["cmj"], answers["season1"]["deidentify"]
    md = ["# Expected answers for the synthetic squad", "",
          "All names are made up. Codes change on every run of deidentify.py, so these are by name; the key file maps them.", "",
          "## cmj_flags.py on season 1 (after deidentify.py force_plate)",
          f"- Chosen week: {c['chosen_week']}",
          f"- Flagged in that week: {c['flagged_in_chosen_week'][0]} (drop {c['planted_drops_cm'][0]} cm), "
          f"{c['flagged_in_chosen_week'][1]} (drop {c['planted_drops_cm'][1]} cm)",
          f"- Decoy, NOT flagged: {c['decoy_not_flagged']} (drop {c['decoy_drop_cm']} cm: past the SWC, short of k x TE)",
          f"- Not enough data: {c['not_enough_data']} (tested in weeks 7 and 8 only)",
          f"- Only 2 trials: {c['two_trials_only']['player']}, week 6",
          f"- Duplicated test day: {c['duplicated_test_day']['player']}, week 7 (trials 1,2,3,1,2,3; day excluded)",
          f"- Value in inches: {c['value_in_inches']['player']}, week 9, trial 2 (excluded; day then has 2 trials)",
          f"- Thresholds when the data were generated: TE {c['thresholds_at_generation_cm']['te']} cm, "
          f"SWC {c['thresholds_at_generation_cm']['swc']} cm, k x TE {c['thresholds_at_generation_cm']['k_te']} cm",
          "", "## deidentify.py on season 1",
          f"- Conflicting heights: {d['conflicting_heights']['player']} ({d['conflicting_heights']['heights_cm'][0]} and "
          f"{d['conflicting_heights']['heights_cm'][1]} cm) in gps_season1.csv",
          f"- Name variant pair: {d['name_variant_pair'][0]} and {d['name_variant_pair'][1]} in gps_season1.csv",
          f"- Ambiguous date: {d['ambiguous_date_present']} (the run stops if date_format is blank)",
          f"- Notes column naming a coach: {d['notes_column_with_a_name']['name']} in wellness_season1.csv (dropped by the default settings; "
          f"warned about if kept)",
          f"- Unique goalkeeper: {d['unique_goalkeeper']} (athlete-level warning in gps and wellness; row-level warning for the week-6 injury)",
          "", "## Season 2", f"- {len(answers['season2']['left_after_season1'])} players left, {len(answers['season2']['joined_in_season2'])} joined "
          f"({answers['season2']['turnover_percent']}% turnover). No planted problems."]
    with open(os.path.join(EXPECTED, "expected_answers.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(f"Wrote 6 files to {OUT} and the expected answers to {EXPECTED}.")
    print(f"Thresholds at generation: {plants['thresholds']}; decoy drop {plants['decoy_drop']} cm")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the data files here instead of synthetic_data/")
    ap.add_argument("--expected", help="write the expected answers here instead of expected_output/")
    a = ap.parse_args()
    main(a.out, a.expected)
