---
name: dibufusion-api
description: Operate the internal DibuFusion GPU console at 10.249.187.159:32320 through direct HTTP APIs. Query resources, workloads, files, datasets, images, billing, and settings, or perform specifically authorized resource operations without browser interaction.
---

Use this skill's `scripts/dibu.py`; it requires only the Python standard library. The default site is `http://10.249.187.159:32320`. In the examples, `CLI` is the absolute path to that script.

## Discover only the operation you need

Routine calls do not require reading the full API catalog or workflow reference. Use `--help` or `list` for the command overview, `GROUP --help` for actions and read/write labels, and `GROUP ACTION --help` for typed options, defaults, required fields/headers, and examples. Use `GROUP ACTION --describe` for the underlying operation entry as JSON, including body schemas. Public commands are grouped by resource; legacy flat operation names remain compatible but are omitted from the overview. Creation, conversion, job creation, workload estimates, and extension estimates/submissions also provide `--template` for an editable JSON body. Discovery works offline without authentication, even for write operations or operations with missing required fields. Examples contain illustrative IDs; resolve current IDs before execution.

```bash
python3 "$CLI" list
python3 "$CLI" tasks list --help
python3 "$CLI" workloads create --describe
python3 "$CLI" workloads create --template
python3 "$CLI" billing estimate --template
python3 "$CLI" resources summary
python3 "$CLI" tasks summary
python3 "$CLI" tasks summary --id 276
python3 "$CLI" tasks list --state running --limit 20
python3 "$CLI" experiments list --state finished
python3 "$CLI" images list --scope mine --temporary true --query ubuntu
python3 "$CLI" files list --path /dotfiles
python3 "$CLI" files list --shared --path /datasets
python3 "$CLI" billing usage --page 1 --limit 20
python3 "$CLI" images note --id 42 --note "Sample image"
```

## Command groups and consolidated entrypoints

| Group | Purpose |
| --- | --- |
| `resources` | Dashboard summaries and GPU configuration |
| `tasks` | Task list, all-category summary, and one-task inspection |
| `experiments` | Interactive experiment list, stop, restart, and conversion |
| `distributed` | Distributed task list, creation, deletion, network, and logs |
| `workloads` | Container task/experiment creation, deletion, events, network, and logs |
| `images` | Image list, snapshots, metadata, registration, and deletion |
| `files` | Personal/shared listings and personal path/storage operations |
| `datasets` | Dataset registration metadata |
| `account` | Profile, credentials, and Tailscale enrollment |
| `billing` | Credits, usage, ledger, estimates, and extensions |
| `docs` | Platform documentation |

`login` interactively obtains and saves an authentication token; `config` reads frontend configuration; `list` repeats the command overview. Groups with a default action list it in group help. Routine query groups default to their list action; `resources` defaults to the compact Ready-node summary (`--all` includes other node states), `account` to profile, and `billing` to credits. Explicit actions are recommended in scripts. Use `distributed` for multi-node/worker tasks and `tasks` for single-container tasks. The old `jobs` group remains a compatibility alias and is hidden from the overview; API operation names and fields such as `job_id` remain unchanged.

Consolidated forms are `resources summary --raw` for the full dashboard, `tasks summary --id ID` for one task plus events, `files list --shared` for shared listings, and `files space --refresh` for a storage recalculation (write). Existing `dashboard`, `task-status`, `shared-files`, and `file-space-refresh` calls keep their original behavior. Shared listing does not enable shared-directory writes. Deleting a current workload and deleting its history remain distinct actions.

Billing `usage`/`ledger` support `--limit 20|50|100`; start at page 1 and follow returned pagination (page 2 of an empty list returns HTTP 404).

`--state` selects a list category (`running`, `pending`, or `finished`); it does not guarantee the actual state of returned rows. `--scope` selects `all`, `mine`, `public`, or `base` images. `--id` maps to the operation's actual identifier field. Other options are operation-specific; unsupported options are rejected. Creation options include `--image`, `--cpu`, `--memory`, `--duration` (positive seconds or integer `s`/`m`/`h` suffix), `--name`, `--command`, and `--mode task|experiment`. They supplement a body file and do not generate passwords, estimate costs, select resources, or submit automatically.

Templates are illustrative configurations, not automatic resource choices or quotes. Replace ID/name/command placeholders and generate a password in a mode-600 file before use; container templates intentionally leave passwords empty. `--template` prints only the body and cannot be combined with execution, request, response-output, or other discovery options. Use shell redirection to save a template, then protect the file before filling secrets. Body schemas document field types, required fields, units, conditional task commands, and GPU selection guidance; they do not replace server validation or restrict additional raw API fields.

`--param KEY=VALUE` remains the raw API escape hatch. JSON numbers, booleans, arrays, objects, and null are parsed; other values stay strings. `--body-file payload.json` supplies an object. Conflicting named options and raw parameters/body-file fields are rejected; repeated conflicting raw parameters are rejected without printing their values. Legacy raw parameters still override body-file fields. Common options work before or after the operation.

[references/operations.json](references/operations.json) is the single source for operation metadata and typed option mappings; inspect it only when maintaining the catalog or investigating unsupported fields. Read [references/workflows.md](references/workflows.md) for resource selection, creation/conversion payloads, quoting, extensions, asynchronous lifecycle operations, or nontrivial file/image semantics. Simple queries and exact-ID operations can use focused CLI help.

Writes default to a redacted preview. Once a specific operation is authorized, pass `--execute` without asking again. Some GET operations mutate state; use the catalog's `write` flag. `--dry-run` previews ordinary API operations without authentication or requests; summary commands do not accept it. Creation still requires a nonempty password in a protected body file, the estimate fingerprint, and an idempotency key. Use `--header NAME:VALUE` for required headers; see operation help. Header names are normalized case-insensitively. Identical duplicates are deduplicated; conflicting duplicates, empty values, and multiline values fail before authentication or submission, including in previews.

## Response output

Default output remains JSON. Recognized task, experiment, job, image, file, shared-file, and dataset lists omit known bulky configuration fields while preserving identifiers, actual status, resource values, pagination, and envelope diagnostics. Lists with unknown row fields, missing identifiers, or unfamiliar structures fall back to the full response. This conservative fallback can still produce large output; it does not indicate an error.

- `--raw`, `-v`, and `--verbose` are equivalent: return the full API response without projection. They do not enable HTTP tracing.
- `--output response.json` saves the full response with mode `600` and prints only a file receipt for API operations. It takes precedence over display options. A JSON business error is still reported as a failure after the complete response is saved; the CLI exits nonzero and prints no successful file receipt. Non-JSON logs and empty responses remain supported. Secret-returning operations still require this option.
- `resources` / `resources summary` default to Ready nodes only, with compact availability fields and sampling/stale/error metadata. `--all` includes all node states in the compact view. `-v` / `--raw` returns the complete dashboard without filtering; `--output` also saves the complete dashboard. Stale or disabled nodes do not gain known schedulable GPU counts. The older `reported_free_gpus` field is available in dashboard form as `gpu_remain_num`.
- `resource-summary --raw` returns the dashboard response. `task-summary --raw` and `task-status --raw` return a `responses` array containing each request's operation, query, and full response, including fetched pages and events. Summary `--output` saves this full representation with mode `600` without printing it.
- Task and experiment lists show workload ID/name, actual status, node, GPU type/count, CPU/memory, creation time, timing state only, and extension eligibility. DRA request details and elapsed/remaining timing values are omitted; use `-v` / `--raw` when diagnosing GPU allocation or timers. Nonempty image-save state and active commits remain visible. Legacy duration counters, image/account details, restart flags, connection addresses, ports, pod names, passwords, and commands require `--raw`. Unknown top-level row fields still trigger the existing full-response fallback. Image lists omit the redundant owner nickname. Profile output omits WeChat binding and avatar fields. `account` / `account profile` (and legacy `profile`) replace `nickname`, `grade`, `email`, `gender`, and `phone` values with `*`, including raw output, unknown-field fallback, and saved responses. Only the local `--show-private` option reveals these values: `account --show-private`. It is not sent to the API; `-v` alone does not reveal these fields. File lists already contain only essential fields.
- Image-save status omits recognized runtime identifiers from `client_data`, while preserving operation ID, image name, node, temporary/automatic flags, result, timestamps, and diagnostics. Unknown client fields trigger full-response fallback.
- Write results, estimates, billing, dashboard, GPU inventory, config, other diagnostics, logs, documentation, and other unadapted operations retain their full responses, including IDs, fingerprints, warnings, and errors. Previews retain their existing redaction regardless of `--raw`.

```bash
python3 "$CLI" tasks list --param size=20
python3 "$CLI" tasks list -v --param size=20
python3 "$CLI" tasks list --output tasks.json
```

Live workload-write sampling found creation receipts (`message`, `port`, `IP`), stop acceptance messages, and empty-body HTTP receipts already minimal; they remain complete by default. Creation may omit the workload ID, so reconcile the exact unique name in current/pending/history lists and check actual status. A stop acceptance can precede populated save status and workload termination. See [maintenance/verification.md](maintenance/verification.md) for sampled coverage and failures.

Changing existing consumers to `--raw` preserves the previous response shape. Raw responses and fallback output may contain sensitive fields; do not paste or commit them.

## GPU allocation policy

Before allocation, query `resources summary` (dashboard only) and current workloads. If the user has not specified a GPU count and the program is verified to actually use multiple GPUs, request the largest currently schedulable count the workload can effectively use. Explicit counts, budgets, and resource limits take precedence.

Bound the count by fresh free GPUs, CPU/memory ratios, VRAM, quota, parallelism, and topology. Single-node programs cannot sum GPUs across nodes; unverified cross-node support does not establish distributed capability. Allocate multiple workloads jointly, refresh availability between submissions, and do not reuse the same free-GPU snapshot for every allocation. Match workers/data shards to the allocation; `device_map=auto` alone does not prove effective multi-GPU use. See [resource preflight](references/workflows.md#资源预检与最大有效卡数).

Resource queries do not authorize creation, expansion, or stopping existing workloads. Estimate the actual chosen configuration and respect existing budget/charging authorization. Do not stop other workloads to resolve resource shortages.

## Authentication and failures

API authentication is loaded only from `~/.cache/dibu_token`: a readable UTF-8 file containing a nonempty bare token, with surrounding whitespace trimmed. Use mode `600`. The script adds `Authorization: Token <token>`; it does not read or fall back to `DIBU_TOKEN`. Do not print or commit credentials. `DIBU_BASE_URL` can override the site; use its matching token file. No shell configuration or environment export is required.

When authentication is missing, unreadable, empty, malformed, or rejected with HTTP 401, stop authenticated requests and give the user a command to execute manually:

```bash
python ~/.agents/skills/dibufusion-api/scripts/dibu.py login
```

Use the actual installed script path if it differs. The CLI's error message also provides a command for its own script path. Do not run interactive login on the user's behalf, refresh credentials automatically, or ask for usernames/passwords or plaintext tokens in chat. Wait until the user completes login before retrying the requested authenticated operation.

The user enters a username and a password with hidden terminal input. `login` sends an unauthenticated POST to `/user/login/` at the configured site, without an Authorization header or cookies. On success it validates the response token and atomically replaces `~/.cache/dibu_token` with mode `600`; token/password and profile response are never printed. Rejected/malformed responses, cancelled input, and failed replacement preserve the existing token. If hidden password input is unavailable, login stops rather than echoing it. Login accepts no credential flags, raw response options, or resource-write execution flags. `DIBU_BASE_URL` selects the login site as well as authenticated API requests; login is only performed when the user explicitly runs the command.

 Diagnose HTTP 403 from the response body rather than assuming a permission problem from the status alone. Do not replay old browser quote fingerprints or idempotency keys.

Writes are not retried automatically. After an uncertain network outcome, reconcile exact workload names, IDs, and state before retrying with the existing idempotency key. Do not generate a new key to repeat an uncertain creation.

## Logs and actual state

Keep workload stdout, stderr, startup/exit records, and worker logs in separate task/run directories under `/workspace/task_run_logs/`; avoid overwriting previous runs.

`tasks summary` paginates task categories. `tasks summary --id ID` searches them and attaches scheduling events. Query `experiments list` and `distributed list` separately; task summaries do not cover all workloads.

After creation, resolve the real ID, actual status, and events. Running-category rows can be Pending. Submission acceptance, Running, application startup, and verified results are distinct stages. `Not exist or finished` only indicates that the workload ended or is absent. Project scripts must verify result completeness and metrics; platform state cannot establish application correctness.

## Maintenance evidence

Read [maintenance/verification.md](maintenance/verification.md) only for historical availability, known failures, sampling coverage, or skill maintenance. Installed skill directories are manually synchronized by the user; maintain source in this repository.
