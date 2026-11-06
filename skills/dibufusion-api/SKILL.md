---
name: dibufusion-api
description: 通过直接 HTTP API 操作内网 DibuFusion GPU 控制台（10.249.187.159:32320），查询资源、任务、实验、分布式任务、文件、共享目录、数据集、镜像、算元和个人设置，或执行用户授权的资源操作。用于此站点的后续自动化，免去重复浏览器点击。
---

使用本 skill 内的 `scripts/dibu.py`，仅依赖 Python 3 标准库。默认站点为 `http://10.249.187.159:32320`。

## 调用

令 `CLI` 为本 skill 目录下 `scripts/dibu.py` 的绝对路径：

```bash
python3 "$CLI" list
python3 "$CLI" dashboard
python3 "$CLI" tasks --param operate_id=1 --param size=20
python3 "$CLI" experiments --param operate_id=0
python3 "$CLI" jobs
python3 "$CLI" images --param q=ubuntu --param opt=0
python3 "$CLI" files --param path=/dotfiles
python3 "$CLI" shared-files --param path=/datasets
python3 "$CLI" credits
python3 "$CLI" usage --param page=1 --param size=20
```

`--param KEY=VALUE` 使用服务端原始字段，数字、布尔、数组、对象按 JSON 解析，其余保留字符串；`--body-file payload.json` 提供 JSON 正文。返回原始响应，新的 API 常用 `data` 包裹，旧接口可能是数组或 `{count,results}`。不假设所有接口有相同响应结构。

查 [references/operations.json](references/operations.json) 获取命名操作、HTTP 方法、URL、默认参数、必填参数、写操作标记和必填请求头。读取 [references/workflows.md](references/workflows.md) 后再创建/转换工作负载、续时、删除或修改文件及镜像。

写操作默认预览；已得到用户对具体操作的授权后传 `--execute`。按现有会话授权执行，不重复索要确认。部分 GET 有副作用，以目录中的 `write` 为准。`--dry-run` 可预览任何操作。

## 认证

认证仅从 `DIBU_TOKEN` 环境变量读取，值为裸 token；请求自动添加 `Authorization: Token <token>`。未设置或为空时直接报错。

先在运行环境中设置 `DIBU_TOKEN`，再执行上述命令。不在输出或仓库中记录 token。`DIBU_BASE_URL` 可指定站点地址，更换站点时使用对应 token。

收到 401 时停止调用，明确提醒用户认证已失效，请更新 `DIBU_TOKEN` 环境变量；等待用户更新后再继续，不自动登录、刷新或索取聊天中的明文 token。

## 验证范围

[references/verification.json](references/verification.json) 记录 26 次实测查询/估价与响应顶层结构，全部通过。

请求失败时，先核对请求和 skill 中的记录，不能盲目沿用旧 payload，如果 API 过时提醒用户检查并更新。 `scripts/dibu.py` 不自动重试写入；网络结果不确定时先查询状态和列表，保留原幂等键，不以新键重复创建。

API 整理时间：2026-11-06
