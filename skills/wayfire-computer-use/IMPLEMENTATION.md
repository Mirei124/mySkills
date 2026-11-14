> Current runtime: Rust (`cargo build --locked --release`). Python/C runtime code and its regression suite are archived under archive/legacy and are not dependencies of the active executable. Historical milestones below retain their original status; see the latest Rust completion entry and references/usage.md.

> Current initial-release status: the skill now lives directly at `skills/wayfire-computer-use`. Historical milestones below retain their original status at the time. See `references/usage.md` and `references/simulation-tests.md` for current commands and supported validation scope.

# Implementation status

This is a partial P0 milestone, not completion of archive/PLAN.md.

Implemented: read-only diagnostic CLI, strict draft action shape validation, skill instructions and metadata, and offline contract tests.

Validation: two unittest cases passed. skill-creator quick_validate could not run because the repository virtual environment lacks PyYAML. Doctor ran; see a fresh doctor invocation for current environment evidence. No real desktop input was attempted.

Pending: official schema revision lock, native persistent input helper, portal/PipeWire capture, reliable output mapping, session supervisor and private socket, notification lifecycle, request deduplication, cleanup and all P1/P2 integration tests. The execution commands fail explicitly rather than simulating success. The optional MCP adapter is not implemented.

## Follow-up diagnostics

Using `.venv/bin/python3`, installed PyYAML for validation and dbus-next for portal work. Skill quick_validate and both contract tests now pass. With desktop access enabled, Wayland socket, wayland-info, portal introspection, notification introspection, and PipeWire core probes succeed. This supersedes the earlier sandbox denial; it does not verify input or frame capture.

Added an asynchronous portal Screenshot request client with signal subscription before requesting, unique request tokens, cancellation/timeout cleanup, and explicit portal errors. It is not yet wired to the execution CLI or tested against a real capture. ScreenCast and native input remain pending.

## ScreenCast probe

Verified gst-plugin-pipewire 1.6.11. Implemented portal CreateSession, SelectSources (one monitor), Start, OpenPipeWireRemote, and session/FD cleanup. A real portal stream returned position (0, 0) and size (1920, 1080). A GStreamer pipeline using the portal-provided FD captured one PNG successfully and exited zero; the portal session was then closed. The probe image is temporary at /tmp/wf-frame.png and is not committed.

Blocked on reliable stream-to-output identity: this portal response provides position and size but no output name. The plan prohibits guessing the identity. An explicit output selection and geometry validation path must be agreed before implementing input mapping. Persistent fresh-frame acquisition remains pending; the successful single-frame probe does not establish it.

## Native helper prototype

Retrieved both upstream protocol XML files through jsDelivr, retaining license notices. Generated bindings and compiled a C helper against wayland-client 1.26.0 and xkbcommon 1.13.2 without compiler warnings. Read-only protocol probe succeeds. A notified, no-input test created virtual devices, uploaded a US keymap, reported READY, processed stop, and exited zero. No clicks or text were sent. This proves device creation/destruction only; output binding, Unicode, supervision, lifecycle enforcement, and event behavior remain pending.

Output selection now follows the user's decision: automatically select the sole output, require an explicit choice among multiple outputs, and verify portal position/size. Six offline tests and a real single-output capture with geometry validation passed.

## GTK and persistent-capture preparation

Installed PyGObject 3.58.1 and pycairo 1.29.2 into the repository virtual environment. Verified Gtk 3 and GStreamer 1.28.9 imports with `.venv/bin/python3`. Added a dedicated GTK text-entry fixture and a prototype persistent appsink capture implementation. Six offline tests and skill validation still pass.

The persistent-capture probe stopped at Portal SelectSources: the backend launched a slurp display selector and did not receive a selection before its timeout. Cleanup ran; no input was sent. The capture implementation has not reached frame acquisition and remains unverified. Single-output automatic mapping does not bypass the portal backend's own source-selection UI.

## Fresh-frame and input probes

Retried persistent capture with source selection completed: two successive observations from one portal session returned 1920x1080 frames and the session closed normally. Launched the dedicated GTK fixture, inspected a screenshot, moved to its entry, clicked, and sent a single 'a'; fixture state and a subsequent screenshot confirmed success.

Added a prototype Python dispatcher over the persistent C helper. A follow-up click / CTRL+A / type 'Wayfire 123!' probe failed: the fixture state remained 'a'. Input cleanup and end notification ran. Stopped testing at this failure per user instruction. The cause (focus, event timing, keymap/modifier handling, or dispatch) has not yet been isolated. No claim of shortcut or text dispatcher correctness is made. CLI session integration remains pending.

## Input timing investigation

Reopened the dedicated fixture and inspected its screenshot. Adding a 300 ms startup/inter-action delay made sequential ASCII input, CTRL+A, and replacement text pass. Added conservative startup (150 ms) and post-action (50 ms) settling delays to the prototype dispatcher; a separate replacement-text probe passed with 'Verified 42!'. This is evidence of timing sensitivity, not proof of the precise root cause or toolkit-independent reliability.

Attempted controlled Unicode keymap switching in the native helper. The first Unicode action returned INPUT_FAILED during a real fixture probe. Cleanup ran, and testing stopped under the user's stop-on-problem instruction. The Unicode implementation is experimental and must not be advertised as supported until its failure is isolated. No clipboard fallback was used.

## Unicode investigation

Found and corrected a return-value bug: wl_display_roundtrip succeeds for any nonnegative value, while the Unicode command previously accepted only zero. A new dedicated-fixture probe no longer reported INPUT_FAILED, but actual text was 'aaaWayfire a' instead of the requested Chinese/symbol text. Thus successful protocol delivery does not establish Unicode keymap use. The cause of unchanged AC01 symbols is not yet isolated (keymap merge/override semantics, compositor behavior, or client update timing). Stopped at this new observed failure and cleaned up input. Unicode remains unverified and unsuitable for use.

## Unicode timing result and CLI integration

Offline libxkbcommon inspection confirmed AC01 maps to Unicode keysym 0x01004F60 for all tested merge forms; a new offline regression checks it. With experimental 50 ms waits before emission and before restoring the base keymap, the GTK fixture received exactly '你好，Wayfire ✓'. This supports a client keymap-update timing explanation but does not establish universal toolkit/IME/emoji compatibility.

Added a private per-display Unix-socket session owner with flock, portal lifetime, persistent capture and input, observation IDs, request deduplication/conflict checks, stale/layout checks, idle/helper-exit monitoring, lifecycle notifications, and screenshot cleanup. A real CLI start returned a screenshot; a click returned a fresh screenshot; replaying the identical request returned the identical saved result. Stop cleanup reported no errors. Remaining lifecycle/failure tests are not yet complete.

Added native output-name discovery and virtual-pointer v2 output binding. Native multi-output behavior remains unverified; the session currently rejects multiple outputs explicitly after confirmation rather than claiming it works. Public click button names wheel/back/forward are now recognized, with middle retained as a local alias. Seven offline tests pass.

## Test isolation failure (stopped)

During a later CLI probe the dedicated fixture process was no longer running. The start screenshot did not show the fixture, but the test orchestration still sent CTRL+A. No replacement text was sent. Stopped the session immediately on recognizing the missing fixture. This is an orchestration error: input tests must verify fixture liveness and visible focus immediately before dispatch, and stop when isolation is lost. The destination of that shortcut was not established. Do not count this probe as successful validation.

## Test-target guard

Added per-fixture random identity, PID and focus state with atomic state publication. The test-only guard checks process liveness, /proc command identity, unique window title, active toplevel through wlrctl, and focused entry before permitting a test action. Missing-state and exited-process regression tests pass. This reduces accidental-target risk; shared-desktop focus can still change after a check, so visual verification remains required.

Added offline session tests for deduplication without replay, execution reporting when post-action capture fails, stale/layout rejection before input, and single capture for screenshot actions. Fourteen offline tests pass. Skill instructions now describe the implemented development CLI and remaining limitations rather than diagnosis-only behavior.

The subsequent guarded desktop run did not reach input: Portal source selection timed out. Session cleanup ran and the fixture was closed. No guarded action was dispatched. Real guard integration remains pending interactive source selection; offline guard/session tests are not counted as desktop verification.

## Guarded desktop verification and stop responsiveness

A fresh fixture/portal run completed successfully under the test guard. Inspected the initial image, verified fixture identity/liveness/focus, dispatched Chinese/symbol text through the session CLI, inspected the resulting screenshot, then dispatched CTRL+A and ASCII replacement with guard checks and screenshot inspection between actions. Fixture state and images matched the requested contents. Stopped the session afterward.

An offline concurrency probe then found a stop responsiveness defect: the stop request waits behind the same serial lock held by a running action (STOP_BLOCKED_BY_ACTION_LOCK). No real desktop input was involved in that probe. Stop must bypass the action queue, cancel the in-flight dispatcher, release input in its finally path, and wait for cleanup completion. Paused at this confirmed failure per user instruction. Current CLI is not ready for deployment.

## Stop cancellation fix

Moved stop handling outside the serialized action queue. The first stop request marks the session stopping, cancels the tracked input task, and waits for final cleanup/notification results; later stop requests share that completion without cancelling release again. Signal and idle/helper-exit paths use the same cancellation entry point. Added regression tests for prompt action cancellation, acknowledgment only after cleanup completion, repeated stop during release, cancelled-drag release, failed-action release, preflight bounds, axis ordering, and key aliases.

Twenty-two offline tests pass. Also added stopped-result replay for repeated stop after socket removal, frame-dimension invalidation, and atomic ready publication. A real-desktop stop-during-action test remains pending. No actual desktop input was sent during these offline checks.

## Stop integration failure (paused)

Twenty-four offline tests passed, including notification-start failure preventing input and cleanup continuation after input cleanup failure. However, a real CLI stop-during-wait probe timed out. No clicks or text were issued. The helper and owner processes were explicitly terminated after identity checks and an interruption notification was sent.

Suspected shutdown ordering deadlock: serve closes the server and awaits wait_closed before setting session.finished, while the stop client awaits session.finished before closing its connection. Python 3.12 server shutdown can wait for live client transports, creating a cycle. This hypothesis still needs an actual Unix-socket regression test. Pause here under the stop-on-problem instruction. Reorder cleanup/completion signaling before waiting for client transport closure, with bounded transport shutdown. Also cover stop arriving during pre-dispatch discovery and capture, which the current input-only active-task tracking does not fully cover.

## Unix-socket shutdown ordering fix

Reordered shutdown to close the listener, clean resources, unlock control, attempt the end notification, publish stop completion, and then await client transport closure with a bound. A real Unix-socket regression now keeps the stop connection open until receiving the completion result, exercising the previous deadlock.

Expanded cancellation tracking to the entire request, including output discovery and post-action capture. Added regressions for stop before dispatch (no action executed) and stop during capture (prior execution preserved). Twenty-seven tests pass. Added stale runtime socket recovery, cleanup of orphaned screenshot artifacts at the next locked start, interrupted-task end-notification wording, and repeated stop result replay. Current real-desktop retry is awaiting portal source selection.

## Real stop verification and guarded pointer test

The desktop stop-during-wait retry passed: stop returned stopped with an empty errors list in approximately 0.067 seconds, and the in-flight request returned ACTION_CANCELLED. No clicks or text were sent during that probe.

Pinned the official action source as a vendored SHA-256-identified snapshot, added a local JSON schema and compatibility documentation, and expanded doctor output with protocol versions, parsed outputs, native read-only probe, PipeWire plugin and portal route information.

A subsequent pointer-action fixture run reached capture, but the fixture was no longer focused after portal selection. The guard rejected the move before dispatch (FIXTURE_NOT_FOCUSED). Stopped the session cleanly and closed the fixture. This is the intended fail-closed guard behavior, not a successful pointer-action test. Remaining mouse-action verification requires the user to focus the dedicated fixture after selecting the portal source.

## Portal startup wait (paused)

The next pointer-fixture run did not reach readiness: portal source selection remained pending and the CLI returned SESSION_START_TIMEOUT. No action was dispatched and no input helper had been created. The lingering owner was terminated after checking its command identity, and the fixture was closed.

This exposes a separate lifecycle gap: CLI startup timeout does not currently cancel its spawned preparing owner, and signal cancellation does not interrupt prepare immediately. Before retrying interactive verification, track the preparing task, cancel it on startup timeout/signals, and bound portal cleanup. Also allow a configurable longer source-selection timeout instead of requiring repeated short retries.

## Authorized Portal selector bootstrap and nine-action run

The user explicitly authorized one wlrctl click to choose the sole Portal display. Added the opt-in --auto-select-single-output bootstrap: single-output check, new same-user slurp monitor-selector detection, start notification before clicking, one left click, and no retry. Ordinary actions continue using the native helper. This is process-based detection, not an input-grab acknowledgment; its race/association limits are documented.

Added preparation cancellation on signals and CLI startup timeout termination of the spawned owner. Offline regressions cover preparation cancellation, one selector click after notification, ambiguous-selector rejection and notification failure preventing the click. Thirty-one tests pass.

Two real automatic-selector starts succeeded without manual selection. The second run focused the known unique fixture title using wlrctl toplevel focus, checked the fixture guard, and called all nine standard actions through the session dispatcher with screenshot inspection between actions. The GTK event log confirmed move, press/release, double click, drag motion with held button, and two scroll events. Unicode text and CTRL+A were visible in subsequent screenshots. Wait and screenshot also completed. This verifies basic dispatch and event delivery on the current single 1920x1080 output; it does not establish scroll-distance calibration, useful drag selection in an empty field, multi-output mapping, rotation/scaling, or cross-toolkit Unicode reliability. Stop returned stopped with no cleanup errors.

## Display simulation follow-up

Added 288 offline pointer-contract cases across three origins, four scale factors and eight rotations/reflections, with three image points per combination. These assume display-oriented frames and normalized output-bound mapping; they are explicitly not compositor acceptance tests.

Fixed an actual layout invalidation gap: parse_outputs now includes wl_output scale and transform metadata, so a 180-degree rotation or scale metadata change cannot leave an old observation valid solely because logical bounds stayed unchanged. Added targeted session regressions. Thirty-four tests pass.

Added and ran tests/probe_headless.py in a private runtime directory using /usr/bin/wayfire (bypassing the user's launcher wrapper), WLR_BACKENDS=headless, two outputs and pixman. The real isolated compositor exposed HEADLESS-1 at (-960,0), scale 2, rotation 180 degrees, logical 960x540; HEADLESS-2 at (0,0), configured scale 1.25, rotation 90 degrees, logical 864x1536. The current desktop configuration was untouched. The isolated process was terminated and runtime removed. This verifies compositor output geometry, not Portal capture or actual multi-output pointer hit targets. See references/simulation-tests.md for reproduction and limits.

## Current-session HEADLESS-8 integration

Confirmed eDP-1 at (0,0) and HEADLESS-8 at (1920,0), each 1920x1080 at scale 1 and normal orientation. Created a uniquely identified fixture and moved only that view to HEADLESS-8 with Wayfire IPC; no display configuration was changed.

Added a test-only Session subclass gate and tests/probe_current_multi.py to exercise the existing native output-bound helper and Portal stream verification on the explicitly authorized HEADLESS-8. The selector bootstrap moved the output-bound test pointer into HEADLESS-8 while a fresh slurp monitor selector was active, then sent one wlrctl click. The Portal returned frames whose metadata and visible fixture matched HEADLESS-8.

Inspected the initial image, focused the known fixture, and used the process/focus guard for each action. Click (300,213) produced fixture-local press/release (168,18). Unicode text matched exactly. Drag from (134,213) to (300,213) produced held-button events and a visible text selection. Fresh screenshots were inspected between actions. Stop returned stopped with no cleanup errors, and the fixture was closed. Thirty-four offline tests still pass.

Production multi-output input remains disabled by default: this result establishes the specific two-output, normal-orientation, scale-1 mapping, not every scaling/rotation configuration. Broader multi-output capability policy and remaining archive/PLAN.md acceptance work are still pending.

## Initial-release consolidation and review

Moved the skill to skills/wayfire-computer-use and merged archive/PLAN.md, this record and tests into the same directory. Updated test imports, reproduction commands and skill references for the consolidated layout. Refreshed stale diagnostic-only troubleshooting text and UI metadata.

Review fixes: Portal D-Bus calls now have deadlines; output-discovery subprocesses are reaped on cancellation; cancelled/failed CLI startup terminates and reaps its preparing owner while a successfully ready owner remains running. Added targeted regressions.

Final validation: 37 offline tests pass; native helper clean build passes without compiler warnings; the isolated two-output Wayfire geometry probe passes after migration; skill-creator quick_validate passes. No live desktop input was sent during this consolidation review. The user-approved initial scope retains the production multi-output gate, limited Unicode/toolkit coverage, and documented remaining reliability-matrix work.

## Rust rewrite in progress (paused at PipeWire stream failure)

The user requested a Rust runtime rewrite to remove Python and the separate C helper runtime. Added a root Cargo project with a lockfile, strict action types/validation, native Rust Wayland discovery and output-bound pointer/keyboard devices, xkbcommon keymaps, ashpd Portal sessions, zbus notifications, PNG encoding, and an experimental direct PipeWire capture thread. Existing Python/C entrypoints remain the documented working implementation until parity and desktop acceptance pass; this is not a completed migration.

The Rust project builds offline with the available toolchain. Three Rust action-validation tests pass. Native Rust doctor correctly reported current eDP-1 and HEADLESS-8 geometry and protocol versions without external discovery commands. A capture-only probe selected the explicitly authorized HEADLESS-8 Portal source using the Rust virtual pointer, but direct PipeWire capture returned PIPEWIRE_STREAM_ERROR before producing a frame. The probe closed its portal session and exited. It did not click ordinary applications or type text. Startup errors conservatively report selector_click_may_have_executed when automatic selection was requested.

Stopped under the user's earlier stop-on-problem instruction. Next work: retain bounded/sanitized PipeWire error details and diagnose format/buffer negotiation; then verify frame timestamp semantics and screenshot bytes before migrating session/action dispatch. The current Rust capture negotiates BGRx only and requires a header timestamp; these restrictions have not passed real capture validation. Rust session CLI parity, lifecycle/cancellation tests and runtime documentation cutover remain pending.

## Rust PipeWire diagnosis follow-up

The user authorized diagnosis of the prior stream error. Retaining a bounded, control-character-filtered PipeWire error string identified 'no more input formats'. Expanded the requested format pod with BGRx/BGRA/RGBx/RGBA choices, image-size bounds and frame-rate bounds; added corresponding packed-pixel conversion paths. This change has not yet passed a real capture test.

The next real probe returned a generic deadline error instead of a frame. No ordinary application click or text was requested. The probe process exited. Added stage-specific Portal timeout contexts and changed cleanup reporting so Portal close or end-notification errors cannot replace the primary capture failure; end notification is attempted after Portal close failure. A manual probe-end notification was submitted after the failed run.

Paused at this new timeout under the user's stop-on-problem instruction, without issuing another source-selection click. Next probe should distinguish source-selection/start/remote-open/close timeout from capture negotiation, then confirm actual frame format, buffer layout and monotonic header timestamps. Three Rust validation tests continue to pass. Existing Python/C runtime remains unchanged and is still the documented implementation.

## Rust stage-specific timeout and service-state diagnosis

A new authorized screenshot probe returned PORTAL_CREATE_TIMEOUT, before selector discovery or the PipeWire capture thread. No source-selection click was sent by this attempt. Read-only systemd checks show both portal services active, but recent journal entries include portal-wlr reporting a fatal PipeWire core error and systemd restarting that backend, failure to close ashpd session objects, and a slurp coredump in xkb_state_update_mask. These observations do not establish a single root cause or prove the Rust client caused each failure. No desktop service was manually restarted.

Added the Rust action dispatcher implementation (not yet wired into the CLI/session owner), preserving key aliases, text/chord distinction, bounds checking, cancellation checks and release attempts. Five Rust offline tests pass. The new code is not runtime-parity acceptance.

Paused further current-desktop probing because service/selector failures make that environment unsuitable for repeated tests. Recommended next step: reproduce in an isolated Wayfire/session-bus/portal environment, verify pointer-only selector bootstrap without creating or releasing a keyboard device, and diagnose PipeWire negotiation there. The current Rust bootstrap uses a combined Input device and therefore uploads/releases a keyboard keymap even though it only needs a pointer; whether this contributed to the observed slurp crash is unverified. Capture negotiation, actual screenshot validation and session CLI migration remain incomplete; existing Python/C runtime remains available.

## Rust initial runtime migration complete

Replaced the active Python/C runtime with the root Rust Cargo project. The supported initial CLI now provides doctor, validate, start, act, status, capabilities, release_all and stop with the existing JSON action/envelope contract. One executable runs both the owner and its supervised input worker; no independent C helper artifact is launched. Default instructions now target target/release/wayfire-computer-use. Archived Python/C code and its regression suite live under archive/legacy; optional Python GUI/Portal test dependencies are separated into requirements-dev.txt.

The direct PipeWire path now negotiates packed pixel format, size, frame rate and header metadata, checks mapped buffer bounds/stride/offset, converts RGB/BGR safely, requires fresh monotonic timestamps and writes private PNGs. Pointer-only selector bootstrap never creates a keyboard or uploads a keymap. Private integration uses an activation-disabled bus, only the wlr Portal backend, a private PipeWire server, policy-only WirePlumber and a notification sink. Controlled GTK repainting makes fresh capture testable without weakening freshness requirements. No current desktop services were restarted or used during these tests.

The session owner preserves per-display exclusive locking, serialized actions, strict envelopes, cached request deduplication/conflict rejection, observation/layout checks, private runtime files, idle/worker monitoring, cooperative cancellation, bounded worker termination, and notification/cleanup results. Emergency stop bypasses the action lock. Cleanup completion is signaled before waiting for client closure, avoiding the historical stop deadlock. Pending screenshot paths are registered before asynchronous capture; cancellation synchronizes output writing before deleting files. Wayland registry discovery and roundtrips have deadlines, including a silent-compositor regression. Known capture failure is checked before input and ends an idle owner. Management requests reject extra fields.

Verification: 13 Rust unit tests pass, cargo clippy --all-targets -- -D warnings passes, skill quick_validate passes, and a stripped release build succeeds (approximately 5.9 MiB on the tested machine). ldd shows libpipewire-0.3, libxkbcommon and standard Linux libraries, with no Python/GStreamer/libwayland-client runtime dependency. A C toolchain/libclang is still needed to build native bindings, not to run the resulting executable.

Private real integration passed direct capture, input-worker ASCII/chord/Chinese text, all nine session actions with GTK double-click/scroll reception, exact text assertions and screenshot inspection. It also passed duplicate-request non-replay, stale-observation rejection, cancellation during wait, repeated stop, image cleanup, start-notification failure preventing control, end-notification failure reporting without blocking cleanup, and killed-worker cleanup with an interruption notice. The geometry-only two-output probe was updated to query the Rust doctor and passed negative origin, integer/fractional scale and rotation metadata checks. Notification submission in isolation uses a stub; it does not prove delivery on a user's display.

Initial production input remains gated to a single normal-orientation output at scale 1. Rust screenshot/input integration for transformed or multiple outputs, broad toolkit/IME/emoji compatibility and the full archived plan reliability matrix are not claimed as complete. Historical physical-plus-headless testing belongs to the archived implementation. The Rust rewrite is complete for the user-approved initial scope; further capabilities require separate validation.

## Explicit output selection with multiple outputs

Removed the blanket multi-output input gate in favor of explicit selection. A sole output remains automatic; multiple outputs require --output NAME. Duplicate names/identical logical geometry are rejected, and virtual-pointer v2 is required when multiple outputs exist. The selected output still must be normal orientation at scale 1. Capture stream position/size, input worker layout and every subsequent request's layout remain verified. --auto-select-output names the optional one-click selector bootstrap; --auto-select-single-output is retained as a compatibility alias.

Added unit regressions for mandatory names, missing/duplicate names, ambiguous geometry, missing output binding and unsupported transform. The private integration harness now supports two headless outputs and moves only its private fixture through Wayfire IPC to the second output. A complete session run against HEADLESS-2 at nonzero origin (1920,0) passed.

Current-desktop verification found eDP-1 and HEADLESS-8, moved a new unique fixture to HEADLESS-8 and attempted the release CLI with explicit selection. It returned PORTAL_CREATE_TIMEOUT before the bootstrap callback, with selector_click_may_have_executed=false. No ordinary input was sent, the preparing owner exited and the fixture was closed. No services or display configurations were changed. Paused current-desktop testing pending resolution/authorization for Portal service recovery; do not count this as shared-desktop validation.

Final checks for this selection change: 15 Rust unit tests, strict Clippy and skill validation pass. The rebuilt isolated dual-output session suite also verifies that omitting --output fails with OUTPUT_CONFIRMATION_REQUIRED without sending a start notice, before the successful explicit HEADLESS-2 run. Release binary rebuilt successfully. Current-desktop acceptance remains blocked at Portal creation; no automatic retry or service restart was performed.

## Authorized live Portal restart and standalone-owner failure

The user explicitly approved restarting xdg-desktop-portal-wlr.service and xdg-desktop-portal.service to recover the blocked live Portal. Both user services restarted and reported active. Created a new unique animated GTK fixture, moved only that view to HEADLESS-8, then started the release Rust CLI with --output HEADLESS-8 --auto-select-output. It returned ready and a 1920x1080 screenshot visibly matching the headless output and fixture. This establishes live Rust Portal/capture recovery after the restart.

Before sending the first ordinary test click, guarded_action queried status and received SESSION_UNAVAILABLE. Read-only process inspection found neither owner nor worker, and stopped.json had not been written. No ordinary click or text was dispatched. The cause is not proven; launcher process-group/session cleanup is a leading hypothesis because private integration kept the outer orchestration process alive and did not cover standalone tool-launch completion.

Stopped under the stop-on-problem instruction. Acquired the now-free control lock and removed only the matching failed session's stale ready/socket/screenshot artifacts, closed the known fixture, and submitted a conservative interruption notice rather than claiming normal cleanup had completed. No output configuration was changed. Next work: reproduce standalone owner survival after the launching command exits, then isolate/detach owner lifetime with explicit startup cancellation and cleanup guarantees before retrying live input.

## Owner lifetime regression and live mixed-case failure

Reproduced owner loss by destroying the launching command's process group after start returned. The owner now creates an independent session, retains a parent-death guard until readiness, and clears that guard before publishing ready metadata. The input worker retains its parent-death guard. Bootstrap selection observes cancellation before its click. Added a private integration launcher-boundary regression and private-runtime-only detached-process cleanup.

The isolated dual-output session suite passed with launcher-boundary destruction, all nine actions and existing failure/cleanup checks. Strict Clippy, 15 Rust unit tests and the release build passed. In the current desktop, the release owner remained active across separate tool launches; explicit HEADLESS-8 capture and a guarded click reached the dedicated GTK fixture.

Live text validation then failed: requested `Rust 多屏测试 123!`, while both the screenshot and fixture state showed `rust 多屏测试 123!`. This is a case-preservation failure, not a complete live input pass. Per the user's stop-on-problem instruction, no subsequent input tests or runtime fixes were attempted. Normal stop returned an empty errors array and the known fixture was closed. Investigate initial uppercase/modifier synchronization against the actual desktop before accepting text input or repeating broader live tests.

## Initial Shift fix and Unicode-transition regression

Typing shifted ASCII now sends the Shift key press before the modifier mask and releases it after the character. This addresses the observed first-key keyboard-activation ordering issue. Added an isolated first-keyboard-action mixed-case assertion, without the former Ctrl+A warm-up. Strict Clippy, 15 Rust unit tests, the isolated dual-output session/launcher-boundary suite and release build passed.

Live HEADLESS-8 testing preserved the initial `Rust FIRST AbZ !@_`, but the complete request `Rust FIRST AbZ !@_ 中文 aA` became `Rust FIRST AbZ !@_ 中文 AA`. Both the returned screenshot and fixture state confirm the lowercase-to-uppercase error after Unicode. The input case-preservation issue remains unresolved; investigate temporary Unicode keymap restoration and modifier state. Testing paused under the stop-on-problem instruction. Stop reported no cleanup errors and the identified fixture was closed. No broader live acceptance or final commit is claimed.

## Text settling fix and completed live regression

Added cancellable 50 ms waits before and after ASCII key delivery so the next character cannot immediately change its modifier state while input-method/client delivery is pending. Unicode restoration now explicitly clears modifiers and waits 50 ms after uploading the base map. This addresses the observed live mixed-case failures; it is a timing-based compatibility measure, not an acknowledgment from the focused client or a universal input-method guarantee. Long text can exceed the existing 30-second action deadline after partial execution.

Strict Clippy, all 15 Rust unit tests, release build and the isolated dual-output session suite with launcher-boundary destruction passed. Current-desktop release testing on HEADLESS-8 alongside eDP-1 passed all nine actions. First keyboard input exactly matched `Rust FIRST AbZ !@_ 中文 aA`; Ctrl+A followed by replacement exactly matched `aA zZ 1! 中文 bB Rust`. Screenshots were visually inspected after each action. The fixture confirmed motion, double-click and scroll reception, and drag visibly selected text. Normal/repeated stop reported no errors, socket/screenshots were removed and the identified fixture was closed. The former lifetime and mixed-case blockers are resolved for this tested configuration. Broader toolkit/IME and transform coverage remain outside acceptance.

## Additional primary-output and cancellation verification

With the user explicitly selecting eDP-1, the release runtime captured that primary output while HEADLESS-8 remained present. The dedicated GTK fixture received an image-space click at (300,213) as local (168,18). In the existing fcitx5-running desktop environment, exact fixture-state checks and screenshots verified `aA中bB文zZ 1!_+ {}[] éÉ Ωω ✓ 😀`, followed by Ctrl+A replacement with `lower UPPER lower 中文 aA zZ 0123456789 !@#$%^&*()`. This covers these particular code points and transitions, not emoji sequences or composition-mode acceptance. No input-method settings or output configuration were changed. Stop returned no errors, screenshots/socket were removed and the identified fixture was closed.

Extended the private dual-output session regression to start a 400-character text action, wait for real partial delivery, then stop during cancellable settling. Stop completed within two seconds, the action returned ACTION_CANCELLED with action_executed=true, text remained unchanged for 300 ms after stop and no screenshots leaked. The full isolated suite with launcher-boundary testing passed again. Runtime code was unchanged during this validation round.
