#!/bin/sh
set -eu

SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# Native PipeWire bindings need the compiler's built-in C headers.
if [ -z "${CARGO_BUILD_TARGET:-}" ]; then
    case " $* " in
        *" --target "*|*" --target="*) ;;
        *)
            if include_dir=$("${CC:-cc}" -print-file-name=include 2>/dev/null) &&
                [ -r "$include_dir/stdbool.h" ]; then
                export BINDGEN_EXTRA_CLANG_ARGS="${BINDGEN_EXTRA_CLANG_ARGS:+$BINDGEN_EXTRA_CLANG_ARGS }-isystem \"$include_dir\""
            fi
            ;;
    esac
fi

exec cargo build --locked --release --manifest-path "$SKILL_DIR/Cargo.toml" --target-dir "$SKILL_DIR/target" "$@"
