#!/bin/sh
set -eu

SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_DIR=${1:-"$HOME/.local/bin"}
TARGET="$INSTALL_DIR/hypha"
SOURCE="$SKILL_DIR/scripts/hypha"

mkdir -p "$INSTALL_DIR"
if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
    if [ "$(readlink -f "$TARGET" 2>/dev/null || true)" = "$(readlink -f "$SOURCE")" ]; then
        printf '%s\n' "Hypha is already installed: $TARGET"
        exit 0
    fi
    printf '%s\n' "Error: $TARGET already exists and is not this Hypha launcher; choose another directory." >&2
    exit 2
fi
ln -s "$SOURCE" "$TARGET"
printf '%s\n' "Installed Hypha: $TARGET"
printf '%s\n' "Next: ensure $INSTALL_DIR is on PATH, then run hypha --help"
