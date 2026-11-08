#!/usr/bin/env python3
"""DibuFusion API CLI using only the Python standard library."""

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAT = json.loads((ROOT / "references/operations.json").read_text())
BASE = "http://10.249.187.159:32320"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def load_json_file(path):
    return json.loads(pathlib.Path(path).read_text())


def auth_config():
    base = os.environ.get("DIBU_BASE_URL", BASE).rstrip("/")
    token_path = pathlib.Path.home() / ".cache" / "dibu_token"
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise ValueError(
            "Cannot read ~/.cache/dibu_token; create a readable UTF-8 file containing only the bare token."
        ) from exc
    if not token:
        raise ValueError("Authentication file ~/.cache/dibu_token is empty.")
    if any(character.isspace() for character in token):
        raise ValueError("Invalid ~/.cache/dibu_token format; store only the bare token.")
    return base, "Token " + token


def value(s):
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return s


def prepare(name, params, body):
    op = CAT[name]
    q = dict(op["query"])
    b = None if op["body"] is None else dict(op["body"])
    path = op["path"]
    for key in list(params):
        marker = "{" + key + "}"
        if marker in path:
            path = path.replace(marker, urllib.parse.quote(str(params.pop(key)), safe=""))
    if "{" in path:
        raise ValueError("Missing path parameter: " + path + "; use " + name + " --help")
    if body is not None:
        if not isinstance(body, dict):
            raise ValueError("JSON request body must be an object")
        b = {**(b or {}), **body}
    if op["method"] in ["GET", "DELETE"]:
        q.update(params)
    else:
        b = {**(b or {}), **params} if params else b
    if name in ["files", "shared-files"] and (
        b.get("action") != "ls" or b.get("is_share_dir", False) != (name == "shared-files")
    ):
        raise ValueError("List operations cannot override action/is_share_dir; use the corresponding file operation")
    if name.startswith("file-") and op["body"] and b.get("action") != op["body"]["action"]:
        raise ValueError("Cannot override the file operation action")
    if name == "dataset-update" and b is not None:
        b["data_id"] = urllib.parse.unquote(path.rstrip("/").rsplit("/", 1)[1])
    for key in op["required"]:
        if key == "body":
            if not b:
                raise ValueError("A request body is required; use --body-file payload.json (see operation --help)")
        elif "{" + key + "}" in op["path"]:
            continue
        elif key not in q and (b is None or key not in b):
            raise ValueError(
                "Missing API field " + key + "; use " + name + " --help for named options or --param " + key + "=VALUE"
            )
    if name in ("container-create", "container-convert"):
        if not isinstance(b.get("password"), str) or not b["password"].strip():
            raise ValueError(
                "password must be a nonempty string; generate it with secrets.token_urlsafe and store it in a mode-600 body file without printing it."
            )
        if b.get("is_VM") is False and not str(b.get("cmd", "")).strip():
            raise ValueError("Tasks require a nonempty cmd; use --command or a request body.")
        selection = b.get("gpu_selection")
        if selection and selection.get("count") != b.get("num_gpu"):
            raise ValueError("gpu_selection.count must match num_gpu.")
    return op, path, q, b


def request(base, auth, op, path, q, b, headers, output=None):
    url = base + path + ("?" + urllib.parse.urlencode(q, doseq=True) if q else "")
    hs = {"Accept": "application/json", "Authorization": auth, **headers}
    data = None
    if b is not None:
        data = json.dumps(b, ensure_ascii=False).encode()
        hs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hs, method=op["method"])
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        detail = e.read(4000).decode(errors="replace")
        for secret in (auth, auth[len("Token ") :], (b or {}).get("password", "")):
            if secret:
                detail = detail.replace(secret, "[REDACTED]")
        if e.code == 401:
            raise ValueError("HTTP 401: authentication expired; update ~/.cache/dibu_token before retrying. " + detail)
        if e.code == 403:
            raise ValueError("HTTP 403: request rejected; diagnose using the server response. " + detail)
        raise ValueError(f"HTTP {e.code}: {detail}")
    if output:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
    try:
        result = json.loads(raw)
        if isinstance(result, dict) and result.get("error"):
            raise ValueError("API error: " + json.dumps(result["error"], ensure_ascii=False))
    except (json.JSONDecodeError, UnicodeDecodeError):
        result = {"status": status, "text": raw.decode(errors="replace")}
    if output:
        return {"status": status, "output": str(output), "bytes": len(raw)}
    return result


def parse_headers(entries):
    """Normalize supported headers before checking duplicates or required values."""
    names = {
        "idempotency-key": "Idempotency-Key",
        "x-dibufusion-estimate-fingerprint": "X-DibuFusion-Estimate-Fingerprint",
    }
    headers = {}
    for entry in entries:
        if ":" not in entry:
            raise ValueError("--header requires NAME:VALUE")
        key, val = entry.split(":", 1)
        name = names.get(key.strip().lower())
        if name is None:
            raise ValueError("Unsupported additional request header")
        if "\r" in val or "\n" in val or not val.strip():
            raise ValueError("Empty or multiline request header: " + name)
        val = val.strip()
        if name in headers and headers[name] != val:
            raise ValueError("Conflicting duplicate request header: " + name)
        headers[name] = val
    return headers


def redact(obj):
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if any(word in k.lower() for word in ("password", "token", "secret")) else redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def resource_summary(dashboard):
    """Keep unknown availability unknown; never count disabled nodes as usable."""
    nodes = []
    for n in dashboard.get("nodes", []):
        ready = n.get("node_status") == "Ready"
        fresh = dashboard.get("stale") is False and not dashboard.get("errors")
        free = n.get("gpu_remain_num")
        usable = free if ready and fresh and isinstance(free, int) else None
        nodes.append(
            {
                "node_id": n["node_id"],
                "node_name": n.get("node_name"),
                "state": n.get("node_status"),
                "gpu_type": n.get("gputype"),
                "reported_free_gpus": free,
                "schedulable_free_gpus": usable,
                "free_cpu_cores": n.get("cpu_remain_num"),
                "free_memory_gib": n.get("mem_remain_num"),
            }
        )
    return {
        "nodes": nodes,
        "dashboard_sampled_at_ms": dashboard.get("sampled_at_ms"),
        "dashboard_stale": dashboard.get("stale"),
        "dashboard_refresh_pending": dashboard.get("refresh_pending"),
        "dashboard_errors": dashboard.get("errors"),
        "note": "Schedulable counts are preflight upper bounds; verify taints, GPU partition mode, CPU/memory, account quota, and scheduling events. null means unknown.",
    }


LIST_IDENTITIES = {
    "tasks": {"container_id"},
    "experiments": {"container_id"},
    "jobs": {"job_id", "id"},
    "images": {"image_id"},
    "files": {"name", "filename", "file_name", "path"},
    "shared-files": {"name", "filename", "file_name", "path"},
    "datasets": {"data_id", "dataset_id", "id"},
}
LIST_FIELDS = {
    "id",
    "container_id",
    "job_id",
    "image_id",
    "data_id",
    "dataset_id",
    "name",
    "lab_name",
    "job_name",
    "image_name",
    "image_tag",
    "data_name",
    "dataset_name",
    "filename",
    "file_name",
    "path",
    "status",
    "state",
    "node_id",
    "node_name",
    "num_gpu",
    "gpu_type",
    "gputype",
    "cpu",
    "memory",
    "create_time",
    "created_at",
    "update_time",
    "updated_at",
    "start_time",
    "end_time",
    "size",
    "file_size",
    "is_dir",
    "type",
    "is_public",
    "permission",
    "permissions",
    "owner",
    "username",
    "note",
    "source",
    "count",
    "error",
    "errors",
    "warning",
    "warnings",
    "message",
    "reason",
    "events",
}
# Only known bulky configuration fields may be omitted. New fields trigger
# full-response fallback so schema changes cannot silently hide diagnostics.
LIST_DETAILS = {
    "password",
    "cmd",
    "command",
    "env",
    "environment",
    "volumes",
    "mounts",
    "gpu_selection",
    "pod_spec",
    "pod_template",
    "metadata",
    "annotations",
    "labels",
}

# Fields observed in read-only live samples on 2026-11-08. Keep scheduling,
# timing, image-save and restart state; connection details remain available raw.
LIST_EXTRA_FIELDS = {
    "tasks": {
        "duration",
        "requested_duration_minutes",
        "cur_duration",
        "add_hours",
        "is_VM",
        "manual_restart_used",
        "image_save",
        "is_committing",
        "timing",
        "can_extend",
        "dra_request",
    },
    "images": {"record_datetime", "tag", "is_push", "node"},
    "files": {"modified_date"},
    "shared-files": {"modified_date"},
}
LIST_EXTRA_FIELDS["experiments"] = LIST_EXTRA_FIELDS["tasks"]
LIST_EXTRA_DETAILS = {
    "tasks": {
        "pod_name",
        "node_ip",
        "outer_ip",
        "port",
        "outer_port",
        "jupyter_port",
        "vnc_port",
    },
    "images": {"nickname", "lab_name"},
}
LIST_EXTRA_DETAILS["experiments"] = LIST_EXTRA_DETAILS["tasks"]
PROFILE_DETAILS = {"wechat_openid", "wechat_avatar_url", "wechat_username"}
PROFILE_FIELDS = {
    "user_id",
    "username",
    "nickname",
    "first_login",
    "grade",
    "email",
    "gputime",
    "gputime_used",
    "gputime_all",
    "date_joined",
    "gender",
    "phone",
}
IMAGE_SAVE_DETAILS = {
    "pod_uid",
    "runtime",
    "job_name",
    "pod_name",
    "username",
    "namespace",
    "container_name",
    "container_name_or_id",
}
IMAGE_SAVE_FIELDS = {"auto", "node_name", "image_name", "is_temporary", "operation_id"}


def compact_response(operation, result):
    """Project recognized lists without changing wrappers or pagination."""
    if operation == "image-save-status" and isinstance(result, dict):
        client = result.get("client_data")
        if isinstance(client, dict) and not (set(client) - IMAGE_SAVE_FIELDS - IMAGE_SAVE_DETAILS):
            return {
                **result,
                "client_data": {key: val for key, val in client.items() if key in IMAGE_SAVE_FIELDS},
            }
        return result
    if operation == "profile":
        if isinstance(result, dict) and "user_id" in result and not (set(result) - PROFILE_FIELDS - PROFILE_DETAILS):
            return {key: val for key, val in result.items() if key not in PROFILE_DETAILS}
        return result
    identities = LIST_IDENTITIES.get(operation)
    if identities is None:
        return result
    keep = LIST_FIELDS | LIST_EXTRA_FIELDS.get(operation, set())
    omit = LIST_DETAILS | LIST_EXTRA_DETAILS.get(operation, set())

    def project(payload):
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
            rows = payload["results"]
        else:
            return payload
        if any(not isinstance(row, dict) or not identities.intersection(row) or set(row) - keep - omit for row in rows):
            return payload
        projected = [{key: val for key, val in row.items() if key in keep} for row in rows]
        return projected if isinstance(payload, list) else {**payload, "results": projected}

    if isinstance(result, dict) and "data" in result:
        return {**result, "data": project(result["data"])}
    return project(result)


def run_summary(operation, params, raw=False):
    base, auth = auth_config()
    responses = []

    def get(name, query):
        op, path, q, b = prepare(name, dict(query), None)
        response = request(base, auth, op, path, q, b, {})
        if raw:
            responses.append({"operation": name, "query": dict(query), "response": response})
        return response

    if operation == "resource-summary":
        if params:
            raise ValueError("resource-summary does not accept parameters")
        dashboard = get("dashboard", {})
        return dashboard if raw else resource_summary(dashboard)
    target = params.pop("container_id", None)
    if operation == "task-status" and target is None:
        raise ValueError("task-status requires --id ID or --param container_id=ID")
    if params:
        raise ValueError("Task summaries only support container_id (--id for task-status)")
    found = {}
    for mode in (1, 2, 0):
        page = 1
        while True:
            data = get("tasks", {"operate_id": mode, "size": 100, "page": page})
            for row in data.get("results", []):
                if target is not None and str(row.get("container_id")) != str(target):
                    continue
                found.setdefault(
                    row["container_id"],
                    {
                        k: row.get(k)
                        for k in (
                            "container_id",
                            "lab_name",
                            "status",
                            "node_name",
                            "num_gpu",
                            "cpu",
                            "memory",
                            "create_time",
                        )
                    },
                )
            if not data.get("next"):
                break
            page += 1
    rows = list(found.values())
    result = {
        "count": len(rows),
        "tasks": rows,
        "note": "Inspect actual status; list category is not runtime state, and finished does not prove application correctness.",
    }
    if target is not None and rows:
        result["events"] = get("events", {"container_id": target}).get("events")
    return {"responses": responses} if raw else result


SUMMARY_OPS = {
    "resource-summary": {
        "description": "Summarize fresh dashboard resources; unknown availability stays unknown",
        "required": [],
        "cli": {"options": [], "examples": ["resource-summary"]},
    },
    "task-summary": {
        "description": "Summarize all task pages; --id inspects one task with events",
        "required": [],
        "cli": {
            "options": [
                {
                    "flags": ["--id"],
                    "field": "container_id",
                    "type": "positive-int",
                    "help": "Optional task ID; include scheduling events",
                }
            ],
            "examples": ["task-summary", "task-summary --id 276"],
        },
    },
    "task-status": {
        "description": "Find one task across categories and attach scheduling events",
        "required": ["container_id"],
        "cli": {
            "options": [
                {
                    "flags": ["--id"],
                    "field": "container_id",
                    "type": "positive-int",
                    "help": "Task container ID",
                }
            ],
            "examples": ["task-status --id 276"],
        },
    },
}


# Public command paths map to existing operations; old flat names remain accepted.
COMMAND_GROUPS = {
    "resources": (
        "Inspect capacity and GPU configuration",
        {"summary": "resource-summary", "inventory": "gpu-inventory"},
    ),
    "tasks": (
        "List tasks, summarize history, or inspect one task",
        {"list": "tasks", "summary": "task-summary"},
    ),
    "experiments": (
        "List and manage interactive experiments",
        {
            "list": "experiments",
            "stop": "experiment-stop",
            "restart": "experiment-restart",
            "restart-status": "restart-status",
            "convert": "container-convert",
        },
    ),
    "jobs": (
        "List and manage distributed jobs",
        {
            "list": "jobs",
            "create": "job-create",
            "delete": "job-delete",
            "history-delete": "job-history-delete",
            "network": "job-network",
            "logs": "job-log",
        },
    ),
    "workloads": (
        "Create tasks/experiments and manage container workloads",
        {
            "create": "container-create",
            "delete": "container-delete",
            "history-delete": "container-history-delete",
            "events": "events",
            "network": "container-network",
            "logs": "container-log",
        },
    ),
    "images": (
        "List images, save snapshots, and edit image metadata",
        {
            "list": "images",
            "save": "image-save",
            "save-status": "image-save-status",
            "visibility": "image-visibility",
            "permanent": "image-permanent",
            "note": "image-note",
            "register": "image-register",
            "delete": "image-delete",
        },
    ),
    "files": (
        "List personal/shared files and manage personal paths",
        {
            "list": "files",
            "mkdir": "file-mkdir",
            "remove": "file-remove",
            "move": "file-move",
            "space": "file-space",
        },
    ),
    "datasets": (
        "List and edit dataset registrations",
        {
            "list": "datasets",
            "create": "dataset-create",
            "update": "dataset-update",
            "delete": "dataset-delete",
        },
    ),
    "account": (
        "Manage profile, credentials, and Tailscale enrollment",
        {
            "profile": "profile",
            "update": "profile-update",
            "password": "password-change",
            "token-info": "access-token-info",
            "token-create": "access-token-create",
            "token-revoke": "access-token-revoke",
            "tailscale-status": "tailscale-status",
            "tailscale-enroll": "tailscale-enroll",
        },
    ),
    "billing": (
        "Inspect credits and usage; quote or submit extensions",
        {
            "credits": "credits",
            "usage": "usage",
            "ledger": "ledger",
            "estimate": "estimate",
            "extension-estimate": "extension-estimate",
            "extend": "extension-submit",
            "extension-status": "extension-status",
        },
    ),
    "docs": ("Read platform documentation", {"read": "doc"}),
}
DEFAULT_ACTIONS = {
    "resources": "summary",
    "tasks": "list",
    "experiments": "list",
    "jobs": "list",
    "images": "list",
    "files": "list",
    "datasets": "list",
    "account": "profile",
    "billing": "credits",
}


def canonical_command(operation):
    aliases = {
        "shared-files": "files list --shared",
        "dashboard": "resources summary --raw",
        "task-status": "tasks summary",
        "file-space-refresh": "files space --refresh",
    }
    if operation in aliases:
        return aliases[operation]
    for group, (_, actions) in COMMAND_GROUPS.items():
        for action, target in actions.items():
            if target == operation:
                return group + " " + action
    return operation


def command_overview(group=None):
    if group:
        description, actions = COMMAND_GROUPS[group]
        lines = [
            f"Usage: dibu.py {group} ACTION [OPTIONS]",
            "",
            description,
            "",
            "Actions:",
        ]
        for action, operation in actions.items():
            spec = operation_spec(operation)
            lines.append(
                "  {:<18s} {:<5s} {}".format(
                    action,
                    "write" if spec.get("write") else "read",
                    spec["description"],
                )
            )
        if group == "files":
            lines += [
                "",
                "list --shared selects shared files; space --refresh requests recalculation (write).",
            ]
        if group == "resources":
            lines += ["", "summary --raw returns the full resource/workload dashboard."]
        if group in DEFAULT_ACTIONS:
            lines += [
                "",
                "Default action: " + DEFAULT_ACTIONS[group] + " (when ACTION is omitted)",
            ]
        lines += [
            "",
            f"Use 'dibu.py {group} ACTION --help' for parameters and examples.",
        ]
    else:
        lines = ["Usage: dibu.py GROUP ACTION [OPTIONS]", "", "Commands:"]
        lines += [f"  {name:<14s} {description}" for name, (description, _) in COMMAND_GROUPS.items()]
        lines += [
            "  config         Read frontend capabilities and presets",
            "  list           Show this command overview",
            "",
            "Use 'dibu.py GROUP --help' for actions and read/write labels.",
            "Use 'dibu.py GROUP ACTION --help' for parameters; --describe for JSON schema.",
            "Writes preview by default; --execute submits a specifically authorized write.",
            "Legacy flat operation names remain accepted but are omitted from this overview.",
        ]
    return "\n".join(lines)


def route_command(argv):
    """Resolve a public command path without interpreting operation arguments."""
    if not argv or argv[0] in ("-h", "--help"):
        print(command_overview())
        raise SystemExit(0)
    group = argv[0]
    if group not in COMMAND_GROUPS:
        if not group.startswith("-") and group not in CAT and group not in SUMMARY_OPS and group != "list":
            raise ValueError("Unknown command: " + group + "; use dibu.py --help")
        return argv
    _, actions = COMMAND_GROUPS[group]
    tail = argv[1:]
    # Group help stays concise and never makes API requests.
    if tail in (["--help"], ["-h"]):
        print(command_overview(group))
        raise SystemExit(0)
    if tail and not tail[0].startswith("-"):
        action = tail.pop(0)
        if action not in actions:
            raise ValueError("Unknown action for " + group + ": " + action + "; use " + group + " --help")
    else:
        action = DEFAULT_ACTIONS.get(group)
        if action is None:
            if not tail:
                print(command_overview(group))
                raise SystemExit(0)
            raise ValueError("Choose an action; use " + group + " --help")
    operation = actions[action]
    if group == "files" and action == "list" and "--shared" in tail:
        tail.remove("--shared")
        operation = "shared-files"
    if group == "files" and action == "space" and "--refresh" in tail:
        tail.remove("--refresh")
        operation = "file-space-refresh"
    return [operation, *tail]


def positive_int(text):
    try:
        number = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("Expected a positive integer") from None
    if number <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer")
    return number


def duration_seconds(text):
    match = re.fullmatch(r"([1-9][0-9]*)([smh]?)", text)
    if not match:
        raise argparse.ArgumentTypeError("Expected positive seconds or an integer with s/m/h suffix (for example 10m)")
    return int(match[1]) * {"": 1, "s": 1, "m": 60, "h": 3600}[match[2]]


def operation_spec(name):
    return CAT[name] if name in CAT else SUMMARY_OPS[name]


def operation_help(name, spec):
    lines = [spec["description"]]
    if name in CAT:
        lines += [
            f"API: {spec['method']} {spec['path']}",
            "Defaults: " + json.dumps({"query": spec["query"], "body": spec["body"]}),
            "Required API fields: " + (", ".join(spec["required"]) or "none"),
            "Required execution headers: " + (", ".join(spec["headers"]) or "none"),
        ]
    lines += spec.get("cli", {}).get("notes", [])
    if name == "files":
        lines += ["Use files list --shared to query shared files instead of personal files."]
    if name == "file-space":
        lines += ["Use files space --refresh to request recalculation (write; preview unless --execute)."]
    if name == "resource-summary":
        lines += ["Use --raw for the full resource/workload dashboard."]
    if "body_schema" in spec:
        lines += ["Body fields (client guidance; server validation remains authoritative):"]
        required = spec["body_schema"].get("required", [])
        for field, rule in spec["body_schema"]["properties"].items():
            kind = rule.get("type", "integer|string")
            lines.append(
                "  {}: {}{} - {}".format(
                    field,
                    kind,
                    " (required)" if field in required else "",
                    rule.get("description", ""),
                )
            )
        lines += ["Use --template for an editable JSON body; replace placeholders before submission."]
    lines += ["Examples:"] + [
        "  dibu.py " + canonical_command(name) + example[len(name) :] for example in spec["cli"]["examples"]
    ]
    return "\n".join(lines)


def parse_cli(argv=None):
    common = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    common.add_argument(
        "--param",
        action="append",
        metavar="KEY=VALUE",
        help="Raw API parameter; repeat as needed",
    )
    common.add_argument("--body-file", help="JSON request body; use a mode-600 file for secrets")
    common.add_argument(
        "--header",
        action="append",
        help="Idempotency or estimate header, NAME:VALUE; repeat as needed",
    )
    common.add_argument(
        "--execute",
        action="store_true",
        help="Execute a specifically authorized write; otherwise preview",
    )
    common.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the request without authentication or network calls",
    )
    common.add_argument("--output", help="Save the full response to a mode-600 file")
    common.add_argument(
        "--raw",
        "-v",
        "--verbose",
        action="store_true",
        help="Return full API responses",
    )
    common.add_argument(
        "--describe",
        action="store_true",
        help="Print the operation schema as JSON without calling the API",
    )
    common.add_argument(
        "--template",
        action="store_true",
        help="Print an editable JSON body template offline; replace placeholders",
    )
    parser = argparse.ArgumentParser(
        description="DibuFusion API CLI. Use GROUP --help or GROUP ACTION --help for guidance.",
        usage="%(prog)s GROUP ACTION [OPTIONS]",
        parents=[common],
    )
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("list", help="List available API operations", parents=[common])
    for name, spec in {**SUMMARY_OPS, **CAT}.items():
        command = commands.add_parser(
            name,
            prog=parser.prog + " " + canonical_command(name),
            help=spec["description"],
            description=operation_help(name, spec),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            parents=[common],
        )
        for option in spec["cli"]["options"]:
            kwargs = {
                "dest": "alias_" + option["field"],
                "default": argparse.SUPPRESS,
                "help": option["help"] + " (API: " + option["field"] + ")",
                "metavar": option["field"].upper(),
            }
            if option.get("mapping"):
                kwargs.pop("metavar")
                kwargs["choices"] = list(option["mapping"])
            else:
                kwargs["type"] = {
                    "positive-int": positive_int,
                    "duration": duration_seconds,
                    "str": str,
                }[option["type"]]
                if "choices" in option:
                    kwargs.pop("metavar")
                    kwargs["choices"] = option["choices"]
            command.add_argument(*option["flags"], **kwargs)
    # Preserve legacy global options before the operation, including repeatable
    # values supplied on both sides. argparse subparsers otherwise replace lists.
    argv = list(sys.argv[1:] if argv is None else argv)
    index = 0
    while index < len(argv) and argv[index].startswith("-"):
        flag = argv[index].split("=", 1)[0]
        if flag in ("-h", "--help"):
            break
        if flag not in common._option_string_actions:
            break
        action = common._option_string_actions[flag]
        index += 1 if "=" in argv[index] or action.nargs == 0 else 2
    if index < len(argv) and not argv[index].startswith("-"):
        length = 1
        if argv[index] in COMMAND_GROUPS and index + 1 < len(argv) and not argv[index + 1].startswith("-"):
            length = 2
        argv = [*argv[index : index + length], *argv[:index], *argv[index + length :]]
    argv = route_command(argv)
    args = parser.parse_args(
        argv,
        namespace=argparse.Namespace(
            param=[],
            body_file=None,
            header=[],
            execute=False,
            dry_run=False,
            output=None,
            raw=False,
            describe=False,
            template=False,
        ),
    )
    if args.template and (
        args.describe
        or args.output
        or args.execute
        or args.dry_run
        or args.body_file
        or args.param
        or args.header
        or args.raw
        or any(key.startswith("alias_") for key in vars(args))
    ):
        parser.error("--template cannot be combined with request, output, or other discovery options")
    params = {}
    for item in args.param:
        if "=" not in item:
            parser.error("--param requires KEY=VALUE")
        key, text = item.split("=", 1)
        if not key:
            parser.error("--param requires a nonempty field name")
        val = value(text)
        if key in params and params[key] != val:
            parser.error("Conflicting values for API field " + key)
        params[key] = val
    if args.operation != "list":
        for option in operation_spec(args.operation)["cli"]["options"]:
            dest = "alias_" + option["field"]
            if not hasattr(args, dest):
                continue
            val = getattr(args, dest)
            if option.get("mapping"):
                val = option["mapping"][val]
            key = option["field"]
            if key in params and params[key] != val:
                parser.error("Conflicting alias and --param for API field " + key)
            params[key] = val
    return args, params


def main():
    a, params = parse_cli()
    if a.template:
        spec = operation_spec(a.operation) if a.operation != "list" else {}
        if "body_template" not in spec:
            raise ValueError("No body template for " + a.operation + "; use --help or --describe")
        print(json.dumps(spec["body_template"], indent=2))
        return
    if a.operation == "list":
        if a.describe:
            print(
                json.dumps(
                    {
                        name: {"command": canonical_command(name), **spec}
                        for name, spec in {**SUMMARY_OPS, **CAT}.items()
                    },
                    indent=2,
                )
            )
        else:
            print(command_overview())
        return
    if a.describe:
        print(
            json.dumps(
                {
                    "operation": a.operation,
                    "command": canonical_command(a.operation),
                    **operation_spec(a.operation),
                },
                indent=2,
            )
        )
        return
    if a.operation in ("resource-summary", "task-summary", "task-status"):
        if a.body_file or a.header or a.execute or a.dry_run:
            raise ValueError("Summaries are read-only and do not accept body/header/execute/dry-run")
        result = run_summary(a.operation, params, raw=a.raw or bool(a.output))
        if a.output:
            fd = os.open(a.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    body = load_json_file(a.body_file) if a.body_file else None
    for option in CAT[a.operation]["cli"]["options"]:
        key = option["field"]
        if hasattr(a, "alias_" + key) and isinstance(body, dict) and key in body and body[key] != params[key]:
            raise ValueError("Conflicting alias and --body-file for API field " + key)
    op, path, q, b = prepare(a.operation, params, body)
    headers = parse_headers(a.header)
    if a.dry_run or (op["write"] and not a.execute):
        print(
            json.dumps(
                {
                    "operation": a.operation,
                    "method": op["method"],
                    "path": path,
                    "query": q,
                    "body": "[BODY HIDDEN]" if a.operation == "password-change" else redact(b),
                    "headers": headers,
                    "preview": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    for h in op["headers"]:
        if not any(k.lower() == h.lower() and v for k, v in headers.items()):
            raise ValueError("Missing execution header: " + h)
    if a.operation in ["access-token-create", "tailscale-enroll"] and not a.output:
        raise ValueError("This operation returns secrets; --output is required.")
    base, auth = auth_config()
    result = request(base, auth, op, path, q, b, headers, a.output)
    print(
        json.dumps(
            result if a.raw or a.output else compact_response(a.operation, result),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
