#!/usr/bin/env python3
"""Hypha: local task and knowledge graph CLI (stdlib-only MVP)."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid
from collections import defaultdict
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no advisory flock.
    fcntl = None

TASK_STATUSES = {"todo", "in_progress", "blocked", "done", "dropped"}
KNOWLEDGE_STATUSES = {"active", "superseded"}
CLAIM_KINDS = {"sourced", "inference", "agreement", "note"}
KNOWLEDGE_KINDS = {"rationale", "constraint", "decision", "consensus", "invariant", "non_goal", "definition", "lesson", "assumption", "synthesis"}
KNOWLEDGE_SCOPES = {"project", "subsystem", "task"}
KNOWLEDGE_AUTHORITIES = {"user_explicit", "user_confirmed", "repository", "external_source", "agent_inference"}
GLOBAL_COMMANDS = {"init", "apply", "lint", "dismiss", "defer", "list", "drafts", "route", "show", "ingest", "search", "migrate", "view"}
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
WORD = re.compile(r"[\w-]+", re.UNICODE)
BOOTSTRAP_EXCLUDED = {".git", ".hypha", "node_modules", "dist", "build", "target", "vendor", "__pycache__", ".venv"}
BOOTSTRAP_TEXT_SUFFIXES = {".md", ".txt", ".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go", ".java", ".kt", ".rb", ".php", ".cs", ".c", ".h", ".cpp", ".hpp"}
BOOTSTRAP_BACKGROUND_NAMES = {"readme.md", "contributing.md", "architecture.md", "design.md", "spec.md"}
ROUTE_TRIGGER_WEIGHT = 100
ROUTE_TITLE_WEIGHT = 10
ROUTE_OPEN_TASK_TIE_BREAK = 1


def agent_follow_up(purpose: str, steps: list[str], context: list[str] | None = None) -> None:
    """Print a stable hand-off for semantic work the deterministic CLI cannot do."""
    print("AGENT FOLLOW-UP (semantic judgment required; do not treat candidates as facts)")
    print(f"Purpose: {purpose}")
    if context:
        print("Context:")
        for item in context:
            print(f"- {item}")
    print("Instructions:")
    for index, step in enumerate(steps, 1):
        print(f"{index}. {step}")


def root(args: argparse.Namespace) -> Path:
    if getattr(args, "global_store", False):
        return Path.home() / ".hypha"
    return Path(args.workspace).resolve() / ".hypha"


def parse_value(value: str):
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        return [parse_value(part) for part in value[1:-1].split(",") if part.strip()]
    # IDs are fixed-width strings: YAML-style integer coercion must not turn
    # 0007 into 7 (the same applies to IDs inside inline relationship lists).
    if value.isdigit() and (value == "0" or not value.startswith("0")):
        return int(value)
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value


def parse_frontmatter(front: str) -> dict:
    """Parse the intentionally small YAML subset used by Hypha nodes."""
    lines, data, i = front.splitlines(), {}, 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1; continue
        if line.startswith((" ", "\t")) or ":" not in line:
            raise ValueError(f"无效 frontmatter 行：{line}")
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value:
            data[key] = parse_value(value); i += 1; continue
        i += 1; items = []
        while i < len(lines) and (lines[i].startswith("  ") or not lines[i].strip()):
            if not lines[i].strip(): i += 1; continue
            item = lines[i].strip()
            if not item.startswith("-"):
                raise ValueError(f"无效 frontmatter 缩进行：{lines[i]}")
            item = item[1:].strip()
            if ":" not in item:
                items.append(parse_value(item)); i += 1; continue
            obj = {}
            k, v = item.split(":", 1); obj[k.strip()] = parse_value(v)
            i += 1
            while i < len(lines) and lines[i].startswith("    "):
                k, v = lines[i].strip().split(":", 1); obj[k.strip()] = parse_value(v); i += 1
            items.append(obj)
        data[key] = items
    return data


def read_node(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: 缺少 frontmatter")
    _, front, body = text.split("---\n", 2)
    data = parse_frontmatter(front)
    data["_path"] = path
    data["_body"] = body
    data["title"] = next((x[2:].strip() for x in body.splitlines() if x.startswith("# ")), path.stem)
    return data


def quote_value(value) -> str:
    text = str(value)
    return json.dumps(text, ensure_ascii=False) if any(x in text for x in ":#[]{}\n,\"") else text


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        with contextlib.suppress(FileNotFoundError): os.unlink(temp)


def write_node(path: Path, node: dict, atomic: bool = False) -> None:
    keys = [k for k in node if not k.startswith("_") and k != "title"]
    front = []
    for key in keys:
        value = node[key]
        if isinstance(value, list) and value and isinstance(value[0], dict):
            front.append(f"{key}:")
            for entry in value:
                fields = list(entry)
                front.append(f"  - {fields[0]}: {quote_value(entry[fields[0]])}")
                front.extend(f"    {field}: {quote_value(entry[field])}" for field in fields[1:])
        elif isinstance(value, list): front.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        else: front.append(f"{key}: {quote_value(value)}")
    text = "---\n" + "\n".join(front) + "\n---\n" + node["_body"]
    atomic_write(path, text) if atomic else path.write_text(text, encoding="utf-8")


def scan(home: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    tasks, knowledge = {}, {}
    for folder, sink in ((home / "intent", tasks), (home / "know", knowledge)):
        if not folder.exists():
            continue
        for path in folder.rglob("*.md"):
            node = read_node(path)
            key = str(path.relative_to(home)).removesuffix(".md")
            if sink is tasks:
                sink[str(node.get("id", ""))] = node
            else:
                sink[key] = node
    return tasks, knowledge


@contextlib.contextmanager
def locked(home: Path):
    """Advisory local lock. All public commands take it before scanning/writing."""
    home.mkdir(parents=True, exist_ok=True)
    fd = os.open(home / "lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def links(node: dict) -> list[str]:
    return [item.strip().removesuffix(".md") for item in WIKILINK.findall(node.get("_body", ""))]


def knowledge_triggers(node: dict) -> list[str]:
    """The only machine-routing field; derive a conservative default if absent."""
    explicit = node.get("triggers")
    if explicit:
        return [str(item).casefold() for item in explicit]
    return sorted({item.casefold() for item in WORD.findall(node["title"] + " " + str(node.get("when", "")))})[:12]


def intent_link_id(link: str) -> str | None:
    if not link.startswith("intent/"):
        return None
    match = re.match(r"intent/(\d{4})(?:[-/].*)?$", link)
    return match.group(1) if match else ""


def graph(tasks: dict, knowledge: dict) -> dict:
    backlinks, premises, children, unlocks = (defaultdict(set) for _ in range(4))
    redlinks = set()
    for path, node in knowledge.items():
        for link in links(node):
            if link in knowledge: backlinks[link].add(path)
            elif link.startswith("know/"): redlinks.add(link)
        for task_id in node.get("affects", []):
            if str(task_id) in tasks: premises[str(task_id)].add(path)
    for task_id, node in tasks.items():
        if node.get("parent") in tasks: children[str(node["parent"])].add(task_id)
        for dep in node.get("depends_on", []):
            if str(dep) in tasks: unlocks[str(dep)].add(task_id)
        for link in links(node):
            if link in knowledge: premises[task_id].add(link)
            elif link.startswith("know/"): redlinks.add(link)
    return {"backlinks": backlinks, "premises": premises, "children": children, "unlocks": unlocks, "redlinks": redlinks}


def task_progresses(tasks: dict) -> dict[str, int | None]:
    """Return leaf-owned progress; ancestors average all non-dropped descendant leaves."""
    children = defaultdict(list)
    for task_id, node in tasks.items():
        parent = str(node["parent"]) if node.get("parent") is not None else None
        if parent in tasks: children[parent].append(task_id)
    for task_ids in children.values(): task_ids.sort()
    memo: dict[str, tuple[int, int]] = {}
    visiting = set()
    def totals(task_id: str) -> tuple[int, int]:
        if task_id in memo: return memo[task_id]
        if task_id in visiting: raise ValueError(f"任务 parent 成环：{task_id}")
        visiting.add(task_id)
        node = tasks[task_id]
        if node.get("status") == "dropped":
            result = (0, 0)
        elif not children[task_id]:
            value = 100 if node.get("status") == "done" else int(node.get("progress", 0))
            result = (max(0, min(100, value)), 1)
        else:
            child_totals = [totals(child) for child in children[task_id]]
            result = (sum(total for total, _ in child_totals), sum(count for _, count in child_totals))
        visiting.remove(task_id)
        memo[task_id] = result
        return result
    progresses = {}
    for task_id in sorted(tasks):
        total, count = totals(task_id)
        progresses[task_id] = round(total / count) if count else None
    return progresses


def reopen_incomplete_done_tasks(tasks: dict) -> set[str]:
    """Keep done consistent when structure or authoritative leaf progress changes."""
    progresses = task_progresses(tasks)
    changed = set()
    for task_id, node in tasks.items():
        if node.get("status") == "done" and progresses[task_id] != 100:
            node["status"] = "in_progress"
            node.pop("progress", None)
            changed.add(task_id)
    return changed


def anchor_text(home: Path, anchor: str) -> str | None:
    file_name, marker, fragment = anchor.partition("#")
    path = home / file_name
    if not path.is_file(): return None
    text = path.read_text(encoding="utf-8")
    if not marker: return text
    headings = list(re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", text))
    for index, heading in enumerate(headings):
        slug = re.sub(r"[^\w\s-]", "", heading.group(1).casefold()).replace(" ", "-")
        if slug == fragment.casefold():
            return text[heading.end():headings[index + 1].start() if index + 1 < len(headings) else len(text)]
    return None


def cycle_errors(tasks: dict) -> list[str]:
    state, errors = {}, []
    def visit(task_id: str, stack: list[str]):
        state[task_id] = 1
        node = tasks[task_id]
        targets = ([str(node["parent"])] if node.get("parent") else []) + [str(x) for x in node.get("depends_on", [])]
        for target in targets:
            if target not in tasks: continue
            if state.get(target) == 1: errors.append("任务关系成环：" + " -> ".join(stack + [task_id, target]))
            elif not state.get(target): visit(target, stack + [task_id])
        state[task_id] = 2
    for task_id in tasks:
        if not state.get(task_id): visit(task_id, [])
    return errors


def validate(home: Path, tasks: dict, knowledge: dict) -> list[str]:
    errors, agents_text = [], None
    for task_id, node in tasks.items():
        if not node.get("id") or not node.get("status"): errors.append(f"{task_id}: 缺 id 或 status")
        if node.get("status") not in TASK_STATUSES: errors.append(f"{task_id}: 无效状态")
        if node.get("status") == "blocked" and not node.get("blocked_reason"): errors.append(f"{task_id}: blocked 缺 blocked_reason")
        if node.get("parent") and str(node["parent"]) not in tasks: errors.append(f"{task_id}: 悬空 parent {node['parent']}")
        for dep in node.get("depends_on", []):
            if str(dep) not in tasks: errors.append(f"{task_id}: 悬空依赖 {dep}")
        for link in links(node):
            linked_id = intent_link_id(link)
            if linked_id == "" or (linked_id and linked_id not in tasks):
                errors.append(f"{task_id}: 悬空任务正文链接 {link}")
    errors.extend(cycle_errors(tasks))
    for path, node in knowledge.items():
        kind = node.get("claim_kind")
        if kind not in CLAIM_KINDS: errors.append(f"{path}: 无效或缺少 claim_kind")
        if node.get("status", "active") not in KNOWLEDGE_STATUSES: errors.append(f"{path}: 无效知识状态")
        if node.get("status") == "superseded" and not node.get("superseded_by"): errors.append(f"{path}: superseded 缺 superseded_by")
        anchors = node.get("anchors", [])
        if kind == "sourced" and (not anchors or not node.get("evidence")): errors.append(f"{path}: sourced 缺 anchor 或 evidence")
        if kind == "inference" and (not anchors or not node.get("inference")): errors.append(f"{path}: inference 缺 inference 或来源 anchor")
        if kind == "agreement":
            if node.get("authority") not in {"user_explicit", "user_confirmed"}: errors.append(f"{path}: agreement 必须标明 user_explicit 或 user_confirmed authority")
            if not node.get("agreement_quote"): errors.append(f"{path}: agreement 缺 agreement_quote")
            if node.get("knowledge_kind") not in KNOWLEDGE_KINDS: errors.append(f"{path}: agreement 缺有效 knowledge_kind")
            if node.get("scope") not in KNOWLEDGE_SCOPES: errors.append(f"{path}: agreement 缺有效 scope")
            if node.get("agreement_quote"):
                if agents_text is None:
                    documents = []
                    for directory, names, files in os.walk(home.parent):
                        names[:] = [name for name in names if name not in BOOTSTRAP_EXCLUDED and not name.startswith(".")]
                        if "AGENTS.md" in files:
                            try: documents.append((Path(directory) / "AGENTS.md").read_text(encoding="utf-8"))
                            except OSError: pass
                    agents_text = "\n".join(documents)
                if str(node["agreement_quote"]).strip() in agents_text:
                    errors.append(f"{path}: agreement_quote 已存在于 AGENTS.md；Hypha 只保存缘由、范围、历史或失效条件")
        if node.get("knowledge_kind") is not None and node.get("knowledge_kind") not in KNOWLEDGE_KINDS:
            errors.append(f"{path}: 无效 knowledge_kind")
        if node.get("scope") is not None and node.get("scope") not in KNOWLEDGE_SCOPES: errors.append(f"{path}: 无效 scope")
        if node.get("authority") is not None and node.get("authority") not in KNOWLEDGE_AUTHORITIES: errors.append(f"{path}: 无效 authority")
        if kind != "note" and not node.get("when"): errors.append(f"{path}: 缺 when")
        for evidence in node.get("evidence", []):
            if not isinstance(evidence, dict) or not evidence.get("anchor") or not evidence.get("quote"):
                errors.append(f"{path}: 无效 evidence"); continue
            section = anchor_text(home, str(evidence["anchor"]))
            if section is None: errors.append(f"{path}: 证据 anchor 不存在：{evidence['anchor']}")
            elif str(evidence["quote"]) not in section: errors.append(f"{path}: quote 不在指定 anchor 段落中")
        for task_id in node.get("affects", []):
            if str(task_id) not in tasks: errors.append(f"{path}: 悬空 affects {task_id}")
    return errors


def bootstrap_ignore_patterns(workspace: Path) -> list[str]:
    path = workspace / ".hypha-bootstrapignore"
    if not path.is_file(): return []
    return [line.strip().removesuffix("/") for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def bootstrap_ignored(path: Path, patterns: list[str]) -> bool:
    text = path.as_posix()
    return any(text == pattern or text.startswith(pattern + "/") or fnmatch.fnmatch(text, pattern) for pattern in patterns)


def workspace_files(workspace: Path) -> list[Path]:
    """Return a bounded, deterministic inventory without relying on Git alone."""
    found, patterns = set(), bootstrap_ignore_patterns(workspace)
    try:
        result = subprocess.run(["git", "-C", str(workspace), "ls-files"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            found.update(Path(line) for line in result.stdout.splitlines() if line.strip())
    except OSError:
        pass
    for directory, names, files in os.walk(workspace):
        names[:] = sorted(name for name in names if name not in BOOTSTRAP_EXCLUDED and (not name.startswith(".") or name == ".github"))
        base = Path(directory)
        for name in sorted(files):
            relative = (base / name).relative_to(workspace)
            if not any(part in BOOTSTRAP_EXCLUDED for part in relative.parts) and not bootstrap_ignored(relative, patterns): found.add(relative)
            if len(found) >= 5000: break
        if len(found) >= 5000: break
    return sorted(path for path in found
                  if not bootstrap_ignored(path, patterns)
                  and not any(part in BOOTSTRAP_EXCLUDED or (part.startswith(".") and part != ".github") for part in path.parts))[:5000]


def bootstrap_signals(workspace: Path, paths: list[Path]) -> dict:
    completed, open_items, todos = [], [], []
    markdown = tests = 0
    for relative in paths:
        name = relative.name.casefold()
        if relative.suffix.casefold() == ".md": markdown += 1
        if "test" in name or "spec" in name or any(part.casefold() in {"test", "tests", "spec", "specs"} for part in relative.parts): tests += 1
        absolute = workspace / relative
        if relative.suffix.casefold() not in BOOTSTRAP_TEXT_SUFFIXES: continue
        try:
            if absolute.stat().st_size > 512_000: continue
            text = absolute.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            checked = re.match(r"^\s*[-*]\s*\[[xX]\]\s+(.+?)\s*$", line)
            unchecked = re.match(r"^\s*[-*]\s*\[ \]\s+(.+?)\s*$", line)
            todo = re.match(r"^\s*(?://|#|/\*|\*|<!--)\s*(?:TODO|FIXME)\b[:\s-]*(.+?)\s*(?:\*/|-->)?\s*$", line, re.IGNORECASE)
            item = {"path": relative.as_posix(), "line": line_no}
            if checked: completed.append({**item, "text": checked.group(1)})
            if unchecked: open_items.append({**item, "text": unchecked.group(1)})
            if todo and todo.group(1).strip(): todos.append({**item, "text": todo.group(1).strip()})
    return {"files": len(paths), "tests": tests, "markdown": markdown,
            "completed_items": completed[:100], "open_items": open_items[:100], "todo_items": todos[:100]}


def recent_git_work(workspace: Path, limit: int = 20) -> list[dict]:
    try:
        result = subprocess.run(["git", "-C", str(workspace), "log", f"-{limit}", "--format=%H%x09%s"],
                                capture_output=True, text=True, check=False)
    except OSError: return []
    if result.returncode: return []
    work = []
    for line in result.stdout.splitlines():
        commit, separator, subject = line.partition("\t")
        if separator and subject.strip(): work.append({"commit": commit[:12], "subject": subject.strip()})
    return work


def heading_slug(title: str) -> str:
    return re.sub(r"[^\w\s-]", "", title.casefold()).replace(" ", "-")


def background_candidates(workspace: Path, paths: list[Path]) -> list[dict]:
    candidates = []
    ranked = sorted((path for path in paths if path.suffix.casefold() == ".md" and
                     (path.name.casefold() in BOOTSTRAP_BACKGROUND_NAMES or any(part.casefold() in {"docs", "design_docs"} for part in path.parts))),
                    key=lambda path: (path.name.casefold() != "readme.md", len(path.parts), path.as_posix()))
    for relative in ranked:
        try: text = (workspace / relative).read_text(encoding="utf-8")
        except OSError: continue
        heading_match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
        title = heading_match.group(1).strip() if heading_match else relative.stem.replace("-", " ").replace("_", " ").title()
        start = heading_match.end() if heading_match else 0
        paragraph = next((part.strip() for part in re.split(r"\n\s*\n", text[start:])
                          if part.strip() and not part.lstrip().startswith(("#", "```", "<!--"))), "")
        quote = paragraph[:280]
        if not quote: continue
        triggers = sorted({word.casefold() for word in WORD.findall(title) if len(word) > 2})[:8]
        candidates.append({"key": f"background:{len(candidates) + 1}", "title": title, "source": relative.as_posix(),
                           "heading": title if heading_match else None, "quote": quote,
                           "summary": f"Repository background captured from {relative.as_posix()}.",
                           "when": f"Working on topics described by {title}", "triggers": triggers or [relative.stem.casefold()],
                           "affects": ["root"], "confidence": "unreviewed"})
        if len(candidates) >= 8: break
    return candidates


def build_bootstrap_plan(workspace: Path) -> dict:
    paths = workspace_files(workspace)
    signals = bootstrap_signals(workspace, paths)
    git_work = recent_git_work(workspace)
    explicit = [(item, "done", 100) for item in signals["completed_items"]]
    explicit += [(item, "todo", 0) for item in [*signals["open_items"], *signals["todo_items"]]]
    tasks = [{"key": "root", "title": f"Continue {workspace.name}", "parent": None, "status": "todo",
              "confidence": "unreviewed", "acceptance": ["Replace with the repository's actual long-running goal and acceptance criteria."],
              "evidence": [f"inventory: {signals['files']} files", f"recent Git commits: {len(git_work)}"]}]
    for index, (item, status, progress) in enumerate(explicit[:24], 1):
        location = f"{item['path']}:{item['line']}"
        tasks.append({"key": f"explicit:{index}", "title": item["text"], "parent": "root", "status": status,
                      "progress": progress, "confidence": "explicit-marker",
                      "acceptance": [f"Confirm the explicit repository item at {location}."],
                      "evidence": [f"{location}: {item['text']}"]})
    return {"schemaVersion": 2, "kind": "hypha-bootstrap-plan", "workspace": workspace.name, "reviewed": False,
            "warning": "Evidence bundle only. An agent must review task meaning, status, acceptance, progress, and knowledge before apply.",
            "inventory": {key: signals[key] for key in ("files", "tests", "markdown")},
            "observations": {"recent_git_work": git_work,
                             "completed_items": signals["completed_items"], "open_items": signals["open_items"],
                             "todo_items": signals["todo_items"]},
            "tasks": tasks, "knowledge": background_candidates(workspace, paths)}


def apply_bootstrap_plan(home: Path, plan: dict) -> list[str]:
    if plan.get("schemaVersion") != 2 or plan.get("kind") != "hypha-bootstrap-plan":
        raise ValueError("无效 bootstrap plan schema")
    if plan.get("reviewed") is not True:
        raise ValueError("bootstrap plan 必须由 agent 审阅并显式设置 reviewed: true")
    entries = plan.get("tasks")
    if not isinstance(entries, list) or not entries: raise ValueError("bootstrap plan 缺少 tasks")
    knowledge_entries = plan.get("knowledge", [])
    if not isinstance(knowledge_entries, list): raise TypeError("bootstrap plan knowledge 必须为数组")
    tasks, knowledge = prepare(home)
    if tasks or knowledge: raise ValueError("bootstrap --apply 仅支持空任务与知识图；已有节点请使用 add/apply")
    keys = [entry.get("key") for entry in entries if isinstance(entry, dict)]
    if len(keys) != len(entries) or len(set(keys)) != len(keys) or any(not key for key in keys):
        raise ValueError("bootstrap plan task key 必须唯一且非空")
    ids = {key: f"{index:04d}" for index, key in enumerate(keys, 1)}
    parent_keys = {entry.get("parent") for entry in entries if entry.get("parent") is not None}
    proposed = {}
    paths = []
    for entry in entries:
        status = entry.get("status", "todo")
        if status not in TASK_STATUSES: raise ValueError(f"bootstrap status 无效：{status}")
        parent_key = entry.get("parent")
        if parent_key is not None and parent_key not in ids: raise ValueError(f"bootstrap parent 不存在：{parent_key}")
        task_id = ids[entry["key"]]
        title = str(entry.get("title", "")).strip()
        if not title: raise ValueError("bootstrap task title 不能为空")
        acceptance = [str(item).strip() for item in entry.get("acceptance", []) if str(item).strip()]
        evidence = [str(item).strip() for item in entry.get("evidence", []) if str(item).strip()]
        if not acceptance or any(item.startswith("Replace with ") for item in acceptance):
            raise ValueError(f"bootstrap task {entry['key']} 必须有已审阅的具体验收条件")
        if not evidence: raise ValueError(f"bootstrap task {entry['key']} 必须有证据")
        slug = re.sub(r"[^\w\-]+", "-", title.lower()).strip("-") or task_id
        path = home / "intent" / f"{task_id}-{slug[:40]}.md"
        body = "\n# " + title + "\n\n## 验收\n\n" + "\n".join(f"- {item}" for item in acceptance)
        body += "\n\n## 证据\n\n" + "\n".join(f"- {item}" for item in evidence) + "\n"
        node = {"id": task_id, "status": status, "bootstrap_confidence": entry.get("confidence", "reviewed"),
                "_body": body, "_path": path, "title": title}
        if entry["key"] not in parent_keys:
            progress = entry.get("progress", 0)
            if not isinstance(progress, int) or not 0 <= progress <= 100: raise ValueError("bootstrap leaf progress 必须为 0..100 整数")
            if status == "done" and progress != 100: raise ValueError("bootstrap done 叶子任务的 progress 必须为 100")
            node["progress"] = progress
        if parent_key is not None: node["parent"] = ids[parent_key]
        proposed[task_id] = node; paths.append(path)
    reopen_incomplete_done_tasks(proposed)
    proposed_knowledge, source_copies = {}, []
    workspace = home.parent
    for index, entry in enumerate(knowledge_entries, 1):
        if not isinstance(entry, dict): raise TypeError("bootstrap knowledge 条目必须是对象")
        if entry.get("confidence") == "unreviewed":
            raise ValueError("bootstrap knowledge 候选必须审阅、删除或把 confidence 改为 reviewed")
        title, source, quote = (str(entry.get(field, "")).strip() for field in ("title", "source", "quote"))
        if not title or not source or not quote: raise ValueError("bootstrap knowledge 必须有 title、source、quote")
        source_path = (workspace / source).resolve()
        try: relative = source_path.relative_to(workspace.resolve())
        except ValueError as exc: raise ValueError(f"bootstrap knowledge source 越界：{source}") from exc
        if not source_path.is_file() or ".hypha" in relative.parts: raise ValueError(f"bootstrap knowledge source 无效：{source}")
        captured = Path("src") / "bootstrap" / relative
        anchor = captured.as_posix()
        if entry.get("heading"): anchor += "#" + heading_slug(str(entry["heading"]))
        affects = []
        for key in entry.get("affects", []):
            if key not in ids: raise ValueError(f"bootstrap knowledge affects 不存在：{key}")
            affects.append(ids[key])
        triggers = [str(item).casefold() for item in entry.get("triggers", []) if str(item).strip()]
        if not triggers: raise ValueError(f"bootstrap knowledge {title} 缺 triggers")
        slug = re.sub(r"[^\w-]+", "-", title.lower()).strip("-") or f"background-{index}"
        ident = f"know/bootstrap/{slug[:48]}"
        if ident in proposed_knowledge: ident += f"-{index}"
        target = home / (ident + ".md")
        node = {"claim_kind": "sourced", "status": "active", "when": str(entry.get("when", "")).strip() or f"Working on {title}",
                "triggers": triggers, "anchors": [anchor], "evidence": [{"anchor": anchor, "quote": quote}],
                "affects": affects, "_body": f"\n# {title}\n\n{str(entry.get('summary', '')).strip()}\n", "_path": target, "title": title}
        proposed_knowledge[ident] = node; paths.append(target); source_copies.append((source_path, captured))
    with tempfile.TemporaryDirectory() as temp_dir:
        validation_home = Path(temp_dir)
        for source_path, captured in source_copies:
            destination = validation_home / captured; destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source_path, destination)
        errors = validate(validation_home, proposed, proposed_knowledge)
    if errors: raise ValueError("\n".join(errors))
    (home / "intent").mkdir(parents=True, exist_ok=True)
    for source_path, captured in source_copies:
        destination = home / captured; destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source_path, destination)
    for task_id, node in proposed.items(): write_node(node["_path"], node, atomic=True)
    for node in proposed_knowledge.values(): write_node(node["_path"], node, atomic=True)
    sync(home, by="bootstrap")
    return [str(path.relative_to(home)) for path in paths]


def init(args):
    home = root(args)
    with locked(home):
        for name in ("src", "intent", "know", ".drafts", "snapshots"):
            (home / name).mkdir(parents=True, exist_ok=True)
        atomic_write(home / ".gitignore", "lock\nview.html\n")
        atomic_write(home / ".gitattributes", "snapshots/*.jsonl merge=union\naudit-resolutions.jsonl merge=union\n")
        sync(home)
    print(f"已初始化 {home}")


def rebuild_index(home: Path):
    tasks, knowledge = scan(home)
    rows = ["# Hypha index", "", "## Tasks", ""]
    rows += [f"- intent/{task_id} | [{n.get('status')}] | {n['title']}" for task_id, n in sorted(tasks.items())]
    rows += ["", "## Knowledge"]
    if knowledge: rows.append("")
    for key, node in sorted(knowledge.items()):
        triggers = knowledge_triggers(node)
        rows.append(f"- {key} | {node.get('when', '')} | {', '.join(map(str, triggers))}")
    atomic_write(home / "INDEX.md", "\n".join(rows) + "\n")


def normalize(value):
    if isinstance(value, list):
        if all(not isinstance(item, dict) for item in value):
            return sorted(set(map(str, value)))
        return [{key: normalize(item[key]) for key in sorted(item)} for item in value]
    if isinstance(value, dict): return {key: normalize(value[key]) for key in sorted(value)}
    return value


def audit_projection(node: dict) -> dict:
    """The audit log intentionally excludes body text; git owns body history."""
    fields = ("id", "status", "progress", "parent", "depends_on", "affects", "blocked_reason",
              "superseded_by", "claim_kind", "knowledge_kind", "scope", "authority", "review_when",
              "agreement_quote", "anchors", "evidence", "inference", "when", "triggers")
    result = {field: normalize(node[field]) for field in fields if field in node}
    result["body_hash"] = hashlib.sha256(node.get("_body", "").encode("utf-8")).hexdigest()
    return result


def replay(home: Path) -> tuple[dict[str, dict], dict[tuple[str, str, str], str]]:
    """Replay append-only observations.  This is an audit projection, never current truth."""
    state: dict[str, dict] = {}
    last_by: dict[tuple[str, str, str], str] = {}
    for path in sorted((home / "snapshots").glob("*.jsonl")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip(): continue
            try: event = json.loads(line)
            except json.JSONDecodeError as exc: raise ValueError(f"{path}:{line_no}: 无效快照 JSON：{exc}")
            if not {"kind", "id", "field", "to", "recorded_at", "origin"} <= set(event):
                raise ValueError(f"{path}:{line_no}: 快照字段不完整")
            if event["kind"] not in {"intent", "know"}:
                continue
            key = f"{event['kind']}:{event['id']}"
            state.setdefault(key, {})[event["field"]] = event["to"]
            last_by[(str(event["kind"]), str(event["id"]), str(event["field"]))] = str(event.get("by", "direct"))
    return state, last_by


def append_audit(home: Path, tasks: dict, knowledge: dict, by: str = "direct") -> None:
    previous, _ = replay(home)
    current = {f"{kind}:{ident}": audit_projection(node)
               for kind, nodes in (("intent", tasks), ("know", knowledge)) for ident, node in nodes.items()}
    origin = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
    changes, last_stamp = [], ""
    for key in sorted(set(previous) | set(current)):
        old, new = previous.get(key, {}), current.get(key, {})
        kind, ident = key.split(":", 1)
        for field in sorted(set(old) | set(new)):
            if old.get(field) == new.get(field): continue
            stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            stamp = max(stamp, last_stamp)
            last_stamp = stamp
            changes.append({"recorded_at": stamp, "origin": origin, "scope": "global" if home == Path.home() / ".hypha" else "ws",
                            "kind": kind, "id": ident, "field": field, "from": old.get(field), "to": new.get(field), "by": by})
    if changes:
        target = home / "snapshots" / (dt.datetime.now(dt.timezone.utc).date().isoformat() + ".jsonl")
        with target.open("a", encoding="utf-8") as handle:
            for change in changes: handle.write(json.dumps(change, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush(); os.fsync(handle.fileno())


def sync(home: Path, by: str = "direct") -> tuple[dict, dict]:
    tasks, knowledge = scan(home)
    append_audit(home, tasks, knowledge, by)
    rebuild_index(home)
    return tasks, knowledge


def prepare(home: Path) -> tuple[dict, dict]:
    """Mandatory entry barrier: notice unmanaged writes and rebuild derived state."""
    return sync(home, by="direct")


def add(args):
    home = root(args)
    with locked(home):
        (home / "intent").mkdir(parents=True, exist_ok=True)
        tasks, knowledge = prepare(home)
        if args.parent and args.root:
            raise ValueError("不能同时指定父任务和 --root")
        if args.parent and args.parent not in tasks:
            raise ValueError(f"父任务不存在：{args.parent}")
        if tasks and not args.parent and not args.root:
            raise ValueError("已有任务；请指定父任务 ID，或用 --root 显式创建独立根任务")
        duplicate = next((task_id for task_id, node in tasks.items()
                          if node.get("status") != "dropped" and node["title"].casefold() == args.title.casefold()), None)
        if duplicate:
            raise ValueError(f"已有同名任务 {duplicate}；请续接该任务，或使用不同标题")
        numeric = [int(x) for x in tasks if x.isdigit()]
        task_id = f"{(max(numeric, default=0) + 1):04d}"
        slug = re.sub(r"[^\w\-]+", "-", args.title.lower()).strip("-") or task_id
        path = home / "intent" / f"{task_id}-{slug[:40]}.md"
        node = {"id": task_id, "status": "todo", "_body": f"\n# {args.title}\n\n## 验收\n\n## 证据\n"}
        if args.parent: node["parent"] = args.parent
        probe = dict(tasks); probe[task_id] = node
        if args.parent: probe[args.parent].pop("progress", None)
        reopened = reopen_incomplete_done_tasks(probe)
        errors = validate(home, probe, knowledge)
        if errors: raise ValueError("\n".join(errors))
        for changed_id in sorted(reopened | ({args.parent} if args.parent else set())):
            write_node(tasks[changed_id]["_path"], tasks[changed_id], atomic=True)
        write_node(path, node, atomic=True)
        sync(home, by="cli")
    print(f"已创建 {task_id}: {path.relative_to(home)}")


def task_mutate(args):
    home = root(args)
    with locked(home):
        tasks, knowledge = prepare(home); node = tasks.get(args.id)
        if not node: raise ValueError(f"不存在任务 {args.id}")
        children = graph(tasks, knowledge)["children"].get(args.id, set())
        if args.command == "progress":
            if children: raise ValueError(f"{args.id} 有子任务；请更新叶子节点进度")
            value = int(args.value)
            if not 0 <= value <= 100: raise ValueError("progress 必须为 0..100")
            node["progress"] = value
            if value > 0 and node.get("status") == "todo": node["status"] = "in_progress"
            if value < 100 and node.get("status") == "done": node["status"] = "in_progress"
        elif args.command == "block": node["status"] = "blocked"; node["blocked_reason"] = args.value
        else:
            node["status"] = {"start": "in_progress", "done": "done", "drop": "dropped"}[args.command]
            node.pop("blocked_reason", None)
            if args.command == "done":
                if children:
                    progress = task_progresses(tasks)[args.id]
                    if progress != 100: raise ValueError(f"{args.id} 的叶子节点聚合进度为 {progress if progress is not None else '—'}%；达到 100% 后才能完成")
                    node.pop("progress", None)
                else: node["progress"] = 100
        reopened = reopen_incomplete_done_tasks(tasks)
        errors = validate(home, tasks, knowledge)
        if errors: raise ValueError("\n".join(errors))
        for changed_id in sorted(reopened | {args.id}): write_node(tasks[changed_id]["_path"], tasks[changed_id], atomic=True)
        sync(home, by="cli")
    print(f"已更新 {args.id}: {node['status']}")
    if args.command == "progress" and int(args.value) == 100:
        print(f"提示：100% 只表示叶子工作量完成；核实验收与证据后再运行 hypha done {args.id}。")


def lint_findings(home: Path, tasks: dict, knowledge: dict, trigger_warn_ratio: float) -> tuple[list[str], list[str], list[str]]:
    errors = validate(home, tasks, knowledge)
    ignored = (home / ".gitignore").read_text(encoding="utf-8") if (home / ".gitignore").exists() else ""
    if "lock" not in ignored: errors.append(".hypha/.gitignore 必须忽略 lock")
    if ".drafts/" in ignored: errors.append(".hypha/.drafts/ 是跨机器恢复状态，不能被忽略")
    if workspace_ignores_hypha(home.parent): errors.append("工作区 Git 忽略了 .hypha/")
    return errors, trigger_warnings(knowledge, trigger_warn_ratio), unmanaged_fields(home, tasks, knowledge)


def lint(args):
    home = root(args)
    with locked(home):
        tasks, knowledge = prepare(home)
        errors, warnings, unmanaged = lint_findings(home, tasks, knowledge, args.trigger_warn_ratio)
        if args.audit: audit(home, tasks, knowledge)
        if unmanaged:
            print("提示：检测到未托管正式写入（已审计，建议下次使用草稿 + apply）：")
            for item in unmanaged[:12]: print("- " + item)
        for warning in warnings: print("警告：" + warning)
    if errors:
        print("\n".join("错误：" + e for e in errors)); raise SystemExit(1)
    print("lint 通过")


def trigger_warnings(knowledge: dict, ratio: float = .5) -> list[str]:
    if not 0 < ratio <= 1:
        raise ValueError("--trigger-warn-ratio 必须大于 0 且不超过 1")
    active = [node for node in knowledge.values()
              if node.get("claim_kind") != "note" and node.get("status", "active") == "active"]
    population = max(len(active), 1); counts = defaultdict(int)
    for node in active:
        for trigger in set(knowledge_triggers(node)): counts[trigger] += 1
    return [f"共享 trigger 候选：{trigger} 命中 {count}/{population} 条 active 知识；请由 agent 判断是否过宽"
            for trigger, count in sorted(counts.items()) if count > 1 and count / population >= ratio]


def workspace_ignores_hypha(workspace: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace), "check-ignore", "-q", ".hypha"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def unmanaged_fields(home: Path, tasks: dict, knowledge: dict) -> list[str]:
    _, last_by = replay(home)
    findings = []
    for kind, nodes in (("intent", tasks), ("know", knowledge)):
        for ident, node in nodes.items():
            for field in audit_projection(node):
                if last_by.get((kind, ident, field)) == "direct": findings.append(f"{kind}:{ident} {field}")
    return sorted(findings)


def candidate_id(candidate: dict) -> str:
    payload = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def load_audit_resolutions(home: Path) -> dict[str, str]:
    resolutions = {}
    path = home / "audit-resolutions.jsonl"
    if not path.exists():
        return resolutions
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            resolutions[str(record["candidate"])] = str(record["resolution"])
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path}:{line_no}: 无效 audit 判定：{exc}") from exc
    return resolutions


def audit_candidates(tasks: dict, knowledge: dict) -> list[dict]:
    candidates = []
    relations = graph(tasks, knowledge)
    if len(tasks) > 1:
        for task_id, task in sorted(tasks.items()):
            connected = (
                task.get("parent")
                or task.get("depends_on")
                or relations["children"].get(task_id)
                or relations["unlocks"].get(task_id)
                or relations["premises"].get(task_id)
            )
            if not connected:
                candidates.append({"kind": "isolated-task", "task": task_id})
    for task_id, task in sorted(tasks.items()):
        if task.get("status") not in {"todo", "in_progress", "blocked"}:
            continue
        terms = {item.casefold() for item in WORD.findall(task["title"])}
        for path, node in knowledge.items():
            if node.get("claim_kind") == "note":
                continue
            words = {item.casefold() for item in WORD.findall(node["title"] + " " + " ".join(knowledge_triggers(node)))}
            if terms & words and task_id not in map(str, node.get("affects", [])):
                candidates.append({"kind": "missing-relation", "task": task_id, "knowledge": path})
    return candidates


def audit(home: Path, tasks: dict, knowledge: dict) -> None:
    """Heuristic-only audit; it never changes nodes or task state."""
    print("audit（候选，需人工判断）：")
    resolutions = load_audit_resolutions(home)
    unresolved = [candidate for candidate in audit_candidates(tasks, knowledge)
                  if resolutions.get(candidate_id(candidate)) != "unrelated"]
    for candidate in unresolved:
        if candidate["kind"] == "isolated-task":
            print(f"- [{candidate_id(candidate)}] {candidate['task']}: 孤立任务；请判断是否应设置 parent/needs，或保留为独立根任务")
        else:
            print(f"- [{candidate_id(candidate)}] {candidate['task']}: 可能缺 affects/正文链接：{candidate['knowledge']}")
    if not unresolved:
        print("- 没有未判定的关系候选")
    print("路由预演：")
    for task_id, task in sorted(tasks.items()):
        if task.get("status") in {"todo", "in_progress", "blocked"}:
            candidates = route(tasks, knowledge, task["title"])
            print(f"- {task_id}: {', '.join(path for _, path, _ in candidates[:4]) or '无'}")
    if unresolved:
        agent_follow_up(
            "Adjudicate heuristic graph candidates without inventing relationships.",
            [
                "Read each candidate task and knowledge node, including body, scope, evidence, and existing links.",
                "For missing-relation candidates, decide whether the knowledge materially affects the task; if yes, publish the actual affects/wiki-link change before resolving it.",
                "For isolated tasks, decide whether the task is a legitimate root, a child, or dependency-related; change the graph only with evidence or user confirmation.",
                "Run lint --audit again. Use dismiss <id> only for confirmed false positives; use defer <id> when evidence is currently insufficient.",
            ],
            [f"unresolved candidates: {len(unresolved)}"],
        )


def resolve_candidate(args, resolution: str):
    home = root(args)
    with locked(home):
        tasks, knowledge = prepare(home)
        current = {candidate_id(candidate): candidate for candidate in audit_candidates(tasks, knowledge)}
        if args.candidate not in current:
            raise ValueError("candidate 不是当前 lint --audit 候选；请重新运行 lint --audit")
        path = home / "audit-resolutions.jsonl"
        record = {
            "candidate": args.candidate,
            "resolution": resolution,
            "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    print(f"已记录 {args.candidate}: {resolution}")
    if resolution == "deferred": print("提示：deferred 候选仍会在后续 audit 中显示。")


def dismiss(args): resolve_candidate(args, "unrelated")


def defer(args): resolve_candidate(args, "deferred")


def needs(args):
    home = root(args)
    with locked(home):
        tasks, knowledge = prepare(home)
        if args.id not in tasks or args.dependency not in tasks: raise ValueError("任务不存在")
        node = tasks[args.id]; deps = list(node.get("depends_on", []))
        if args.dependency not in deps: deps.append(args.dependency)
        node["depends_on"] = deps
        errors = validate(home, tasks, knowledge)
        if errors: raise ValueError("\n".join(errors))
        write_node(node["_path"], node, atomic=True); sync(home, by="cli")
    print(f"{args.id} 依赖 {args.dependency}")


def set_parent(args):
    home = root(args)
    with locked(home):
        tasks, knowledge = prepare(home)
        if args.id not in tasks or args.parent not in tasks: raise ValueError("任务不存在")
        if args.id == args.parent: raise ValueError("任务不能以自身为父任务")
        tasks[args.id]["parent"] = args.parent
        tasks[args.parent].pop("progress", None)
        reopened = reopen_incomplete_done_tasks(tasks)
        errors = validate(home, tasks, knowledge)
        if errors: raise ValueError("\n".join(errors))
        for changed_id in sorted(reopened | {args.id, args.parent}):
            write_node(tasks[changed_id]["_path"], tasks[changed_id], atomic=True)
        sync(home, by="cli")
    print(f"{args.id} 的父任务为 {args.parent}")


def apply(args):
    home, draft = root(args), Path(args.draft).resolve()
    drafts = (home / ".drafts").resolve()
    if drafts not in draft.parents: raise ValueError("草稿必须位于 .hypha/.drafts/")
    with locked(home):
        node = read_node(draft)
        draft_kind = node.pop("kind", None)
        if draft_kind in {"note", "handoff"}:
            raise ValueError(f"kind: {draft_kind} 是交接/笔记草稿，不能 apply 发布")
        if draft_kind == "task-update":
            if args.global_store: raise ValueError("--global apply 只允许知识草稿，不能发布 task-update")
            if not node.get("id"):
                raise ValueError("kind: task-update 必须提供 id")
            kind, ident = "intent", str(node["id"])
        elif draft_kind == "know":
            if node.get("id") is not None:
                raise ValueError("kind: know 不能包含任务 id")
            kind, ident = "know", ""
        elif draft_kind is None:
            if node.get("id") is None:
                raise ValueError("无 id 的草稿必须显式写 kind: know；交接请使用 kind: handoff")
            raise ValueError("任务更新必须显式写 kind: task-update")
        else:
            raise ValueError(f"未知草稿 kind: {draft_kind}；可用 task-update、know、handoff、note")
        tasks, knowledge = prepare(home)
        if kind == "intent":
            if ident not in tasks:
                raise ValueError(f"task-update 只能更新已有任务：{ident}")
            existing = tasks[ident]
            target = existing["_path"]
            node = {**existing, **node, "_path": target}
        else:
            slug = re.sub(r"[^\w-]+", "-", node["title"].lower()).strip("-")
            target = home / kind / f"{slug or hashlib.sha256(draft.read_bytes()).hexdigest()[:12]}.md"
            ident = str(target.relative_to(home)).removesuffix(".md")
            node.setdefault("status", "active")
            node.setdefault("triggers", knowledge_triggers(node))
        if kind == "intent": tasks[ident] = node
        else:
            incoming_hash = audit_projection(node)["body_hash"]
            duplicate = next((path for path, old in knowledge.items() if audit_projection(old)["body_hash"] == incoming_hash and path != ident), None)
            if duplicate: raise ValueError(f"草稿内容已发布为 {duplicate}")
            knowledge[ident] = node
        if kind == "intent" and graph(tasks, knowledge)["children"].get(ident): node.pop("progress", None)
        reopened = reopen_incomplete_done_tasks(tasks) if kind == "intent" else set()
        errors = validate(home, tasks, knowledge)
        if errors: raise ValueError("\n".join(errors))
        for changed_id in sorted(reopened - {ident}):
            write_node(tasks[changed_id]["_path"], tasks[changed_id], atomic=True)
        write_node(target, node, atomic=True); sync(home, by="apply")
        mark_draft_applied(home, draft)
    print(f"已发布 {target.relative_to(home)}")


def route(tasks: dict, knowledge: dict, text: str) -> list[tuple[int, str, dict]]:
    terms = {x.casefold() for x in WORD.findall(text)}
    scored = []
    for path, node in knowledge.items():
        if node.get("claim_kind") == "note" or node.get("status", "active") != "active": continue
        triggers = knowledge_triggers(node)
        trigger_hits = len(terms & {str(x).casefold() for x in triggers})
        title_hits = len(terms & {x.casefold() for x in WORD.findall(node["title"])})
        if not (trigger_hits or title_hits): continue
        open_affects = sum(str(x) in tasks and tasks[str(x)].get("status") in {"todo", "in_progress", "blocked"}
                           for x in node.get("affects", []))
        score = (ROUTE_TRIGGER_WEIGHT * trigger_hits + ROUTE_TITLE_WEIGHT * title_hits
                 + ROUTE_OPEN_TASK_TIE_BREAK * open_affects)
        scored.append((score, path, node))
    return sorted(scored, key=lambda item: (-item[0], item[1]))


def read_events(home: Path) -> list[dict]:
    events = []
    for path in sorted((home / "snapshots").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip(): events.append(json.loads(line))
    return events


def node_observation_times(events: list[dict]) -> dict[tuple[str, str], dict[str, str]]:
    """Derive first/last observation times without making audit data current truth."""
    times: dict[tuple[str, str], dict[str, str]] = {}
    for event in events:
        kind, ident, stamp = event.get("kind"), event.get("id"), event.get("recorded_at")
        if kind not in {"intent", "know"} or not ident or not isinstance(stamp, str):
            continue
        item = times.setdefault((str(kind), str(ident)), {"created_at": stamp, "updated_at": stamp})
        item["created_at"] = min(item["created_at"], stamp)
        item["updated_at"] = max(item["updated_at"], stamp)
    return times


def append_session_marker(home: Path, action: str) -> None:
    event = {
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "origin": f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}",
        "scope": "global" if home == Path.home() / ".hypha" else "ws",
        "kind": "session",
        "id": "workspace",
        "field": "lifecycle",
        "from": None,
        "to": action,
        "by": "cli",
    }
    target = home / "snapshots" / (dt.datetime.now(dt.timezone.utc).date().isoformat() + ".jsonl")
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def previous_session_unclosed(home: Path) -> bool:
    events = read_events(home)
    lifecycle = [event for event in events
                 if event.get("kind") == "session" and event.get("field") == "lifecycle"]
    if not lifecycle:
        return any(event.get("kind") in {"intent", "know"} for event in events)
    return lifecycle[-1].get("to") == "open"


def applied_draft_hashes(home: Path) -> dict[str, str]:
    """Read the local publication ledger; invalid ledgers never hide a draft."""
    path = home / ".drafts" / ".applied.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): str(item) for key, item in value.items()} if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def mark_draft_applied(home: Path, draft: Path) -> None:
    path = home / ".drafts" / ".applied.json"
    hashes = applied_draft_hashes(home)
    hashes[str(draft.relative_to(home))] = hashlib.sha256(draft.read_bytes()).hexdigest()
    atomic_write(path, json.dumps(hashes, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def pending_drafts(home: Path) -> list[tuple[Path, str, str, str]]:
    """List recoverable drafts without treating malformed work as formal state."""
    found = []
    published = applied_draft_hashes(home)
    for path in sorted((home / ".drafts").glob("*.md")):
        try:
            node = read_node(path)
            current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if node.get("kind") in {"know", "task-update"} and published.get(str(path.relative_to(home))) == current_hash:
                continue
            found.append((path, str(node.get("kind", "missing")), str(node.get("id", "")), node["title"]))
        except (OSError, ValueError) as exc:
            found.append((path, "invalid", "", str(exc)))
    return found


def print_draft_summary(home: Path, verbose: bool = False) -> None:
    drafts = pending_drafts(home)
    if not drafts:
        return
    print(f"未 apply 草稿：{len(drafts)} 个（.hypha/.drafts/；跨机器恢复状态）")
    if verbose:
        for path, kind, task_id, title in drafts:
            suffix = f" id={task_id}" if task_id else ""
            print(f"- {path.name} | kind={kind}{suffix} | {title}")


def drafts_command(args):
    home = root(args)
    with locked(home):
        prepare(home)
        drafts = pending_drafts(home)
    if not drafts:
        print("没有未 apply 草稿。")
        return
    print_draft_summary(home, verbose=True)


def section(body: str, name: str) -> str:
    match = re.search(rf"(?ms)^##\s+{re.escape(name)}\s*$\n?(.*?)(?=^##\s|\Z)", body)
    return match.group(1).strip() if match else ""


def done_in_current_session(home: Path) -> set[str]:
    events = read_events(home)
    opens = [index for index, event in enumerate(events)
             if event.get("kind") == "session" and event.get("field") == "lifecycle" and event.get("to") == "open"]
    start = opens[-1] if opens else -1
    return {str(event["id"]) for event in events[start + 1:]
            if event.get("kind") == "intent" and event.get("field") == "status"
            and event.get("to") == "done"}


def git_changes(workspace: Path) -> list[str]:
    try:
        result = subprocess.run(["git", "-C", str(workspace), "status", "--short", "--", ".hypha"], capture_output=True, text=True, check=False)
    except OSError: return []
    return [line[3:] for line in result.stdout.splitlines() if len(line) > 3]


def boot(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    if previous_session_unclosed(home):
        running = ", ".join(task_id for task_id, node in sorted(tasks.items()) if node.get("status") == "in_progress") or "无"
        print(f"提示：上次会话可能未收尾；运行中任务：{running}")
    agreements = sorted((home / "agreements").glob("*.md"))
    if agreements:
        print("迁移提示：agreements/ 已弃用；操作规则移入适用范围内的 AGENTS.md，缘由与历史移入 know/。")
        for path in agreements: print(f"- legacy agreements/{path.name}")
    print("任务：")
    for task_id, node in sorted(tasks.items()):
        ready = node.get("status") == "todo" and all(tasks[str(dep)].get("status") == "done" for dep in node.get("depends_on", []))
        if node.get("status") in {"in_progress", "blocked"} or ready:
            print(f"- {task_id} [{node.get('status')}] {node['title']}")
    print("知识：")
    for _, path, node in route(tasks, knowledge, args.term)[:12]:
        triggers = knowledge_triggers(node)
        print(f"- {path} | {node.get('when', '')} | {', '.join(map(str, triggers))}")
    redlinks = graph(tasks, knowledge)["redlinks"]
    if redlinks: print("红链：" + ", ".join(sorted(redlinks)))
    print_draft_summary(home)
    print("选择候选后运行：hypha start <id>")
    with locked(home): append_session_marker(home, "open")


def ready(args):
    home = root(args)
    with locked(home): tasks, _ = prepare(home)
    progresses = task_progresses(tasks)
    running = [(task_id, node) for task_id, node in sorted(tasks.items()) if node.get("status") == "in_progress"]
    if running:
        print("运行中（续接候选）：")
        for task_id, node in running:
            progress = f" {progresses[task_id]}%" if progresses[task_id] is not None else ""
            print(f"- {task_id}{progress} {node['title']}")
    print("可开工：")
    for task_id, node in sorted(tasks.items()):
        if node.get("status") == "todo" and all(tasks[str(dep)].get("status") == "done" for dep in node.get("depends_on", [])):
            print(f"- {task_id} {node['title']}")
    print_draft_summary(home)
    print("下一步：hypha start <id>")


def list_nodes(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    observation_times = node_observation_times(read_events(home))
    progresses = task_progresses(tasks)
    rows = []
    if args.type in {"all", "task"}:
        for task_id, node in sorted(tasks.items()):
            status = str(node.get("status", "todo"))
            if args.status and status != args.status:
                continue
            rows.append({
                "id": task_id, "type": "task", "title": node["title"], "status": status,
                "progress": progresses[task_id], "parent": node.get("parent"),
                "path": str(node["_path"].relative_to(home)),
                **observation_times.get(("intent", task_id), {}),
            })
    if args.type in {"all", "knowledge"}:
        for path, node in sorted(knowledge.items()):
            status = str(node.get("status", "active"))
            if args.status and status != args.status:
                continue
            rows.append({
                "id": path, "type": "knowledge", "title": node["title"], "status": status,
                "claim_kind": node.get("claim_kind"), "knowledge_kind": node.get("knowledge_kind"),
                "scope": node.get("scope"), "authority": node.get("authority"),
                "path": str(node["_path"].relative_to(home)),
                **observation_times.get(("know", path), {}),
            })
    if args.json:
        counts = {kind: sum(row["type"] == kind for row in rows) for kind in ("task", "knowledge")}
        print(json.dumps({"schemaVersion": 1, "counts": {"total": len(rows), **counts}, "nodes": rows}, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("No nodes match the filters.")
        return
    if args.tree:
        task_rows = {row["id"]: row for row in rows if row["type"] == "task"}
        children = defaultdict(list)
        for task_id, row in task_rows.items():
            parent = str(row["parent"]) if row.get("parent") is not None else None
            children[parent if parent in task_rows else None].append(task_id)
        def render_task(task_id: str, prefix: str = "") -> None:
            row = task_rows[task_id]
            progress = f" {row['progress']}%" if row.get("progress") is not None else ""
            print(f"{prefix}{task_id} [{row['status']}]{progress} {row['title']}")
            for child in children[task_id]:
                render_task(child, prefix + "  ")
        if task_rows:
            print("Tasks")
            for task_id in children[None]:
                render_task(task_id)
        knowledge_rows = [row for row in rows if row["type"] == "knowledge"]
        if knowledge_rows:
            if task_rows: print()
            print("Knowledge")
            for row in knowledge_rows:
                print(f"{row['id']} [{row['status']}] {row['title']}")
        return
    table = [[
        row["type"], row["id"], row["status"],
        f"{row['progress']}%" if row.get("progress") is not None else "—",
        row.get("updated_at", "—")[:10], row["title"],
    ] for row in rows]
    headers = ["TYPE", "ID", "STATUS", "PROGRESS", "UPDATED", "TITLE"]
    widths = [max(len(headers[index]), *(len(row[index]) for row in table)) for index in range(len(headers) - 1)]
    print("  ".join(headers[index].ljust(widths[index]) for index in range(len(widths))) + "  " + headers[-1])
    for row in table:
        print("  ".join(row[index].ljust(widths[index]) for index in range(len(widths))) + "  " + row[-1])


def route_command(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    terms = {x.casefold() for x in WORD.findall(args.term)}
    for score, path, node in route(tasks, knowledge, args.term):
        trigger_hits = sorted(terms & {str(x).casefold() for x in knowledge_triggers(node)})
        title_hits = sorted(terms & {x.casefold() for x in WORD.findall(node["title"])})
        open_affects = [str(x) for x in node.get("affects", [])
                        if str(x) in tasks and tasks[str(x)].get("status") in {"todo", "in_progress", "blocked"}]
        print(f"{path}\tscore={score}\ttrigger_hits={','.join(trigger_hits) or '-'}"
              f"\ttitle_hits={','.join(title_hits) or '-'}\topen_affects={','.join(open_affects) or '-'}"
              f"\twhen={node.get('when', '')}")


def close(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    errors, warnings, unmanaged = lint_findings(home, tasks, knowledge, .5)
    if errors:
        raise ValueError("收尾前 lint 未通过：\n" + "\n".join(errors))
    for warning in warnings: print("警告：" + warning)
    if unmanaged:
        print("提示：检测到未托管正式写入：")
        for item in unmanaged[:12]: print("- " + item)
    print("运行中：" + ", ".join(k for k,v in tasks.items() if v.get("status") == "in_progress"))
    print("受阻：" + ", ".join(k for k,v in tasks.items() if v.get("status") == "blocked"))
    redlinks = graph(tasks, knowledge)["redlinks"]
    print("红链：" + ", ".join(sorted(redlinks)))
    audit(home, tasks, knowledge)
    done = done_in_current_session(home)
    for task_id in done:
        if task_id not in tasks: continue
        node = tasks[task_id]
        print(f"完成候选 {task_id}：")
        print(section(node.get("_body", ""), "验收") or "（无验收）")
        print(section(node.get("_body", ""), "证据") or "（无证据）")
        print("知识前提：" + ", ".join(sorted(graph(tasks, knowledge)["premises"].get(task_id, set()))) )
    changes = git_changes(home.parent)
    if changes:
        print("本轮文件：" + ", ".join(changes))
        print("建议提交：git add " + " ".join(changes) + " && git commit -m 'hypha: update state'")
    else: print("本轮没有未提交文件。")
    agent_follow_up(
        "Finish the governed session using semantic evidence, not status or Git activity alone.",
        [
            "Compare the user's requested outcome with each active task's acceptance criteria and the actual repository changes.",
            "For every completion candidate, verify acceptance item by item and cite concrete tests, files, commands, or user confirmation; reopen tasks whose evidence is insufficient.",
            "Identify durable rationale, constraints, decisions, consensus, lessons, assumptions, or deviations from this session; update existing knowledge before creating duplicates.",
            "Propose task creation, done/drop, reparenting, or major knowledge changes to the user unless they directly requested that state change.",
            "If this review causes further graph changes, run close once more; otherwise this command records the session close. Follow AGENTS.md for version-control actions.",
        ],
        [f"completion candidates since latest boot: {', '.join(sorted(done)) or 'none'}"],
    )
    with locked(home):
        append_session_marker(home, "close")


def ingest(args):
    home, source = root(args), Path(args.file).resolve()
    if not source.is_file(): raise ValueError(f"来源不存在：{source}")
    with locked(home):
        tasks, knowledge = prepare(home)
        destination = home / "src" / source.name
        if destination.exists() and destination.read_bytes() != source.read_bytes():
            destination = home / "src" / f"{source.stem}-{hashlib.sha256(source.read_bytes()).hexdigest()[:8]}{source.suffix}"
        if not destination.exists(): shutil.copy2(source, destination)
        sync(home, by="cli")
    candidates = route(tasks, knowledge, source.stem)[:8]
    print(f"已复制来源：{destination.relative_to(home)}")
    print("候选旧知识：" + ", ".join(path for _, path, _ in candidates) if candidates else "候选旧知识：无")
    agent_follow_up(
        "Turn the captured source into evidence-backed project knowledge.",
        [
            "Read the copied source and extract only durable claims relevant across sessions; preserve exact quotes and heading/file anchors.",
            "Search existing knowledge with search using 3-8 literal keywords from the source, then inspect the listed candidates and backlinks.",
            "For each durable claim, classify it as support, refinement, contradiction, or genuinely new knowledge relative to existing nodes.",
            "Update or supersede existing knowledge instead of duplicating it. Create a sourced draft only when a distinct claim remains, with when, triggers, anchors, evidence, and affected tasks.",
            "Do not infer task completion from the source. Ask for confirmation when scope, consensus, or a high-impact relationship is ambiguous.",
            "Validate and publish confirmed drafts with hypha apply, then run lint --audit.",
        ],
        [f"captured source: {destination.relative_to(home)}",
         f"route candidates: {', '.join(path for _, path, _ in candidates) or 'none'}"],
    )


def search(args):
    """Search knowledge or explicit source files using comma-separated literals."""
    if args.limit < 1: raise ValueError("search --limit 必须大于 0")
    home = root(args)
    with locked(home): _tasks, knowledge = prepare(home)
    terms = []
    for term in args.keywords.replace("，", ",").split(","):
        normalized = term.strip().casefold()
        if normalized and normalized not in terms: terms.append(normalized)
    if not terms: raise ValueError("search 至少需要一个非空关键词")
    candidates = []
    if args.file:
        workspace = home.parent.resolve()
        seen = set()
        for value in args.file:
            requested = Path(value)
            target = requested.resolve() if requested.is_absolute() else (workspace / requested).resolve()
            try: target.relative_to(workspace)
            except ValueError as exc: raise ValueError(f"search --file 必须位于 workspace 内：{value}") from exc
            if not target.exists(): raise ValueError(f"search --file 不存在：{value}")
            paths = [target] if target.is_file() else sorted(path for path in target.rglob("*") if path.is_file())
            for path in paths:
                resolved = path.resolve()
                try: resolved.relative_to(workspace)
                except ValueError: continue
                try: eligible = resolved not in seen and resolved.stat().st_size <= 1_000_000
                except OSError: continue
                if eligible:
                    seen.add(resolved); candidates.append(resolved)
    else:
        candidates = [node["_path"] for node in knowledge.values()
                      if node.get("status", "active") == "active" and node.get("claim_kind") != "note"]
    matches = []
    for path in candidates:
        try: lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError: continue
        for line_no, line in enumerate(lines, 1):
            folded = line.casefold()
            hit_terms = [term for term in terms if term in folded]
            if not hit_terms: continue
            occurrences = sum(folded.count(term) for term in hit_terms)
            try: display = path.relative_to(home.parent).as_posix()
            except ValueError: display = str(path)
            snippet = re.sub(r"\s+", " ", line).strip()
            matches.append((len(hit_terms), occurrences, display, line_no, snippet))
    matches.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    if not matches:
        print("No matches.")
        return
    for _, _, path, line_no, snippet in matches[:args.limit]:
        print(f"{path}:{line_no}: {snippet}")


def migrate(args):
    home = root(args)
    with locked(home):
        tasks, knowledge = prepare(home)
        errors = validate(home, tasks, knowledge)
        if errors: raise ValueError("\n".join(errors))
        agreements = sorted((home / "agreements").glob("*.md"))
    if not agreements:
        print("没有检测到需要迁移的 legacy agreements；结构校验请使用 hypha lint。")
        return
    agent_follow_up(
        "Migrate legacy agreements without losing rationale or duplicating always-on rules.",
        [
            "Read each legacy agreement and the nearest applicable AGENTS.md.",
            "Move only concise always-on operational instructions into AGENTS.md; preserve rationale, history, scope, exceptions, evidence, and review conditions as Hypha knowledge drafts.",
            "Ask the user before treating inferred consensus as confirmed agreement.",
            "Publish validated knowledge drafts, verify AGENTS.md does not duplicate their explanatory text, then remove legacy files only after the migration is reviewed.",
            "Run hypha lint --audit after the reviewed migration.",
        ],
        [f"legacy file: {path.relative_to(home)}" for path in agreements],
    )


def bootstrap(args):
    if args.global_store: raise ValueError("bootstrap 仅支持 workspace，不支持 --global")
    workspace, home = Path(args.workspace).resolve(), root(args)
    if args.apply_plan:
        plan_path = Path(args.apply_plan).resolve()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not home.is_dir(): raise ValueError("尚未 init；请先运行 hypha init")
        with locked(home): created = apply_bootstrap_plan(home, plan)
        print(f"已从 bootstrap plan 创建 {len(created)} 个节点")
        for path in created: print("- " + path)
        return
    plan = build_bootstrap_plan(workspace)
    rendered = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.dry_run:
        print(rendered, end=""); return
    if not home.is_dir(): raise ValueError("尚未 init；请先运行 hypha init")
    target = Path(args.output).resolve() if args.output else home / ".drafts" / "bootstrap-plan.json"
    try: target.relative_to(workspace)
    except ValueError as exc: raise ValueError("bootstrap plan 必须写在 workspace 内") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, rendered)
    print(f"已生成 bootstrap plan：{target}")
    agent_follow_up(
        "Convert repository observations into a truthful initial long-running task and knowledge graph.",
        [
            "Read the plan observations and relevant repository files; identify what work has actually happened, what remains, and the durable project background.",
            "Replace the placeholder root goal and acceptance criteria with the user's real long-running outcome. Do not infer progress from file counts, tests, commits, or documentation volume.",
            "Verify every checklist-derived task against its source and current repository state; correct status and leaf progress, and remove transient or already irrelevant items.",
            "Review each background candidate against its exact quote. Rewrite it into a durable sourced claim, merge it with existing concepts, or delete it; do not publish generic summaries.",
            "Set reviewed: true only after task meaning, acceptance, status, progress, evidence, knowledge scope, and relationships are justified.",
            f"Apply the reviewed plan with hypha --workspace {workspace} bootstrap --apply {target}.",
        ],
        [f"bootstrap plan: {target}", f"observed files: {plan['inventory']['files']}"],
    )


def view(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    events = read_events(home)
    observation_times = node_observation_times(events)
    progresses = task_progresses(tasks)
    relations = graph(tasks, knowledge)
    edges = []
    for task_id, task in tasks.items():
        if task.get("parent") in tasks:
            edges.append({"from": str(task["parent"]), "to": task_id, "kind": "parent"})
        for dependency in task.get("depends_on", []):
            if str(dependency) in tasks:
                edges.append({"from": str(dependency), "to": task_id, "kind": "depends"})
    for path, node in knowledge.items():
        for link in links(node):
            if link in knowledge:
                edges.append({"from": path, "to": link, "kind": "wiki"})
        for task_id in node.get("affects", []):
            if str(task_id) in tasks:
                edges.append({"from": path, "to": str(task_id), "kind": "affects"})
    data = {
        "schemaVersion": 1,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "initialMode": args.mode,
        "tasks": {
            key: {
                "title": node["title"], "status": node.get("status"), "progress": progresses[key],
                **observation_times.get(("intent", key), {}),
                "path": str(node["_path"].relative_to(home)), "summary": node.get("_body", "")[:280], "markdown": node.get("_body", ""),
                "metadata": {field: node.get(field) for field in ("parent", "depends_on", "affects", "when") if field in node},
            } for key, node in tasks.items()
        },
        "knowledge": {
            key: {
                "title": node["title"], "claim_kind": node.get("claim_kind"), "path": str(node["_path"].relative_to(home)),
                **observation_times.get(("know", key), {}),
                "summary": node.get("_body", "")[:280], "markdown": node.get("_body", ""),
                "metadata": {field: node.get(field) for field in ("affects", "when", "triggers", "anchors", "knowledge_kind", "scope", "authority", "review_when") if field in node},
            } for key, node in knowledge.items()
        },
        "edges": edges,
        "redlinks": sorted(relations["redlinks"]),
        "diagnostics": {"redlinks": sorted(relations["redlinks"]), "warnings": []},
        "events": events,
    }
    template_path = Path(__file__).parents[1] / "templates" / "view.html"
    try:
        template = template_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"缺少视图模板：{template_path}") from exc
    page = template.replace("{{HYPHA_DATA}}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    if page == template:
        raise ValueError(f"视图模板缺少 {{HYPHA_DATA}} 占位符：{template_path}")
    output = home / "view.html"
    atomic_write(output, page)
    print(output)
    if args.open:
        open_view(output)

def open_view(path: Path) -> None:
    """Open a generated local view without waiting for the viewer to exit."""
    if sys.platform.startswith("linux"):
        command = ["xdg-open", str(path)]
    elif sys.platform == "darwin":  # pragma: no cover - exercised on macOS.
        command = ["open", str(path)]
    else:
        raise ValueError("--open 目前仅支持 Linux（xdg-open）和 macOS（open）；请手动打开生成的 HTML 文件")
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except FileNotFoundError as exc:
        raise ValueError(f"找不到 {command[0]}；请手动打开 {path}") from exc


def show(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    n = tasks.get(args.target) or knowledge.get(args.target.removesuffix(".md"))
    if not n: raise ValueError(f"不存在节点 {args.target}")
    print(n["_path"].relative_to(root(args))); print(n["title"])
    for key in ("status", "parent", "depends_on", "affects", "when", "claim_kind", "knowledge_kind", "scope", "authority", "review_when"):
        if key in n: print(f"{key}: {n[key]}")
    relations = graph(tasks, knowledge)
    if args.target in tasks:
        progress = task_progresses(tasks)[args.target]
        print(f"progress: {progress if progress is not None else '—'}")
        print("知识前提：" + ", ".join(sorted(relations["premises"].get(args.target, set()))))
        print("子任务：" + ", ".join(sorted(relations["children"].get(args.target, set()))))
        print("解锁：" + ", ".join(sorted(relations["unlocks"].get(args.target, set()))))
    else:
        path = args.target.removesuffix(".md")
        print("反链：" + ", ".join(sorted(relations["backlinks"].get(path, set()))))
    print("红链：" + ", ".join(sorted(relations["redlinks"])))


def main():
    parser = argparse.ArgumentParser(
        prog="hypha",
        description="本地任务与知识图谱：用命令维护结构，用草稿 + apply 发布正文。",
        epilog="会话开始用 boot；结构问题用 lint；完成前用 close。",
    )
    parser.add_argument("--workspace", default=".", help="工作区根目录（默认当前目录）")
    parser.add_argument("--global", dest="global_store", action="store_true", help="改用 ~/.hypha 跨仓库知识库")
    sub = parser.add_subparsers(dest="command", required=True, title="命令")
    sub.add_parser("init", help="初始化当前工作区的 .hypha 目录", description="创建任务、知识、草稿、来源和审计目录。")
    p = sub.add_parser("add", help="创建一个 todo 任务", description="任务 ID 自动分配；可选地挂到已有父任务下。")
    p.add_argument("title", help="任务标题")
    p.add_argument("parent", nargs="?", help="可选父任务 ID，例如 0001")
    p.add_argument("--root", action="store_true", help="已有任务时，显式创建一个独立根任务")
    for name in ("start", "done", "drop"):
        actions = {"start": "开始执行任务", "done": "标记任务完成", "drop": "放弃任务"}
        p = sub.add_parser(name, help=actions[name]); p.add_argument("id", help="任务 ID")
    p = sub.add_parser("progress", help="更新任务进度（0 到 100）")
    p.add_argument("id", help="任务 ID"); p.add_argument("value", help="进度整数，例如 60")
    p = sub.add_parser("block", help="标记任务受阻并记录原因")
    p.add_argument("id", help="任务 ID"); p.add_argument("value", help="阻塞原因")
    p = sub.add_parser("needs", help="声明任务依赖，形成 DAG 边")
    p.add_argument("id", help="依赖方任务 ID"); p.add_argument("dependency", help="必须先完成的任务 ID")
    p = sub.add_parser("parent", help="为已有任务设置父任务，形成层级边")
    p.add_argument("id", help="子任务 ID"); p.add_argument("parent", help="父任务 ID")
    p = sub.add_parser("apply", help="校验并原子发布一份草稿")
    p.add_argument("draft", help=".hypha/.drafts/ 下的 Markdown 草稿路径")
    p = sub.add_parser("lint", help="检查结构、证据、链接和路由规则")
    p.add_argument("--audit", action="store_true", help="额外列出可能缺失的关系和路由候选")
    p.add_argument("--trigger-warn-ratio", type=float, default=.5, help="共享 trigger 警告比例（默认 0.5；仅警告）")
    p = sub.add_parser("dismiss", help="确认 audit 候选无关并永久隐藏")
    p.add_argument("candidate", help="lint --audit 输出的候选 ID")
    p = sub.add_parser("defer", help="暂缓判断 audit 候选，并在后续继续显示")
    p.add_argument("candidate", help="lint --audit 输出的候选 ID")
    p = sub.add_parser("boot", help="输出当前任务与相关知识的精简上下文")
    p.add_argument("term", nargs="*", default=[], help="当前任务或话题关键词")
    sub.add_parser("ready", help="列出运行中续接候选与依赖已满足的任务")
    p = sub.add_parser("list", help="列出所有任务和知识节点", description="输出紧凑表格，也可筛选、按任务层级展示或输出 JSON。")
    p.add_argument("--type", choices=("all", "task", "knowledge"), default="all", help="节点类型（默认 all）")
    p.add_argument("--status", choices=tuple(sorted(TASK_STATUSES | KNOWLEDGE_STATUSES)), help="按状态精确筛选")
    formats = p.add_mutually_exclusive_group()
    formats.add_argument("--tree", action="store_true", help="按 parent 层级展示任务，并单列知识节点")
    formats.add_argument("--json", action="store_true", help="输出稳定的机器可读 JSON")
    sub.add_parser("drafts", help="列出未 apply 草稿，供中断会话恢复")
    p = sub.add_parser("route", help="解释当前话题召回了哪些知识及其评分")
    p.add_argument("term", help="要展开的关键词")
    p = sub.add_parser("show", help="显示节点及其派生关系")
    p.add_argument("target", help="任务 ID 或 know/... 路径")
    sub.add_parser("close", help="会话收尾：审计、完成证据与提交建议")
    p = sub.add_parser("ingest", help="复制一份外部来源，并列出旧知识候选")
    p.add_argument("file", help="要复制进 .hypha/src/ 的来源文件")
    p = sub.add_parser("search", help="用逗号分隔的字面关键词全文检索知识")
    p.add_argument("keywords", help="逗号分隔关键词，例如 登录,认证,auth,session")
    p.add_argument("--file", action="append", help="只搜索 workspace 内指定文件或目录；可重复使用")
    p.add_argument("--limit", type=int, default=30, help="最多返回的匹配行数（默认 30）")
    sub.add_parser("migrate", help="检查 legacy agreements 并输出语义迁移协议")
    p = sub.add_parser("bootstrap", help="扫描现有项目并生成可审阅的初始任务计划")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="只把候选计划输出到 stdout")
    group.add_argument("--output", help="把候选计划写到 workspace 内的指定 JSON 文件")
    group.add_argument("--apply", dest="apply_plan", help="校验并应用已审阅的 bootstrap plan")
    p = sub.add_parser("view", help="生成可拖拽缩放的任务/知识 Canvas 面板")
    p.add_argument("--mode", choices=("all", "tasks", "knowledge"), default="all", help="初始图层：all、tasks 或 knowledge")
    p.add_argument("--open", action="store_true", help="生成后用系统默认浏览器打开（Linux 使用 xdg-open）")
    args = parser.parse_args()
    try:
        if args.global_store and args.command not in GLOBAL_COMMANDS:
            raise ValueError(f"--global 不支持 {args.command}；任务治理必须使用 workspace-local .hypha")
        if args.command == "init": init(args)
        elif args.command == "add": add(args)
        elif args.command in {"start", "progress", "block", "done", "drop"}: task_mutate(args)
        elif args.command == "needs": needs(args)
        elif args.command == "parent": set_parent(args)
        elif args.command == "apply": apply(args)
        elif args.command == "lint": lint(args)
        elif args.command == "dismiss": dismiss(args)
        elif args.command == "defer": defer(args)
        elif args.command == "boot": args.term = " ".join(args.term); boot(args)
        elif args.command == "ready": ready(args)
        elif args.command == "list": list_nodes(args)
        elif args.command == "drafts": drafts_command(args)
        elif args.command == "route": route_command(args)
        elif args.command == "show": show(args)
        elif args.command == "close": close(args)
        elif args.command == "ingest": ingest(args)
        elif args.command == "search": search(args)
        elif args.command == "migrate": migrate(args)
        elif args.command == "bootstrap": bootstrap(args)
        else: view(args)
    except (TypeError, ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr); raise SystemExit(2)


if __name__ == "__main__": main()
