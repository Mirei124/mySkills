# Diagnostics and recovery

Run `target/release/wayfire-computer-use doctor` inside the intended Wayfire session. It reports outputs/protocols, session-bus service ownership and PipeWire socket access without creating input devices. Service ownership does not establish capture permission or successful streaming. Do not change socket permissions or switch input backends to evade restrictions.

| Result | Response |
|---|---|
| WAYFIRE_IPC_UNAVAILABLE / WAYFIRE_IPC_ERROR | Window management requires the intended WAYFIRE_SOCKET and ipc/ipc-rules plugins. Inspect availability; do not silently change compositor configuration or choose another session. |
| TOPLEVEL_NOT_FOUND / TOPLEVEL_CLOSED / TOPLEVEL_IDENTITY_CHANGED | List windows again and identify the intended current ID/PID. Do not choose a same-title replacement automatically. |
| TOPLEVEL_OUTPUT_MISMATCH | An active owner cannot focus a window outside its selected output. Stop and explicitly select the intended output before controlling it. |
| TOPLEVEL_FOCUS_TIMEOUT / WAYFIRE_IPC_TIMEOUT | Confirmation or IPC did not complete within three seconds. Inspect focus_request_may_have_executed and do not retry automatically. Refresh the screenshot before further input. |
| WAYLAND_UNAVAILABLE | Check the intended session's Wayland socket/access. Permission errors do not prove missing protocols. |
| WAYLAND_RESPONSE_TIMEOUT | The compositor did not answer within the bounded roundtrip. Stop; do not replay input blindly. |
| OUTPUT_CONFIRMATION_REQUIRED | Confirm the desired output. Automatic single-output selection does not apply to multiple outputs. |
| UNKNOWN_OUTPUT / AMBIGUOUS_OUTPUT_NAME | Choose one existing unique output name. |
| AMBIGUOUS_OUTPUT_GEOMETRY / OUTPUT_BINDING_UNAVAILABLE | Capture identity or native output binding cannot be verified; stop rather than guessing coordinates. |
| UNSUPPORTED_OUTPUT_TRANSFORM_OR_SCALE | Initial input support requires normal orientation and scale 1. Other geometry tests do not prove click mapping. |
| PORTAL_CREATE_TIMEOUT / PORTAL_SOURCE_SELECTION_TIMEOUT / PORTAL_START_TIMEOUT | The named phase failed. Stop and inspect Portal state before a deliberate retry; do not automatically repeat clicks. |
| PORTAL_SELECTOR_DISAPPEARED | The detected selector exited before the single bootstrap click completed. Do not repeat the click automatically. Inspect the selector journal/core; a reproduced slurp missing-keymap crash is described below. |
| PIPEWIRE_STREAM_ERROR | Inspect the bounded error detail. Diagnose format/policy/buffer negotiation in the private test environment before affecting the real desktop. |
| FRAME_TIMESTAMP_UNAVAILABLE / CAPTURE_TIMEOUT | No acceptable fresh timestamped frame was obtained. Do not substitute a cached screenshot or assume the input failed. Static headless tests may need controlled repainting. |
| STALE_OBSERVATION / LAYOUT_CHANGED | Do not reuse coordinates. Stop and create a fresh session/mapping. |
| ACTION_CANCELLED / ACTION_TIMEOUT | Partial input may have occurred. Inspect action_executed and cleanup errors. |
| REQUEST_ID_CONFLICT | An ID was reused with different content. Do not assume the new action ran. |
| SESSION_BUSY / SESSION_UNAVAILABLE | Inspect the existing owner or use stop; never alter the lock permissions. |
| INPUT_FORCE_TERMINATED | The owner had to kill its worker. Report cleanup uncertainty and verify desktop state. |
| NOTIFICATION_TIMEOUT / notification D-Bus error | Do not begin ordinary control if the start notice failed. End-notification failure must still be reported after cleanup. |

Always inspect stop's errors list. Losing a whole process group or the bus can prevent an end notification. A submitted notification is not user acknowledgment.

Current Rust validation and historical Python/C results are distinguished in IMPLEMENTATION.md and simulation-tests.md. archive/legacy is not a fallback runtime. Do not restart the user's services as an unrequested repair.


## Selector keyboard handoff

A current-desktop failure with slurp 1.5.0-2 was traced to xkb_state_update_mask receiving a null state. A private Wayfire regression reproduces the state by keeping one keyboard present, creating and stopping another virtual keyboard, then starting slurp: the compositor sends enter/modifiers without a preceding keymap. The selector crashes before the bootstrap click completes. This is independent of output count. A local slurp 1.5.0-3 patch ignores key/modifier events until an XKB state exists; it preserves pointer source selection and does not inject a keyboard event to restore the compositor's current keyboard. It does not repair the compositor's keyboard handoff or guarantee Escape works before a keymap arrives.

Use the opt-in private regression from the repository root (after building the release executable):

```bash
./.venv/bin/python3 skills/wayfire-computer-use/tests/probe_selector_keyboard.py
```

`--selector PATH` checks a specific executable; `--expect-crash` deliberately verifies the original SIGSEGV in the private desktop. Each invocation creates a fresh compositor and retains its Wayland trace. Run probes serially. A selector disappearance alone does not establish this diagnosis; inspect evidence before applying an external package patch.

## Lock-screen feedback

The runtime currently exposes no dedicated locked status/error and does not subscribe to logind's LockedHint. A session may remain active while a screenshot shows the lock screen. If capture is invalidated, the ordinary session/stream-loss handling stops control and attempts an end notification, without identifying a lock as the cause. Do not interpret active as unlocked or an end notification as a lock-specific notice. Stop input when the observed screen is locked; any test-driver LockedHint guard is separate from runtime behavior. The completed-lock screenshot test in simulation-tests.md verified lock-screen content in the tested configuration, not automatic lock detection.
