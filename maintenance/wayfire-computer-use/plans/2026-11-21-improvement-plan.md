# wayfire-computer-use improvement plan (2026-11-21)

Execution plan derived from acceptance-testing feedback and a feasibility review of
the current implementation. Hand this document to the executing agent as the single
source of scope. Work items are ordered by priority inside each phase; phases are
independent milestones and each item should land as its own commit (or small commit
series) following the repository commit convention
(`wayfire-computer-use: <type>: <summary>`).

## Context

The skill drives existing Wayfire desktop applications through a Rust CLI
(`skills/wayfire-computer-use/`) using Portal/PipeWire capture and virtual
pointer/keyboard input. Acceptance testing identified friction points; a code-level
review confirmed which ones have feasible fixes. This plan contains only the items
judged feasible. Items explicitly out of scope are listed at the end.

### Verified environment facts (checked 2026-11-21 on the development machine)

- The AT-SPI accessibility bus is running (`at-spi-bus-launcher` active; address
  resolvable via `org.a11y.Bus GetAddress`) and already has 3 applications
  registered on it. `at-spi2-core 2.62.1` is installed.
- `tesseract 5.5.4` is installed with the `chi_sim` language model only
  (`eng` is NOT installed; OCR work must either note this or request installation).
- `pyatspi` is not installed. The runtime must stay Python-free regardless; use the
  Rust `atspi` crate (zbus-based, maintained by the Odilia project) for AT-SPI work.
- The project already depends on `wayland-protocols-wlr` (virtual pointer bindings
  in `src/desktop.rs`), which also contains the `zwlr_data_control_manager_v1`
  bindings needed for clipboard work.

### Design invariants — do not weaken

1. **Conservative capability claims.** Only document configurations actually
   validated by tests. Never claim untested toolkit/layout support.
2. **Explicit failure, no automatic retry, no silent fallback.** Errors must fail
   loudly; partial execution is reported conservatively (`action_executed`,
   `*_may_have_executed` fields).
3. **Observation discipline.** Any operation that can change the desktop
   invalidates the current observation and requires a fresh viewed screenshot
   before further ordinary input. New write-capable commands MUST go through the
   same action queue and observation-invalidation path as native input (model:
   owner-managed `toplevel focus`).
4. **Real-input priority policy** (new, to be encoded in SKILL.md by item 3.1):
   AT-SPI is preferred for *reads* (locating, state, wait conditions); simulated
   input is preferred for *writes*. Within simulated input, keyboard semantics
   (Enter/Esc/Tab/mnemonics/shortcuts) are preferred over coordinate clicks.
   Rationale: real input inherits the UI's own affordance constraints (occluded or
   disabled controls cannot be clicked), keeps the screenshot-as-ground-truth
   discipline meaningful, and produces results transferable to real users.
5. English for all documentation, CLI help/output and error messages.
6. Development artifacts (tests, evaluations, prototypes, this plan) live under
   `maintenance/wayfire-computer-use/`; the installed skill payload under
   `skills/wayfire-computer-use/` must not depend on the maintenance tree.

## Phase 1 — small, low-risk ergonomics (do first)

### 1.1 `wait` with an optional duration

- Current: hard-coded 250 ms in `src/execute.rs` (`Action::Wait` arm).
- Change: add an optional `duration_ms` field to the `wait` action (strict serde;
  reject unknown fields as today). Validate bounds, e.g. 50–10000 ms; default 250.
  The existing 30-second per-action deadline still applies.
- Update `references/actions.md` (action table row and the "Wait has no
  per-action duration field" sentence) and the schema artifacts under
  `maintenance/wayfire-computer-use/references/` if the schema lock covers `wait`.
- Acceptance: `validate` accepts/rejects the new field correctly; an integration
  test exercises a non-default duration; docs updated.

### 1.2 Configurable idle timeout

- Current: hard-coded 300 s in the session tick loop in `src/session.rs`
  (`elapsed() > Duration::from_secs(300)`).
- Change: `start --idle-timeout-secs N` with a documented cap (suggest 60–1800,
  default 300). Reflect the value in `status`/`capabilities` output.
- Acceptance: timeout honored in an integration test (short value); docs updated.

### 1.3 Convenience envelope: `act --latest`

- Current: every `act` call requires manually copied `session_id`,
  `observation_id` and a fresh `request_id`.
- Change: an opt-in flag (`act --latest`) that reads the current
  `session_id`/`observation_id` from the owner's control socket (the `status`
  path already exposes them) and auto-generates a `request_id`. The full resolved
  envelope MUST be echoed in the result for auditability. Validation semantics are
  unchanged: a stale observation still fails. Auto-generated request IDs forfeit
  caller-side dedup, so retries/replays MUST still require an explicit
  `request_id`; document this trade-off.
- Acceptance: stale-observation rejection still covered by tests when using
  `--latest`; result echoes the resolved envelope; docs updated.

### 1.4 Recovery guidance in error output

- Current: after timeouts/invalidation the caller must infer the restart sequence.
- Change: for observation-invalid, idle-timeout and permanent-capture errors,
  append a machine-readable `recovery` hint (ordered next-step commands: `stop`,
  `start`, re-`toplevel focus`, fresh screenshot) to the error payload, and a
  short "Recovery" subsection in `references/troubleshooting.md`. This is
  guidance only — no behavioral change, no automatic recreation.
- Acceptance: hints present in the three error paths; docs updated.

## Phase 2 — medium work items

### 2.1 Clipboard text input (fixes non-BMP rejection and large-text timeouts)

- Mechanism: implement an explicit clipboard path for `type`
  (e.g. `{"type":"type","text":...,"via":"clipboard"}` — strict serde, default
  remains key input): set the clipboard through `zwlr_data_control_manager_v1`
  (bindings already in the `wayland-protocols-wlr` dependency), then send
  Ctrl+V through the existing virtual keyboard.
- Requirements:
  - Explicit opt-in only; never a silent fallback. Update the SKILL.md sentence
    "No clipboard fallback is enabled" to describe the explicit option instead.
  - Document side effects: overwrites the user clipboard (optionally snapshot and
    restore it via data-control — if restore is implemented, report restore
    failure explicitly); the paste shortcut is application-dependent (terminals
    often use Ctrl+Shift+V), so the paste chord should be overridable in the
    action and the default documented.
  - Non-BMP text is allowed on this path; the key-input path keeps rejecting it.
  - Capabilities output (`clipboard:false` today in `src/session.rs` status JSON)
    must reflect reality.
- Acceptance: integration test pasting a non-BMP string (emoji) into a GTK app;
  test that default `type` still rejects non-BMP; docs (SKILL.md, actions.md,
  usage.md, compatibility.md) updated consistently.

### 2.2 Conditional waits

Two complementary mechanisms:

- **`toplevel wait`** — `toplevel wait --app-id X | --title-regex R
  [--state focused|mapped] --timeout-secs N` built on the existing Wayfire IPC
  client in `src/toplevel.rs` (poll `window-rules/list-views`, or subscribe to
  ipc events if straightforward). Read-only; same plugin requirements and
  identity checks as `toplevel list`; no observation invalidation.
- **`wait_stable` action** — capture-side wait that returns after N consecutive
  unchanged frames (bounded by a timeout), building on the existing 100 ms
  capture health tick and frame timestamps in `src/session.rs`. Define
  "unchanged" cheaply (e.g. buffer hash); document that visual stability is a
  heuristic, not a correctness proof.
- Acceptance: integration tests for both (window appears late; animation
  settles); docs updated; timeouts bounded and explicit.

### 2.3 Lock-screen detection

- Mechanism: subscribe to logind `org.freedesktop.login1.Session` `LockedHint`
  over the system bus (the project already uses D-Bus). Report lock state in
  `doctor` and `status`; when `LockedHint` becomes true during a session, cancel
  input the same way other monitor-triggered cancellations work.
- Conservative semantics: detection blocks input; the absence of `LockedHint`
  proves nothing (lockers may not report it). Screenshots remain the final
  authority; document this in `references/troubleshooting.md#lock-screen-feedback`.
- Acceptance: doctor/status show the state; a simulated LockedHint toggle cancels
  input in a test (mock or loginctl-driven); docs updated.

### 2.4 AT-SPI read-only element discovery (`ui` subcommands)

The highest-value Phase 2 item. First iteration is **read-only** — no AT-SPI
Action invocation.

- Commands:
  - `ui tree --window-id ID` — dump roles/names/states/extents for a toplevel.
  - `ui find --role button --name "Save" [--window-id ID]` — return matching
    nodes with **absolute** coordinates.
- Coordinate strategy (the key design point): AT-SPI global coordinates are
  unreliable on Wayland. Query extents with window-relative coordinate type and
  add the toplevel's logical geometry from Wayfire IPC (`toplevel list` already
  returns it). Correlate the AT-SPI application/window with the Wayfire toplevel
  via pid + title/app_id; fail explicitly on ambiguous correlation.
- Implementation: Rust `atspi` crate (zbus-based). Keep it an optional capability
  like `toplevel`: missing a11y bus fails explicitly, never degrades other
  commands.
- Document toolkit coverage honestly: GTK3/4 register automatically; Qt needs
  `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1`; Chromium/Electron expose a full tree only
  with accessibility forced; Xwayland apps are reachable (AT-SPI is D-Bus-based,
  display-protocol-independent).
- Scope note: AT-SPI *write* operations (Action.press) are deliberately deferred.
  If ever added, they must run through the owner's action queue, invalidate the
  observation, be explicitly labeled in results as a non-real-input path, and be
  used only after real input has been tried and failed or under explicit user
  authorization (see invariant 4).
- Acceptance: on the development desktop, `ui find` for a visible GTK button
  returns coordinates that a subsequent `click` hits (validated end-to-end with a
  screenshot); ambiguity and missing-bus paths covered by tests; docs updated
  (SKILL.md workflow step: locate via `ui find`, verify via screenshot, act via
  input).

### 2.5 SKILL.md workflow/priority update

- Encode invariant 4 (read/write split, keyboard-over-coordinates preference) in
  SKILL.md and `references/usage.md` once 2.4 lands. Keep it short; SKILL.md is
  the installed instruction surface.

## Phase 3 — larger milestones

### 3.2 MCP adapter

- A separate MCP server wrapping the control socket, returning screenshots as
  image content blocks and holding session state server-side. Eliminates the
  "path → read image" round trip and manual ID management in one stroke.
- Big item; design doc first (under maintenance), then implementation. The CLI
  remains the source of truth; the adapter must not bypass the queue/observation
  model. `references/actions.md` currently states the MCP adapter is not
  implemented — keep that statement accurate until this ships.

## Out of scope (do not attempt)

- **OCR location and integer scale 2**: removed from scope by the maintainer.
- **Shared seat isolation** (moving windows to a headless output or nesting a
  compositor): a different product shape; long-term exploration only.
- **Mid-session output switching**: Portal ScreenCast streams are per-source;
  stop/restart is the correct model.
- **Fractional scale and rotated outputs**: excluded alongside scale 2.

## Investigation item (no committed fix)

- **Xwayland native-dialog clicks not registering** (observed once during
  acceptance; keyboard confirmation worked). Reproduce first; use `ui tree`
  (2.4) to check the button's true extents vs. the clicked coordinates, and
  determine whether virtual-pointer absolute motion is mistranslated through
  Xwayland pointer emulation or the application ignored the click. Write findings
  to `maintenance/wayfire-computer-use/` before proposing any code change.

## Process requirements for the executing agent

- Git only (no Jujutsu). Commit subjects: `wayfire-computer-use: <type>: <summary>`.
- Build with `./build.sh` in the skill directory; run Python tooling through the
  repository venv wrapper per AGENTS.md.
- Keep `skills/wayfire-computer-use/` self-contained; evidence, prototypes and
  test assets go under `maintenance/wayfire-computer-use/`.
- Update documentation in the same commit as the behavior it describes.
- When uncertain whether a capability claim is validated, claim less.
