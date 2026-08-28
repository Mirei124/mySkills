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
import time
import uuid
from collections import defaultdict
from pathlib import Path

TASK_STATUSES = {"todo", "in_progress", "blocked", "done", "dropped"}
KNOWLEDGE_STATUSES = {"active", "superseded"}
CLAIM_KINDS = {"sourced", "inference", "note"}
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
WORD = re.compile(r"[\w-]+", re.UNICODE)


def root(args: argparse.Namespace) -> Path:
    if getattr(args, "global_store", False):
        return Path.home() / ".hypha"
    return Path(args.workspace).resolve() / ".hypha"


def parse_value(value: str):
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        return [part.strip().strip('"\'') for part in value[1:-1].split(",") if part.strip()]
    # IDs are fixed-width strings: YAML-style integer coercion must not turn
    # 0007 into 7 (the same applies to IDs inside inline relationship lists).
    if value.isdigit() and (value == "0" or not value.startswith("0")):
        return int(value)
    return value.strip('"\'')


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
        elif isinstance(value, list): front.append(f"{key}: [" + ", ".join(quote_value(x) for x in value) + "]")
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
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        except ImportError:
            pass
        yield
    finally:
        with contextlib.suppress(Exception):
            import fcntl; fcntl.flock(fd, fcntl.LOCK_UN)
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


def init(args):
    home = root(args)
    with locked(home):
        for name in ("src", "intent", "know", ".drafts", "snapshots", "agreements"):
            (home / name).mkdir(parents=True, exist_ok=True)
        atomic_write(home / ".gitignore", "lock\n.drafts/\nview.html\n")
        atomic_write(home / ".gitattributes", "snapshots/*.jsonl merge=union\n")
        sync(home)
    print(f"已初始化 {home}")


def rebuild_index(home: Path):
    tasks, knowledge = scan(home)
    rows = ["# Hypha index", "", "## Tasks", ""]
    rows += [f"- intent/{task_id} | [{n.get('status')}] | {n['title']}" for task_id, n in sorted(tasks.items())]
    rows += ["", "## Knowledge", ""]
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
            if stamp < last_stamp: stamp = last_stamp
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
        if "lock" not in ignored or ".drafts/" not in ignored: errors.append(".hypha/.gitignore 必须忽略 lock 和 .drafts/")
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
        result = subprocess.run(["git", "-C", str(workspace), "check-ignore", "-q", ".hypha"], check=False)
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


def audit(home: Path, tasks: dict, knowledge: dict) -> None:
    """Heuristic-only audit; it never changes nodes or task state."""
    print("audit（候选，需人工判断）：")
    for task_id, task in sorted(tasks.items()):
        if task.get("status") not in {"todo", "in_progress", "blocked"}: continue
        terms = {x.casefold() for x in WORD.findall(task["title"])}
        matches = []
        for path, node in knowledge.items():
            if node.get("claim_kind") == "note": continue
            words = {x.casefold() for x in WORD.findall(node["title"] + " " + " ".join(map(str, node.get("triggers", []))))}
            if terms & words and task_id not in map(str, node.get("affects", [])): matches.append(path)
        if matches: print(f"- {task_id}: 可能缺 affects/正文链接：{', '.join(matches[:4])}")
    print("路由预演：")
    for task_id, task in sorted(tasks.items()):
        if task.get("status") in {"todo", "in_progress", "blocked"}:
            candidates = route(tasks, knowledge, task["title"])
            print(f"- {task_id}: {', '.join(path for _, path, _ in candidates[:4]) or '无'}")


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


def apply(args):
    home, draft = root(args), Path(args.draft).resolve()
    drafts = (home / ".drafts").resolve()
    if drafts not in draft.parents: raise ValueError("草稿必须位于 .hypha/.drafts/")
    with locked(home):
        node = read_node(draft)
        if node.get("id") is not None:
            kind, ident = "intent", str(node["id"])
            slug = re.sub(r"[^\w-]+", "-", node["title"].lower()).strip("-") or ident
            target = home / kind / f"{ident}-{slug[:40]}.md"
        else:
            kind = "know"; slug = re.sub(r"[^\w-]+", "-", node["title"].lower()).strip("-")
            target = home / kind / f"{slug or hashlib.sha256(draft.read_bytes()).hexdigest()[:12]}.md"; ident = str(target.relative_to(home)).removesuffix(".md")
            node.setdefault("status", "active")
            node.setdefault("triggers", knowledge_triggers(node))
        tasks, knowledge = prepare(home)
        if kind == "intent" and ident in tasks and tasks[ident]["_path"].resolve() != target.resolve():
            raise ValueError(f"任务 ID 已存在：{ident}")
        if kind == "intent": tasks[ident] = node
        else:
            incoming_hash = audit_projection(node)["body_hash"]
            duplicate = next((path for path, old in knowledge.items() if audit_projection(old)["body_hash"] == incoming_hash and path != ident), None)
            if duplicate: raise ValueError(f"草稿内容已发布为 {duplicate}")
            knowledge[ident] = node
        errors = validate(home, tasks, knowledge)
        if errors: raise ValueError("\n".join(errors))
        write_node(target, node, atomic=True); sync(home, by="apply")
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
    print("下一步：hypha next")


def next_task(args):
    home = root(args)
    with locked(home): tasks, _ = prepare(home)
    for task_id, node in sorted(tasks.items()):
        if node.get("status") == "todo" and all(tasks[str(dep)].get("status") == "done" for dep in node.get("depends_on", [])):
            print(f"{task_id} {node['title']}")
    print("下一步：hypha start <id>")


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
    with locked(home): tasks, knowledge = prepare(home)
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


def view(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    relations = graph(tasks, knowledge)
    data = {"tasks": {k: {"title": v["title"], "status": v.get("status"), "parent": v.get("parent"), "depends_on": v.get("depends_on", [])} for k,v in tasks.items()}, "knowledge": {k: {"title":v["title"], "affects":v.get("affects", []), "backlinks":sorted(relations["backlinks"].get(k, []))} for k,v in knowledge.items()}, "redlinks":sorted(relations["redlinks"]), "events":read_events(home)}
    atomic_write(home / "view.html", "<!doctype html><meta charset=utf-8><title>Hypha</title><style>body{font:14px system-ui;max-width:1000px;margin:2rem auto}pre{white-space:pre-wrap}</style><h1>Hypha graph and timeline</h1><pre id=x></pre><script>x.textContent=JSON.stringify(" + json.dumps(data, ensure_ascii=False) + ",null,2)</script>")
    print(home / "view.html")


def show(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
    n = tasks.get(args.target) or knowledge.get(args.target.removesuffix(".md"))
    if not n: raise ValueError(f"不存在节点 {args.target}")
    print(n["_path"].relative_to(root(args))); print(n["title"])
    for key in ("status", "parent", "depends_on", "affects", "when"): 
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
    parser = argparse.ArgumentParser(prog="hypha")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--global", dest="global_store", action="store_true", help="use ~/.hypha instead of this workspace")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    p = sub.add_parser("add"); p.add_argument("title"); p.add_argument("parent", nargs="?")
    for name in ("start", "done", "drop"):
        p = sub.add_parser(name); p.add_argument("id")
    p = sub.add_parser("progress"); p.add_argument("id"); p.add_argument("value")
    p = sub.add_parser("block"); p.add_argument("id"); p.add_argument("value")
    p = sub.add_parser("needs"); p.add_argument("id"); p.add_argument("dependency")
    p = sub.add_parser("apply"); p.add_argument("draft")
    p = sub.add_parser("lint"); p.add_argument("--fix", action="store_true"); p.add_argument("--audit", action="store_true")
    p = sub.add_parser("boot"); p.add_argument("term", nargs="*", default=[])
    sub.add_parser("next")
    p = sub.add_parser("why"); p.add_argument("term")
    p = sub.add_parser("show"); p.add_argument("target")
    sub.add_parser("close")
    p = sub.add_parser("ingest"); p.add_argument("file")
    p = sub.add_parser("ask"); p.add_argument("question"); p.add_argument("--file")
    sub.add_parser("migrate")
    sub.add_parser("view")
    args = parser.parse_args()
    try:
        if args.command == "init": init(args)
        elif args.command == "add": add(args)
        elif args.command in {"start", "progress", "block", "done", "drop"}: task_mutate(args)
        elif args.command == "needs": needs(args)
        elif args.command == "apply": apply(args)
        elif args.command == "lint": lint(args)
        elif args.command == "boot": args.term = " ".join(args.term); boot(args)
        elif args.command == "next": next_task(args)
        elif args.command == "why": why(args)
        elif args.command == "show": show(args)
        elif args.command == "close": close(args)
        elif args.command == "ingest": ingest(args)
        elif args.command == "ask": ask(args)
        elif args.command == "migrate": migrate(args)
        else: view(args)
    except (ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr); raise SystemExit(2)


if __name__ == "__main__": main()
