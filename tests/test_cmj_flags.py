"""Tests for cmj_flags.py. Run from the repository root:  python -m unittest discover -s tests"""
import csv
import hashlib
import json
import math
import os
import shutil
import statistics
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cmj_flags  # noqa: E402
import deidentify  # noqa: E402

with open(os.path.join(ROOT, "expected_output", "expected_answers.json"), encoding="utf-8") as f:
    _ALL = json.load(f)["season1"]
EXP_FD = _ALL["cmj_forcedecks"]
EXP_TR = _ALL["cmj_trials"]
PER_TEST_COLUMNS = {"jump_height_column": "Jump Height (Imp-Mom)", "trial_column": "", "reps_column": "Reps",
                    "depth_column": "Countermovement Depth"}


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class MethodTests(unittest.TestCase):
    """Hand-checkable numbers on a tiny made-up squad."""

    def test_te_swc_and_flag_by_hand(self):
        trials = {
            "A": {1: [30.0], 2: [31.0], 3: [30.0], 4: [31.0], 5: [27.0], 6: [30.4]},
            "B": {1: [40.0], 2: [42.0], 3: [40.0], 4: [42.0], 5: [41.0]},
            "C": {1: [35.0], 2: [35.0]},   # not enough data
        }
        s = {"baseline_days": 4, "k": 1.5, "expected_trials_per_day": 1, "swc_multiplier": 0.2, "individual_te": False}
        results, squad, warnings, athletes = cmj_flags.analyse(trials, s)
        diffs = [1, -1, 1, 2, -2, 2]                    # consecutive baseline differences, A then B
        te = statistics.stdev(diffs) / math.sqrt(2)
        self.assertAlmostEqual(squad["te"], te, places=6)
        self.assertAlmostEqual(squad["swc"], 0.2 * statistics.stdev([30.5, 41.0]), places=6)
        by = {(r["athlete"], r["day"]): r for r in results}
        self.assertEqual(by[("A", 5)]["status"], "FLAG")             # drop 3.5 > both
        self.assertEqual(by[("A", 6)]["status"], "no flag")          # drop 0.1
        self.assertEqual(by[("B", 5)]["status"], "no flag")          # drop 0
        self.assertEqual(by[("C", 1)]["status"], "not enough data")
        self.assertEqual(by[("A", 1)]["status"], "baseline")
        self.assertIsNone(by[("C", 1)]["baseline"])

    def test_improvement_is_never_flagged(self):
        trials = {"A": {i: [30.0 + (i % 2)] for i in range(1, 5)} | {5: [45.0]},
                  "B": {i: [40.0 + (i % 2)] for i in range(1, 5)}}
        s = {"baseline_days": 4, "k": 1.5, "expected_trials_per_day": 1, "swc_multiplier": 0.2, "individual_te": False}
        results, _, _, _ = cmj_flags.analyse(trials, s)
        self.assertEqual([r["status"] for r in results if r["athlete"] == "A" and r["day"] == 5], ["no flag"])

    def test_heading_matching_ignores_units_and_end_spaces(self):
        headers = ["Name", "Jump Height (Imp-Mom) in Inches [in] ", "RSI-modified [m/s] "]
        self.assertEqual(cmj_flags.find_column("Jump Height (Imp-Mom)", headers, "x"), headers[1])
        self.assertEqual(cmj_flags.find_column("Jump Height (Imp-Mom) [cm]", headers, "x"), headers[1])
        self.assertEqual(cmj_flags.find_column("RSI-modified [m/s]", headers, "x"), headers[2])
        self.assertEqual(cmj_flags.unit_of(headers[1]), "in")
        with self.assertRaises(cmj_flags.StopRun):
            cmj_flags.find_column("Nope", headers, "x")


class _SquadBase(unittest.TestCase):
    """Shared machinery: de-identify one force plate file, run cmj_flags on it, map names to codes."""
    profile = None
    expected = None
    cmj_overrides = {}

    @classmethod
    def setUpClass(cls):
        if cls.profile is None:
            raise unittest.SkipTest("base class")
        cls.tmp = tempfile.mkdtemp(prefix="cmj_")
        settings = json.loads(json.dumps(deidentify.SETTINGS))
        for p in settings["profiles"].values():
            p["input_file"] = os.path.join(ROOT, p["input_file"])
        r = deidentify.run(settings, cls.profile, output_override=os.path.join(cls.tmp, "coded"), key_override=os.path.join(cls.tmp, "key"))
        cls.deid = r
        with open(r["key_path"], newline="", encoding="utf-8") as f:
            cls.code = {row["original_id"]: row["code"] for row in csv.DictReader(f)}
        cls.name = {v: k for k, v in cls.code.items()}
        cls.coded_file = r["output_file"]
        cls.settings = dict(cmj_flags.SETTINGS) | cls.cmj_overrides
        cls.settings["input_file"] = cls.coded_file
        cls.settings["output_folder"] = os.path.join(cls.tmp, "cmj")
        cls.before = file_hash(cls.coded_file)
        cls.out = cmj_flags.run(cls.settings, explain_code=cls.code[cls.expected["flagged_in_chosen_week"][0]])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_input_untouched(self):
        self.assertEqual(self.before, file_hash(self.coded_file))

    def test_exactly_the_expected_flags(self):
        wk = self.expected["chosen_week"]
        flags = {self.name[r["athlete"]] for r in self.out["results"] if r["status"] == "FLAG" and r["day"] == wk}
        self.assertEqual(flags, set(self.expected["flagged_in_chosen_week"]),
                         "the flagged set must be exactly the two planted athletes in the chosen week")
        drops = {self.name[r["athlete"]]: r["drop"] for r in self.out["results"] if r["status"] == "FLAG" and r["day"] == wk}
        for name, drop in zip(self.expected["flagged_in_chosen_week"], self.expected["planted_drops_cm"]):
            self.assertAlmostEqual(drops[name], drop, places=2)

    def test_decoy_is_the_only_other_athlete_past_the_swc_in_the_chosen_week(self):
        wk, swc = self.expected["chosen_week"], self.out["squad"]["swc"]
        past = {self.name[r["athlete"]] for r in self.out["results"]
                if r["day"] == wk and r["status"] == "no flag" and r["drop"] > swc}
        self.assertEqual(past, {self.expected["decoy_not_flagged"]})

    def test_decoy_not_flagged(self):
        decoy = self.code[self.expected["decoy_not_flagged"]]
        row = next(r for r in self.out["results"] if r["athlete"] == decoy and r["day"] == self.expected["chosen_week"])
        self.assertEqual(row["status"], "no flag")
        self.assertGreaterEqual(row["drop"] - self.out["squad"]["swc"], 0.3, "the decoy must clearly exceed the SWC")
        self.assertGreaterEqual(self.out["squad"]["k_te"] - row["drop"], 0.3, "the decoy must clearly fall short of k x TE")
        self.assertEqual(row["drop"], self.expected["decoy_drop_cm"], "the script must report the drop in the expected answers")

    def test_not_enough_data(self):
        code = self.code[self.expected["not_enough_data"]]
        statuses = {r["status"] for r in self.out["results"] if r["athlete"] == code}
        self.assertEqual(statuses, {"not enough data"})

    def test_duplicated_day_excluded(self):
        code = self.code[self.expected["duplicated_test_day"]["player"]]
        wk = self.expected["duplicated_test_day"]["week"]
        self.assertTrue(any(a == code and d == str(wk) and "duplicated" in m for a, d, m in self.out["exclusions"]))
        self.assertFalse(any(r["athlete"] == code and r["day"] == wk for r in self.out["results"]), "the duplicated day must not be in the results")

    def test_counts_and_thresholds(self):
        c, sq = self.out["counts"], self.out["squad"]
        self.assertEqual(c["athletes"], 28)
        gen = self.expected["thresholds_at_generation_cm"]
        self.assertAlmostEqual(sq["te"], gen["te"], places=2)
        self.assertAlmostEqual(sq["swc"], gen["swc"], places=2)
        self.assertAlmostEqual(sq["k_te"], gen["k_te"], places=2)
        self.assertEqual(sq["effective_threshold"], max(sq["swc"], sq["k_te"]))

    def test_outputs_and_explain(self):
        self.assertTrue(os.path.exists(self.out["results_file"]))
        self.assertTrue(os.path.exists(self.out["report_file"]))
        text = "\n".join(self.out["explain"])
        self.assertIn("Baseline mean", text)
        self.assertIn("=> FLAG", text)
        report = "\n".join(self.out["report"])
        self.assertIn("prompt to check in", report)
        self.assertIn("version", report)

    def test_missing_column_stops(self):
        s = dict(self.settings) | {"jump_height_column": "Nope"}
        with self.assertRaises(cmj_flags.StopRun):
            cmj_flags.run(s)


class ForceDecksPerTestTests(_SquadBase):
    """The real VALD ForceDecks layout: one row per test, inches, after deidentify.py converted it to cm."""
    profile = "force_plate"
    expected = EXP_FD
    cmj_overrides = PER_TEST_COLUMNS

    def test_mode_and_unit_reported(self):
        self.assertEqual(self.out["info"]["mode"], "per-test")
        report = "\n".join(self.out["report"])
        self.assertIn("per-test", report)
        self.assertIn("could not be run", report)
        self.assertIn("per-trial export is better", report)
        self.assertEqual(self.out["info"]["jump_unit"], "cm")      # deidentify already converted inches to cm

    def test_reps_2_is_a_note_not_an_exclusion(self):
        code = self.code[self.expected["reps_2"]["player"]]
        wk = self.expected["reps_2"]["week"]
        self.assertTrue(any(a == code and d == str(wk) and "Reps column shows 2" in m for a, d, m in self.out["warnings"]))
        self.assertTrue(any(r["athlete"] == code and r["day"] == wk for r in self.out["results"]))

    def test_cm_typed_into_inches_column_is_excluded(self):
        code = self.code[self.expected["cm_typed_into_inches_column"]["player"]]
        wk = self.expected["cm_typed_into_inches_column"]["week"]
        msgs = [m for a, d, m in self.out["exclusions"] if a == code and d == str(wk)]
        self.assertTrue(any("outside the plausible range" in m and "inches column" in m for m in msgs), msgs)
        self.assertFalse(any(r["athlete"] == code and r["day"] == wk for r in self.out["results"]))

    def test_depth_negative_values_are_valid(self):
        self.assertFalse(any("countermovement depth" in m for _, _, m in self.out["warnings"]),
                         "all synthetic depths are negative and in range, so no depth warning is expected")


class PerTrialTests(_SquadBase):
    """The example per-trial layout in cm."""
    profile = "force_plate_trials"
    expected = EXP_TR

    def test_mode(self):
        self.assertEqual(self.out["info"]["mode"], "per-trial")

    def test_day_to_day_variation_is_about_four_percent(self):
        means = [r["baseline"] for r in self.out["results"] if r["status"] == "baseline"]
        self.assertAlmostEqual(self.out["squad"]["te"] / statistics.fmean(means), 0.04, delta=0.005)

    def test_decoy_drop_matches_the_per_test_file(self):
        self.assertEqual(EXP_TR["decoy_drop_cm"], EXP_FD["decoy_drop_cm"])

    def test_two_trials_warning(self):
        code = self.code[self.expected["two_trials_only"]["player"]]
        self.assertTrue(any(a == code and d == str(self.expected["two_trials_only"]["week"]) and "2 trial" in m
                            for a, d, m in self.out["warnings"]))

    def test_inches_value_excluded(self):
        code = self.code[self.expected["value_in_inches"]["player"]]
        wk = self.expected["value_in_inches"]["week"]
        self.assertTrue(any(a == code and d == str(wk) and "inches" in m for a, d, m in self.out["exclusions"]))
        row = next(r for r in self.out["results"] if r["athlete"] == code and r["day"] == wk)
        self.assertEqual(row["trials"], 2)


class RawInchesFileTests(unittest.TestCase):
    """cmj_flags.py read straight from the uncoded ForceDecks file: the inches conversion happens inside cmj_flags."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="cmjin_")
        cls.settings = dict(cmj_flags.SETTINGS) | {
            "input_file": os.path.join(ROOT, "synthetic_data", "cmj_season1.csv"), "output_folder": os.path.join(cls.tmp, "o"),
            "athlete_column": "Name", "day_column": "Date", "day_format": "%m/%d/%Y"} | PER_TEST_COLUMNS
        cls.out = cmj_flags.run(cls.settings)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_inches_converted_and_reported(self):
        self.assertEqual(self.out["info"]["jump_unit"], "in")
        self.assertTrue(self.out["info"]["converted"])
        self.assertIn("converted to cm (x 2.54)", "\n".join(self.out["report"]))
        # the raw file's first row, converted by hand, must equal the test-day value the script reports
        with open(self.settings["input_file"], newline="", encoding="utf-8") as f:
            first = next(csv.DictReader(f))
        raw_in = float(first["Jump Height (Imp-Mom) in Inches [in] "])
        name = first["Name"]
        day = cmj_flags.day_key(first["Date"], "%m/%d/%Y")
        row = next(r for r in self.out["results"] if r["athlete"] == name and r["day"] == day)
        self.assertAlmostEqual(row["test_day_value"], round(raw_in * 2.54, 2), places=2)

    def test_same_flags_as_the_coded_route(self):
        season_start = cmj_flags.day_key("2024-08-05", "")
        flags = {r["athlete"] for r in self.out["results"] if r["status"] == "FLAG"
                 and (r["day"] - season_start).days // 7 + 1 == EXP_FD["chosen_week"]}
        self.assertEqual(flags, set(EXP_FD["flagged_in_chosen_week"]))

    def test_cm_in_inches_column_note(self):
        msgs = [m for _, _, m in self.out["exclusions"] if "centimetres typed into the in column" in m]
        self.assertEqual(len(msgs), 1)

    def test_missing_unit_stops(self):
        s = dict(self.settings) | {"jump_height_column": "RSI-modified"}     # has a unit, but not a length
        with self.assertRaises(cmj_flags.StopRun) as cm:
            cmj_flags.run(s)
        self.assertIn("unit", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
