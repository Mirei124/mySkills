> Historical Python/C simulation and current-output results below are retained as evidence for that implementation. The Rust runtime has separate isolated capture/input/session tests, documented at the end. Historical tests do not automatically validate the rewrite.

# Simulated display validation

Run the offline suite from the repository root:

```bash
.venv/bin/python3 -m unittest discover -s skills/wayfire-computer-use/archive/legacy/tests
```

The suite includes 288 pointer-contract cases spanning three output origins, four scale factors (1, 1.25, 1.5, 2), eight rotations/reflections, and three image positions. The fake compositor assumes display-oriented frames and output-bound normalized pointer semantics. These cases test the dispatcher contract, not whether a real compositor honors that binding or a portal supplies correctly oriented frames.

Output parsing now preserves wl_output integer scale and transform, so layout invalidation also detects rotation/scale metadata changes with unchanged logical bounds. wl_output.scale is rounded up for fractional scaling: a configured scale of 1.25 can advertise integer scale 2; logical geometry remains the relevant positioning information. Fractional scale changes that preserve all parsed metadata are not separately detected by the parser.

An opt-in integration probe starts the distribution Wayfire binary with two headless outputs, pixman rendering, a private runtime directory, an explicit minimal configuration, no plugins, and no connection to the live desktop/session bus:

```bash
.venv/bin/python3 skills/wayfire-computer-use/tests/probe_headless.py --result /tmp/wf-headless-result.json
```

It bypasses user session-launch wrappers, verifies output geometry and rotation, then terminates the isolated process and removes its runtime directory. It does not change the current desktop configuration. Verified on Wayfire 0.12.0 / wlroots 0.20.2:

| Output | Mode | Position | Configured scale | Rotation | Observed logical size |
|---|---|---|---|---|---|
| HEADLESS-1 | 1920x1080 | -960,0 | 2 | 180 degrees | 960x540 |
| HEADLESS-2 | 1920x1080 | 0,0 | 1.25 | 90 degrees | 864x1536 |

The probe does not run Portal or validate actual pointer hit targets. Portal stream orientation, output binding, multi-output click mapping and changed-layout recovery still require further isolated integration work before multi-output input is enabled. No simulated test result is treated as physical-display acceptance.

## Current-session two-output integration (2026-11-14)

With explicit user authorization, the existing Wayfire session was tested with eDP-1 at (0,0) and HEADLESS-8 at (1920,0), both 1920x1080 at scale 1 with normal orientation. Only a newly created, uniquely identified GTK fixture was moved to HEADLESS-8 using Wayfire IPC.

The archived test-only archive/legacy/tests/probe_current_multi.py subclass bypasses the production multi-output gate solely for HEADLESS-8. A newly detected Portal selector receives an output-bound virtual pointer move to the headless display center and one authorized wlrctl click. The production single-output auto-selector option remains restricted to one output. The Portal stream must still match the explicitly selected output's position and logical size.

Observed results:

- Portal returned HEADLESS-8 frames at 1920x1080, visually containing the fixture and a different desktop background from eDP-1.
- A click at image (300,213) generated fixture-local press/release at (168,18), consistent with its client origin (132,195).
- The fixture received `HEADLESS-8 点击映射测试` exactly; the screenshot showed the same text.
- A drag from image x=134 through x=300 at y=213 produced held-button motion and a visible text selection. The event log included local x=2 and x=168.
- Stop returned an empty cleanup-errors list and the fixture was closed. Output configuration was unchanged.

This verifies a real Portal/input loop on the current physical-plus-headless, normal-orientation, scale-1 configuration with a nonzero selected-output origin. It does not validate scale/rotation capture orientation or every multi-output layout. Production multi-output input remains gated pending broader acceptance and an explicit supported-capability policy.

## Rust isolated integration

Build the debug binary with `cargo build --locked` in the skill directory, then from the repository root run:

```bash
.venv/bin/python3 skills/wayfire-computer-use/tests/probe_rust_isolated.py --input-test --session-test
```

The harness owns a private runtime directory, D-Bus with activation disabled, headless Wayfire, PipeWire, policy-only WirePlumber, a notification sink and the wlr Portal. The selector uses a pointer-only Rust device. The animated GTK fixture generates controlled screen damage so fresh-frame requirements are testable. Notification submission is tested against a stub, not a real user display.

Verified: direct PipeWire packed-pixel capture with header timestamps and PNG inspection; Rust input-worker click, ASCII/chord/Chinese text; session CLI all nine actions, double-click/scroll event reception, deduplication, stale-observation rejection, wait cancellation, repeated stop and screenshot cleanup; start-notification denial, end-notification failure reporting, and input-worker crash cleanup/interruption notice. Scope is a single unrotated 1920x1080 headless output at scale 1. The two-output geometry-only probe now reads the Rust doctor's output; it still does not establish Portal/input mapping for those transforms.

No current desktop service is restarted or used by this test. The Rust selected-output scale/transform gates remain in place.

## Rust explicit secondary-output selection

The Rust runtime now accepts --output NAME when multiple outputs exist, while requiring normal orientation/scale 1 on the selected output, virtual-pointer v2 binding and unique geometry. Add --multi-output to the isolated session probe to create HEADLESS-1 at (0,0) and HEADLESS-2 at (1920,0), move only the private fixture to HEADLESS-2 and exercise explicit selection there. This integration passed capture, input and session lifecycle checks. An initial current-desktop attempt stopped at PORTAL_CREATE_TIMEOUT. After the authorized Portal restart and subsequent lifetime/text fixes, current-desktop acceptance for the tested configuration passed as described below.

## Rust launcher lifetime and current-desktop validation

Run the dual-output regression with:

```bash
.venv/bin/python3 skills/wayfire-computer-use/tests/probe_rust_isolated.py --multi-output --session-test --launcher-boundary-test
```

The launcher-boundary case destroys the launching command process group after readiness and verifies that the detached owner remains active. The session suite also types mixed-case ASCII, symbols and Chinese as its first keyboard action, without a Ctrl+A warm-up. All existing nine-action, deduplication, cancellation, notification-failure and worker-crash checks passed. Detached-process cleanup matches both the executable and the private runtime directory.

On the current eDP-1/HEADLESS-8 desktop (both 1920x1080, scale 1, normal orientation), the release runtime explicitly selected HEADLESS-8 at (1920,0) using one authorized Rust pointer-only selector click. The owner survived separate launching commands. Only the unique animated GTK fixture was targeted. Every returned screenshot was viewed before further input.

Verified all nine action types, exact first-input text `Rust FIRST AbZ !@_ 中文 aA`, Ctrl+A replacement with exact `aA zZ 1! 中文 bB Rust`, visible click/double-click/drag selection and fixture motion/double-click/scroll events. Normal and repeated stop returned empty error arrays, removed screenshots and the control socket, and the fixture was closed. Ready metadata is retained until the next start; it is not an active-session indicator. No output configuration was changed.

These results cover this GTK configuration and the private harness. Settling delays are experimental; arbitrary input methods, other toolkits, emoji and scaled/rotated input remain unverified.

## Additional eDP-1 and text-cancellation coverage

The same isolated command now also verifies cancellation after observing partial delivery of a 400-character text action. It requires stop within two seconds, conservative partial-execution reporting, unchanged fixture text for 300 ms after stop and no screenshot leaks.

The user subsequently selected eDP-1 for live release testing with both outputs still present. Capture, exact click mapping and Ctrl+A replacement passed in the dedicated GTK fixture. Exact text assertions covered `aA中bB文zZ 1!_+ {}[] éÉ Ωω ✓ 😀` and `lower UPPER lower 中文 aA zZ 0123456789 !@#$%^&*()`. fcitx5 was running; its mode/settings were not changed, so this does not establish composition-mode behavior. One standalone emoji is verified in this GTK environment; multi-code-point emoji sequences and other toolkits remain unverified. Normal stop removed socket/screenshots and returned no errors; the fixture was closed.

## Dolphin and Chromium application-control checks

Used only a newly launched Dolphin window and a Chromium instance with a unique temporary user-data directory, on the user-selected eDP-1 output. All input went through the release Rust CLI, with PID/view/focus checks and screenshot inspection between actions. No browser automation, clipboard insertion or existing browser session was used. Test data was confined to /tmp/wf-app-probe-d8i6sb3e.

Dolphin passed Ctrl+L location editing with `/tmp/wf-app-probe-d8i6sb3e/Input 中文 aA`, Enter navigation to the correct directory containing Marker.txt, Alt+Left back navigation and double-click re-entry. This establishes the tested Qt path-entry and navigation behavior, not all Qt widgets.

Chromium 156.0.8078.79 (Arch Linux), launched with an isolated profile and explicit Wayland backend, opened a generated local plain-text document. Ctrl+F opened its find field. Typing `Rust aA 中文 éÉ Ωω ✓ 😀` returned an action-success response, but the screenshot showed a replacement glyph at the end and find reported 0/0 despite the original line being present in the document. Exact browser Unicode delivery is therefore not accepted; the non-BMP character is the leading suspect, not a proven root cause. Chromium launch arguments also included distribution defaults --gtk-version=4 and --disable-gtk-ime. No input-method mode was changed.

Paused at this discrepancy under the user's stop-on-problem instruction. Browser scrolling, address-entry navigation and further abnormal-state tests were not attempted. Stop returned an empty errors array and removed control socket/screenshots. Closed only the dedicated application processes after verifying identity (Chromium executable and unique profile, Dolphin launch arguments). The temporary test data/logs remain for investigation. No runtime changes were made.

## Chromium BMP boundary and conservative non-BMP rejection

Reproduced the difference within Chromium's find field: `Rust aA 中文 éÉ Ωω ✓` matched 1/1; appending ` 😀` produced a replacement glyph and 0/0. The upstream Chromium [KeyEvent::GetCharacter implementation](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/ui/events/event.cc) explicitly retains a BMP-only character boundary and narrows the scalar to char16_t. This supports a keyboard-path limitation; the moving upstream source is corroboration, not a proof of the installed build's exact call stack.

Added whole-action validation rejecting every non-BMP code point with UNSUPPORTED_NON_BMP_TEXT before dispatch. This intentionally applies across applications: previously observed GTK emoji success is not a portable capability. Supplementary CJK, musical symbols and many emoji are also excluded. No clipboard, surrogate-key injection or application-specific bypass was added. Unit regression covers mixed text with a valid prefix, supplementary CJK and musical symbols; the isolated integration requires no prefix delivery and unchanged observation metadata after rejection. Capabilities and usage now state this boundary.

All 16 unit tests, strict Clippy, release build and the isolated dual-output session/launcher-boundary/text-cancellation suite passed. Live release testing in Chromium returned the expected rejection with action_executed=false and visually unchanged find contents. Subsequent BMP text again matched 1/1. Escape, pointer-targeted scrolling and Ctrl+L address entry with a mixed Chinese/ASCII/space file URL followed by Enter worked; the intended Marker.txt content appeared. Scroll validation establishes direction/movement, not exact pixel calibration. Stop returned no errors, screenshot/socket cleanup passed and only the dedicated Chromium instance was closed. Other outstanding reliability and input-method composition cases remain untested.

## Typora, composition, XWayland and additional reliability probes

Used separate temporary Typora profiles and only /tmp/wf-typora-test-5z75c1nk/Electron Probe.md, targeting the user-selected eDP-1 through the release native input CLI. Typora --version unexpectedly launched an application process; that exact process was closed before the isolated-profile tests. Native Wayland Typora passed click, Ctrl+A replacement and Ctrl+S. Saved UTF-8 text verified exact code points and paragraph order for `Rust aA 中文 éÉ Ωω ✓`, decomposed `Combining e\u0301 and a\u0308`, and `RTL שלום العربية end`. Typora's Markdown serialization separates paragraphs with blank lines; the check accounts for that formatting without normalizing Unicode code points.

With fcitx5's configured shuangpin method activated, typing `ni` displayed preedit and candidates, Space committed `你`, a second `ni` followed by Escape cancelled the preedit, and saved content contained exactly one committed `你`. Restored the original keyboard-us/inactive state (fcitx5-remote reports 1). This validates that composition interaction, not arbitrary literal text insertion while an IME is active. Reopened only the temporary document with --ozone-platform=x11 and a separate profile; xlsclients identified Typora. Click, multiline append `XWayland aA 中文 ✓` and saved-file verification passed. Both dedicated Typora instances were closed and their control sessions stopped without errors.

Added optional --reliability-case to the private harness (no current-desktop services or output settings are used). Ten start/capture/stop cycles passed with owner FD count 31 each time and RSS 45148–45564 KiB; this is short-cycle evidence, not a long-duration leak acceptance. Moving the selected private output from (1920,0) to (2200,0) caused the attempted old-coordinate click to return LAYOUT_CHANGED/action_executed=false; stop took approximately 0.09 seconds with no errors. Terminating private PipeWire caused CAPTURE_ENDED/action_executed=false; stop took approximately 0.06 seconds with no errors.

The private Portal-frontend termination case found a policy discrepancy: after xdg-desktop-portal exited, the already established PipeWire stream still returned a real screenshot successfully. The test expected automatic loss reporting and failed with RELIABILITY_LOSS_NOT_REPORTED. This does not prove unauthorized capture or fabricated output; the established stream may remain valid. Paused under the user's stop-on-problem instruction pending a decision whether frontend loss must revoke the control session. Runtime code was not modified. The failed test's forceful harness teardown reported input/Portal/notification cleanup errors as its private bus/services were being removed; no owner/worker remained and screenshot/socket artifacts were removed. Harness cleanup now requests orderly stop before tearing down services; this follow-up cleanup improvement is not yet rerun against that failure.

The first new layout run also exposed a test-only uninitialized cleanup variable; initialized it before all test branches, cleaned only its private runtime processes, and reran layout successfully. Remaining unrun cases include portal-wlr/compositor loss, resolution/disable/re-enable changes, long-duration single-session checks, timeout recovery, scroll calibration, and additional composition patterns. The user approved being present for real lock/suspend/unlock, but neither lock nor suspend was executed because testing stopped at the Portal policy question.

## Portal service-loss cancellation implemented

Per the user's confirmed policy, sessions now stop when org.freedesktop.portal.Desktop or org.freedesktop.impl.portal.desktop.wlr loses or changes its D-Bus owner, or the monitor/bus ends. A lifetime-bound task subscribes before CreateSession and notifies the owner independently of the action/engine lock. Loss takes priority in the owner loop, signals input cancellation, cancels capture/bootstrap and runs normal local cleanup. Actions also check the loss state before dispatch. Dropping the Portal aborts the monitor. Cleanup skips remote Close after identity loss, avoiding activation of or calls to a replacement service, and explicitly reports PORTAL_SERVICE_LOST: session close could not be confirmed. futures-util is now a direct dependency using the version already present in Cargo.lock.

Private regressions passed frontend loss while idle, frontend loss during a 400-character text action, and wlr-backend loss. Active text returned ACTION_CANCELLED/action_executed=true and did not continue after automatic stop. Each case verified stopped metadata, removed socket/screenshots and rejection of subsequent capture. The expected cleanup uncertainty remains reported after remote service loss. All 16 Rust unit tests, strict Clippy, release build and the complete private dual-output session/launcher-boundary/text-cancellation suite passed. The harness now requests orderly stop while private services remain alive before fallback process termination.

Continuing the private compositor-loss test found a new unresolved result-reporting issue: after private Wayfire terminated, screenshot failed and an immediate stop returned SESSION_UNAVAILABLE rather than a stopped cleanup result. Later inspection found stopped.json and no remaining owner/worker or socket/screenshots. Its errors included INPUT_EXIT_FAILED and notification/bus failure during the harness's subsequent teardown, so those observations do not establish verified compositor-loss cleanup. A gap between removing the control socket and publishing the final cleanup result is a leading hypothesis, not yet a proven diagnosis. Testing paused at this issue under the user's stop-on-problem instruction. No current-desktop Portal/compositor service was terminated. Real lock/suspend tests remain authorized with the user present, but have not been executed.

## Cleanup-result publication race fixed; initial lock sample inconclusive

Reproduced the stop-result gap without compositor failure by delaying the private end notification by 500 ms. The first stop was still waiting, but a second stop returned SESSION_UNAVAILABLE because the listener/socket had already closed and stopped.json was not yet published. Kept accepting clients while the cleanup future and final notification run; stop requests share the completion channel, status remains readable and ordinary actions remain blocked. Only after publishing the result is the listener/socket removed. The injected-delay regression now gets identical successful results for both stop requests.

The private compositor-loss case now returns stopped metadata reliably, with INPUT_EXIT_FAILED and PORTAL_SERVICE_LOST retained rather than hiding uncertainty caused by the absent compositor/remote service. All 16 Rust unit tests, strict Clippy, release build and the complete isolated dual-output session/launcher-boundary/cancellation suite passed after the change.

The user explicitly authorized current-desktop lock/suspend with manual unlocking. Created only a dedicated animated GTK fixture and a release capture session on eDP-1. Requested the configured Noctalia session lock; loginctl session 95 reported LockedHint=yes immediately before the screenshot request. The returned screenshot still showed desktop content. A later check after visually inspecting the frame reported LockedHint=no. The script did not record LockedHint immediately after capture, so this observation cannot distinguish a lock transition/early unlock from capture during a completed lock. Do not count it as a pass or a confirmed privacy failure. Paused for user clarification under the stop-on-problem instruction. Stop returned no errors; no owner, worker or fixture process remained. The fixture had already exited when explicit cleanup checked its PID; no unrelated process was targeted. No suspend was executed. A controlled follow-up, if authorized, must sample before/after lock state in the same script and allow lock completion before capture.

## Controlled lock validation and actual suspend/resume result

The user confirmed that the first lock test displayed the lock screen and they manually unlocked approximately 15 seconds later. Repeated once with a controlled script: requested Noctalia lock, waited three seconds, sampled loginctl session 95 LockedHint immediately before and immediately after the screenshot call, and stopped the control session within that script. Both samples were yes; the screenshot showed only the blurred lock-screen background and empty password UI, not the original desktop or fixture. Stop reported no errors. No pointer/key events were sent while locked. The reviewed lock image was removed. This validates capture content for the completed lock in this configuration; the earlier transition sample remains inconclusive and does not establish a privacy failure.

After manual unlock, created another dedicated animated GTK fixture and release capture session on eDP-1. The user had explicitly authorized actual suspend and manual wake/unlock. systemctl suspend returned success; CLOCK_BOOTTIME minus CLOCK_MONOTONIC deltas recorded approximately 9.375 seconds of actual suspend. The machine reported deep as the selected mem_sleep mode. After wake and manual unlock (LockedHint=no), the original owner still reported active, but a screenshot request failed with PIPEWIRE_STREAM_ERROR: no more input formats and action_executed=false. No stale screenshot or input event was returned.

Stopped at this unresolved resume behavior under the stop-on-problem instruction. Local screenshot/socket and input-process cleanup completed, but stop reported that the remote Portal session object no longer existed. Both observations are consistent with a session/stream invalidated across suspend; they do not prove its exact cause. No automatic retry or new capture session was started. The runtime currently monitors Portal service identity, not the individual Session Closed signal; ashpd exposes Session::receive_closed for possible follow-up. Decide whether session closure/terminal capture errors should automatically terminate control rather than leaving status active. Re-establishing a session after wake remains unverified in this run. The dedicated fixture was closed and no owner/worker/fixture processes remained.

## Session-closure and terminal-capture handling work in progress

Added a Portal Session Closed signal subscription before source selection/Start, independent of the action lock. A confirmed closure permits local cleanup without calling an already-removed remote object. Added a 100 ms capture-health check independent of the engine/action lock; a stored permanent stream error cancels control even when no screenshot action is requested. These changes compile in the debug binary; all 16 unit tests and strict Clippy passed. Release rebuild and full integration acceptance have not been completed for this patch.

Extended optional private reliability cases with session/session-active/pipewire-active and a replacement-session check. The session case enumerated the private wlr backend's single session object and invoked org.freedesktop.impl.portal.Session.Close directly. It reached automatic-stop verification and removal of the control socket, but replacement start failed with Portal request didn't succeed: Other. The private frontend log then reported that org.freedesktop.impl.portal.desktop.wlr was unavailable. This test does not isolate whether Closed notification or capture-health cancellation stopped the owner. Direct backend Close may also be an unsuitable external-closure injection or expose a backend defect; do not infer a confirmed runtime root cause.

Paused at this recovery failure under the user's stop-on-problem instruction. No current desktop service, suspend or lock operation was invoked during this patch attempt. Harness cleanup left no owner/worker; the failed replacement start's saved stopped result was empty, which must not be substituted for the original auto-stop cleanup result. Next investigation should preserve per-session cleanup evidence, inspect private backend process exit and distinguish a valid frontend session closure from direct backend manipulation before claiming successful recovery. Active-input loss cases, actual suspend/resume retest, and release acceptance remain pending.

## Recovery crash reproduced and external backend patch verified

Preserved per-session recovery-trace.jsonl checkpoints and pre-cleanup process exit status. With the distribution backend, three consecutive direct-backend-close recovery runs failed because portal-wlr exited with -11/SIGSEGV before replacement start. A normal ten-cycle start/capture/stop control run passed. After the user rebuilt and installed a matching debug package (Build ID 5eff3fb5a113b21a7013f80d3e58430153f95a76), the same recovery failed another three times with identical backend SIGSEGV. Debug symbols and source confirmed the stack: xdpw_screencast_instance_destroy -> xdpw_pwr_stream_destroy -> PipeWire state_changed -> pwr_disarm_process_retry -> xdpw_destroy_timer -> wl_list_remove. The retry timer was freed by the instance's timer loop while cast->process_retry retained its address; disconnect triggered another cleanup of that dangling pointer.

At the user's request, patched /home/k/test/xdg-desktop-portal-wlr with fix-process-retry-timer-use-after-free.patch, clearing cast->process_retry before destroying that timer. Added the patch/checksum to PKGBUILD prepare(), regenerated .SRCINFO, raised pkgrel to 2, preserved the user's debug configuration, and applied the patch to the existing extracted build tree. Clean-source dry-run, source checksums and local Ninja compilation passed. No system installation or shared service restart was performed by the agent.

Added --portal-wlr-binary to the private harness for controlled executable selection. This also exposed a test semantic error: the backend Session.Close method intentionally does not emit Closed, so this injection cannot by itself validate frontend Session Closed monitoring. Retained session/session-active as the pending auto-stop expectation and added a distinct backend-close diagnostic case: direct backend closure, failed fresh capture (CAPTURE_TIMEOUT), explicit stop, new session and successful fresh capture. Three consecutive runs using the patched local backend passed, the backend remained alive, and both stop results had empty errors arrays. Successful trace directories: /tmp/wf-rust-isolated-5__au4bt, /tmp/wf-rust-isolated-wdur171j, /tmp/wf-rust-isolated-y40yiq0y.

This A/B result validates the timer-lifetime fix for the reproduced backend crash and explicit recovery. It does not establish automatic handling of a genuine frontend Closed event, idle paused-stream loss, or actual suspend recovery with the pending Rust patch. System installation of the backend patch remains with the user.

## Installed backend and recovery acceptance

Installed xdg-desktop-portal-wlr 0.8.4-2 (Build ID d4fe73e60c8ca364c48d1b78c3f08612e1a7e50b), then restarted the current desktop Portal services under the user's existing authorization and verified the running backend matched the installed executable. Three consecutive backend-close diagnostic runs passed using the system binary: /tmp/wf-rust-isolated-y2tbufru, /tmp/wf-rust-isolated-fjy6w3ze and /tmp/wf-rust-isolated-4avxio4d. Each retained a live backend, reported CAPTURE_TIMEOUT for the closed stream, stopped without cleanup errors and successfully captured through a replacement session.

Corrected session/session-active to disable the selected private output, exercising compositor-driven session/stream invalidation rather than invoking the backend Close method. Idle and active cases passed in /tmp/wf-rust-isolated-jeckoc6u and /tmp/wf-rust-isolated-h1f56omm: automatic stop, removed socket/images, no continued input, output re-enable and replacement capture/cleanup. Active input returned ACTION_CANCELLED/action_executed=true. These combined tests establish automatic invalidation handling but do not independently isolate the Session Closed signal from the permanent-capture-error monitor. PipeWire loss during active input also cancelled delivery; cleanup retained PORTAL_SERVICE_LOST uncertainty when the backend exited with PipeWire (/tmp/wf-rust-isolated-gegblnd6).

Run private desktop probes serially: the selector detector searches same-UID processes, so overlapping private slurp instances interfere. One concurrent session-active attempt failed PORTAL_SELECTOR_DISAPPEARED; its serialized rerun passed. This is a harness orchestration limitation, not a passed concurrent-selector test.

Actual current-desktop suspend/resume on eDP-1 passed with the release binary and patched system backend. CLOCK_BOOTTIME minus CLOCK_MONOTONIC deltas measured approximately 5.828 seconds of suspend. After manual wake/unlock, the old session was automatically stopped with errors=[], no socket/images and no remaining owner/worker. A newly established session returned a fresh fixture screenshot; native input delivered exactly `Resume aA 中文 ✓`, verified against fixture state. Final stop returned errors=[] and the dedicated fixture was closed. Evidence: /tmp/wf-suspend-fixed-report.json and /tmp/wf-suspend-fixture.json. The first reporting script used check_output for a deliberately unavailable status and raised on its nonzero exit; the saved clock measurements and stopped state were recovered without repeating suspend.

All 16 Rust tests, strict Clippy, release compilation and the complete isolated dual-output session/launcher-boundary suite passed (/tmp/wf-rust-isolated-as9iktr0). These results supersede the pending acceptance statements above. Long-duration soak, physical cable hotplug/resolution changes, exact scroll calibration and additional IME configurations remain outside the completed coverage. Rotated/scaled selected outputs and non-BMP text remain explicitly unsupported.

## Current-desktop output add/remove attempt

Used the repository Python with /home/k/myWS/wfsock.py output add, creating only HEADLESS-10 alongside the original sole eDP-1. An existing eDP-1 session rejected a click based on its pre-add observation with LAYOUT_CHANGED/action_executed=false; stop had errors=[]. This validates stale-layout input rejection after adding an output.

Moved the dedicated animated GTK fixture to HEADLESS-10 and attempted one explicitly authorized Portal selector click. Start failed PORTAL_SELECTOR_DISAPPEARED with selector_click_may_have_executed=true. The current desktop journal recorded slurp PID 3736171 SIGSEGV at xkb_state_update_mask, via libffi/Wayland dispatch, at 22:00:45 local time. This establishes a selector crash, not its root cause. Stop reported PORTAL_CLOSE_TIMEOUT. Paused under the user's stop-on-problem instruction: no repeated selection, selected-output removal acceptance or Chromium soak run was attempted. Closed only the identified fixture and removed only the newly created HEADLESS-10 through output remove -n; verified the original sole eDP-1 remained and no runtime owner/worker was left. Evidence: /tmp/wf-hotplug-soak-1794664776/events.jsonl and the user service journal. The requested removal/reconnect and 30-minute Chromium validations remain pending.

## Selector fix and current-desktop output lifecycle acceptance

The saved slurp core confirmed a null xkb_state and xkb_keymap in the seat at xkb_state_update_mask. A fresh private Wayfire with a retained stand-in keyboard and a second control keyboard created/stopped reproduced enter/modifiers without a preceding keymap. Three fresh system-slurp runs crashed with SIGSEGV: /tmp/wf-slurp-isolated-wp2riuvb, /tmp/wf-slurp-isolated-yc1s50qk and /tmp/wf-slurp-isolated-yup4zttv. Consecutive injections within one compositor can restore a usable keymap, so the committed probe uses a fresh compositor per invocation and requires the missing-keymap trace as well as the expected exit.

Prepared /home/k/test/slurp/fix-null-keyboard-state.patch and an Arch slurp 1.5.0-3 package. The patch ignores key/modifier callbacks until an XKB state exists; it does not alter source selection, send restorative key events or repair the compositor's handoff. Three fresh patched runs survived the same no-keymap modifiers: /tmp/wf-slurp-isolated-qbdroxsm, /tmp/wf-slurp-isolated-h5jtmt5a and /tmp/wf-slurp-isolated-cdgh2w2q. Raw reports remain in those test roots. The private full dual-output session/launcher-boundary suite passed with the patched selector (/tmp/wf-rust-isolated-iqye4h53). After the user installed the package, pacman reported slurp 1.5.0-3 and the committed selector probe passed against /usr/bin/slurp (/tmp/wf-slurp-isolated-u06p4fkn). No Portal service restart was needed for replacing the short-lived selector.

Resumed current-desktop tests with the release runtime and only new virtual outputs, added/removed through the repository Python invoking /home/k/myWS/wfsock.py output add and output remove -n NAME. Selected HEADLESS-11 capture succeeded; removing it automatically stopped the session with errors=[]. A fresh eDP-1 session captured and delivered exactly `Hotplug aA 中文 ✓`. Added HEADLESS-12, established a fresh eDP-1 session, then removed the unselected HEADLESS-12: the old-observation click returned LAYOUT_CHANGED/action_executed=false; stop had errors=[]. Added and selected HEADLESS-13, started a 400-character text action only in the dedicated focused fixture, and removed that output after delivery began. It delivered one character, returned ACTION_CANCELLED/action_executed=true, stopped with errors=[] and delivered nothing after stop. Verified only the original eDP-1 remained. Evidence: /tmp/wf-hotplug-soak-1794664776/events.jsonl. This accepts compositor-created output add/remove/recreate behavior, not physical cable events or monitor firmware/EDID behavior.


## Chromium sustained-session run cancelled by user

Created a dedicated Chromium profile and generated local 3,000-record text file on eDP-1. Native Ctrl+F and BMP typing `Resume aA 中文 ✓` matched 1/1, and Escape worked. The user then changed the requested test application to an existing game launcher. Stopped and cleaned the Chromium control session with errors=[] and closed only the dedicated Chromium/fixture processes. The timed soak phase lasted approximately 157.5 seconds and did not execute a timed scrolling checkpoint before cancellation; it is not long-duration acceptance. Evidence: /tmp/wf-hotplug-soak-1794664776/soak-result.json and soak-metrics.jsonl. No automated browser/CDP control was used.


## Full-screen game control and sustained-session result

At the user's request, replaced the Chromium task with the existing An Anime Game Launcher window on eDP-1. Using the release CLI, clicked Launch, observed the full-screen Chinese game client under Proton/XWayland (app-id steam_proton), waited for approximately 530 MB of game-managed resource updates, clicked the enter prompt and reached the playable world using the existing login state. No credentials were supplied or extracted. All ordinary input used the skill's native worker, with actual image inspection between actions; window IPC/wlrctl was used only to identify/focus the authorized launcher/game.

Verified Esc menu open/close, numeric-key character switching, M opening the map, wheel zoom, a 21-point map drag, Esc returning to the world, B opening inventory and a pointer click closing inventory. Some action-result frames preceded the visible UI transition; a subsequent wait/observation confirmed each durable change before another input decision. A Space action was sent, but no airborne frame was inspected, so jumping is not accepted. Held movement, combat, text/chat and relative camera control are not established by these checks. During map/inventory exit, the observed world camera orientation changed; this does not establish calibrated relative motion or unchanged camera state.

The same owner/session remained active for approximately 1,867.3 seconds (31.1 minutes), including startup/update time and approximately 27.5 minutes after first observing the playable world. Generated and inspected 32 observations with 32 distinct image hashes. The last screenshot was at approximately 29.6 minutes; a final active/healthy status/resource sample was recorded at approximately 30.2 minutes before stopping. A test-driver focus guard paused monitoring once when the game lost focus around minute 18; after the user requested more game interactions, explicitly refocused the identified game and continued with the same owner, input worker and Portal session. This was a monitor pause, not a runtime restart. No capture timeout, action error or runtime crash was observed in this game session.

Thirteen resource samples from approximately minute 6.6 through minute 30.2 showed owner RSS 64,308–94,704 KiB (62.8–92.5 MiB), owner FD count 31 and input-worker FD count 10. RSS dipped and later increased during additional observations; these measurements do not prove the absence of a slow leak. This accepts the measured sustained session, not multi-hour leak testing or all game input modes. Final stop returned errors=[], removed all runtime screenshots/socket and left no owner/worker process. Only metadata/hashes and resource records remain under /tmp/wf-hotplug-soak-1794664776 (game-soak-result.json, game-soak-metrics.jsonl and game-image-metadata.json). The game remains running in the logged-in world for the user; only eDP-1 remains. No lock/suspend operation was performed during this game run. Lock-state checks in the test driver are not runtime lock feedback.


## Rust toplevel listing and focus commands

Added `toplevel list` and `toplevel focus --id ID [--pid PID]` using the existing Wayfire IPC protocol directly in Rust. Listing filters mapped application toplevels, preserves distinct same-title IDs and reports title/app-id/PID/output/geometry/activation metadata. Focus validates target identity and (for an active owner) the selected output, requests focus once and verifies compositor active-view state. It reports possible request execution separately from confirmation, has a three-second IPC deadline/four-MiB response limit, and never falls back to another desktop/tool after failure. Active-owner focus shares the input action queue and clears the old observation, requiring a fresh screenshot before further input. Standalone focus holds the per-display control lock. No Python/wlrctl runtime dependency, virtual device or additional standard action type was introduced.

All 23 Rust unit tests, strict Clippy and the release build passed. New protocol tests cover fragmented framing, oversized frames and plugin errors, same-title windows/filtering, refusal to accept acknowledgment alone as focus confirmation, disappearance after request, PID/output/cancellation rejection before sending focus, and a withheld confirmation reply retaining execution uncertainty without retrying.

The complete private dual-output session/launcher-boundary suite with `--toplevel-test` passed in /tmp/wf-rust-isolated-j970oyoe. Two private GTK fixtures verified real focus switching, rejection of an old observation after focus, successful capture with observation_id=null, and queuing focus after a text action starts without redirecting any remaining text into the second window. Cross-output focus and closed-window focus were rejected; standalone focus after stop and PID mismatch protection also passed. Existing deduplication, input/capture, notification, cancellation and worker-lifecycle checks remained successful.

Release current-desktop validation passed with two dedicated GTK windows (/tmp/wf-toplevel-live-hpfywpc6): listed exact PID/title identities, switched focus and observed GTK's active state, rejected a mismatched PID without changing focus, then rejected the closed window ID. Closed only those test processes and restored the original listed window's focus. No shared Portal restart or ordinary input event was used. Focus confirmation establishes compositor active-view state, not exclusive keyboard ownership during a popup/grab/lock; lock-specific runtime feedback remains unimplemented.
