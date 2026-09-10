# Conclusion Records

Use `record "Conclusion" --evidence "Observation and limits" --task ID`; repeat evidence/task flags as needed, or supply concrete `--when` for standalone knowledge. The CLI never guesses a task. Conditions/disposition are optional; do not invent form values.

Observations support agent inference, not automatic proof. A passing probe plus failing integration does not invalidate the primitive; profiler-based deferral is not a failed implementation. Keep these limits in prose. Task Evidence receives brief links, not copied observations or completed acceptance. Old paragraphs remain; clean them only through guarded edits after checking that knowledge preserves their useful content.

## Add Evidence Or Correct A Conclusion

First `show know/path` for its revision.

- **Same conclusion:** `record "Exact existing conclusion" --update know/path --revision HASH --evidence "New observation"`. Preserves body/observations; task links default to existing links, while explicit `--task` values replace that set. Disposition changes record history.
- **Changed conclusion:** `record "New scoped conclusion" --supersedes know/old --revision HASH --because "Correction reason" --evidence "New observation"`. Retains old knowledge/evidence and adds replacement links/correction references to old and new related tasks; no automatic semantic supersession.
- **User/sourced knowledge:** edit in place with `knowledge edit`; `record --update` cannot downgrade origin. Superseding such knowledge through record still produces agent inference and requires adequate evidence/authority, not invented user confirmation.

Stale revisions reject the operation: reread/reconcile, never guess hashes. Failed record writes roll back knowledge, task links, index, and audit. Reads refuse interrupted transactions until the writer finishes or a subsequent write/`check` restores pre-write state. Recovery needs write permission; reads do not request it automatically.

## Multiple Sources

Repeat equal numbers of local sources and exact quotes in matching order:

```sh
python3 "$HYPHA_CLI" --workspace "$HYPHA_WORKSPACE" knowledge create "Version-specific API evidence" --origin repository --when "Building the target version" --source docs/api.txt --quote "Exact documented statement" --source src/api.h --quote "Exact declaration"
```

Each source has separate evidence. `--source` cannot download URLs. For mixed-source synthesis, record observations/locators and say what each supports; local implementation evidence is not a universal API contract.

Navigation-only records must state the limit, e.g. `record "API references to inspect" --when "Checking compatibility" --evidence "Candidate links, claims unverified" --reference https://example.org/api`. Never use unverified locators to bypass evidence requirements for factual claims.

## Source Snapshot Behavior

| Operation | Capture |
| --- | --- |
| `knowledge create --origin repository/external --source FILE --quote TEXT` | Complete files under `.hypha/src/`, even with `--draft`; all quote checks precede copying. Later publication failure retains drafts/sources. |
| `advanced import FILE` | File under `.hypha/src/`, no knowledge. `--suggest` adds existing candidates only. |
| `advanced bootstrap --apply PLAN` | Reviewed knowledge sources first in temporary validation storage, then `.hypha/src/bootstrap/<relative-path>`. Dry runs do not copy. |

Import/create reuse same-name, same-content snapshots; changed content gets a hash-suffixed filename. Different filenames are not content-deduplicated. Bootstrap uses its relative-path layout.

Copies prefer Linux reflink/CoW, falling back to `shutil.copy2` with metadata. No hard links: original-file changes must not alter evidence. Filesystem/platform support varies; no extra flag is needed, but do not claim reflink success or guaranteed space savings.

`record --reference` neither copies files nor fetches URLs. `--body-file` embeds text, not a source snapshot. Queries, ordinary draft publication, and user/inference knowledge creation do not capture external files. Explicitly import artifacts when durable content is needed; avoid large/sensitive captures merely for pointers.

## Draft Recovery Is Exceptional

Direct record/create/body-file operations need no manual drafts. `advanced drafts --all` shows pending/stale/published/discarded states. Publish accepts the displayed unique ID, optional `.md`, or exact path. `advanced discard ID` retains the file but hides unchanged content from recovery; editing makes it pending again. Published content is also hidden.

Use [guarded drafts](drafts.md) for coordinated changes. Never pick by listing order, invent target/revision fields, or remove guards to resolve conflicts.
