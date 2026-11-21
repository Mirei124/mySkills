# Actions and compatibility

The Rust runtime validates action objects and envelopes with strict serde types and preflight checks before dispatch. Unknown fields and unsupported values are rejected.

| Action | Required fields | Behavior |
|---|---|---|
| screenshot | none | Capture exactly once; no input |
| wait | optional integer `duration_ms` (0–30000) | Wait for the specified duration (default 250 ms), then capture |
| wait_stable | frames (2–60) | Capture after consecutive identical fresh RGB frames. The capture deadline is eight seconds. |
| move | x, y | Absolute image-pixel position |
| click | x, y, button | Move, press and release |
| double_click | x, y | Two left clicks |
| drag | path | Hold left button across path points |
| scroll | x, y, scroll_x, scroll_y | Move then emit vertical/horizontal axes |
| keypress | keys | Chord, then release all |
| type | text | Input text, then release all |

Pointer actions optionally accept keys (array or null); unknown fields fail. Coordinates are integers, with booleans rejected, and must lie inside the current image. Click buttons left/right/wheel/back/forward match the public enumeration; middle is a local alias of wheel. The axis conversion is 10 requested pixels per Wayland axis unit; in private Chromium 158 and Electron 44 windows at scale 1, requests of +80, +160 and −80 on each axis moved the page by +96, +192 and −96 CSS pixels on each axis. Applications control the final scroll distance.

Native key input is restricted to BMP code points (U+0000 through U+FFFF, with unsupported controls still rejected). Any non-BMP character rejects the entire action before input with UNSUPPORTED_NON_BMP_TEXT; no valid prefix is sent. This covers many emoji, supplementary CJK and musical symbols. Previous GTK emoji results are historical observations, not current supported capability. Text is limited to 10,000 code points, drag paths to 1,000 points and at least two points. The 30-second action deadline includes execution overhead. The idle timeout defaults to five minutes. Set it when creating the owner with `start --idle-timeout SECONDS` (1–3600). Large Unicode text can exceed the input-action timeout; partial execution is reported conservatively.

Keys include CTRL, SHIFT, ALT, SUPER, ENTER, TAB, ESC, BACKSPACE, DELETE, HOME, END, PAGEUP, PAGEDOWN, arrows, SPACE, F1-F12 and ASCII alphanumeric keys. CONTROL, ESCAPE, RETURN, ARROWLEFT/RIGHT/UP/DOWN and META have explicit aliases. CMD is unsupported and is never silently translated to CTRL. Shortcut keycodes follow the helper's controlled US keymap. ASCII text holds each modifier state through experimental 50 ms waits before and after key delivery. Unicode uses a temporary keymap with experimental 50 ms client-settling delays, explicitly resets modifiers and waits after restoring the base map; Chinese and a checkmark passed in GTK 3. A current-desktop Typora test verified fcitx5 shuangpin composition, commit and cancellation. Native key input rejects supplementary-plane emoji. Explicit clipboard input delivered mixed Unicode including emoji, supplementary CJK and a combining mark to Chromium, Electron, Qt, Xwayland Zenity and Kitty in private tests.

The request envelope and session metadata are local extensions, not OpenAI native fields. The skill does not register a computer tool. The optional [MCP adapter](mcp.md) returns inline PNGs.

## Rust implementation

The default runtime is the bundled Cargo project's executable. The action/envelope schema is enforced by strict serde types and preflight checks; the supervised input worker is another process of that same binary. No Python, GStreamer or standalone C helper is used. Screenshot freshness is checked against negotiated PipeWire header timestamps, with checked buffer planes/stride/offset and packed RGB conversion. Input targets one selected normal-orientation output at scale 1; multiple outputs require explicit selection and virtual-pointer v2 binding.

Clipboard mode uses the native Rust data-control client and requires compositor data-control support. Send `{"type":"type","text":"😀𠀀","via_clipboard":true}` only with authorization to overwrite the clipboard. The previous clipboard contents are lost. The input worker serves the new selection until replacement or session shutdown. Clipboard managers may retain a copy. Ctrl+V is the default shortcut. Add `"shift_paste":true` for applications using Ctrl+Shift+V. Confirm delivery from the resulting observation.
