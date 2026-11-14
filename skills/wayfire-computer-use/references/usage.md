# Development CLI

Use the repository `.venv/bin/python3` for all Python commands. Install requirements.txt into that environment and run `make -C native` from the skill directory. Runtime dependencies include Python, both packages in requirements.txt, libwayland-client, libxkbcommon, GStreamer typelibs and appsink/videoconvert/PipeWire plugins, wayland-info, notify-send, and a working desktop portal. The native/build/input-helper executable is required for input at runtime. A C compiler, pkg-config, Wayland/xkbcommon development files and wayland-scanner are build-time dependencies. GTK 3 typelibs are needed for the test fixture; PyYAML is only needed for skill-creator validation and is not a runtime requirement.

Run `scripts/computer.py doctor`, then `scripts/computer.py start`. Select the display in the portal UI. With one output, mapping selection is automatic; the portal's authorization UI remains independent. Multiple outputs require an explicit `--output NAME`; native multi-output input is not yet verified and currently fails explicitly.

Start returns a session_id, observation_id, screenshot_path, dimensions, output and layout_version. View the PNG using the host image viewer before acting. Pass an envelope to `scripts/computer.py act` on stdin, for example:

```json
{"request_id":"r-1","session_id":"COPY_FROM_START","observation_id":"COPY_FROM_START","action":{"type":"click","x":300,"y":213,"button":"left"}}
```

View each returned screenshot and use its new observation_id. Reusing a request_id with exactly the same envelope returns the saved result without replaying input; a different envelope returns REQUEST_ID_CONFLICT. If action_executed is true on an error, partial execution may have occurred. Observe again, never blindly replay. A screenshot action may omit a stale observation only after recovery support is implemented; currently a lost observation requires restarting the session.

`status`, `release_all`, and `stop` are management commands. Stop bypasses the action queue, cancels the active request and returns after cleanup and the end-notification attempt. Inspect its errors array; the result is also stored in the private runtime stopped.json. Repeated stop returns the completed result. Screenshots are temporary and removed at cleanup. The session exits after five idle minutes or helper death. Notifications do not replace the exclusive per-display lock. SIGKILL of the owner can prevent the end notification; killing the entire process group or losing the session bus cannot guarantee cleanup notification delivery.

This CLI is under development and has not passed the complete ../archive/PLAN.md reliability matrix. Do not install it as a production skill yet.

## Authorized single-output selector click

When the user has authorized automatic Portal source selection, use `start --auto-select-single-output`. It checks that exactly one output exists, waits for a newly observed same-user slurp monitor selector, submits the start notification, then issues exactly one `wlrctl pointer click left` at the existing cursor position. It never uses relative move as absolute positioning. Multi-output selection still requires confirmation. A selector process is not proof of an active input grab; disappearance or concurrent matching selectors can prevent reliable association. Keep this feature explicitly enabled and do not silently retry the click. The native helper remains the backend for ordinary computer actions.

This bootstrap notification occurs before capture is ready because selecting the capture source itself requires the authorized click. It is sent once, and the normal end notification follows cleanup. A selector click may have executed even when later startup steps fail; treat startup failure after the bootstrap notice as potentially having clicked.
