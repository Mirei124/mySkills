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
MODULE = runpy.run_path(str(SCRIPT))


class RecoveryUsabilityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.home = self.workspace / ".hypha"
        self.cli("init")

    def cli(self, *args, input=None, code=0):
        result = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(self.workspace), *args],
                                input=input, text=True, capture_output=True, check=False)
        self.assertEqual(code, result.returncode, result.stdout + result.stderr)
        return result.stdout

    def seed(self, key, title, task=None, when="Applies when choosing implementation", body="", **fields):
        node = {"title": title, "authority": "agent_inference", "claim_kind": "inference", "status": "active",
                "inference": title, "observations": ["Scoped observation; load behavior untested"],
                "when": when, "affects": [task] if task else [], "_body": f"\n# {title}\n\n{body}\n", **fields}
        MODULE["write_node"](self.home / f"know/{key}.md", node, atomic=True)

    def snapshot(self):
        return {str(path.relative_to(self.home)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.home.rglob("*") if path.is_file()}

    def revision(self, key):
        return re.search(r"revision: (\w+)", self.cli("show", key)).group(1)

    def test_ranking_uses_title_scope_and_common_term_discount(self):
        for index in range(20): self.seed(f"noise-{index}", f"Firefox check {index}")
        self.seed("pdf", "PDF-only entry", when="Firefox PDF ingestion")
        self.seed("legacy", "Legacy check", triggers=["and", "applies", "firefox"])
        output = self.cli("advanced", "explain", "Firefox PDF")
        self.assertTrue(output.startswith("know/pdf\t"), output)
        self.assertEqual("", self.cli("advanced", "explain", "and applies when"))
        terms = MODULE["knowledge_triggers"]({"title": "Zebra target", "when": "a and applies alpha beta gamma delta epsilon theta iota kappa lambda mu nu"})
        self.assertEqual(["zebra", "target"], terms[:2])
        self.assertNotIn("applies", terms)

    def test_chinese_phrase_matches_longer_unsegmented_scope(self):
        self.seed("pdf", "网页入口仅直链PDF", when="处理网页入口时禁止抓取正文")
        self.seed("quality", "详细概览局部信息不足待优化", when="收到缺失案例再重启")
        self.assertIn("know/pdf", self.cli("advanced", "explain", "继续网页入口功能"))
        self.assertIn("know/quality", self.cli("advanced", "explain", "概览信息不足"))

    def test_hydrate_focuses_task_and_reads_required_bodies_without_writes(self):
        self.cli("task", "create", "PDF entry", "--acceptance", "Direct PDF ingestion")
        self.cli("task", "create", "Unrelated deployment", "--root", "--acceptance", "Deployment")
        self.cli("task", "start", "0001")
        self.cli("task", "start", "0002")
        self.seed("pdf", "Direct entry constraint", "0001", body="Only direct PDF links are allowed.")
        self.seed("defer", "Detail quality deferral", "0001", body="Wait for missing-detail examples.")
        for index in range(16): self.seed(f"noise-{index}", f"Deployment check {index}", "0002")
        before = self.snapshot()
        output = self.cli("context", "resume", "PDF entry", "--hydrate")
        self.assertIn("Only direct PDF links are allowed.", output)
        self.assertIn("Wait for missing-detail examples.", output)
        self.assertIn("Remaining: Direct PDF ingestion", output)
        self.assertIn("load behavior untested", output)
        self.assertNotIn("know/noise", output)
        self.assertNotIn("Recovery is not complete from this index", output)
        self.assertEqual(before, self.snapshot())
        self.assertIn("know/defer", self.cli("context", "resume", "--task", "0001", "--hydrate"))
        self.cli("context", "resume", "--task", "9999", "--hydrate", code=2)

    def test_hydration_reports_budget_omissions_and_task_ambiguity(self):
        self.cli("task", "create", "PDF entry", "--acceptance", "Direct PDF ingestion")
        self.seed("large", "Long constraint", "0001", body="Do not lose this limit. " * 1000)
        self.seed("small", "Small constraint", "0001", body="Offline only.")
        output = self.cli("context", "resume", "--hydrate", "--max-chars", "2500")
        self.assertIn("Offline only.", output)
        self.assertIn("know/large: required; body budget; hypha show know/large", output)
        self.assertNotIn("Do not lose this limit.", output)
        self.cli("context", "resume", "--hydrate", "--max-chars", "0", code=2)
        self.cli("task", "create", "Other", "--root", "--acceptance", "Other")
        self.seed("other", "Unrelated constraint", "0002")
        ambiguous = self.cli("context", "resume", "--hydrate")
        self.assertIn("No unique task selected", ambiguous)
        self.assertNotIn("know/small", ambiguous)
        self.assertNotIn("know/other", ambiguous)

    def test_many_generic_matches_do_not_override_a_matching_task_title(self):
        self.cli("task", "create", "PDF entry", "--acceptance", "PDF")
        self.cli("task", "create", "Other project", "--root", "--acceptance", "Other")
        self.seed("pdf", "Direct PDF constraint", "0001")
        for index in range(20): self.seed(f"noise-{index}", f"Firefox check {index}", "0002")
        output = self.cli("context", "resume", "PDF Firefox")
        self.assertIn("Selected task: 0001", output)
        self.assertIn("Selected task: 0001", self.cli("context", "resume", "继续任务0001"))
        ambiguous = self.cli("context", "resume", "0001 and 0002", "--hydrate")
        self.assertIn("No unique task selected", ambiguous)

    def test_hydration_follows_replacements_from_task_body_links(self):
        self.cli("task", "create", "PDF entry", "--acceptance", "PDF")
        self.seed("old", "Old constraint", status="superseded", superseded_by="know/current")
        self.seed("current", "Current constraint", body="Preserve the unresolved failure.")
        body = self.workspace / "evidence.md"
        body.write_text("Historical decision: [[know/old]].\n", encoding="utf-8")
        self.cli("task", "edit", "0001", "--section", "Evidence", "--body-file", str(body))
        output = self.cli("context", "resume", "--hydrate")
        self.assertIn("Preserve the unresolved failure.", output)
        self.assertIn("- know/old: superseded", output)

    def test_archive_restore_preserves_evidence_links_and_history(self):
        self.cli("task", "create", "PDF entry", "--acceptance", "Ingestion")
        self.cli("record", "Browser pass", "--task", "0001", "--evidence", "One batch passed; load untested")
        key = "know/browser-pass"
        path = self.home / f"{key}.md"
        original = MODULE["read_node"](path)
        task_path = next((self.home / "intent").glob("*.md"))
        task_before = task_path.read_bytes()
        rev = self.revision(key)
        self.cli("knowledge", "archive", key, "--reason", "Covered by batch summary", "--revision", rev)
        archived = MODULE["read_node"](path)
        for field in ("_body", "observations", "affects", "authority"):
            self.assertEqual(original[field], archived[field])
        self.assertEqual(task_before, task_path.read_bytes())
        self.assertEqual("No matches.\n", self.cli("search", "Browser pass", "--type", "knowledge"))
        self.assertIn(key, self.cli("search", "Browser pass", "--status", "archived", "--type", "knowledge"))
        self.assertIn(key, self.cli("list", "--type", "knowledge", "--status", "archived"))
        self.assertIn("status: archived", self.cli("show", key))
        self.assertIn(f"- {key}: archived", self.cli("context", "resume", "--task", "0001", "--hydrate"))
        self.cli("record", "append", key, "--evidence", "Not active", code=2)
        self.cli("knowledge", "restore", key, "--revision", rev, code=2)
        self.cli("knowledge", "restore", key)
        self.assertEqual("active", MODULE["read_node"](path)["status"])
        self.assertIn(key, self.cli("context", "resume"))
        events = "".join(path.read_text() for path in (self.home / "snapshots").glob("*.jsonl"))
        self.assertIn("Covered by batch summary", events)
        self.cli("check", "--strict")

    def test_restore_superseded_record_does_not_reactivate_it(self):
        self.cli("record", "Old decision", "--when", "PDF", "--evidence", "Old scoped evidence")
        key = "know/old-decision"
        self.cli("record", "New decision", "--supersedes", key, "--revision", self.revision(key),
                 "--because", "Changed evidence", "--evidence", "New evidence", "--when", "PDF")
        self.cli("knowledge", "archive", key, "--reason", "Historical")
        self.cli("knowledge", "restore", key)
        output = self.cli("show", key)
        self.assertIn("status: superseded", output)
        self.assertIn("superseded_by: know/new-decision", output)
        self.assertNotIn(key, self.cli("advanced", "explain", "PDF"))

    def test_archive_write_failure_rolls_back(self):
        self.cli("record", "Decision", "--when", "PDF", "--evidence", "Evidence")
        before = self.snapshot()
        operation = MODULE["knowledge_lifecycle"]
        real_sync = operation.__globals__["sync"]
        def fail_after_sync(*args, **kwargs):
            real_sync(*args, **kwargs)
            raise OSError("Injected failure")
        args = argparse.Namespace(workspace=str(self.workspace), workspace_explicit=True, global_store=False,
                                  command="knowledge", action="archive", target="know/decision", reason="Historical", revision=None)
        with mock.patch.dict(operation.__globals__, {"sync": fail_after_sync}), self.assertRaises(OSError):
            operation(args)
        self.assertEqual(before, self.snapshot())

    def test_quote_file_and_stdin_preserve_exact_text_without_shell_execution(self):
        marker = self.workspace / "must-not-exist"
        quote = f'网页入口仅直链 PDF；`$(touch {marker})` "原样"\n概览优化等待缺失案例。\n'
        path = self.workspace / "quote.txt"
        path.write_text(quote, encoding="utf-8")
        for title, source, input_value in (("File decision", str(path), None), ("Stdin decision", "-", quote)):
            self.cli("knowledge", "create", title, "--origin", "user", "--when", "PDF entry", "--quote-file", source, input=input_value)
            node = MODULE["read_node"](self.home / "know" / f"{title.lower().replace(' ', '-')}.md")
            self.assertEqual(quote, node["agreement_quote"])
        self.assertFalse(marker.exists())

    def test_mixed_file_and_inline_inputs_preserve_source_pairing_and_evidence_order(self):
        source = self.workspace / "source.txt"
        source.write_text("First claim.\n第二条原话。\n", encoding="utf-8")
        quote = self.workspace / "quote.txt"
        quote.write_text("第二条原话。", encoding="utf-8")
        self.cli("knowledge", "create", "Source claims", "--origin", "repository", "--when", "PDF",
                 "--source", str(source), "--quote", "First claim.", "--source", str(source), "--quote-file", str(quote))
        evidence = MODULE["read_node"](self.home / "know/source-claims.md")["evidence"]
        self.assertEqual(["First claim.", "第二条原话。"], [item["quote"] for item in evidence])
        self.cli("record", "Observed", "--when", "PDF", "--evidence", "First", "--evidence-file", "-",
                 "--user-quote-file", str(quote), input="第二条\n保留换行\n")
        node = MODULE["read_node"](self.home / "know/observed.md")
        self.assertEqual(["First", "第二条\n保留换行\n"], node["observations"])
        self.assertEqual(["第二条原话。"], node["user_observations"])

    def test_invalid_file_inputs_do_not_write_and_exact_quotes_still_validate(self):
        before = self.snapshot()
        self.cli("record", "Empty", "--when", "PDF", code=2)
        self.cli("record", "Empty", "--when", "PDF", "--evidence-file", "-", input=" \n", code=2)
        self.cli("record", "Missing", "--when", "PDF", "--evidence-file", str(self.workspace / "missing"), code=2)
        self.cli("record", "Ambiguous", "--when", "PDF", "--evidence-file", "-", "--user-quote-file", "-", input="quote", code=2)
        source = self.workspace / "source.txt"
        source.write_text("Actual statement", encoding="utf-8")
        self.cli("knowledge", "create", "Invalid", "--when", "PDF", "--origin", "repository",
                 "--source", str(source), "--quote-file", "-", input="Not in source", code=2)
        self.assertEqual(before, self.snapshot())

    def test_check_info_is_quiet_by_default_and_failure_codes_are_stable(self):
        for index in range(3): self.seed(f"noise-{index}", "Firefox check", triggers=["firefox", "and", "applies"])
        normal = self.cli("check")
        self.assertNotIn("Shared trigger candidate", normal)
        self.assertIn("Info: unmanaged writes", normal)
        self.assertIn("hypha knowledge edit know/noise-0 --draft", normal)
        verbose = self.cli("check", "--verbose", "--strict")
        self.assertIn("Info: Shared trigger candidate: firefox", verbose)
        self.assertNotIn("candidate: and", verbose)
        self.cli("task", "create", "Missing acceptance")
        strict = json.loads(self.cli("check", "--strict", "--json", code=1))
        self.assertEqual("validation_failed", strict["error"]["code"])
        self.assertIn("task edit 0001 --section Acceptance --body-file FILE", strict["error"]["output"])
        path = self.home / "know/noise-0.md"
        path.write_text(path.read_text().replace("status: active", "status: invalid"))
        failure = json.loads(self.cli("check", "--json", code=1))
        self.assertIn("invalid knowledge status", failure["error"]["output"])
        self.cli("check", "--limit", "0", code=2)


if __name__ == "__main__":
    unittest.main()
