# Hypha

Hypha is a local, Git-native task and knowledge graph for coding agents. Tasks, evidence, relationships, and knowledge stay in readable Markdown under `.hypha/`; a standard-library Python CLI validates the graph and produces a self-contained offline HTML view.

It is designed for one agent working locally in one repository. It does not require a server, database, account, or network connection.

## New users: fastest path to a working graph

### 1. Requirements

- Python 3.10 or newer
- Git if you want task state to travel with your code
- A browser for the optional visual graph

Node.js is not required to use Hypha. It is only needed when developing the frontend.

### 2. Point the CLI at your project

Clone or download this repository, then keep its CLI path in a shell variable:

```bash
HYPHA_CLI=/absolute/path/to/hypha/skills/hypha-governance/scripts/hypha.py
PROJECT=/absolute/path/to/your/project
```

Initialize Hypha inside the project:

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" init
```

This creates `$PROJECT/.hypha/`. Commit that directory with the project; only local lock and generated view files are ignored.

If you use Codex and want Hypha to trigger as an installed skill, copy it once:

```bash
mkdir -p ~/.agents/skills
cp -R /absolute/path/to/hypha/skills/hypha-governance ~/.agents/skills/
```

For active Hypha development, a symlink is more convenient than repeatedly copying the directory.

### 3. Create and start the first task

For an existing codebase, generate a reviewable bootstrap plan first:

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" bootstrap
```

Hypha writes `.hypha/.drafts/bootstrap-plan.json`. It inventories Git-tracked and local files, groups top-level areas, counts tests, documentation, checklist completion, and TODO/FIXME markers, then proposes a low-confidence maturity estimate. Review titles, boundaries, parent links, and progress before applying it:

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" bootstrap --apply "$PROJECT/.hypha/.drafts/bootstrap-plan.json"
```

Use `bootstrap --dry-run` to print the plan without writing a file, or `bootstrap --output path/to/plan.json` to choose its location. Applying a plan is allowed only when the task graph is empty, so it cannot silently mix inferred tasks into an active graph.

For a new project, create the first task manually:

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" add "Ship the first working feature"
python3 "$HYPHA_CLI" --workspace "$PROJECT" start 0001
```

For later work, create a child task by supplying its parent:

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" add "Add regression coverage" 0001
```

If a task is genuinely independent, say so explicitly:

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" add "Independent maintenance track" --root
```

Hypha intentionally rejects ambiguous new roots and duplicate active titles. Follow-up feedback, small fixes, and acceptance work should normally continue the current task instead of creating one node per conversation turn.

### 4. Use this five-command session loop

At the beginning of a session:

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" boot "what you are working on"
python3 "$HYPHA_CLI" --workspace "$PROJECT" next
python3 "$HYPHA_CLI" --workspace "$PROJECT" start 0001
```

While working:

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" list
python3 "$HYPHA_CLI" --workspace "$PROJECT" list --tree
python3 "$HYPHA_CLI" --workspace "$PROJECT" progress 0001 60
python3 "$HYPHA_CLI" --workspace "$PROJECT" needs 0002 0001
python3 "$HYPHA_CLI" --workspace "$PROJECT" parent 0002 0001
```

When the acceptance criteria and evidence are real:

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" done 0001
python3 "$HYPHA_CLI" --workspace "$PROJECT" lint --audit
python3 "$HYPHA_CLI" --workspace "$PROJECT" close
```

`parent` means hierarchy; `needs` means execution dependency. Do not use chronology alone as a reason to create a dependency edge.

Progress belongs only to leaf tasks. Set it with `progress <id> <0..100>` or complete a leaf with `done`; parent progress is the equal-weight average of every non-dropped descendant leaf, regardless of intermediate grouping. A parent cannot be assigned progress directly and can be marked done only after its derived progress reaches 100%. Adding a child removes the former leaf's stored progress, recalculates every ancestor, and reopens any `done` ancestor that falls below 100%. Reaching 100% does not automatically mark ancestors done because their acceptance and evidence still require confirmation. Dropping a task excludes its whole subtree from ancestor progress.

### 5. Add durable knowledge

Write new content to `.hypha/.drafts/` first. For example:

```markdown
---
kind: know
claim_kind: note
affects: [0001]
triggers: [authentication, token]
---
# Authentication implementation note

The refresh path is handled by `src/auth/refresh.py`.
```

Publish it atomically:

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" apply "$PROJECT/.hypha/.drafts/auth-note.md"
```

Use `claim_kind: sourced` for claims copied from a source and provide `anchors` plus exact evidence quotes. Use `claim_kind: inference` for conclusions and state their premises. Plain `note` pages stay out of automatic boot routing.

### 6. Open the visual map

```bash
python3 "$HYPHA_CLI" --workspace "$PROJECT" view --mode all --open
```

The generated `.hypha/view.html` is read-only, self-contained, and works from `file://`. Use the CLI or drafts to change state; the HTML is only a projection.

### Command map

| Goal | Command |
|---|---|
| Resume context | `boot "topic"`, then `next` |
| List every node | `list`, optionally `--type`, `--status`, `--tree`, or `--json` |
| Inspect a node | `show 0001` or `show know/path` |
| Create structure | `add`, `parent`, `needs` |
| Bootstrap existing code | `bootstrap`, review JSON, then `bootstrap --apply` |
| Update state | `start`, `progress`, `block`, `done`, `drop` |
| Publish Markdown | `apply .hypha/.drafts/file.md` |
| Check integrity | `lint --audit` |
| Explain routing | `why "terms"` |
| Finish a session | `close` |
| View the graph | `view --mode all --open` |

Run `python3 "$HYPHA_CLI" --help` for the complete command list.

## Developers taking over: fastest path to a safe change

### 1. Understand the boundaries

Hypha has two deliverables:

- `skills/hypha-governance/scripts/hypha.py` — the stdlib-only CLI and data model.
- `skills/hypha-governance/templates/view.html` — the generated offline graph distributed with the skill.

Frontend source lives in `frontend/`. The generated template is not the editing surface.

Key paths:

| Path | Responsibility |
|---|---|
| `skills/hypha-governance/SKILL.md` | Agent workflow and governance rules |
| `skills/hypha-governance/scripts/hypha.py` | CLI, validation, audit log, routing, graph export |
| `tests/test_hypha.py` | CLI and persistence regression suite |
| `frontend/src/app.tsx` | Application state, filters, selection history |
| `frontend/src/graph.tsx` | React Flow nodes and edges |
| `frontend/src/layout.ts` | Deterministic layouts |
| `frontend/src/inspector.tsx` | Semantic node inspector |
| `frontend/docs/ARCHITECTURE.md` | Frontend data flow and change boundaries |
| `frontend/docs/VISUAL_STYLE.md` | Visual guardrails and reference design |
| `design_docs/intent.md` | Product rationale and tradeoffs |
| `design_docs/spec.md` | Data model and behavioral specification |

### 2. Run the baseline in under a minute

The CLI has no runtime dependencies. Run its tests directly:

```bash
python3 -m unittest discover -s tests -v
```

The repository pre-commit hook also runs Ruff. Enable it once per clone:

```bash
git config core.hooksPath .githooks
```

For frontend work:

```bash
cd frontend
pnpm install
pnpm typecheck
pnpm lint
pnpm test
pnpm build:template
pnpm test:e2e
```

`pnpm build:template` produces a single-file build and copies it to `skills/hypha-governance/templates/view.html`. Always commit that generated template with its frontend source change.

### 3. Preserve these invariants

- Markdown frontmatter is current truth; snapshot JSONL is an append-only audit projection.
- Task `parent` and `depends_on` references must resolve and remain acyclic.
- Knowledge links may be redlinks; task links may not dangle.
- The CLI does not infer semantic relationships. It reports candidates and requires an explicit decision.
- A non-empty graph requires `add <title> <parent>` or `add <title> --root`.
- Drafts are the safe publishing path. Do not directly edit formal task or knowledge nodes in normal operation.
- `.hypha/` belongs in the product repository so code and task state move together.
- The HTML view remains read-only, offline, and reconstructable from Markdown.
- Layout output must be deterministic; do not add unseeded randomness.
- Do not restore animated SVG filters or large Firefox backdrop-filter regions without measuring repaint cost.

### 4. Make a change safely

1. Run `boot` and `next`; resume a relevant running task before creating another.
2. Add a child only when it is independently trackable and separately acceptable.
3. Change CLI source or frontend source—not generated state by hand.
4. Add regression coverage close to the changed behavior.
5. Run CLI tests and the proportional frontend checks.
6. For frontend changes, rebuild the template and inspect a mixed graph plus a selected-node state at 1920 × 1080.
7. Run `lint --audit`, publish acceptance/evidence through a task-update draft, and run `close`.
8. Review `git diff --check` and commit code together with the corresponding `.hypha` state.

### 5. Test and release notes

- Python tests use temporary workspaces and should not touch the repository's `.hypha` state.
- Playwright verifies that the exported HTML is offline and exercises search, filters, focus, graph selection, inspector navigation, pan, and zoom.
- `frontend/dist`, `frontend/test-results`, and `frontend/playwright-report` are disposable generated directories.
- If you develop against an installed local skill, sync the changed `SKILL.md`, CLI script, and generated template into that installation after tests. The repository remains the source of truth.

## Scope and non-goals

Hypha is local-first and single-agent. It is not a multi-writer coordination service, hosted project manager, vector database, or automatic Git committer. It keeps deterministic structure in the CLI and leaves semantic decisions—what is related, what counts as evidence, and whether work is genuinely complete—to the agent and user.
