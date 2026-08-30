# Bootstrap evidence bundle

`hypha bootstrap` initializes a brownfield workspace without pretending that file counts or Git activity reveal the project's true completion state. The command produces a reviewable evidence bundle; an agent supplies the semantic judgment before anything enters the graph.

## What discovery records

- A bounded inventory of repository and local files, excluding Hypha state, build output, dependencies, hidden directories, and patterns in `.hypha-bootstrapignore`.
- Up to 20 recent Git commit subjects as observations of work that occurred. A commit is not proof that a task is complete.
- Explicit Markdown checklist items and comment-form `TODO`/`FIXME` markers. Checked items become 100% leaf candidates and open items become 0% leaf candidates, but remain subject to agent review.
- Up to eight high-signal background documents such as `README.md` and Markdown under `docs/` or `design_docs/`. Each candidate carries an exact quote and source anchor. `AGENTS.md` is intentionally not copied into knowledge because it already supplies scoped, always-on operating instructions.

Bootstrap deliberately does not create tasks for top-level directories or estimate progress from the presence of tests, documentation, source files, or commits. Those proxies produce precise-looking values with no defensible relationship to actual acceptance.

## Review contract

New plans use schema version 2 and start with `reviewed: false`. Before applying a plan, the agent must:

1. Replace the placeholder root with the actual long-running goal and concrete acceptance criteria from the user and repository evidence.
2. Merge, split, remove, or rewrite explicit-marker task candidates as needed; confirm their status and leaf progress.
3. Inspect every background candidate, remove irrelevant or stale material, correct its summary, triggers, affected tasks, and source details, and change `confidence` from `unreviewed` to `reviewed`.
4. Set the plan-level `reviewed` field to `true` only after those judgments are complete.

Application is limited to an empty task and knowledge graph. The CLI validates task relationships, leaf progress, evidence presence, source containment, and exact quotes before writing. Accepted sources are copied to `.hypha/src/bootstrap/`, and their knowledge pages are published as `sourced` claims under `.hypha/know/bootstrap/`.

## Relationship to task and knowledge initialization

The task side follows task-forest's useful boundary: deterministic tooling prepares proposals, while an agent identifies meaningful task boundaries and asks for or relies on explicit user intent. The knowledge side follows the LLM Wiki pattern: preserve raw source material separately from maintained knowledge pages, with provenance connecting the two.

This makes bootstrap an initialization aid for genuinely long work, not an automatic project manager and not a command to run for ordinary one-session changes.
