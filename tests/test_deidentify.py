"""Tests for deidentify.py on the synthetic squad. Run from the repository root:  python -m unittest discover -s tests"""
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import deidentify  # noqa: E402

with open(os.path.join(ROOT, "expected_output", "expected_answers.json"), encoding="utf-8") as f:
    EXPECTED = json.load(f)["season1"]["deidentify"]


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class DeidentifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="deid_")
        self.settings = json.loads(json.dumps(deidentify.SETTINGS))
        for p in self.settings["profiles"].values():
            p["input_file"] = os.path.join(ROOT, p["input_file"])
        self.out = os.path.join(self.tmp, "out")
        self.key = os.path.join(self.tmp, "key")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_profile(self, name, **kw):
        return deidentify.run(self.settings, name, output_override=self.out, key_override=self.key, **kw)

    def key_map(self):
        return {r["original_id"]: r["code"] for r in read_csv(os.path.join(self.key, "athlete_key.csv"))}

    # ---- planted problems in the GPS file
    def test_gps_plants_are_caught_and_input_untouched(self):
        src = self.settings["profiles"]["gps"]["input_file"]
        before = file_hash(src)
        r = self.run_profile("gps")
        self.assertEqual(before, file_hash(src), "the input file must never change")
        self.assertIn(tuple(EXPECTED["name_variant_pair"]), r["name_variants"], "name variant pair not reported")
        key = self.key_map()
        conflict_code = key[EXPECTED["conflicting_heights"]["player"]]
        self.assertIn(conflict_code, r["conflicts"], "conflicting heights not reported")
        self.assertTrue(any("184" in x or str(EXPECTED["conflicting_heights"]["heights_cm"][0]) in x for x in r["conflicts"][conflict_code]))
        gk = key[EXPECTED["unique_goalkeeper"]]
        self.assertTrue(any(gk in codes and len(codes) == 1 for codes in r["checks"]["athlete_level_small_groups"].values()),
                        "the goalkeeper should be reported as a group of one")
        out = read_csv(r["output_file"])
        self.assertNotIn("Jersey Number", out[0], "a column not on the keep-list must be dropped")
        self.assertNotIn("Device ID", out[0])
        self.assertIn("Week", out[0])
        self.assertIn("Athlete Code", out[0])
        self.assertTrue(all(o["Week"].isdigit() for o in out), "every date must become a week number")
        self.assertTrue(all("kg" in o["Body Mass (kg)"] for o in out), "body mass must be banded")

    def test_no_original_id_survives(self):
        r = self.run_profile("gps")
        names = {n.casefold() for n in self.key_map()}
        with open(r["output_file"], encoding="utf-8") as f:
            text = f.read().casefold()
        for n in names:
            self.assertNotIn(n, text, f"original ID survived in the output: {n}")
        self.assertTrue(any("OK: the output was re-read" in line for line in r["report"]))

    def test_verification_deletes_a_leaking_output(self):
        # keep a column that repeats the name: the re-read must catch it and delete the file
        src = self.settings["profiles"]["gps"]["input_file"]
        leaky = os.path.join(self.tmp, "leaky.csv")
        rows = read_csv(src)
        with open(leaky, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) + ["Coach Note"])
            w.writeheader()
            for row in rows:
                w.writerow(row | {"Coach Note": f"Talked to {row['Player Name']}"})
        self.settings["profiles"]["gps"]["keep_columns"].append("Coach Note")
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_profile("gps", input_override=leaky)
        self.assertIn("VERIFICATION FAILED", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.out, "coded_leaky.csv")))

    def test_ambiguous_date_stops_when_format_blank(self):
        self.settings["profiles"]["gps"]["date_format"] = ""
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_profile("gps")
        self.assertIn("two ways", str(cm.exception))

    def test_wrong_date_format_stops(self):
        self.settings["profiles"]["gps"]["date_format"] = "%Y-%m-%d"
        with self.assertRaises(deidentify.StopRun):
            self.run_profile("gps")

    def test_alias_merges_variant(self):
        a, b = EXPECTED["name_variant_pair"]
        self.settings["id_aliases"] = {a: b}
        r = self.run_profile("gps")
        self.assertEqual(r["name_variants"], [])
        self.assertNotIn(a, self.key_map())
        self.assertEqual(len(self.key_map()), 28)

    # ---- wellness: row level and the notes column
    def test_wellness_row_level_and_notes(self):
        r = self.run_profile("wellness")
        rows = r["checks"]["row_level_small_groups"]
        self.assertTrue(any(x["Week"] == EXPECTED["goalkeeper_injury_week"] and x["Position"] == "Goalkeeper"
                            and x["athletes"] == 1 for x in rows), "the goalkeeper's week-6 injury must be a row-level warning")
        out = read_csv(r["output_file"])
        self.assertNotIn("Notes", out[0], "Notes is not on the keep-list and must be dropped")
        # now keep Notes: the coach's name in it must raise the name-shaped warning
        self.settings["profiles"]["wellness"]["keep_columns"].append("Notes")
        r2 = self.run_profile("wellness")
        self.assertIn("Notes", r2["name_shaped"])

    # ---- key reuse and safety
    def test_key_is_reused_across_exports(self):
        self.run_profile("gps")
        k1 = self.key_map()
        self.run_profile("force_plate")
        self.run_profile("wellness")
        k2 = self.key_map()
        for name, code in k1.items():
            self.assertEqual(k2[name], code, "an athlete must keep one code across exports")
        self.assertTrue(all(c.startswith("ATH-") and len(c) == 10 for c in k2.values()))

    def test_refuses_output_in_input_folder(self):
        src = self.settings["profiles"]["gps"]["input_file"]
        with self.assertRaises(deidentify.StopRun):
            deidentify.run(self.settings, "gps", output_override=os.path.dirname(src), key_override=self.key)

    def test_refuses_key_inside_output(self):
        with self.assertRaises(deidentify.StopRun):
            deidentify.run(self.settings, "gps", output_override=self.out, key_override=os.path.join(self.out, "k"))

    def test_report_never_claims_anonymity(self):
        r = self.run_profile("gps")
        text = "\n".join(r["report"]).casefold()
        self.assertIn("coded data", text)
        self.assertIn("not anonymous", text)
        self.assertIn("version", text)


if __name__ == "__main__":
    unittest.main()
