---
name: dibufusion-api
description: Operate the internal DibuFusion GPU console at 10.249.187.159:32320 through direct HTTP APIs. Query resources, workloads, files, datasets, images, billing, and settings, or perform specifically authorized resource operations without browser interaction.
---

Use this skill's `scripts/dibu.py` (Python standard library only). The default site is `http://10.249.187.159:32320`; `DIBU_BASE_URL` selects another site. In examples, `CLI` is the script's absolute path.

## Discover the requested operation

Use `list` or `--help` for groups, `GROUP --help` for actions and read/write labels, and `GROUP ACTION --help` for typed flags. `--describe` prints the API entry and body schema; supported creation and estimate actions also provide `--template`. Discovery is offline and requires no credentials. Templates contain illustrative IDs and empty passwords, not ready-to-submit requests.

```bash
python "$CLI" resources summary
python "$CLI" tasks summary --id 276
python "$CLI" workloads create --describe
python "$CLI" billing estimate --template
```

Use `tasks` for single-container tasks, `experiments` for interactive containers, and `distributed` for multi-node/worker tasks. `jobs` and old flat operation names remain compatibility aliases. `tasks summary` covers task categories, not experiments or distributed workloads. `--state` selects a list category; inspect each row's actual status. Prefer exact local ID/name matching when reconciling writes; server-side search has been observed to return unrelated rows.

Prefer typed flags from action help. `--param KEY=VALUE`, `--body-file`, and `--header` remain raw escape hatches; named/body/raw conflicts are rejected. Do not guess unsupported flags. The catalog [references/operations.json](references/operations.json) owns operation schemas; read it only for unsupported fields or catalog maintenance.

## Resource operations

Read [references/workflows.md](references/workflows.md) before allocation, creation/conversion, extensions, or nontrivial file/image operations. It covers resource preflight, quotas, runtime planning, payloads, quoting, and asynchronous completion.

If no GPU count is specified and the application is verified to use multiple GPUs, request the largest fresh, schedulable count it can effectively use, bounded by quota, CPU/RAM, VRAM, parallelism, and topology. User counts and budgets take precedence. Jointly allocate concurrent runs; match workers to cards. `device_map=auto` alone does not prove multi-GPU utilization.

Writes preview by default; pass `--execute` for the specifically authorized action without asking again. Read-only resource requests do not authorize creation or stopping workloads. Do not stop unrelated workloads to free capacity. Some GET operations are writes; action help identifies them.

Creation requires a nonempty random password in a mode-600 body file, an estimate for the exact resource configuration, `X-DibuFusion-Estimate-Fingerprint`, and a stable `Idempotency-Key`. An estimate does not establish quota or schedulability, and past `metering_only` observations do not establish future free usage. After an uncertain network outcome, reconcile the exact workload before retrying with the existing key. Changed payloads require a new quote and key; do not repeat resource mutations automatically.

## Authentication

The CLI reads only `~/.cache/dibu_token` (UTF-8 bare token, mode 600), never `DIBU_TOKEN`. No shell configuration is needed for API authentication. Do not print or commit credentials.

For missing/invalid credentials or HTTP 401, stop authenticated calls and ask the user to run the actual installed script manually:

```bash
python "$CLI" login
```

Login uses hidden password input and atomically replaces the token only on success. Do not run interactive login or refresh credentials on the user's behalf, or request credentials in chat. Wait for the user's completed login before retrying. Diagnose HTTP 403 from its response body; quota, configuration, and field-validation failures are not interchangeable.

## Output and verification

Default JSON is compact for recognized lists; unknown fields can trigger full-response fallback. `--raw`, `-v`, and `--verbose` request full responses. `--output FILE` privately saves the full response (mode 600), not necessarily the compact JSON printed by a normal query. It also preserves error responses and does not turn business errors into success. Profile privacy masking still applies unless explicitly enabled with `account --show-private`. Raw responses, logs, and fallback output may contain secrets.

`resources summary` defaults to Ready nodes; `--all` includes other states, while `--raw` or `--output` retain the complete dashboard. Preserve stale/error metadata and treat null availability as unknown. For field-level projections, summary envelopes, privacy exceptions, or existing JSON consumers, read [references/cli-output.md](references/cli-output.md).

Save stdout, stderr, startup/exit records, and worker logs under `/workspace/task_run_logs/<task>/<run>/`. Keep a credential-free project index linking workload ID, configuration, result paths, logs, and validation status. Include required project environment setup inside the submitted command, not only the submitting shell; suppress secret-printing bootstrap output.

Resolve the real workload ID after submission; receipts may omit it. Check actual status/events and application logs. Submission acceptance, Running, worker startup, and validated completion are different states. `Not exist or finished` does not prove success. An application can fail while its container still shows Running; report that discrepancy before considering an authorized replacement. Project-level metrics and complete, unique sample/result artifacts establish application correctness, not an exit code alone.
