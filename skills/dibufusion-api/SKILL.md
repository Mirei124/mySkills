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

认证仅从 `~/.cache/dibu_token` 读取。文件使用 UTF-8，内容为裸 token；脚本去掉首尾空白，文件缺失、不可读、为空或格式错误时直接报错。请求自动添加 `Authorization: Token <token>`，不读取或回退到 `DIBU_TOKEN` 环境变量。

无需加载 shell 配置或导出环境变量。设置文件权限为 `600`，不在输出或仓库中记录 token。`DIBU_BASE_URL` 仍可覆盖站点地址；切换站点时使用对应的 token 文件。

收到 HTTP 401 时停止调用，请用户更新 `~/.cache/dibu_token`，更新后再继续；不自动登录、刷新凭据或索取聊天中的明文 token。

## 失败处理

写入不自动重试。网络结果不确定时先查询状态和列表，保留原幂等键，不以新键重复创建。HTTP 403 应依据服务端响应正文诊断，不能仅凭状态码认定账号缺少权限；也不能直接重放浏览器请求中的旧估价指纹和幂等键。

## 按需参考

日常操作读取上述接口清单和工作流。只有核对历史可用性、排查已知问题或维护本技能时，才读取 [maintenance/verification.md](maintenance/verification.md)；该文件集中记录测试结果、未测项、暂存问题、接口来源和维护方法。
