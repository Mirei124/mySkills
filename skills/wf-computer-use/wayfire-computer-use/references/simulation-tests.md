# Simulated display validation

Run the offline suite from the repository root:

```bash
.venv/bin/python3 -m unittest discover -s skills/wf-computer-use/tests
```

The suite includes 288 pointer-contract cases spanning three output origins, four scale factors (1, 1.25, 1.5, 2), eight rotations/reflections, and three image positions. The fake compositor assumes display-oriented frames and output-bound normalized pointer semantics. These cases test the dispatcher contract, not whether a real compositor honors that binding or a portal supplies correctly oriented frames.

Output parsing now preserves wl_output integer scale and transform, so layout invalidation also detects rotation/scale metadata changes with unchanged logical bounds. wl_output.scale is rounded up for fractional scaling: a configured scale of 1.25 can advertise integer scale 2; logical geometry remains the relevant positioning information. Fractional scale changes that preserve all parsed metadata are not separately detected by the parser.

An opt-in integration probe starts the distribution Wayfire binary with two headless outputs, pixman rendering, a private runtime directory, an explicit minimal configuration, no plugins, and no connection to the live desktop/session bus:

```bash
.venv/bin/python3 skills/wf-computer-use/tests/probe_headless.py --result /tmp/wf-headless-result.json
```

It bypasses user session-launch wrappers, verifies output geometry and rotation, then terminates the isolated process and removes its runtime directory. It does not change the current desktop configuration. Verified on Wayfire 0.12.0 / wlroots 0.20.2:

| Output | Mode | Position | Configured scale | Rotation | Observed logical size |
|---|---|---|---|---|---|
| HEADLESS-1 | 1920x1080 | -960,0 | 2 | 180 degrees | 960x540 |
| HEADLESS-2 | 1920x1080 | 0,0 | 1.25 | 90 degrees | 864x1536 |

The probe does not run Portal or validate actual pointer hit targets. Portal stream orientation, output binding, multi-output click mapping and changed-layout recovery still require further isolated integration work before multi-output input is enabled. No simulated test result is treated as physical-display acceptance.

## Current-session two-output integration (2026-11-14)

With explicit user authorization, the existing Wayfire session was tested with eDP-1 at (0,0) and HEADLESS-8 at (1920,0), both 1920x1080 at scale 1 with normal orientation. Only a newly created, uniquely identified GTK fixture was moved to HEADLESS-8 using Wayfire IPC.

The test-only probe_current_multi.py subclass bypasses the production multi-output gate solely for HEADLESS-8. A newly detected Portal selector receives an output-bound virtual pointer move to the headless display center and one authorized wlrctl click. The production single-output auto-selector option remains restricted to one output. The Portal stream must still match the explicitly selected output's position and logical size.

Observed results:

- Portal returned HEADLESS-8 frames at 1920x1080, visually containing the fixture and a different desktop background from eDP-1.
- A click at image (300,213) generated fixture-local press/release at (168,18), consistent with its client origin (132,195).
- The fixture received `HEADLESS-8 点击映射测试` exactly; the screenshot showed the same text.
- A drag from image x=134 through x=300 at y=213 produced held-button motion and a visible text selection. The event log included local x=2 and x=168.
- Stop returned an empty cleanup-errors list and the fixture was closed. Output configuration was unchanged.

This verifies a real Portal/input loop on the current physical-plus-headless, normal-orientation, scale-1 configuration with a nonzero selected-output origin. It does not validate scale/rotation capture orientation or every multi-output layout. Production multi-output input remains gated pending broader acceptance and an explicit supported-capability policy.
