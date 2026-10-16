# Current platform overview

Status: implemented functionality in this checkout, reviewed 12 October 2026. This is separate from the [proposed roadmap](roadmap.md).

## Project families

| Family | Current availability | Dataset workflow |
| --- | --- | --- |
| Vision — object detection | Available | Image import, boxes, completion, annotation review, publishing, and training |
| Vision — image classification | Available | Image import, class labels, completion, annotation review, publishing, and training |
| Vision — anomaly detection | Available | Unlabelled images, no classes or annotation review; frozen train/test partitions, publishing, and training |
| LLM/VLM | Placeholder | New Project displays **Under Development - Check in Soon** |
| Language | Placeholder | New Project displays **Under Development - Check in Soon** |

The Vision form retains its values when switching sections. Placeholder sections cannot create projects. Anomaly implementations learn without class labels; the bundled baseline reports scores rather than detection accuracy against unavailable ground truth.

## Data and model flow

1. Create a project and import images. Supervised tasks require annotation completion; anomaly imports are immediately ready for dataset operations.
2. Inspect image membership, duplicate findings, and split leakage. Manage classes for supervised projects or configure the anomaly split in Manage.
3. Publish an immutable local version. Push that version to lakeFS as a separate action; local publication does not itself mean a lakeFS commit exists.
4. Select a published version, a compatible model workbench, validated configuration, and local or remote compute.
5. The compute agent receives a ZIP of the published version and returns metrics and an artifact. Studio records the result and a registered-model entry; MLflow records tracking information when available.
6. Follow individual relationships in Lineage or compare published dataset versions. Download a trained model for use outside Studio.

Anomaly version manifests freeze each image's `train` or `test` assignment. Supervised live exports provide train/test archives; the PyTorch demos currently use their model configuration for validation holdouts. New publications use a frozen train/validation/test contract for supervised Vision; anomaly datasets retain train/test.

## Existing usability features

- Light and dark themes with grouped metric colours, compact run actions, and visible focus indicators.
- Pydantic defaults, structured augmentation and callback settings, and field-description popups.
- Closable start/trainer error popups without losing the training form.
- Per-run TensorBoard links for the supported demo callback configuration, with losses and Grad-CAM visualizations.
- Named runs using `YYMMDD-{project-name}-v{version-number}`.
- Per-entry lineage connectors, including descriptions on hover/focus and dashed same-dataset snapshot relationships.
- Image deletion recovery, immutable version previews, comments, history, and quality findings.

## Practical limits that inform the roadmap

- Agent jobs persist progress and results and Studio reattaches after restart. Agent execution still uses in-process worker threads: agent restart reports interruption; cooperative cancellation is available; checkpoint resume remains future work.
- Remote compute is selected by endpoint; there is no agent fleet scheduler or resource reservation system.
- Saved models now expose held-out predictions, metrics and examples in a dialog. Run comparison, example filtering and pagination, anomaly threshold exploration and model-linked review are available. A general inference playground and configurable metric policies remain future work.
- Registered-model and deployment lineage records do not constitute a managed model-serving lifecycle with rollout and rollback controls.
- The model contract and archive representation are vision-oriented. LLM/VLM and Language need suitable sample schemas and validation before their placeholders can become functional.
- Studio has MySQL-backed accounts, teams and repository Read/Write/Owner access. Other storage/tracking/compute services require separate access controls. See [identity setup](users-and-repository-access.md).
- Documentation for released artifacts must distinguish a published release from newer source-checkout features, including anomaly model contracts.

For operational details, use the [deployment](deployment.md) and [persistence](migration.md) guides. None of the limits above is a claim that the existing demo workflow cannot be used locally.
