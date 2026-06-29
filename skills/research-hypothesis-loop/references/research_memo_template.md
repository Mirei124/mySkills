# Persistent Research Memo Template

Use one memo per project at `research/research_memo.md` unless the user supplies another path. The XML-like blocks are Markdown-friendly state containers; they do not need to form valid XML.

## State Rules

- Allocate monotonically increasing three-digit IDs within each prefix: `CTX`, `SEARCH`, `LIT`, `OBS`, `HYP`, `CONC`, `EVT`, and `NEXT`. Never reuse an ID.
- Treat hypotheses and conclusions as the current snapshot. Update the same entity in place; create a new ID only for a genuinely different entity.
- Keep weakened, rejected, completed, and superseded blocks so prior reasoning remains inspectable.
- Treat every `EVT` block as append-only. Initial creation writes `EVT-001` with `Before state: none`; later events record before/after state, evidence, and rationale.
- Deduplicate literature by arXiv ID. Upgrade an existing `LIT` block when abstract evidence is replaced by full-text evidence.
- Keep exactly one `NEXT` block with `status: current`. Mark the prior one `completed` if its experiment produced the new input, otherwise `superseded`, before assigning a new current experiment.
- Never store code-derived method details, paths, symbols, configuration values, or commits; code context expires with the session.

## Template

<research_memo id="MEMO-001" schema_version="2">

<research_context id="CTX-001">
- Goal:
- Target model/task/data:
- Stable research baseline (no code details):
- Current decision:
- Constraints:
</research_context>

<search_round id="SEARCH-001">
- Date:
- Mode: quick | deep
- Queries:
- Date range:
- Categories:
- Selection criteria:
- Papers screened:
- Papers read in full:
</search_round>

<literature_finding id="LIT-001">
- arXiv ID:
- Title:
- Evidence scope: abstract | full-text
- Finding:
- Contribution:
- Evidence:
- Limitation:
- Relevance:
</literature_finding>

<user_observation id="OBS-001">
- Date:
- Observation or result:
- Conditions:
- Metric or qualitative signal:
- Possible measurement or implementation confounds:
- Related literature IDs:
- Confidence:
</user_observation>

<hypothesis id="HYP-001">
- Claim:
- Type: conservative | null | mechanistic | artifact
- Supporting literature IDs:
- Supporting observation IDs:
- Opposing evidence IDs:
- Distinct prediction:
- Discriminating observation:
- Status: candidate | supported | weakened | rejected (terminal only with replicated or uncertainty-controlled evidence)
- Confidence: no stronger than the evidence and its replication
- Open uncertainty:
</hypothesis>

<conclusion id="CONC-001">
- Claim:
- Based on literature IDs:
- Based on observation IDs:
- Related hypothesis IDs:
- Status: tentative | strengthened | weakened | contradicted | refined (contradicted is terminal and requires replicated or uncertainty-controlled evidence)
- Rationale:
- Open uncertainty:
</conclusion>

<evolution_event id="EVT-001">
- Date:
- New input:
- Affected IDs:
- Before state:
- After state:
- Evidence IDs:
- Change type: strengthens | weakens | contradicts | refines | adds | supersedes
- Rationale:
</evolution_event>

<priority_next_experiment id="NEXT-001">
- Primary question:
- Hypotheses distinguished:
- Comparison:
- Critical controls:
- Expected separating signals:
- Result that would change the conclusion: qualitative unless numeric criteria were supplied or derived from available data
- Status: current | completed | superseded
</priority_next_experiment>

</research_memo>

## Update Sequence

When creating or changing research state:

1. Append a `SEARCH` or `OBS` block, or update an existing `LIT` block for the same arXiv paper.
2. Update affected `HYP` and `CONC` blocks while preserving their IDs.
3. Append one `EVT` block; for a new memo, use `Before state: none` and describe the initialized blocks.
4. Resolve the prior current `NEXT`, then add a new current `NEXT` only when the priority experiment changes.
