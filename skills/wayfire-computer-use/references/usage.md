# Rust runtime usage

From the skill directory, build once:

```bash
cargo build --locked --release
./target/release/wayfire-computer-use doctor
./target/release/wayfire-computer-use start
```

For one authorized Portal selection click (with explicit selection when several outputs exist):

```bash
./target/release/wayfire-computer-use start --output HEADLESS-8 --auto-select-output
```

This uses a pointer-only Wayland device, not wlrctl. It requires an explicit output name when multiple outputs exist, checks for a new same-user slurp monitor-selector process, allows setup time, moves within the selected output using output binding, then sends one click. The old --auto-select-single-output spelling remains an alias. The start notification precedes the click. Selector process discovery is not input-grab acknowledgment; concurrent selectors or disappearance prevent a reliable association. Never silently repeat a click. selector_click_may_have_executed conservatively records an uncertain startup side effect.

The runtime controls one selected normal-orientation output at scale 1. A sole output is automatic; with several outputs, --output NAME is mandatory. Duplicate output names, overlapping identical output geometry, missing virtual-pointer v2 output binding, and unsupported selected-output transform/scale fail before ordinary input. The full layout is still tracked to reject stale observations after changes. Rust explicit secondary-output selection has passed private dual-output integration and current-desktop GTK tests on HEADLESS-8 alongside eDP-1. This validates the tested scale-1, normal-orientation configuration, not arbitrary layouts or toolkits.

Start returns session_id, observation_id, screenshot_path, dimensions, output and layout_version. View the screenshot, then pass one envelope on stdin to `act`:

```json
{"request_id":"r-1","session_id":"COPY_FROM_START","observation_id":"COPY_FROM_START","action":{"type":"click","x":300,"y":213,"button":"left"}}
```

Read the result and actually view its new screenshot before deciding the next action. `validate` accepts an action object alone on stdin and sends no input. `status` and `capabilities` report the current session. `release_all` (also accepted as release-all) is a management recovery command. `stop` waits for cleanup and notification submission attempts, including when it arrives after cleanup has already started. The control socket continues accepting stop/status until the final result is published; check it even when status is stopped.

Identical request IDs return the cached response without replaying input. IDs with different content fail. Non-BMP text is rejected as a whole before input with UNSUPPORTED_NON_BMP_TEXT; clipboard fallback is disabled. A failed action can be partially executed: action_executed is conservative, not a guarantee that every event completed. Observe before deciding further work; the skill workflow stops/restarts on mapping or capture failure. A successful screenshot is never fabricated for an executed action whose capture failed.

The same binary starts an owner and input-worker process. The owner runs in an independent session, surviving launcher process-group cleanup after readiness; until readiness it retains a parent-death guard. The input worker retains its parent-death guard for the owner lifetime. The owner holds an exclusive per-display lock in a mode-0700 XDG_RUNTIME_DIR subdirectory shared with the legacy lock convention, plus a compositor-level lock shared with capture probes and standalone focus. The latter is keyed by the actual Wayland server PID and canonical socket directory, so alternate display spellings or client runtime directories cannot bypass it. Control requires an identifiable, named filesystem Wayland server socket; unnamed socket-pair transports fail explicitly. Its socket and metadata/images are private. Screenshots are removed at stop; orphan images from a forcibly killed owner are removed at the next locked start. Request bodies/text are not written to runtime logs. Sessions stop after five idle minutes, worker death, Portal frontend/wlr backend owner release or replacement, loss of the service monitor/session bus, a confirmed Portal Session Closed signal, or a permanent capture error. Capture health is checked every 100 ms independently of the action lock; a frame timeout alone is not a permanent stream error. There is no automatic session recreation or input replay after recovery. Confirmed session closure skips the already-removed remote object during cleanup. Service monitoring is installed before CreateSession and can cancel input while the PipeWire stream is still alive. After service identity loss, cleanup does not call the missing/replacement service; PORTAL_SERVICE_LOST records that remote session closure could not be confirmed. Wayland roundtrips have a three-second deadline; input actions have a 30-second limit. Text delivery uses experimental 50 ms settling waits before and after ASCII key events and around Unicode keymap changes, including restoration. Large text may time out after partial execution; the 10,000-code-point validation ceiling does not imply it fits in 30 seconds. Emergency stop permanently revokes its input worker: queued Execute requests cannot clear an already-delivered cancellation signal. Cleanup/release requests remain available. Stop terminates an unresponsive worker after a bounded wait and reports cleanup uncertainty. Completed connection tasks are reaped during normal operation and shutdown, rather than being retained for the session lifetime.

There is no dedicated lock-screen status or automatic lock-specific notification. An active session may capture the lock screen; stop input when it is observed. See [lock-screen feedback](troubleshooting.md#lock-screen-feedback).

Normal stop, cancellation and idle/worker failure attempt one end notification after device cleanup and lock release. Start notification failure prevents ordinary input. SIGKILL of the owner or entire process group, compositor failure, bus loss and system shutdown cannot guarantee notification delivery. Notification submission is not proof of user acknowledgment.

## Window management

The Rust executable directly implements Wayfire IPC window discovery and focus requests; no Python or wlrctl is used:

```bash
./target/release/wayfire-computer-use toplevel list
./target/release/wayfire-computer-use toplevel focus --id 123 --pid 456
```

These optional commands require Wayfire's ipc and ipc-rules plugins and an absolute WAYFIRE_SOCKET inherited from the intended desktop. The socket and server peer must belong to the current user. Before focus, the CLI additionally requires the IPC server PID to match the server actually reached through the current Wayland connection; owner-managed focus remains pinned to the owner's original compositor PID. Read-only list does not perform this additional Wayland check. Missing/unavailable IPC fails explicitly; the CLI does not discover other sessions, alter compositor configuration or fall back to another tool. Existing capture/input commands do not require these plugins.

`list` is read-only and returns status=ok and a toplevels array sorted by ID. Each item includes id, title, app_id, pid (null when unknown), output_name/output_id, logical geometry when available, activated, minimized, fullscreen and focusable. Only mapped application toplevels are included; shell/layer surfaces and unmapped windows are excluded. Empty lists are valid. Same-title windows remain separate IDs. IDs refer to the current compositor lifetime; list again after compositor restart or window closure. `--pid` optionally pins process identity and rejects a mismatch before requesting focus.

`focus` requests one exact ID, then checks both its activated state and Wayfire's get-focused-view result. A successful result has status=focused, focus_confirmed=true and the current toplevel metadata. This confirms compositor active-view state at observation time, not future key delivery or the absence of a popup, input-method grab or lock screen. The window manager may switch workspaces or restore a minimized window as part of its focus policy. These commands create no Portal session or virtual input device and submit no control notification on their own. Each IPC phase has a three-second deadline and a four-MiB response limit.

Without a control owner, focus acquires both the per-display and compositor-level control locks. If another display spelling reaches an already-controlled compositor, the standalone request returns SESSION_BUSY rather than bypassing that owner. With an owner, it goes through the same action queue as native input, so it cannot redirect an in-progress text action. Owner-managed focus only accepts a window on the selected output. Every owner-managed focus attempt reaching IPC invalidates the previous observation, including rejection or uncertain completion, and returns session_id with observation_id=null. Request and view a new screenshot before ordinary input:

```json
{"request_id":"after-focus-1","session_id":"COPY_FROM_FOCUS","observation_id":null,"action":{"type":"screenshot"}}
```

Focus is a management command, not an additional standard action type. It does not use act's request-ID deduplication. On error, inspect focus_request_may_have_executed; true means the request may have affected the desktop despite missing confirmation. Never retry automatically. Preparing/stopping/busy owners fail explicitly, with no standalone fallback after an owner has been contacted. Window metadata and successful focus do not replace the required PNG observation for mouse/keyboard work.

## Dependencies

Runtime: the compiled Rust executable, libpipewire-0.3 and its SPA support, libxkbcommon/keymap data, the Linux C/system libraries linked by the build, a Wayfire session exposing the virtual-pointer/keyboard protocols, D-Bus, a notification service, PipeWire and a Screenshot/ScreenCast-capable desktop portal. Window-management commands additionally use Wayfire IPC as described above. The session's PipeWire policy manager must connect capture streams. Python, pip, GStreamer, notify-send, wayland-info, wlrctl, a compiler and a separate C helper are not runtime requirements.

Build: a compatible Rust/Cargo toolchain, a C compiler for native binding build steps, pkg-config, PipeWire/SPA and xkbcommon development files, and libclang for generated PipeWire bindings. Cargo.lock pins the dependency resolution. Binaries target the build machine's Linux ABI; this is not a promise of a universally static executable. Check `ldd target/release/wayfire-computer-use` when packaging.

Development tests only: requirements-dev.txt installs Python fixture/validation packages. The isolated integration harness additionally needs the distribution Wayfire and Portal executables, dbus-run-session, PipeWire and WirePlumber. Its paths currently match the tested Arch Linux installation.

## Validation commands

```bash
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
cargo build --locked
```

From the repository root, optional isolated integration tests use the repository interpreter:

```bash
.venv/bin/python3 skills/wayfire-computer-use/tests/probe_rust_isolated.py --input-test --session-test
.venv/bin/python3 skills/wayfire-computer-use/tests/probe_rust_isolated.py --multi-output --session-test --launcher-boundary-test
.venv/bin/python3 skills/wayfire-computer-use/tests/probe_rust_isolated.py --multi-output --session-test --toplevel-test --launcher-boundary-test
.venv/bin/python3 skills/wayfire-computer-use/tests/probe_control_regressions.py
.venv/bin/python3 skills/wayfire-computer-use/tests/probe_headless.py
```

The private integration test starts its own D-Bus, headless Wayfire, PipeWire, policy-only WirePlumber, notification sink, permission store and wlr Portal. It does not restart or connect to the current desktop's Portal services. Logs/screenshots remain in its reported /tmp/wf-rust-isolated-* directory for inspection; remove that directory after review.

`probe-capture --output NAME --path FILE [--auto-select]` is a diagnostic capture-only command. Its explicit selector automation can target a confirmed named output, including a headless test output; ordinary sessions use the same explicit-selection and geometry checks, with the selected transform/scale limits above. It acquires the per-display lock and closes its Portal session on exit.
