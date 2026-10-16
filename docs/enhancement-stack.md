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

## Validation completed

The final integration branch contains all 21 slices and their regression fixes. All branch tips were checked for sequential ancestry.

- Full local verification: 57 backend tests (including isolated MySQL authorization), 15 agent tests, 8 PyTorch augmentation/Grad-CAM tests, 3 tooling tests and 12 frontend tests, plus static checks, the production build and Compose validation.
- Both PyTorch workbench smoke workflows passed discovery, fitting/validation, artifact reload, inference, TensorBoard and Grad-CAM.
- Both runtime images built under separate test tags. An isolated container workflow passed sign-in, import preview, annotation, publication, readiness, training, binary artifact download, held-out evaluation, provenance and deterministic augmentation previews.
- Backup/restoration of disposable Studio and training-run volumes passed checksum/path checks, SQLite/image/model reference validation and restored-service model/evaluation/artifact retrieval. Complete MySQL/lakeFS/MLflow service restore rehearsal remains an operator check; all configured named volumes are included by the backup command.
- Dependency audit reports zero vulnerabilities. Existing FastAPI test-client deprecation and demo Pydantic Enum serialization warnings remain non-failing.
- Interactive browser inspection was unavailable in this environment. Component rendering smoke tests, static checks and production compilation passed; visual keyboard/theme checks remain manual.

No changes were deployed to the existing running stack, and main was not advanced. The aggregate branch is `fix/integration-boundaries`. Checkpoint resume, general serving, group-aware splits and new project families remain deferred as originally discussed.

## Repository layout follow-up

`fix/repository-layout` follows the aggregate branch. It aligns dashboard preparation cards, readiness actions, form labels and control heights, repository access badges and forms, and review task layouts. Compact widths use stacked fields and wrapping navigation. Safari visual checks covered Dashboard, Explore, annotation and Manage at desktop width, plus Explore at compact widths. Frontend static checks, 12 tests (including rendering all updated workflow components), production/container builds and 56 backend regression tests passed; the MySQL integration test was skipped in this UI-only follow-up because its isolated database was not running. The updated Studio container is running at localhost:8081. This follow-up and the complete enhancement stack are included in the local main merge.
