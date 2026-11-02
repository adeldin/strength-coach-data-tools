"""The committed synthetic files must be exactly what the generator produces, on every platform."""
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    def test_scripts_run_from_the_command_line(self):
        tmp = tempfile.mkdtemp(prefix="cli_")
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, "deidentify.py", "force_plate", "--output-folder", os.path.join(tmp, "o"),
                                "--key-folder", os.path.join(tmp, "k")], cwd=ROOT, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("coded data", r.stdout)
            r = subprocess.run([sys.executable, "cmj_flags.py", "--input", os.path.join(tmp, "o", "coded_cmj_season1.csv"),
                                "--output-folder", os.path.join(tmp, "c")], cwd=ROOT, capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("FLAGS (2)", r.stdout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
