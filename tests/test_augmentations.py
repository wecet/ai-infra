"""Check config validation and image/box alignment for training augmentations."""
import pytest
import torch
from pydantic import ValidationError

from pytorch_classification.augmentor import Augmentor as ClassificationAugmentor
from pytorch_classification.config import ClassificationConfig
from pytorch_detection.augmentor import Augmentor as DetectionAugmentor
from pytorch_detection.config import DetectionConfig
from demo_support.config import Augmentation, Callback


def config(model_type, **options):
    return model_type(dataset_path="dataset.zip", output_path="output", project_id="demo", dataset_version_id="v1", class_names=("red",), **options)


@pytest.mark.parametrize("direction,expected", [("horizontal", [5, 1, 7, 4]), ("vertical", [1, 2, 3, 5]), ("both", [5, 2, 7, 5])])
def test_flips_keep_boxes_and_labels_aligned(direction, expected):
    image = torch.arange(144, dtype=torch.float32).reshape(3, 6, 8) / 144
    target = {"boxes": torch.tensor([[1., 1., 3., 4.]]), "labels": torch.tensor([1])}
    augmentor = DetectionAugmentor(config(DetectionConfig, augmentations={"flip": direction, "flip_probability": 1}))
    augmented, labels = augmentor(image, target)
    dimensions = [-1] if direction == "horizontal" else [-2] if direction == "vertical" else [-1, -2]
    torch.testing.assert_close(augmented, image.flip(dimensions))
    torch.testing.assert_close(labels["boxes"], torch.tensor([expected], dtype=torch.float32))
    assert labels["labels"].tolist() == [1] and target["boxes"].tolist() == [[1, 1, 3, 4]]


def test_photometric_rotation_and_empty_targets():
    options = {"blur": 1, "rotation": 45, "brightness": 0.2, "contrast": 0.2, "saturation": 0.2}
    image = torch.rand(3, 16, 20)
    labels = torch.tensor([1.])
    transformed, result = ClassificationAugmentor(config(ClassificationConfig, augmentations=options))(image, labels)
    assert transformed.shape == image.shape and result is labels
    assert torch.isfinite(transformed).all() and (0 <= transformed).all() and (transformed <= 1).all()
    negative = {"boxes": torch.empty(0, 4), "labels": torch.empty(0, dtype=torch.int64)}
    transformed, result = DetectionAugmentor(config(DetectionConfig, augmentations=options))(image, negative)
    assert transformed.shape == image.shape and result["boxes"].shape == (0, 4) and result["labels"].shape == (0,)
    tiny, _ = ClassificationAugmentor(config(ClassificationConfig, augmentations={"blur": 10}))(torch.ones(3, 1, 1), labels)
    assert torch.isfinite(tiny).all()


def test_config_defaults_and_invalid_options():
    for model_type in (ClassificationConfig, DetectionConfig):
        defaults = config(model_type)
        assert defaults.augmentations == {} and defaults.callbacks == ["tensorboard", "gradcam"]
        assert config(model_type, callbacks=[]).callbacks == []
        for invalid in ({"augmentations": {"blur": -1}}, {"augmentations": {"flip": "diagonal"}},
                        {"augmentations": {"unknown": 1}}, {"callbacks": ["unknown"]}):
            with pytest.raises(ValidationError):
                config(model_type, **invalid)


def test_enum_options_are_exported_and_round_trip_as_json():
    for model_type in (ClassificationConfig, DetectionConfig):
        value = config(model_type, augmentations={"blur": 1, "flip": "vertical"})
        assert all(isinstance(key, Augmentation) for key in value.augmentations)
        assert all(isinstance(item, Callback) for item in value.callbacks)
        assert value.model_dump(mode="json")["augmentations"] == {"blur": 1.0, "flip": "vertical"}
        schema = model_type.model_json_schema()
        assert schema["$defs"]["Callback"]["enum"] == ["tensorboard", "gradcam"]
        assert schema["$defs"]["Augmentation"]["enum"] == [item.value for item in Augmentation]
        assert schema["properties"]["augmentations"]["propertyNames"]["$ref"] == "#/$defs/Augmentation"


def test_valid_subpixel_boxes_survive_augmentation():
    image = torch.rand(3, 6, 8)
    target = {"boxes": torch.tensor([[1., 1., 1.2, 1.3]]), "labels": torch.tensor([1])}
    for options in ({}, {"flip": "vertical", "flip_probability": 1}):
        _, transformed = DetectionAugmentor(config(DetectionConfig, augmentations=options))(image, target)
        assert transformed["boxes"].shape == (1, 4) and transformed["labels"].tolist() == [1]
