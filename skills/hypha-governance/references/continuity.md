# Continuity Examples

## Missing Context During Work

A new adapter needs a hosting choice. Code shows a local process but not whether hosting is acceptable. Before asking, search `hosting,offline,cloud,customer`, inspect current task links, and read the relevant body—not only its title.

Use a user-explicit isolated-network restriction while its stated condition holds; no repeat confirmation is needed in a new session. Do not generalize a customer-scoped decision, and do not infer data-transfer permission from internet access. Apply current corrections; ask only if hosting remains unresolved. If bounded search finds no answer, ask about that choice without searching archives or inventing history, while continuing independent work.

## What To Capture

| Available information | Action |
| --- | --- |
| README already specifies the exact build command | Follow or cite README; no knowledge duplicate. |
| Code uses a local process; the user explains that an isolated customer network ruled out the hosted option | Save that missing rationale, the applicable customer/deployment, rejected option, and review condition. Link the implementation. |
| The user answers that the deployment applies to customer Orion, and repeats that this selection should be remembered | Save the stated choice directly with scope and origin, without a second confirmation. |
| The agent suspects all future customers will require isolation | Keep it as an explicitly uncertain inference or draft; do not publish a universal user agreement. |
| A one-off test used a temporary port | Keep it in execution context unless later recovery actually depends on it. |

Knowledge should state the recoverable answer and conditions, using actual user quotes. Capture rationale and non-goals absent from files; link existing facts instead of copying them. Never store credentials or complete transcripts.

## Multiple Plans, One Goal

Task 0001 delivers an import pipeline with CSV and JSON. Plan A verifies CSV; Plan B adds JSON and recovery. Record CSV as a milestone, but keep 0001 open until the remaining acceptance is verified; a new plan does not create a new root or reset the goal.

If a customer replaces JSON with XML, keep 0001 when the outcome continues. Record old and new boundaries, the user's reason, cancelled JSON acceptance, and retained CSV evidence. XML and recovery stay open; do not present old work as newly verified.

An independently schedulable analytics report can be a linked child or another authorized task; an isolated parser helper in the current plan is normally an acceptance detail. If moving work changes a dependency, preserve the actual prerequisite. Do not drop a blocked item just because its old plan was replaced.

## Material Change Record

Use a dated entry under `Change History` in the existing task body. Record only affected aspects in concise prose; the following is an illustrative change, not mandatory fields:

- **Previous boundary:** CSV and JSON import with recovery.
- **Current boundary:** CSV and XML import with recovery.
- **Reason / authority:** Cite the actual user correction requesting XML for the target customer's integration.
- **Unfinished work:** JSON explicitly cancelled by that correction; XML and recovery remain on this task. No unrelated scope cancelled.
- **Evidence and decisions:** CSV checks remain relevant; JSON-specific decisions no longer govern XML. Link any superseding knowledge. Verify the new acceptance before completion.

The record describes a semantic change, not every edit. The current task body should be enough to understand what remains and why the goal evolved without reading old plans, session transcripts, or Git history.

Keep current acceptance in one task checklist. A handoff normally references that task and adds only temporary recovery details. If a legacy handoff says "implement JSON," replace its duplicate scope summary with a task pointer and reconcile any stale temporary instruction. The recorded correction settles the issue without another user question.

## Two-Stage Handoff

Run `context close` to prepare. Review the current conversation for unsaved decisions and recovery details, update the authoritative task and any narrowly scoped handoff draft, then fill the two review decisions in `.hypha/.drafts/context-close.json`. Run `context close --finalize` only after that review. Preparation leaves the context open; finalization records the handoff but does not complete active tasks or end the current work.

On resume without a topic, the latest completed handoff is the preferred entry point. Read its current task and Next Step, then its knowledge and recovery references. Hash or status differences mean the current files changed after handoff; reread current content instead of restoring the recorded version. With an explicit topic, use normal topic retrieval and treat the latest handoff as supplemental context. An unfinished preparation is only a warning that the prior handoff was never confirmed.
