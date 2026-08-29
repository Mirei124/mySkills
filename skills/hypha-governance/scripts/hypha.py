#!/usr/bin/env python3
"""Hypha: local task and knowledge graph CLI (stdlib-only MVP)."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
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
CLAIM_KINDS = {"sourced", "inference", "note"}
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
WORD = re.compile(r"[\w-]+", re.UNICODE)
BOOTSTRAP_EXCLUDED = {".git", ".hypha", "node_modules", "dist", "build", "target", "vendor", "__pycache__", ".venv"}
BOOTSTRAP_TEXT_SUFFIXES = {".md", ".txt", ".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go", ".java", ".kt", ".rb", ".php", ".cs", ".c", ".h", ".cpp", ".hpp"}


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
    errors = []
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


def workspace_files(workspace: Path) -> list[Path]:
    """Return a bounded, deterministic inventory without relying on Git alone."""
    found = set()
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
            if not any(part in BOOTSTRAP_EXCLUDED for part in relative.parts): found.add(relative)
            if len(found) >= 5000: break
        if len(found) >= 5000: break
    return sorted(path for path in found
                  if not any(part in BOOTSTRAP_EXCLUDED or (part.startswith(".") and part != ".github") for part in path.parts))[:5000]


def bootstrap_signals(workspace: Path, paths: list[Path]) -> dict:
    checked = unchecked = todos = 0
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
        checked += len(re.findall(r"(?im)^\s*[-*]\s*\[[xX]\]", text))
        unchecked += len(re.findall(r"(?im)^\s*[-*]\s*\[ \]", text))
        todos += len(re.findall(r"(?i)\b(?:TODO|FIXME)\b", text))
    return {"files": len(paths), "tests": tests, "markdown": markdown, "checked": checked, "unchecked": unchecked, "todos": todos}


def estimated_progress(signals: dict) -> tuple[int, list[str]]:
    checklist_total = signals["checked"] + signals["unchecked"]
    evidence = [f"{signals['files']} files"]
    if checklist_total:
        progress = round(100 * signals["checked"] / checklist_total)
        evidence.append(f"checklist {signals['checked']}/{checklist_total} complete")
    else:
        progress = 35
        if signals["tests"]:
            progress += 20; evidence.append(f"{signals['tests']} test/spec files")
        if signals["markdown"]:
            progress += 10; evidence.append(f"{signals['markdown']} documentation files")
    if signals["todos"]:
        progress -= min(20, signals["todos"] * 2); evidence.append(f"{signals['todos']} TODO/FIXME markers")
    return max(0, min(100, progress)), evidence


def build_bootstrap_plan(workspace: Path) -> dict:
    paths = workspace_files(workspace)
    groups = defaultdict(list)
    for path in paths:
        if len(path.parts) > 1: groups[path.parts[0]].append(path)
    areas = []
    for name, area_paths in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))[:12]:
        signals = bootstrap_signals(workspace, area_paths)
        progress, evidence = estimated_progress(signals)
        areas.append({"key": f"area:{name}", "title": f"Review and maintain {name}", "parent": "root",
                      "status": "done" if progress == 100 else "in_progress", "progress": progress,
                      "confidence": "low", "evidence": evidence, "signals": signals, "paths": [name]})
    all_signals = bootstrap_signals(workspace, paths)
    root_progress = round(sum(item["progress"] * max(1, item["signals"]["files"]) for item in areas)
                          / max(1, sum(item["signals"]["files"] for item in areas))) if areas else estimated_progress(all_signals)[0]
    root_task = {"key": "root", "title": f"Adopt and maintain {workspace.name}", "parent": None,
                 "status": "done" if root_progress == 100 else "in_progress", "progress": root_progress,
                 "confidence": "low", "evidence": [f"inventory covers {all_signals['files']} files", f"{len(areas)} top-level areas"], "paths": ["."]}
    return {"schemaVersion": 1, "kind": "hypha-bootstrap-plan", "workspace": workspace.name,
            "warning": "Progress is a low-confidence maturity estimate; review every task before apply.",
            "inventory": all_signals, "tasks": [root_task, *areas]}


def apply_bootstrap_plan(home: Path, plan: dict) -> list[str]:
    if plan.get("schemaVersion") != 1 or plan.get("kind") != "hypha-bootstrap-plan":
        raise ValueError("无效 bootstrap plan schema")
    entries = plan.get("tasks")
    if not isinstance(entries, list) or not entries: raise ValueError("bootstrap plan 缺少 tasks")
    tasks, knowledge = prepare(home)
    if tasks: raise ValueError("bootstrap --apply 仅支持空任务图；已有任务请使用 add/parent")
    keys = [entry.get("key") for entry in entries if isinstance(entry, dict)]
    if len(keys) != len(entries) or len(set(keys)) != len(keys) or any(not key for key in keys):
        raise ValueError("bootstrap plan task key 必须唯一且非空")
    ids = {key: f"{index:04d}" for index, key in enumerate(keys, 1)}
    proposed = {}
    paths = []
    for entry in entries:
        progress = entry.get("progress")
        if not isinstance(progress, int) or not 0 <= progress <= 100: raise ValueError("bootstrap progress 必须为 0..100 整数")
        status = entry.get("status", "in_progress")
        if status == "done" and progress != 100: raise ValueError("bootstrap done 任务的 progress 必须为 100")
        parent_key = entry.get("parent")
        if parent_key is not None and parent_key not in ids: raise ValueError(f"bootstrap parent 不存在：{parent_key}")
        task_id = ids[entry["key"]]
        title = str(entry.get("title", "")).strip()
        if not title: raise ValueError("bootstrap task title 不能为空")
        slug = re.sub(r"[^\w\-]+", "-", title.lower()).strip("-") or task_id
        path = home / "intent" / f"{task_id}-{slug[:40]}.md"
        evidence = [str(item) for item in entry.get("evidence", [])]
        body = "\n# " + title + "\n\n## 验收\n\n- Review this bootstrap candidate against the repository's actual goals.\n\n## 证据\n\n" + "\n".join(f"- {item}" for item in evidence) + "\n"
        node = {"id": task_id, "status": status, "progress": progress, "bootstrap_confidence": entry.get("confidence", "low"),
                "bootstrap_paths": [str(item) for item in entry.get("paths", [])], "_body": body, "_path": path, "title": title}
        if parent_key is not None: node["parent"] = ids[parent_key]
        proposed[task_id] = node; paths.append(path)
    errors = validate(home, proposed, knowledge)
    if errors: raise ValueError("\n".join(errors))
    (home / "intent").mkdir(parents=True, exist_ok=True)
    for task_id, node in proposed.items(): write_node(node["_path"], node, atomic=True)
    sync(home, by="bootstrap")
    return [str(path.relative_to(home)) for path in paths]


def init(args):
    home = root(args)
    with locked(home):
        for name in ("src", "intent", "know", ".drafts", "snapshots", "agreements"):
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
              "superseded_by", "claim_kind", "anchors", "evidence", "inference", "when", "triggers")
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
        errors = validate(home, probe, knowledge)
        if errors: raise ValueError("\n".join(errors))
        write_node(path, node, atomic=True)
        sync(home, by="cli")
    print(f"已创建 {task_id}: {path.relative_to(home)}")


def task_mutate(args):
    home = root(args)
    with locked(home):
        tasks, knowledge = prepare(home); node = tasks.get(args.id)
        if not node: raise ValueError(f"不存在任务 {args.id}")
        if args.command == "progress":
            value = int(args.value)
            if not 0 <= value <= 100: raise ValueError("progress 必须为 0..100")
            node["progress"] = value
        elif args.command == "block": node["status"] = "blocked"; node["blocked_reason"] = args.value
        else:
            node["status"] = {"start": "in_progress", "done": "done", "drop": "dropped"}[args.command]
            node.pop("blocked_reason", None)
            if args.command == "done": node["progress"] = 100
        errors = validate(home, tasks, knowledge)
        if errors: raise ValueError("\n".join(errors))
        write_node(node["_path"], node, atomic=True)
        sync(home, by="cli")
    print(f"已更新 {args.id}: {node['status']}")


def lint(args):
    home = root(args)
    with locked(home):
        tasks, knowledge = prepare(home); errors = validate(home, tasks, knowledge)
        ignored = (home / ".gitignore").read_text(encoding="utf-8") if (home / ".gitignore").exists() else ""
        if "lock" not in ignored: errors.append(".hypha/.gitignore 必须忽略 lock")
        if ".drafts/" in ignored: errors.append(".hypha/.drafts/ 是跨机器恢复状态，不能被忽略")
        if workspace_ignores_hypha(home.parent): errors.append("工作区 Git 忽略了 .hypha/")
        if args.audit: audit(home, tasks, knowledge)
        errors.extend(trigger_errors(knowledge))
        unmanaged = unmanaged_fields(home, tasks, knowledge)
        if unmanaged:
            print("提示：检测到未托管正式写入（已审计，建议下次使用草稿 + apply）：")
            for item in unmanaged[:12]: print("- " + item)
        if args.fix and not errors: rebuild_index(home)
    if errors:
        print("\n".join("错误：" + e for e in errors)); raise SystemExit(1)
    print("lint 通过")


def trigger_errors(knowledge: dict) -> list[str]:
    population = max(len(knowledge), 1); counts = defaultdict(int)
    for node in knowledge.values():
        if node.get("claim_kind") != "note":
            for trigger in set(knowledge_triggers(node)): counts[trigger] += 1
    return [f"trigger 过宽：{trigger} 命中 {count}/{population} 条知识" for trigger, count in counts.items() if count / population > .2 and count > 1]


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
    unresolved = [candidate for candidate in audit_candidates(tasks, knowledge) if candidate_id(candidate) not in resolutions]
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


def resolve(args):
    home = root(args)
    with locked(home):
        prepare(home)
        path = home / "audit-resolutions.jsonl"
        record = {
            "candidate": args.candidate,
            "resolution": args.resolution,
            "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    print(f"已记录 {args.candidate}: {args.resolution}")


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
        errors = validate(home, tasks, knowledge)
        if errors: raise ValueError("\n".join(errors))
        write_node(tasks[args.id]["_path"], tasks[args.id], atomic=True)
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
        errors = validate(home, tasks, knowledge)
        if errors: raise ValueError("\n".join(errors))
        write_node(target, node, atomic=True); sync(home, by="apply")
        mark_draft_applied(home, draft)
    print(f"已发布 {target.relative_to(home)}")


def route(tasks: dict, knowledge: dict, text: str) -> list[tuple[int, str, dict]]:
    terms = {x.casefold() for x in WORD.findall(text)}
    scored = []
    for path, node in knowledge.items():
        if node.get("claim_kind") == "note" or node.get("status", "active") != "active": continue
        triggers = knowledge_triggers(node)
        score = 5 * len(terms & {str(x).casefold() for x in triggers}) + 2 * len(terms & {x.casefold() for x in WORD.findall(node["title"])})
        score += 2 * sum(str(x) in tasks and tasks[str(x)].get("status") in {"todo", "in_progress", "blocked"} for x in node.get("affects", []))
        if score: scored.append((score, path, node))
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
    if not events:
        return False
    latest = events[-1]
    return not (latest.get("kind") == "session" and latest.get("to") == "close")


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


def done_today(home: Path) -> set[str]:
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    return {str(event["id"]) for event in read_events(home)
            if event.get("kind") == "intent" and event.get("field") == "status"
            and event.get("to") == "done" and str(event.get("recorded_at", "")).startswith(today)}


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
        print("不可协商：")
        for path in agreements: print(f"- agreements/{path.name}")
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
    print("下一步：hypha next")


def next_task(args):
    home = root(args)
    with locked(home): tasks, _ = prepare(home)
    running = [(task_id, node) for task_id, node in sorted(tasks.items()) if node.get("status") == "in_progress"]
    if running:
        print("运行中（续接候选）：")
        for task_id, node in running:
            progress = f" {node['progress']}%" if "progress" in node else ""
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
    rows = []
    if args.type in {"all", "task"}:
        for task_id, node in sorted(tasks.items()):
            status = str(node.get("status", "todo"))
            if args.status and status != args.status:
                continue
            rows.append({
                "id": task_id, "type": "task", "title": node["title"], "status": status,
                "progress": node.get("progress"), "parent": node.get("parent"),
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
                "claim_kind": node.get("claim_kind"), "path": str(node["_path"].relative_to(home)),
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


def why(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    for score, path, node in route(tasks, knowledge, args.term):
        print(f"{path}\tscore={score}\twhen={node.get('when', '')}\ttriggers={','.join(knowledge_triggers(node))}")


def close(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    print("运行中：" + ", ".join(k for k,v in tasks.items() if v.get("status") == "in_progress"))
    print("受阻：" + ", ".join(k for k,v in tasks.items() if v.get("status") == "blocked"))
    redlinks = graph(tasks, knowledge)["redlinks"]
    print("红链：" + ", ".join(sorted(redlinks)))
    audit(home, tasks, knowledge)
    done = done_today(home)
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
    print("下一步：在 .hypha/.drafts/ 写候选节点；判断关系后执行 hypha apply <draft>")


def ask(args):
    """Expose deterministic local context; assertion generation remains agent work."""
    home = root(args)
    with locked(home): _tasks, knowledge = prepare(home)
    terms = {x.casefold() for x in WORD.findall(args.question)}
    for path, node in sorted(knowledge.items()):
        text = node["title"] + " " + " ".join(map(str, knowledge_triggers(node)))
        if terms & {x.casefold() for x in WORD.findall(text)}: print(path)


def migrate(args):
    home = root(args)
    with locked(home):
        tasks, knowledge = prepare(home)
        errors = validate(home, tasks, knowledge)
        if errors: raise ValueError("\n".join(errors))
        sync(home, by="migrate")
    print("迁移检查完成；现有 markdown 保持不变。")


def bootstrap(args):
    if args.global_store: raise ValueError("bootstrap 仅支持 workspace，不支持 --global")
    workspace, home = Path(args.workspace).resolve(), root(args)
    if args.apply_plan:
        plan_path = Path(args.apply_plan).resolve()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not home.is_dir(): raise ValueError("尚未 init；请先运行 hypha init")
        with locked(home): created = apply_bootstrap_plan(home, plan)
        print(f"已从 bootstrap plan 创建 {len(created)} 个任务")
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
    print(f"检查并编辑后运行：hypha --workspace {workspace} bootstrap --apply {target}")


def view(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    events = read_events(home)
    observation_times = node_observation_times(events)
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
                "title": node["title"], "status": node.get("status"), "progress": node.get("progress"),
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
                "metadata": {field: node.get(field) for field in ("affects", "when", "triggers", "anchors") if field in node},
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
    for key in ("status", "progress", "parent", "depends_on", "affects", "when"):
        if key in n: print(f"{key}: {n[key]}")
    relations = graph(tasks, knowledge)
    if args.target in tasks:
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
    p.add_argument("--fix", action="store_true", help="重建派生索引（默认也会同步索引）")
    p.add_argument("--audit", action="store_true", help="额外列出可能缺失的关系和路由候选")
    p = sub.add_parser("resolve", help="持久化一项 audit 候选的人工判定")
    p.add_argument("candidate", help="lint --audit 输出的候选 ID")
    p.add_argument("resolution", choices=("related", "unrelated", "deferred"), help="人工判定结果")
    p = sub.add_parser("boot", help="输出当前任务与相关知识的精简上下文")
    p.add_argument("term", nargs="*", default=[], help="当前任务或话题关键词")
    sub.add_parser("next", help="列出运行中续接候选与依赖已满足的任务")
    p = sub.add_parser("list", help="列出所有任务和知识节点", description="输出紧凑表格，也可筛选、按任务层级展示或输出 JSON。")
    p.add_argument("--type", choices=("all", "task", "knowledge"), default="all", help="节点类型（默认 all）")
    p.add_argument("--status", choices=tuple(sorted(TASK_STATUSES | KNOWLEDGE_STATUSES)), help="按状态精确筛选")
    formats = p.add_mutually_exclusive_group()
    formats.add_argument("--tree", action="store_true", help="按 parent 层级展示任务，并单列知识节点")
    formats.add_argument("--json", action="store_true", help="输出稳定的机器可读 JSON")
    sub.add_parser("drafts", help="列出未 apply 草稿，供中断会话恢复")
    p = sub.add_parser("why", help="解释关键词命中的知识路由候选")
    p.add_argument("term", help="要展开的关键词")
    p = sub.add_parser("show", help="显示节点及其派生关系")
    p.add_argument("target", help="任务 ID 或 know/... 路径")
    sub.add_parser("close", help="会话收尾：审计、完成证据与提交建议")
    p = sub.add_parser("ingest", help="复制一份外部来源，并列出旧知识候选")
    p.add_argument("file", help="要复制进 .hypha/src/ 的来源文件")
    p = sub.add_parser("ask", help="按问题关键词查找已有知识")
    p.add_argument("question", help="要查找的问题")
    p.add_argument("--file", help="可选的来源文件范围（供后续问答工作流使用）")
    sub.add_parser("migrate", help="校验并同步现有 Hypha Markdown")
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
        if args.command == "init": init(args)
        elif args.command == "add": add(args)
        elif args.command in {"start", "progress", "block", "done", "drop"}: task_mutate(args)
        elif args.command == "needs": needs(args)
        elif args.command == "parent": set_parent(args)
        elif args.command == "apply": apply(args)
        elif args.command == "lint": lint(args)
        elif args.command == "resolve": resolve(args)
        elif args.command == "boot": args.term = " ".join(args.term); boot(args)
        elif args.command == "next": next_task(args)
        elif args.command == "list": list_nodes(args)
        elif args.command == "drafts": drafts_command(args)
        elif args.command == "why": why(args)
        elif args.command == "show": show(args)
        elif args.command == "close": close(args)
        elif args.command == "ingest": ingest(args)
        elif args.command == "ask": ask(args)
        elif args.command == "migrate": migrate(args)
        elif args.command == "bootstrap": bootstrap(args)
        else: view(args)
    except (ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr); raise SystemExit(2)


if __name__ == "__main__": main()
