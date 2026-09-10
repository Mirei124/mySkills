# Hypha

Hypha is a local, Git-native task and knowledge graph for people and coding agents. Its Python CLI stores readable Markdown under `.hypha/`, validates relationships and evidence, records append-only audit events, and generates a read-only HTML graph. It works offline and has no model or server dependency.

## Install and start

Hypha requires Python 3.10 or newer. Install the bundled launcher into `~/.local/bin`:

```bash
./skills/hypha-governance/install.sh
hypha --help
```

Pass another directory to the installer when needed. It refuses to replace a different existing file. The Python entry point remains available at `skills/hypha-governance/scripts/hypha.py`.

Initialize a project from its root. Later commands search upward for the nearest `.hypha`; `--workspace` takes priority. Queries never initialize a store implicitly.

```bash
cd /path/to/project
hypha init
```

## Four common paths

Create and start a task without writing YAML:

```bash
hypha task create "Support offline deployment" \
  --acceptance "Runs with networking disabled"
hypha task start 0001
```

Save a decision stated by the user:

```bash
hypha knowledge create "Offline deployment" \
  --origin user \
  --quote "The product must work without network access." \
  --when "Choosing deployment architecture"
```

Create knowledge backed by an exact file quote. Hypha saves the source automatically and publishes only after validation succeeds:

```bash
hypha knowledge create "Offline deployment" \
  --origin repository \
  --source docs/requirements.md \
  --quote "The product must work without network access." \
  --when "Choosing deployment architecture"
```

Resume relevant context, read selected records, then choose executable work separately:

```bash
hypha context resume "offline deployment"
hypha show 0001
hypha list --type task --ready
```

`context resume` returns an index and reading guide. `list --ready` lists todo tasks whose dependencies are complete.

## Tasks and knowledge

Task creation supports repeated `--acceptance`, `--body-file`, `--parent`, and `--root`. Completion requires non-empty Acceptance and Evidence sections, and progress belongs only to leaf tasks.

```bash
hypha task create "Regression coverage" --parent 0001 \
  --acceptance "Offline behavior has a regression test"
hypha task progress 0002 40
hypha task block 0002 "Waiting for a fixture"
hypha task needs 0002 0003
```

Task and knowledge edits share the same safe interface. `--body-file` publishes a revision-guarded update, `--editor` opens a prefilled draft and publishes after validation, and `--draft` keeps the prefilled draft for later publication. `--section` updates one level-two section while retaining other content and metadata.

```bash
hypha task edit 0001 --section Evidence --body-file evidence.md
hypha knowledge edit know/offline-deployment --editor
hypha advanced publish .hypha/.drafts/edit-example.md
```

Knowledge origins map to the existing authority fields:

| CLI origin | Stored authority | Required evidence |
|---|---|---|
| `user` | `user_explicit` | `--quote` |
| `user-confirmed` | `user_confirmed` | `--quote` |
| `repository` | `repository` | `--source` and exact `--quote` |
| `external` | `external_source` | `--source` and exact `--quote` |
| `inference` | `agent_inference` | repeated `--premise` and `--reason` |

All knowledge also requires `--when`. Use `--review-when`, repeated `--affects`, `--body-file`, `--draft`, or `--editor` as needed. Classification and retrieval terms are derived when omitted. An active knowledge title cannot be overwritten. Failed publication retains the draft and leaves no formal node or newly copied source.

## Sources, drafts, and advanced operations

Importing a document stores material only. Add `--suggest` to request existing knowledge candidates; interpretation and claim extraction remain agent work.

```bash
hypha advanced import contract.md
hypha advanced drafts
hypha advanced publish .hypha/.drafts/decision.md
hypha advanced bootstrap
hypha advanced bootstrap --apply .hypha/.drafts/bootstrap-plan.json
hypha advanced migrate
hypha advanced explain "offline deployment"
```

`advanced migrate` retains legacy-agreement guidance. Bootstrap proposals must be reviewed before `--apply`, which requires an empty graph.

## Two-stage context handoff

Prepare a handoff, review this turn for anything not yet saved, then finalize it:

```bash
hypha context close
# Review .hypha/.drafts/context-close.json and save missing information.
hypha context close --finalize
```

Preparation selects all in-progress and blocked tasks, or accepts repeated `--task ID`. It creates or reuses the JSON preparation without writing a close marker. Fill `resume_task` for multiple active targets, or `no_task_reason` when there is no task. Both knowledge and recovery reviews must be `saved` with valid references or `not_needed` with a reviewed reason; the CLI never supplies that answer.

Finalization checks task Acceptance and Next Step, blockers, completed-task evidence, review decisions, and references. It writes `.hypha/handoffs/<handoff-id>.json` with content hashes before appending the linked close marker. Repeating finalize is idempotent. These checks cannot prove that the conversation contained no other information worth saving.

Without a topic, `context resume` shows the latest completed handoff first, including the current Next Step and references. It reports task, status, hash, and reference changes without restoring old content. With a topic, normal retrieval remains primary and handoff data is supplemental. An unfinished close preparation is reported as unconfirmed.

## Query, validation, and output

```bash
hypha list --type task --status in_progress
hypha show know/offline-deployment
hypha search "offline,network" --type knowledge
hypha check --audit
hypha view --mode all
```

`list`, `show`, and `search` are shared query commands. `show` also accepts a draft under `.hypha/.drafts/`. `check` performs structural validation; `--audit` adds semantic review candidates. The graph is read-only.

All commands accept `--json`, and common options can appear before or after the selected command. Successful JSON has `ok`, `command`, and `result`; errors use `ok: false` with a stable error code and message. `list --json` places its structured counts and node collection inside `result`. Normal explanatory text is never mixed into JSON.

`--global` is limited to knowledge, sources, drafts, and applicable queries. Tasks and context lifecycle operations always use workspace-local storage.

## Command migration

Old entries are no longer execution aliases. They exit with a replacement command:

| Old entry | Replacement |
|---|---|
| `add` | `task create` |
| `start`, `block`, `done`, `drop`, `progress` | `task <command>` |
| `parent`, `needs` | `task <command>` |
| `edit` | `task edit` or `knowledge edit` |
| `boot` | `context resume` |
| `close` | `context close` |
| `ready` | `list --type task --ready` |
| `ingest` | `advanced import` |
| `apply` | `advanced publish` |
| `drafts` | `advanced drafts` |
| `lint` | `check` |
| `route` | `advanced explain` |
| `bootstrap`, `migrate`, `dismiss`, `defer` | `advanced <command>` |

## Development

```bash
python3 -m unittest discover -s tests -v
cd frontend
pnpm install
pnpm typecheck
pnpm lint
pnpm test
pnpm build:template
pnpm test:e2e
```

Playwright cannot navigate to `file://` here. Serve generated HTML over localhost for browser inspection, then stop the server:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory .hypha
```

Preserve these boundaries: Markdown frontmatter is current truth; snapshots are an append-only audit projection; task relationships must resolve and remain acyclic; formal edits use revision protection; source quotes must match saved material; graph rendering stays read-only and deterministic.
