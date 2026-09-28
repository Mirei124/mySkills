# Recovery And Capture Usability

Source: user-supplied feedback from session `01a0d415-1d3f-7121-bf13-5c0657205d` and the subsequent approved ROI review. The session archive was not inspected. This development document replaces the skill's feedback roadmap; runtime instructions remain focused on available commands.

| Priority | Capability | Status and boundary |
| --- | --- | --- |
| 1 | Focused recall and hydration | Implemented: title-first triggers, Chinese/English stopwords, common-term discount, lightweight Chinese bigrams, selected-task links, and `context resume --task ID --hydrate`. A configurable node-text budget lists every unexpanded candidate; no silent truncation. Reads do not mutate the store. No semantic coverage inference or recency-as-truth rule. |
| 1 | Safe text input | Implemented: `--quote-file`, `--evidence-file`, and `--user-quote-file`; `-` reads stdin once per invocation. Mixed inline/file inputs preserve order, provenance, and exact-source validation. |
| 2 | Archive and restore | Implemented: `knowledge archive PATH --reason TEXT` and `knowledge restore PATH`, optional revision guards, retained bodies/evidence/links, previous-status restoration, rollback journal, and explicit archived searches. Existing append and supersession remain the consolidation tools. |
| 2 | Diagnostic noise | Implemented: shared-trigger Info only under `check --verbose`, actionable existing edit commands for unmanaged notices, completeness warnings, and stable validation/request failure exit codes with JSON diagnostics. Semantic conflicts still require review. |
| Conditional | External-change acknowledgement | Deferred: there is one concrete reported friction point and an existing unchanged-body publication workflow. The new check hint makes that path discoverable. Add a dedicated guarded acknowledgement only if repeated usage demonstrates that this extra step remains costly. |
| Deferred | Validation subsystem, merge, facets, sync-reference | Routine verification stays in existing Markdown. Archive/append/supersession cover current maintenance needs. Introduce a validation model only after cross-batch matrix queries become frequent. Avoid another source of task/document synchronization. |
| Deferred | Clean/compact/no-snapshot | Reduce unnecessary writes first. Current snapshots are integrity history, not disposable cache. Reconsider only with measured growth and a preservation/migration policy. |

CLI regression coverage lives in `tests/test_recovery_usability.py`: noisy and Chinese retrieval, selected-task isolation, read-only hydration and explicit budget gaps, archive/restore history and rollback, exact file/stdin input, and diagnostic exit codes. Skill behavioral cases cover refusing routine-validation capture; CLI tests do not prove that agents always make the correct capture or applicability judgment.
