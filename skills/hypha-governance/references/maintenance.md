# Maintenance

Read only for bootstrap/import, migration, semantic follow-ups, or rejected publication. Source capture and copy behavior are described in [Conclusion records](records.md#source-snapshot-behavior).

## Migrate Existing Task Records

When moving from another task system, read [Migration review](migration.md). Preserve originals and account for every unfinished task, blocker, dependency, and todo. Completed history may be summarized; unfinished work needs a live task, named remaining acceptance, or evidence-backed cancellation/supersession. A historical table alone is not a destination.

Treat old percentages as historical reported values. Set current numeric progress only when current acceptance items justify it. Verify migration coverage separately from `check`: structural validation cannot prove that the source's unfinished scope survived.


## Execute Semantic CLI Hand-offs

`advanced bootstrap`, `check --audit`, and `advanced migrate` may print `AGENT FOLLOW-UP`. This means the command completed a mechanical first stage and the calling agent should continue its Instructions in the same turn whenever safely possible. `advanced import --suggest` only captures a source and lists existing knowledge candidates; it does not create knowledge or emit that protocol. Continue the authorized semantic work until:

- evidence from nodes, sources, code, or user confirmation supports a validated change;
- a candidate is confirmed unrelated and recorded with `advanced dismiss`; or
- evidence is insufficient, so it is retained with `advanced defer` and uncertainty is reported.

The CLI supplies candidates, paths, status, and constraints; the agent owns classification, relationship selection, acceptance review, deviation detection, and user-confirmation decisions. Never treat candidates as facts or merely print the prompt and claim completion.

Exhaust safe, authorized work before asking for confirmation. Ask only when a missing decision would materially change formal task/knowledge state or requires new authority. If confirmation concerns optional knowledge capture rather than the user's primary request, leave a draft or defer the candidate, report it briefly, and still finish the primary work. A deferred audit candidate remains visible but does not emit another follow-up, so do not rerun `check --audit` merely to revisit it.

## Handle CLI Rejections Without Stalling

A nonzero CLI exit is a validation result, not proof that the user's work is blocked. Read the error, inspect current nodes, and perform every safe deterministic correction available. For example, update leaves before completing a parent, choose `task parent` versus `task needs` from established task semantics, or keep uncertain knowledge as a draft. Ask the user only when the remaining choice is materially ambiguous and would change formal state. Do not mark a runtime goal blocked merely because `task create`, `advanced publish`, `task done`, `check`, or `context close` rejected invalid state.

For an unknown command or argument, inspect the bundled CLI's relevant `--help`; there is no old-command translation layer. Distinguish syntax errors from invalid node state. Read-only queries do not need write permission, but source capture, publication, and `check` do; a copying fallback does not bypass filesystem permissions.

For a real handoff, `context close` only prepares `.hypha/.drafts/context-close.json`. Review and save this turn's missing task, knowledge, and recovery information before `context close --finalize`. Finalization records a handoff and leaves each selected task in its existing status; it is not a signal to finish active work or the current turn. Finalize failures preserve the preparation and keep context open. Do not default either review to `not_needed`, and do not create false records to satisfy checks. A retry may safely finish an interrupted close when the handoff record was written before its linked close marker.

An unmanaged-write notice with a successful check is historical audit information, not a validation failure. Inspect relevant content and continue the primary task. To acknowledge it, publish the same body with actually reviewed metadata; this appends a review event without erasing direct-write history. Do not alter whitespace, repeatedly check, rewrite audit logs, or delete drafts solely to clear a notice. CLI validation does not replace semantic review.
