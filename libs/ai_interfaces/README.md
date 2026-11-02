# ai-infra interfaces

Framework-neutral abstract base classes used by the labeller and training agents. Use
this package in each ML repository that you want the training platform to discover.

## Install

Install the current feature branch while developing:

```bash
pip install "ai-infra-interfaces @ git+https://github.com/wecet/ai-infra.git@ai-interfaces-v0.4.0#subdirectory=libs/ai_interfaces"
```

Or install the wheel attached to the GitHub Release:

```bash
pip install "https://github.com/wecet/ai-infra/releases/download/ai-interfaces-v0.4.0/ai_infra_interfaces-0.4.0-py3-none-any.whl"
```

Release tags and wheel assets are immutable inputs for reproducible workbenches. Avoid
installing from a moving branch in production.

## Create a discoverable workbench

For a full directory layout and separate `config.py`, `model.py`, `train.py` and
`infer.py` skeletons, see [Workspace authoring](../../docs/workspace-authoring.md).

Each repository needs exactly two integration files at its root:

```text
my-vision-repository/
├── ai-workbench.json
├── ai_workbench.py
└── your_model_package/
```

Copy [`workbench.example.json`](workbench.example.json) to `ai-workbench.json`. It
points discovery at the exported model class:

```json
{
  "entrypoint": "ai_workbench.py:MODEL_CLASS"
}
```

Then define the Pydantic configuration and model export in `ai_workbench.py`:

```python
from pathlib import Path
from typing import Literal
from ai_interfaces import (
    BaseModelConfig, DatasetVersion, ImageClassificationModel,
    ModelArtifact, ModelDescriptor, TrainingContext, TrainingResult,
)

class ResNetConfig(BaseModelConfig):
    architecture: Literal["resnet18", "resnet50"] = "resnet18"
    pretrained: bool = True
    dropout: float = 0.1

class ResNetClassifier(ImageClassificationModel[ResNetConfig]):
    config_type = ResNetConfig

    @classmethod
    def descriptor(cls):
        return ModelDescriptor(
            key="resnet-classifier",
            name="ResNet classifier",
            task="image_classification",
            description="Fine-tunes a pretrained ResNet classifier.",
        )

    def train(self, context: TrainingContext):
        # Read context.dataset.archive, train using self.config, and write only
        # beneath context.output_dir.
        artifact = context.output_dir / "model.pt"
        artifact.write_bytes(b"replace with trained weights")
        return TrainingResult(
            metrics={"validation_accuracy": 0.0},
            artifact=ModelArtifact(artifact),
        )

    def load(self, artifact: Path):
        pass

    def predict(self, image: Path):
        return []


MODEL_CLASS = ResNetClassifier
```

`BaseModelConfig` includes the dataset path, output path, MLflow URL, project and
dataset-version IDs, class names, devices, epochs, batch size, learning rate, weight
decay, image size, random seed, and validation split. Model packages extend it with
every configurable architecture or preprocessing option. Extra fields are rejected,
so a job cannot silently pass an unsupported hyperparameter.

The platform automatically fills these infrastructure-owned fields from the selected
published labelling version:

- `dataset_path`
- `output_path`
- `mlflow_url`
- `project_id`
- `dataset_version_id`
- `class_names`
- `devices`

Every other property in your Pydantic model becomes an editable field in the Training
UI. Defaults, numeric limits, booleans, and `Literal` choices come from Pydantic's JSON
Schema. Keep all configurable preprocessing, architecture, optimizer, and training
options in the config class rather than reading ad-hoc environment variables.

## Discovery and compatibility

The Compose stack mounts the host directory configured by `TRAINING_WORKSPACES_PATH`
read-only. In the local `.env` this is `/Users/owenagius/Documents`. The agent searches
at most six directories deep for explicit `ai-workbench.json` markers and inspects at
most 100 workbenches.

The marker is an opt-in trust boundary: its entrypoint is imported in a time-limited
subprocess to verify the ABC and extract the Pydantic schema. Only select workbenches
whose code you trust. Imports must succeed inside the training-agent environment, so
framework dependencies such as PyTorch must be installed in the agent image used for
that workbench.

Both task types remain visible in the UI. An object-detection workbench is disabled in
an image-classification project, and vice versa. Invalid imports, missing abstract
methods, and unavailable dependencies are also shown as disabled instead of being
silently omitted.

During training, the model must write its final artifact beneath
`TrainingContext.output_dir`. Artifacts outside that directory or larger than 512 MiB
are rejected.

Keeping framework objects behind this boundary lets a workspace use PyTorch,
TensorFlow, ONNX, or a custom runtime without changing the infrastructure contract.

Callback and augmentation controls belong to each workbench's `config_type`, not
to the framework or the Studio defaults. Omit either field when unsupported.
Workspace `config.py` should list supported callbacks and augmentation keys as string
Enums and use them in its Pydantic field types:

```python
from enum import Enum
from pydantic import Field

class Callback(str, Enum):
    CHECKPOINT = "checkpoint"
    EARLY_STOPPING = "early_stopping"

class Augmentation(str, Enum):
    BLUR = "blur"
    FLIP = "flip"

class FlipDirection(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"

class Config(BaseModelConfig):
    callbacks: list[Callback] = Field(default=[], description="Enabled training callbacks.")
    augmentations: dict[Augmentation, float | FlipDirection] = Field(
        default={}, description="Training augmentation options and their settings.")
```

Add key-specific validation for augmentation settings (for example, blur must be a
nonnegative number and flip must be a direction). The demos combine enum keys with
typed-dictionary validation and JSON-schema properties for per-option descriptions
and limits. Studio resolves callback enums and augmentation `propertyNames` enums
for workspace-specific choices and help. Augmentation values remain a JSON editor.
Older Literal/typed-dictionary configs remain compatible. Declaring an option does
not implement it: the workbench must apply it during training.

### Anomaly detection

Unsupervised workbenches declare `task="anomaly_detection"`, subclass `AnomalyDetectionModel`, and use `AnomalyModelConfig` (or a subclass). It preserves the shared lifecycle while allowing an empty `class_names` tuple. Supervised `BaseModelConfig` still requires classes. The default anomaly `validation_split` is zero because the dataset's partitions are already frozen.

Published anomaly archives contain unlabelled image records in `annotations/*.json`, with empty `categories` and `annotations`. Each image includes `split: "train"` or `split: "test"`; `info` records the split ratio, seed, and partition sizes. Fit and calibrate using training records only. Use test records for held-out scoring. Return predictions such as `{"anomaly_score": 0.8, "is_anomaly": true}`; implementations may additionally return heatmaps.

### Live progress events

`TrainingContext.report_progress` is optional. Use it to report lifecycle phases, log messages and finite numeric metrics without coupling training to a browser or logging service. Existing implementations remain compatible when the callback is absent. The demos report batches/epochs, validation and saving. See [Training jobs and evaluation](../../docs/training-jobs-and-evaluation.md) for the event example and evaluation prediction requirements.

Saved-model evaluation expects JSON-serialisable predictions: classification records use `class_name` and `score`; detection additionally uses `bbox=[x, y, width, height]` in original image pixels; anomaly records use a finite `anomaly_score` and optional `is_anomaly`. The evaluator runs `load(artifact)` before `predict(image)` and uses the saved effective configuration. Workbenches must remain available on the run's agent.

## Dataset-analysis contracts (v0.4.0)

Two further contracts sit beside the training models. They follow the same rules:
framework-neutral, strict Pydantic configuration, and large outputs written as files.
Platform integration (discovery, jobs and AI Studio views) lands separately; these are
the stable shapes implementations build against.

### `EmbeddingWorkbench` — task `"embedding"`

Turns every image in a published dataset version into one vector, for similarity
search, duplicate and outlier detection, and dataset maps.

```python
from ai_interfaces import (
    EMBEDDING_TASK, EmbeddingConfig, EmbeddingResult, EmbeddingSet,
    EmbeddingWorkbench, ModelDescriptor,
)

class DinoConfig(EmbeddingConfig):
    backbone: str = "dinov2-small"

class DinoEmbedder(EmbeddingWorkbench[DinoConfig]):
    config_type = DinoConfig

    @classmethod
    def descriptor(cls):
        return ModelDescriptor("dinov2", "DINOv2 embeddings", EMBEDDING_TASK, "Self-supervised ViT features")

    def embed(self, context):
        # Write a float32 (n_images, dim) .npy under context.output_dir.
        return EmbeddingResult(EmbeddingSet(context.output_dir / "embeddings.npy", image_ids, 384, "dinov2"))

    def embed_images(self, images):
        ...  # vectors in the same space, for ad-hoc queries
```

`EmbeddingConfig` carries the infrastructure fields plus `batch_size`, `image_size`
and `normalize`. `EmbeddingSet` records the file, row order (`image_ids`), dimension,
model and distance metric.

### `SampleSelector` — task `"sample_selection"`

Ranks unlabelled images to label next within a budget (active learning).
`SelectionContext` gives the candidate pool, already-labelled ids, the budget and,
when available, the current model's predictions and an `EmbeddingSet`. Selectors must
work when either is missing.

`select()` returns `SampleSuggestion`s carrying rank, score, a short reason and the
model key, version and confidence they came from. Suggestions are never accepted
annotations. `validate_selection(context, result)` checks a result is legal: within
budget, candidates only, no duplicates, ranks 1..n.
