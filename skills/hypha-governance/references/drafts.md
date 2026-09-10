# Draft Formats

Use SKILL.md's CLI prefix. Drafts live under the project's `.hypha/.drafts/`, including nested paths. YAML supports scalars, inline lists, and mapping lists—not block scalars or arbitrary nesting.

## Update Existing Nodes

Prefer `record` for observed conclusions and `task edit ID --section NAME --body-file FILE` for direct section replacement. Use drafts for coordinated review/unresolved content:
```sh
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" task edit 0001 --draft
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" task edit 0001 --section Evidence --draft
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" knowledge edit know/offline-deployment --draft
```

Edit, then `advanced publish <draft-path-or-ID>`. Full drafts preserve fields/body; section drafts replace only the named level-two section. Keep generated target/base_revision/section; reconcile changed sources, never remove guards. Knowledge edits retain paths even when titles change.

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

`show` derives remaining items; counts are neither progress nor evidence. Plain acceptance text remains supported. Completion requires non-empty Acceptance/Evidence and actual verification. Add Next Step/Risks only for recovery value.

Legacy `kind: task-update` plus `id` preserves omitted metadata but replaces the entire body; prefer generated guards. Publishing unchanged reviewed content acknowledges supplied fields without erasing direct-write history. See [Draft recovery](records.md#draft-recovery-is-exceptional) for IDs, states, and discard.

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

Quote only sufficient actual words; body adds missing rationale/exclusions/context. No reconfirmation for explicit statements; keep ambiguous interpretations as drafts.

Supply authority/evidence, concrete `when`, and title. Claim kind is derived; classification never replaces applicability. `affects: [0001]` links existing tasks, triggers supply aliases, and `review_when` preserves known invalidation.

| Authority | Derived claim kind |
| --- | --- |
| user_explicit | agreement |
| user_confirmed | agreement |
| repository | sourced |
| external_source | sourced |
| agent_inference | inference |

Explicit claim_kind must match authority. Agreement needs user authority/agreement_quote; source inference needs resolvable anchors and reasoning. `record` instead uses observations; neither inference form implies user agreement.

## Source Evidence

`knowledge create --source FILE` captures sources with knowledge; `advanced import FILE` captures material only. Both save full files, unlike `record --reference`. See [Source snapshots](records.md#source-snapshot-behavior) for CoW/fallback, reuse, and failure recovery. Avoid duplicating file-recoverable facts unless requested.

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

Use real snapshot paths/exact quotes; repeat source/quote pairs for multiple sources. Evidence supplies omitted anchors. Status defaults to active; supersession needs `status: superseded` and `superseded_by`. See [Conclusion records](records.md) for corrections.

Search before creating: validation cannot detect semantic duplicates. New titles select paths; `knowledge edit` preserves identity.

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

Omit id without a task. Handoff/note drafts cannot publish as knowledge. Copy no task state, transcripts, or secrets; current task decisions override old summaries.

## Context Close Preparation

`context close` prepares `.hypha/.drafts/context-close.json`. Keep generated `handoff_id`; choose one `resume_task` among multiple active tasks; explain `no_task_reason` without tasks. Both reviews need `saved` plus existing task/knowledge/handoff-draft references, or `not_needed` plus a reviewed reason. Use exact existing task-file paths including `.md` in review references. `pending` blocks finalization. Unpublished handoff drafts are valid recovery references, not publishable knowledge.
