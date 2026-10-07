import io
import json
import zipfile

from fastapi.testclient import TestClient
from PIL import Image

import app
from workbenches import discover_workbenches


def dataset_zip():
    image = io.BytesIO()
    Image.new("RGB", (8, 8), (220, 80, 60)).save(image, format="PNG")
    coco = {"images": [{"id": 1, "file_name": "images/sample.png", "width": 8,
                         "height": 8, "category_ids": [1]}], "annotations": [],
            "categories": [{"id": 1, "name": "coral"}]}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("images/sample.png", image.getvalue())
        bundle.writestr("annotations/dataset.json", json.dumps(coco))
    return archive.getvalue()


def test_capabilities_and_classification_training():
    client = TestClient(app.app)
    capabilities = client.get("/api/v1/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["cpu"]["available"] is True
    manifest = {"annotation_type": "image_classification", "base_model": "histogram-centroid-v1",
                "devices": ["cpu"], "hyperparameters": {"epochs": 1}, "config": {
                    "dataset_path": "/workspace/dataset.zip", "output_path": "/workspace/output",
                    "project_id": "project", "dataset_version_id": "version", "class_names": ["coral"],
                    "devices": ["cpu"], "epochs": 1}}
    response = client.post("/api/v1/train", data={"manifest": json.dumps(manifest)},
                           files={"dataset": ("dataset.zip", dataset_zip(), "application/zip")})
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["metrics"]["samples"] == 1
    assert response.json()["artifact"]["filename"] == "model.json"


def test_discovers_workbench_and_pydantic_schema(tmp_path):
    repository = tmp_path / "detector-workbench"; repository.mkdir()
    (repository / "ai-workbench.json").write_text('{"entrypoint":"ai_workbench.py:MODEL_CLASS"}')
    (repository / "ai_workbench.py").write_text('''
from pathlib import Path
from typing import Literal
from ai_interfaces import BaseModelConfig, ModelArtifact, ModelDescriptor, ObjectDetectionModel, TrainingResult
class Config(BaseModelConfig):
    backbone: Literal["tiny", "large"] = "tiny"
class Detector(ObjectDetectionModel[Config]):
    config_type = Config
    @classmethod
    def descriptor(cls): return ModelDescriptor("detector", "Detector", "object_detection", "Test detector")
    def train(self, context): return TrainingResult({}, ModelArtifact(context.output_dir / "model.bin"))
    def load(self, artifact: Path): pass
    def predict(self, image: Path): return []
MODEL_CLASS = Detector
''')
    found = discover_workbenches(tmp_path, refresh=True)
    assert len(found) == 1
    assert found[0]["available"] is True
    assert found[0]["task"] == "object_detection"
    assert found[0]["config_schema"]["properties"]["backbone"]["enum"] == ["tiny", "large"]


def test_invalid_workbench_remains_visible(tmp_path):
    repository = tmp_path / "broken"; repository.mkdir()
    (repository / "ai-workbench.json").write_text("{}")
    found = discover_workbenches(tmp_path, refresh=True)
    assert found[0]["available"] is False
    assert found[0]["reason"]
