# Repository Guidance

- Run Python scripts and validation with `./.venv/bin/python` so repository dependencies are consistent.
- When documenting MCP calls in a skill, use the exact registered tool name. For the arXiv server, names use the `mcp__arxiv_mcp_server__<tool>` form, such as `mcp__arxiv_mcp_server__search_papers`.
- Use Git for version control and commits in this repository and do not use Jujutsu (`jj`).
- Start commit subjects with `<skill-name>: <type>: <summary>`, for example `wayfire-computer-use: feat: add window focus`. Types include `feat`, `fix`, `refactor`, `docs`, `test`, and `chore`. For changes spanning several skills, use comma-separated skill names; use `repo` for repository-only infrastructure changes.
- Keep `skills/` limited to self-contained installation payloads. Include source and build scripts needed to compile on the target machine. Place development-only projects, tests, evaluations, plans, archives, and implementation evidence under `maintenance/<skill-name>/`. Installed skill instructions and runtime resources must not depend on that maintenance tree.
- Use English for repository documentation, skill instructions, CLI help and output, error messages, generated task section headings, and frontend user-facing text.
- Playwright CLI blocks `file://` navigation. To inspect generated local HTML, serve its directory temporarily with `python3 -m http.server <port> --bind 127.0.0.1 --directory <directory>`, open the corresponding `http://127.0.0.1:<port>/...` URL, and stop the server afterward.
