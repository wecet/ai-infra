from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_interfaces import (
    BaseModelConfig,
    ImageClassificationModel,
    ModelArtifact,
    ModelDescriptor,
    TrainingResult,
)


class ExampleConfig(BaseModelConfig):
    backbone: str = "resnet18"


class ExampleClassifier(ImageClassificationModel[ExampleConfig]):
    config_type = ExampleConfig

    @classmethod
    def descriptor(cls):
        return ModelDescriptor("example", "Example", "image_classification", "Test model")

    def train(self, context):
        return TrainingResult({}, ModelArtifact(Path("model.bin")))

    def load(self, artifact): pass

    def predict(self, image): return []


def valid_config(**extra):
    return {"dataset_path": "/data/dataset.zip", "output_path": "/output",
            "project_id": "project", "dataset_version_id": "version",
            "class_names": ["cat", "dog"], **extra}


def test_model_validates_declared_config():
    model = ExampleClassifier(valid_config(epochs=3, backbone="resnet50"))
    assert model.config.epochs == 3
    assert model.config.backbone == "resnet50"


def test_unknown_config_is_rejected():
    with pytest.raises(ValidationError):
        ExampleClassifier(valid_config(typo_epochs=3))


def test_incomplete_implementation_is_abstract():
    with pytest.raises(TypeError):
        ImageClassificationModel(valid_config())


def test_anomaly_config_requires_no_labels_without_weakening_supervised_config():
    from ai_interfaces import AnomalyModelConfig
    values = valid_config(); values.pop('class_names')
    assert AnomalyModelConfig(**values).class_names == ()
    with pytest.raises(ValidationError):
        AnomalyModelConfig(**values, class_names=['normal'])
    with pytest.raises(ValidationError):
        BaseModelConfig(**values, class_names=[])
