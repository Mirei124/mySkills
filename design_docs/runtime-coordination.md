# Runtime plan and goal boundary

Hypha overlaps superficially with the agent runtime's plan and goal mechanisms because all three can mention work and completion. Their lifetimes and sources of truth are different, so they should be layered instead of synchronized field by field.

| Layer | Lifetime and owner | Stores | Must not become |
|---|---|---|---|
| Runtime plan | Current execution/turn, owned by the active agent | A small ordered list of pending, in-progress, and completed steps | A repository backlog or audit history |
| Runtime goal | Current conversation thread, created only on explicit request | One continuing objective, optional budget, and terminal complete/blocked state | A task DAG, knowledge base, or Git-tracked project truth |
| Hypha intent | Repository-local and Git-shared across sessions and agents | Stable task boundaries, milestones, dependencies, acceptance, evidence, blockers, and durable progress | A copy of every runtime plan step or tool action |
| Hypha knowledge | Repository-local, cumulative project memory | Rationale, constraints, decisions, consensus, definitions, lessons, assumptions, sources, contradictions, and links | Always-on operating instructions already owned by `AGENTS.md` |

## Synchronization rule

Do not automatically mirror runtime state into Hypha. A plan step such as “run tests” is normally transient. A goal such as “finish this refactor” may restate an existing Hypha root but does not become another node. Update Hypha only at semantic commit points: a durable boundary or dependency changes, a milestone gains acceptance evidence, a blocker changes future scheduling, or reusable knowledge is established.

At session start, Hypha may inform the runtime goal and plan. During execution, the plan guides immediate actions. At a meaningful boundary, the agent writes only the durable delta back to Hypha. This one-way briefing plus selective write-back prevents three competing progress trackers.

This boundary preserves Hypha's purpose: prevent drift in long-running repository work and accumulate an Obsidian-like knowledge graph, while leaving immediate orchestration to the runtime.
