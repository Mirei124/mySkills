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
- 当前工作环境使用 `/Users/connor/.pyvenv/bin/python3` 执行脚本和校验；缺少依赖时提醒用户安装。
- 在源码目录维护，安装目录由用户手动同步。不要把 token、密码、含秘密的原始响应加入仓库。
- 运行技能创建器的 `quick_validate.py` 和 `git diff --check`；语法与本地回归通过不代表服务端所有接口可用。
