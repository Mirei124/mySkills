# Diagnostics and recovery

Run `target/release/wayfire-computer-use doctor` inside the intended Wayfire session. It reports outputs/protocols, session-bus service ownership and PipeWire socket access without creating input devices. Service ownership does not establish capture permission or successful streaming. Do not change socket permissions or switch input backends to evade restrictions.

| Result | Response |
|---|---|
| WAYLAND_UNAVAILABLE | Check the intended session's Wayland socket/access. Permission errors do not prove missing protocols. |
| WAYLAND_RESPONSE_TIMEOUT | The compositor did not answer within the bounded roundtrip. Stop; do not replay input blindly. |
| OUTPUT_CONFIRMATION_REQUIRED | Confirm the desired output. Automatic single-output selection does not apply to multiple outputs. |
| MULTI_OUTPUT_INPUT_UNVERIFIED | The initial production runtime keeps multi-output input disabled; historical test results have limited scope. |
| UNSUPPORTED_OUTPUT_TRANSFORM_OR_SCALE | Initial input support requires normal orientation and scale 1. Other geometry tests do not prove click mapping. |
| PORTAL_CREATE_TIMEOUT / PORTAL_SOURCE_SELECTION_TIMEOUT / PORTAL_START_TIMEOUT | The named phase failed. Stop and inspect Portal state before a deliberate retry; do not automatically repeat clicks. |
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
