# Diagnostics

Run doctor in the environment intended to access the existing desktop. WAYLAND_ACCESS_DENIED means the socket connection was denied; it does not show that protocols are unavailable. Do not change permissions to bypass this restriction.

Read each subprocess result separately. Missing commands and timeouts are reported as failures. Portal introspection proves reachability only, not capture permission. Notification introspection does not send a notification. Protocol and output information is preserved as wayland-info output for inspection.

No input, capture, notification delivery, or desktop end-to-end test has passed yet. Do not use this milestone to control the desktop.
