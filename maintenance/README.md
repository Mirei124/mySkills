# Skill maintenance

`skills/` contains self-contained installation payloads, including source and build scripts needed on target machines. This directory holds development-only material, grouped by skill name.

| Skill | Maintenance entry |
|---|---|
| hypha-governance | [CLI guide and tests](hypha-governance/README.md), [frontend](hypha-governance/frontend/README.md), [evaluations](hypha-governance/evals/README.md), [design documents](hypha-governance/design_docs/) |
| dibufusion-api | [Offline tests and API evidence](dibufusion-api/README.md) |
| wayfire-computer-use | [Build, regressions and history](wayfire-computer-use/README.md) |
| research-hypothesis-loop (deprecated) | [Evaluations](research-hypothesis-loop/README.md) |

Follow [repository guidance](../AGENTS.md). Python validation uses `./.venv/bin/python` from the repository root. The [pre-commit hook](../.githooks/pre-commit) runs Hypha lint and regressions; enable it with `git config core.hooksPath .githooks` if desired. Commit subjects start with `<skill-name>: <type>: <summary>`.

The root `.hypha/` records repository task/knowledge history. Historical paths in audit records are retained rather than rewritten as current installation instructions.
