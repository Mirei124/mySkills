# Draft Formats

Use the CLI prefix from SKILL.md. Drafts live in the target `.hypha/.drafts/` and support nested paths. YAML supports scalars, inline lists, and lists of mappings—not block scalars or arbitrary nesting.

## Update Existing Nodes

For ordinary observed conclusions use `record` instead of task-body editing; see [Conclusion records](records.md). Direct edits use `task edit ID --section NAME --body-file FILE` (whole section replacement). Choose a draft only for coordinated review or unresolved content:
```sh
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" task edit 0001 --draft
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" task edit 0001 --section Evidence --draft
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" knowledge edit know/offline-deployment --draft
```

Edit the returned draft, then run `advanced publish <draft-path>`. Full drafts preserve fields and body; section drafts replace only their named level-two section. Use full drafts for coordinated scope/evidence/history changes. Keep generated target, base_revision, and section fields; if the source changed, regenerate and reconcile rather than removing the revision guard. Knowledge edits retain their path when titles change.

Keep one authoritative Acceptance checklist:
```markdown
## Acceptance

- [x] CSV import passes fixture checks.
- [ ] XML import passes fixture checks.
- [ ] Interrupted imports resume without duplicates.

## Evidence

- CSV checks passed; cite the actual command and artifact.

## Change History

- Record the actual date: the user replaced JSON with XML because the customer's export format changed. JSON is cancelled; CSV evidence remains applicable; recovery remains required.
```

`show` derives remaining items. Counts are not progress or evidence; plain legacy acceptance text remains supported. Acceptance and Evidence must be non-empty before completion, and the agent verifies meaning. Next Step and Risks should add recovery value, not filler.

Legacy handwritten `kind: task-update` drafts with `id` remain supported: omitted metadata is preserved, but the entire body is replaced. Prefer generated guarded drafts. Applying unchanged reviewed content acknowledges direct-write history for supplied fields without erasing history. Use `advanced drafts --all` for state and target details, and `advanced discard ID` to retire a stale candidate without deletion. Publish accepts an exact draft path or its unique ID; do not guess a filename.

## Minimal User Knowledge

```markdown
---
kind: know
authority: user_explicit
agreement_quote: Customer Orion's records must not leave its isolated network.
when: Choosing deployment for customer Orion
review_when: Orion changes its data-transfer policy
---
# Orion deployment constraint
```

Use the smallest sufficient actual quote; body prose adds only missing rationale, exclusions, or context. Explicit statements need no reconfirmation; ambiguous interpretations remain drafts.

Supply origin, evidence, concrete `when`, and title. The CLI derives claim_kind; optional classifications never replace applicability. `affects: [0001]` links existing tasks only, triggers add useful aliases, and known review_when conditions should remain.

| Authority | Derived claim kind |
| --- | --- |
| user_explicit | agreement |
| user_confirmed | agreement |
| repository | sourced |
| external_source | sourced |
| agent_inference | inference |

Legacy explicit claim_kind remains supported; it must not contradict the authority. Agreement requires a user authority and agreement_quote. Inference requires anchors and an inference statement explaining premises and conclusion; do not promote it to user agreement.

## Source Evidence

Use `knowledge create --source <file>` to capture evidence while creating knowledge, or `advanced import <file>` to retain material without publishing knowledge. Do not duplicate facts already fully answered by current project files unless explicitly requested.

```markdown
---
kind: know
authority: repository
when: Reviewing the historical Orion deployment choice
evidence:
  - anchor: src/architecture.md#deployment
    quote: Customer environments have no network access.
---
# Historical deployment evidence
```

Use actual snapshot paths and exact quotes. Repeat CLI source/quote pairs for multiple sources. Anchors derive from evidence when omitted; source-derived inference requires resolvable premise anchors. Experimental observations instead use record, which does not claim source verification. Status defaults to active; supersession requires `status: superseded` and `superseded_by`. See [Conclusion records](records.md) for reviewed corrections and unverified source locators.

New knowledge uses its title to choose a path. Use `knowledge edit` for existing knowledge to retain identity. Search before creating: structural validation cannot determine semantic duplication.

## Minimal Handoff

When the task covers recovery, add no summary; otherwise save only missing temporary detail:

```markdown
---
kind: handoff
id: 0001
---
# Resume task 0001

Read task 0001 for current scope, acceptance, evidence, and knowledge links.

## Recovery Detail

- Cite the actual cursor/artifact path and whether it was verified.
```

Omit id if no task exists. Do not copy task state, transcripts, or secrets. Handoff/note drafts are non-publishable recovery data. Current task decisions override legacy summaries; reconcile only stale temporary instructions.

## Context Close Preparation

`context close` creates `.hypha/.drafts/context-close.json`. It is a small review record, not a copy of task bodies. Keep its generated `handoff_id`; select one `resume_task` when multiple active tasks are present; explain `no_task_reason` for a task-free handoff. Set each review to `saved` with existing task, knowledge, or handoff-draft references, or to `not_needed` with a reviewed reason. `pending` intentionally blocks finalization. A handoff draft may be referenced while unpublished and remains non-publishable recovery data.
