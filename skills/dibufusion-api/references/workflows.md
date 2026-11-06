# DibuFusion 参数与工作流

来源：2026-11-06 的实际 HAR 与 `app-tlgJjJ4J.js`，工作负载模块 `chunk-M1oagQDA.js`、创建表单 `chunk-HadGHOrl.js`、镜像 `chunk-CU-7TWxK.js`、文件 `chunk-foqsaYVD.js`、数据集 `chunk-1WsbCLfj.js`。已验证项见 verification.json。以下写操作均仅由前端实现确认，未实测改变资源。

## 列表与路径

- tasks/experiments：`operate_id=1` 运行中、`0` 已完成、`2` 待调度；`paginate=1,page=1,size=10`；可传 `search`。`is_VM=0` 任务、`1` 实验，命名操作已设置。
- jobs：`operate_id` 同上，`is_distributed=1`。
- images：`opt=0` 全部，`1` 个人，`2` 公开，`3` 基础；`is_temporary=1` 临时。可用 `q,image_id,username,name,ordering,page,size`。前端选择器使用 `ordering=recently_used`。`paginate=0` 请求无分页列表。
- files：API `path=/` 是个人工作区根目录，UI 显示 `/workspace`。下级目录传 `/dotfiles`，不要把 `/workspace` 当 API 前缀。
- shared-files：API `path=/` 是共享根目录，UI 显示 `/share`；下级目录 `/datasets`。请求含 `is_share_dir=true`。共享 UI 不提供写入操作。
- file-move 使用 `path,to_path`；file-mkdir/file-remove 使用 `path`。删除前确定精确路径和范围，不在根目录试验删除。
- 文件传输 UI 提供 SCP 与 Web 客户端，未发现经过验证的 HTTP 上传/下载接口，不编造 API。SCP 连接参数从当前 config/UI 获取，不把本次用户名固定为通用规则。
- datasets 返回数组，字段 `data_id,name,path,type,description,uploader`；创建/更新正文 `name,path,type,description,uploader`，更新还含 `data_id`（脚本从 `id` 补充）。当前用户只显示查询 UI，不能据前端 bundle 推断具有登记权限。
- images 原始 ID 字段 `image_id`。image-visibility 参数 `image_id,is_public`（0/1）；image-permanent 参数 `image_id`；image-note 参数 `image_id,note`。这些 GET 是写操作。登记镜像正文 `image_name,image_tag,source,is_public,note`。

## 创建任务、实验、分布式任务

先查 gpu-inventory 和 images 获取真实资源及镜像 ID。当前无运行资源，不用测试创建占用 GPU。任务和实验通过 container-create；分布式通过 job-create；已有实验转任务通过 container-convert。

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
  "password": "",
  "path": "/workspace",
  "shm": "2Gi",
  "use_ib": false,
  "use_master": true,
  "cmd": "<任务命令>",
  "outer_ssh": false
}
```

`duration` 单位是秒，0 代表无限时长选项；必须是用户请求的时长。实验 `is_VM=true`，另有 `auto_save_on_finish`；任务 `cmd` 必填，实验可空。转换附 `container_id`，镜像 ID 可以由源容器决定。上述 `is_test=true` 是当前前端提交字段，不能据其名称认为创建只是测试或不会占资源。

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

创建后查询 tasks/experiments/jobs 确认真实 ID 与状态；创建响应成功不等于资源已 ready。

## 生命周期、诊断与续时

- container-delete/job-delete 删除当前工作负载；container-history-delete/job-history-delete 删除历史记录。参数分别 `container_id/job_id`。不要混淆历史删除与停止运行。
- experiment-stop：GET `/container/containerStop/?container_id=…`，有副作用。
- experiment-restart：POST `container_id`，之后 restart-status GET 轮询。镜像保存 image-save 是有副作用 GET，之后 image-save-status 查询结果。
- events：`container_id`；分布式附 `is_job=true`。network 操作使用 `id`，可传 `refresh=1`。返回可能包含敏感访问地址。
- container-log/job-log 使用 `id` 和 `--output /path/log.txt` 下载。实时日志前端使用 `ws://<host>/search/log/`，连接后发送 `{container:<podName>,since:"all",tail:100,follow:true}`，分布式附 `is_job:true`；未验证鉴权与真实流，当前脚本只封装 HTTP 日志下载，不声称支持实时 WebSocket。
- extension-estimate：`id,additional_minutes`；响应 `data.quote_id`。extension-submit 正文 `quote_id,additional_minutes,reason`，附 `Idempotency-Key`。读响应 `operation_id`，用 extension-status 的 `id,operation` 查询，不能重复新建请求代替查状态。

## 算元、个人设置

- usage 可传 `workload_kind,time_quality,node,gpu_mode,workload_mode,min_amount_micro,max_amount_micro,started_from,started_to,page,size`。
- ledger 可传 `kind,committed_from,committed_to,page,size`。金额 `*_micro` 保留整数或字符串精度，不按浮点当作元展示。
- profile-update 正文 `nickname,email,phone,gender`（男/女/未知）；password-change 正文 `username,old_password,new_password`，用权限受限临时 JSON 文件传入，完成后删除，不在命令行或输出显示密码。
- access-token-create 和 tailscale-enroll 必须给 `--output` 保存含秘密响应，文件应限制权限。访问令牌的认证方式未单独验证，脚本仅使用 `DIBU_TOKEN` 环境变量提供的 token。
- 主题和语言保存在浏览器偏好中，不是本次观察到的业务 HTTP API。
