# Training jobs and saved-model evaluation

Implemented in this source checkout. Upgrade Studio and the compute agent together; older published images do not provide the asynchronous job protocol.

## Job ownership and recovery

**Start training** creates a persisted Studio job and returns promptly. Studio submits it to the compute agent's `/api/v1/jobs` endpoint. The agent owns execution, so closing a page, refreshing it, or disconnecting the browser does not cancel training.

The agent persists status, its recent 200 log messages, heartbeat, metrics and results under `TRAINING_RUNS_ROOT/.jobs/{job_id}`. Heartbeats are emitted every five seconds; Studio monitors approximately every two seconds and the browser polls every four seconds. Opening or returning to Training fetches the latest persisted state. Capability discovery no longer delays loading the job list.

Refreshing preserves the selected project and project tab within the browser tab, so Training reopens directly with the latest job state.

Submission is idempotent by job ID. Studio restart recovery checks for an existing agent job and reattaches to it instead of submitting it again. Temporary agent connection failures show reconnecting/delayed state. Consecutive outages are bounded by `AGENT_RECONNECT_SECONDS` (default 300); permanent HTTP errors finish the observer with a useful failure. Agent-owned work may still finish after an observer times out. A compute-agent/container restart cannot preserve an in-process trainer: interrupted work is explicitly marked failed and can be retried as a new run. Cooperative cancellation is available for queued/running jobs; trainers stop at their next progress callback. A trainer that never reports progress can only stop when it returns. Capacity is bounded by `TRAINING_MAX_CONCURRENT_JOBS` (default 1). Checkpoint resume remains future work. Legacy synchronous agents remain compatible but cannot provide live heartbeats/progress or the same restart guarantees.

The agent stores the uploaded training archive, status, logs and artifact/result files in the training-runs volume. Retain that volume when recreating services. Automatic retention and cleanup are not implemented.

## Progress contract

`TrainingContext.report_progress` is an optional callback for workbenches. Existing implementations remain valid without it; they still receive agent lifecycle phases and heartbeat updates. A trainer can report:

```python
if context.report_progress:
    context.report_progress(
        phase="training",
        message="Epoch 3/10 complete",
        metrics={"train_loss": 0.42, "validation_loss": 0.39},
        epoch=3,
        epochs=10,
    )
```

Use finite, JSON-serialisable numeric metrics. This callback is a structured event channel, not an automatic capture of arbitrary stdout. Both PyTorch demos report batches, epochs, validation and model saving; TensorBoard and Grad-CAM remain available through their existing callbacks.

Job cards show phase, elapsed time, heartbeat age and latest metric. Expand **Latest logs** or **All metrics** for details. Active runs can open live metrics when configured; successful runs expose model/download/tracking actions; failed runs can refill the form through **Retry configuration**. Cloning or retrying prepares a new configuration for review, rather than silently starting another run.

## Fixed held-out partition

New schema-v2 publications freeze train/validation/test membership with seed 42. Supervised validation reserves 20% of the non-test pool (at least one sample when that pool has three or more); anomaly datasets retain train/test only. Studio sends fitting and validation samples, excluding every test sample. The demo trainers honor the frozen split; bundled baselines fit only train samples. Custom workbenches must honor manifest splits. Legacy snapshots retain deterministic train/test fallback and their existing trainer-defined validation behavior.

Runs retain a snapshot hash, exact partition membership, effective configuration, Python/platform/package summary, archive hash and workbench source hash. Clone configuration preserves a parent-run ID and previews changes; it creates a new run only after Start training.

Older models without a recorded partition are not advertised as having a verified held-out evaluation. A new model with an empty test partition explains that limitation. Configure a ratio that yields test samples and train a new run to enable evaluation. Never relabel an image used for fitting as held out after the fact.

## Evaluation dialog

Click **View model**, a saved-model card, or a registered-model node in Lineage. When a model has a recorded test partition and an available artifact, Studio starts evaluation or loads its existing saved result. Evaluation continues if the dialog closes. Its result is tied to the model, training job, published version and exact held-out image IDs.

Evaluation executes on the run's compute agent. Workspace models must still be discoverable there and implement artifact loading and prediction. Inference uses CPU for the demo workbenches. Results are cached for that model and fixed partition; failed evaluations can be retried. All prediction/failure/flagged rows are retained. The browser displays 24 per page with source, class and confidence filters. Saved metrics remain fixed when filters or exploratory anomaly thresholds change.

| Task | Metrics and interpretation |
| --- | --- |
| Image classification | Exact-match accuracy for multi-label sets, micro precision/recall/F1 and TP/FP/FN; prediction score threshold 0.5 |
| Object detection | Class-matched precision/recall/F1 and TP/FP/FN at score ≥ 0.5 and IoU ≥ 0.5; greedy matching by descending score; this is not mAP |
| Anomaly detection | Mean/max anomaly score and flagged fraction when supplied by predictions; flags are not verified errors without ground truth |

Predictions show source images and expected labels. Detection overlays show predicted boxes plus expected boxes. Supervised failure examples are samples with label/box mismatches. Anomaly evaluation instead provides flagged examples, without claiming accuracy or failure labels.

## Verification

Tests cover client closure/reopening, idempotent submission, persisted progress, interrupted-agent reporting, reattachment, disjoint train/test archives, cached evaluation provenance, classification failures and complete anomaly predictions. The PyTorch smoke checks retain training, reload/inference, TensorBoard and Grad-CAM coverage. Browser checks should include both themes, page refresh during training, delayed heartbeat, model dialogs and legacy-model explanations.

## Working with saved results

Compare saved models in Training. Metrics are comparable only when task, immutable version, held-out membership and metric policy agree. Expand shared examples to inspect both models on the same image.

Send supervised failure examples to Model review. Suggestions retain their model/version/prediction, never replace annotations automatically, and can be assigned to active users with repository write access. Resolved and needs-changes tasks require a reason. Changes to live labels require a new publication and run; the original evaluation remains immutable. Activity records successful project mutations with the authenticated actor.

Augmentation preview uses the selected installed workbench's `augmentor.py:Augmentor` with its validated configuration in a separate process. The seed, before/after images and transformed boxes are shown. Unsupported workbenches explain why preview is unavailable.
