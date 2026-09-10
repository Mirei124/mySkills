# Migration Review

Use only for authorized migration of existing task records. `advanced migrate` handles legacy Hypha agreements, not arbitrary imports; bootstrap examines repository evidence, not a source task graph.

1. Inspect source statuses, tasks, todos, blockers, dependencies, deviations, and handoffs; preserve originals.
2. Prepare a coverage table: every unfinished item needs an explicit destination/disposition and evidence, preserving acceptance—not just titles or percentages.
3. Reuse existing tasks. Split independently acceptable/schedulable work; merge smaller items into named remaining acceptance on live tasks.
4. Save reviewed changes directly or through coordinated guarded drafts. Compare destination bodies/relations against every unfinished source ID and todo; `check` proves structure, not coverage.
5. Retain the table with source paths/destination links. Leave uncertain mappings pending, never silently archived/cancelled. Finish unambiguous work before asking about material choices.

## Coverage Example

| Source | State | Destination / evidence |
| --- | --- | --- |
| OLD-1 | in_progress, reported 90% | Existing `[[intent/0001]]`: verify both import sources. |
| OLD-7 | in_progress, reported 95% | 0001 remaining acceptance: second-source pagination. |
| OLD-3 | done | Historical summary retaining source acceptance/evidence. |
| OLD-8 | blocked by OLD-7 | Live `[[intent/0002]]` needs 0001; retain blocking condition after the merge. |

"OLD-7 was 95% complete" alone preserves no unfinished work. Cancellation/supersession requires evidence or user authority; newer tasks do not automatically replace older scope. Do not hide independently schedulable blockers through merging.

Keep old percentages as dated source reports, not current progress. Use status/remaining acceptance until current evidence justifies a number; parent progress derives from live leaves.

Use sourced knowledge for quoted source facts, agreement for explicit user decisions, and inference for conclusions with premises/observations and review conditions. `advanced import FILE` or `knowledge create --source FILE --quote TEXT` preserves a snapshot; `record --reference` alone does not. See [Source snapshots](records.md#source-snapshot-behavior). Operating rules belong in AGENTS.md; missing rationale/history belongs in Hypha.
