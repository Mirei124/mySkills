import argparse
import hashlib
import json
import re
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "skills/hypha-governance/scripts/hypha.py"


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.home = self.workspace / ".hypha"
        self.cli("init")
        self.cli("task", "create", "Pipeline", "--acceptance", "Verify ingestion and recovery")

    def cli(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(self.workspace), *args], capture_output=True, text=True, check=False)
        if ok: self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        else: self.assertNotEqual(0, result.returncode)
        return result

    def snapshot(self):
        return {str(p.relative_to(self.home)): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.home.rglob("*") if p.is_file()}

    def revision(self, key):
        return re.search(r"revision: (\w+)", self.cli("show", key).stdout).group(1)

    def test_all_recovery_reads_leave_every_file_unchanged(self):
        self.cli("record", "Defer overlap", "--task", "0001", "--evidence", "Profiler reports 2% transfer; no overlap implementation was tested", "--decision", "defer", "--review-when", "Transfer becomes the bottleneck")
        (self.home / "lock").unlink()
        before = self.snapshot()
        for args in [("show", "0001"), ("show", "know/defer-overlap"), ("list",), ("search", "overlap"), ("context", "resume", "overlap"), ("advanced", "drafts"), ("advanced", "drafts", "--all"), ("advanced", "explain", "overlap")]:
            self.cli(*args)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.home / "lock").exists())

    def test_record_links_without_copying_observations_or_completing_task(self):
        result = self.cli("record", "Defer overlap", "--task", "0001", "--evidence", "Profiler reports 2% transfer", "--decision", "defer", "--reference", "reports/profile.txt")
        self.assertIn("not fetch or verify", result.stdout)
        task = self.cli("show", "0001").stdout
        self.assertIn("[[know/defer-overlap]]", task)
        self.assertNotIn("Profiler reports 2%", task)
        self.assertIn("status: todo", task)
        self.assertIn("[ ] Verify ingestion", task)
        knowledge = self.cli("show", "know/defer-overlap").stdout
        self.assertIn("authority: agent_inference", knowledge)
        self.assertIn("Profiler reports 2%", knowledge)
        self.assertEqual([], list((self.home / ".drafts").glob("*.md")))
        self.cli("record", "Unscoped", "--evidence", "Observed", ok=False)
        self.cli("record", "Wrong task", "--task", "9999", "--evidence", "Observed", ok=False)

    def test_explicit_correction_updates_old_relationships_and_preserves_evidence(self):
        self.cli("record", "Scratch integration fails", "--task", "0001", "--evidence", "Primitive passed; full regression failed", "--decision", "reject")
        key = "know/scratch-integration-fails"
        rev = self.revision(key)
        self.cli("record", "Separate buffers pass", "--evidence", "Both dtype regressions passed", "--supersedes", key, "--because", "New integration changed buffer ownership", "--revision", "stale", ok=False)
        self.assertIn("status: active", self.cli("show", key).stdout)
        self.cli("record", "Separate buffers pass", "--evidence", "Both dtype regressions passed", "--supersedes", key, "--because", "New integration changed buffer ownership", "--revision", rev, "--decision", "keep")
        old = self.cli("show", key).stdout
        self.assertIn("status: superseded", old)
        self.assertIn("Primitive passed; full regression failed", old)
        self.assertIn("superseded_by: know/separate-buffers-pass", old)
        self.assertIn("[[know/separate-buffers-pass]]", self.cli("show", "0001").stdout)
        self.assertNotIn("know/scratch-integration-fails.md:", self.cli("search", "Scratch", "--type", "knowledge").stdout)
        self.assertIn("corrected knowledge", self.cli("search", "Scratch", "--type", "task").stdout)

    def test_record_update_adds_observations_and_rejects_changed_claim(self):
        self.cli("record", "Overlap deferred", "--task", "0001", "--evidence", "First profile", "--decision", "defer")
        key = "know/overlap-deferred"
        rev = self.revision(key)
        self.cli("record", "New claim", "--update", key, "--revision", rev, "--evidence", "Second profile", ok=False)
        self.cli("record", "Overlap deferred", "--update", key, "--revision", rev, "--evidence", "Second profile")
        shown = self.cli("show", key).stdout
        self.assertIn("First profile", shown)
        self.assertIn("Second profile", shown)
        self.cli("record", "Overlap deferred", "--update", key, "--revision", rev, "--evidence", "Third profile", ok=False)

    def test_multiple_exact_sources_and_no_silent_downgrade(self):
        a, b = self.workspace / "official.txt", self.workspace / "local.h"
        a.write_text("Separate buffers are supported.")
        b.write_text("architecture == 2201")
        self.cli("knowledge", "create", "Scoped sources", "--origin", "external", "--when", "Target 2201", "--source", str(a), "--quote", "Separate buffers", "--source", str(b), "--quote", "architecture == 2201")
        shown = self.cli("show", "know/scoped-sources").stdout
        self.assertIn("src/official.txt", shown)
        self.assertIn("src/local.h", shown)
        self.assertIn("claim_kind: sourced", shown)
        self.cli("knowledge", "create", "Missing pair", "--origin", "external", "--when", "Target", "--source", str(a), "--quote", "Separate buffers", "--source", str(b), ok=False)
        self.cli("knowledge", "create", "Invalid URL", "--origin", "external", "--when", "Target", "--source", "https://example.com", "--quote", "Unknown", ok=False)
        self.assertEqual(1, len(list((self.home / "know").glob("*.md"))))

    def test_draft_ids_discard_and_published_states(self):
        draft = Path(self.cli("task", "edit", "0001", "--draft").stdout.splitlines()[0])
        self.cli("advanced", "discard", draft.stem)
        self.assertTrue(draft.exists())
        self.assertIn("discarded", self.cli("advanced", "drafts", "--all").stdout)
        self.assertIn("No unapplied drafts", self.cli("advanced", "drafts").stdout)
        self.cli("advanced", "publish", draft.stem, ok=False)
        draft.write_text(draft.read_text() + "\n## Evidence\n\nObserved milestone.\n")
        self.cli("advanced", "publish", draft.stem)
        self.assertIn("published", self.cli("advanced", "drafts", "--all").stdout)

    def test_record_write_failure_rolls_back_all_nodes_and_audit(self):
        module = runpy.run_path(str(SCRIPT))
        function = module["record_conclusion"]
        before = {k: data for k, (data, _) in self.snapshot().items()}
        args = argparse.Namespace(workspace=str(self.workspace), workspace_explicit=True, global_store=False, command="record", conclusion="Test result", evidence=["Observed"], task=["0001"], when=None, reference=[], decision=None, review_when=None, update=None, supersedes=None, because=None, revision=None)
        original = module["write_node"]
        calls = 0
        def fail_second(*a, **kw):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError("Injected failure")
            return original(*a, **kw)
        with mock.patch.dict(function.__globals__, {"write_node": fail_second}), self.assertRaisesRegex(OSError, "Injected"):
            function(args)
        after = {k: data for k, (data, _) in self.snapshot().items()}
        self.assertEqual(before, after)

    def test_interrupted_record_is_not_read_as_complete(self):
        task = next((self.home / "intent").glob("*.md"))
        original = task.read_text()
        journal = self.home / ".pending-record.json"
        journal.write_text(json.dumps({str(task.relative_to(self.home)): original}))
        task.write_text(original.replace("Pipeline", "Partial write"))
        self.cli("show", "0001", ok=False)
        self.cli("check")
        self.assertEqual(original, task.read_text())
        self.assertFalse(journal.exists())
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), self.revision("0001"))

    def test_append_failure_rolls_back_current_state_quotes_and_observations(self):
        self.cli("record", "Browser validation", "--task", "0001", "--evidence", "Not tested", "--current-state", "Pending")
        module = runpy.run_path(str(SCRIPT))
        function = module["record_conclusion"]
        args = module["build_parser"]().parse_args(["--workspace", str(self.workspace), "record", "append", "know/browser-validation", "--evidence", "Reported pass", "--current-state", "Passed", "--user-quote", "It passed."])
        args.workspace_explicit = True
        before = {k: data for k, (data, _) in self.snapshot().items()}
        original = module["write_node"]
        calls = 0
        def fail_second(*a, **kw):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError("Injected append failure")
            return original(*a, **kw)
        with mock.patch.dict(function.__globals__, {"write_node": fail_second}), self.assertRaisesRegex(OSError, "Injected append"):
            function(args)
        self.assertEqual(before, {k: data for k, (data, _) in self.snapshot().items()})
