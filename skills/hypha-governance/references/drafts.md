# Draft Formats

Use the CLI prefix from SKILL.md. Drafts live under the target workspace's `.hypha/.drafts/`; nested paths are supported. The small YAML subset supports scalars, inline lists, and lists of mappings, not block scalars or arbitrary nesting.

## Update Existing Nodes

Choose one:
```sh
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" edit 0001
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" edit 0001 --section Evidence
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" edit know/offline-deployment
```

Edit the returned draft file, then run `advanced publish <draft-path>`. Full drafts preserve all fields and the body automatically. Section drafts replace only the named level-two section. Use a full draft for coordinated scope/evidence/history changes. Keep generated target, base_revision, and section fields unchanged. If the source changed, regenerate and reconcile; do not remove the revision guard. Knowledge edits retain their path even when the title changes.

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

`show` derives remaining unchecked items. Counts are not work percentages or evidence. Plain legacy acceptance text remains supported. Acceptance and Evidence must be non-empty before completion; the agent verifies meaning. Optional Next Step and Risks sections should add useful information, not filler.

Legacy handwritten `kind: task-update` drafts with `id` remain supported: omitted metadata is preserved, but the entire body is replaced. Prefer generated guarded drafts. Applying unchanged reviewed content acknowledges direct-write history for supplied fields without erasing history.

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

Use the actual smallest sufficient quote. The quote already supplies the answer; body prose adds only missing rationale, exclusions, or context. Explicit statements need no second confirmation; ambiguous interpretations remain drafts until confirmed.

Supply origin and evidence, concrete applicability (`when`), and a title. The CLI derives claim_kind from authority when omitted. Optional knowledge_kind and coarse scope classifications do not replace concrete applicability. Optional `affects: [0001]` links existing tasks; do not invent a task. Optional triggers add useful aliases to automatically derived literal keywords. Preserve meaningful review_when conditions when known.

| Authority | Derived claim kind |
| --- | --- |
| user_explicit | agreement |
| user_confirmed | agreement |
| repository | sourced |
| external_source | sourced |
| agent_inference | inference |

Legacy explicit claim_kind remains supported; it must not contradict the authority. Agreement requires a user authority and agreement_quote. Inference requires anchors and an inference statement explaining premises and conclusion; do not promote it to user agreement.

## Source Evidence

Use ingest to retain relevant sources when needed. Do not duplicate facts already fully answered by current project files unless explicitly requested.

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

Use actual snapshot paths and exact quotes. Anchors are derived from evidence when omitted; inference still needs explicit premise anchors. Status defaults to active. Superseded knowledge requires status: superseded and superseded_by; preserve conflicting history rather than silently overwriting it.

New knowledge uses its title to choose a path. Use edit for existing knowledge to retain identity. Search before creating: structural validation cannot determine semantic duplication.

## Minimal Handoff

When the task covers recovery, no extra summary is needed. Otherwise save only missing temporary information:

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

Omit id if no task exists. Do not copy task state, transcripts, or secrets. Handoff/note drafts are recovery data and cannot be applied as knowledge. Pending drafts appear in drafts and boot; applied drafts are hidden automatically. Current task decisions override legacy handoff summaries. Keep history in the task and reconcile only temporary instructions that became stale.
