import json
import re
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
CLI = [sys.executable, str(ROOT / "skills" / "hypha-governance" / "scripts" / "hypha.py")]

class HyphaCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, ok=True):
        result = subprocess.run(CLI + ["--workspace", str(self.workspace), *args], text=True, capture_output=True, check=False)
        if ok and result.returncode:
            self.fail(result.stderr + result.stdout)
        return result

    def test_help_explains_workflow(self):
        help_text = self.cli("--help").stdout
        self.assertIn("用命令维护结构，用草稿 + apply 发布正文", help_text)
        self.assertIn("输出当前任务与相关知识的精简上下文", help_text)
        self.assertIn("生成可拖拽缩放的任务/知识 Canvas 面板", help_text)
        self.assertIn("会话开始用 boot；结构问题用 lint；完成前用 close", help_text)

    def test_task_flow_relations_and_sync(self):
        self.cli("init")
        self.cli("add", "first task")
        self.cli("add", "second task", "--root")
        self.cli("needs", "0002", "0001")
        self.cli("done", "0001")
        self.assertIn("0002 second task", self.cli("next").stdout)
        task = next((self.workspace / ".hypha" / "intent").glob("0002-*.md"))
        task.write_text(task.read_text(encoding="utf-8").replace("status: todo", "status: in_progress"), encoding="utf-8")
        self.assertIn("0002 [in_progress]", self.cli("boot").stdout)
        events = list((self.workspace / ".hypha" / "snapshots").glob("*.jsonl"))
        self.assertTrue(events)
        self.assertNotIn(".observed.json", {path.name for path in (self.workspace / ".hypha" / "snapshots").iterdir()})

    def test_add_requires_explicit_root_or_parent_and_can_reparent(self):
        self.cli("init")
        self.cli("add", "umbrella")
        result = self.cli("add", "independent", ok=False)
        self.assertIn("请指定父任务 ID，或用 --root", result.stderr)
        duplicate = self.cli("add", "umbrella", "--root", ok=False)
        self.assertIn("已有同名任务 0001", duplicate.stderr)
        self.cli("add", "independent", "--root")
        self.cli("parent", "0002", "0001")
        self.assertIn("子任务：0002", self.cli("show", "0001").stdout)
        self.assertIn("parent: 0001", self.cli("show", "0002").stdout)

    def test_audit_reports_isolated_tasks(self):
        self.cli("init")
        self.cli("add", "first")
        self.cli("add", "second", "--root")
        output = self.cli("lint", "--audit").stdout
        self.assertIn("0001: 孤立任务", output)
        self.assertIn("0002: 孤立任务", output)

    def test_bootstrap_scans_project_writes_plan_and_applies_reviewed_tasks(self):
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "app.py").write_text("def run():\n    return True\n", encoding="utf-8")
        (self.workspace / "tests").mkdir()
        (self.workspace / "tests" / "test_app.py").write_text("def test_run():\n    assert True\n", encoding="utf-8")
        (self.workspace / "docs").mkdir()
        (self.workspace / "docs" / "plan.md").write_text("# Plan\n\n- [x] design\n- [ ] release\n", encoding="utf-8")

        plan = json.loads(self.cli("bootstrap", "--dry-run").stdout)
        self.assertFalse((self.workspace / ".hypha").exists())
        self.assertEqual("hypha-bootstrap-plan", plan["kind"])
        self.assertEqual("low", plan["tasks"][0]["confidence"])
        self.assertEqual({"area:docs", "area:src", "area:tests", "root"}, {task["key"] for task in plan["tasks"]})
        docs = next(task for task in plan["tasks"] if task["key"] == "area:docs")
        self.assertEqual(50, docs["progress"])

        self.cli("init")
        output = self.cli("bootstrap").stdout
        self.assertIn("bootstrap-plan.json", output)
        plan_path = self.workspace / ".hypha" / ".drafts" / "bootstrap-plan.json"
        self.assertTrue(plan_path.is_file())
        applied = self.cli("bootstrap", "--apply", str(plan_path)).stdout
        self.assertIn("创建 4 个任务", applied)
        self.assertIn("子任务：0002, 0003, 0004", self.cli("show", "0001").stdout)
        child = next((self.workspace / ".hypha" / "intent").glob("0002-*.md"))
        self.assertIn("bootstrap_confidence: low", child.read_text(encoding="utf-8"))
        rejected = self.cli("bootstrap", "--apply", str(plan_path), ok=False)
        self.assertIn("仅支持空任务图", rejected.stderr)

    def test_apply_evidence_and_show(self):
        self.cli("init")
        self.cli("add", "oauth work")
        source = self.workspace / "source.md"
        source.write_text("# Tokens\n\n## Refreshing Tokens\nrotate token safely\n", encoding="utf-8")
        self.cli("ingest", str(source))
        draft = self.workspace / ".hypha" / ".drafts" / "oauth.md"
        draft.write_text("---\nkind: know\nclaim_kind: sourced\nwhen: OAuth refresh fails\ntriggers: [oauth, refresh]\nanchors: [src/source.md#refreshing-tokens]\nevidence:\n  - anchor: src/source.md#refreshing-tokens\n    quote: rotate token safely\naffects: [0001]\n---\n# OAuth token rotation\n\nUse the documented rotation procedure.\n", encoding="utf-8")
        self.cli("apply", str(draft))
        self.assertIn("没有未 apply 草稿", self.cli("drafts").stdout)
        draft.write_text(draft.read_text(encoding="utf-8") + "\nchanged after publish\n", encoding="utf-8")
        self.assertIn("oauth.md", self.cli("drafts").stdout)
        self.assertIn("知识前提：know/oauth", self.cli("show", "0001").stdout)
        self.assertIn("know/oauth", self.cli("why", "oauth").stdout)
        self.cli("lint")

    def test_invalid_task_body_intent_link_is_rejected(self):
        self.cli("init")
        self.cli("add", "task")
        task = next((self.workspace / ".hypha" / "intent").glob("0001-*.md"))
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
        self.cli("add", "follow up", "0001")
        self.assertIn("完成候选 0001", self.cli("close").stdout)
        view = Path(self.cli("view", "--mode", "tasks").stdout.strip())
        html = view.read_text(encoding="utf-8")
        self.assertIn("Tasks", html)
        self.assertIn("Knowledge", html)
        self.assertIn("Hypha Mycelial Canvas", html)
        self.assertIn("Mycelium", html)
        self.assertIn('"initialMode": "tasks"', html)
        self.assertIn('"schemaVersion": 1', html)
        self.assertIn('"diagnostics": {"redlinks"', html)
        self.assertIn('"kind": "parent"', html)
        self.assertIn('"progress": 100', html)
        self.assertIn('"path": "intent/', html)
        self.assertIn('"summary":', html)
        self.assertIn('"markdown":', html)
        self.assertIn('"metadata":', html)
        self.assertIn('"generatedAt":', html)
        task = next((self.workspace / ".hypha" / "intent").glob("0001-*.md"))
        task.write_text(task.read_text(encoding="utf-8").replace("progress: 100", "progress: 99"), encoding="utf-8")
        self.assertIn("未托管正式写入", self.cli("lint").stdout)

    def test_open_view_uses_linux_xdg_open_without_waiting(self):
        module = runpy.run_path(str(CLI[1]))
        with mock.patch.object(module["subprocess"], "Popen") as popen:
            module["open_view"](Path("/tmp/hypha-view.html"))
        popen.assert_called_once_with(
            ["xdg-open", "/tmp/hypha-view.html"],
            stdout=module["subprocess"].DEVNULL,
            stderr=module["subprocess"].DEVNULL,
            start_new_session=True,
        )

    def test_apply_requires_explicit_publishable_kind(self):
        self.cli("init")
        self.cli("add", "recover flow")
        drafts = self.workspace / ".hypha" / ".drafts"
        handoff = drafts / "handoff.md"
        handoff.write_text("---\nkind: handoff\n---\n# Continue task 0001\n", encoding="utf-8")
        result = self.cli("apply", str(handoff), ok=False)
        self.assertIn("不能 apply 发布", result.stderr)
        partial = drafts / "partial.md"
        partial.write_text("---\nkind: task-update\ntask: 0001\n---\n# Partial\n", encoding="utf-8")
        result = self.cli("apply", str(partial), ok=False)
        self.assertIn("必须提供 id", result.stderr)
        unknown = drafts / "unknown.md"
        unknown.write_text("---\nclaim_kind: note\n---\n# Unknown\n", encoding="utf-8")
        result = self.cli("apply", str(unknown), ok=False)
        self.assertIn("必须显式写 kind: know", result.stderr)
        self.assertFalse(list((self.workspace / ".hypha" / "know").glob("*.md")))
        update = drafts / "task-update.md"
        update.write_text("---\nkind: task-update\nid: 0001\n---\n# Recovered flow\n\n## 验收\nrecovered\n", encoding="utf-8")
        self.cli("apply", str(update))
        shown = self.cli("show", "0001").stdout
        self.assertIn("Recovered flow", shown)
        self.assertIn("status: todo", shown)

    def test_frontmatter_round_trip_preserves_quotes_and_lists(self):
        self.cli("init")
        draft = self.workspace / ".hypha" / ".drafts" / "quote.md"
        inference = "Provider A's evidence: \"rotate, then retry\""
        draft.write_text(
            "---\nkind: know\nclaim_kind: inference\nwhen: Choosing a provider\nanchors: [src/provider.md#decision]\ninference: [\""
            + inference.replace('"', '\\"')
            + "\"]\n---\n# Provider decision\n",
            encoding="utf-8",
        )
        self.cli("apply", str(draft))
        published = next((self.workspace / ".hypha" / "know").glob("*.md"))
        module = runpy.run_path(str(CLI[1]))
        self.assertEqual([inference], module["read_node"](published)["inference"])

    def test_recovery_hints_and_non_git_lint_are_quiet(self):
        self.cli("init")
        self.assertNotIn(".drafts/", (self.workspace / ".hypha" / ".gitignore").read_text(encoding="utf-8"))
        self.cli("add", "continue flow")
        self.cli("start", "0001")
        self.cli("progress", "0001", "40")
        draft = self.workspace / ".hypha" / ".drafts" / "resume.md"
        draft.write_text("---\nkind: handoff\n---\n# Resume OAuth flow\n", encoding="utf-8")
        boot = self.cli("boot", "oauth")
        self.assertIn("上次会话可能未收尾", boot.stdout)
        self.assertIn("未 apply 草稿：1 个", boot.stdout)
        next_output = self.cli("next").stdout
        self.assertIn("运行中（续接候选）", next_output)
        self.assertIn("0001 40%", next_output)
        self.assertIn("kind=handoff", self.cli("drafts").stdout)
        self.assertIn("progress: 40", self.cli("show", "0001").stdout)
        lint = self.cli("lint", "--audit")
        self.assertEqual("", lint.stderr)
        self.cli("close")
        self.assertNotIn("上次会话可能未收尾", self.cli("boot", "oauth").stdout)

    def test_audit_resolution_suppresses_repeated_candidate(self):
        self.cli("init")
        self.cli("add", "OAuth provider")
        draft = self.workspace / ".hypha" / ".drafts" / "provider.md"
        draft.write_text("---\nkind: know\nclaim_kind: inference\nwhen: Choosing OAuth provider\nanchors: [src/provider.md]\ninference: provider evidence\ntriggers: [oauth, provider]\n---\n# OAuth provider decision\n", encoding="utf-8")
        self.cli("apply", str(draft))
        output = self.cli("lint", "--audit").stdout
        match = re.search(r"\[([0-9a-f]{12})\] 0001", output)
        self.assertIsNotNone(match)
        self.cli("resolve", match.group(1), "unrelated")
        self.assertNotIn(match.group(1), self.cli("lint", "--audit").stdout)

if __name__ == "__main__":
    unittest.main()
