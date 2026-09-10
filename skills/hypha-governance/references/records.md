# Conclusion Records

Ordinary capture uses `record "Conclusion" --evidence "Actual observation and its limits" --task ID`. Repeat evidence and task flags when necessary. Standalone knowledge instead requires concrete `--when`; the CLI never guesses the current task. `--reference` stores a locator, not verified source content. Conditions and disposition are optional; do not manufacture values to fill a form.

The resulting knowledge is explicitly agent inference backed by observations. For example, a primitive probe passing and an integrated regression failing supports investigation of integration, not a universal claim that the primitive is broken. An overlap design deferred from profiler evidence is not a failed implementation. Preserve these limits in the evidence sentence rather than maintaining another stage taxonomy.

The tool adds task Evidence references, not a second copy of the observations. It never marks tasks complete or deletes their old paragraphs. Optional cleanup can later use a guarded task edit after verifying that the knowledge preserves the useful content. Logs and source files remain the detailed artifacts; do not turn Hypha into another transcript store.

## Add Evidence Or Correct A Conclusion

Read `show know/path`; it includes the current revision.

- Add observations to the same recorded conclusion with `record "Existing exact conclusion" --update know/path --revision HASH --evidence "New observation"`. Existing observations and body sections survive. Task links default to the existing record's links. Explicit `--task` values replace that link set. A disposition change records history.
- For a changed conclusion, use `record "New scoped conclusion" --supersedes know/old --revision HASH --because "Why the previous interpretation no longer governs" --evidence "New observation"`. The tool retains the old node/evidence, links its replacement, and adds correction references to the old and new related tasks. This is an explicit review action, not automatic semantic matching.
- For sourced or user-attributed knowledge, use `knowledge edit` to edit in place; record updates cannot silently downgrade its origin. A correction through record remains agent inference, even when it replaces a user/source claim; the agent must have adequate evidence or authorization for the correction and must not present it as user confirmation.

Stale revisions reject the entire record operation. Reread and reconcile; do not guess a new hash. A failed record write rolls back knowledge, task references, index, and audit. An interrupted transaction is hidden from normal reads until the writer finishes or a subsequent write/check restores the saved pre-write state. `check` requires write permission for recovery; ordinary reads never request it automatically.

## Multiple Sources

For checked excerpts, repeat local `--source` and matching `--quote` in the same order:

```sh
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" knowledge create "Version-specific API evidence" --origin repository --when "Building the specified target version" --source docs/api-snapshot.txt --quote "Exact documented statement" --source src/api.h --quote "Exact declaration"
```

Every excerpt is checked before sources are copied. Each source has its own evidence entry. `--source` does not download URLs; retain a local snapshot when exact-source validation is needed. For a mixed-source synthesis, use record observations and locators and state what each source supports. Do not silently label all observations as independently verified or elevate local implementation evidence into a universal API contract.

For a navigation list only, record that limited purpose explicitly, e.g. `record "API references to inspect" --when "Investigating target compatibility" --evidence "These are candidate links; their claims have not been verified" --reference https://example.org/api`. This stores useful provenance without pretending it is a source-backed factual conclusion. Do not use it as a workaround for publishing an unsupported fact.

## Draft Recovery Is Exceptional

Direct record/create/body-file operations do not require manual draft management. `advanced drafts --all` shows pending, stale, published, and discarded states. Publish accepts the displayed draft ID (with or without `.md`) or exact path. Use `advanced discard ID` to retire a stale candidate without deleting its file; changing a discarded draft's content makes it pending again. Published and discarded content is hidden from normal recovery lists. Revision guards still prevent stale publication.

Task/knowledge full-body editing remains available for coordinated changes; generated draft targets and revision guards are not user-authored fields. Do not pick a draft by directory listing order or remove a guard to resolve a conflict.
