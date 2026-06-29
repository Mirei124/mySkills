<research_memo id="MEMO-001" schema_version="2">

<research_context id="CTX-001">
- Goal: Understand modality-specific token redundancy in audio-visual question answering.
- Target model/task/data: Audio-visual language model on AVQA.
- Stable research baseline (no code details): Fixed 25% retention for both audio and video tokens.
- Current decision: Determine whether pruning budgets should be modality-specific.
- Constraints: Preserve total token budget.
</research_context>

<user_observation id="OBS-001">
- Date: 2026-06-20
- Observation or result: Fixed 25% retention loses 2.1 accuracy points relative to no pruning.
- Conditions: Same checkpoint, decoding, and evaluation split.
- Metric or qualitative signal: AVQA accuracy.
- Possible measurement or implementation confounds: One random seed.
- Related literature IDs: none
- Confidence: medium
</user_observation>

<hypothesis id="HYP-001">
- Claim: Audio tokens contain more task-critical information than video tokens at the same retention ratio.
- Type: mechanistic
- Supporting literature IDs: none
- Supporting observation IDs: OBS-001
- Opposing evidence IDs: none
- Distinct prediction: Increasing audio retention alone should recover more accuracy than increasing video retention alone.
- Discriminating observation: Modality-specific retention sweep at a fixed total token budget.
- Status: candidate
- Confidence: low
- Open uncertainty: The observed loss may come from seed variance or pruning implementation.
</hypothesis>

<hypothesis id="HYP-002">
- Claim: The apparent loss is seed variance rather than modality-specific information loss.
- Type: null
- Supporting literature IDs: none
- Supporting observation IDs: none
- Opposing evidence IDs: OBS-001
- Distinct prediction: The difference should disappear across repeated seeds without changing retention ratios.
- Discriminating observation: Repeat the baseline and pruned setting across seeds.
- Status: candidate
- Confidence: medium
- Open uncertainty: Only one seed is available.
</hypothesis>

<conclusion id="CONC-001">
- Claim: Current evidence is insufficient to assign different audio and video retention budgets.
- Based on literature IDs: none
- Based on observation IDs: OBS-001
- Related hypothesis IDs: HYP-001, HYP-002
- Status: tentative
- Rationale: The accuracy loss is real in one run but does not identify its modality source.
- Open uncertainty: Modality sensitivity and seed variance are not separated.
</conclusion>

<evolution_event id="EVT-001">
- Date: 2026-06-20
- New input: Initial fixed-ratio pruning result.
- Affected IDs: OBS-001, HYP-001, HYP-002, CONC-001
- Before state: No experiment evidence.
- After state: Two candidate explanations and a tentative conclusion.
- Evidence IDs: OBS-001
- Change type: adds
- Rationale: The first result establishes a phenomenon but not its cause.
</evolution_event>

<priority_next_experiment id="NEXT-001">
- Primary question: Is the pruning loss specific to one modality?
- Hypotheses distinguished: HYP-001, HYP-002
- Comparison: Increase audio retention alone versus video retention alone at matched total tokens.
- Critical controls: Same checkpoint, seed, decoding, and evaluation examples.
- Expected separating signals: Larger recovery from audio supports HYP-001; no stable difference supports HYP-002.
- Result that would change the conclusion: A stable modality gap across seeds would support modality-specific budgets; an unstable gap would preserve the null explanation.
- Status: current
</priority_next_experiment>

</research_memo>
