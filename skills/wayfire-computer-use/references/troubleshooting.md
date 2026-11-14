# Diagnostics and recovery

Run doctor in the environment intended to access the existing desktop. WAYLAND_ACCESS_DENIED means the socket connection was denied; it does not show that protocols are unavailable. Never change permissions or switch input backends to bypass access restrictions.

Read each probe result separately. Missing commands and timeouts are failures. Portal introspection proves reachability, not capture permission. Notification introspection does not send a notification. Doctor reports protocol versions, output geometry, portal routing and PipeWire plugin availability without sending input.

| Result | Response |
|---|---|
| OUTPUT_CONFIRMATION_REQUIRED | Confirm the desired output with the user. Single-output automatic selection does not apply to multiple outputs. |
| MULTI_OUTPUT_INPUT_UNVERIFIED | The initial production CLI keeps multi-output input disabled. The separately documented HEADLESS-8 integration test does not enable every configuration. |
| CAPTURE_CANCELLED | Portal selection was cancelled. Stop; do not automatically repeat selection clicks. |
| SESSION_START_TIMEOUT / SESSION_START_FAILED | Startup did not complete; the CLI terminates its preparing owner. Check portal/plugin availability and source selection before a deliberate retry. |
| STALE_OBSERVATION / LAYOUT_CHANGED | Do not reuse coordinates. Stop and create a new session/mapping. |
| ACTION_CANCELLED | Input may have partially executed; inspect action_executed and the stop cleanup result. |
| REQUEST_ID_CONFLICT | A request ID was reused with different content. Do not assume the new action ran. |
| FIXTURE_NOT_FOCUSED | Test-only guard refused dispatch. Confirm the uniquely identified fixture is alive, visible and focused. |
| NOTIFICATION_FAILED | Start notification submission failed; no ordinary control should begin. |

Always inspect stop's errors list. Cleanup uncertainty must be reported; a successfully submitted notification does not prove the user saw it. If a whole process group is killed or the desktop bus is lost, an end notification cannot be guaranteed.

See IMPLEMENTATION.md at the skill root for historical tests and fixes, and simulation-tests.md for the exact virtual/current-output validation scope. The initial version has passed current-session screenshot/input tests and offline regression tests, but its full fault and hardware matrix is incomplete.
