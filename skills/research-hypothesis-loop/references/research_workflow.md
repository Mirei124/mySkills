# Research Workflow

Use this procedure after routing the request in `SKILL.md`. Keep the user-facing answer compact, but preserve the evidence and state needed for later updates.

## 1. Load State and Frame the Decision

For a state-changing task, load the user-provided memo path or `research/research_memo.md`. If it does not exist, create it from `research_memo_template.md` after enough context is available.

State the research goal, target model/task/data setting, current baseline, and decision to be made. Ask only for missing information that would materially change the query, interpretation, or experiment.

Convert experiment feedback into an observation before explaining it. Record conditions, metrics or qualitative signals, and plausible measurement or implementation confounds.

## 2. Search arXiv

Use only these arXiv MCP tools for external literature work:

- `mcp__arxiv_mcp_server__search_papers`
- `mcp__arxiv_mcp_server__get_abstract`
- `mcp__arxiv_mcp_server__download_paper`
- `mcp__arxiv_mcp_server__read_paper` when revisiting a downloaded paper

Unless the user asks for classic, historical, or all-time coverage, set `date_from` to six calendar months before the current date. Sort by relevance for focused questions and by date for latest/recent requests. Use categories such as `cs.AI`, `cs.LG`, `cs.CL`, `cs.CV`, `cs.MA`, `cs.RO`, or `stat.ML` when they improve precision. Deduplicate by arXiv ID.

Choose depth from the task:

- **Quick mode**: screen 5-8 papers and read the full text of 1-3 central or technically decisive papers.
- **Deep mode**: use 2-4 complementary queries, screen 12-20 unique papers, and read the full text of 3-6 central or conflicting papers. Use this for an explicitly systematic review or a consequential research decision.

Fetch abstracts before downloading full text. Abstract-only evidence can support broad scope, stated contributions, and author-reported headline results. Base method details, limitations, and strong technical comparisons on full text. Record `Evidence scope` in each literature finding.

Do not use ordinary web search, project pages, or non-arXiv publication databases. Under this evidence boundary, describe novelty only as “not found in this arXiv search,” never as an absolute claim.

## 3. Process an Explicit Local PDF

Do this only when the user explicitly requests a local PDF:

1. Verify the path and inspect it with `pdfinfo`.
2. Extract text with `pdftotext -layout`, retaining page boundaries for page references.
3. Cite the local path and page number for claims based on the PDF.

If the file is scanned or extraction is unusable, state that OCR is unsupported and stop the PDF analysis. Do not compensate with web search. A standalone local-PDF request does not create or update the research memo unless the user also asks to integrate it into the research loop.

## 4. Ground the Current Method in Code

Do this only when the user asks to use the current project implementation for research reasoning. Search narrowly, open the relevant entrypoints, configuration, model, training, or evaluation code, and cite `file:line` for implemented behavior.

Treat code as temporary method context, not empirical evidence. Separate observed implementation facts from inference, and use them only to clarify the current method, identify research confounds or feasibility constraints, and choose a research-level ablation. Do not design code changes, prescribe edits, modify files, or store code paths, symbols, configuration values, commits, or method details in the memo.

Return two compact sections: **Current method facts** with `file:line` citations, and **Ablation brief** with question, one changed factor, control, expected signal, conclusion-changing result, and `Implementation owner: code agent`.

## 5. Build the Evidence Model

Separate literature claims, user observations, and assistant inferences. For each important paper, record its arXiv ID, contribution, evidence, limitation, relevance, and evidence scope. Track conflicts and gaps. Put a compact arXiv source list after each user-facing paragraph containing literature claims.

## 6. Run the Competing-Hypothesis Loop

For a new phenomenon or a hypothesis-generation request:

1. Create 2-4 plausible competing hypotheses, including at least one conservative or null explanation such as measurement error, data effects, or an existing mechanism.
2. Link supporting and opposing `LIT` and `OBS` IDs to each hypothesis.
3. Give each hypothesis an observable prediction that differs from at least one alternative.
4. Calibrate status and confidence to the evidence without erasing rejected or weakened alternatives.
5. Choose the smallest experiment that distinguishes the leading alternatives.

Treat one unreplicated result as evidence for or against an explanation, not as grounds for a terminal status. The next experiment specifies the comparison, controls, separating signals, and what result would change the conclusion; add implementation detail only when requested.

For a code-grounded ablation, provide only the research brief: question, single changed factor, control, expected separating signal, and conclusion-changing result. State that implementation belongs to the code agent; do not provide file-change or code-design instructions.

## 7. Review a Research Proposal

Assess:

- Evidence supporting the proposed mechanism and contribution.
- Assumptions required for the plan to work.
- Conservative and competing explanations.
- Measurement, data, implementation, and evaluation confounds.
- Feasibility of the minimal informative test.
- Predictions that make the proposal falsifiable.
- The result that would change the conclusion.

End with the smallest test that resolves the highest-impact uncertainty. Do not assert global novelty from the bounded arXiv search.

## 8. Update Persistent State

Follow the state rules and update sequence in `research_memo_template.md`, including its initialization event. Write the state before the response; do not write for read-only tasks.

Before writing, audit the memo and reply: downgrade terminal statuses based only on unreplicated evidence, and replace experimental numbers not supplied by the user or derived from recorded data with qualitative criteria.

## 9. Shape the Response

Use only the route that fits:

- **Literature investigation**: scope, main findings, gaps, implications, paragraph-level sources.
- **Observation update**: recorded observation, changed hypotheses/conclusions, relation to prior IDs, minimal discriminating experiment.
- **Hypothesis generation**: competing hypotheses, evidence for/against, distinct predictions, selected discriminator.
- **Proposal review**: verdict, evidence, assumptions/confounds, falsification test, conclusion-changing result.
- **Code-grounded method review**: current implemented behavior with file citations, research implications, and an implementation-free ablation brief.
- **State query**: current progress, active hypotheses, current conclusion, outstanding uncertainty; no write.

Mention memo creation or update briefly. Do not expose the complete XML-like record unless requested.
