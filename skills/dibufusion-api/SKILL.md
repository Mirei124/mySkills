---
name: dibufusion-api
description: 通过直接 HTTP API 操作内网 DibuFusion GPU 控制台（10.249.187.159:32320），查询资源、任务、实验、分布式任务、文件、共享目录、数据集、镜像、算元和个人设置，或执行用户授权的资源操作。用于此站点的后续自动化，免去重复浏览器点击。
---

使用本 skill 内的 `scripts/dibu.py`，仅依赖 Python 3 标准库。默认站点为 `http://10.249.187.159:32320`。

## 调用

令 `CLI` 为本 skill 目录下 `scripts/dibu.py` 的绝对路径：

```bash
python3 "$CLI" list
python3 "$CLI" resource-summary
python3 "$CLI" task-summary
python3 "$CLI" task-status --param container_id=<ID>
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

## GPU 申请默认策略

申请前查询 `resource-summary`（只读取 dashboard）和当前任务。用户没有指定卡数时，若已确认程序支持并会实际使用多卡，**默认申请本次工作负载可调度、可有效利用的最大可用 GPU 数量**，以加快运行。用户明确卡数、预算或资源上限优先。

最大值受当前空闲 GPU、CPU/内存配比、显存、账号配额、任务并行度和拓扑共同限制；单机程序只能计算一个兼容节点内的卡，未验证跨节点分布式时不能把各节点卡数相加。多组任务同时提交时应联合分配，使总申请不超出可用资源，逐次刷新，不能每组重复使用同一份空闲数。多个 worker/数据分片需与卡数匹配；仅 `device_map=auto` 不证明会有效利用全部 GPU。详细预检见 [工作流](references/workflows.md#资源预检与最大有效卡数)。

只读查看资源不授权创建、扩容或停止任务。确认最大卡数后按实际配置估价，仍遵守用户已有预算和收费授权；资源不足时不要擅自停止其他任务。

## 认证

认证仅从 `~/.cache/dibu_token` 读取。文件使用 UTF-8，内容为裸 token；脚本去掉首尾空白，文件缺失、不可读、为空或格式错误时直接报错。请求自动添加 `Authorization: Token <token>`，不读取或回退到 `DIBU_TOKEN` 环境变量。

无需加载 shell 配置或导出环境变量。设置文件权限为 `600`，不在输出或仓库中记录 token。`DIBU_BASE_URL` 仍可覆盖站点地址；切换站点时使用对应的 token 文件。

收到 HTTP 401 时停止调用，请用户更新 `~/.cache/dibu_token`，更新后再继续；不自动登录、刷新凭据或索取聊天中的明文 token。

## 失败处理

写入不自动重试。网络结果不确定时先查询状态和列表，保留原幂等键，不以新键重复创建。HTTP 403 应依据服务端响应正文诊断，不能仅凭状态码认定账号缺少权限；也不能直接重放浏览器请求中的旧估价指纹和幂等键。

## 任务日志

任务的 stdout、stderr、启动/退出记录及各 worker 日志统一保存到 `/workspace/task_run_logs/` 下按任务名和运行标识区分的独立子目录，避免不同实验或重试相互覆盖。

## 状态与诊断

`task-summary` 分页汇总任务列表；`task-status --param container_id=ID` 按 ID 检索运行、排队和历史列表并附调度事件。交互实验另查 `experiments`，分布式任务另查 `jobs`；不要把任务摘要当全部工作负载。

创建成功后查真实 ID、实际 `status` 和事件。有时运行列表中会出现 Pending，应按行内状态报告。提交成功、Running、应用日志已启动、应用结果已验证是不同阶段；`Not exist or finished` 只能表明工作负载已结束/不存在。结果完整性与指标验证由项目脚本负责，不能由平台状态推断成功。

## 按需参考

日常操作读取上述接口清单和工作流。只有核对历史可用性、排查已知问题或维护本技能时，才读取 [maintenance/verification.md](maintenance/verification.md)；该文件集中记录测试结果、未测项、暂存问题、接口来源和维护方法。
