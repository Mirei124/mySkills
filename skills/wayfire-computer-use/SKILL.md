---
name: wayfire-computer-use
description: Operate existing Wayfire desktop applications through a Rust CLI using Portal/PipeWire screenshots and virtual mouse/keyboard input. Use for native visual desktop tasks, not ordinary file editing or pure browser automation. Initial runtime supports one unrotated output at scale 1; other configurations fail explicitly.
---

# Wayfire computer use

Use `target/release/wayfire-computer-use` relative to this skill directory. Build once with `cargo build --locked --release` if the executable is absent. Runtime uses no Python, GStreamer, external C helper, model API or API key. Read [usage](references/usage.md) for system libraries, build instructions and capability limits.

1. Run `doctor`. Inspect outputs, protocol versions, D-Bus service ownership and PipeWire socket access. This command does not create input devices or capture sessions. Do not change permissions or switch backends to evade access restrictions.
2. Run `start`, optionally with `--output NAME`. The production initial release requires one output, scale 1 and normal orientation. Multiple outputs require confirmation but remain gated even with a confirmed name; stop on the explicit error. A single output is selected automatically for mapping.
3. Portal source selection can require interaction. Only with explicit user authorization, add `--auto-select-single-output` to permit one native virtual-pointer click on a newly detected slurp monitor selector. This bootstrap is pointer-only, submits a start notification first, and never retries automatically. Process detection cannot prove an active input grab; stop on ambiguity or disappearance.
4. Actually view the returned PNG with the host image viewer before acting. A path alone is not an observation. Identify the target and current focus. Input shares the user's cursor and keyboard focus; serialize control and stop if unexpected changes invalidate the target.
5. Send one action envelope to `act` on stdin, using the current session_id/observation_id and a new request_id. View every resulting screenshot before continuing. Supported actions are screenshot, wait, move, click, double_click, drag, scroll, keypress and type. See [actions](references/actions.md).
6. Treat action_executed on an error as possible partial execution. Do not automatically replay side effects. Identical request IDs deduplicate only within the current session; changed content with the same ID fails. Layout changes invalidate old coordinates. Stop and restart to establish a new mapping after failures.
7. Always `stop` at completion, cancellation or failure. It bypasses the action queue and waits for input/capture/Portal cleanup and the end-notification attempt. Inspect the errors array. Repeated stop returns the saved completion result. `release_all` is a recovery management command, not a standard action.

The same Rust executable runs a supervised input-worker process; no separate helper artifact is needed. A failed start notification prevents ordinary input. End notifications follow device cleanup and control-lock release. Notifications do not prove the user saw them. Killing the entire process group or losing the desktop bus can prevent an end notification.

Chinese, ASCII and symbols have passed isolated GTK tests using temporary keymaps with experimental settling delays; do not infer universal IME/emoji/toolkit support. No clipboard fallback is enabled. The complete historical reliability matrix is not claimed as passed. See [testing scope](references/simulation-tests.md), [troubleshooting](references/troubleshooting.md) and IMPLEMENTATION.md. Python/C code in archive/legacy is historical and is not the runtime. This skill does not register a native computer tool.
