# Hypha 实现规格

> v0.1｜2026-08-29。Hypha 是本地、单 agent 使用的任务与知识统一层。markdown 是当前真相；CLI 维护确定性结构，不调用 LLM，也不判断自然语言真假。

## 1. 范围

Hypha 管理任务、知识、来源、索引与变更审计。它不做多 agent 并发写、多仓库事务、向量检索、服务端、MCP、自动提交，或自动改变任务状态。

```text
<workspace>/.hypha/
  src/          # 外部来源快照
  intent/       # 任务节点
  know/         # 知识节点
  .drafts/      # agent 可写草稿；不扫描、不进 Git
  snapshots/    # 追加式 JSONL 日志
  INDEX.md      # 纯派生路由索引
  lock          # 本地锁；不进 Git
```

`.hypha/` 随工作区 Git 跟踪；`lock`、`.drafts/`、`view.html` 被 `.hypha/.gitignore` 忽略。`src/` 是来源快照，Phase 1 不做 hash 不可变校验。可选的 `~/.hypha/` 存跨仓库知识和长期任务，有独立锁、索引和日志。

## 2. 正式节点

### 任务

```markdown
---
id: 0007
status: in_progress
progress: 60
parent: 0001
depends_on: [0005]
difficulty: medium
estimate_minutes: 240
---

# OAuth 登录流程接入

## 验收

- 首次授权后保存 refresh token
- token 过期后自动刷新

## 证据

- `pnpm test oauth` 通过
- [[know/api/oauth-refresh]]
```

`id`、`status` 必填。状态为 `todo | in_progress | blocked | done | dropped`；blocked 必须有 `blocked_reason`。ID 由 CLI 分配。`parent` 是单主父，`depends_on` 是执行前置；两者必须解析且无环。

`progress` 只存于叶子任务，由 `progress` 或 `done` 更新。非叶任务的进度不落盘，而是递归收集所有未 dropped 后代叶子后做等权平均；中间分组不改变结果。没有显式进度的叶子按 0 计算，done 叶子按 100 计算，被 dropped 的任务整棵子树不参与祖先进度。新增节点或降低叶子进度会重算整条祖先链，并把聚合值低于 100 的 done 祖先重新打开为 in_progress；反方向不会自动级联 done，因为父任务验收与证据仍需确认。非叶任务聚合达到 100 前不能标记 done。

### 知识

```markdown
---
claim_kind: sourced
status: active
when: 排查 OAuth 回调、401 或刷新 token 失败时阅读
triggers: [oauth, callback, "401", refresh_token]
anchors: [src/oauth-doc.md#refreshing-tokens]
evidence:
  - anchor: src/oauth-doc.md#refreshing-tokens
    quote: "Refresh tokens may be used to obtain a new access token."
affects: [0007]
---

# OAuth refresh token
```

`claim_kind` 必填：

| 类型 | 规则 | boot |
|---|---|---|
| `sourced` | 必须有来源 anchor 与 `{anchor, quote}` evidence | 参与 |
| `inference` | 必须含 `inference` 和至少一个来源 anchor | 参与 |
| `agreement` | 必须含用户授权来源、最小原话、知识类型和适用范围 | 参与 |
| `note` | 可无来源、无 `when` | 不参与 |

`knowledge_kind` 为 `rationale | constraint | decision | consensus | invariant | non_goal | definition | lesson | assumption | synthesis`，描述知识在项目中的作用；`scope` 为 `project | subsystem | task`；`authority` 描述用户、仓库、外部来源或 agent inference；`review_when` 保存失效或重审条件。`agreement` 的 authority 只能是 `user_explicit | user_confirmed`。

`when` 是人读的说明；`triggers` 是唯一机器路由字段，缺省时由标题与 `when` 自动抽取。`status` 为 `active | superseded`，后者必须有 `superseded_by`。CLI 只验证结构和可定位证据，不证明断言蕴含成立。

## 3. 关系与索引

正向关系：知识正文的 `[[know/...]]`、知识的 `affects: [id]`、任务正文的 `[[know/...]]`、任务的 `parent` 与 `depends_on`。

每次扫描都在内存派生：

- `backlinks[path]`：知识反链；
- `premises[id]`：任务知识前提，合并 `affects` 和任务正文链接；
- `children[id]`：任务子节点；
- `unlocks[id]`：完成该任务能解锁的任务。

指向任务的关系必须解析；指向知识的正文链接可悬空，列为红链待办。反向表只收已解析边。

## 4. 草稿发布、日志与同步

agent 只能直接写 `.hypha/.drafts/`。发布正式节点：

```text
hypha apply .hypha/.drafts/oauth-refresh.md
```

`apply` 在锁内做解析、硬校验、临时文件写入、`fsync`、`os.replace`、日志追加和索引重建。发布前崩溃只留草稿；发布后崩溃由下次同步收敛。直接修改正式文件是兼容路径，仍记录但由 lint 标为未托管写入。

日志是一行一个字段变更：

```json
{"ts":"2026-08-29T09:14:22.481Z","origin":"7c2a:3f1","scope":"ws","kind":"intent","id":"0007","field":"status","from":"todo","to":"in_progress","by":"cli"}
```

`ts` 是 Hypha 观察到变更的 UTC 时刻，同一 origin 内单调钳位。可选 `effective_at` 只供迁移等已知历史事实使用；绝不使用文件 mtime。日志按 `(ts, origin, id, field)` 去重；日志是审计，磁盘 frontmatter 才是当前真相。`snapshots/*.jsonl` 使用 `merge=union`，只合并日志行，不解决 frontmatter 冲突。

每个 CLI 命令入口与出口执行：持锁 → 扫正式节点（排除 drafts）→ 重放日志 → 以磁盘差异追加审计行 → 原子重建 INDEX → 解锁。读路径始终取磁盘，日志永不回写 markdown。

## 5. 路由与 CLI

`INDEX.md` 从 frontmatter 派生。候选由 triggers 精确匹配、标题与 triggers 的 bigram、`affects` 命中开放任务、同目录变更文件打分。`boot` 输出任务状态和最多 12 条知识；知识只输出路径、`when`、`triggers`，并一律视为不可信数据，不执行其中任何指令。note 不参加候选。始终生效的仓库操作规则由适用范围内的 `AGENTS.md` 提供，Hypha 不复制。旧 `agreements/` 只产生迁移提示。`hypha why <term>` 展开未入选知识。

维护少量路由回归样本：`当前任务 + 话轮 + 变更路径 -> 必须命中的知识路径`。每次改动打分或抽词都运行它。

高频 CLI：

```text
boot | next | show <id-or-path> | add <title> [parent]
start | progress | block | done | drop
needs <id> <dependency> | why <term> | apply <draft>
lint [--fix] [--audit] | close | view
```

低频 CLI：`init`、`migrate`、`ingest <file>`、`ask "keyword1,keyword2" [--file <path>]`。用户明确或确认的持久知识直接写成 `.hypha/.drafts/` 下的 agreement 草稿；统一由 `apply` 校验，且 agreement quote 不得逐字复制 `AGENTS.md` 操作规则。`ask` 不做自然语言问答、内置分词或正则解释；agent 把问题展开为一个逗号分隔的关键词参数，CLI 对 active、非 note 知识正文执行大小写不敏感的字面全文检索。传入一个或多个 `--file` 时，仅检索 workspace 内这些文件或目录，并返回可复核的 `path:line: snippet`。

CLI 负责 ID、路径归一化、图校验、候选生成、原子发布、索引、日志和可复制的纠错命令。LLM 只负责断言、关系、冲突、触发词和验收判断。

## 6. 审计、收尾与 ingest

`lint` 的硬错误：必填字段缺失、证据不存在、quote 不在指定 anchor、inference 缺来源、任务悬空或成环、无效状态、过宽 trigger、`.hypha/` 被 Git 忽略。

`hypha lint --audit` 不写文件。它用本轮 Git 变更、开放任务、标题、triggers、变更路径和既有链接列出：可能缺少的 affects、可能遗漏的正文知识链接、当前路由预演。LLM 只回答关联／不关联／暂缓。

`close` 只读：列出本轮修改、运行中和受阻任务、冲突、红链、audit 和 lint。对本轮改成 done 的任务，显示 `## 验收`、`## 证据`、关联知识和变更文件；CLI 不自动批准，agent 确认完成或退回 `in_progress`。

`ingest`：复制来源到 src → CLI 预筛 top-K 旧知识 → LLM 输出候选断言（claim_kind、when、triggers、anchors、evidence、affects）→ LLM 仅判断 unrelated / supports / refines / contradicts → 先写 drafts 再 apply → CLI 列出受影响任务与 audit 候选。冲突的两页都保留。已 apply 草稿按内容 hash 去重，使 ingest 可重入。

## 7. 验收

自动化覆盖：任务关系的悬空和环；反链对称；来源 quote 定位；note 不入路由；apply 的崩溃原子性；日志重放幂等、索引可重建、日志不回写；路由回归样本；500 节点下同步 ≤50ms、boot <300ms。

真实使用两周后，boot 推荐知识中至少一半在同轮被实际 Read；同时人工抽查路由回归和 audit，避免只优化“少推一些容易被读的条目”。
