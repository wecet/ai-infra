# ai-infra interfaces

Framework-neutral abstract base classes used by the labeller and training agents. A
model package must subclass `ImageClassificationModel` or `ObjectDetectionModel`,
declare a Pydantic `config_type`, and implement `descriptor`, `train`, `load`, and
`predict`.

```python
from typing import Literal
from ai_interfaces import BaseModelConfig, ImageClassificationModel

class ResNetConfig(BaseModelConfig):
    architecture: Literal["resnet18", "resnet50"] = "resnet18"
    pretrained: bool = True
    dropout: float = 0.1

class ResNetClassifier(ImageClassificationModel[ResNetConfig]):
    config_type = ResNetConfig
    # descriptor, train, load and predict are required by the ABC.
```

`BaseModelConfig` includes the dataset path, output path, MLflow URL, project and
dataset-version IDs, class names, devices, epochs, batch size, learning rate, weight
decay, image size, random seed, and validation split. Model packages extend it with
every configurable architecture or preprocessing option. Extra fields are rejected,
so a job cannot silently pass an unsupported hyperparameter.

Install directly from a tagged checkout:

```bash
pip install "ai-infra-interfaces @ git+https://github.com/wecet/ai-infra.git@v1.0.0#subdirectory=libs/ai_interfaces"
```

Keeping framework objects behind this boundary lets a workspace use PyTorch,
TensorFlow, ONNX, or a custom runtime without changing the infrastructure contract.
