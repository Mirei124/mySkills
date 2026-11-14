# Wayfire computer use maintenance

The [installation payload](../../skills/wayfire-computer-use/SKILL.md) includes the complete Rust project and `build.sh`, so copies installed by skill managers can compile locally. `target/` and generated executables are ignored. Runtime does not depend on this maintenance directory. Updating source does not automatically rebuild an existing executable; rebuild explicitly.

Run from the repository root:

```bash
./skills/wayfire-computer-use/build.sh
cargo test --locked --manifest-path skills/wayfire-computer-use/Cargo.toml
cargo clippy --locked --manifest-path skills/wayfire-computer-use/Cargo.toml --all-targets -- -D warnings
cargo build --locked --manifest-path skills/wayfire-computer-use/Cargo.toml
./.venv/bin/python -m pip install -r maintenance/wayfire-computer-use/requirements-dev.txt
```

Python packages are development-only. The isolated harness additionally needs Wayfire, D-Bus, PipeWire, WirePlumber, Portal services and the fixture toolkit described in its source; paths match the tested Arch installation. Run desktop probes serially:

```bash
./.venv/bin/python maintenance/wayfire-computer-use/tests/probe_rust_isolated.py --input-test --session-test
./.venv/bin/python maintenance/wayfire-computer-use/tests/probe_rust_isolated.py --multi-output --session-test --toplevel-test --launcher-boundary-test
./.venv/bin/python maintenance/wayfire-computer-use/tests/probe_control_regressions.py
./.venv/bin/python maintenance/wayfire-computer-use/tests/probe_headless.py
./.venv/bin/python maintenance/wayfire-computer-use/tests/probe_selector_keyboard.py
```

The isolated harness starts private services and retains logs/screenshots in its reported temporary directory. It does not restart the current desktop's Portal services. `probe_selector_keyboard.py --selector PATH` selects a specific slurp binary; `--expect-crash` deliberately checks the original private-desktop crash. Read the probe options before running fault injection.

- [Implementation history](IMPLEMENTATION.md)
- [Validation evidence and coverage limits](references/simulation-tests.md)
- [Schema provenance](references/schema-lock.json) and [vendored snapshot](references/action-schema-snapshot.py.txt)
- [Archived plan](archive/PLAN.md) and [historical Python/C implementation](archive/legacy/)

Historical paths and temporary evidence locations record their original context; use the commands above for the current layout.
