---
name: research-hypothesis-loop
description: Use this skill for general AI research workflows that need arXiv literature search, local PDF paper reading, contribution and finding synthesis, hypothesis generation, feedback-driven phenomenon summaries, proposal sanity checks, and iterative next-plan design. Use it when the user asks to investigate papers, compare research ideas, explain what is known, assess whether a current research plan is reasonable, or propose new experiments from recent feedback.
---

# Research Hypothesis Loop

## Overview

Use this skill as a high-frequency research collaborator for general AI research. It coordinates arXiv evidence gathering, local paper reading, finding synthesis, hypothesis generation, proposal review, and feedback-driven iteration.

Match the user's language. If the user writes in Chinese, answer in Chinese; if the user writes in English, answer in English.

## Research Loop

Run the work as an interactive loop, not as a one-shot report unless the user explicitly asks for a full memo.

1. Frame the question
   - Restate the research question, target model/task/data setting, and current constraint.
   - If the user provided experiment feedback, convert it into concrete observations before proposing causes.
   - Ask a short clarifying question only when a missing detail changes the search query or evaluation criterion.

2. Search arXiv
   - Use `mcp__arxiv_mcp_server.search_papers` for literature search.
   - By default, search recent papers from the last six months. Set `date_from` accordingly unless the user asks for classic, historical, or all-time coverage.
   - Default to quick scanning: search about 5-8 papers per round.
   - Prefer relevance sort for focused questions and date sort for "latest/recent" requests.
   - Use categories when useful for AI research, commonly `cs.AI`, `cs.LG`, `cs.CL`, `cs.CV`, `cs.MA`, `cs.RO`, or `stat.ML`.
   - Use `get_abstract` before `download_paper` unless the search result already makes a paper clearly central.
   - Download and read full papers only for highly relevant or technically decisive papers.

3. Read user-provided local PDFs
   - If the user gives a local PDF path, first verify the file exists.
   - Try to extract readable text with available local tools.
   - If extraction fails or is incomplete, state the limitation and use only the readable content.
   - Do not broaden to ordinary web search; external literature search is limited to arXiv tools.

4. Synthesize evidence
   - Summarize each relevant paper by problem, method, evidence, contribution, and limitation.
   - Separate paper claims from your inference.
   - Track agreements, contradictions, negative results, and unexplained phenomena.
   - Keep citations tied to arXiv IDs or local PDF paths.

5. Generate hypotheses
   - Produce a small set of candidate hypotheses, each linked to evidence and expected observable outcomes.
   - Prefer hypotheses that can be falsified by a minimal experiment.
   - Include at least one conservative explanation before proposing a novel mechanism.

6. Review the current plan
   - Use the evidence-risk-experiment rubric:
     - Evidence: what supports the plan?
     - Risk: what assumption could make it fail?
     - Gap: what is not yet explained or measured?
     - Experiment: what is the smallest check that would change the decision?
   - Do not over-engineer solutions before the key uncertainty is identified.

7. Ask for feedback and iterate
   - After each major stage, offer concise options for the next step.
   - When the user provides new feedback, update known observations first, then revise hypotheses and the plan.

## Default Output Shape

For normal interactive work, use compact sections:

- Current read
- Evidence
- Candidate hypotheses
- Plan check
- Next options

For a full research memo, read `references/research_memo_template.md` and follow that structure.

## Tool Discipline

- Use arXiv MCP tools for external paper discovery and paper retrieval.
- Use local filesystem tools for user-provided PDF paths.
- Do not use ordinary web search for literature expansion unless the user explicitly overrides the arXiv-only constraint.
- When evidence is thin, say so and propose the next search or experiment instead of overstating certainty.
