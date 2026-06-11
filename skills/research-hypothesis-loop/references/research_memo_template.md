# Structured Living Research Memo Template

Use this template after literature collection or when consolidating feedback rounds. The memo is a living state record designed for LLM recall, update, and merge. Treat it as memory support: use it to decide what changed and what to recommend next, but do not paste the whole record into the answer unless the user asks for it. It uses paired XML-like tags around Markdown content; the format does not need to be valid XML.

## Record Rules

- Keep stable IDs. Update an existing block when a new result changes it; create a new ID only for a genuinely new item.
- Use ID prefixes consistently:
  - `CTX-###` for research context
  - `SEARCH-###` for search rounds
  - `LIT-###` for literature findings
  - `OBS-###` for user observations or experiment results
  - `CONC-###` for inferred conclusions
  - `EVT-###` for evolution events
  - `NEXT-###` for priority next experiment directions
- Prefer short fields over long prose so blocks can be updated independently.
- In every update, add an `<evolution_event>` that references affected finding and conclusion IDs.
- Keep next experiments directional. Do not include implementation details unless requested.
- In user-facing replies, summarize the updated progress and the changed conclusions instead of dumping all blocks.

## Template

<research_memo id="MEMO-001">

<research_context id="CTX-001">
- Goal:
- Target setting:
- Current method or baseline:
- Current decision needed:
</research_context>

<search_round id="SEARCH-001">
- arXiv queries:
- Date range:
- Categories:
- Selection criteria:
- Papers screened:
- Papers read in detail:
</search_round>

<literature_finding id="LIT-001">
- Source:
- Finding:
- Contribution:
- Evidence:
- Limitation:
- Relevance:
</literature_finding>

<user_observation id="OBS-001">
- Observation or result:
- Conditions:
- Metric or qualitative signal:
- Related literature IDs:
- Confidence:
</user_observation>

<conclusion id="CONC-001">
- Claim:
- Based on literature IDs:
- Based on observation IDs:
- Status: tentative | strengthened | weakened | contradicted | refined
- Rationale:
- Open uncertainty:
</conclusion>

<evolution_event id="EVT-001">
- New input:
- Affected literature IDs:
- Affected observation IDs:
- Affected conclusion IDs:
- Change type: strengthens | weakens | contradicts | refines | adds
- What changed:
- Updated conclusion:
</evolution_event>

<priority_next_experiment id="NEXT-001">
- Primary question to verify:
- Broad experiment idea:
- Expected observation if current conclusion is right:
- Result that would change the conclusion:
</priority_next_experiment>

<next_feedback_needed>
- Needed detail:
- Why it matters:
- Suggested next options:
</next_feedback_needed>

</research_memo>

## Update Pattern

When the user provides a new phenomenon or experiment conclusion:

1. Add or update one `<user_observation>` block.
2. Update affected `<conclusion>` blocks in place, preserving IDs.
3. Add one `<evolution_event>` block explaining the relationship to previous findings and conclusions.
4. Replace or update the single most important `<priority_next_experiment>` block with a concise direction.
