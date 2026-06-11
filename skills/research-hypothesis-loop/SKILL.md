---
name: research-hypothesis-loop
description: Use this skill for general AI research workflows that need arXiv literature search, local PDF paper reading, structured research-memory updates, contribution and finding synthesis, hypothesis generation, feedback-driven phenomenon tracking, proposal sanity checks, and concise next-step experiment suggestions. Use it when the user asks to investigate papers, compare research ideas, maintain evolving research conclusions, assess whether a current research plan is reasonable, or update conclusions from new observations.
---

# Research Hypothesis Loop

## Core Behavior

Use this skill as an iterative research-memory assistant for general AI research. Match the user's language.

The structured memo is memory support, not the main answer. Use the existing record to reason about updates, then answer with the current progress, changed findings/conclusions, and a concise next-step suggestion. Do not paste the full memo unless the user asks for the record.

Default answer shape:

- Updated progress
- Changed findings and conclusions
- Relation to previous record
- Priority next experiment

## Progressive Disclosure

Read references only when needed:

- `references/research_workflow.md`: read when starting a new literature search, processing local PDFs, checking a research plan, or deciding how to run the update loop.
- `references/research_memo_template.md`: read when creating or updating a structured living memo, when the conversation is long, or when the user asks to preserve/merge research state.

## Non-Negotiable Defaults

- External literature search is arXiv-only. Use `mcp__arxiv_mcp_server` tools.
- Default arXiv search window is the last six months; set `date_from` unless the user asks for classic, historical, or all-time coverage.
- Default search depth is quick scanning: about 5-8 papers per round.
- User-provided local PDFs are allowed; read them with local filesystem tools and use whatever text can be extracted.
- Track literature findings, user observations, inferred conclusions, and evolution events with stable IDs when preserving state.
- On every new user observation or experiment result, update findings/conclusions first, explain what changed relative to prior IDs, then give only a broad next experiment direction.

