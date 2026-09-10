import errno
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "skills/hypha-governance/scripts/hypha.py"


class CopyAndHookTest(unittest.TestCase):
    def test_copy_fallback_and_same_file_protection(self):
        module = runpy.run_path(str(SCRIPT))
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "source", Path(folder) / "target"
            source.write_bytes(b"original evidence")
            source.chmod(0o640)
            fake = mock.Mock()
            fake.ioctl.side_effect = OSError(errno.EOPNOTSUPP, "Unsupported")
            with mock.patch.dict(module["copy_source"].__globals__, fcntl=fake):
                module["copy_source"](source, target)
            self.assertEqual(source.read_bytes(), target.read_bytes())
            self.assertEqual(source.stat().st_mode, target.stat().st_mode)
            self.assertNotEqual(source.stat().st_ino, target.stat().st_ino)
            source.write_bytes(b"changed")
            self.assertEqual(b"original evidence", target.read_bytes())
            with self.assertRaises(shutil.SameFileError):
                module["copy_source"](source, source)
            self.assertEqual(b"changed", source.read_bytes())

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux reflink path")
    def test_reflink_success_skips_copy2(self):
        module = runpy.run_path(str(SCRIPT))
        def clone(dst, request, src):
            self.assertEqual(0x40049409, request)
            os.write(dst, os.read(src, 1024))
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "source", Path(folder) / "target"
            source.write_bytes(b"evidence")
            with mock.patch.object(module["fcntl"], "ioctl", side_effect=clone), mock.patch.object(shutil, "copy2") as fallback:
                module["copy_source"](source, target)
            fallback.assert_not_called()
            self.assertEqual(b"evidence", target.read_bytes())

    def test_git_hook_blocks_lint_and_test_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            # Hooks inherit repository-local Git variables; never leak them into this fixture.
            env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
            def git(*args):
                return subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=False)
            self.assertEqual(0, git("init", "-q").returncode)
            git("config", "user.name", "Hook Test")
            git("config", "user.email", "hook@example.invalid")
            git("config", "commit.gpgsign", "false")
            git("config", "core.hooksPath", str(ROOT / ".githooks"))
            (repo / ".venv/bin").mkdir(parents=True)
            (repo / ".venv/bin/python").symlink_to(sys.executable)
            script = repo / "skills/hypha-governance/scripts/hypha.py"
            script.parent.mkdir(parents=True)
            script.write_text("undefined_symbol\n")
            (repo / "tests").mkdir()
            test = repo / "tests/test_sample.py"
            test.write_text("import unittest\n\n\nclass Test(unittest.TestCase):\n    def test_case(self):\n        self.fail('hook-test-sentinel')\n")
            git("add", "skills", "tests")
            lint = git("commit", "-m", "Must reject lint")
            self.assertNotEqual(0, lint.returncode)
            self.assertIn("F821", lint.stdout + lint.stderr)
            script.write_text("# Valid source\n")
            git("add", "skills")
            tests = git("commit", "-m", "Must reject test")
            self.assertNotEqual(0, tests.returncode)
            self.assertIn("hook-test-sentinel", tests.stdout + tests.stderr)
            self.assertNotEqual(0, git("rev-parse", "--verify", "HEAD").returncode)
            test.write_text(test.read_text().replace("self.fail('hook-test-sentinel')", "self.assertTrue(True)"))
            git("add", "tests")
            passed = git("commit", "-m", "Checks passed")
            self.assertEqual(0, passed.returncode, passed.stdout + passed.stderr)
            self.assertIn("Ran 1 test", passed.stdout + passed.stderr)
