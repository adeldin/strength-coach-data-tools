"""Tests for the v1.0.0 release: the file-lock retry, the setting labels, the coach documents and the verification spreadsheet."""
import ast
import contextlib
import csv
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmj_flags  # noqa: E402
import deidentify  # noqa: E402
import make_verify_spreadsheet as sheet  # noqa: E402
from test_review_fixes import CMJ_FILE, cmj_settings, link_or_skip, read_text, write_csv  # noqa: E402
from test_second_review import OUTPUT, REPORT, ChangeBase  # noqa: E402

README = os.path.join(ROOT, "README.md")
QUICKSTART = os.path.join(ROOT, "QUICKSTART.md")
CHECKLIST = os.path.join(ROOT, "REVIEW_CHECKLIST.md")
SPREADSHEET = os.path.join(ROOT, "verify_ivo_larsen.xlsx")
CHANGE = "# CHANGE THIS for your own data"
LEAVE = "# LEAVE AS IS for your first runs"
LOCKED = PermissionError(13, "Access is denied")


class LockedDestination:
    """Stands in for os.replace: the named destination is refused this many times, as a file held by antivirus would be."""

    def __init__(self, name, refusals, before_each=None):
        self.name, self.refusals, self.before_each = name, refusals, before_each
        self.attempts, self.sources = 0, []
        self.real = os.replace

    def __call__(self, src, dst):
        if os.path.basename(dst) != self.name:
            return self.real(src, dst)
        self.attempts += 1
        self.sources.append(src)
        if self.before_each:
            self.before_each(self.attempts)
        if self.attempts <= self.refusals:
            raise LOCKED
        return self.real(src, dst)


class RetryBase(ChangeBase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("time.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def waits(self):
        return [c.args[0] for c in self.sleep.call_args_list]


class RetryOnLockedFile(RetryBase):
    def test_two_refusals_then_success(self):
        self.first_run()
        self.add_athlete()
        locked = LockedDestination(OUTPUT, 2)
        with mock.patch("os.replace", locked):
            r = self.run_it(overwrite=True)
        self.assertEqual(locked.attempts, 3)
        self.assertEqual(self.waits(), [0.2, 0.4])
        self.assertEqual(r["rows"], 3)
        self.assertEqual(len(read_text(self.out_path()).splitlines()), 4)

    def test_every_attempt_refused_stops_plainly_and_replaces_nothing(self):
        before, key_before = self.first_run()
        self.add_athlete()
        locked = LockedDestination(REPORT, 99)
        with mock.patch("os.replace", locked):
            with self.assertRaises(deidentify.StopRun) as cm:
                self.run_it(overwrite=True)
        self.assertEqual(locked.attempts, 5)
        self.assertEqual(self.waits(), [0.2, 0.4, 0.8, 1.6])
        message = str(cm.exception)
        for phrase in ("antivirus", "cloud sync", "Close the file", "pause syncing", "Nothing was replaced"):
            self.assertIn(phrase, message)
        self.assertEqual(read_text(self.out_path()), before)
        self.assertEqual(read_text(self.key_path()), key_before)

    def test_only_our_own_temporary_file_is_moved(self):
        self.first_run()
        self.add_athlete()
        locked = LockedDestination(OUTPUT, 2)
        with mock.patch("os.replace", locked):
            self.run_it(overwrite=True)
        self.assertEqual(len(set(locked.sources)), 1)
        self.assertTrue(os.path.basename(locked.sources[0]).startswith(".tmp_"))

    def test_retry_stops_if_the_destination_becomes_a_link(self):
        self.first_run()
        self.add_athlete()
        target = write_csv(os.path.join(self.tmp, "target.csv"), ["a"], [["1"]])
        target_before = read_text(target)
        try:
            os.symlink(target, os.path.join(self.tmp, "probe"))
        except (OSError, NotImplementedError):
            self.skipTest("this computer does not allow symbolic links without special permission")

        def swap(attempt):
            if attempt == 1:
                os.remove(self.out_path())
                os.symlink(target, self.out_path())
        locked = LockedDestination(OUTPUT, 99, swap)
        with mock.patch("os.replace", locked):
            with self.assertRaises(deidentify.StopRun) as cm:
                self.run_it(overwrite=True)
        self.assertEqual(locked.attempts, 1, "no further move after the destination changed")
        self.assertIn("symbolic link", str(cm.exception))
        self.assertEqual(read_text(target), target_before)

    def test_retry_stops_if_a_file_appears_where_there_was_none(self):
        self.export()
        appeared = "someone else's file\n"

        def appear(attempt):
            if attempt == 1:
                with open(self.out_path(), "w", encoding="utf-8") as f:
                    f.write(appeared)
        locked = LockedDestination(OUTPUT, 99, appear)
        with mock.patch("os.replace", locked):
            with self.assertRaises(deidentify.StopRun) as cm:
                self.run_it()
        self.assertEqual(locked.attempts, 1)
        self.assertIn("changed by another program", str(cm.exception))
        self.assertEqual(read_text(self.out_path()), appeared)

    def test_retry_stops_if_the_file_is_swapped_for_another(self):
        self.first_run()
        self.add_athlete()
        real = os.replace

        def swap(attempt):
            if attempt == 1:
                other = self.out_path("other.csv")
                with open(other, "w", encoding="utf-8") as f:
                    f.write("swapped\n")
                real(other, self.out_path())
        locked = LockedDestination(OUTPUT, 99, swap)
        with mock.patch("os.replace", locked):
            with self.assertRaises(deidentify.StopRun):
                self.run_it(overwrite=True)
        self.assertEqual(read_text(self.out_path()), "swapped\n")

    def test_other_errors_are_not_retried(self):
        self.export()
        real = os.replace

        def replace(src, dst):
            if os.path.basename(dst) == OUTPUT:
                raise OSError(28, "No space left on device")
            real(src, dst)
        with mock.patch("os.replace", replace):
            with self.assertRaises(deidentify.StopRun) as cm:
                self.run_it()
        self.assertEqual(self.waits(), [])
        self.assertIn("No space left", str(cm.exception))
        self.assertNotIn("antivirus", str(cm.exception))

    def test_a_locked_temporary_file_does_not_hide_the_real_message(self):
        self.export()
        with mock.patch("os.remove", side_effect=LOCKED), mock.patch.object(deidentify, "verify_output", side_effect=deidentify.StopRun("the real message")):
            with self.assertRaises(deidentify.StopRun) as cm:
                self.run_it()
        self.assertEqual(str(cm.exception), "the real message")


class RetryInJumpScript(RetryBase):
    def setUp(self):
        super().setUp()
        self.src = write_csv(os.path.join(self.in_dir, "c.csv"), *CMJ_FILE)
        self.name = f"cmj_results_{os.path.basename(self.src)}"

    def test_two_refusals_then_success(self):
        locked = LockedDestination(self.name, 2)
        with mock.patch("os.replace", locked):
            out = cmj_flags.run(cmj_settings(self.src, self.out))
        self.assertEqual(locked.attempts, 3)
        self.assertEqual(self.waits(), [0.2, 0.4])
        self.assertTrue(os.path.exists(out["results_file"]))

    def test_every_attempt_refused_stops_plainly_and_replaces_nothing(self):
        first = cmj_flags.run(cmj_settings(self.src, self.out))
        before = read_text(first["results_file"])
        write_csv(self.src, CMJ_FILE[0], CMJ_FILE[1][:-3])
        locked = LockedDestination(os.path.basename(first["report_file"]), 99)
        with mock.patch("os.replace", locked):
            with self.assertRaises(cmj_flags.StopRun) as cm:
                cmj_flags.run(cmj_settings(self.src, self.out), overwrite=True)
        self.assertEqual(locked.attempts, 5)
        message = str(cm.exception)
        for phrase in ("antivirus", "cloud sync", "Close the file", "pause syncing", "Nothing was replaced"):
            self.assertIn(phrase, message)
        self.assertEqual(read_text(first["results_file"]), before)

    def test_retry_stops_if_the_destination_becomes_a_link(self):
        first = cmj_flags.run(cmj_settings(self.src, self.out))
        target = write_csv(os.path.join(self.tmp, "target.csv"), ["a"], [["1"]])
        target_before = read_text(target)
        link_or_skip(self, target, os.path.join(self.tmp, "probe"))

        def swap(attempt):
            if attempt == 1:
                os.remove(first["results_file"])
                os.symlink(target, first["results_file"])
        locked = LockedDestination(self.name, 99, swap)
        with mock.patch("os.replace", locked):
            with self.assertRaises(cmj_flags.StopRun):
                cmj_flags.run(cmj_settings(self.src, self.out), overwrite=True)
        self.assertEqual(locked.attempts, 1)
        self.assertEqual(read_text(target), target_before)


def settings_lines(path):
    text = read_text(path)
    start = text.index("SETTINGS = {\n")
    return text[start:text.index("\n}\n", start)].split("\n")


class SettingLabels(unittest.TestCase):
    def labelled(self, path, names):
        out = {}
        for line in settings_lines(path):
            m = re.match(r'^\s+"(\w+)":', line)
            if m and m.group(1) in names:
                out.setdefault(m.group(1), []).append(line)
        return out

    def test_every_setting_in_both_scripts_has_one_label(self):
        profile_names = set(deidentify.SETTINGS["profiles"]["force_plate_trials"])
        top = set(deidentify.SETTINGS) - {"profiles"}
        for path, names in ((os.path.join(ROOT, "deidentify.py"), top | profile_names), (os.path.join(ROOT, "cmj_flags.py"), set(cmj_flags.SETTINGS))):
            found = self.labelled(path, names)
            self.assertEqual(set(found), names, path)
            for lines in found.values():
                for line in lines:
                    self.assertEqual((CHANGE in line) + (LEAVE in line), 1, line)

    def changed(self, path, names):
        return {k for k, lines in self.labelled(path, names).items() if any(CHANGE in x for x in lines)}

    def test_a_beginner_changes_only_these(self):
        d = self.changed(os.path.join(ROOT, "deidentify.py"), set(deidentify.SETTINGS) | set(deidentify.SETTINGS["profiles"]["gps"]))
        self.assertEqual(d, {"season_start_date", "input_file", "athlete_id_column", "keep_columns", "date_columns", "date_format"})
        self.assertEqual(self.changed(os.path.join(ROOT, "cmj_flags.py"), set(cmj_flags.SETTINGS)), {"input_file", "jump_height_column"})

    def test_they_are_listed_near_the_top_of_the_readme(self):
        text = read_text(README)
        section = text[text.index("## The settings to change"):text.index("## 1. Install Python")]
        for name in ("season_start_date", "input_file", "athlete_id_column", "keep_columns", "date_columns", "date_format", "jump_height_column"):
            self.assertIn(f'"{name}"', section)
        self.assertLess(text.index("## The settings to change"), text.index("## 1. Install Python"))

    def test_the_labels_changed_no_setting_value(self):
        self.assertEqual(deidentify.SETTINGS["season_start_date"], "2024-08-05")
        self.assertEqual(cmj_flags.SETTINGS["k"], 1.5)
        self.assertEqual(cmj_flags.SETTINGS["baseline_days"], 4)
        self.assertEqual(cmj_flags.SETTINGS["swc_multiplier"], 0.2)


class NoNetwork(unittest.TestCase):
    BANNED = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "socketserver", "asyncio", "requests", "webbrowser"}

    def imports(self, name):
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                found.add((node.module or "").split(".")[0])
        return found

    def test_the_scripts_import_no_network_module_and_only_the_standard_library(self):
        for name in ("deidentify.py", "cmj_flags.py"):
            found = self.imports(name)
            self.assertFalse(found & self.BANNED, name)
            if hasattr(sys, "stdlib_module_names"):
                self.assertTrue(found <= set(sys.stdlib_module_names), found - set(sys.stdlib_module_names))


class Quickstart(unittest.TestCase):
    """Every line of output pasted into QUICKSTART.md must come from a real run today."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="quick_")
        shutil.copytree(os.path.join(ROOT, "synthetic_data"), os.path.join(cls.tmp, "synthetic_data"))
        cwd = os.getcwd()
        os.chdir(cls.tmp)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                deidentify.main(["force_plate_trials"])
                cmj_flags.main([])
                with open("KEY_DO_NOT_SHARE/athlete_key.csv", newline="", encoding="utf-8") as f:
                    codes = {r["original_id"]: r["code"] for r in csv.DictReader(f)}
                cmj_flags.main(["--explain", codes["Ivo Larsen"]])
                cmj_flags.main(["--explain", codes["Zane Zahra"]])
            cls.output = out.getvalue().replace("\\", "/")
        finally:
            os.chdir(cwd)
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_pasted_line_matches_a_real_run(self):
        blocks = re.findall(r"```text\n(.*?)```", read_text(QUICKSTART), re.S)
        self.assertEqual(len(blocks), 4)
        lines = set(self.output.splitlines())
        for block in blocks:
            for line in block.splitlines():
                if line.strip():
                    self.assertIn(line, lines)

    def test_the_commands_and_steps_are_there(self):
        text = read_text(QUICKSTART)
        for phrase in ("python deidentify.py force_plate_trials", "python cmj_flags.py", "--explain", "verify_ivo_larsen.xlsx", "Download ZIP",
                       "strength-coach-data-tools-main", "Ivo Larsen", "Zane Zahra", "not a decision", "15 minutes", "python3", "--overwrite"):
            self.assertIn(phrase, text)


class VerificationSpreadsheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book = sheet.read_workbook(SPREADSHEET)
        cls.answers = sheet.evaluate_workbook(cls.book)
        cls.ivo = cls.book[sheet.IVO_SHEET]
        cls.squad = cls.book[sheet.SQUAD_SHEET]

    def test_every_match_cell_says_ok(self):
        matches = [v for (s, c), v in self.answers.items() if v in ("OK", "CHECK")]
        self.assertEqual(len(matches), 19)
        self.assertEqual(set(matches), {"OK"})

    def test_the_stored_answers_are_the_formulas_answers(self):
        for (s, c), answer in self.answers.items():
            stored = self.book[s][c]["value"]
            if isinstance(answer, str):
                self.assertEqual(stored, answer, (s, c))
            else:
                self.assertAlmostEqual(stored, answer, places=9, msg=(s, c))

    def test_the_calculated_cells_are_live_formulas(self):
        for cell in ("E6", "E7", "E8", "E9", "E10", "E14", "E15", "E19", "E20", "E21", "E27"):
            self.assertIsNotNone(self.ivo[cell]["formula"], cell)
        for cell in ("B5", "B6", "B7", "B8", "B10", "B12", "N16", "R16", "S16"):
            self.assertIsNotNone(self.squad[cell]["formula"], cell)

    def test_the_worked_example_numbers(self):
        got = {c: self.answers[(sheet.IVO_SHEET, c)] for c in ("E10", "E14", "E15", "E19", "E20", "E21")}
        want = {"E10": 28.56, "E14": 24.57, "E15": 3.99, "E19": 1.45, "E20": 1.07, "E21": 2.18}
        for cell, value in want.items():
            self.assertAlmostEqual(got[cell], value, delta=0.0051, msg=cell)
        self.assertEqual(self.answers[(sheet.IVO_SHEET, "E27")], "FLAG")

    def test_it_agrees_with_the_scripts_exactly(self):
        athletes, squad, _ = sheet.squad_values()
        self.assertAlmostEqual(self.answers[(sheet.SQUAD_SHEET, "B7")], squad["te"], places=9)
        self.assertAlmostEqual(self.answers[(sheet.SQUAD_SHEET, "B10")], squad["swc"], places=9)
        self.assertAlmostEqual(self.answers[(sheet.SQUAD_SHEET, "B12")], squad["k_te"], places=9)
        self.assertAlmostEqual(self.answers[(sheet.IVO_SHEET, "E10")], athletes["Ivo Larsen"]["baseline_mean"], places=9)
        names = [self.squad[f"A{r}"]["value"] for r in range(16, 43)]
        self.assertEqual(names, sorted(n for n, a in athletes.items() if a["enough"]))

    def test_the_settings_in_the_sheet_match_the_defaults(self):
        self.assertEqual(self.squad["B9"]["value"], cmj_flags.SETTINGS["swc_multiplier"])
        self.assertEqual(self.squad["B11"]["value"], cmj_flags.SETTINGS["k"])

    def test_the_scripts_do_not_need_the_builder(self):
        self.assertNotIn("openpyxl", read_text(os.path.join(ROOT, "deidentify.py")) + read_text(os.path.join(ROOT, "cmj_flags.py")))


class CoachDocuments(unittest.TestCase):
    def test_the_review_checklist_lists_the_five_checks_on_one_page(self):
        text = read_text(CHECKLIST)
        for phrase in ("No network calls", "Input files are untouched", "no names or IDs", "Thresholds match the stated method", "tests pass"):
            self.assertIn(phrase, text.replace("The tests pass", "tests pass"))
        for command in ("grep -nE", "Select-String", "shasum -a 256", "Get-FileHash", "python -m unittest discover -s tests", "verify_ivo_larsen.xlsx"):
            self.assertIn(command, text)
        self.assertLessEqual(len(text.split()), 500, "one page")

    def test_the_readme_says_what_it_does_and_does_not_do(self):
        text = read_text(README)
        section = text[text.index("## What this software does and does not do"):]
        section = section[:section.index("\n## ", 5)]
        self.assertIn("no network connections", section)
        self.assertIn("0.4.0", section)
        self.assertIn("1.0.0", section)
        self.assertLessEqual(len(section.split()), 220, "short")

    def test_the_files_table_names_the_new_files(self):
        table = read_text(README)
        table = table[table.index("## Files"):]
        for name in ("QUICKSTART.md", "REVIEW_CHECKLIST.md", "verify_ivo_larsen.xlsx", "make_verify_spreadsheet.py"):
            self.assertIn(name, table)


if __name__ == "__main__":
    unittest.main()
