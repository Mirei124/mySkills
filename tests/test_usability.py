import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "skills/hypha-governance/scripts/hypha.py"


class UsabilityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.home = self.workspace / ".hypha"
        self.cli("init")

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(self.workspace), *args], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.workspace), *args], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout

    def test_body_file_merges_acceptance_including_legacy_heading(self):
        for index, heading in enumerate(("Acceptance", "验收"), 1):
            body = self.workspace / "body.md"
            body.write_text(f"## {heading}\n\n- [x] Existing criterion\n\n## Evidence\n\nOriginal evidence.\n")
            self.cli("task", "create", f"Task {index}", "--root", "--body-file", str(body), "--acceptance", "First new criterion", "--acceptance", "Second new criterion")
            shown = self.cli("show", f"{index:04d}").stdout
            self.assertIn("1/3 checked", shown)
            self.assertIn("Remaining: First new criterion", shown)
            self.assertIn("Remaining: Second new criterion", shown)
            self.assertIn("Original evidence.", shown)
        body.write_text("## Acceptance\n\nOne\n\n## Acceptance\n\nTwo\n")
        self.cli("task", "create", "Ambiguous", "--root", "--body-file", str(body), "--acceptance", "Three", ok=False)
        self.assertEqual(2, len(list((self.home / "intent").glob("*.md"))))

    def test_completeness_and_next_action_recovery(self):
        body = self.workspace / "body.md"
        body.write_text("## Next action\n\nRun the browser check.\n")
        self.cli("task", "create", "Browser", "--body-file", str(body))
        checked = self.cli("check").stdout
        self.assertIn("structural validation", checked)
        self.assertIn("0001: missing Acceptance", checked)
        self.assertIn("recognized as Next Step", checked)
        self.cli("check", "--strict", ok=False)
        self.assertIn("Current Next Step: Run the browser check.", self.cli("show", "0001", "--summary").stdout)
        strict = json.loads(self.cli("check", "--strict", "--json", ok=False).stdout)
        self.assertFalse(strict["ok"])

    def test_append_preserves_metadata_origin_history_and_revision_guard(self):
        self.cli("task", "create", "Browser", "--acceptance", "Browser passes")
        self.cli("record", "Browser validation", "--task", "0001", "--evidence", "Browser not tested", "--reference", "report-a", "--current-state", "Browser pending")
        key = "know/browser-validation"
        revision = re.search(r"revision: (\w+)", self.cli("show", key).stdout).group(1)
        task_before = next((self.home / "intent").glob("*.md")).read_bytes()
        self.cli("record", "append", key, "--evidence", "Reported pass covers browser flow only", "--user-quote", "The browser flow passed.", "--current-state", "Browser passed; load testing remains", "--reference", "report-b")
        self.cli("record", "append", key, "--evidence", "Second observation")
        shown = self.cli("show", key).stdout
        self.assertIn("authority: agent_inference", shown)
        self.assertIn("affects: ['0001']", shown)
        self.assertIn("report-a", shown)
        self.assertIn("report-b", shown)
        self.assertIn("Second observation", shown)
        self.assertIn("User observations (user_explicit quotes", shown)
        self.assertIn("State history (earlier states", shown)
        self.assertLess(shown.index("Current state (agent inference): Browser passed"), shown.index("Browser pending"))
        self.assertEqual(task_before, next((self.home / "intent").glob("*.md")).read_bytes())
        self.cli("record", "append", key, "--revision", revision, "--evidence", "Stale update", ok=False)
        self.assertNotIn("Stale update", self.cli("show", key).stdout)
        self.cli("record", "append", "--task", "0001", "--evidence", "Missing target", ok=False)
        self.cli("knowledge", "create", "User statement", "--origin", "user", "--quote", "Exact words", "--when", "Browser")
        self.cli("record", "append", "know/user-statement", "--evidence", "Inference", ok=False)
        self.assertIn("authority: user_explicit", self.cli("show", "know/user-statement").stdout)

    def seed_audit(self):
        self.cli("task", "create", "Browser validation", "--acceptance", "Pass")
        self.cli("task", "create", "Browser rendering", "--parent", "0001", "--acceptance", "Pass")
        self.cli("task", "create", "MHCSinkhorn solver", "--root", "--acceptance", "Pass")
        for title in ("Browser validation policy", "Browser rendering policy", "MHCSinkhorn solver policy", "Browser reference"):
            self.cli("record", title, "--when", "Choosing implementation", "--evidence", "Observed constraint")

    def test_audit_scope_confidence_limit_and_stable_resolution(self):
        self.seed_audit()
        output = self.cli("check", "--audit", "--task", "0001").stdout
        self.assertIn("know/browser-validation-policy", output)
        self.assertNotIn("know/browser-rendering-policy", output)
        self.assertNotIn("mhcsinkhorn", output.lower())
        self.assertNotIn("know/browser-reference", output)
        all_matches = self.cli("check", "--audit", "--task", "0001", "--all-candidates").stdout
        self.assertIn("know/browser-reference", all_matches)
        subtree = self.cli("check", "--audit", "--subtree", "0001").stdout
        self.assertIn("know/browser-rendering-policy", subtree)
        self.assertNotIn("mhcsinkhorn", subtree.lower())
        limited = self.cli("check", "--audit", "--subtree", "0001", "--limit", "1").stdout
        self.assertEqual(1, len(re.findall(r"^- \[[0-9a-f]{12}\]", limited, re.MULTILINE)))
        candidate = re.search(r"\[([0-9a-f]{12})\]", output).group(1)
        self.cli("advanced", "dismiss", candidate)
        self.assertNotIn(candidate, self.cli("check", "--audit", "--subtree", "0001").stdout)
        self.cli("check", "--task", "0001", ok=False)
        self.cli("check", "--audit", "--subtree", "9999", ok=False)
        evidence = self.workspace / "evidence.md"
        evidence.write_text("Reviewed [[know/browser-rendering-policy]].\n")
        self.cli("task", "edit", "0002", "--section", "Evidence", "--body-file", str(evidence))
        self.assertNotIn("know/browser-rendering-policy", self.cli("check", "--audit", "--task", "0002").stdout)

    def test_changed_audit_includes_changed_knowledge_and_untracked_nodes(self):
        self.seed_audit()
        self.git("init")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "Fixture")
        empty = self.cli("check", "--audit", "--changed").stdout
        self.assertIn("Showing 0/0", empty)
        self.cli("record", "append", "know/browser-validation-policy", "--evidence", "New evidence")
        changed = self.cli("check", "--audit", "--changed").stdout
        self.assertIn("know/browser-validation-policy", changed)
        self.assertNotIn("know/browser-rendering-policy", changed)
        self.assertNotIn("mhcsinkhorn", changed.lower())
        self.cli("record", "Browser rendering limits", "--when", "Choosing implementation", "--evidence", "New constraint")
        untracked = self.cli("check", "--audit", "--changed", "HEAD").stdout
        self.assertIn("know/browser-rendering-limits", untracked)
        scoped = self.cli("check", "--audit", "--changed", "--task", "0001").stdout
        self.assertNotIn("know/browser-rendering-limits", scoped)
        self.cli("check", "--audit", "--changed", "missing-ref", ok=False)


if __name__ == "__main__":
    unittest.main()
