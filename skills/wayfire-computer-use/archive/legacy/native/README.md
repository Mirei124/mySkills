> Archived Python/C implementation. The active runtime is the Rust executable built from the skill root.

# Native input helper

Build with `make`. Requires wayland-scanner, wayland-client, and xkbcommon development files. `build/input-helper --probe` checks protocol availability without creating input devices. The default mode creates persistent devices and accepts internal line commands on stdin; use the session CLI for desktop tasks so locking, notifications and capture are enforced.

The helper supports absolute motion, output-name binding with virtual-pointer v2, button/key state, modifiers, axes, temporary Unicode keymaps, release, and stop. EOF releases recorded states and destroys devices. The Python owner serializes actions, supervises helper exit and cancels requests before shutdown. Terminating the entire owner process group can prevent notifications.

Current real tests cover one unrotated 1920x1080 display at scale 1, GTK pointer events and Chinese/ASCII text with experimental settling delays. Multi-output binding, scaling/rotation, emoji and other toolkits remain unverified. The session rejects multi-output input until mapping is validated. Do not treat basic event delivery as full reliability acceptance.

Protocol XML files retain their upstream copyright and MIT-style license notices. Retrieved 2026-11-14 via jsDelivr from swaywm/wlr-protocols master (unstable/wlr-virtual-pointer-unstable-v1.xml) and swaywm/wlroots master (protocol/virtual-keyboard-unstable-v1.xml). The files are vendored; upstream Git revision pinning remains pending.
