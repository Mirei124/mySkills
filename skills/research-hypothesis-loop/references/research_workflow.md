# Research Workflow

Use this reference for detailed operating procedure. Keep final answers concise unless the user asks for a full record.

## 1. Frame the Question

- Restate the research goal, target model/task/data setting, and current constraint.
- Convert user feedback into concrete observations before proposing explanations.
- Ask only for details that would change the search query, interpretation, or next experiment.

## 2. Search arXiv

- Use `mcp__arxiv_mcp_server.search_papers`.
- Default to recent papers from the last six months by setting `date_from`.
- Search about 5-8 papers per round.
- Prefer relevance sort for focused questions and date sort for "latest/recent" requests.
- Use categories when useful: `cs.AI`, `cs.LG`, `cs.CL`, `cs.CV`, `cs.MA`, `cs.RO`, `stat.ML`.
- Use `get_abstract` before `download_paper` unless a paper is clearly central.
- Download/read full papers only for highly relevant or technically decisive papers.

## 3. Read Local PDFs

- If the user gives a local PDF path, verify the file exists.
- Try to extract readable text with available local tools.
- If extraction fails or is incomplete, state the limitation and use only readable content.
- Do not broaden to ordinary web search.

## 4. Build or Update the Research Record

- Use the structured memo only as memory support.
- Prefer stable tagged blocks from `research_memo_template.md`.
- Preserve existing IDs when updating.
- Create a new ID only for a genuinely new literature finding, user observation, conclusion, or evolution event.
- Keep citations tied to arXiv IDs or local PDF paths.

## 5. Synthesize and Update

- Separate literature claims, user observations, and assistant inferences.
- Emphasize:
  - What the literature already found.
  - Each paper's contribution.
  - What the user has newly observed.
  - What conclusions can now be inferred.
  - Which previous findings/conclusions are strengthened, weakened, contradicted, or refined.
- When evidence is thin, say so and propose the next check.

## 6. Suggest the Next Experiment

- Give only the highest-priority next experiment direction.
- Keep it broad: primary question, rough intervention/comparison, expected signal.
- Do not provide detailed implementation, metrics, ablations, or schedules unless requested.

