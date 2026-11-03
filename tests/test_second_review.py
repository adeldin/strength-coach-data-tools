"""One test or more for each fix from the second independent review, of version 0.4.0. Numbers follow the review's list."""
import contextlib
import csv
import io
import json
import os
import re
import sys
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmj_flags  # noqa: E402
import deidentify  # noqa: E402
from test_review_fixes import CMJ_FILE, Base, DeidBase, cmj_settings, link_or_skip, read_rows, read_text, write_csv  # noqa: E402

README = os.path.join(ROOT, "README.md")
OUTPUT, REPORT, PRIVATE = "coded_export.csv", "deidentify_report_export.txt", "PRIVATE_deidentify_report_export.txt"


def hard_link_or_skip(test, target, link):
    try:
        os.link(target, link)
    except (OSError, NotImplementedError):
        test.skipTest("this computer does not allow hard links here")


# Antivirus or cloud sync on the computer running these tests can really lock a file at any moment. Those real locks
# must not count as part of a lock a test simulates, so real steps wait them out here, and only simulated locks skip the wait.
REAL_SLEEP, REAL_REPLACE = time.sleep, os.replace


def patient(action, *args):
    """Do a real file step in a test, waiting out any real lock."""
    for _ in range(100):
        try:
            return action(*args)
        except PermissionError:
            REAL_SLEEP(0.1)
    return action(*args)


class LockClock:
    """Stands in for time.sleep. The wait after a simulated lock is recorded and skipped. Any other wait really happens."""

    def __init__(self):
        self.waits = []
        self.simulated_lock = False
        self.skip_every_wait = False

    def __call__(self, seconds):
        if self.simulated_lock:
            self.simulated_lock = False
            self.waits.append(seconds)
        elif not self.skip_every_wait:
            REAL_SLEEP(seconds)


def fail_replace_on(clock, *names):
    """A stand-in for os.replace that fails when the destination's name is listed, as a locked file would."""

    def replace(src, dst):
        if os.path.basename(dst) in names:
            clock.simulated_lock = True
            raise PermissionError(f"{os.path.basename(dst)} is locked")
        patient(REAL_REPLACE, src, dst)
    return replace


class ChangeBase(DeidBase):
    def setUp(self):
        super().setUp()
        self.clock = LockClock()
        patcher = mock.patch("time.sleep", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def key_path(self):
        return os.path.join(self.key, "athlete_key.csv")

    def backup_path(self):
        return os.path.join(self.key, "athlete_key_backup.csv")

    def out_path(self, name=OUTPUT):
        return os.path.join(self.out, name)

    def first_run(self):
        """A finished earlier run: outputs and a key holding Ann Lee and Ben Fox."""
        self.export()
        self.run_it()
        return read_text(self.out_path()), read_text(self.key_path())

    def add_athlete(self):
        return self.export(rows=[["Ann Lee", "08/05/2024", "10"], ["Ben Fox", "08/07/2024", "20"], ["Cal Roy", "08/07/2024", "30"]])


class Fix01KeyBackup(ChangeBase):
    def test_input_named_like_the_backup_in_the_key_folder_is_not_replaced(self):
        self.first_run()
        src = write_csv(self.backup_path(), self.HEADER, [["Ann Lee", "08/05/2024", "10"], ["Cal Roy", "08/05/2024", "30"]])
        before = read_text(src)
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(input_override=src, overwrite=True)
        self.assertIn("key backup", str(cm.exception))
        self.assertEqual(read_text(src), before)

    def test_backup_hard_linked_to_the_input_is_refused_and_input_unchanged(self):
        self.first_run()
        src = self.add_athlete()
        before = read_text(src)
        if os.path.exists(self.backup_path()):
            patient(os.remove, self.backup_path())
        hard_link_or_skip(self, src, self.backup_path())
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(overwrite=True)
        self.assertIn("key backup", str(cm.exception))
        self.assertEqual(read_text(src), before)

    def test_backup_hard_linked_to_an_output_is_refused(self):
        self.first_run()
        hard_link_or_skip(self, self.out_path(), self.backup_path())
        self.add_athlete()
        with self.assertRaises(deidentify.StopRun):
            self.run_it(overwrite=True)

    def test_backup_hard_linked_to_any_other_file_is_refused(self):
        self.first_run()
        other = write_csv(os.path.join(self.tmp, "other.csv"), ["a"], [["1"]])
        hard_link_or_skip(self, other, self.backup_path())
        self.add_athlete()
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(overwrite=True)
        self.assertIn("hard link", str(cm.exception))
        self.assertEqual(read_text(other), "a\n1\n")

    def test_backup_symlink_is_refused_and_its_target_unchanged(self):
        self.first_run()
        other = write_csv(os.path.join(self.tmp, "other.csv"), ["a"], [["1"]])
        link_or_skip(self, other, self.backup_path())
        self.add_athlete()
        with self.assertRaises(deidentify.StopRun):
            self.run_it(overwrite=True)
        self.assertEqual(read_text(other), "a\n1\n")

    def test_backup_that_is_a_folder_is_refused(self):
        self.export()
        os.makedirs(self.backup_path())
        with self.assertRaises(deidentify.StopRun):
            self.run_it()

    def test_backup_goes_through_a_new_file_and_holds_the_previous_key(self):
        _, first_key = self.first_run()
        self.add_athlete()
        self.run_it(overwrite=True)
        self.assertEqual(read_text(self.backup_path()), first_key)
        inode = os.stat(self.backup_path()).st_ino
        second_key = read_text(self.key_path())
        self.export(rows=[["Dee Ash", "08/05/2024", "10"]])
        with mock.patch.object(deidentify.shutil, "copy2", wraps=deidentify.shutil.copy2) as copy:
            self.run_it(overwrite=True)
        self.assertEqual(read_text(self.backup_path()), second_key)
        self.assertNotEqual(os.stat(self.backup_path()).st_ino, inode, "the backup must be replaced, not written in place")
        self.assertNotIn(self.backup_path(), [call.args[1] for call in copy.call_args_list])
        self.assertEqual([n for n in os.listdir(self.key) if n.startswith(".tmp_")], [])


class Fix02PartialWrites(ChangeBase):
    def test_report_destination_is_a_folder_and_nothing_is_written(self):
        self.export()
        os.makedirs(self.out_path(REPORT))
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(overwrite=True)
        self.assertIn("is a folder", str(cm.exception))
        self.assertFalse(os.path.exists(self.out_path()))
        self.assertFalse(os.path.exists(self.key_path()))

    def test_private_report_destination_is_a_folder_and_old_output_is_unchanged(self):
        before, key_before = self.first_run()
        patient(os.remove, os.path.join(self.key, PRIVATE))
        os.makedirs(os.path.join(self.key, PRIVATE))
        self.add_athlete()
        with self.assertRaises(deidentify.StopRun):
            self.run_it(overwrite=True)
        self.assertEqual(read_text(self.out_path()), before)
        self.assertEqual(read_text(self.key_path()), key_before)

    def test_a_folder_at_the_key_path_or_a_file_at_the_folder_path_stops_first(self):
        self.export()
        os.makedirs(self.key_path())
        with self.assertRaises(deidentify.StopRun):
            self.run_it()
        blocked = write_csv(os.path.join(self.tmp, "blocked"), ["a"], [])
        with self.assertRaises(deidentify.StopRun) as cm:
            deidentify.run(self.settings(), "t", output_override=os.path.join(blocked, "out"), key_override=os.path.join(self.tmp, "k2"))
        self.assertIn("not a folder", str(cm.exception))

    def test_a_later_failure_puts_every_earlier_file_back(self):
        before, key_before = self.first_run()
        report_before = read_text(self.out_path(REPORT))
        self.add_athlete()
        with mock.patch("os.replace", fail_replace_on(self.clock, PRIVATE)):
            with self.assertRaises(deidentify.StopRun) as cm:
                self.run_it(overwrite=True)
        self.assertIn("put back", str(cm.exception))
        self.assertIn(PRIVATE, str(cm.exception))
        self.assertEqual(read_text(self.out_path()), before)
        self.assertEqual(read_text(self.out_path(REPORT)), report_before)
        self.assertEqual(read_text(self.key_path()), key_before)
        self.assertFalse(os.path.exists(self.backup_path()), "a backup that did not exist before is removed again")
        self.assertEqual([n for n in os.listdir(self.out) + os.listdir(self.key) if n.startswith(".tmp_")], [])

    def test_a_later_failure_removes_new_files(self):
        self.export()
        with mock.patch("os.replace", fail_replace_on(self.clock, REPORT)):
            with self.assertRaises(deidentify.StopRun):
                self.run_it()
        self.assertFalse(os.path.exists(self.out_path()))
        self.assertFalse(os.path.exists(self.key_path()))

    def test_when_a_file_cannot_be_put_back_the_message_names_it_and_keeps_its_old_copy(self):
        before, _ = self.first_run()
        self.add_athlete()
        coded = self.out_path()

        def replace(src, dst):
            if os.path.basename(dst) == PRIVATE or (dst == coded and src.endswith(".previous")):
                self.clock.simulated_lock = True
                raise PermissionError("locked")
            patient(REAL_REPLACE, src, dst)
        with mock.patch("os.replace", replace):
            with self.assertRaises(deidentify.StopRun) as cm:
                self.run_it(overwrite=True)
        message = str(cm.exception)
        self.assertIn("could not be put back", message)
        self.assertIn(coded, message)
        self.assertNotIn("nothing was replaced", message.casefold())
        saved = re.search(r"previous version is at (.+?\.previous)", message).group(1)
        self.assertEqual(read_text(saved), before)

    def test_cmj_report_destination_is_a_folder_and_nothing_is_written(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), *CMJ_FILE)
        os.makedirs(os.path.join(self.out, "cmj_report_c.txt"))
        with self.assertRaises(cmj_flags.StopRun) as cm:
            cmj_flags.run(cmj_settings(src, self.out))
        self.assertIn("is a folder", str(cm.exception))
        self.assertEqual(os.listdir(self.out), ["cmj_report_c.txt"])

    def test_cmj_later_failure_puts_the_results_back(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), *CMJ_FILE)
        first = cmj_flags.run(cmj_settings(src, self.out))
        before = read_text(first["results_file"])
        write_csv(src, CMJ_FILE[0], CMJ_FILE[1][:-3])
        with mock.patch("os.replace", fail_replace_on(self.clock, os.path.basename(first["report_file"]))):
            with self.assertRaises(cmj_flags.StopRun) as cm:
                cmj_flags.run(cmj_settings(src, self.out), overwrite=True)
        self.assertIn("put back", str(cm.exception))
        self.assertEqual(read_text(first["results_file"]), before)


class Fix03PermittedValues(ChangeBase):
    HEAD = ["Name", "Date", "Load", "Event"]

    def event_run(self, rows, **kw):
        self.export(self.HEAD, rows)
        return self.run_it(self.settings(keep_columns=self.HEAD, **kw))

    def test_category_and_event_columns_need_a_list(self):
        rows = [["Ann Lee", "08/05/2024", "10", "Injury"]]
        for kw in ({"event_columns": ["Event"]}, {"column_types": {"Event": "category"}}, {"class_year_column": "Event"},
                   {"event_columns": ["Event"], "allowed_values": {"Event": []}}):
            with self.assertRaises(deidentify.StopRun, msg=kw) as cm:
                self.event_run(rows, **kw)
            self.assertIn("allowed_values", str(cm.exception))

    def test_other_values_are_blanked_counted_and_named_only_in_the_private_report(self):
        note = "hamstring, saw physio Friday"
        r = self.event_run([["Ann Lee", "08/05/2024", "10", "Injury"], ["Ben Fox", "08/05/2024", "20", note], ["Cal Roy", "08/05/2024", "30", note],
                            ["Dee Ash", "08/05/2024", "30", ""]],
                           event_columns=["Event"], allowed_values={"Event": ["Injury", "Illness"]})
        self.assertEqual([x["Event"] for x in read_rows(r["output_file"])], ["Injury", "", "", ""])
        self.assertEqual(r["not_permitted"], {"Event": 2})
        shareable, private = read_text(r["report_file"]), read_text(r["private_report_file"])
        self.assertIn("2 value(s) in 'Event'", shareable)
        self.assertNotIn("hamstring", shareable)
        self.assertIn(f"'{note}' (2 rows)", private)

    def test_a_listed_value_matches_any_case_and_comes_out_as_listed(self):
        r = self.event_run([["Ann Lee", "08/05/2024", "10", " injury "]], column_types={"Event": "category"}, allowed_values={"Event": ["Injury"]})
        self.assertEqual(read_rows(r["output_file"])[0]["Event"], "Injury")
        self.assertEqual(r["not_permitted"], {})

    def test_a_listed_value_holding_a_name_still_stops(self):
        with self.assertRaises(deidentify.StopRun):
            self.event_run([["Ann Lee", "08/05/2024", "10", "Saw Ann Lee"]], event_columns=["Event"], allowed_values={"Event": ["Saw Ann Lee"]})

    def test_an_allowed_text_column_needs_no_list(self):
        r = self.event_run([["Ann Lee", "08/05/2024", "10", "free note"]], event_columns=["Event"], allowed_text_columns=["Event"])
        self.assertEqual(read_rows(r["output_file"])[0]["Event"], "free note")

    def test_a_position_outside_position_groups_is_treated_the_same_way(self):
        self.export(["Name", "Date", "Load", "Position"], [["Ann Lee", "08/05/2024", "10", "GK"], ["Ben Fox", "08/05/2024", "20", "backup, knee"]])
        r = self.run_it(self.settings(keep_columns=["Name", "Date", "Load", "Position"], position_column="Position"))
        self.assertEqual([x["Position"] for x in read_rows(r["output_file"])], ["Goalkeeper", ""])
        self.assertNotIn("backup, knee", read_text(r["report_file"]))
        self.assertIn("backup, knee", read_text(r["private_report_file"]))

    def test_readme_warns_about_notes_in_event_fields(self):
        self.assertIn("event fields can contain identifying notes", " ".join(read_text(README).split()))


class Fix04NamesInHeadingsAndReport(ChangeBase):
    def test_a_name_in_a_banded_columns_heading_stops(self):
        heading = "Ann Lee Body Mass (kg)"
        self.export(["Name", "Date", "Load", heading], [["Ann Lee", "08/05/2024", "10", "70"]])
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(self.settings(keep_columns=["Name", "Date", "Load", heading], body_mass_column=heading))
        self.assertIn("heading", str(cm.exception))
        self.assertFalse(os.path.exists(self.out_path()))

    def test_a_name_in_an_asymmetry_heading_stops(self):
        heading = "Ann Lee (Asym) (%)"
        self.export(["Name", "Date", "Load", heading], [["Ann Lee", "08/05/2024", "10", "5 L"]])
        with self.assertRaises(deidentify.StopRun):
            self.run_it(self.settings(keep_columns=["Name", "Date", "Load", heading]))

    def test_name_variants_in_any_heading_stop(self):
        for heading in ("Lee, Ann load", "A. Lee load", "A Lee load", "Lee A load", "ann_lee_load", "AnnLee load", "ALee load"):
            self.export(["Name", "Date", "Load", heading], [["Ann Lee", "08/05/2024", "10", "70"]])
            with self.assertRaises(deidentify.StopRun, msg=heading):
                self.run_it(self.settings(keep_columns=["Name", "Date", "Load", heading]), overwrite=True)

    def test_every_output_heading_is_checked_whatever_its_kind(self):
        for kind in ("number", "text", "band", "side"):
            path = write_csv(os.path.join(self.tmp, f"{kind}.csv"), ["Athlete Code", "Ann Lee x"], [["ATH-AAAAAA", ""]])
            problems, _, _ = deidentify.verify_output(path, ["code", kind], {"Ann Lee"}, {"ATH-AAAAAA": "Ann Lee"})
            self.assertTrue(any("heading contained" in p for p in problems), kind)

    def test_anything_in_the_shareable_report_stops_the_run(self):
        self.export(["Name", "Date", "Load", "Position"], [["Ann Lee", "08/05/2024", "10", "GK"]])
        s = self.settings(keep_columns=["Name", "Date", "Load", "Position"], position_column="Position")
        with mock.patch.object(deidentify, "suggest_coarser", return_value="ask Lee, Ann about it"):
            with self.assertRaises(deidentify.StopRun) as cm:
                self.run_it(s)
        self.assertIn("shareable report", str(cm.exception))
        self.assertFalse(os.path.exists(self.out_path()))
        self.assertFalse(os.path.exists(self.out_path(REPORT)))
        self.assertFalse(os.path.exists(self.key_path()))

    def test_a_dropped_heading_holding_a_name_stays_hidden_and_the_run_finishes(self):
        self.export(self.HEADER + ["Ann Lee notes"], [["Ann Lee", "08/05/2024", "10", "x"]])
        r = self.run_it()
        self.assertNotIn("Ann Lee", read_text(r["report_file"]))
        self.assertIn("Ann Lee notes", read_text(r["private_report_file"]))

    def test_digits_in_the_reports_own_counts_and_dates_do_not_stop_a_numeric_id(self):
        year = str(deidentify.datetime.now().year)
        self.export(rows=[[year, "08/05/2024", "10"], ["1", "08/05/2024", "20"], ["2", "08/05/2024", "30"]])
        self.assertTrue(self.run_it())

    def test_a_short_numeric_id_matching_a_heading_stops_with_advice(self):
        self.export(["Name", "Date", "Fatigue (1-5)"], [["5", "08/05/2024", "3"]])
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(self.settings(keep_columns=["Name", "Date", "Fatigue (1-5)"]))
        self.assertIn("longer or non-numeric IDs", str(cm.exception))


class Fix05EmbeddedIds(ChangeBase):
    def note_run(self, athlete, note):
        self.export(self.HEADER + ["Note"], [[athlete, "08/05/2024", "10", note]])
        return self.run_it(self.settings(keep_columns=self.HEADER + ["Note"], allowed_text_columns=["Note"]), overwrite=True)

    def test_ids_of_four_or_more_characters_are_found_inside_longer_text(self):
        for athlete, note in (("12345", "Player12345sore"), ("Anna", "Annabel note"), ("Ann Lee", "xxAnn Leexx"), ("Ann Lee", "ann_lee_notes"),
                              ("ABCD", "zzabcdzz"), ("1234", "row1234")):
            with self.assertRaises(deidentify.StopRun, msg=(athlete, note)) as cm:
                self.note_run(athlete, note)
            self.assertIn("VERIFICATION FAILED", str(cm.exception))

    def test_ids_shorter_than_four_characters_stay_whole_word(self):
        self.assertTrue(self.note_run("Bo", "both good"))
        self.assertTrue(self.note_run("123", "row1234"))
        for note in ("saw Bo today", "bo_note"):
            with self.assertRaises(deidentify.StopRun, msg=note):
                self.note_run("Bo", note)

    def test_the_pattern_itself(self):
        pattern = deidentify.id_pattern({"Anna", "Bo"})
        find = lambda text: bool(pattern.search(deidentify.scan_form(text)))
        self.assertTrue(find("Annabel"))
        self.assertTrue(find("BO"))
        self.assertFalse(find("both"))


class Fix06PartialNumericCopies(ChangeBase):
    def test_some_rows_copying_the_id_warn_and_name_the_column(self):
        self.export(rows=[["12345", "08/05/2024", "12345.0"], ["67890", "08/05/2024", "50"]])
        r = self.run_it()
        self.assertEqual(r["partial_id_copies"], {"Load": 1})
        line = next(x for x in r["report"] if "own athlete ID" in x)
        self.assertIn("DO NOT SHARE", line)
        self.assertIn("'Load'", line)
        self.assertTrue(os.path.exists(r["output_file"]), "a warning, not a stop")

    def test_no_copy_no_warning(self):
        self.export(rows=[["12345", "08/05/2024", "60"], ["67890", "08/05/2024", "50"]])
        r = self.run_it()
        self.assertEqual(r["partial_id_copies"], {})
        self.assertFalse(any("own athlete ID" in x for x in r["report"]))

    def test_a_whole_column_copying_the_id_still_stops(self):
        self.export(rows=[["12345", "08/05/2024", "12345"], ["67890", "08/05/2024", "67890"]])
        with self.assertRaises(deidentify.StopRun):
            self.run_it()

    def test_numeric_ids_under_five_digits_warn(self):
        self.export(rows=[["1234", "08/05/2024", "10"], ["67890", "08/05/2024", "20"], ["Ann Lee", "08/05/2024", "30"]])
        line = next(x for x in self.run_it()["report"] if "shorter than 5 digits" in x)
        self.assertIn("1 athlete ID(s)", line)

    def test_long_or_non_numeric_ids_do_not_warn(self):
        self.export(rows=[["12345", "08/05/2024", "10"], ["Ann Lee", "08/05/2024", "20"], ["A12", "08/05/2024", "30"]])
        self.assertFalse(any("shorter than" in x for x in self.run_it()["report"]))

    def test_readme_recommends_non_numeric_or_long_ids(self):
        self.assertIn("non-numeric or long athlete IDs", " ".join(read_text(README).split()))


class Fix07TwoTestsOnOneDate(ChangeBase):
    HEAD = ["Name", "Date", "Slot", "Load"]

    def slot_run(self, rows, **kw):
        self.export(self.HEAD, rows)
        return self.run_it(self.settings(keep_columns=["Name", "Date", "Load"], **kw))

    def test_readme_no_longer_says_to_change_dates(self):
        text = " ".join(read_text(README).split())
        self.assertNotIn("with different dates", text)
        self.assertIn("one test per date", text)
        self.assertIn("session_column", text)
        self.assertIn("Do not change a date", text)

    def test_session_column_numbers_two_tests_on_one_date(self):
        r = self.slot_run([["Ann Lee", "08/05/2024", "PM", "1"], ["Ann Lee", "08/05/2024", "AM", "2"], ["Ben Fox", "08/05/2024", "PM", "3"],
                           ["Ben Fox", "08/07/2024", "AM", "4"]], session_column="Slot")
        self.assertEqual([x["Session"] for x in read_rows(r["output_file"])], ["2", "1", "2", "3"])
        self.assertNotIn("Slot", r["output_headers"])

    def test_numeric_session_identifiers_sort_by_size(self):
        r = self.slot_run([["Ann Lee", "08/05/2024", "10", "1"], ["Ann Lee", "08/05/2024", "2", "2"]], session_column="Slot")
        self.assertEqual([x["Session"] for x in read_rows(r["output_file"])], ["2", "1"])

    def test_without_the_setting_nothing_changes(self):
        r = self.slot_run([["Ann Lee", "08/05/2024", "PM", "1"], ["Ann Lee", "08/05/2024", "AM", "2"]])
        self.assertEqual([x["Session"] for x in read_rows(r["output_file"])], ["1", "1"])

    def test_session_column_must_exist_and_stay_out_of_keep_columns(self):
        self.export(self.HEAD, [["Ann Lee", "08/05/2024", "AM", "1"]])
        with self.assertRaises(deidentify.StopRun):
            self.run_it(self.settings(keep_columns=["Name", "Date", "Load"], session_column="Missing"))
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it(self.settings(keep_columns=self.HEAD, session_column="Slot"))
        self.assertIn("keep_columns", str(cm.exception))

    def test_the_jump_script_reads_them_as_two_test_days(self):
        head = ["Name", "Date", "Slot", "Test Type", "Trial", "Jump Height (cm)"]
        rows = [[a, f"08/{d:02d}/2024", slot, "CMJ", t, base + d / 10 + t / 10] for a, base in (("Ann Lee", 30), ("Ben Fox", 40))
                for d, slot in ((5, "AM"), (5, "PM"), (12, "AM"), (19, "AM"), (26, "AM")) for t in (1, 2, 3)]
        self.export(head, rows)
        r = self.run_it(self.settings(keep_columns=["Name", "Date", "Test Type", "Trial", "Jump Height (cm)"], session_column="Slot",
                                      column_types={"Test Type": "category"}, allowed_values={"Test Type": ["CMJ"]}))
        out = cmj_flags.run(cmj_settings(r["output_file"], os.path.join(self.tmp, "cmj")))
        self.assertEqual(out["exclusions"], [])
        self.assertEqual(out["counts"]["test_days"], 10)


class Fix08SpreadsheetFormulas(ChangeBase):
    def test_text_values_get_an_apostrophe_and_the_report_says_so(self):
        values = ["=1+1", "+cmd", "-2", "@sum", "  =trim", "plain"]
        self.export(self.HEADER + ["Note"], [[f"Ath {chr(65 + i)}{chr(65 + i)}", "08/05/2024", "10", v] for i, v in enumerate(values)])
        r = self.run_it(self.settings(keep_columns=self.HEADER + ["Note"], allowed_text_columns=["Note"]))
        self.assertEqual([x["Note"] for x in read_rows(r["output_file"])], ["'=1+1", "'+cmd", "'-2", "'@sum", "'=trim", "plain"])
        self.assertEqual(r["formula_guarded"], {"Note": 5})
        line = next(x for x in r["report"] if "formula" in x and "WARNING" in x)
        self.assertIn("5 value(s) in 'Note'", line)
        self.assertIn("INFORMATION ONLY", line)

    def test_a_listed_category_value_is_guarded_too(self):
        self.export(rows=[["Ann Lee", "08/05/2024", "-"]])
        r = self.run_it(self.settings(column_types={"Load": "category"}, allowed_values={"Load": ["-"]}))
        self.assertEqual(read_rows(r["output_file"])[0]["Load"], "'-")

    def test_number_columns_are_left_alone(self):
        self.export(rows=[["Ann Lee", "08/05/2024", "-5.5"], ["Ben Fox", "08/05/2024", "+2"]])
        r = self.run_it()
        self.assertEqual([x["Load"] for x in read_rows(r["output_file"])], ["-5.5", "+2"])
        self.assertEqual(r["formula_guarded"], {})
        self.assertFalse(any("SPREADSHEET" in x for x in r["report"]))

    def test_a_guarded_value_is_still_checked_for_ids(self):
        self.export(self.HEADER + ["Note"], [["Ann Lee", "08/05/2024", "10", "=Ann Lee"]])
        with self.assertRaises(deidentify.StopRun):
            self.run_it(self.settings(keep_columns=self.HEADER + ["Note"], allowed_text_columns=["Note"]))


class Fix09ReadmeReruns(unittest.TestCase):
    def test_readme_says_overwrite_and_never_to_delete_folders(self):
        text = " ".join(read_text(README).split())
        self.assertIn("python deidentify.py gps --overwrite", text)
        self.assertIsNone(re.search(r"delete[^.]*(coded_output|cmj_output|folder|key)", text, re.I))
        self.assertNotIn("Keep the key folder", text)


class Fix10ReadmeSettingsExample(DeidBase):
    def example(self):
        block = re.search(r"### A complete example of edited settings.*?```python\n(.*?)```", read_text(README), re.S).group(1)
        names = {}
        exec(block, names)
        return names["SETTINGS"]

    def test_the_example_runs_exactly_as_written_on_a_matching_file(self):
        settings = self.example()
        name = next(iter(settings["profiles"]))
        p = settings["profiles"][name]
        self.assertEqual(p["input_file"], "C:\\Users\\coach\\Documents\\exports\\jumps_fall.csv")
        rows = [["Ann Lee", "09/01/2025", "CMJ", "1", "35.5", "70"], ["Ben Fox", "09/01/2025", "CMJ", "1", "41.2", "82"]]
        src = write_csv(os.path.join(self.in_dir, "jumps_fall.csv"), p["keep_columns"], rows)
        r = deidentify.run(settings, name, input_override=src, output_override=self.out, key_override=self.key)
        self.assertEqual(r["rows"], 2)

    def test_the_example_has_every_setting_in_the_script(self):
        settings = self.example()
        self.assertEqual(set(settings), set(deidentify.SETTINGS))
        for p in settings["profiles"].values():
            self.assertEqual(set(p), set(deidentify.SETTINGS["profiles"]["force_plate_trials"]))

    def test_the_example_is_not_an_abbreviation(self):
        self.assertNotIn("# ...", read_text(README))


class Fix11EmptyInput(ChangeBase):
    def assert_no_records(self, cm):
        self.assertIn("no athlete records found", str(cm.exception).casefold())

    def test_header_only_file_stops(self):
        self.export(rows=[])
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it()
        self.assert_no_records(cm)
        self.assertFalse(os.path.exists(self.key_path()))

    def test_completely_empty_file_stops(self):
        src = os.path.join(self.in_dir, "export.csv")
        with open(src, "w", encoding="utf-8"):
            pass
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it()
        self.assert_no_records(cm)

    def test_every_id_blank_stops(self):
        self.export(rows=[["", "08/05/2024", "10"], ["  ", "08/05/2024", "20"]])
        with self.assertRaises(deidentify.StopRun) as cm:
            self.run_it()
        self.assert_no_records(cm)

    def test_header_only_file_stops_the_jump_script(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), CMJ_FILE[0], [])
        with self.assertRaises(cmj_flags.StopRun) as cm:
            cmj_flags.run(cmj_settings(src, self.out))
        self.assert_no_records(cm)

    def test_command_line_prints_the_message(self):
        src = self.export(rows=[])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = deidentify.main(["gps", "--input", src, "--output-folder", self.out, "--key-folder", self.key])
        self.assertEqual(code, 1)
        self.assertIn("No athlete records found", out.getvalue())


class Fix12TypicalErrorWording(Base):
    def test_either_direction_everywhere_with_the_trend_example(self):
        src = write_csv(os.path.join(self.in_dir, "c.csv"), *CMJ_FILE)
        report = " ".join(cmj_flags.run(cmj_settings(src, self.out))["report"])
        for text in (" ".join(read_text(README).split()), " ".join(report.split()), " ".join(cmj_flags.__doc__.split())):
            self.assertIn("distort", text)
            self.assertIn("either direction", text)
            self.assertIn("31, 32, 33, 34", text)
            self.assertNotIn("TE is inflated", text)


class Release(unittest.TestCase):
    def test_version_is_1_0_0_everywhere(self):
        self.assertEqual(deidentify.SCRIPT_VERSION, "1.0.2")
        self.assertEqual(cmj_flags.SCRIPT_VERSION, "1.0.2")
        self.assertIn("version: 1.0.2", read_text(os.path.join(ROOT, "CITATION.cff")))

    def test_licence_is_mit_everywhere(self):
        self.assertIn("MIT License\n\nCopyright (c) 2026 Anthony Deldin", read_text(os.path.join(ROOT, "LICENSE")))
        self.assertIn("license: MIT", read_text(os.path.join(ROOT, "CITATION.cff")))
        self.assertIn("MIT. See `LICENSE`.", read_text(README))


class SyntheticProfilesStillClean(DeidBase):
    def test_no_synthetic_value_is_blanked_by_the_permitted_lists(self):
        settings = json.loads(json.dumps(deidentify.SETTINGS))
        for name, profile in settings["profiles"].items():
            profile["input_file"] = os.path.join(ROOT, profile["input_file"])
            r = deidentify.run(settings, name, output_override=self.out, key_override=self.key)
            self.assertEqual(r["not_permitted"], {}, name)
            for line in csv.reader(io.StringIO(read_text(r["output_file"]))):
                self.assertFalse(any(cell.startswith("'") for cell in line), name)


if __name__ == "__main__":
    unittest.main()
