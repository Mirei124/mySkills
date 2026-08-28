import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
CLI = [sys.executable, str(ROOT / "hypha.py")]

class HyphaCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, ok=True):
        result = subprocess.run(CLI + ["--workspace", str(self.workspace), *args], text=True, capture_output=True)
        if ok and result.returncode:
            self.fail(result.stderr + result.stdout)
        return result

    def test_task_flow_relations_and_sync(self):
        self.cli("init")
        self.cli("add", "first task")
        self.cli("add", "second task")
        self.cli("needs", "0002", "0001")
        self.cli("done", "0001")
        self.assertIn("0002 second task", self.cli("next").stdout)
        task = next((self.workspace / ".hypha" / "intent").glob("0002-*.md"))
        task.write_text(task.read_text(encoding="utf-8").replace("status: todo", "status: in_progress"), encoding="utf-8")
        self.assertIn("0002 [in_progress]", self.cli("boot").stdout)
        events = list((self.workspace / ".hypha" / "snapshots").glob("*.jsonl"))
        self.assertTrue(events)
        self.assertNotIn(".observed.json", {path.name for path in (self.workspace / ".hypha" / "snapshots").iterdir()})

    def test_apply_evidence_and_show(self):
        self.cli("init")
        self.cli("add", "oauth work")
        source = self.workspace / "source.md"
        source.write_text("# Tokens\n\n## Refreshing Tokens\nrotate token safely\n", encoding="utf-8")
        self.cli("ingest", str(source))
        draft = self.workspace / ".hypha" / ".drafts" / "oauth.md"
        draft.write_text("---\nclaim_kind: sourced\nwhen: OAuth refresh fails\ntriggers: [oauth, refresh]\nanchors: [src/source.md#refreshing-tokens]\nevidence:\n  - anchor: src/source.md#refreshing-tokens\n    quote: rotate token safely\naffects: [0001]\n---\n# OAuth token rotation\n\nUse the documented rotation procedure.\n", encoding="utf-8")
        self.cli("apply", str(draft))
        self.assertIn("知识前提：know/oauth", self.cli("show", "0001").stdout)
        self.assertIn("know/oauth", self.cli("why", "oauth").stdout)
        self.cli("lint")

    def test_invalid_task_body_intent_link_is_rejected(self):
        self.cli("init")
        self.cli("add", "task")
        task = next((self.workspace / ".hypha" / "intent").glob("*.md"))
        task.write_text(task.read_text(encoding="utf-8") + "\n[[intent/9999-missing]]\n", encoding="utf-8")
        result = self.cli("lint", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("悬空任务正文链接", result.stdout)

    def test_snapshots_replay_shape(self):
        self.cli("init")
        self.cli("add", "one")
        event_file = next((self.workspace / ".hypha" / "snapshots").glob("*.jsonl"))
        event = json.loads(event_file.read_text(encoding="utf-8").splitlines()[0])
        self.assertIn("recorded_at", event)
        fields = {json.loads(line)["field"] for line in event_file.read_text(encoding="utf-8").splitlines()}
        self.assertIn("body_hash", fields)

    def test_close_view_and_unmanaged_warning(self):
        self.cli("init")
        self.cli("add", "deliverable")
        self.cli("done", "0001")
        self.assertIn("完成候选 0001", self.cli("close").stdout)
        view = Path(self.cli("view").stdout.strip())
        self.assertIn("graph and timeline", view.read_text(encoding="utf-8"))
        task = next((self.workspace / ".hypha" / "intent").glob("*.md"))
        task.write_text(task.read_text(encoding="utf-8").replace("progress: 100", "progress: 99"), encoding="utf-8")
        self.assertIn("未托管正式写入", self.cli("lint").stdout)

if __name__ == "__main__":
    unittest.main()
