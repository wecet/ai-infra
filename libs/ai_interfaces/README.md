# ai-infra interfaces

Framework-neutral abstract base classes used by the labeller and training agents. Use
this package in each ML repository that you want the training platform to discover.

## Install

Install the current feature branch while developing:

```bash
pip install "ai-infra-interfaces @ git+https://github.com/wecet/ai-infra.git@feature/model-training-workspace#subdirectory=libs/ai_interfaces"
```

For reproducible workbenches, replace the branch with a release tag or commit SHA.

## Create a discoverable workbench

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
