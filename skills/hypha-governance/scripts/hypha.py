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


def pending_drafts(home: Path) -> list[tuple[Path, str, str, str]]:
    """List recoverable drafts without treating malformed work as formal state."""
    found = []
    for path in sorted((home / ".drafts").glob("*.md")):
        try:
            node = read_node(path)
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


def view(args):
    home = root(args)
    with locked(home): tasks, knowledge = prepare(home)
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
        "initialMode": args.mode,
        "tasks": {key: {"title": node["title"], "status": node.get("status")} for key, node in tasks.items()},
        "knowledge": {key: {"title": node["title"], "claim_kind": node.get("claim_kind")} for key, node in knowledge.items()},
        "edges": edges,
        "redlinks": sorted(relations["redlinks"]),
        "events": read_events(home),
    }
    page = """<!doctype html>
<meta charset=utf-8><title>Hypha canvas</title>
<style>
:root{color:#142033;background:#f3f5f8;font:14px system-ui,sans-serif}*{box-sizing:border-box}body{margin:0}main{max-width:1440px;margin:auto;padding:22px}header{display:flex;align-items:baseline;gap:14px}h1{font-size:22px;margin:0}header p{margin:0;color:#5c677a}.toolbar{display:flex;gap:7px;align-items:center;margin:18px 0 12px;flex-wrap:wrap}button{border:1px solid #a9b4c3;background:#fff;color:#263247;padding:7px 11px;cursor:pointer}button.active{background:#1d4ed8;border-color:#1d4ed8;color:#fff}.hint{margin-left:auto;color:#5c677a;font-size:12px}.board{height:680px;display:grid;grid-template-columns:minmax(0,1fr) 270px;border:1px solid #d5dbe5;background:#fff}.canvas-wrap{position:relative;min-width:0;overflow:hidden}canvas{display:block;width:100%;height:100%;cursor:grab;touch-action:none}.canvas-wrap.dragging canvas{cursor:grabbing}aside{border-left:1px solid #d5dbe5;padding:16px;overflow:auto;background:#fafbfd}aside h2{font-size:14px;margin:0 0 12px}aside p{line-height:1.5;color:#536074}dl{margin:0}dt{font-size:11px;text-transform:uppercase;color:#6b7688;margin-top:13px}dd{margin:3px 0;word-break:break-word}.legend{display:grid;gap:7px;font-size:12px;color:#536074}.dot{display:inline-block;width:9px;height:9px;margin-right:6px}.dot.task{background:#2563eb}.dot.knowledge{background:#9333ea}.line{display:inline-block;width:20px;border-top:2px solid #0f766e;margin-right:6px}.line.wiki{border-color:#7c3aed}.line.affects{border-color:#c2410c}@media(max-width:800px){main{padding:12px}.board{grid-template-columns:1fr;height:720px}aside{border-left:0;border-top:1px solid #d5dbe5;max-height:210px}.hint{width:100%;margin-left:0}}</style>
<main><header><h1>Hypha canvas</h1><p>拖拽节点 · 拖拽空白处平移 · 滚轮缩放 · 点击查看详情</p></header><div class=toolbar><button data-mode=all>全部关系</button><button data-mode=tasks>任务 DAG</button><button data-mode=knowledge>知识关系</button><button id=reset>重置视图</button><span class=hint>父子 / 依赖 / 双链 / affects</span></div><section class=board><div class=canvas-wrap id=canvas-wrap><canvas id=graph aria-label="Hypha 可交互关系图"></canvas></div><aside id=detail><h2>节点详情</h2><p>选择一个节点，查看它的类型、状态和相邻关系。</p><div class=legend><span><i class="dot task"></i>任务</span><span><i class="dot knowledge"></i>知识</span><span><i class=line></i>依赖</span><span><i class="line wiki"></i>双链</span><span><i class="line affects"></i>affects</span></div></aside></section></main>
<script>const DATA=""" + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + r""";
const canvas=document.querySelector('#graph'),ctx=canvas.getContext('2d'),wrap=document.querySelector('#canvas-wrap'),detail=document.querySelector('#detail');
const view={x:0,y:0,scale:1},nodeSize={w:156,h:58},positions=new Map(),modes=['all','tasks','knowledge'];let mode=modes.includes(DATA.initialMode)?DATA.initialMode:'all',selected=null,gesture=null;
const nodes=[...Object.entries(DATA.tasks).map(([id,n])=>({id,type:'task',...n})),...Object.entries(DATA.knowledge).map(([id,n])=>({id,type:'knowledge',...n}))];
function visibleEdge(edge){return mode==='all'||(mode==='tasks'&&['parent','depends'].includes(edge.kind))||(mode==='knowledge'&&edge.kind==='wiki')}
function visibleNodes(){return nodes.filter(n=>mode==='all'||n.type===(mode==='tasks'?'task':'knowledge'))}
function layout(){const shown=visibleNodes(),cols=Math.max(1,Math.ceil(Math.sqrt(shown.length||1)));shown.forEach((n,i)=>{if(!positions.has(n.id)||mode!==positions.get(n.id).mode)positions.set(n.id,{x:130+(i%cols)*225,y:110+Math.floor(i/cols)*130,mode})})}
function resize(){const r=wrap.getBoundingClientRect(),dpr=devicePixelRatio||1;canvas.width=r.width*dpr;canvas.height=r.height*dpr;canvas.style.width=r.width+'px';canvas.style.height=r.height+'px';ctx.setTransform(dpr,0,0,dpr,0,0);draw()}
function screen(p){return{x:p.x*view.scale+view.x,y:p.y*view.scale+view.y}}
function world(p){return{x:(p.x-view.x)/view.scale,y:(p.y-view.y)/view.scale}}
function trim(text,max=21){return text.length>max?text.slice(0,max-1)+'…':text}
function edgeStyle(kind){return kind==='depends'?'#0f766e':kind==='wiki'?'#7c3aed':kind==='affects'?'#c2410c':'#64748b'}
function arrow(a,b,color,dashed){const dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1,ux=dx/len,uy=dy/len,end={x:b.x-ux*40,y:b.y-uy*30};ctx.save();ctx.strokeStyle=color;ctx.lineWidth=kindWidth(color);ctx.setLineDash(dashed?[7,5]:[]);ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(end.x,end.y);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(end.x,end.y);ctx.lineTo(end.x-9*ux+5*uy,end.y-9*uy-5*ux);ctx.lineTo(end.x-9*ux-5*uy,end.y-9*uy+5*ux);ctx.closePath();ctx.fill();ctx.restore()}
function kindWidth(color){return color==='#c2410c'?2.4:1.5}
function draw(){const r=wrap.getBoundingClientRect();ctx.clearRect(0,0,r.width,r.height);layout();const shown=visibleNodes(),ids=new Set(shown.map(n=>n.id));ctx.fillStyle='#f8fafc';ctx.fillRect(0,0,r.width,r.height);for(const edge of DATA.edges.filter(e=>visibleEdge(e)&&ids.has(e.from)&&ids.has(e.to))){const a=screen(positions.get(edge.from)),b=screen(positions.get(edge.to));arrow(a,b,edgeStyle(edge.kind),edge.kind==='depends')}for(const n of shown){const p=screen(positions.get(n.id)),w=nodeSize.w*view.scale,h=nodeSize.h*view.scale;ctx.save();ctx.translate(p.x,p.y);ctx.fillStyle=n.type==='task'?'#dbeafe':'#f3e8ff';ctx.strokeStyle=selected===n.id?'#111827':n.type==='task'?'#2563eb':'#9333ea';ctx.lineWidth=selected===n.id?3:1.5;ctx.beginPath();ctx.roundRect(-w/2,-h/2,w,h,6);ctx.fill();ctx.stroke();ctx.fillStyle='#182338';ctx.font=`${12*view.scale}px system-ui`;ctx.fillText(trim(n.id+' · '+n.title),-w/2+10*view.scale,-4*view.scale);ctx.fillStyle='#526176';ctx.font=`${11*view.scale}px system-ui`;ctx.fillText(n.type==='task'?(n.status||'todo'):(n.claim_kind||'note'),-w/2+10*view.scale,17*view.scale);ctx.restore()}}
function hit(point){const p=world(point);return visibleNodes().reverse().find(n=>{const q=positions.get(n.id);return Math.abs(p.x-q.x)<=nodeSize.w/2&&Math.abs(p.y-q.y)<=nodeSize.h/2})}
function select(node){selected=node?node.id:null;if(!node){detail.innerHTML='<h2>节点详情</h2><p>选择一个节点，查看它的类型、状态和相邻关系。</p>';draw();return}const connected=[...new Set(DATA.edges.filter(e=>e.from===node.id||e.to===node.id).map(e=>`${e.kind}: ${e.from===node.id?e.to:e.from}`))];detail.innerHTML=`<h2>${esc(node.title)}</h2><dl><dt>ID</dt><dd>${esc(node.id)}</dd><dt>类型</dt><dd>${node.type==='task'?'任务':'知识'}</dd><dt>${node.type==='task'?'状态':'断言类型'}</dt><dd>${esc(node.status||node.claim_kind||'—')}</dd><dt>关系</dt><dd>${connected.length?connected.map(esc).join('<br>'):'无直接关系'}</dd></dl>`;draw()}
function esc(text){return String(text).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
canvas.addEventListener('pointerdown',event=>{const p={x:event.offsetX,y:event.offsetY},n=hit(p);canvas.setPointerCapture(event.pointerId);gesture={p,n,origin:n?{...positions.get(n.id)}:{x:view.x,y:view.y}};wrap.classList.add('dragging')});canvas.addEventListener('pointermove',event=>{if(!gesture)return;const p={x:event.offsetX,y:event.offsetY},dx=p.x-gesture.p.x,dy=p.y-gesture.p.y;if(gesture.n){const q=positions.get(gesture.n.id);q.x=gesture.origin.x+dx/view.scale;q.y=gesture.origin.y+dy/view.scale}else{view.x=gesture.origin.x+dx;view.y=gesture.origin.y+dy}draw()});canvas.addEventListener('pointerup',event=>{if(gesture&&Math.hypot(event.offsetX-gesture.p.x,event.offsetY-gesture.p.y)<4)select(gesture.n);gesture=null;wrap.classList.remove('dragging')});canvas.addEventListener('wheel',event=>{event.preventDefault();const before=world({x:event.offsetX,y:event.offsetY});view.scale=Math.min(2.4,Math.max(.35,view.scale*(event.deltaY<0?1.12:.89)));view.x=event.offsetX-before.x*view.scale;view.y=event.offsetY-before.y*view.scale;draw()},{passive:false});document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{mode=button.dataset.mode;selected=null;view.x=0;view.y=0;view.scale=1;document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b===button));draw()}));document.querySelector('#reset').addEventListener('click',()=>{view.x=0;view.y=0;view.scale=1;draw()});document.querySelector(`[data-mode="${mode}"]`).classList.add('active');new ResizeObserver(resize).observe(wrap);resize();
</script>"""
    atomic_write(home / "view.html", page)
    print(home / "view.html")


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
    for name in ("start", "done", "drop"):
        actions = {"start": "开始执行任务", "done": "标记任务完成", "drop": "放弃任务"}
        p = sub.add_parser(name, help=actions[name]); p.add_argument("id", help="任务 ID")
    p = sub.add_parser("progress", help="更新任务进度（0 到 100）")
    p.add_argument("id", help="任务 ID"); p.add_argument("value", help="进度整数，例如 60")
    p = sub.add_parser("block", help="标记任务受阻并记录原因")
    p.add_argument("id", help="任务 ID"); p.add_argument("value", help="阻塞原因")
    p = sub.add_parser("needs", help="声明任务依赖，形成 DAG 边")
    p.add_argument("id", help="依赖方任务 ID"); p.add_argument("dependency", help="必须先完成的任务 ID")
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
    p = sub.add_parser("view", help="生成可拖拽缩放的任务/知识 Canvas 面板")
    p.add_argument("--mode", choices=("all", "tasks", "knowledge"), default="all", help="初始图层：all、tasks 或 knowledge")
    args = parser.parse_args()
    try:
        if args.command == "init": init(args)
        elif args.command == "add": add(args)
        elif args.command in {"start", "progress", "block", "done", "drop"}: task_mutate(args)
        elif args.command == "needs": needs(args)
        elif args.command == "apply": apply(args)
        elif args.command == "lint": lint(args)
        elif args.command == "resolve": resolve(args)
        elif args.command == "boot": args.term = " ".join(args.term); boot(args)
        elif args.command == "next": next_task(args)
        elif args.command == "drafts": drafts_command(args)
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
