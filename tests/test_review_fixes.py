"""One test or more for each fix from the independent code review of version 0.3.0. Numbers follow the review's list."""
import contextlib
import csv
import io
import json
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


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def link_or_skip(test, target, link):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        test.skipTest("this computer does not allow symbolic links without special permission")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="review_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.in_dir = os.path.join(self.tmp, "in")
        os.makedirs(self.in_dir)
        self.out = os.path.join(self.tmp, "out")
        self.key = os.path.join(self.tmp, "key")


class DeidBase(Base):
    HEADER = ["Name", "Date", "Load"]

    def profile(self, **kw):
        return {"input_file": os.path.join(self.in_dir, "export.csv"), "athlete_id_column": "Name",
                "keep_columns": ["Name", "Date", "Load"], "date_columns": ["Date"], "date_format": "%m/%d/%Y"} | kw

    def settings(self, **kw):
        s = json.loads(json.dumps(deidentify.SETTINGS))
        s["profiles"] = {"t": self.profile(**kw)}
        return s

    def export(self, header=None, rows=None):
        rows = rows if rows is not None else [["Ann Lee", "08/05/2024", "10"], ["Ben Fox", "08/07/2024", "20"]]
        return write_csv(os.path.join(self.in_dir, "export.csv"), header or self.HEADER, rows)

    def run_it(self, settings=None, **kw):
        return deidentify.run(settings or self.settings(), "t", output_override=self.out, key_override=self.key, **kw)


class Fix01DuplicateHeadings(DeidBase):
    def test_two_columns_converting_to_one_heading_stop(self):
        self.export(["Name", "Date", "Reach (cm)", "Reach (in)"], [["Ann Lee", "08/05/2024", "100", "40"]])
        s = self.settings(keep_columns=["Name", "Date", "Reach (cm)", "Reach (in)"])
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(s)
        self.assertIn("Two output columns", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(self.out, "coded_export.csv")))

    def test_a_kept_column_named_week_or_session_or_athlete_code_stops(self):
        for name in ("Week", "Session", "Athlete Code", "week"):
            self.export(["Name", "Date", name], [["Ann Lee", "08/05/2024", "3"]])
            with self.assertRaises(deidentify.StopRun, msg=name):
                self.run_it(self.settings(keep_columns=["Name", "Date", name]))

    def test_two_date_columns_stop(self):
        self.export(["Name", "Date", "Date 2"], [["Ann Lee", "08/05/2024", "08/06/2024"]])
        with self.assertRaises(deidentify.StopRun):
            self.run_it(self.settings(keep_columns=["Name", "Date", "Date 2"], date_columns=["Date", "Date 2"]))

    def test_verification_reads_every_physical_cell(self):
        # the second column under a repeated heading is invisible to a dict reader; here it holds the name
        path = write_csv(os.path.join(self.tmp, "f.csv"), ["Athlete Code", "Note", "Note"], [["ATH-AAAAAA", "fine", "Ann Lee"]])
        problems, _ = deidentify.verify_output(path, ["code", "text", "text"], {"Ann Lee"}, {"ATH-AAAAAA": "Ann Lee"})
        self.assertTrue(any("original ID" in p for p in problems))
        self.assertTrue(any("headings" in p for p in problems))

    def test_verification_checks_headings_separately(self):
        path = write_csv(os.path.join(self.tmp, "f.csv"), ["Athlete Code", "Ann Lee load"], [["ATH-AAAAAA", "5"]])
        problems, _ = deidentify.verify_output(path, ["code", "number"], {"Ann Lee"}, {"ATH-AAAAAA": "Ann Lee"})
        self.assertTrue(any("heading contained" in p for p in problems))


class Fix02SymlinksAndIdentity(DeidBase):
    def test_output_symlink_to_the_input_is_refused_and_input_unchanged(self):
        src = self.export()
        before = read_text(src)
        os.makedirs(self.out)
        link_or_skip(self, src, os.path.join(self.out, "coded_export.csv"))
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(overwrite=True)
        self.assertIn("symbolic link", str(cm.exception))
        self.assertEqual(before, read_text(src))

    def test_dangling_output_symlink_is_refused(self):
        self.export()
        os.makedirs(self.out)
        link_or_skip(self, os.path.join(self.tmp, "nowhere.csv"), os.path.join(self.out, "coded_export.csv"))
        with self.assertRaises(deidentify.StopRun):
            self.run_it()

    def test_output_folder_symlinked_to_the_input_folder_is_refused(self):
        self.export()
        link_or_skip(self, self.in_dir, self.out)
        with self.assertRaises(deidentify.StopRun):
            self.run_it()

    def test_hard_link_to_the_input_is_refused(self):
        src = self.export()
        os.makedirs(self.out)
        try:
            os.link(src, os.path.join(self.out, "coded_export.csv"))
        except (OSError, NotImplementedError):
            self.skipTest("this file system does not allow hard links")
        with self.assertRaises(deidentify.StopRun):
            self.run_it(overwrite=True)

    def test_key_symlink_is_refused(self):
        src = self.export()
        os.makedirs(self.key)
        link_or_skip(self, src, os.path.join(self.key, "athlete_key.csv"))
        with self.assertRaises(deidentify.StopRun):
            self.run_it()

    def test_key_folder_cannot_contain_the_output_folder(self):
        self.export()
        with self.assertRaises(deidentify.StopRun):
            deidentify.run(self.settings(), "t", output_override=os.path.join(self.key, "o"), key_override=self.key)

    def test_no_temporary_files_are_left(self):
        self.export()
        self.run_it()
        for folder in (self.out, self.key):
            self.assertFalse([f for f in os.listdir(folder) if f.startswith(".tmp_")])

    def test_cmj_output_symlink_is_refused(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), *CMJ_FILE)
        os.makedirs(self.out)
        link_or_skip(self, src, os.path.join(self.out, "cmj_results_c.csv"))
        with self.assertRaises(cmj_flags.StopRun):
            cmj_flags.run(cmj_settings(src, self.out), overwrite=True)


class Fix03ExistingOutputs(DeidBase):
    def test_second_run_stops_and_changes_nothing(self):
        self.export()
        r = self.run_it()
        before = read_text(r["output_file"])
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it()
        self.assertIn("--overwrite", str(cm.exception))
        self.assertEqual(before, read_text(r["output_file"]))

    def test_overwrite_replaces(self):
        self.export()
        self.run_it()
        self.assertTrue(os.path.exists(self.run_it(overwrite=True)["output_file"]))

    def test_failed_verification_keeps_the_existing_file(self):
        self.export()
        r = self.run_it()
        before = read_text(r["output_file"])
        self.export(self.HEADER + ["Note"], [["Ann Lee", "08/05/2024", "10", "Saw Ann Lee"]])
        s = self.settings(keep_columns=self.HEADER + ["Note"], allowed_text_columns=["Note"])
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(s, overwrite=True)
        self.assertIn("VERIFICATION FAILED", str(cm.exception))
        self.assertEqual(before, read_text(r["output_file"]), "the file from the earlier run must survive")
        self.assertFalse([f for f in os.listdir(self.out) if f.startswith(".tmp_")])

    def test_cmj_second_run_stops_explain_does_not_write(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), *CMJ_FILE)
        s = cmj_settings(src, self.out)
        cmj_flags.run(s)
        with self.assertRaises(cmj_flags.StopRun):
            cmj_flags.run(s)
        cmj_flags.run(s, overwrite=True)
        before = os.path.getmtime(os.path.join(self.out, "cmj_results_c.csv"))
        out = cmj_flags.run(s, explain_code="ATH-A", write=False)
        self.assertTrue(out["explain"])
        self.assertEqual(before, os.path.getmtime(os.path.join(self.out, "cmj_results_c.csv")))


class Fix04Reports(DeidBase):
    def setUp(self):
        super().setUp()
        self.export(["Name", "Date", "Load", "Position", "Height (cm)"],
                    [["Jamal Okafor", "08/05/2024", "10", "XX", "180"], ["J. Okafor", "08/05/2024", "11", "XX", "181"],
                     ["Ann Lee", "08/05/2024", "12", "XX", "170"], ["Ann Lee", "08/12/2024", "12", "XX", "190"]])
        self.r = self.run_it(self.settings(keep_columns=["Name", "Date", "Load", "Position", "Height (cm)"],
                                           position_column="Position", height_column="Height (cm)"))

    def test_shareable_report_has_no_names_or_identifying_values(self):
        text = read_text(self.r["report_file"])
        for secret in ("Okafor", "Ann Lee", "'XX'", "190.0", self.key):
            self.assertNotIn(secret, text)

    def test_private_report_sits_with_the_key_and_is_labelled(self):
        path = self.r["private_report_file"]
        self.assertEqual(os.path.dirname(path), self.key)
        text = read_text(path)
        self.assertTrue(text.startswith("PRIVATE"))
        self.assertIn("J. Okafor", text)
        self.assertIn("Ann Lee", text)
        self.assertIn("'XX'", text)
        self.assertIn("190.0", text)

    def test_a_heading_holding_a_name_is_hidden_from_the_report(self):
        self.export(self.HEADER + ["Ann Lee old"], [["Ann Lee", "08/05/2024", "10", "x"]])
        r = self.run_it(overwrite=True)
        self.assertNotIn("Ann Lee", read_text(r["report_file"]))


class Fix05Sessions(DeidBase):
    def test_two_dates_in_a_week_become_sessions(self):
        self.export(rows=[["Ann Lee", "08/05/2024", "10"], ["Ann Lee", "08/07/2024", "11"], ["Ben Fox", "08/07/2024", "12"], ["Ann Lee", "08/12/2024", "13"]])
        rows = read_rows(self.run_it()["output_file"])
        self.assertEqual([(r["Week"], r["Session"]) for r in rows], [("1", "1"), ("1", "2"), ("1", "2"), ("2", "1")])
        self.assertNotIn("Date", rows[0])

    def test_cmj_reads_two_sessions_as_two_days_and_a_true_repeat_as_a_duplicate(self):
        rows = [["A", 1, 1, t, 30] for t in (1, 2, 3)] + [["A", 1, 2, t, 31] for t in (1, 2, 3)] + [["B", 1, 1, 1, 30], ["B", 1, 1, 1, 31]]
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)"], rows)
        out = cmj_flags.run(cmj_settings(src, self.out) | {"test_type_column": ""})
        self.assertEqual(sorted(out["athletes"]["A"]["days"]), [(1, 1), (1, 2)])
        self.assertTrue(any(a == "B" and "duplicated" in m for a, _, m in out["exclusions"]))

    def test_session_label_appears_in_the_results(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), *CMJ_FILE)
        out = cmj_flags.run(cmj_settings(src, self.out))
        self.assertIn("week 1 session 1", read_text(out["results_file"]))


class Fix06FreeText(DeidBase):
    def test_text_in_a_number_column_is_blanked_and_counted(self):
        self.export(rows=[["Ann Lee", "08/05/2024", "called Dr Who"], ["Ben Fox", "08/05/2024", "20"]])
        r = self.run_it()
        self.assertEqual([x["Load"] for x in read_rows(r["output_file"])], ["", "20"])
        self.assertEqual(r["blanked"], {"Load": 1})
        self.assertNotIn("called Dr Who", read_text(r["output_file"]) + read_text(r["report_file"]))

    def test_text_that_fails_unit_conversion_is_blanked(self):
        self.export(["Name", "Date", "Load [lb]"], [["Ann Lee", "08/05/2024", "see Dr Who"], ["Ben Fox", "08/05/2024", "100"]])
        r = self.run_it(self.settings(keep_columns=["Name", "Date", "Load [lb]"]))
        self.assertEqual([x["Load [kg]"] for x in read_rows(r["output_file"])], ["", "45.36"])

    def test_a_text_column_is_dropped_unless_allowed(self):
        self.export(rows=[["Ann Lee", "08/05/2024", "felt fine"], ["Ben Fox", "08/05/2024", "tired"]])
        r = self.run_it()
        self.assertNotIn("Load", r["output_headers"])
        self.assertEqual(r["dropped_text"], ["Load"])
        r2 = self.run_it(self.settings(allowed_text_columns=["Load"]), overwrite=True)
        self.assertIn("Load", r2["output_headers"])
        self.assertTrue(any("allowed_text_columns" in line and "DO NOT SHARE" in line for line in r2["report"]))

    def test_categories_pass_and_long_ones_are_blanked(self):
        long_note = "x" * 41
        self.export(rows=[["Ann Lee", "08/05/2024", "Match"], ["Ben Fox", "08/05/2024", long_note]])
        r = self.run_it(self.settings(column_types={"Load": "category"}))
        self.assertEqual([x["Load"] for x in read_rows(r["output_file"])], ["Match", ""])

    def test_nan_and_infinity_are_not_numbers(self):
        self.export(rows=[["Ann Lee", "08/05/2024", "nan"], ["Ben Fox", "08/05/2024", "inf"], ["Cal Dee", "08/05/2024", "5"]])
        r = self.run_it()
        self.assertEqual([x["Load"] for x in read_rows(r["output_file"])], ["", "", "5"])

    def test_unknown_type_and_second_id_column_stop(self):
        self.export()
        with self.assertRaises(deidentify.StopRun):
            self.run_it(self.settings(column_types={"Load": "text"}))
        with self.assertRaises(deidentify.StopRun):
            self.run_it(self.settings(column_types={"Load": "id"}))

    def test_readme_says_name_detection_is_not_comprehensive(self):
        self.assertIn("not comprehensive", read_text(os.path.join(ROOT, "README.md")))


class Fix07ShortIds(DeidBase):
    def test_short_id_inside_text_is_found(self):
        self.export(self.HEADER + ["Note"], [["Bo", "08/05/2024", "10", "saw Bo, then left"]])
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(self.settings(keep_columns=self.HEADER + ["Note"], allowed_text_columns=["Note"]))
        self.assertIn("VERIFICATION FAILED", str(cm.exception))

    def test_short_id_inside_a_longer_word_is_not_a_match(self):
        self.export(self.HEADER + ["Note"], [["Bo", "08/05/2024", "10", "both good"]])
        self.assertTrue(self.run_it(self.settings(keep_columns=self.HEADER + ["Note"], allowed_text_columns=["Note"])))

    def test_numeric_id_is_not_confused_with_ordinary_numbers(self):
        self.export(rows=[["7", "08/05/2024", "7"], ["8", "09/23/2024", "7"]])
        self.assertTrue(self.run_it())

    def test_numeric_id_found_in_text_and_in_a_copied_column(self):
        self.export(self.HEADER + ["Note"], [["7", "08/05/2024", "10", "athlete 7 sore"]])
        with self.assertRaises(deidentify.StopRun):
            self.run_it(self.settings(keep_columns=self.HEADER + ["Note"], allowed_text_columns=["Note"]))
        self.export(rows=[["7", "08/05/2024", "7"], ["8", "08/05/2024", "8"]])
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it()
        self.assertIn("repeats the athlete ID", str(cm.exception))

    def test_input_file_name_holding_an_id_stops(self):
        src = write_csv(os.path.join(self.in_dir, "bo_jumps.csv"), self.HEADER, [["Bo", "08/05/2024", "10"]])
        with self.assertRaises(deidentify.StopRun):
            self.run_it(input_override=src)


class Fix08Uniqueness(DeidBase):
    def test_an_athletes_rare_second_value_is_counted(self):
        names = [f"P{i}" for i in range(6)]
        rows = [[n, "08/05/2024", "1", "CM", "70"] for n in names] + [["P0", "08/12/2024", "1", "CM", "70"], ["P0", "08/19/2024", "1", "CM", "95"]]
        self.export(["Name", "Date", "Load", "Position", "Body Mass (kg)"], rows)
        r = self.run_it(self.settings(keep_columns=["Name", "Date", "Load", "Position", "Body Mass (kg)"],
                                      position_column="Position", body_mass_column="Body Mass (kg)"))
        small = r["checks"]["athlete_level_small_groups"]
        self.assertEqual(list(small), ["Midfielder | 95-100 kg"], "the rare value is released, so it must be checked even though it is not P0's usual one")

    def test_counts_are_athletes_not_rows(self):
        rows = [["P0", f"08/{d:02d}/2024", "1", "CM"] for d in range(5, 26)]
        self.export(["Name", "Date", "Load", "Position"], rows)
        r = self.run_it(self.settings(keep_columns=["Name", "Date", "Load", "Position"], position_column="Position"))
        self.assertEqual(len(next(iter(r["checks"]["athlete_level_small_groups"].values()))), 1)


class Fix09CmjHeadings(Base):
    def test_headings_equal_after_normalising_stop(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)", "Jump Height [in]", "Test Type"],
                        [["A", 1, 1, 1, 30, 12, "CMJ"]])
        with self.assertRaises(cmj_flags.StopRun) as cm:
            cmj_flags.run(cmj_settings(src, self.out))
        self.assertIn("same once units", str(cm.exception))

    def test_missing_filter_column_stops_unless_turned_off(self):
        header = ["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)"]
        src = write_csv(os.path.join(self.in_dir, "c.csv"), header, [["A", 1, 1, 1, 30]])
        with self.assertRaises(cmj_flags.StopRun) as cm:
            cmj_flags.run(cmj_settings(src, self.out))
        self.assertIn("test type", str(cm.exception))
        self.assertTrue(cmj_flags.run(cmj_settings(src, self.out) | {"test_type_column": ""}))
        self.assertTrue(cmj_flags.run(cmj_settings(src, self.out) | {"test_type_value": ""}, overwrite=True))

    def test_filter_is_applied(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)", "Test Type"],
                        [["A", 1, 1, 1, 30, "CMJ"], ["A", 1, 1, 2, 60, "SJ"]])
        self.assertEqual(cmj_flags.run(cmj_settings(src, self.out))["counts"]["trials"], 1)

    def test_missing_configured_column_stops(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Trial", "Jump Height (cm)", "Test Type"], [["A", 1, 1, 30, "CMJ"]])
        with self.assertRaises(cmj_flags.StopRun):
            cmj_flags.run(cmj_settings(src, self.out))


class Fix10HeightInMetres(DeidBase):
    def test_metres_convert_for_the_height_column_only(self):
        self.export(["Name", "Date", "Height (m)", "Total Distance (m)"], [["Ann Lee", "08/05/2024", "1.82", "5000"]])
        r = self.run_it(self.settings(keep_columns=["Name", "Date", "Height (m)", "Total Distance (m)"], height_column="Height (m)"))
        row = read_rows(r["output_file"])[0]
        self.assertEqual(row["Height (cm)"], "180-185 cm")
        self.assertEqual(row["Total Distance (m)"], "5000", "a distance in metres is not a height")

    def test_inches_still_convert(self):
        self.export(["Name", "Date", "Height (in)"], [["Ann Lee", "08/05/2024", "70"]])
        r = self.run_it(self.settings(keep_columns=["Name", "Date", "Height (in)"], height_column="Height (in)"))
        self.assertEqual(read_rows(r["output_file"])[0]["Height (cm)"], "175-180 cm")

    def test_other_height_units_stop(self):
        for col in ("Height (ft)", "Height (mm)", "Height", "Height [kg]"):
            self.export(["Name", "Date", col], [["Ann Lee", "08/05/2024", "6"]])
            with self.assertRaises(deidentify.StopRun, msg=col):
                self.run_it(self.settings(keep_columns=["Name", "Date", col], height_column=col))


class Fix11KeyFile(DeidBase):
    def key_path(self):
        return os.path.join(self.key, "athlete_key.csv")

    def bad_key(self, header, rows):
        os.makedirs(self.key, exist_ok=True)
        write_csv(self.key_path(), header, rows)
        self.export()
        before = read_text(self.key_path())
        with self.assertRaises(deidentify.StopRun):
            self.run_it()
        self.assertEqual(before, read_text(self.key_path()), "a rejected key must not be changed")

    def test_missing_column(self):
        self.bad_key(["name", "code"], [["Ann Lee", "ATH-AAAAAA"]])

    def test_blank_code(self):
        self.bad_key(["original_id", "code"], [["Ann Lee", " "]])

    def test_blank_athlete(self):
        self.bad_key(["original_id", "code"], [["", "ATH-AAAAAA"]])

    def test_two_codes_for_one_athlete(self):
        self.bad_key(["original_id", "code"], [["Ann Lee", "ATH-AAAAAA"], ["Ann Lee", "ATH-BBBBBB"]])

    def test_one_code_for_two_athletes(self):
        self.bad_key(["original_id", "code"], [["Ann Lee", "ATH-AAAAAA"], ["Ben Fox", "ATH-AAAAAA"]])

    def test_backup_holds_the_previous_key_and_first_coded_survives(self):
        os.makedirs(self.key)
        write_csv(self.key_path(), ["original_id", "code", "first_coded"], [["Ann Lee", "ATH-AAAAAA", "2020-01-01"]])
        previous = read_text(self.key_path())
        self.export()
        self.run_it()
        self.assertEqual(previous, read_text(os.path.join(self.key, "athlete_key_backup.csv")))
        rows = {r["original_id"]: r for r in read_rows(self.key_path())}
        self.assertEqual(rows["Ann Lee"]["code"], "ATH-AAAAAA")
        self.assertEqual(rows["Ann Lee"]["first_coded"], "2020-01-01")
        self.assertIn("Ben Fox", rows)

    def test_key_is_unchanged_when_verification_fails(self):
        os.makedirs(self.key)
        write_csv(self.key_path(), ["original_id", "code", "first_coded"], [["Ann Lee", "ATH-AAAAAA", "2020-01-01"]])
        previous = read_text(self.key_path())
        self.export(self.HEADER + ["Note"], [["Ben Fox", "08/05/2024", "10", "Saw Ben Fox"]])
        with self.assertRaises(deidentify.StopRun):
            self.run_it(self.settings(keep_columns=self.HEADER + ["Note"], allowed_text_columns=["Note"]))
        self.assertEqual(previous, read_text(self.key_path()))


class Fix12DuplicateOrder(Base):
    def test_per_trial_duplicate_with_an_unreadable_value_excludes_the_day(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)", "Test Type"],
                        [["A", 1, 1, 1, 30, "CMJ"], ["A", 1, 1, 2, 31, "CMJ"], ["A", 1, 1, 1, "", "CMJ"], ["B", 1, 1, 1, 30, "CMJ"]])
        out = cmj_flags.run(cmj_settings(src, self.out))
        self.assertTrue(any(a == "A" and "duplicated" in m for a, _, m in out["exclusions"]))
        self.assertNotIn("A", out["athletes"])

    def test_per_test_duplicate_with_an_unreadable_value_excludes_the_day(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Session", "Reps", "Jump Height (cm)", "Test Type"],
                        [["A", 1, 1, 3, 30, "CMJ"], ["A", 1, 1, 3, "n/a", "CMJ"], ["B", 1, 1, 3, 30, "CMJ"]])
        out = cmj_flags.run(cmj_settings(src, self.out) | {"trial_column": "", "reps_column": "Reps"})
        self.assertTrue(any(a == "A" and "duplicated" in m for a, _, m in out["exclusions"]))
        self.assertNotIn("A", out["athletes"])

    def test_trial_1_and_1_point_0_are_the_same_trial(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)", "Test Type"],
                        [["A", 1, 1, "1", 30, "CMJ"], ["A", 1, 1, "1.0", 31, "CMJ"], ["B", 1, 1, 1, 30, "CMJ"]])
        self.assertNotIn("A", cmj_flags.run(cmj_settings(src, self.out))["athletes"])

    def test_an_unreadable_value_alone_only_loses_that_trial(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)", "Test Type"],
                        [["A", 1, 1, 1, 30, "CMJ"], ["A", 1, 1, 2, "inf", "CMJ"]])
        out = cmj_flags.run(cmj_settings(src, self.out))
        self.assertEqual(out["athletes"]["A"]["trials"][(1, 1)], [30.0])
        self.assertTrue(any("unreadable jump height" in m for _, _, m in out["exclusions"]))


class Fix13InputValidation(DeidBase):
    def stops(self, rows, **settings):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)", "Test Type"], rows)
        with self.assertRaises(cmj_flags.StopRun) as cm:
            cmj_flags.run(cmj_settings(src, self.out) | settings)
        return str(cm.exception)

    def test_mixed_weeks_and_dates_stop(self):
        self.assertIn("one kind", self.stops([["A", 1, 1, 1, 30, "CMJ"], ["A", "2024-08-05", 1, 1, 30, "CMJ"]]))
        self.assertIn("one kind", self.stops([["A", "08/05/2024", 1, 1, 30, "CMJ"], ["A", 2, 1, 1, 30, "CMJ"]], day_format="%m/%d/%Y"))

    def test_bad_week_values_stop(self):
        for week in ("1.9", "inf", "nan", "-inf"):
            self.assertIn("whole week", self.stops([["A", week, 1, 1, 30, "CMJ"]]), week)

    def test_bad_session_values_stop(self):
        for session in ("1.5", "inf", "0", "-1", "two"):
            self.assertIn("session number", self.stops([["A", 1, session, 1, 30, "CMJ"]]), session)

    def test_nan_body_mass_and_height_do_not_crash(self):
        self.export(["Name", "Date", "Body Mass (kg)", "Height (cm)"], [["Ann Lee", "08/05/2024", "nan", "inf"], ["Ben Fox", "08/05/2024", "70", "180"]])
        r = self.run_it(self.settings(keep_columns=["Name", "Date", "Body Mass (kg)", "Height (cm)"], body_mass_column="Body Mass (kg)", height_column="Height (cm)"))
        self.assertEqual(read_rows(r["output_file"])[0]["Body Mass (kg)"], "")
        self.assertEqual(r["blanked"], {"Body Mass (kg)": 1, "Height (cm)": 1})

    def test_a_file_not_saved_as_utf8_stops_clearly(self):
        src = os.path.join(self.in_dir, "export.csv")
        with open(src, "wb") as f:
            f.write("Name,Date,Load\nJos\u00e9 Ruiz,08/05/2024,1\n".encode("latin-1"))
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it()
        self.assertIn("UTF-8", str(cm.exception))
        with self.assertRaises(cmj_flags.StopRun) as cm:
            cmj_flags.run(cmj_settings(src, self.out))
        self.assertIn("UTF-8", str(cm.exception))

    def test_a_bad_season_start_stops_clearly(self):
        self.export()
        s = self.settings()
        s["season_start_date"] = "08/05/2024"
        with self.assertRaises(deidentify.StopRun):
            self.run_it(s)

    def test_command_line_prints_a_message_not_a_crash(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)", "Test Type"], [["A", "1.9", 1, 1, 30, "CMJ"]])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cmj_flags.main(["--input", src, "--output-folder", self.out])
        self.assertEqual(code, 1)
        self.assertIn("STOPPED", buf.getvalue())


class Fix14ExplainWithoutThresholds(Base):
    def test_explain_says_thresholds_are_unavailable(self):
        rows = [["A", w, 1, 1, 30 + w, "CMJ"] for w in range(1, 7)]    # one athlete: no between-athlete SD, so no SWC
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)", "Test Type"], rows)
        out = cmj_flags.run(cmj_settings(src, self.out), explain_code="A")
        self.assertIn("Thresholds unavailable", "\n".join(out["explain"]))
        self.assertTrue(any(r["status"] == "thresholds unavailable" for r in out["results"]))


class Fix15DateFormat(DeidBase):
    def test_blank_date_format_always_stops(self):
        self.export(rows=[["Ann Lee", "2024-08-05", "1"]])      # this date can only be read one way, and it still stops
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(self.settings(date_format=""))
        self.assertIn("date_format is blank", str(cm.exception))

    def test_cmj_dates_need_a_format(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), ["Athlete Code", "Date", "Trial", "Jump Height (cm)", "Test Type"], [["A", "2024-08-05", 1, 30, "CMJ"]])
        with self.assertRaises(cmj_flags.StopRun):
            cmj_flags.run(cmj_settings(src, self.out) | {"day_column": "Date", "session_column": ""})


class Fix16BaselineTrend(Base):
    SETTINGS = {"baseline_days": 4, "k": 1.5, "expected_trials_per_day": 1, "swc_multiplier": 0.2, "individual_te": False}

    def test_steady_trend_warns_and_gives_te_zero(self):
        trials = {"A": {i + 1: [31.0 + i] for i in range(4)}, "B": {i + 1: [41.0 + i] for i in range(4)}}
        _, squad, warnings, _ = cmj_flags.analyse(trials, self.SETTINGS)
        self.assertEqual(squad["te"], 0)
        self.assertEqual({a for a, _, m in warnings if "same direction" in m}, {"A", "B"})

    def test_falling_trend_warns_and_a_mixed_baseline_does_not(self):
        trials = {"A": {1: [34.0], 2: [33.0], 3: [32.0], 4: [31.0]}, "B": {1: [40.0], 2: [41.0], 3: [40.0], 4: [41.0]}}
        _, _, warnings, _ = cmj_flags.analyse(trials, self.SETTINGS)
        self.assertEqual({a for a, _, m in warnings if "same direction" in m}, {"A"})

    def test_report_and_readme_explain_it(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), *CMJ_FILE)
        report = "\n".join(cmj_flags.run(cmj_settings(src, self.out))["report"])
        self.assertIn("misleadingly small", report)
        self.assertIn("misleadingly small", read_text(os.path.join(ROOT, "README.md")))


class Fix17ReadmeAndLabels(DeidBase):
    def test_readme_has_every_requested_section(self):
        text = read_text(os.path.join(ROOT, "README.md"))
        for phrase in ("strength-coach-data-tools-main", "coach-edited mapping", r"C:\\Users", "cloud", "athlete_key.csv", "PRIVATE",
                       "two sessions", "Season 2", "FIX BEFORE USING RESULTS", "DO NOT SHARE", "INFORMATION ONLY", "--overwrite"):
            self.assertIn(phrase, text, phrase)

    def test_every_warning_in_every_report_has_a_label(self):
        settings = json.loads(json.dumps(deidentify.SETTINGS))
        labels = ("[FIX BEFORE USING RESULTS]", "[DO NOT SHARE]", "[INFORMATION ONLY]")
        for name, profile in settings["profiles"].items():
            profile["input_file"] = os.path.join(ROOT, profile["input_file"])
            r = deidentify.run(settings, name, output_override=self.out, key_override=self.key)
            lines = [line for line in r["report"] if "WARNING" in line]
            self.assertTrue(all(any(x in line for x in labels) for line in lines), lines)

    def test_every_cmj_warning_has_a_label(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), *CMJ_FILE)
        out = cmj_flags.run(cmj_settings(src, self.out))
        self.assertTrue(all("[" in m for _, _, m in out["warnings"]))


class Version(unittest.TestCase):
    def test_version_is_0_4_0(self):
        self.assertEqual(deidentify.SCRIPT_VERSION, "0.4.0")
        self.assertEqual(cmj_flags.SCRIPT_VERSION, "0.4.0")


CMJ_FILE = (["Athlete Code", "Week", "Session", "Trial", "Jump Height (cm)", "Test Type"],
            [[a, w, 1, t, round(base + w % 2 + t / 10, 1), "CMJ"] for a, base in (("ATH-A", 30), ("ATH-B", 40)) for w in range(1, 7) for t in (1, 2, 3)])


def cmj_settings(path, out):
    return dict(cmj_flags.SETTINGS) | {"input_file": path, "output_folder": out}


if __name__ == "__main__":
    unittest.main()
