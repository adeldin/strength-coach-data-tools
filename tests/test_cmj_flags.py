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
    EXPECTED = json.load(f)["season1"]["cmj"]


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
        self.assertEqual(by[("B", 5)]["status"], "no flag")          # improvement is never flagged... drop is 0
        self.assertEqual(by[("C", 1)]["status"], "not enough data")
        self.assertEqual(by[("A", 1)]["status"], "baseline")
        self.assertIsNone(by[("C", 1)]["baseline"])

    def test_improvement_is_never_flagged(self):
        trials = {"A": {i: [30.0 + (i % 2)] for i in range(1, 5)} | {5: [45.0]},
                  "B": {i: [40.0 + (i % 2)] for i in range(1, 5)}}
        s = {"baseline_days": 4, "k": 1.5, "expected_trials_per_day": 1, "swc_multiplier": 0.2, "individual_te": False}
        results, _, _, _ = cmj_flags.analyse(trials, s)
        self.assertEqual([r["status"] for r in results if r["athlete"] == "A" and r["day"] == 5], ["no flag"])


class SyntheticSquadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="cmj_")
        settings = json.loads(json.dumps(deidentify.SETTINGS))
        for p in settings["profiles"].values():
            p["input_file"] = os.path.join(ROOT, p["input_file"])
        key_dir = os.path.join(cls.tmp, "key")
        r = deidentify.run(settings, "force_plate", output_override=os.path.join(cls.tmp, "coded"), key_override=key_dir)
        with open(r["key_path"], newline="", encoding="utf-8") as f:
            cls.code = {row["original_id"]: row["code"] for row in csv.DictReader(f)}
        cls.name = {v: k for k, v in cls.code.items()}
        cls.coded_file = r["output_file"]
        cls.settings = dict(cmj_flags.SETTINGS)
        cls.settings["input_file"] = cls.coded_file
        cls.settings["output_folder"] = os.path.join(cls.tmp, "cmj")
        cls.before = file_hash(cls.coded_file)
        cls.out = cmj_flags.run(cls.settings, explain_code=cls.code[EXPECTED["flagged_in_chosen_week"][0]])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_input_untouched(self):
        self.assertEqual(self.before, file_hash(self.coded_file))

    def test_exactly_the_expected_flags(self):
        flags = {(self.name[r["athlete"]], r["day"]) for r in self.out["results"] if r["status"] == "FLAG"}
        expected = {(n, EXPECTED["chosen_week"]) for n in EXPECTED["flagged_in_chosen_week"]}
        self.assertEqual(flags, expected, "the flagged set must be exactly the two planted athletes in the chosen week")

    def test_decoy_not_flagged(self):
        decoy = self.code[EXPECTED["decoy_not_flagged"]]
        row = next(r for r in self.out["results"] if r["athlete"] == decoy and r["day"] == EXPECTED["chosen_week"])
        self.assertEqual(row["status"], "no flag")
        self.assertGreater(row["drop"], self.out["squad"]["swc"], "the decoy must exceed the SWC")
        self.assertLess(row["drop"], self.out["squad"]["k_te"], "the decoy must not exceed k x TE")

    def test_not_enough_data(self):
        code = self.code[EXPECTED["not_enough_data"]]
        statuses = {r["status"] for r in self.out["results"] if r["athlete"] == code}
        self.assertEqual(statuses, {"not enough data"})

    def test_two_trials_warning(self):
        code = self.code[EXPECTED["two_trials_only"]["player"]]
        self.assertTrue(any(a == code and d == str(EXPECTED["two_trials_only"]["week"]) and "2 trial" in m
                            for a, d, m in self.out["warnings"]))

    def test_duplicated_day_excluded(self):
        code = self.code[EXPECTED["duplicated_test_day"]["player"]]
        wk = EXPECTED["duplicated_test_day"]["week"]
        self.assertTrue(any(a == code and d == str(wk) and "duplicated" in m for a, d, m in self.out["exclusions"]))
        self.assertFalse(any(r["athlete"] == code and r["day"] == wk for r in self.out["results"]), "the duplicated day must not be in the results")

    def test_inches_value_excluded(self):
        code = self.code[EXPECTED["value_in_inches"]["player"]]
        wk = EXPECTED["value_in_inches"]["week"]
        self.assertTrue(any(a == code and d == str(wk) and "inches" in m for a, d, m in self.out["exclusions"]))
        row = next(r for r in self.out["results"] if r["athlete"] == code and r["day"] == wk)
        self.assertEqual(row["trials"], 2)

    def test_counts_and_thresholds(self):
        c, sq = self.out["counts"], self.out["squad"]
        self.assertEqual(c["athletes"], 28)
        gen = EXPECTED["thresholds_at_generation_cm"]
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


if __name__ == "__main__":
    unittest.main()
