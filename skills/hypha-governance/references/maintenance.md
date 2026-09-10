# Maintenance

Read only for migration, semantic follow-ups, or rejected publication.

## Migrate Existing Task Records

When moving from another task system, read [Migration review](migration.md) before publishing. Preserve the original records and account for every unfinished task, blocker, dependency, and outstanding todo. Completed history can be summarized. Unfinished work needs an explicit destination: a live Hypha task, a specific remaining acceptance item, or an evidence-backed cancellation/supersession. An entry in a historical table alone is not a destination. Reuse task boundaries when appropriate; do not copy every historical step into a new node.

Treat old percentages as historical reported values. Set current numeric progress only when current acceptance items justify it. Verify migration coverage separately from `check`: structural validation cannot prove that the source's unfinished scope survived.


## Execute Semantic CLI Hand-offs

`advanced bootstrap`, `advanced import --suggest`, `check --audit`, and `advanced migrate` may print `AGENT FOLLOW-UP`. This means the command completed a mechanical first stage and the calling agent should continue its Instructions in the same turn whenever safely possible. It is not, by itself, a reason to yield, ask the user a question, or mark work blocked. Continue until:

- evidence from nodes, sources, code, or user confirmation supports a validated change;
- a candidate is confirmed unrelated and recorded with `advanced dismiss`; or
- evidence is insufficient, so it is retained with `advanced defer` and uncertainty is reported.

The CLI supplies candidates, paths, status, and constraints. The agent owns summarization, support/refinement/contradiction classification, relationship selection, acceptance review, deviation detection, and deciding when user confirmation is required. Never treat prompt candidates as facts or merely print the prompt and claim completion.

Exhaust safe, authorized work before asking for confirmation. Ask only when a missing decision would materially change formal task/knowledge state or requires new authority. If confirmation concerns optional knowledge capture rather than the user's primary request, leave a draft or defer the candidate, report it briefly, and still finish the primary work. A deferred audit candidate remains visible but does not emit another follow-up, so do not rerun `check --audit` merely to revisit it.

## Handle CLI Rejections Without Stalling

A nonzero CLI exit is a validation result, not proof that the user's work is blocked. Read the error, inspect current nodes, and perform every safe deterministic correction available. For example, update leaves before completing a parent, choose `task parent` versus `task needs` from established task semantics, or keep uncertain knowledge as a draft. Ask the user only when the remaining choice is materially ambiguous and would change formal state. Do not mark a runtime goal blocked merely because `task create`, `advanced publish`, `task done`, `check`, or `context close` rejected invalid state.

For a real handoff, `context close` only prepares `.hypha/.drafts/context-close.json`. Review and save this turn's missing task, knowledge, and recovery information before `context close --finalize`. Finalize failures preserve the preparation and keep context open. Do not default either review to `not_needed`, and do not create false records to satisfy checks. A retry may safely finish an interrupted close when the handoff record was written before its linked close marker.

An unmanaged-write notice with a successful check is historical audit information, not a validation failure. Inspect relevant content when needed and continue the primary task. To acknowledge reviewed content, publish a draft containing the same body and the metadata fields actually reviewed. Even with unchanged content, publication appends a review event for those fields while preserving the original direct-write history; omitted metadata is not acknowledged. Do not add/remove whitespace, repeatedly check, rewrite audit logs, or delete drafts solely to clear a notice. CLI validation does not replace semantic review.
