# 测试记录与维护说明

本文仅用于维护技能、核对接口可用性和追踪问题；日常调用不需要加载。测试日期为 2026-11-06，结论仅代表当时站点和账号的情况。

## 维护范围与来源

- API 清单：`../references/operations.json`；请求实现：`../scripts/dibu.py`。
- 使用说明：`../SKILL.md` 和 `../references/workflows.md`。
- 接口依据：当日 HAR 与前端模块 `app-tlgJjJ4J.js`、`chunk-M1oagQDA.js`、`chunk-HadGHOrl.js`、`chunk-CU-7TWxK.js`、`chunk-foqsaYVD.js`、`chunk-1WsbCLfj.js`。
- 分布式文档：[HAIOS 分布式任务一键式部署](https://west-timbale-474.notion.site/HAIOS-1de4c34734c880baa44ee463a15e3182)。

## 查询与估价测试

以下 26 项均通过。响应结构保留接口原始字段，数组数量为测试时的观察值。

| 操作 | 参数 | 响应结构 |
| --- | --- | --- |
| `dashboard` | `{}` | `sampled_at_ms`、`nodes`、`overview`、`user_count`、`stale`、`refresh_pending`、`errors` |
| `config` | `{}` | `frontend_config` |
| `gpu-inventory` | `{}` | `nodes`、`sampled_at_ms`、`stale`、`refresh_pending`、`errors` |
| `tasks` | `{}` | `count`、`next`、`previous`、`results` |
| `experiments` | `{}` | `count`、`next`、`previous`、`results` |
| `jobs` | `{}` | 数组，0 项 |
| `files` | `{}` | 数组，3 项 |
| `shared-files` | `{}` | 数组，8 项 |
| `file-space` | `{}` | `dir_size`、`is_calculating` |
| `datasets` | `{}` | 数组，0 项 |
| `images` | `{}` | `count`、`next`、`previous`、`results` |
| `profile` | `{}` | `user_id`、`username`、`nickname`、`first_login`、`grade`、`email`、`gputime`、`gputime_used`、`gputime_all`、`date_joined`、`gender`、`phone`、`wechat_openid`、`wechat_avatar_url`、`wechat_username` |
| `access-token-info` | `{}` | `exists`、`token_prefix`、`created_at` |
| `tailscale-status` | `{}` | `enabled`、`enrollment_available`、`hostname`、`nodes`、`ports`、`auth_key_expiry_seconds`、`node_key_expiry_days`、`has_enrollment` |
| `credits` | `{}` | `api_version`、`request_id`、`observed_at`、`data`、`warnings`、`error` |
| `usage` | `{}` | `api_version`、`request_id`、`observed_at`、`data`、`warnings`、`error` |
| `ledger` | `{}` | `api_version`、`request_id`、`observed_at`、`data`、`warnings`、`error` |
| `files` | `{"path":"/dotfiles"}` | 数组，14 项 |
| `shared-files` | `{"path":"/datasets"}` | 数组，0 项 |
| `images` | `{"q":"ubuntu","opt":0}` | `count`、`next`、`previous`、`results` |
| `images` | `{"q":"pytorch","opt":0}` | `count`、`next`、`previous`、`results` |
| `tasks` | `{"operate_id":0}` | `count`、`next`、`previous`、`results` |
| `jobs` | `{"operate_id":0}` | 数组，0 项 |
| `experiments` | `{"operate_id":0}` | `count`、`next`、`previous`、`results` |
| `doc` | `{"document":"1-instructions-for-use.md"}` | `status`、`text` |
| `estimate` | `{}` | `api_version`、`request_id`、`observed_at`、`data`、`warnings`、`error` |

## 工作负载生命周期测试

| 项目 | 结果 | 证据与范围 |
| --- | --- | --- |
| 创建实验 | 通过 | 实验 169；8 核 CPU、32 GiB、无 GPU、12 小时，HTTP 201；估价为不收费。 |
| SSH 与命令执行 | 通过 | 实验 169 可用 root 登录，身份、主机名、系统查询和文件读写正常。 |
| 保存镜像及状态查询 | 通过 | 保存状态由 `committing` 转为 `finished`，返回摘要；生成私有镜像 34。 |
| 暂停实验 | 通过 | 实验 169 保存临时镜像 35 后停止；旧记录显示 `Not exist or finished`。 |
| 从暂停镜像恢复 | 通过 | 使用镜像 35 新建实验 170；SSH 确认 `/root` 中的标记文件保留。 |
| 原 Pod 重启 | 阻塞 | 对停止和运行中的实验均返回 HTTP 409：“原 Pod 重启服务尚未配置”。 |
| 重启状态查询 | 通过 | 返回 `state=unused,remaining=1`；仅代表查询可用，重启动作未通过。 |
| 实验转任务 | 阻塞 | HTTP 403：`The container num is 1, cannot be larger than 1`，单容器配额阻塞转换。 |
| 内部网络信息 | 失败 | HTTP 503：`workload_network_unavailable`；实验 SSH 仍可用。 |
| 从保存镜像创建任务 | 通过 | 镜像 34 在另一节点启动任务 171；实时日志包含持久化文件内容和命令成功标记。 |
| Pod 事件查询 | 通过 | 任务 171 返回 `Scheduled`、`Pulled`、`Created`、`Started`。 |
| HTTP 日志下载 | 阻塞 | 任务运行时及结束后均返回 HTTP 403：`The container has no log file associated with it.`。 |
| 实时日志 | 通过 | WebSocket 返回持久化文件和命令成功标记；响应是包含转义换行的 Python bytes 字符串表示。 |
| 任务 SSH | 不可用 | 测试任务的 SSH 连接被关闭；不代表任务命令没有执行。 |
| 结束实验与任务 | 通过 | 实验 170、任务 171 删除返回 HTTP 204；运行和待调度列表为空，历史记录和私有镜像 34 保留。 |

## 其他资源操作测试

| 项目 | 结果 | 证据与范围 |
| --- | --- | --- |
| 目录新建、列表、移动、删除 | 通过 | 使用唯一临时目录，测试结束后已删除。 |
| 空间统计刷新 | 已受理 | 刷新请求成功，后续查询仍为 `is_calculating=true`；未验证计算完成。 |
| 数据集登记、修改、列表、删除 | 通过 | 使用临时登记记录，仅修改元数据，未创建或删除实际数据文件。 |
| 镜像备注、设为私有、转永久 | 通过 | 临时镜像 35 更新后可在个人永久镜像列表中查询；未测试公开镜像。 |
| 删除测试镜像 | 通过 | 镜像 35 删除返回 HTTP 204；镜像 34 保留。 |
| 创建分布式任务 | 阻塞，后台状态不确定 | 1 worker、无 GPU、2 核、4 GiB、600 秒，HTTP 403：`Apply successfully but failed to retrieve status (timeout or immediate exit)`；运行、排队、历史列表均为空。 |
| 续时估价 | 阻塞 | 任务 173 返回 HTTP 403，错误码 `SITE_SUPER_ADMIN_REQUIRED`。 |
| 删除任务历史 | 通过 | 任务 173 先结束，再删除历史，均返回 HTTP 204，最终列表无该 ID。 |
| 外部镜像登记 | 阻塞 | `swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/ubuntu:26.04`，`source=chenkeyu,is_public=false`，HTTP 403：`error user`；前后均无登记记录。 |

## 未完成的测试

- 续时提交、续时状态：估价要求站点超级管理员，未生成报价或操作 ID。
- 分布式任务网络、日志、删除及历史删除：创建未返回任务 ID，不猜测 ID。
- 修改资料和密码、创建或撤销访问令牌、Tailscale 接入：会影响账号或已有连接，不纳入普通资源测试。
- 镜像公开发布：仅测试设为私有。
- 外部镜像拉取：登记被拒绝，未启动容器，不能据此判断镜像是否存在或可拉取。

## 暂存问题：分布式任务创建失败

用户要求先记录，暂不解决。原请求使用 `ubuntu-base:v1`、1 worker、无 GPU、关闭 IB、逐 worker 启动，命令为 `/bin/sh -c 'echo DIBU_JOB_OK; sleep 300'`。提交时间约为 2026-11-06 14:17:20。

对照部署文档：

- 一条命令对应一个 worker；文档未规定至少两个 worker，也未明确禁止 CPU-only 分布式任务。
- 文档的 IB 最低 GPU 数量存在 2 与 8 的矛盾，不能将其中一个数字固化为规则；本次关闭 IB，因此该限制不解释失败。
- 示例使用自定义训练镜像；这既不能证明 `ubuntu-base:v1` 兼容，也不能证明其不兼容。
- 响应表示已申请但状态获取失败，不能归因为配额、命令引号、GPU 或 worker 数量。
- 精确诊断需要相应时间的后端创建/状态查询日志、Job/Pod 事件以及 master/worker 启动日志。空列表不能证明后台无残留。未重复提交原请求。

## 暂存问题：外部镜像登记被拒绝

请求结构与前端适配器一致：`image_name,image_tag,source,is_public,note`。`error user` 未指出具体规则，可能涉及服务端用户检查；不能直接认定为仓库不存在或不可拉取。未通过更换来源或重复提交猜测规则。

## 脚本维护与回归

- 认证只从 `~/.cache/dibu_token` 读取。已验证文件缺失、空文件、不可读、格式错误、首尾空白处理及忽略 `DIBU_TOKEN` 环境变量。
- HTTP 401、403 和其他错误应保留服务端响应并隐藏认证值。已用模拟响应验证 400/401/403 内容保留及 token 脱敏；401 提示应指向 token 文件。
- 变更接口时先对照当前前端与服务端响应；不要根据单次测试推导永久权限、配额或通用默认值。
- 写入测试使用独立临时资源，记录创建 ID、估价、稳定幂等键和清理结果；响应不确定时先查询，不自动新建请求。
- 历史测试用的镜像 34 已按用户要求保留；不要把历史 ID 当作未来测试的固定目标。
- 使用当前项目明确指定的 Python 环境执行脚本和校验，不沿用历史机器的解释器路径；缺少依赖时遵循当前项目的安装约定。
- 在源码目录维护，安装目录由用户手动同步。不要把 token、密码、含秘密的原始响应加入仓库。
- 运行技能创建器的 `quick_validate.py` 和 `git diff --check`；语法与本地回归通过不代表服务端所有接口可用。

## 2026-11-08 使用反馈与本地维护

- 创建任务的空 password 被服务端以 blank 拒绝；CLI 现在提交前校验并在预览中脱敏，正文文件仍由调用者安全保存。
- gpu-inventory 曾 stale=true 且 available_cards=null；dashboard 更鲜但与 inventory 的内存数不一致。新增 resource-summary 同时展示来源，未知可用量不补成物理总数。
- Pending 曾出现内存不足、节点 taint、ResourceClaim 模板缺失；Running/历史 finished 不能证明应用评测成功。
- 新增 task-summary/task-status 的分页摘要与按 ID 事件查询。摘要/校验本地模拟测试不代表新接口在线端到端验证。
- 用户明确偏好：支持且能实际利用多卡的任务，未指定卡数时默认按可调度资源与应用上限申请最大有效 GPU 数；多组任务应联合分配，不能重复计算空闲卡。

本次维护验证：5 项离线回归测试通过，覆盖创建参数、预览脱敏、过期/未知/禁调度资源、分页检索及事件摘要；quick_validate 通过。未创建、取消、扩容或修改任何线上工作负载。

后续用户修订：资源预检及 resource-summary 只读取 dashboard，不再自动读取 gpu-inventory；任务运行日志统一保存到 `/workspace/task_run_logs/` 的独立运行子目录。历史记录中的双来源方案已被此规则取代。


## 2026-11-08 live output review

Executed 35 bounded read-only requests: 34 succeeded; `container-network` returned HTTP 503. No resources, files, account settings, or credentials were modified. Responses stayed in process memory; only schema names, types, sizes, and aggregate comparisons were emitted. Authentication came from the existing token file. No raw samples were persisted.

Initial sampling covered `dashboard`, `gpu-inventory`, `config`, `tasks`, `experiments`, `jobs`, `images`, `files`, `shared-files`, `datasets`, `file-space`, `profile`, `access-token-info`, `tailscale-status`, `credits`, `usage`, and `ledger`.

After updating projections, sampled the first page of running, pending, and historical tasks, experiments, and jobs; rechecked images, files, shared files, and profile. Queried events, restart status, image-save status, and network for an ID discovered in the current experiment list. Read the known usage document. Did not guess IDs, download logs, generate estimates, or execute any catalog entry marked `write` (including mutating GET operations).

| Operation/sample | Raw JSON bytes | Compact JSON bytes | Reduction | Decision |
| --- | ---: | ---: | ---: | --- |
| Tasks, running | 2957 | 2315 | 21.7% | Omit command, password, pod name, addresses, ports |
| Tasks, historical first page | 13960 | 9793 | 29.8% | Same projection; retain pagination |
| Experiments, running | 927 | 728 | 21.5% | Same projection |
| Experiments, historical first page | 9521 | 7483 | 21.4% | Same projection |
| Images | 1776 | 1654 | 6.9% | Omit redundant owner nickname |
| Profile | 379 | 256 | 32.5% | Omit WeChat binding and avatar fields |
| Files / shared files | 638 / 842 | unchanged | 0% | Four essential fields already sufficient |

Sizes compare the same in-memory response serialized as UTF-8 JSON with `ensure_ascii=False`, before and after projection; they are not HTTP transfer sizes or token counts. Live assertions verified unchanged pagination and preserved IDs, actual status, timing, DRA allocation, and extension eligibility. Offline fixtures use invented values.

The earlier broad allowlist caused real task, experiment, image, and file schemas to fall back to full output. Added operation-specific observed fields rather than dropping unfamiliar fields. Timing, requested duration, DRA allocation details, image-save state, and restart state remain visible because they affect decisions. Unknown row fields still trigger full-response fallback.

### Operations retaining full output

- Resource/configuration: `dashboard`, `gpu-inventory`, `config`. Samples were approximately 1.8 KB, 4.0 KB, and 1.1 KB respectively. Preserve capacity, GPU partition/preset information, freshness, and errors. Use `resource-summary` for a focused dashboard view.
- Billing: `credits`, `usage`, `ledger`, `estimate`, `extension-estimate`, `extension-status`. Balance and empty billing pages were approximately 0.3 KB. Keep units, monetary precision, warnings, pagination, quote IDs, and fingerprints. No new estimates were generated; extension operations were not sampled.
- Small diagnostics: `file-space`, `access-token-info`, `tailscale-status`, `events`, `restart-status`, `image-save-status`. No useful redundancy in sampled responses. Nonempty event lists and Tailscale nodes were not observed.
- Network: `container-network`, `job-network`. Container network failed with HTTP 503; no current job ID was available. No schema projection inferred from failures.
- Content: `container-log`, `job-log`, `doc`. Preserve the requested content; logs were not downloaded. Documentation was approximately 6.2 KB.
- All catalog operations marked `write`: preserve full results and existing preview/secret-output protections. They were not executed for output testing.
- `jobs` and `datasets`: samples were empty; existing conservative list handling remains, but nonempty schema compatibility and reduction are unverified. Pending task/experiment samples were also empty.

These measurements cover current samples only. They do not establish compatibility with every historical row, nonempty billing record, failed event, GPU partition configuration, or future server schema. Installed skill directories remain manually synchronized by the user.


## 2026-11-08 controlled write sampling: awaiting capacity

User authorized saving a disposable image followed by creating temporary experiments/tasks for response sampling. Saving the image from existing experiment `test1` (266) did not stop that experiment. The saved image is private, ID 42, tag `dad0c3e7-v1-v3`; save status reached `finished`. It is a disposable regular snapshot (`is_temporary=false`), rather than a pause-generated image, because pausing would interrupt the source workload.

Observed writes:

| Operation | Result | Output decision |
| --- | --- | --- |
| `image-save` | Accepted; response contains only `message` | Keep full response; acceptance is not completion |
| `image-note` | HTTP 200, empty body | Keep `{status: 200, text: ""}` |
| `image-visibility` with private flag | HTTP 200, empty body | Keep existing receipt |
| `image-permanent` on disposable regular snapshot | HTTP 200, empty body | Keep existing receipt |
| `container-create` | HTTP 403, `The container num is 3, cannot be larger than 3` | Preserve diagnostic; no successful-create schema inferred |

The proposed workload uses the snapshot, 0 GPUs, 2 CPU cores, 4 GiB RAM, and 600 seconds. Two estimates returned `metering_only`, `will_charge=false`, `maximum_micro="0"`, and `billing_node_rate_missing`; no charge was inferred merely from historical pricing. Creation was submitted once with a fresh estimate fingerprint and stable idempotency key. All three task-list categories were checked afterward; no uniquely named sampling task was found. The server ignored the `search` parameter in observed responses, so exact local name matching was used.

Current experiment 266 and tasks 267/268 occupied the three container slots. The user explicitly chose to wait without stopping any existing workload. Snapshot 42 must remain private and available until sampling resumes; it has not been deleted. There is no successful temporary-workload creation, conversion, stop/restart, deletion, or history-deletion sample from this attempt. Do not mark those operations validated or retry creation while the account remains at capacity.

A credential-free, mode-600 checkpoint is saved under `/workspace/task_run_logs/dibu-output-sampling/<run>/checkpoint.json`. It contains the run name, snapshot/source IDs, attempted workload name, stable idempotency key, resource configuration, and deferred cleanup scope. Fresh pricing and current lists are required before a later submission; uncertain outcomes require reconciliation before any new creation key.

The successful save-status sample included `client_data` with repeated runtime details. Added a projection retaining `operation_id`, `image_name`, `node_name`, `auto`, and `is_temporary`, while preserving all top-level fields, result digest/size, timestamps, and errors. Unrecognized client fields fall back to full output. The measured response decreased from 741 to 437 JSON bytes (41.0%). `--raw` and `--output` retain the complete response. This is a status-query improvement; sampled write results themselves were already minimal.


## 2026-11-08 resumed write sampling: completed

This section supersedes the capacity checkpoint above. On user request to continue, current lists showed that the two business tasks had ended, source experiment 266 remained Running, and private snapshot 42 was still available. No existing workload was stopped or restarted. The previously rejected sampling name was absent from running, pending, and historical lists. New task/experiment payloads used distinct names and new idempotency keys; these were new requests after a confirmed quota rejection, not blind retries after an uncertain outcome.

Executed 57 API requests in the resumed sampling harness: 54 successful responses and three explicit HTTP failures. Initial read-only reconciliation is additional to this count. Each creation/conversion was preceded by an estimate for 0 GPUs, 2 CPU cores, 4 GiB RAM, and 600 seconds. All estimates reported `metering_only`, `will_charge=false`, `maximum_micro="0"`, with `billing_node_rate_missing`. No paid extension or permission/configuration changes were attempted.

| Operation | Observed result | Default-output decision |
| --- | --- | --- |
| `container-create`, task 276 | `{message, port, IP}`, 61 JSON bytes; actual Running status verified separately | Keep full receipt, including connection details; do not invent ID or Running state |
| `container-create`, experiment 277 | Same three fields, 61 bytes; actual Running status verified separately | Keep full receipt |
| `container-delete`, task 276 | HTTP 204, `{status: 204, text: ""}`, 27 bytes | Keep HTTP receipt |
| `container-history-delete`, task 276 and experiment 277 | HTTP 204, same 27-byte receipt | Keep HTTP receipt |
| `experiment-stop`, experiment 277 | `{message}`, 42 bytes | Keep full acceptance message; poll completion separately |
| `image-permanent`, new pause image 43 | HTTP 200, empty body, 27-byte receipt | Keep HTTP receipt |
| `image-delete`, disposable images 43 and 42 | HTTP 204, empty body, 27-byte receipt | Keep HTTP receipt |
| `experiment-restart`, experiment 277 | HTTP 409: original Pod restart service is not configured | Preserve error; no successful-response schema inferred |
| `extension-estimate`, experiment 277 | HTTP 403, `SITE_SUPER_ADMIN_REQUIRED` | Preserve structured server diagnostic; no extension submitted |
| `container-convert`, experiment 277 | HTTP 403: no resource rule for the user | Preserve diagnostic; no duplicate creation or workaround attempted |

After conversion rejection, all three task-list categories were checked for the exact attempted name: no converted task existed, and the temporary experiment remained Running. Its stop request returned before save status was populated (`{}`), and its list row initially remained Running. A later status query reached `finished`, with result digest and size, `is_temporary=true`, and a matching image name. Only then was pause image 43 identified by its new ID and exact sampling experiment name. It was made permanent as a bounded write sample and subsequently deleted. This demonstrates why acceptance, populated status, save completion, and workload termination must not be collapsed into a single success state.

Cleanup was verified through current, pending, and historical workload lists and both regular/temporary private-image lists. Task 276 and experiment 277 and their history records are absent; images 42 and 43 are absent. Existing experiment 266 remained Running. No unrelated history or images were deleted. Local sampling artifacts and checkpoint remain under `/workspace/task_run_logs/dibu-output-sampling/0ae6843891/`; response files have mode 600 and secret-named fields are redacted. No raw workload-list records or passwords were written to the repository. Application correctness was not tested; Running was used only as platform-state evidence.

The sampled write responses are already minimal. No additional write-result projection was added: retain messages, real IDs if supplied, connection details, HTTP status, warnings, and errors. `--raw` remains available, while the existing image-save-status projection handles the larger asynchronous status response. Successful conversion/restart/extension submission, distributed-job writes, account changes, and unrelated file/dataset writes remain outside this sampling result.


## CLI input discovery and named options

Operation-specific `--help` and offline `--describe` are generated from the API catalog, including descriptions, defaults, required fields/headers, typed aliases, mappings, and examples. Named options cover list categories/pagination, image scopes/search, directory paths, required identifiers, and common container creation fields. Creation remains a manually prepared quote/body/header workflow; no password generation, automatic allocation, quoting, retries, or resource mutations are added by these aliases.

Raw `--param`, `--body-file`, and `--header` remain supported. Conflicting alias/raw values or alias/body-file values fail before authentication, as do invalid typed values and operation-inappropriate flags. Raw parameters retain their body-file override behavior; conflicting repeated raw keys now fail instead of silently keeping the last value. Repeatable common options before and after the operation are combined, preserving legacy positioning. CLI-generated help, messages, and operation descriptions are now English.

Validation covers alias-to-API equivalence, image scope and boolean mappings, positive values and duration conversion, escaped path IDs, conflict detection, offline discovery for every operation, all catalog examples, compatibility of mixed-position raw options, and unchanged write previews/secret redaction. This input-only revision did not make live API requests or create new resources.


## Review follow-up: output errors, headers, and body discovery

- `--output` still saves complete successful-HTTP response bytes privately, but no longer skips JSON business-error validation. An `error` envelope raises the same API error with or without the option; saved files remain available for diagnosis. Empty bodies, non-JSON text, and binary logs still produce file receipts. HTTP error handling is unchanged.
- Additional request headers are normalized to canonical supported names before validation and preview. Case-insensitive identical duplicates collapse; conflicting duplicates, empty values, and CR/LF values fail before authentication or requests. Header values are not echoed in these validation errors.
- Added catalog-owned JSON body schemas and offline `--template` support for `container-create`, `container-convert`, `job-create`, `estimate`, `extension-estimate`, and `extension-submit`. Operation help lists field types, required status, and unit/conditional guidance; `--describe` includes nested schema details. Templates contain illustrative values and placeholders; container passwords are empty to prevent accidental reuse. They cannot be combined with request, execution, or response-output options. Schema descriptions guide clients without changing raw-field compatibility or enforcing unverified server constraints.
- Per the user's explicit instruction, unknown-field fallback and its existing password-output behavior were not modified.

Validation: 31 offline regression tests pass, covering saved business errors, no successful CLI receipt on error, non-JSON/binary/empty saves, header normalization and actual wire values, rejection before authentication, and offline templates/placeholder handling. No live API calls or resource mutations were performed for this follow-up.


## CLI online confirmation after parameter and schema changes

Detailed credential-free report: `/workspace/task_run_logs/dibu-cli-verification/3cd77970c0/report.json` (mode 600). Executed 77 CLI invocations that called the API, including composite task-status invocations; the count is not the number of individual HTTP requests. Raw responses stayed in memory. No resource/account/file mutations, log downloads, token changes, or paid extensions were performed. Quotes only generated estimates; request fingerprints were not written to the report.

Twenty successful named/raw query comparisons matched after excluding volatile sampling/request timestamps. Covered running/pending/finished task, experiment, and distributed-job categories; all/mine/public/base image scopes; temporary-image selection; image search and a deliberately nonexistent name; personal/shared root paths; event IDs; and task-status IDs resolved from current history. Public/temporary images and job lists were empty, so equality does not validate their nonempty contents. A separate image pagination check returned one different image on pages 1 and 2, with expected next/previous links; nonexistent-image search returned no rows.

Initial billing page-2/size-2 checks returned HTTP 400. Follow-up comparisons isolated both named and raw behavior: page 1/size 20 succeeded, page 1/sizes 2 and 10 returned HTTP 400, and page 2/size 20 returned HTTP 404 on empty usage and ledger lists. Additional bounded probes accepted sizes 50 and 100 and rejected 21 and 200 on both endpoints. The catalog now advertises typed billing sizes 20/50/100, with local validation; raw fields retain passthrough behavior. Do not infer that every other conceivable size is permanently unsupported.

Quote checks used the generated CPU template plus GPU selections derived from the live inventory and dashboard:

| Quote | Result | Scope of confirmation |
| --- | --- | --- |
| CPU-only template | Success, fingerprint present | Basic estimate template accepted |
| Legacy full GPU on a DRA node | HTTP 400, `node_requires_dra_gpu` | That node requires DRA; no workaround attempted |
| DRA whole GPU | Success, fingerprint present | Current whole-GPU selection syntax accepted by estimate |
| Configured DRA/MIG | Success, fingerprint present | Current config ID and preset key accepted by estimate |

Successful quotes reported `metering_only`, `will_charge=false`, `minimum_micro="0"`, `maximum_micro="0"`, and `billing_node_rate_missing`. These are sample observations, not durable charging guarantees. Inventory was stale and availability unknown; success does not prove GPU capacity or schedulability. Current inventory exposed no legacy-vGPU configuration, so vGPU syntax was not fabricated or tested. Estimate schema guidance now explains the DRA-only-node rejection.

Datasets, distributed jobs, usage records, and ledger records were still empty. Nonempty schema/output projection coverage remains open. Successful conversion, original-Pod restart, extension submission, and distributed-job creation were not retried: prior explicit configuration/account-rule failures remain the last evidence. This run does not claim those blockers were independently cleared or reconfirmed. Existing account/workloads were not changed.


## Grouped command discovery and deduplication

The public overview now presents 11 functional groups plus standalone `config` and `list`. Group help explains each action with a read/write label; action help retains detailed parameter guidance and renders canonical grouped examples. `--describe` includes the canonical command path while retaining the underlying operation ID. Old flat operation names remain accepted and retain existing request semantics, but are not repeated in the overview.

Consolidated public forms: dashboard via `resources summary --raw`; single-task state/events via `tasks summary --id`; shared directory lists via `files list --shared`; and storage recalculation via `files space --refresh`. Explicit writes still preview unless executed. Shared-directory writes remain unavailable. Current-workload deletion and history deletion are distinct operations because their effects differ.

Offline regression coverage checks grouped/legacy request equivalence, common options before and after grouped paths, offline group help, read-only shared listings, unchanged write previews for GET/PATCH/DELETE, and equality of consolidated task inspection. No live API calls or resources were used for this discovery-only change.


## 2026-11-09 tighter workload display and Ready-only resources

The installed script matched repository source at inspection. Read-only samples showed that task rows had no unknown top-level fields: the prior projection was active, but retained many legacy counters and the entire nested DRA selector definition. The observed task response was 1515 raw JSON bytes versus 1187 with the old projection.

Known task/experiment rows now keep core identity, actual status, resources, creation time, timing, and extension eligibility. Effective DRA parameters, allocation kind, preset/profile names, mode, memory, and MIG profile remain; selector count ranges and repeated node information are omitted. Nonempty save state and active commit state remain. Unknown nested DRA metadata is preserved in full, and the existing unknown-top-level fallback behavior is unchanged per user preference. Original objects are not modified; `--raw` remains full output.

`resources` defaults to compact Ready nodes only. `--all` includes other states in the compact view; `--raw` and `--output` retain the complete dashboard. Sampling, stale, refresh, and error metadata remain visible; unknown schedulable GPU counts stay null. Removed the redundant reported GPU count from the compact node and shortened the explanatory note. These changes also apply to the legacy resource-summary entrypoint.

Five read-only API requests verified current task/experiment samples and the three resource display modes. The task response decreased from 1515 to 699 JSON bytes (53.9%); the experiment response decreased from 932 to 476 bytes (48.9%). Sizes compare the same in-memory response serialized as UTF-8 JSON. Resources default returned 2 Ready nodes; `--all` and `-v` returned all 4 nodes including 2 SchedulingDisabled nodes. No credentials or raw workload samples were printed or persisted. No resources were modified.

Forty offline tests pass, including Ready-only defaults, all-state/raw modes, stale/error preservation, unknown GPU availability, unchanged pagination, effective DRA settings versus selector ranges, and unknown nested diagnostics. Installed skill synchronization remains manual.


## 2026-11-09 list-level timing and allocation detail

At user request, recognized task and experiment list rows now omit `dra_request` entirely and retain only `timing.state`. GPU type/count and actual workload status remain visible; raw output retains the allocation and complete timing data. Missing timing state remains null rather than being inferred from workload status. The prior selective DRA projection is superseded, and its unused field tables were removed. Existing unknown-top-level full-response fallback remains unchanged. Offline regressions cover both workload types, unchanged raw objects/pagination, and full `-v`/`--raw`/`--verbose` output. No online resources were queried or modified for this change.


## 2026-11-09 explicit interactive login

Added standalone `login` with terminal username input and hidden password input. It POSTs JSON `{username, password}` to `/user/login/` at the configured base URL, matching the supplied Accept, Accept-Language, Content-Type, and Referer headers. It does not read existing credentials, send Authorization/cookies, follow redirects, retry, or print the response. Only a valid token is saved, via an fsynced mode-600 temporary file and atomic replacement of `~/.cache/dibu_token`; failed input/authentication/response parsing/replacement preserves the old file. No command-line password/username, raw-response, or resource-execution flags are accepted. Inability to obtain hidden input stops login.

Missing/unreadable/empty/malformed token files and HTTP 401 now provide the actual script's manual login command. Skill instructions ask the user to run the installed CLI themselves, never to send credentials in chat; automatic login/refresh remains prohibited. This explicit manual-login workflow supersedes older instructions that only asked users to edit the token file.

Offline tests cover unauthenticated POST contents and headers, base-URL override, new cache creation and existing-token replacement, mode 600, no credential/profile output, invalid/failed responses, HTTP/network errors, hidden-input fallback/cancellation, atomic replacement failure cleanup, help/flag restrictions, and manual-login hints without automatic prompting. No real login was attempted and no real credentials or token files were changed.


## 2026-11-09 explicit distributed-task command name

Renamed the public `jobs` group to `distributed` so multi-node/worker workloads are clearly distinct from single-container `tasks`. Overview, group/action help, canonical examples, and `--describe` command paths use `distributed`; legacy `jobs` (bare, with actions, or with prefixed global options) remains compatible. Underlying API operation IDs, paths, payloads, and `job_id` fields are unchanged. This is a CLI naming change only; no online resources were queried or modified.


## 2026-11-09 private account display fields

Default account/profile responses now replace `nickname`, `grade`, `email`, `gender`, and `phone` with `*`. A local `--show-private` flag explicitly reveals them. Masking precedes compact/full display and response-file writing, so `--raw`, `--output`, and unknown-field fallback do not reveal these five fields by themselves. Saved masked responses retain full JSON fields with mode 600; they are not byte-identical to the server response unless private values are explicitly enabled. Structured HTTP errors are masked too; non-JSON private profile responses are not displayed or saved. Other operations and existing password fallback behavior are unchanged.

Offline coverage checks masked/revealed standard, raw, and saved output; local-only option handling; null/nested fields; unchanged source objects; unknown-field fallback; file permissions; malformed responses; and HTTP-error diagnostics. No live profile requests or account mutations were made.
