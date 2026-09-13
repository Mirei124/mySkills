# Maintenance

Read for bootstrap/import, migration, audits, or rejected writes. See [Source snapshots](records.md#source-snapshot-behavior) for copying and [Migration review](migration.md) before moving another system's task records.

## Semantic Follow-ups

For local maintenance, scope audit to `check --audit --task ID` or `--subtree ID` (repeatable, combined by union). `--changed [REF]` restricts candidates to those touching a task or knowledge node changed since the Git commit (HEAD by default), including staged, unstaged, and untracked nodes. When combined, task scope and changed scope intersect. A Git repository and resolvable commit are required. Scope affects audit candidates, not whole-graph structural validation or completeness warnings.

Default audit includes isolated active tasks and missing links with at least two shared non-generic terms; this is a heuristic, not measured confidence. Superseded knowledge is excluded. `--all-candidates` includes weaker matches; `--limit N` changes the default cap of 20. Only displayed candidates request follow-up, and existing dismiss/defer IDs remain stable across scopes. Do not broaden an audit merely to resolve unrelated work.

`advanced bootstrap`, `check --audit`, and `advanced migrate` may emit `AGENT FOLLOW-UP`: a mechanical stage finished, not the semantic work. Continue safely within the authorized scope until evidence supports a validated change, `advanced dismiss` records an unrelated candidate, or `advanced defer` retains uncertainty.

`advanced import --suggest` only captures a source and lists existing candidates; it neither creates knowledge nor emits that protocol. Candidates are not facts. The agent still owns classification, relationships, acceptance, deviations, and authority checks; printing a follow-up is not completion.

Exhaust safe authorized work before asking about materially ambiguous decisions or new authority. Optional capture must not stall the primary task: leave a draft/deferred candidate and report uncertainty. Deferred audit candidates remain visible without another follow-up; do not repeatedly run `check --audit` merely to revisit them.

## Rejections And Permissions

Distinguish syntax, invalid state, and permissions. For unknown commands/arguments use current `--help`; no compatibility translation exists. Inspect nodes and make safe deterministic corrections, such as updating leaves before completing parents or choosing `task parent` versus `task needs` from established semantics. A rejected operation alone does not justify declaring the task/runtime goal blocked.

Queries are read-only; source capture, publication, and `check` require writes. Copying fallback does not bypass permissions. For interrupted record writes, follow [record recovery](records.md#add-evidence-or-correct-a-conclusion).

## Handoff And Audit Recovery

Follow SKILL.md's handoff sequence. Finalize failures retain preparation and keep context open. Do not default reviews or fabricate records. Retrying can finish an interrupted close whose handoff record exists but close marker does not.

An unmanaged-write notice after a successful check is historical audit information, not failure. Inspect the relevant content and continue. To acknowledge reviewed content, publish its unchanged body with actually reviewed metadata; this records review without erasing history. Do not tweak whitespace, repeat checks, rewrite audit logs, or delete drafts just to clear notices. Structural validation cannot establish semantic completeness.
