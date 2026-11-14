# CLI output contracts

Read when parsing saved responses, adapting an existing consumer, or diagnosing missing fields. Routine queries need only the output summary in `SKILL.md`.

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

Live workload-write sampling found creation receipts (`message`, `port`, `IP`), stop acceptance messages, and empty-body HTTP receipts already minimal; they remain complete by default. Creation may omit the workload ID, so reconcile the exact unique name in current/pending/history lists and check actual status. A stop acceptance can precede populated save status and workload termination. These observations cover sampled operations and do not establish universal write behavior.

Changing existing consumers to `--raw` preserves the previous response shape. Raw responses and fallback output may contain sensitive fields; do not paste or commit them.
