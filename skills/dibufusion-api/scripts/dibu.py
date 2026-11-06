#!/usr/bin/env python3
"""DibuFusion API 命令行工具，仅依赖 Python 3 标准库。"""

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAT = json.loads((ROOT / "references/operations.json").read_text())
BASE = "http://10.249.187.159:32320"


class ChineseArgumentParser(argparse.ArgumentParser):
    def format_usage(self):
        return super().format_usage().replace("usage: ", "用法：", 1)

    def format_help(self):
        return super().format_help().replace("usage: ", "用法：", 1)

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}：参数错误：{message}\n")


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
            "无法读取 ~/.cache/dibu_token；请创建可读的 UTF-8 文件，内容为裸 token。"
        ) from exc
    if not token:
        raise ValueError("认证文件 ~/.cache/dibu_token 为空。")
    if any(character.isspace() for character in token):
        raise ValueError("~/.cache/dibu_token 格式错误；请仅保存裸 token。")
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
            path = path.replace(
                marker, urllib.parse.quote(str(params.pop(key)), safe="")
            )
    if "{" in path:
        raise ValueError("缺少路径参数：" + path)
    if body is not None:
        if not isinstance(body, dict):
            raise ValueError("JSON 正文必须是对象")
        b = {**(b or {}), **body}
    if op["method"] in ["GET", "DELETE"]:
        q.update(params)
    else:
        b = {**(b or {}), **params} if params else b
    if (
        name in ["files", "shared-files"]
        and (
            b.get("action") != "ls"
            or b.get("is_share_dir", False) != (name == "shared-files")
        )
    ):
        raise ValueError("列表操作不允许覆写 action/is_share_dir；请使用对应文件操作")
    if (
        name.startswith("file-")
        and op["body"]
        and b.get("action") != op["body"]["action"]
    ):
        raise ValueError("不允许覆写文件操作类型")
    if name == "dataset-update" and b is not None:
        b["data_id"] = urllib.parse.unquote(path.rstrip("/").rsplit("/", 1)[1])
    for key in op["required"]:
        if key == "body":
            if not b:
                raise ValueError("需要 --body-file JSON 文件")
        elif "{" + key + "}" in op["path"]:
            continue
        elif key not in q and (b is None or key not in b):
            raise ValueError("缺少参数：" + key)
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
        for secret in (auth, auth[len("Token ") :]):
            if secret:
                detail = detail.replace(secret, "[REDACTED]")
        if e.code == 401:
            raise ValueError(
                "HTTP 401：认证已失效，请更新 ~/.cache/dibu_token 后再试。 " + detail
            )
        if e.code == 403:
            raise ValueError("HTTP 403：服务端拒绝请求，请根据响应正文诊断。 " + detail)
        raise ValueError(f"HTTP {e.code}: {detail}")
    if output:
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        return {"status": status, "output": str(output), "bytes": len(raw)}
    try:
        result = json.loads(raw)
        if isinstance(result, dict) and result.get("error"):
            raise ValueError(
                "API 返回错误：" + json.dumps(result["error"], ensure_ascii=False)
            )
        return result
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"status": status, "text": raw.decode(errors="replace")}


def main():
    ap = ChineseArgumentParser(description=__doc__, add_help=False)
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument(
        "operation",
        choices=["list"] + list(CAT),
        help="要执行的操作；list 显示操作清单",
    )
    ap.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="请求参数，可重复传入",
    )
    ap.add_argument("--body-file", help="JSON 请求正文文件")
    ap.add_argument(
        "--header", action="append", default=[], help="估价指纹或幂等请求头，可重复传入"
    )
    ap.add_argument(
        "--execute", action="store_true", help="提交已授权的写操作；否则仅预览"
    )
    ap.add_argument("--dry-run", action="store_true", help="仅预览请求，不发送")
    ap.add_argument("--output", help="将响应保存到权限为 600 的文件")
    a = ap.parse_args()
    if a.operation == "list":
        for n, o in CAT.items():
            print(
                "{:<26s} {:<6s} {:<55s} {:s}".format(
                    n, o["method"], o["path"], "写入" if o["write"] else "查询"
                )
            )
        return
    params = {}
    for s in a.param:
        if "=" not in s:
            raise ValueError("--param 格式为 KEY=VALUE")
        k, v = s.split("=", 1)
        params[k] = value(v)
    body = load_json_file(a.body_file) if a.body_file else None
    op, path, q, b = prepare(a.operation, params, body)
    headers = {}
    for s in a.header:
        k, v = s.split(":", 1)
        if k.strip().lower() not in [
            "idempotency-key",
            "x-dibufusion-estimate-fingerprint",
        ]:
            raise ValueError("不支持的附加请求头")
        headers[k.strip()] = v.strip()
    if a.dry_run or (op["write"] and not a.execute):
        print(
            json.dumps(
                {
                    "operation": a.operation,
                    "method": op["method"],
                    "path": path,
                    "query": q,
                    "body": "[正文已隐藏]" if a.operation == "password-change" else b,
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
            raise ValueError("提交缺少请求头：" + h)
    if a.operation in ["access-token-create", "tailscale-enroll"] and not a.output:
        raise ValueError("此操作返回秘密；必须通过 --output 保存结果。")
    base, auth = auth_config()
    result = request(base, auth, op, path, q, b, headers, a.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
