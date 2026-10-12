# Authoring a model workspace

This guide describes the current AI Studio checkout. A workspace is your model repository; a workbench is the model class it exports to the compute agent. The interfaces are framework-neutral: PyTorch, TensorFlow/Keras and other runtimes can implement the same lifecycle.

## Directory layout

Use a Python package for your implementation and keep discovery files at the workspace root:

```text
my-workspace/
├── ai-workbench.json       # Opt-in discovery marker
├── ai_workbench.py         # Exports MODEL_CLASS
├── requirements.txt        # Runtime dependencies to install in the agent
├── README.md
├── my_model/
│   ├── __init__.py
│   ├── config.py           # Pydantic config and supported option Enums
│   ├── model.py            # Interface implementation and network lifecycle
│   ├── train.py            # Training loop, progress, metrics and artifact saving
│   ├── infer.py            # Preprocessing and JSON-compatible predictions
│   ├── data.py             # Studio archive reader and dataset handling
│   ├── augmentor.py        # Optional training-time augmentation implementation
│   └── callbacks.py        # Optional callback implementations
└── tests/
    ├── test_config.py
    └── test_round_trip.py  # Train → save → reload → predict
```

`train.py` and `infer.py` are organizational conventions, not filenames the agent requires. The existing demos call them `trainer.py` and `inference.py`. Discovery imports the exported class and calls its methods; it does not launch these files as command-line scripts.

## Install and expose the workspace

Install the matching interfaces in the environment that executes your model. For development against this checkout:

```bash
pip install -e /path/to/ai-infra/libs/ai_interfaces
```

Install your framework and other dependencies in the compute-agent environment too. Discovery does not automatically install a workspace's `requirements.txt`. Published interface releases can lag behind the checkout; use a pinned compatible release for deployment.

Place the repository under the host `TRAINING_WORKSPACES_PATH` mounted by Compose, or under the native agent's `TRAINING_WORKSPACES_ROOT`. The workspace mount is read-only; use the agent-assigned output directory for generated files.

`ai-workbench.json`:

```json
{"entrypoint": "ai_workbench.py:MODEL_CLASS"}
```

`ai_workbench.py`:

```python
from my_model.model import MyClassifier

MODEL_CLASS = MyClassifier
```

Keep module imports quick and quiet: discovery imports this file to inspect the class and config. Do not start training, download weights or allocate a GPU at import time. The entrypoint must be a root-level Python file; imported implementation code can live in packages below it.

## config.py

Subclass `BaseModelConfig` and put every user-adjustable setting here. Use descriptions for field help, defaults for optional input, and constraints for validation. Declare the callbacks and augmentation keys your implementation actually supports as string Enums.

```python
from enum import Enum
from pydantic import Field, field_validator
from ai_interfaces import BaseModelConfig


class Callback(str, Enum):
    CHECKPOINT = "checkpoint"
    EARLY_STOPPING = "early_stopping"


class Augmentation(str, Enum):
    BLUR = "blur"
    FLIP = "flip"


class FlipDirection(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class ModelConfig(BaseModelConfig):
    channels: int = Field(default=16, ge=4, le=128,
                          description="Feature channels in the network backbone.")
    callbacks: list[Callback] = Field(default=[],
                                     description="Callbacks enabled during training.")
    augmentations: dict[Augmentation, float | FlipDirection] = Field(
        default={}, description="Training-only transforms and their settings.")

    @field_validator("augmentations")
    @classmethod
    def validate_augmentations(cls, options):
        for option, value in options.items():
            if option == Augmentation.BLUR:
                if not isinstance(value, (int, float)) or not 0 <= value <= 10:
                    raise ValueError("blur must be a number between 0 and 10")
            elif option == Augmentation.FLIP:
                if not isinstance(value, FlipDirection):
                    raise ValueError("flip must be horizontal or vertical")
        return options
```

The configuration still serializes as ordinary JSON:

```json
{"callbacks": ["checkpoint"], "augmentations": {"blur": 1, "flip": "vertical"}}
```

Enum annotations restrict callback names and augmentation keys. Key-specific validators restrict their values. To expose per-augmentation descriptions and ranges in the information popup, add JSON-schema `properties`; the [demo config](../tests/demo_support/config.py) shows this alongside typed-dictionary validation.

Do not declare an option unless training implements it. If your model has no callbacks or augmentations, omit the corresponding field; Studio will not add it. TensorBoard and Grad-CAM are optional implementations, not built-in obligations for TensorFlow workspaces.

Studio supplies `dataset_path`, `output_path`, `mlflow_url`, `project_id`, `dataset_version_id`, `class_names` and `devices`. The base config also supplies common training settings such as epochs, batch size, learning rate and validation split. Other fields become editable controls from the Pydantic schema. Blank input uses defaults; an explicit empty callback list stays empty.

## model.py

The model class connects the interfaces to your implementation. This classification skeleton deliberately leaves framework-specific network and weight handling to you:

```python
from pathlib import Path
from ai_interfaces import ImageClassificationModel, ModelDescriptor
from my_model.config import ModelConfig
from my_model.train import train
from my_model.infer import predict


class MyClassifier(ImageClassificationModel[ModelConfig]):
    config_type = ModelConfig

    @classmethod
    def descriptor(cls):
        return ModelDescriptor(
            key="my-classifier", name="My classifier",
            task="image_classification",
            description="A classifier implemented in this workspace.",
        )

    def build_network(self):
        # Build a torch.nn.Module or tf.keras.Model using self.config.
        raise NotImplementedError("Implement the network architecture")

    def train(self, context):
        return train(self, context)

    def load(self, artifact: Path):
        # Restore architecture, preprocessing and weights from the artifact.
        # Set self.network to the restored model.
        raise NotImplementedError("Implement artifact loading")

    def predict(self, image: Path):
        return predict(self, image)
```

All four lifecycle methods—`descriptor`, `train`, `load`, `predict`—must be implemented. Use a stable descriptor key and one of the supported task names:

| Task | Model base class | Config base class |
| --- | --- | --- |
| `image_classification` | `ImageClassificationModel` | `BaseModelConfig` |
| `object_detection` | `ObjectDetectionModel` | `BaseModelConfig` |
| `anomaly_detection` | `AnomalyDetectionModel` | `AnomalyModelConfig` |

Anomaly models use no class names. Their datasets are unsupervised; do not assume annotation labels exist.

## train.py

Training runs in the compute-agent service, independently of the browser. Read the immutable ZIP from `context.dataset.archive`, build the network, train it, then return a `TrainingResult`. The following is pseudocode: dataset, optimizer, callback and serialization helpers are workspace-owned implementations.

```python
from ai_interfaces import ModelArtifact, TrainingResult


def train(model, context):
    config = model.config
    context.output_dir.mkdir(parents=True, exist_ok=True)
    report = context.report_progress or (lambda **event: None)
    report(phase="preparing", message="Loading training data")

    # Parse the archive; create a validation subset of the training data only.
    train_data, validation_data = load_training_data(
        context.dataset.archive, config)
    model.network = model.build_network()
    augmentor = build_augmentor(config.augmentations)
    callbacks = build_callbacks(config.callbacks, config, context.output_dir)

    metrics = {}
    for epoch in range(config.epochs):
        report(phase="training", message=f"Epoch {epoch + 1}/{config.epochs}")
        train_loss = train_epoch(model.network, train_data, augmentor, config)
        report(phase="validating", message="Evaluating validation data")
        metrics = {"train_loss": float(train_loss)}
        if validation_data is not None:
            metrics["validation_loss"] = float(
                validate_epoch(model.network, validation_data, config))
        report(phase="training", message=f"Epoch {epoch + 1} complete",
               metrics=metrics, epoch=epoch + 1, epochs=config.epochs)
        # Invoke enabled callbacks; honor early stopping if implemented.
        invoke_callbacks(callbacks, model, epoch, metrics)

    report(phase="saving", message="Saving model")
    artifact = context.output_dir / "model.bin"
    save_model(model, artifact)  # Implement reloadable framework serialization.
    return TrainingResult(metrics=metrics, artifact=ModelArtifact(artifact),
                          summary="Training finished")
```

The archive contains an `annotations/*.json` manifest and image assets. Use the manifest's paths and categories rather than assuming folder names are labels. The [demo data reader](../tests/demo_support/data.py) is a concrete reference. Validate ZIP paths if extracting files.

Studio records the train/test partition and sends only the training partition to the trainer. A validation split may be drawn from that subset. Test images must not enter fitting, augmentation statistics, threshold calibration or early stopping.

Apply augmentations during training sample loading; keep validation and inference preprocessing deterministic. Preserve bounding-box alignment for detection transforms. Honor requested devices, or report unsupported devices clearly.

Metrics must be finite numeric values. Progress reports are optional structured events; arbitrary stdout is not automatically captured. Save the final artifact beneath `context.output_dir`; the current agent accepts a single artifact file up to 512 MiB. Bundle auxiliary files if needed, and implement corresponding loading. Avoid depending on temporary training paths when reloading.

## infer.py

Prediction receives one image path after `load()` has restored the saved model. Use the same resize, normalization and label mapping used during training. Return Python dictionaries and ordinary numbers, not framework tensors.

```python
from pathlib import Path


def predict(model, image: Path):
    # These helpers are implemented by your workspace.
    inputs = preprocess_image(image, model.config)
    scores = predict_scores(model.network, inputs)
    return [
        {"class_name": name, "score": float(score)}
        for name, score in zip(model.config.class_names, scores)
    ]
```

The saved-model evaluator expects these result shapes:

```python
# Classification: return class names and confidence scores.
[{"class_name": "cat", "score": 0.92}]

# Detection: boxes in original image pixels, [x, y, width, height].
[{"class_name": "cat", "score": 0.92, "bbox": [12.0, 20.0, 80.0, 60.0]}]

# Anomaly: an image-level score, optionally a flag.
[{"anomaly_score": 0.73, "is_anomaly": True}]
```

Use the published class names exactly. Map detection boxes back to the original image size. All values must be finite and JSON-serializable. The current evaluator uses a fixed confidence threshold of 0.5 for classification and detection, and class-matched IoU of 0.5 for detection; see [evaluation policy](training-jobs-and-evaluation.md).

## Verify the integration

Before selecting the workspace in Studio:

1. Import `MODEL_CLASS` inside the compute-agent environment and inspect `config_type.model_json_schema()`.
2. Validate defaults, supported Enum values, invalid values and JSON round trips.
3. Train on a tiny archive and check that the returned artifact exists under the assigned output directory.
4. Create a fresh model instance, call `load(artifact)`, then `predict(image)` and verify its output shape and label mapping.
5. Select the discovered workspace in Studio; verify its fields, descriptions and defaults, then run training and saved-model evaluation.

See the [PyTorch workspaces](../tests/README.md) for working implementations and [training jobs and evaluation](training-jobs-and-evaluation.md) for progress, persistence and recovery behavior.
