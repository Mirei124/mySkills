---
name: wayfire-computer-use
description: Operate an existing Wayfire desktop session through portal screenshots and virtual mouse/keyboard actions. Use for native desktop applications that require visual interaction. Initial release with explicit capability limits; do not use for ordinary file editing or pure browser automation.
---

# Wayfire computer use

Use the repository `.venv/bin/python3` to run `scripts/computer.py`. Read [usage](references/usage.md) for dependencies, build instructions, JSON envelopes, and known limits. The initial release retains the documented capability limits; do not claim the full design-plan reliability matrix passed.

1. Run `doctor`. Inspect Wayland access, protocols, output geometry, portal, PipeWire and notifications separately. Never alter socket permissions or switch backends to evade access restrictions.
2. Run `start`. A sole output is chosen automatically for mapping. Ask the user to confirm an output when several exist; pass `--output NAME`. The portal can independently require interactive source selection. With explicit user authorization, `--auto-select-single-output` permits one wlrctl click on a newly detected single-output slurp selector; see usage for bootstrap limits. Do not repeat it on uncertain outcomes. Production multi-output input remains gated; only the specific eDP-1 plus HEADLESS-8 test configuration has passed integration testing.
3. View the returned screenshot using the host image viewer. A path alone is not an observation. Identify the target application and current focus before input. For controlled testing, use the dedicated fixture and its process/focus guard; stop if the fixture closes or loses focus.
4. Send one action envelope to `act` on stdin. Use the current session_id and observation_id, and a new request_id. View each resulting screenshot before continuing. Input shares the user's real cursor and focus; serialize control and stop when unexpected desktop changes invalidate the target.
5. If a result reports action_executed on failure, partial input may have occurred. Do not replay the action automatically. Identical request IDs deduplicate execution. Layout changes invalidate observations; stop and establish a new mapping.
6. Always `stop` on completion, cancellation or failure. Verify cleanup completion; stop returns after cleanup and the end-notification attempt, with errors also recorded in the private runtime stopped.json. `release_all` is a recovery command, not a standard computer action.

Start notifications must succeed before input. End notifications follow release of devices and the control lock; a notification request does not prove the user saw it. The helper owner monitors idle timeout and helper exit, but lifecycle/failure coverage remains incomplete. No clipboard fallback is enabled. Unicode has passed a limited GTK test with experimental settling delays; do not infer universal IME, emoji or toolkit support.

See [actions](references/actions.md), [usage](references/usage.md), and [troubleshooting](references/troubleshooting.md). This package does not register a native computer tool or call a model API.
