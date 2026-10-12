# Product brainstorm and proposed roadmap

Status: proposals, reviewed 12 October 2026. Priorities are recommendations for discussion, not approved scope or promised dates. Effort is relative: **S** is a focused change, **M** touches several layers, and **L** needs a new subsystem or substantial contract work. Estimates assume the current single-host deployment and must be revisited after design.

The strongest direction is to make AI Studio a reproducible **dataset → training → evaluation → model** workspace, then extend that reliable workflow into new project families. Existing functionality is documented in [Platform overview](platform-overview.md).

## Implementation update

The first reliability/evaluation slice is now implemented in source: agent-owned persisted jobs, heartbeat/progress/log tails, Studio restart reattachment, compact job cards, recorded train/test IDs, and saved-model evaluation dialogs. Agent restart is reported as interruption, not checkpoint recovery. A dedicated worker queue, cancellation, full manifest-level train/validation/test partitions, configurable evaluation policies and model promotion remain proposals. See [Training jobs and evaluation](training-jobs-and-evaluation.md).

## Recommended first three increments

| Order | Proposal | Why it comes first | A reviewable first slice |
| --- | --- | --- | --- |
| 1 | Reliable jobs and trustworthy status | Long runs should survive a page change or service interruption with an understandable outcome | Persist worker ownership and heartbeats; reconcile interrupted jobs after restart; distinguish training success from tracking/publishing failures |
| 2 | Frozen split and run provenance | Model comparisons are meaningful only when data partitions and run inputs are known | Save train/validation/test membership for one supervised task; record dataset manifest hash, model revision, validated config, seeds, and environment summary |
| 3 | Evaluation and inference workspace | A downloaded artifact is difficult to assess without seeing predictions | Run one registered model on a fixed held-out dataset; show predictions, relevant metrics, and failure examples |

Keep these slices small. A database-backed worker can be sufficient before adding a message broker. A single task's evaluator is more useful than an empty generic dashboard. Keep MLflow and TensorBoard as sources of tracking and detailed visualizations while Studio adds workflow context.

## Reliability, data, and model backlog

| ID | Proposal | Priority / effort | Dependencies | Completion criteria |
| --- | --- | --- | --- | --- |
| R1 | Durable job execution, heartbeats, restart reconciliation | First / M | Persisted state transitions and agent protocol | Restarting Studio or an agent does not leave a job indefinitely marked running; the UI explains interruption or recovery |
| R2 | Cooperative cancellation, bounded retries, checkpoint resume | Next / L | R1; trainer checkpoint/cancel contract | Cancel releases compute; retry creates a traceable new attempt; resume checks model/data compatibility and records its parent run |
| D1 | Frozen train/validation/test partitions for all Vision tasks | First / M | Dataset manifest evolution | Re-running a published version uses identical partitions; models cannot silently resplit a held-out test set |
| D2 | Group-aware and stratified splitting | Next / M | D1; sample group metadata | Related frames, subjects, or duplicate groups stay in one partition; supervised class balance is reported |
| D3 | Import preview, schema validation, batch progress and retry | First / M | Existing import endpoints | Users see accepted/rejected samples and reasons before committing a batch; successful items need not be reuploaded |
| D4 | Object-storage datasets and streaming access | Later / L | Stable manifest and asset identifiers | Agents consume a selected immutable version without copying every image into one large request; checksums verify downloaded assets |
| T1 | Reproducibility record and reusable config presets | First / M | Validated Pydantic config | A run exposes its full inputs, source revision and dependency summary; cloning it preserves originals and highlights changes |
| T2 | Agent health/resource panel and simple job capacity limits | Next / M | R1 | CPU/GPU availability, last contact, memory and current jobs are visible; work is not scheduled beyond configured capacity |
| T3 | Hyperparameter search with an explicit compute budget | Later / L | R1, D1, evaluation | A sweep records trial configs and comparable outcomes, stops at its budget, and retains failed trials |
| E1 | Inference playground and held-out evaluation | First / M per task | Artifact loading and prediction schemas | A user sees source images, predictions, and saved evaluation results linked to model and dataset versions |
| E2 | Run comparison and promote a candidate | Next / M | E1, T1 | Compare runs on the same evaluation version; incompatible metrics are explained rather than ranked together |
| M1 | Serving lifecycle, endpoint health, rollout and rollback | Later / L | Explicit serving contract; model registry | A deployment links to its exact artifact and config, exposes health, and can roll back to a known model |
| O1 | Backup/restore command and restore smoke test | First / M | Existing volumes | Restore database, image assets, MLflow artifacts and training logs into an isolated environment and verify links |
| O2 | Authentication, project roles, attributable audit events | Before shared multi-user use / L | Identity and authorization design | Owners, trainers, labellers and viewers have enforced permissions; direct API access respects the same rules |
| O3 | Storage retention and cleanup preview | Next / M | Artifact ownership and dependency checks | Users see reclaimable space; cleanup cannot remove assets still referenced by retained versions or models |
| O4 | Versioned manifests/contracts, migration checks and release notes | First / M | Package and platform release workflow | A model declares compatible schema versions; upgrades preserve old datasets; docs identify source-only features |

## Task-specific ideas

### Vision

- **Anomaly evaluation:** a score histogram, ranked examples, optional heatmaps, and a threshold explorer. An audited, separately labelled evaluation set can support precision/recall or ROC/PR metrics without adding labels to the unsupervised training workflow. Without ground truth, show score distributions and flagged rates only.
- **Active learning:** queue uncertain or diverse predictions for human labelling in supervised projects. Store model/version/confidence with each suggestion and distinguish suggestions from accepted annotations.
- **Dataset exploration:** image dimensions, class counts, tag filters, camera/source metadata and embedding-based similarity. Start with existing metadata and duplicate findings before computing an embedding index.
- **More annotation tasks:** segmentation, keypoints, OCR/document regions and video. Each needs its own annotation schema, editor, export format and evaluator; a selector entry alone is not support.
- **Augmentation preview:** show representative before/after samples and transformed boxes, with validation for incompatible settings. Keep previews reproducible with a visible seed.

### Language and LLM/VLM

- **Language first slice:** text classification with CSV/JSONL import, labelled text review, frozen splits, a baseline trainer, and a confusion matrix.
- **LLM first slice:** versioned instruction/conversation datasets and prompt evaluation before fine-tuning. Add small, reproducible evaluation suites, response comparison, and latency/token accounting when the model adapter exposes them.
- **VLM first slice:** image-question-answer or image-caption samples, asset validation, multimodal preview, and a compatible inference/evaluation adapter.
- **Later:** retrieval evaluation, preference pairs, adapter fine-tuning and retrieval-augmented generation experiments. An index, retriever, prompt and model must each have a versioned identity for useful lineage.

These are proposed first slices, not available task types. See [Project family expansion](project-families.md) for the taxonomy and contracts.

## UI/UX improvements with high practical value

1. A task-aware readiness checklist before publishing or starting training.
2. Compact job cards with phase, elapsed time, heartbeat, latest metric and context-specific actions.
3. Basic/advanced schema forms that hide infrastructure fields and omit unsupported model options.
4. A split editor with sample counts, duplicate/group leakage warnings and a clear frozen-version preview.
5. Searchable, filterable lineage with selection highlighting and expandable run details.
6. Persistent draft configs, predictable keyboard navigation, accessible dialogs, and useful empty/loading/error states.

Detailed behavior and acceptance checks are in [UI/UX proposals](ui-ux-roadmap.md).

## Ideas to defer until the foundation earns them

Defer a general workflow builder, distributed training orchestrator, full model marketplace, automatic algorithm selection, and a large dashboard widget system. These add substantial surface area without resolving current reproducibility and job-lifecycle gaps. Add a dependency or service when a specific shipped workflow needs it.

## Decisions worth making before implementation

- Is the next target a personal local tool, a small team workspace, or a shared hosted service? This determines authentication and scheduling urgency.
- Is the primary next win anomaly evaluation, supervised evaluation, or text datasets? Choose one end-to-end demonstration.
- Will training read published Studio snapshots or lakeFS commits directly? Record the actual source; do not imply a lakeFS dependency where only a mirror exists.
- Which metrics decide model promotion for each task, and who owns the evaluation dataset?
- What resource and retention budgets should constrain training, experiments and logs?

Review the first three increments after they are used on real projects. Measure fewer stuck jobs, clearer run reproduction, and a user's ability to assess a model; do not use feature count as the success criterion.
