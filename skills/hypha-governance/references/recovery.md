# Recovery Details

Use `context resume --hydrate` to read a minimal packet in one call. Supply `--task ID` when known; otherwise selection uses an unambiguous task ID/topic, the latest completed handoff without a topic, or a unique running/active task. Ambiguity is reported rather than mixing knowledge linked to all active tasks.

Required contains the selected task and its active knowledge, including explicit body links and replacements of superseded conclusions. Optional contains up to three other topic matches; these are candidates, not proof of applicability. Excluded identifies linked archived or superseded records. The CLI does not infer semantic coverage, verify user decisions, or rank by modification time.

The node-text budget defaults to 16000 characters; adjust with `--max-chars N`. A body that does not fit is listed under Not expanded with a `show` command; bodies are not silently truncated. Read deferred required entries before acting. Headers, omission lists, handoff notices, and draft references are outside this budget so recovery gaps remain visible. Plain `context resume` keeps an index-only mode.

Ranking favors matching titles, concrete applicability, and selected-task association. Common terms are discounted by document frequency; boilerplate English/Chinese stopwords are filtered even from old stored triggers. Chinese phrases also use bounded bigram overlap, without a segmentation dependency. `advanced explain TOPIC` exposes matching terms and scores. Weak matches still need applicability review; use a bounded literal `search` for remaining gaps.

The CLI lists pending drafts and finalized handoff references without automatically reading every referenced artifact. Inspect relevant references, missing Next Step/Acceptance, changed hashes, and unconfirmed handoffs. Current task state and user corrections override stale handoff directions.

Read a batch summary before individual passing checks it covers. Preserve any distinct failure, scope condition, or untested boundary absent from that summary. Archive covered records only after that review and within authorized maintenance; coverage is not contradiction. New routine validation belongs in batch Markdown.

For a PDF-entry task with many historical browser passes, the desired packet includes the task, direct-PDF-only scope, and an unresolved detail-quality deferral. Reviewed archived UI passes remain excluded. A still-unresolved browser failure must remain accessible. Do not create validation records just to populate Optional, or ask the user to choose among an unfiltered candidate list.
