# Recovery Selection

The current `context resume` returns candidates, not hydrated bodies. Choose the current task and applicable durable decisions, then batch independent `show` reads. Inspect linked knowledge even when the topic phrase matched poorly; a weak match is not evidence that nothing was saved. Use one bounded follow-up search for a specific remaining gap, not repeated broad scans.

Rank candidates by explicit task relationship, matching title and concrete scope, current applicability, authority, and then recency. Generic words such as `and` and `applies` do not establish relevance. A shared `Firefox` label does not make all frontend records required. The CLI currently has no environment facet filter or improved Chinese segmentation: use specific domain phrases, task IDs, and inspected scope to make the selection; do not claim backend ranking was changed.

Read summary evidence before individual passing checks it covers. Include an older record if it contains a distinct failure, condition, exclusion, or untested boundary absent from the summary. Keep supersession distinct from coverage: a summary covering a successful check does not contradict that check. Excluding it from the recovery packet neither archives it nor changes its status.

For example, when B047 and B049 are individual UI passes covered by the B046–B052 batch summary:

| Packet group | Content |
| --- | --- |
| Required | Task 0002 body; direct-PDF-only entry scope; deferred detailed-overview quality decision; remaining acceptance and next phase. |
| Optional | Up to three relevant validations if the next action needs a regression matrix. Prefer the existing batch document. |
| Excluded | Individual covered UI passes, unless they retain a unique unresolved boundary. |

This is an illustrative selection, not a mandate to find these IDs in every project. The actual packet must identify what was read and any material unresolved gap. Do not invent references, treat the newest summary as universally authoritative, or ask the user to choose among an unfiltered candidate list.
