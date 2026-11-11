# DibuFusion 参数与工作流

## 列表与路径

- tasks/experiments：`operate_id=1` 运行中、`0` 已完成、`2` 待调度；`paginate=1,page=1,size=10`；可传 `search`。`is_VM=0` 任务、`1` 实验，命名操作已设置。
- jobs：`operate_id` 同上，`is_distributed=1`。
- images：`opt=0` 全部，`1` 个人，`2` 公开，`3` 基础；`is_temporary=1` 临时。可用 `q,image_id,username,name,ordering,page,size`。前端选择器使用 `ordering=recently_used`。`paginate=0` 请求无分页列表。
- files：API `path=/` 是个人工作区根目录，UI 显示 `/workspace`。下级目录传 `/dotfiles`，不要把 `/workspace` 当 API 前缀。
- shared-files：API `path=/` 是共享根目录，UI 显示 `/share`；下级目录 `/datasets`。请求含 `is_share_dir=true`。共享 UI 不提供写入操作。
- file-move 使用 `path,to_path`；file-mkdir/file-remove 使用 `path`。删除前确定精确路径和范围，不在根目录试验删除。
- 文件传输 UI 提供 SCP 与 Web 客户端，未发现经过验证的 HTTP 上传/下载接口，不编造 API。SCP 连接参数从当前 config/UI 获取，不把本次用户名固定为通用规则。
- datasets 返回数组，字段 `data_id,name,path,type,description,uploader`；创建/更新正文 `name,path,type,description,uploader`，更新还含 `data_id`（脚本从 `id` 补充）。登记权限由服务端判定。
- images 原始 ID 字段 `image_id`。image-visibility 参数 `image_id,is_public`（0/1）；image-permanent 参数 `image_id`；image-note 参数 `image_id,note`。这些 GET 是写操作。登记镜像正文 `image_name,image_tag,source,is_public,note`。

## 创建任务、实验、分布式任务

先查 resource-summary、当前任务和 images 获取真实资源及镜像 ID。按下方最大有效卡数规则选择资源，不把历史配置当作固定默认值。任务和实验通过 container-create；分布式通过 job-create；已有实验转任务通过 container-convert。

### 资源预检与最大有效卡数

1. 查询 `resource-summary`，只读取 dashboard，保留采样时间、`stale`、`refresh_pending`、`errors`。使用新鲜的可调度节点数据；`SchedulingDisabled` 不计入可用量。GPU/CPU/内存剩余量为 null 表示未知，不能当作零，也不能以总量代替空闲量。dashboard 无法确认的 GPU 分区模式或可用量应明确说明，不能将整卡剩余数套用到 MIG/vGPU；资源预检不自动读取 gpu-inventory。
2. 确认应用的并行方式：数据并行、互不重叠的样本分片、张量并行或已验证的模型切分。单纯增加 num_gpu 不会自动加速。单机任务选择一个满足型号/显存要求的节点；只有已支持跨节点的任务才考虑多节点。任务可处理的独立分片数也是卡数上限。
3. 用户未指定卡数且程序可有效多卡时，默认最大化本次可用且有效的 GPU 数。单节点数据并行可按 `min(空闲兼容卡数, CPU 能支持的 worker 数, 主机内存能支持的 worker 数, 配额上限, 应用并行上限)` 计算；先为固定开销、/dev/shm 和系统负载留有根据的余量，资源配比由程序需求决定，不固化某次实验的数值。模型并行需按其实际资源模型计算。把选定卡数及限制因素简短告知用户，不因默认策略重复索要已授权操作的确认。
4. 多组同时申请要联合分配不同卡/节点并考虑公平的任务完成时间，不能让每组都申请同一节点的全部空闲卡。逐次提交前刷新资源，不能依赖提交前较早的快照。若资源在竞态中减少，重新规划和估价；不自动新建重复请求。
5. 检查 CPU、主机内存、shm 与 GPU 配比。申请内存不能高于节点剩余量；不要混淆 GPU 显存和主机内存。Ready 也不保证无 taint 或 DRA 错误。创建后若 Pending，通过事件检查 `Insufficient memory`、node affinity、untolerated taint、`FailedResourceClaimCreation` 等。CPU/内存不足可在用户授权范围内缩减并重新估价；taint/模板缺失不能靠反复建任务解决，不擅自移除 taint 或改集群配置。

### Quota rejections and replacements

Free node GPUs, per-workload limits, account-wide limits, and container-slot limits are separate constraints. A successful estimate does not check all of them. When a submission is explicitly rejected, retain the exact diagnostic, reconcile tasks, experiments, and distributed workloads, and distinguish these cases:

| Observed diagnostic | Next decision |
| --- | --- |
| `The number of GPUs cannot be larger than N` | Bound this workload by the reported limit. Do not publish N as a permanent site default. |
| `The total number of GPUs cannot be larger than N` | Check account-wide workloads as well as pending/deleting work. An empty task list does not prove that quota accounting has cleared. |
| `The container num is N, cannot be larger than N` | Reconcile active container slots. Conversion has also hit this check; it is not a verified workaround. |

If the user permits a smaller allocation, a changed request may use fewer GPUs with a new estimate/key and matching worker count. If the user explicitly requested a count, do not silently reduce it. Do not binary-search card counts or repeatedly submit the same quota rejection without new evidence; when visibility does not explain the rejection, report the unresolved account/platform constraint. Historical acceptance of a smaller request does not establish why a larger request failed.

Stopping a workload and freeing quota are distinct observations. A stop/delete acceptance does not guarantee immediate release, and a continuing quota error does not by itself prove delayed release. Retain the exact old workload ID and reconcile before replacing an authorized run. Never cancel unrelated experiments or delete history to try to clear quota.

### Runtime planning and durable execution

Estimate total wall time from model/environment startup, smoke tests, full inference, retries, and aggregation; compare it with the requested duration before submitting a long run. A per-rank progress display such as `766/1350` describes one shard, not the full 2700-question dataset. Plan the slowest shard and allow startup/validation margin; increasing cards need not scale perfectly. If completion is unlikely within the permitted duration, prefer resumable per-sample outputs, independently completed shards, or an authorized extension instead of another identical run that discards partial work.

The previously observed experiment maximum is 12 hours; do not infer the same maximum for every task or deployment. Log silence near a requested 12-hour duration is consistent with a time limit, but empty events and a missing exit record do not confirm the termination cause. Save partial artifacts and report completion separately from the suspected cause. A pruning/statistics record can be written before generation completes and is not a completed prediction.

Keep scripts, dependencies, checkpoints, and outputs needed by replacement pods on verified persistent mounts (normally `/workspace` or `/share`) or in a verified image/snapshot. Do not assume packages installed outside shared mounts will exist in a new pod. Put the project's required `source`/activation command inside the submitted script; preserve it when changing GPU count or frame settings. Before diagnosing decoder/model errors, verify that the task uses the intended interpreter and tools. Project-specific model, dataset, retention, and frame settings belong in project configuration, not this skill.

### 创建参数和估价

创建前必须按相同资源配置调用 estimate，其正文：

```json
{
  "workload_kind": "container",
  "workload_mode": "standard",
  "gpu_mode": "full",
  "gpu_type": "",
  "gpu_count": 0,
  "cpu_cores": 4,
  "memory_gib": 16,
  "worker_count": 1,
  "duration_seconds": 3600
}
```

分布式改 `workload_kind=job,workload_mode=distributed,worker_count=实际 worker 数`；vgpu 使用 `gpu_mode=vgpu`，`gpu_type` 去掉 `-vgpu` 后缀。DRA 使用 `gpu_mode=dra` 并附同一 `gpu_selection`。legacy GPU 节点选择还要附 `legacy_node_id`。查看估价 `data.warning_codes,will_charge,minimum_micro,maximum_micro,available_micro`。不要假定本次 `metering_only` 模式一直不收费。

估价命令：

```bash
python3 "$CLI" estimate --body-file estimate.json --output quote.json
```

从响应取 `data.estimate_fingerprint`，在创建请求头传 `X-DibuFusion-Estimate-Fingerprint`，以及本次操作唯一且稳定的 `Idempotency-Key`。同一 payload 网络重试保留原键；不同 payload 重新估价并换键。脚本要求这两个头，未实现自动重试。

任务/实验正文（示例仅演示字段，必须换成真实镜像与用户参数）：

```json
{
  "capabilities": [],
  "cpu": 4,
  "duration": 3600,
  "image_id": "<真实镜像ID>",
  "is_VM": false,
  "is_test": true,
  "lab_name": "<名称>",
  "memory": "16Gi",
  "name": "<当前用户名>",
  "num_gpu": 0,
  "password": "<本次生成并安全保存的非空随机密码>",
  "path": "/workspace",
  "shm": "2Gi",
  "use_ib": false,
  "use_master": true,
  "cmd": "<任务命令>",
  "outer_ssh": false
}
```

`password` 不能留空（本站点已返回 blank 校验错误）。用 `secrets.token_urlsafe(24)` 生成，正文文件权限设为 `600`，不要打印密码或放入 shell 参数；CLI 预览会脱敏。任务的 cmd 必须非空，DRA 的 `gpu_selection.count` 与 `num_gpu` 必须一致。估价和创建使用同一配置，修改配置后重新估价并生成新幂等键。

`duration` is in seconds; `43200` is 12 hours. `0` is the legacy unlimited option, not a maximum-duration shortcut. See runtime planning above for the observed experiment limit and task/deployment uncertainty. 实验设置 `is_VM=true`，支持 `auto_save_on_finish`；任务必须提供 `cmd`，实验可留空。转换还需提供 `container_id`，镜像可由源容器确定。转换曾同样被单容器配额拒绝，不能假设会先释放实验或绕过数量限制；失败后回查源实验和任务列表，不擅自停止源实验。前端的 `is_test=true` 仍会创建真实资源，不代表预览。

GPU 旧路径：附 `gputype`，`num_gpu>0` 且有节点选择时附 `legacy_node_id`；vgpu 附 `gpumem`（前端选择值，不擅自换算单位）。DRA 路径改用：

```json
{"gpu_selection":{"node_id":1,"gpu_type":"<inventory型号>","count":1,"allocation":"builtin_whole"}}
```

配置式 DRA 使用 `allocation=config,config_id,preset_key`；从实时 inventory 取值，不能复用示例 ID。当前前端分布式创建不支持此 DRA 选择路径。

分布式正文：`name,task_name,image_id,work_path=/workspace,worker_num,gpu_per_worker,cpu_per_worker,mem_per_worker="16Gi",shm_per_worker="2Gi",gputype/gpumem（GPU时）,cmd,capabilities,use_ib,use_mpi,duration`。集中启动 `use_mpi=true`，逐 worker 命令 `false`；后一种 `cmd` 用 `;;` 分隔，每个 worker 一条。

```bash
python3 "$CLI" container-create --body-file payload.json --dry-run
# 已获具体创建授权且参数完整后：
python3 "$CLI" container-create --body-file payload.json \
  --header "Idempotency-Key:<本次操作UUID>" \
  --header "X-DibuFusion-Estimate-Fingerprint:<估价指纹>" --execute
```

创建后查询 tasks/experiments/jobs 确认真实 ID 与状态；创建响应成功不等于资源已就绪。获取不到 ID 时按唯一任务名、创建时间与稳定幂等键查证，不以新键重建。Recognized lists use compact JSON by default; use `--raw` for full API responses. `task-summary` and `task-status` omit password and command fields unless raw output is requested.

在有限时间内复查启动（例如最多 3 次、间隔 10–20 秒），若仍排队，附事件和准确状态交付，不能称为已运行。事件为空时承认原因未知，不推断超时、OOM 或正常退出。Running 后还要查看应用日志确认 worker 数/GPU 使用与申请一致，不能以资源已分配代替多卡实际生效。

任务启动命令应将 stdout 和 stderr 持续保存到 `/workspace/task_run_logs/<任务名>/<运行标识>/` 下的独立日志，并记录开始/结束时间和退出码；有多 worker 时保存各自日志。需要 `source` 时使用完整 shell 引用的 `bash -lc '<完整命令>'`；环境加载脚本会输出秘密变量时抑制其 stdout/stderr，不将环境转储写入日志。应用级的样本数、重复/缺失、内部错误、指标与产物验证留在项目运行脚本中，只有其验证通过才称为实验成功。

## 生命周期、诊断与续时

- container-delete/job-delete 删除当前工作负载；container-history-delete/job-history-delete 删除历史记录。参数分别 `container_id/job_id`。不要混淆历史删除与停止运行。
- experiment-stop：GET `/container/containerStop/?container_id=…`，保存临时镜像并停止实验。等待 image-save-status 完成，再用 images 的 `opt=1,is_temporary=1` 查找暂停镜像；旧实验记录可能显示为已完成。
- 恢复暂停实验：使用对应临时镜像的真实 `image_id`，重新估价并通过 container-create 创建 `is_VM=true` 的实验；会生成新的实验 ID。恢复与原 Pod 重启是不同操作。
- SSH 使用 `ssh -p <port> root@<node_ip>`，地址、端口和密码从当前实验读取；密码使用交互输入或受限文件，不放进命令参数和日志。
- experiment-restart：POST `container_id`，之后 restart-status GET 轮询。镜像保存 image-save 是有副作用 GET，之后轮询 image-save-status 至 `state=finished`；仅受理不代表保存成功。
- events：`container_id`；分布式附 `is_job=true`。network 操作使用 `id`，可传 `refresh=1`。返回可能包含敏感访问地址。
- container-log/job-log 使用 `id` 和 `--output /workspace/task_run_logs/<运行标识>/platform.log` 下载。实时日志前端使用 `ws://<host>/search/log/`，连接后发送 `{container:<podName>,since:"all",tail:100,follow:true}`，分布式附 `is_job:true`；脚本只支持 HTTP 日志下载，实时日志需单独使用 WebSocket 客户端。
- extension-estimate：`id,additional_minutes`；响应 `data.quote_id`。extension-submit 正文 `quote_id,additional_minutes,reason`，附 `Idempotency-Key`。读响应 `operation_id`，用 extension-status 的 `id,operation` 查询，不能重复新建请求代替查状态。

## 算元、个人设置

- usage 可传 `workload_kind,time_quality,node,gpu_mode,workload_mode,min_amount_micro,max_amount_micro,started_from,started_to,page,size`。
- ledger 可传 `kind,committed_from,committed_to,page,size`。金额 `*_micro` 保留整数或字符串精度，不按浮点当作元展示。
- profile-update 正文 `nickname,email,phone,gender`（男/女/未知）；password-change 正文 `username,old_password,new_password`，用权限受限临时 JSON 文件传入，完成后删除，不在命令行或输出显示密码。
- access-token-create 和 tailscale-enroll 必须给 `--output` 保存含秘密响应，文件应限制权限。脚本从 `~/.cache/dibu_token` 读取认证值。
- 主题和语言保存在浏览器偏好中，不是本次观察到的业务 HTTP API。


## Live-confirmed quote and pagination constraints

CLI smoke tests confirmed that `usage` and `ledger` accept page sizes 20, 50, and 100; sizes 2, 10, 21, and 200 returned HTTP 400. Page 2 of an empty billing list returned HTTP 404. Begin at page 1 and follow response pagination. Typed `--limit` supports the three confirmed sizes; raw parameters remain available for future server behavior.

CPU-only, DRA whole-GPU, and configured DRA estimate payloads returned successful quotes with fingerprints. A legacy full-GPU quote targeting a current DRA-managed node returned `node_requires_dra_gpu`; use DRA selection for those nodes. This does not establish whether another deployment supports legacy or vGPU allocation. Quote success and candidate counts do not prove that a workload can schedule: the sampled inventory was stale with unknown availability, and configured MIG nodes were not verified schedulable. No workload creation, GPU allocation, or billing extension was performed in this check.
