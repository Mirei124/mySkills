# Migration Review

Use this protocol when the user authorizes moving existing task records into Hypha. `advanced migrate` handles legacy Hypha agreements, not arbitrary imports; `advanced bootstrap` examines repository evidence and does not preserve a source task graph.

1. Inspect source tasks, outstanding todos, dependencies, blockers, deviations, and handoff records. Keep the originals as history. Identify the source's statuses and what they mean before mapping them.
2. Prepare a coverage table before publishing. Each unfinished source item needs one explicit disposition and supporting evidence. Preserve acceptance boundaries, not just titles or percentages.
3. Reuse existing Hypha tasks. Create a child only for independently acceptable or schedulable work. Merge smaller unfinished items into named remaining acceptance items on a live destination task.
4. Save reviewed changes through direct commands, or publish guarded drafts for coordinated changes, then compare destination bodies and relationships with the coverage table. Check every unfinished source ID and todo; `check` proves structure only.
5. Retain the coverage table as migration evidence with source paths and destination links. State unresolved mappings explicitly; leave uncertain items pending rather than silently archiving or cancelling them. Finish all unambiguous migration work before asking about a material scope decision.

## Coverage Example

| Source | Source state | Destination / disposition | Remaining scope or evidence |
| --- | --- | --- | --- |
| OLD-1 | in_progress, reported 90% | Existing live task `[[intent/0001]]` | Verify both import sources; old percentage is historical only. |
| OLD-7 | in_progress, reported 95% | `[[intent/0001]]`, Remaining Acceptance: verify second-source pagination | Outstanding pagination check preserved explicitly. |
| OLD-3 | done | Historical summary with source path | Original acceptance/evidence retained for lookup. |
| OLD-8 | blocked by OLD-7 | Live task `[[intent/0002]]`, needs 0001 | Preserve the actual blocking condition after merging OLD-7 into 0001. |

A history row saying only "OLD-7 was 95% complete" is insufficient. Cancellation or supersession needs evidence or user authorization; a newer task is not proof older unfinished scope disappeared. Preserve an independently schedulable blocker rather than obscuring it through a merge.

Do not transfer old percentages directly into current `progress`. Record them as dated source reports in migration evidence; use status and explicit remaining acceptance until current acceptance items support a percentage. Current parent progress remains derived from live leaves.

Use `sourced` knowledge and a source snapshot for facts taken from the old records, `agreement` for explicit user migration decisions, and `inference` for new conclusions with supporting premises or observations and applicable review conditions. Capture a local source with `advanced import FILE` or directly with `knowledge create --source FILE --quote TEXT`; `record --reference` alone does not preserve the source. See [Source snapshot behavior](records.md#source-snapshot-behavior). Preserve concise operating rules in AGENTS.md and rationale/history in Hypha.
