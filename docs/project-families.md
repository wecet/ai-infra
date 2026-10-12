# Project families and future expansion

Reviewed 12 October 2026. Vision is implemented; LLM/VLM and Language are placeholders displaying **Under Development - Check in Soon**. The designs below are proposals.

| Family | Intended focus | Proposed first usable workflow |
| --- | --- | --- |
| Vision | Image-based classification, detection and anomaly scoring | Existing workflows, followed by stronger held-out evaluation and additional annotation tasks |
| Language | Structured text tasks with task-specific labels | CSV/JSONL text classification → text review → frozen splits → baseline training → confusion matrix |
| LLM/VLM | Generative and multimodal model workflows | Versioned instruction/conversation data → prompt evaluation → response comparison; then image-question-answer samples |

Language should describe task-oriented text workflows, while LLM/VLM should describe generative or multimodal workflows. Shared storage, versioning, jobs, evaluation records and lineage should be reused without forcing text into the vision archive representation.

## Proposed sample formats

- **Language:** sample ID, text, optional label/span annotations, source/group metadata and frozen split.
- **LLM:** sample ID, role-based messages, optional expected response or evaluation rubric, source/group metadata and frozen split.
- **VLM:** the conversation fields plus stable image/asset references and per-asset checksums.

Validate schemas and assets before publishing. Preview representative samples and identify unsupported roles, missing assets and invalid labels. Keep related conversations/documents in a single partition to reduce leakage.

## Contract evolution

Introduce explicit dataset schema versions and task capabilities before adding functional selectors. Model descriptors should declare supported families/tasks, input schema, prediction schema, configuration applicability and evaluation capabilities. Keep Pydantic validation and framework-neutral lifecycle contracts. Add text/multimodal contracts alongside the existing Vision classes rather than renaming them incompatibly.

Each enabled task needs an importer, sample preview/editor where appropriate, immutable manifest, compatible trainer, inference adapter and meaningful evaluator. Model providers may expose latency/token usage; only report these when measured by the adapter. Do not imply generative answer quality from training loss alone.

## Suggested rollout

1. Implement text classification as one complete Language workflow.
2. Implement prompt evaluation on versioned conversation datasets before adding fine-tuning.
3. Add VLM asset validation and multimodal inference/evaluation.
4. Consider retrieval evaluation, preference datasets and adapter training after the above workflows are used.

These steps have no committed dates. Keep the current placeholders until a complete workflow is available.
