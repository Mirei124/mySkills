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
