# Session Feedback: CLI Follow-up

Source: user-supplied feedback from session `01a0d415-1d3f-7121-bf13-5c0657205d`. The session archive was not inspected. These are proposed capabilities, not commands supported by the bundled CLI. The skill-level changes implement capture and recovery discipline using existing commands.

| Priority | Proposed capability | Acceptance boundary |
| --- | --- | --- |
| 1 | Recall ranking and `context resume --hydrate` | Use Chinese/English stopwords and discount applicability boilerplate; favor title, concrete scope, task association, and current applicable state. Model frequent environment labels as facets. Return recommended task/knowledge bodies with bounded optional evidence and explained exclusions; preserve distinct failures and unresolved conditions. Recall remains read-only. |
| 2 | `validation record` and knowledge merge/supersede/archive | Store batch, browser, feature, result, attribution, and evidence separately from durable knowledge. Exclude validation from default recall; allow regression-matrix retrieval. Consolidation preserves evidence, references, provenance, and recoverability; do not infer supersession from recency alone. Existing `record --supersedes` already handles explicit changed conclusions, but no knowledge merge/archive command exists. |
| 3 | External-document coordination and actionable check output | Add explicit reference synchronization or external-change acknowledgement without erasing audit history. Separate structural errors, recovery-affecting warnings, and informational notices, with supported repair commands. Preserve one owner for each kind of information. |
| 4 | Workspace noise policy and safe input | Distinguish committed formal state and integrity history from transient cache before adding ignore rules, clean/compact, or optional snapshot behavior. Add quote/evidence file or stdin input without weakening exact-quote validation or attribution. |

Evaluate the first two priorities with a fixture containing many repeated UI passes, a batch summary, a durable direct-PDF-only scope decision, and a deferred detail-quality issue. Recovery should read the task and applicable decisions without making all browser-tagged records required. Adding a new passing check must not grow active knowledge. A distinct unresolved browser failure must remain discoverable.
