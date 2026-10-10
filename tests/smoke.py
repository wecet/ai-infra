"""Run: tests/.venv/bin/python tests/smoke.py (CPU, synthetic data only)."""
import io
import json
import math
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import torch
from PIL import Image
from pydantic import ValidationError
from ai_interfaces import DatasetVersion, TrainingContext

from pytorch_classification.model import DemoClassifier
from pytorch_detection.model import DemoDetector
from demo_support.data import StudioDataset
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "training_agent"))
import workbenches


def demo():
    torch.set_num_threads(1)
    root = Path(__file__).resolve().parent
    discovered = workbenches.discover_workbenches(root, refresh=True)
    assert len(discovered) == 2 and all(item["available"] for item in discovered), discovered
    # Test the runtime loader as well as the isolated discovery subprocess.
    workbenches.ROOT = root
    assert {workbenches.load_model(item).descriptor().task for item in discovered} == {"image_classification", "object_detection"}
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        categories = [{"id": 7, "name": "red"}, {"id": 23, "name": "blue"}]
        for model_type in (DemoClassifier, DemoDetector):
            task = model_type.descriptor().task
            archive = directory / f"{task}.zip"
            records, annotations = [], []
            with ZipFile(archive, "w") as bundle:
                for index in range(4):
                    image = Image.new("RGB", (48, 40), "red" if index % 2 == 0 else "blue")
                    content = io.BytesIO()
                    image.save(content, format="PNG")
                    name = f"images/{index}.png"
                    bundle.writestr(name, content.getvalue())
                    labels = [7, 23] if index == 0 else ([] if index == 1 else [categories[index % 2]["id"]])
                    records.append({"id": index, "file_name": name, "width": 48, "height": 40, "category_ids": labels})
                    for category in labels:
                        annotations.append({"image_id": index, "category_id": category, "bbox": [4, 5, 20, 15]})
                bundle.writestr("annotations/demo.json", json.dumps({"categories": categories, "images": records, "annotations": annotations}))
            output = directory / task
            config = model_type.config_type(dataset_path=archive, output_path=output, project_id="demo",
                                            dataset_version_id="v1", class_names=("blue", "red"), epochs=2,
                                            batch_size=2, image_size=32, channels=4, score_threshold=0,
                                            augmentations={"blur": 0.5, "flip": "vertical", "flip_probability": 1, "rotation": 15})
            try:
                model_type.config_type.model_validate({**config.model_dump(), "unsupported": True})
            except ValidationError:
                pass
            else:
                raise AssertionError("Unknown hyperparameters must be rejected")
            dataset = StudioDataset(archive, config, task)
            if task == "image_classification":
                assert dataset[0][1].tolist() == [1, 1] and dataset[1][1].tolist() == [0, 0]
            else:
                assert dataset[0][1]["labels"].tolist() == [2, 1]
                assert dataset[1][1]["boxes"].shape == (0, 4)
            context = TrainingContext("smoke", DatasetVersion("demo", "v1", "demo", task, archive, categories), output, {})
            model = model_type(config)
            torch.manual_seed(config.random_seed)
            initial = model.build_network().state_dict()
            result = model.train(context)
            assert any(not torch.equal(initial[name], value) for name, value in model.network.state_dict().items())
            assert result.artifact.path.is_relative_to(output) and result.artifact.path.is_file()
            assert all(math.isfinite(value) for value in result.metrics.values())
            assert "validation_loss" in result.metrics
            assert {"epoch_seconds", "learning_rate"} <= result.metrics.keys()
            if task == "image_classification":
                assert 0 <= result.metrics["validation_label_accuracy"] <= 1
            else:
                assert {"train_loss_classifier", "validation_loss_box_reg", "train_loss_objectness", "validation_loss_rpn_box_reg"} <= result.metrics.keys()
            events = EventAccumulator(str(output / "tensorboard"), size_guidance={"images": 0}).Reload()
            assert {"Loss/batch", "Loss/train", "Loss/validation", "LearningRate"} <= set(events.Tags()["scalars"])
            assert {f"Metrics/{key}" for key in result.metrics} <= set(events.Tags()["scalars"])
            for tag in ("Loss/train", "Loss/validation"):
                values = events.Scalars(tag)
                assert [item.step for item in values] == [1, 2]
                assert all(math.isfinite(item.value) for item in values)
            assert {"GradCAM/sample_0/input", "GradCAM/sample_0/heatmap", "GradCAM/sample_0/overlay"} <= set(events.Tags()["images"])
            for tag in events.Tags()["images"]:
                assert len(events.Images(tag)) == config.epochs
            assert all(not module._forward_hooks for module in model.network.modules())
            image_path = directory / "image.png"
            Image.new("RGB", (48, 40), "red").save(image_path)
            before = model.predict(image_path)
            reloaded = model_type(config.model_copy(update={"channels": 8}))
            reloaded.load(result.artifact.path)
            assert before == reloaded.predict(image_path) and before
            json.dumps(before)
            for prediction in before:
                assert prediction["class_name"] in config.class_names and 0 <= prediction["score"] <= 1
                if task == "object_detection":
                    x, y, width, height = prediction["bbox"]
                    assert 0 <= x < x + width <= 48 and 0 <= y < y + height <= 40
            if task == "image_classification":
                for callbacks in ([], ["tensorboard"], ["gradcam"]):
                    disabled = model_type(config.model_copy(update={"callbacks": callbacks, "epochs": 1}))
                    disabled_output = directory / ("callback-" + "-".join(callbacks))
                    disabled.train(TrainingContext("disabled", context.dataset, disabled_output, {}))
                    if "tensorboard" in callbacks:
                        disabled_events = EventAccumulator(str(disabled_output / "tensorboard")).Reload()
                        assert disabled_events.Tags()["scalars"] and not disabled_events.Tags()["images"]
                    else:
                        assert not (disabled_output / "tensorboard").exists()
            print(f"PASS {task}: discovery, train, validation, reload, inference, TensorBoard, Grad-CAM; {result.metrics}")


if __name__ == "__main__":
    demo()
