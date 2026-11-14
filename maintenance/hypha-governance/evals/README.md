# Hypha Behavioral Evaluations

`evals.json` includes standalone cases and continuity cases requiring a prepared workspace. `setup` is a coordinator instruction, not part of the evaluated user's prompt. Do not treat cases needing setup as runnable against an empty directory.

## Isolated Continuity Scenario

`files/continuity-scenario.json` is coordinator-only scenario data. Do not give the whole file to an evaluated agent: it contains earlier/later prompts and grading assertions that would leak answers across the session boundary.

1. For each skill configuration, create an isolated project containing exactly `project_files`. Save reports and command transcripts outside that project. Use separate projects for the original and revised skill.
2. Give the capture agent its skill path, project path, and `capture_prompt` only. Let it manage the goal and save context through Hypha. Do not tell it which knowledge nodes to create or show grader assertions.
3. Start a fresh agent with no inherited capture conversation. Supply only the skill path, resulting project including `.hypha`, and `recall_prompt`. Do not expose capture reports, transcripts, scenario data, or original statements outside the project. A correct response recovers existing answers and asks only for the absent demo date.
4. Give `evolution_prompt` as a subsequent user correction to the recall agent, keeping the same project. Check that goal identity and CSV evidence survive, JSON is explicitly cancelled, XML and recovery remain unfinished, the reason is saved, and pending handoffs reflect current scope.
5. Grade against actual node bodies, task IDs/status, recall/evolution reports, and command transcripts. Check source attribution, necessary questions, absence of repeated questions, and unchanged project implementation. A passing `check` alone is insufficient evidence.

This scenario never reads real conversation archives. Its invented customer facts are conveyed in the capture prompt and must reach recall through saved project context. Do not count a test as successful recall if the answer leaked through the coordinator's prompt or transcript.

The stale-scope case is a separate negative control: a previous customer's constraint must not silently become a universal rule, and network availability alone must not be treated as permission to transfer records. Ordinary short edits and facts already documented in project files remain non-capture controls.

Report exactly which cases ran. A single successful new/old pair demonstrates the scenario, not a general improvement in success rate; report ties and any missing timing/token measurements honestly. CLI regression tests validate storage and commands, while these agent cases evaluate when to save, recall, ask, or evolve a task.
