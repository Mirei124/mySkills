# Actions and compatibility

The public OpenAI action definitions are pinned as a vendored content snapshot in action-schema-snapshot.py.txt; schema-lock.json records its SHA-256, retrieval date and source URL. The moving upstream branch is not an immutable Git revision. Local strict validation is described by actions.schema.json and enforced before dispatch by computer.py.

| Action | Required fields | Behavior |
|---|---|---|
| screenshot | none | Capture exactly once; no input |
| wait | none | Wait 250 ms, then capture |
| move | x, y | Absolute image-pixel position |
| click | x, y, button | Move, press and release |
| double_click | x, y | Two left clicks |
| drag | path | Hold left button across path points |
| scroll | x, y, scroll_x, scroll_y | Move then emit vertical/horizontal axes |
| keypress | keys | Chord, then release all |
| type | text | Input text, then release all |

Pointer actions optionally accept keys (array or null); unknown fields fail. Coordinates are integers, with booleans rejected, and must lie inside the current image. Click buttons left/right/wheel/back/forward match the public enumeration; middle is a local alias of wheel. The axis conversion is 10 requested pixels per Wayland axis unit; application scrolling is not guaranteed pixel-exact and real calibration remains pending.

Text is restricted to BMP code points (U+0000 through U+FFFF, with unsupported controls still rejected). Any non-BMP character rejects the entire action before input with UNSUPPORTED_NON_BMP_TEXT; no valid prefix is sent. This covers many emoji, supplementary CJK and musical symbols. Previous GTK emoji results are historical observations, not current supported capability. Text is limited to 10,000 code points, drag paths to 1,000 points and at least two points. Wait has no per-action duration field. The session imposes a 30-second input-action limit and five-minute idle timeout. Large Unicode text can exceed the input-action timeout; partial execution is reported conservatively.

Keys include CTRL, SHIFT, ALT, SUPER, ENTER, TAB, ESC, BACKSPACE, DELETE, HOME, END, PAGEUP, PAGEDOWN, arrows, SPACE, F1-F12 and ASCII alphanumeric keys. CONTROL, ESCAPE, RETURN, ARROWLEFT/RIGHT/UP/DOWN and META have explicit aliases. CMD is unsupported and is never silently translated to CTRL. Shortcut keycodes follow the helper's controlled US keymap. ASCII text holds each modifier state through experimental 50 ms waits before and after key delivery. Unicode uses a temporary keymap with experimental 50 ms client-settling delays, explicitly resets modifiers and waits after restoring the base map; Chinese and a checkmark passed in GTK 3. IME, emoji and other toolkit compatibility remain unverified. No clipboard text strategy is enabled.

The request envelope and session metadata are local extensions, not OpenAI native fields. The skill does not register a computer tool. The optional MCP adapter has not been implemented.

## Rust implementation

The default runtime is the root Cargo project's executable. The action/envelope schema is enforced by strict serde types and preflight checks; the supervised input worker is another process of that same binary. No Python, GStreamer or standalone C helper is used. Screenshot freshness is checked against negotiated PipeWire header timestamps, with checked buffer planes/stride/offset and packed RGB conversion. Input targets one selected normal-orientation output at scale 1; multiple outputs require explicit selection and virtual-pointer v2 binding.
