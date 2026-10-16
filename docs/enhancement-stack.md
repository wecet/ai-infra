# Enhancement stack

Each branch starts at the preceding branch tip. Each slice has its own scoped commit; the final branch includes the full stack.

| Branch | Scope |
| --- | --- |
| fix/verification-pipeline | Unified local checks and PR CI |
| fix/evaluation-reconnect | Bounded reconnects and permanent-error handling |
| fix/agent-capacity | Capacity-limited agent scheduling |
| feature/training-controls | Cooperative cancellation and linked retry |
| feature/frozen-provenance | Frozen validation membership and run provenance |
| fix/dataset-transfers | Disk-backed dataset and binary artifact transfers |
| fix/backend-services | Explicit imports and shared dataset services |
| feature/run-cloning | Parent runs and configuration changes |
| feature/dataset-readiness | Readiness report and actionable checks |
| feature/run-comparison | Compatible model comparison and same-image predictions |
| feature/evaluation-browser | Search, class, confidence and error filters; pagination |
| feature/anomaly-explorer | Exploratory threshold and score histogram |
| feature/failure-review | Model-linked review queue |
| feature/dataset-explorer | Metadata and duplicate filters |
| feature/import-staging | Import validation preview and selective commit |
| feature/augmentation-preview | Reproducible image/box preview |
| feature/lineage-navigation | Search and selected ancestry |
| feature/team-review | Review assignment and attributable activity |
| fix/editor-boundaries | Extract editor interaction and persistence helpers |
| feature/backup-restore | Backup and isolated restore verification |
| fix/integration-boundaries | Authorization, state, split and artifact regression checks |

Checkpoint resume and new Language/LLM project families were explicitly deferred in the brainstorm and are outside this stack.
