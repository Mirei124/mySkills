# Repository Guidance

- Run Python scripts and validation with `./venv/bin/python` so repository dependencies are consistent.
- When documenting MCP calls in a skill, use the exact registered tool name. For the arXiv server, names use the `mcp__arxiv_mcp_server__<tool>` form, such as `mcp__arxiv_mcp_server__search_papers`.
- Use Git for version control and commits in this repository and do not use Jujutsu (`jj`).
- Keep concise, always-on repository operating rules in the nearest applicable `AGENTS.md`. Do not duplicate those rules in Hypha knowledge; use Hypha for their rationale, scope, evidence, history, exceptions, review conditions, and links to long-running work.
