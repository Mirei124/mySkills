# Continuity Examples

## Missing Context During Work

A new adapter needs a hosting choice. The code shows a local process, but does not explain whether hosted services are acceptable. Before asking the user, search Hypha for `hosting,offline,cloud,customer` and inspect the current task's knowledge links. Read the relevant body, not just a matching title.

If a user-explicit node says the customer network is isolated and hosted processing was rejected for that reason, with review required only if network access changes, use that answer while the condition holds. Cite the saved rationale briefly if it explains the implementation. No repeat confirmation is needed because this is a new session.

If the node applies only to the previous customer, or the user now says this deployment has internet access, do not generalize the restriction. Use the current correction where it settles the issue; ask only whether hosted processing is acceptable if that choice is still unresolved. Network availability alone does not authorize sending customer data anywhere.

If no record answers the question after a bounded search, ask about the missing choice. Do not search session archives or invent a historical answer. Continue independent implementation work while awaiting necessary input.

## What To Capture

| Available information | Action |
| --- | --- |
| README already specifies the exact build command | Follow or cite README; no knowledge duplicate. |
| Code uses a local process; the user explains that an isolated customer network ruled out the hosted option | Save that missing rationale, the applicable customer/deployment, rejected option, and review condition. Link the implementation. |
| The user answers that the deployment applies to customer Orion, and repeats that this selection should be remembered | Save the stated choice directly with scope and origin, without a second confirmation. |
| The agent suspects all future customers will require isolation | Keep it as an explicitly uncertain inference or draft; do not publish a universal user agreement. |
| A one-off test used a temporary port | Keep it in execution context unless later recovery actually depends on it. |

Knowledge bodies should make the recoverable answer and its conditions clear. Record the actual user quote rather than quoting these examples. Capture rationale and non-goals absent from project files; link existing facts instead of copying them. Never store credentials or complete transcripts.

## Multiple Plans, One Goal

Task 0001 aims to deliver a working import pipeline with CSV and JSON support. Plan A implements and verifies CSV. Plan B implements JSON and failure recovery. Completing Plan A records a CSV milestone on 0001; 0001 stays open because JSON and recovery are not accepted yet. Starting Plan B, even in the same conversation, does not create a new root or reset the goal.

If the user replaces JSON with XML for a customer's integration, keep 0001 when the intended pipeline outcome continues. Record the old CSV+JSON boundary, new CSV+XML boundary, the user's reason, the explicit cancellation of JSON acceptance, and retained CSV evidence. XML and recovery remain unfinished acceptance. A new plan implements those items without disguising old work as newly verified progress.

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

Run `context close` to prepare. Review the current conversation for unsaved decisions and recovery details, update the authoritative task and any narrowly scoped handoff draft, then fill the two review decisions in `.hypha/.drafts/context-close.json`. Run `context close --finalize` only after that review. Preparation leaves the context open.

On resume without a topic, the latest completed handoff is the preferred entry point. Read its current task and Next Step, then its knowledge and recovery references. Hash or status differences mean the current files changed after handoff; reread current content instead of restoring the recorded version. With an explicit topic, use normal topic retrieval and treat the latest handoff as supplemental context. An unfinished preparation is only a warning that the prior handoff was never confirmed.
