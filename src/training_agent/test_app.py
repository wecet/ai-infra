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


def test_workbench_logs_persist_and_job_paths_are_validated(tmp_path, monkeypatch):
    from pathlib import Path
    from ai_interfaces import BaseModelConfig, ModelArtifact, TrainingResult
    class LoggingModel:
        config_type = BaseModelConfig

        def __init__(self, config):
            self.config = config

        def train(self, context):
            logs = context.output_dir / "tensorboard"
            logs.mkdir()
            (logs / "events.test").write_bytes(b"event data")
            artifact = context.output_dir / "model.bin"
            artifact.write_bytes(b"trained model")
            return TrainingResult({}, ModelArtifact(artifact))

    monkeypatch.setattr(app, "RUNS_ROOT", tmp_path / "runs")
    monkeypatch.setattr(app, "TENSORBOARD_URL", "http://localhost:6006")
    monkeypatch.setattr(app, "find_workbench", lambda key: {"task": "image_classification"})
    monkeypatch.setattr(app, "load_model", lambda workbench: LoggingModel)
    client = TestClient(app.app)
    assert client.get("/api/v1/capabilities").json()["tensorboard"] == {"available": True, "url": "http://localhost:6006"}
    manifest = {"job_id": "run-123", "run_name": "261010-test-v1", "annotation_type": "image_classification", "base_model": "workspace:test",
                "devices": ["cpu"], "config": {"dataset_path": "/dataset.zip", "output_path": "/output",
                "project_id": "project", "dataset_version_id": "version", "class_names": ["coral"]}}
    response = client.post("/api/v1/train", data={"manifest": json.dumps(manifest)},
                           files={"dataset": ("dataset.zip", dataset_zip(), "application/zip")})
    assert response.status_code == 200, response.text
    assert (app.RUNS_ROOT / "261010-test-v1/tensorboard/events.test").read_bytes() == b"event data"
    assert not (app.RUNS_ROOT / "261010-test-v1/model.bin").exists()
    assert response.json()["config"]["output_path"] == str(app.RUNS_ROOT / "261010-test-v1")
    assert response.json()["config"]["epochs"] == BaseModelConfig.model_fields["epochs"].default
    assert not Path(manifest["config"]["dataset_path"]).exists()
    assert client.post("/api/v1/train", data={"manifest": json.dumps(manifest)},
                       files={"dataset": ("dataset.zip", dataset_zip(), "application/zip")}).status_code == 409
    manifest["job_id"] = "../outside"
    assert client.post("/api/v1/train", data={"manifest": json.dumps(manifest)},
                       files={"dataset": ("dataset.zip", dataset_zip(), "application/zip")}).status_code == 422


def test_trainer_failure_returns_details_and_agent_remains_usable(tmp_path, monkeypatch):
    from ai_interfaces import BaseModelConfig

    class FailingModel:
        config_type = BaseModelConfig

        def __init__(self, config):
            pass

        def train(self, context):
            raise RuntimeError("Demo trainer failed: invalid batch")

    monkeypatch.setattr(app, "RUNS_ROOT", tmp_path / "runs")
    monkeypatch.setattr(app, "find_workbench", lambda key: {"task": "image_classification"})
    monkeypatch.setattr(app, "load_model", lambda workbench: FailingModel)
    client = TestClient(app.app)
    manifest = {"job_id": "failed-run", "annotation_type": "image_classification", "base_model": "workspace:test",
                "devices": ["cpu"], "config": {"dataset_path": "/dataset.zip", "output_path": "/output",
                "project_id": "project", "dataset_version_id": "version", "class_names": ["coral"]}}
    response = client.post("/api/v1/train", data={"manifest": json.dumps(manifest)},
                           files={"dataset": ("dataset.zip", dataset_zip(), "application/zip")})
    assert response.status_code == 500
    assert response.json()["detail"] == "Training failed: RuntimeError: Demo trainer failed: invalid batch"
    assert client.get("/health").status_code == 200
    manifest["base_model"] = "histogram-centroid-v1"
    assert client.post("/api/v1/train", data={"manifest": json.dumps(manifest)},
                       files={"dataset": ("dataset.zip", dataset_zip(), "application/zip")}).status_code == 200


def test_anomaly_training_uses_only_frozen_training_images():
    import base64
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as bundle:
        records = []
        for index, (split, colour) in enumerate([('train', (255, 0, 0)), ('test', (0, 0, 255))]):
            image = io.BytesIO(); Image.new('RGB', (8, 8), colour).save(image, 'PNG')
            path = f'images/{index}.png'; bundle.writestr(path, image.getvalue())
            records.append({'id': index, 'file_name': path, 'split': split, 'width': 8, 'height': 8})
        bundle.writestr('annotations/dataset.json', json.dumps({'images': records, 'categories': [], 'annotations': []}))
    manifest = {'annotation_type': 'anomaly_detection', 'base_model': 'colour-distance-anomaly-v1',
        'devices': ['cpu'], 'config': {'dataset_path': '/data/dataset.zip', 'output_path': '/output',
            'project_id': 'p', 'dataset_version_id': 'v', 'class_names': []}}
    client = TestClient(app.app)
    assert client.get('/api/v1/capabilities').json()['models']['anomaly_detection'][0]['available']
    response = client.post('/api/v1/train', data={'manifest': json.dumps(manifest)},
        files={'dataset': ('dataset.zip', archive.getvalue(), 'application/zip')})
    assert response.status_code == 200, response.text
    result = response.json()
    artifact = json.loads(base64.b64decode(result['artifact']['content_base64']))
    assert artifact['centroid'] == [1, 0, 0]  # Blue held-out image cannot influence fitting.
    assert result['metrics']['train_samples'] == result['metrics']['test_samples'] == 1
    assert result['metrics']['test_flagged_fraction'] == 1
    assert artifact['configuration']['class_names'] == []
    with zipfile.ZipFile(io.BytesIO(archive.getvalue())) as original:
        no_train = io.BytesIO()
        with zipfile.ZipFile(no_train, 'w') as bundle:
            for name in original.namelist():
                content = original.read(name)
                if name.endswith('.json'):
                    document = json.loads(content)
                    for item in document['images']: item['split'] = 'test'
                    content = json.dumps(document).encode()
                bundle.writestr(name, content)
    response = client.post('/api/v1/train', data={'manifest': json.dumps(manifest)},
        files={'dataset': ('dataset.zip', no_train.getvalue(), 'application/zip')})
    assert response.status_code == 422 and 'no training images' in response.json()['detail']


def test_discovers_unsupervised_anomaly_workbench(tmp_path):
    repository = tmp_path / 'anomaly-workbench'; repository.mkdir()
    (repository / 'ai-workbench.json').write_text('{"entrypoint":"ai_workbench.py:MODEL_CLASS"}')
    (repository / 'ai_workbench.py').write_text('''
from ai_interfaces import AnomalyDetectionModel, AnomalyModelConfig, ModelDescriptor
class Model(AnomalyDetectionModel):
    config_type = AnomalyModelConfig
    @classmethod
    def descriptor(cls): return ModelDescriptor("anomaly", "Anomaly", "anomaly_detection", "Unsupervised")
    def train(self, context): pass
    def load(self, artifact): pass
    def predict(self, image): return [{"anomaly_score": 0.0}]
MODEL_CLASS = Model
''')
    found = discover_workbenches(tmp_path, refresh=True)
    assert len(found) == 1 and found[0]['available'], found
    assert found[0]['task'] == 'anomaly_detection'
    assert found[0]['config_schema']['properties']['class_names']['default'] == []
