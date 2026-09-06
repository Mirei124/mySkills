# Draft Formats

Use the CLI prefix established in SKILL.md. Replace illustrative IDs and statements with verified project content. Keep all drafts inside the target workspace's `.hypha/.drafts/`; subdirectories are supported and included in recovery listings. Hypha uses a small YAML subset: scalar fields, inline lists, and lists of mappings. Avoid block scalars and arbitrary nested YAML.

## Task Update

Read the existing `.hypha/intent/<id>-<slug>.md` first. Copy its complete body, preserving sections and links, then update the intended content. Save as `.hypha/.drafts/task-update.md`:

```markdown
---
kind: task-update
id: 0001
---
# Existing task title

## Acceptance

- Imported records are deduplicated and verified.
- The remaining source is imported and checked.

## Evidence

- First batch verified by the project's import verification command; cite its actual result and artifact here.

## Remaining Acceptance

- The second source still needs import and verification.

## Next Step

- Resume at the saved source cursor; cite the actual file and cursor.

## Risks

- Source pagination has not yet been verified for the second source.
```

The example headings are illustrative, not new mandatory parser fields. `Acceptance` and `Evidence` must be non-empty before completion. `apply` merges supplied task metadata into the existing node but **replaces its entire body**, including the title. Omitting a body section deletes that section; omitting metadata preserves it. Keep lifecycle changes in the normal status/relationship commands. Do not paste the displayed metadata or CLI labels from `show --body` into the body.

```sh
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" apply "$HYPHA_WORKSPACE/.hypha/.drafts/task-update.md"
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" show 0001 --body
```

Publishing an unchanged reviewed body acknowledges a previous direct body write without altering its text. Only explicitly supplied metadata fields are also acknowledged; historical direct-write events remain in snapshots.

## Knowledge Publication

Save a user-authorized statement as `.hypha/.drafts/knowledge.md`:

```markdown
---
kind: know
claim_kind: agreement
knowledge_kind: rationale
scope: project
authority: user_explicit
agreement_quote: The customer environment has no network access.
when: Choosing deployment architecture or dependencies
triggers: [offline, deployment, dependencies]
affects: [0001]
---
# Offline deployment rationale

The customer environment has no network access, so dependency choices must support offline operation.
```

Use the user's actual smallest sufficient quote; remove `affects` if no related task exists. Do not invent a task just to publish knowledge. Keep short operating rules in AGENTS.md and avoid duplicating them here.

For repository or external facts, run `ingest`, then use a complete sourced draft such as:

```markdown
---
kind: know
claim_kind: sourced
knowledge_kind: constraint
scope: project
authority: repository
when: Choosing deployment architecture or dependencies
triggers: [offline, deployment, dependencies]
affects: [0001]
anchors: [src/architecture.md#deployment]
evidence:
  - anchor: src/architecture.md#deployment
    quote: The customer environment has no network access.
---
# Documented deployment constraint

The deployment document records that customer environments have no network access.
```

Use actual snapshot paths and exact source quotes. `authority` accepts only the following values; put source-specific descriptions in the body or evidence instead of inventing new authority strings:

| Value | Origin |
| --- | --- |
| `user_explicit` | The user directly stated or authorized this claim. |
| `user_confirmed` | The user confirmed a proposed interpretation. |
| `repository` | Repository documents or retained project records support the claim. |
| `external_source` | An external source supports the claim. |
| `agent_inference` | The agent derives a conclusion from stated premises. |

`agreement` requires `user_explicit` or `user_confirmed`. For a derived conclusion, use `claim_kind: inference`, `authority: agent_inference`, source `anchors`, and an `inference` field describing premises and conclusion; state invalidation conditions in the body. Summarizing a source is not by itself a reason to label its facts as inference.

```sh
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" apply "$HYPHA_WORKSPACE/.hypha/.drafts/knowledge.md"
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" lint
```

Knowledge publication uses the title to determine its path and replaces the existing node at that path. Read existing content before updating; keep the title stable when updating that node. Preserve conflicting history with supersession instead of silently overwriting it.

## Handoff Draft

Save as `.hypha/.drafts/handoff.md` when context is ending and a recovery record is needed:

```markdown
---
kind: handoff
id: 0001
---
# Resume the existing import task

## Goal and Constraints

- Cite the task and applicable knowledge; preserve constraints needed for the next action.

## Verified Results

- Cite completed checks and saved artifacts, separating verified results from unverified reports.

## Remaining Acceptance

- State the unfinished observable outcomes.

## Next Step

- Give one concrete action and the file, cursor, or command needed to resume.

## Risks

- Record unresolved risks, or explicitly state that none are known.
```

This is recovery-only data, not a published knowledge claim. Read it on resume and do not run `apply` on `kind: handoff` or `kind: note` drafts. Omit `id` if there is no task. Do not copy full transcripts or secrets. `drafts` and `boot` expose pending drafts including nested paths; already applied task/knowledge drafts are hidden automatically and need no cleanup.
