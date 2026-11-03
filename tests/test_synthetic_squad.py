"""The committed synthetic files must be exactly what the generator produces, on every platform."""
import contextlib
import filecmp
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cmj_flags  # noqa: E402
import deidentify  # noqa: E402


class GeneratorTests(unittest.TestCase):
    def test_generator_is_deterministic_and_matches_committed_files(self):
        tmp = tempfile.mkdtemp(prefix="squad_")
        try:
            out, exp = os.path.join(tmp, "data"), os.path.join(tmp, "expected")
            subprocess.run([sys.executable, os.path.join(ROOT, "make_synthetic_squad.py"), "--out", out, "--expected", exp],
                           check=True, capture_output=True)
            for name in os.listdir(os.path.join(ROOT, "synthetic_data")):
                self.assertTrue(filecmp.cmp(os.path.join(ROOT, "synthetic_data", name), os.path.join(out, name), shallow=False),
                                f"{name} differs from the committed copy: regenerate and commit, or the generator changed")
            self.assertTrue(filecmp.cmp(os.path.join(ROOT, "expected_output", "expected_answers.json"),
                                        os.path.join(exp, "expected_answers.json"), shallow=False))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_versions_match(self):
        with open(os.path.join(ROOT, "CITATION.cff"), encoding="utf-8") as f:
            self.assertIn(f"version: {cmj_flags.SCRIPT_VERSION}\n", f.read())
        self.assertEqual(cmj_flags.SCRIPT_VERSION, deidentify.SCRIPT_VERSION)

    def test_old_python_stops_with_a_clear_message(self):
        for script in (cmj_flags, deidentify):
            out = io.StringIO()
            with mock.patch.object(sys, "version_info", (3, 9, 6)), contextlib.redirect_stdout(out):
                with self.assertRaises(SystemExit):
                    script.main([])
            self.assertIn("Python 3.10 or newer", out.getvalue())

    def test_scripts_run_from_the_command_line(self):
        tmp = tempfile.mkdtemp(prefix="cli_")
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, "deidentify.py", "force_plate_trials", "--output-folder", os.path.join(tmp, "o"),
                                "--key-folder", os.path.join(tmp, "k")], cwd=ROOT, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("coded data", r.stdout)
            r = subprocess.run([sys.executable, "cmj_flags.py", "--input", os.path.join(tmp, "o", "coded_cmj_trials_season1.csv"),
                                "--output-folder", os.path.join(tmp, "c")], cwd=ROOT, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("FLAGS (", r.stdout)
            self.assertIn("per-trial", r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
