---
name: research-hypothesis-loop
description: Use this skill for multi-step, arXiv-only AI research loops that investigate literature, maintain research state, compare hypotheses, incorporate experiment feedback, sanity-check proposals, or read current project code as temporary method context for research planning. Trigger it for arXiv investigations, evolving conclusions, evidence-linked hypothesis generation, interpretation of observations, falsifiability review, and code-grounded understanding of the current method or research-level ablation planning. Do not invoke it for pure code debugging, implementation, or a one-paper summary; it reads code without designing or modifying it.
compatibility: Requires the arxiv_mcp_server MCP. Code grounding requires read-only project filesystem access. Explicit local text PDFs require pdfinfo and pdftotext; scanned PDFs and OCR are unsupported.
---

# Research Hypothesis Loop

## Purpose

Connect arXiv evidence, user observations, competing hypotheses, conclusions, and discriminating experiments across sessions. Match the user's language. Use `research/research_memo.md` as the default project source of truth; a user-provided path overrides it.

## Route the Task

Classify the request before acting:

- **Literature investigation**: search arXiv, synthesize evidence, identify gaps, and update the memo.
- **Observation or experiment update**: record the observation, revise affected hypotheses and conclusions, append an evolution event, and select the next discriminating experiment.
- **Hypothesis generation**: produce 2-4 competing explanations, including at least one conservative or null explanation, with distinct predictions.
- **Proposal sanity check**: evaluate evidence, assumptions, alternatives, confounds, feasibility, falsifiability, and what result would change the conclusion.
- **Current-method grounding**: inspect relevant code read-only, cite `file:line` for method facts, and hand a research-level ablation brief to the code agent.
- **State query or temporary explanation**: read the memo when relevant, but do not write it.
- **Explicit local PDF request**: process a text PDF as described in the workflow; a PDF alone is not an implicit trigger.

## Research State

For state-changing tasks, read or initialize the memo, preserve stable IDs and history, and write the update before answering. Code-derived method details remain session-only and never enter the memo. Do not write for a pure explanation, state query, one-paper summary, or code work. Do not show the full memo unless requested.

## Progressive Disclosure

- Read `references/research_workflow.md` for arXiv search, evidence handling, code grounding, hypothesis updates, proposal review, and response shapes.
- Read `references/research_memo_template.md` whenever creating, loading, updating, or merging the persistent memo.

## Defaults

- External discovery is arXiv-only; use the recent quick mode unless the user requests another scope.
- Keep paper claims, user observations, and assistant inferences distinct.
- Prefer one minimal discriminating experiment over a broad experimental plan.
