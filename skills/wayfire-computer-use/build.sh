#!/bin/sh
set -eu

SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec cargo build --locked --release --manifest-path "$SKILL_DIR/Cargo.toml" --target-dir "$SKILL_DIR/target" "$@"
