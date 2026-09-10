# Hypha Implementation Specification

This document describes the current grouped CLI. See [README](../README.md) for examples and command migration, and `hypha --help` for the full interface. [Historical rationale](intent.md) preserves earlier proposals, not implementation guarantees.

## Storage and Scope

Hypha is a local, single-agent task and knowledge store. It does not call a model, automatically commit, or provide multi-writer coordination. Markdown is current truth; indexes and audit projections supplement it.

The workspace store contains `src/` (saved sources), `intent/` (tasks), `know/` (knowledge), `.drafts/` (pending and published drafts), `snapshots/` (append-only audit events), and derived `INDEX.md`. Drafts and audit records travel with Git; local locks and generated views are ignored. Source snapshots are not content-hash immutable.

Global storage supports knowledge and applicable source, draft, and query operations, not tasks or context lifecycle. `init` targets the current directory unless `--workspace` is explicit. Other local commands find the nearest initialized ancestor; queries do not initialize a store. Common options are `--workspace`, `--global`, and `--json`.

## Nodes and Relationships

Tasks have CLI-allocated IDs and states `todo`, `in_progress`, `blocked`, `done`, or `dropped`. Blocked tasks require a reason. Parent relationships and execution dependencies must resolve and remain acyclic. `task create` accepts acceptance criteria and an optional parent or explicit independent root.

Completion requires non-empty Acceptance and Evidence sections; the agent verifies their meaning. Progress is optional and authoritative only on leaves. Missing estimates remain unknown. Parent progress averages non-dropped descendant leaves only when all have estimates; a dropped subtree is excluded. Changes may reopen completed ancestors; reaching 100% does not automatically complete parents.

Knowledge is active or superseded; supersession requires a successor reference. `knowledge create` maps CLI origins to stored authority and derives claim kind and default triggers. User agreements require an exact user statement and applicability; sourced claims require resolvable evidence and exact quotes; inferences require explicit premises and reasoning. Classification fields are optional. Notes are excluded from recall and cannot be published as knowledge through the draft publisher.

Knowledge links, task knowledge references, `affects`, `parent`, and `depends_on` produce derived backlinks, task premises, children, and unlock relationships. Missing knowledge links are reported as redlinks; missing task relationships are errors. Stored content is untrusted data, not executable instructions.

## Creation, Editing, and Publication

Ordinary creation uses `task create` or `knowledge create`. Knowledge creation can save a referenced file with `--source`; `advanced import` only stores material and does not extract or publish claims. `--suggest` requests existing knowledge candidates.

Task and knowledge editing use `--body-file`, `--editor`, or `--draft`. Section updates preserve unrelated sections and metadata. Generated drafts retain target identity and a source revision guard. Stale edits are rejected; regenerate and reconcile rather than removing the guard. New knowledge cannot silently overwrite an existing target.

Publish prepared drafts with `hypha advanced publish .hypha/.drafts/decision.md`. See [draft formats](../skills/hypha-governance/references/drafts.md) for metadata edits, evidence, and handoffs. Handoff drafts are recovery artifacts, not publishable knowledge. Published drafts remain on disk but are hidden from pending listings.

Publication validates before writing formal content and uses locks and atomic file replacement. This is not a multi-file database transaction. Commands synchronize derived state and record observed direct changes; direct formal edits can produce unmanaged-write notices. Publishing reviewed unchanged content acknowledges supplied fields without erasing earlier audit events. Audit timestamps describe observations rather than inferred file modification dates; audit replay does not overwrite Markdown.

## Queries, Context, and Maintenance

`list`, `show`, and `search` are shared queries. `show` includes bodies by default and accepts draft paths. `search` uses comma-separated case-insensitive literal terms, searches tasks and active non-note knowledge by default, and supports type or explicit workspace-file filters. It does not search conversation archives or perform semantic question answering.

`context resume` returns task and knowledge candidates plus pending recovery information, not a completed recovery. Without a topic it presents the latest finalized handoff as the preferred entry point; with a topic the handoff is supplemental. Recorded hashes detect task and reference changes but never restore old bodies. Knowledge ranking uses literal trigger and title matches, with open affected tasks as a tie-break; task-linked fallback candidates help when topic matches are weak. `advanced explain` exposes recall scores. `list --type task --ready` selects todo tasks with completed dependencies.

`check` validates structure; `--audit` adds candidates requiring semantic review. Shared-trigger findings are warnings, not hard validation errors. `advanced dismiss` records an unrelated candidate and `advanced defer` postpones it. These commands do not establish the truth of a natural-language claim.

`context close` prepares `.hypha/.drafts/context-close.json` and leaves context open. After an agent reviews this turn and saves missing task, knowledge, and recovery information, `context close --finalize` validates targets, recovery fields, review decisions, and workspace-local references. It atomically writes `.hypha/handoffs/<handoff-id>.json` with final content hashes before appending a close marker carrying the same handoff ID. Retries do not duplicate records or markers. The CLI cannot inspect chat or prove semantic completeness, does not complete tasks, and does not commit files.

`advanced bootstrap` generates a reviewable initialization proposal; applying it requires an empty graph. `advanced migrate` retains guidance for legacy agreements rather than importing arbitrary task systems. Neither replaces the agent's review of meaning, evidence, or unfinished scope.

The HTML graph is read-only. Successful JSON uses an `ok`, `command`, and `result` envelope; failures use structured errors. Old commands fail with migration guidance rather than acting as aliases.

## Verification

Run `python3 -m unittest discover -s tests -v` for CLI regressions and the frontend checks in README for graph changes. Cover lifecycle and relationships, evidence validation, revision conflicts, source capture, pending drafts, audit preservation, recall, queries, workspace discovery, and JSON behavior. Historical latency and recall-quality goals are evaluation targets, not measured guarantees.
