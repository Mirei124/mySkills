---
kind: task-update
id: 0001
---

# Adopt and maintain hypha

## 验收

- Only leaf tasks accept authoritative progress updates.
- Parent progress is the equal-weight average of non-dropped descendant leaves.
- CLI, list, show, and HTML view expose the same effective progress.
- Repository agents use Git and do not use Jujutsu.

## 证据

- `python3 -m unittest discover -s tests -v` passes 17 tests.
- `ruff check skills/hypha-governance/scripts/hypha.py tests/test_hypha.py` passes.
- The repository graph reports root progress as the rounded leaf average.
