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
        self.assertIn("列出所有任务和知识节点", help_text)
        self.assertIn("生成可拖拽缩放的任务/知识 Canvas 面板", help_text)
        self.assertIn("会话开始用 boot；结构问题用 lint；完成前用 close", help_text)

    def test_task_flow_relations_and_sync(self):
        self.cli("init")
        self.cli("add", "first task")
        self.cli("add", "second task", "--root")
        self.cli("needs", "0002", "0001")
        self.cli("done", "0001")
        self.assertIn("0002 second task", self.cli("ready").stdout)
        task = next((self.workspace / ".hypha" / "intent").glob("0002-*.md"))
        task.write_text(task.read_text(encoding="utf-8").replace("status: todo", "status: in_progress"), encoding="utf-8")
        self.assertIn("0002 [in_progress]", self.cli("boot").stdout)
        events = list((self.workspace / ".hypha" / "snapshots").glob("*.jsonl"))
        self.assertTrue(events)
        self.assertNotIn(".observed.json", {path.name for path in (self.workspace / ".hypha" / "snapshots").iterdir()})

    def test_list_supports_table_filters_tree_and_json(self):
        self.cli("init")
        self.cli("add", "umbrella")
        self.cli("add", "child work", "0001")
        self.cli("start", "0002")
        draft = self.workspace / ".hypha" / ".drafts" / "overview.md"
        draft.write_text("---\nkind: know\nclaim_kind: note\naffects: [0002]\n---\n# Overview note\n", encoding="utf-8")
        self.cli("apply", str(draft))

        table = self.cli("list").stdout
        self.assertIn("TYPE", table)
        self.assertIn("0002", table)
        self.assertIn("know/overview", table)
        filtered = self.cli("list", "--type", "task", "--status", "in_progress").stdout
        self.assertIn("child work", filtered)
        self.assertNotIn("umbrella", filtered)
        self.assertNotIn("Overview note", filtered)
        tree = self.cli("list", "--tree").stdout
        self.assertRegex(tree, r"(?m)^0001 \[todo\].*umbrella\n  0002 \[in_progress\].*child work$")
        payload = json.loads(self.cli("list", "--json").stdout)
        self.assertEqual({"total": 3, "task": 2, "knowledge": 1}, payload["counts"])
        child = next(node for node in payload["nodes"] if node["id"] == "0002")
        self.assertEqual("0001", child["parent"])
        self.assertIn("created_at", child)
        self.assertIn("updated_at", child)
        self.assertEqual("No nodes match the filters.\n", self.cli("list", "--status", "blocked").stdout)

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

    def test_parent_progress_is_derived_from_non_dropped_leaves(self):
        self.cli("init")
        self.cli("add", "parent")
        self.cli("progress", "0001", "40")
        self.cli("add", "first leaf", "0001")
        parent = next((self.workspace / ".hypha" / "intent").glob("0001-*.md"))
        self.assertNotIn("progress:", parent.read_text(encoding="utf-8"))
        rejected = self.cli("progress", "0001", "90", ok=False)
        self.assertIn("请更新叶子节点进度", rejected.stderr)
        self.cli("progress", "0002", "40")
        self.assertIn("progress: 40", self.cli("show", "0001").stdout)
        self.cli("add", "second leaf", "0001")
        self.cli("progress", "0003", "80")
        self.assertIn("progress: 60", self.cli("show", "0001").stdout)
        self.cli("drop", "0003")
        self.assertIn("progress: 40", self.cli("show", "0001").stdout)
        blocked_done = self.cli("done", "0001", ok=False)
        self.assertIn("聚合进度为 40%", blocked_done.stderr)
        self.cli("done", "0002")
        self.cli("done", "0001")
        self.assertIn("progress: 100", self.cli("show", "0001").stdout)
        payload = json.loads(self.cli("list", "--json").stdout)
        root = next(node for node in payload["nodes"] if node["id"] == "0001")
        self.assertEqual(100, root["progress"])

    def test_progress_average_is_independent_of_intermediate_grouping(self):
        module = runpy.run_path(str(CLI[1]))
        tasks = {
            "0001": {"status": "in_progress"},
            "0002": {"status": "done", "progress": 100, "parent": "0001"},
            "0003": {"status": "in_progress", "parent": "0001"},
            "0004": {"status": "done", "progress": 100, "parent": "0003"},
            "0005": {"status": "todo", "progress": 0, "parent": "0003"},
            "0006": {"status": "todo", "progress": 0, "parent": "0003"},
        }
        progresses = module["task_progresses"](tasks)
        self.assertEqual(50, progresses["0001"])
        self.assertEqual(33, progresses["0003"])

    def test_audit_reports_isolated_tasks(self):
        self.cli("init")
        self.cli("add", "first")
        self.cli("add", "second", "--root")
        output = self.cli("lint", "--audit").stdout
        self.assertIn("0001: 孤立任务", output)
        self.assertIn("0002: 孤立任务", output)

    def test_bootstrap_scans_project_writes_plan_and_applies_reviewed_tasks(self):
        (self.workspace / "AGENTS.md").write_text("# Rules\n\n- Always use Git.\n", encoding="utf-8")
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "app.py").write_text("def run():\n    return True\n", encoding="utf-8")
        (self.workspace / "tests").mkdir()
        (self.workspace / "tests" / "test_app.py").write_text("def test_run():\n    assert True\n", encoding="utf-8")
        (self.workspace / "docs").mkdir()
        (self.workspace / "docs" / "plan.md").write_text("# Plan\n\n- [x] design\n- [ ] release\n", encoding="utf-8")

        plan = json.loads(self.cli("bootstrap", "--dry-run").stdout)
        self.assertFalse((self.workspace / ".hypha").exists())
        self.assertEqual("hypha-bootstrap-plan", plan["kind"])
        self.assertEqual(2, plan["schemaVersion"])
        self.assertFalse(plan["reviewed"])
        self.assertEqual(1, len(plan["observations"]["completed_items"]))
        self.assertEqual(1, len(plan["observations"]["open_items"]))
        self.assertEqual(["done", "todo"], [task["status"] for task in plan["tasks"][1:]])
        self.assertEqual([100, 0], [task["progress"] for task in plan["tasks"][1:]])
        self.assertEqual("docs/plan.md", plan["knowledge"][0]["source"])
        self.assertNotIn("AGENTS.md", {entry["source"] for entry in plan["knowledge"]})

        self.cli("init")
        output = self.cli("bootstrap").stdout
        self.assertIn("bootstrap-plan.json", output)
        self.assertIn("AGENT FOLLOW-UP", output)
        plan_path = self.workspace / ".hypha" / ".drafts" / "bootstrap-plan.json"
        self.assertTrue(plan_path.is_file())
        rejected = self.cli("bootstrap", "--apply", str(plan_path), ok=False)
        self.assertIn("reviewed: true", rejected.stderr)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["reviewed"] = True
        plan["tasks"][0]["title"] = "Ship the reviewed project"
        plan["tasks"][0]["acceptance"] = ["All reviewed repository work is represented by evidence-backed leaves."]
        plan["tasks"][0]["confidence"] = "reviewed"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rejected = self.cli("bootstrap", "--apply", str(plan_path), ok=False)
        self.assertIn("knowledge 候选必须审阅", rejected.stderr)
        plan["knowledge"][0]["confidence"] = "reviewed"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        applied = self.cli("bootstrap", "--apply", str(plan_path)).stdout
        self.assertIn("创建 4 个节点", applied)
        self.assertIn("子任务：0002, 0003", self.cli("show", "0001").stdout)
        self.assertIn("progress: 50", self.cli("show", "0001").stdout)
        root = next((self.workspace / ".hypha" / "intent").glob("0001-*.md"))
        self.assertNotIn("progress:", root.read_text(encoding="utf-8"))
        child = next((self.workspace / ".hypha" / "intent").glob("0002-*.md"))
        self.assertIn("bootstrap_confidence: explicit-marker", child.read_text(encoding="utf-8"))
        knowledge = next((self.workspace / ".hypha" / "know" / "bootstrap").glob("*.md"))
        self.assertIn("claim_kind: sourced", knowledge.read_text(encoding="utf-8"))
        self.assertTrue((self.workspace / ".hypha" / "src" / "bootstrap" / "docs" / "plan.md").is_file())
        rejected = self.cli("bootstrap", "--apply", str(plan_path), ok=False)
        self.assertIn("仅支持空任务与知识图", rejected.stderr)

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
        self.assertIn("know/oauth", self.cli("route", "oauth").stdout)
        self.cli("lint")

    def test_search_uses_comma_keywords_and_file_scope(self):
        self.cli("init")
        evidence = self.workspace / "auth-source.md"
        evidence.write_text("Session expiry can require authentication.\n", encoding="utf-8")
        self.cli("ingest", str(evidence))
        active = self.workspace / ".hypha" / ".drafts" / "auth.md"
        active.write_text(
            "---\nkind: know\nclaim_kind: inference\nstatus: active\n"
            "when: 用户无法进入系统\ntriggers: [认证, login]\n"
            "anchors: [src/auth-source.md]\n"
            "inference: 会话失效可能需要重新认证\n---\n"
            "# Authentication recovery\n\n会话失效时重新获取凭据。\n",
            encoding="utf-8",
        )
        self.cli("apply", str(active))
        note = self.workspace / ".hypha" / ".drafts" / "private-note.md"
        note.write_text("---\nkind: know\nclaim_kind: note\n---\n# Note\n\n认证不应被默认搜索。\n", encoding="utf-8")
        self.cli("apply", str(note))

        output = self.cli("search", "登录失败,认证,会话").stdout
        self.assertIn(".hypha/know/authentication-recovery.md", output)
        self.assertIn("会话失效时重新获取凭据", output)
        self.assertNotIn("private-note", output)
        self.assertIn("authentication-recovery", self.cli("search", "无命中，认证").stdout)

        source = self.workspace / "docs" / "runbook.txt"
        source.parent.mkdir()
        source.write_text("Rotate the session cookie after authentication failure.\n", encoding="utf-8")
        scoped = self.cli("search", "登录失败,session", "--file", "docs", "--limit", "1").stdout
        self.assertEqual("docs/runbook.txt:1: Rotate the session cookie after authentication failure.\n", scoped)
        rejected = self.cli("search", "session", "--file", "../outside", ok=False)
        self.assertIn("必须位于 workspace 内", rejected.stderr)
        empty = self.cli("search", ",，,", ok=False)
        self.assertIn("至少需要一个非空关键词", empty.stderr)

    def test_agreement_draft_publishes_without_duplicating_agents(self):
        self.cli("init")
        self.assertFalse((self.workspace / ".hypha" / "agreements").exists())
        self.cli("add", "Long migration")
        draft = self.workspace / ".hypha" / ".drafts" / "offline-rationale.md"
        draft.write_text(
            "---\nkind: know\nclaim_kind: agreement\nknowledge_kind: rationale\nscope: project\n"
            "authority: user_explicit\nstatus: active\nwhen: Changing deployment or runtime architecture\n"
            "triggers: [offline, deployment]\nagreement_quote: The product must work without network access.\n"
            "affects: [0001]\nreview_when: The supported environment gains guaranteed network access\n---\n"
            "# Offline architecture rationale\n\nOffline operation is a product boundary, not merely a deployment convenience.\n",
            encoding="utf-8",
        )
        text = draft.read_text(encoding="utf-8")
        self.assertIn("claim_kind: agreement", text)
        self.assertIn("knowledge_kind: rationale", text)
        self.assertEqual(0, json.loads(self.cli("list", "--type", "knowledge", "--json").stdout)["counts"]["knowledge"])
        self.cli("apply", str(draft))
        payload = json.loads(self.cli("list", "--type", "knowledge", "--json").stdout)
        self.assertEqual("user_explicit", payload["nodes"][0]["authority"])
        self.assertEqual("project", payload["nodes"][0]["scope"])

        (self.workspace / "AGENTS.md").write_text("# Rules\n\n- Use Git for commits.\n", encoding="utf-8")
        duplicate = self.workspace / ".hypha" / ".drafts" / "git-rule.md"
        duplicate.write_text(
            "---\nkind: know\nclaim_kind: agreement\nknowledge_kind: constraint\nscope: project\n"
            "authority: user_confirmed\nwhen: Committing\ntriggers: [git]\n"
            "agreement_quote: Use Git for commits.\n---\n# Git rule\n\nDuplicate operating rule.\n",
            encoding="utf-8",
        )
        rejected = self.cli("apply", str(duplicate), ok=False)
        self.assertIn("已存在于 AGENTS.md", rejected.stderr)

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

    def test_node_observation_times_use_first_and_last_node_events(self):
        module = runpy.run_path(str(CLI[1]))
        events = [
            {"kind": "intent", "id": "0001", "recorded_at": "2026-08-29T02:00:00Z"},
            {"kind": "session", "id": "workspace", "recorded_at": "2026-08-29T02:30:00Z"},
            {"kind": "intent", "id": "0001", "recorded_at": "2026-08-29T01:00:00Z"},
            {"kind": "intent", "id": "0001", "recorded_at": "2026-08-29T03:00:00Z"},
        ]
        self.assertEqual(module["node_observation_times"](events), {
            ("intent", "0001"): {
                "created_at": "2026-08-29T01:00:00Z",
                "updated_at": "2026-08-29T03:00:00Z",
            },
        })

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
        self.assertIn('"progress": 0', html)
        self.assertIn('"status": "in_progress"', html)
        self.assertIn('"path": "intent/', html)
        self.assertIn('"summary":', html)
        self.assertIn('"markdown":', html)
        self.assertIn('"metadata":', html)
        self.assertIn('"generatedAt":', html)
        self.assertIn('"created_at":', html)
        self.assertIn('"updated_at":', html)
        task = next((self.workspace / ".hypha" / "intent").glob("0001-*.md"))
        task.write_text(task.read_text(encoding="utf-8").replace("# deliverable", "# deliverable changed"), encoding="utf-8")
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
        ready_output = self.cli("ready").stdout
        self.assertIn("运行中（续接候选）", ready_output)
        self.assertIn("0001 40%", ready_output)
        self.assertIn("kind=handoff", self.cli("drafts").stdout)
        self.assertIn("progress: 40", self.cli("show", "0001").stdout)
        lint = self.cli("lint", "--audit")
        self.assertEqual("", lint.stderr)
        self.cli("close")
        self.assertNotIn("上次会话可能未收尾", self.cli("boot", "oauth").stdout)

    def test_dismiss_suppresses_repeated_candidate(self):
        self.cli("init")
        self.cli("add", "OAuth provider")
        draft = self.workspace / ".hypha" / ".drafts" / "provider.md"
        draft.write_text("---\nkind: know\nclaim_kind: inference\nwhen: Choosing OAuth provider\nanchors: [src/provider.md]\ninference: provider evidence\ntriggers: [oauth, provider]\n---\n# OAuth provider decision\n", encoding="utf-8")
        self.cli("apply", str(draft))
        output = self.cli("lint", "--audit").stdout
        match = re.search(r"\[([0-9a-f]{12})\] 0001", output)
        self.assertIsNotNone(match)
        self.cli("dismiss", match.group(1))
        self.assertNotIn(match.group(1), self.cli("lint", "--audit").stdout)

    def test_semantic_follow_ups_and_resolution_guards(self):
        self.cli("init")
        self.cli("add", "OAuth provider")
        source = self.workspace / "provider.md"
        source.write_text("# Provider\n\nUse short-lived access tokens.\n", encoding="utf-8")
        ingest = self.cli("ingest", str(source)).stdout
        self.assertIn("AGENT FOLLOW-UP", ingest)
        self.assertIn("support, refinement, contradiction", ingest)

        draft = self.workspace / ".hypha" / ".drafts" / "provider.md"
        draft.write_text(
            "---\nkind: know\nclaim_kind: inference\nwhen: Choosing OAuth provider\n"
            "anchors: [src/provider.md]\ninference: provider evidence\ntriggers: [oauth, provider]\n---\n"
            "# OAuth provider decision\n",
            encoding="utf-8",
        )
        self.cli("apply", str(draft))
        audit = self.cli("lint", "--audit").stdout
        self.assertIn("AGENT FOLLOW-UP", audit)
        candidate = re.search(r"\[([0-9a-f]{12})\] 0001", audit).group(1)
        deferred = self.cli("defer", candidate).stdout
        self.assertIn("仍会在后续 audit 中显示", deferred)
        self.assertIn(candidate, self.cli("lint", "--audit").stdout)
        rejected = self.cli("dismiss", "deadbeefdead", ok=False)
        self.assertIn("不是当前 lint --audit 候选", rejected.stderr)

    def test_session_completion_scope_and_migrate_protocol(self):
        self.cli("init")
        self.cli("add", "deliver")
        self.cli("boot")
        self.cli("done", "0001")
        close = self.cli("close").stdout
        self.assertIn("completion candidates since latest boot: 0001", close)
        self.assertIn("AGENT FOLLOW-UP", close)
        self.assertNotIn("上次会话可能未收尾", self.cli("boot").stdout)
        self.assertIn("没有检测到需要迁移", self.cli("migrate").stdout)

        agreements = self.workspace / ".hypha" / "agreements"
        agreements.mkdir()
        (agreements / "legacy.md").write_text("# Legacy rule\n", encoding="utf-8")
        migration = self.cli("migrate").stdout
        self.assertIn("AGENT FOLLOW-UP", migration)
        self.assertIn("legacy file: agreements/legacy.md", migration)

    def test_route_explains_components_and_trigger_overlap_warns_only(self):
        self.cli("init")
        self.cli("add", "OAuth work")
        for name in ("first", "second"):
            draft = self.workspace / ".hypha" / ".drafts" / f"{name}.md"
            draft.write_text(
                f"---\nkind: know\nclaim_kind: inference\nwhen: OAuth fails\n"
                f"anchors: [src/{name}.md]\ninference: x\ntriggers: [oauth]\n---\n# {name} OAuth\n",
                encoding="utf-8",
            )
            (self.workspace / ".hypha" / "src" / f"{name}.md").write_text("evidence\n", encoding="utf-8")
            self.cli("apply", str(draft))
        routed = self.cli("route", "oauth").stdout
        self.assertIn("trigger_hits=oauth", routed)
        self.assertIn("title_hits=oauth", routed)
        lint = self.cli("lint").stdout
        self.assertIn("警告：共享 trigger 候选", lint)
        self.assertIn("lint 通过", lint)

    def test_command_surface_is_unambiguous_and_progress_starts_work(self):
        self.cli("init")
        self.cli("add", "implementation")
        progress = self.cli("progress", "0001", "100").stdout
        self.assertIn("已更新 0001: in_progress", progress)
        self.assertIn("100% 只表示叶子工作量完成", progress)
        self.assertIn("status: in_progress", self.cli("show", "0001").stdout)

        help_text = self.cli("--help").stdout
        for command in ("search", "route", "ready", "dismiss", "defer"):
            self.assertIn(command, help_text)
        for removed in ("ask", "why", "next", "resolve", "sync"):
            self.assertNotRegex(help_text, rf"(?m)^    {removed}\s")
        rejected = subprocess.run(
            CLI + ["--workspace", str(self.workspace), "--global", "add", "global task"],
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("任务治理必须使用 workspace-local", rejected.stderr)

if __name__ == "__main__":
    unittest.main()
