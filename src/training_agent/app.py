"""Portable compute agent. Deploy this same container on CPU or GPU hosts."""
import base64
import hashlib
import platform
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import uuid
from pathlib import Path

from contextlib import asynccontextmanager
import jobs as agent_jobs
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, ImageStat
from fastapi.responses import FileResponse
from ai_interfaces import AnomalyModelConfig, BaseModelConfig, DatasetVersion, TrainingContext
from pydantic import Field
from workbenches import discover_workbenches, find_workbench, load_model

RUNS_ROOT = Path(os.environ.get("TRAINING_RUNS_ROOT", "/tmp/training-runs"))
TENSORBOARD_URL = os.environ.get("TENSORBOARD_PUBLIC_URL", "")

def jobs_root(): return RUNS_ROOT / ".jobs"


@asynccontextmanager
async def lifespan(application):
    agent_jobs.recover(jobs_root(), {"training": execute_training, "evaluation": execute_evaluation})
    yield


app = FastAPI(title="ai-infra compute agent", lifespan=lifespan)

class AnomalyBaselineConfig(AnomalyModelConfig):
    threshold_quantile: float = Field(default=0.95, gt=0, le=1,
        description="Quantile of training anomaly scores used as the anomaly threshold.")


MODELS = {
    "anomaly_detection": [{
        "key": "colour-distance-anomaly-v1", "name": "Colour distance anomaly baseline",
        "description": "Unsupervised CPU baseline fitted only to the frozen training split; scores held-out images.",
        "defaults": {"threshold_quantile": 0.95},
    }],
    "image_classification": [{
        "key": "histogram-centroid-v1", "name": "Colour histogram centroid",
        "description": "Lightweight classification baseline for validating the training pipeline.",
        "defaults": {"epochs": 1, "batch_size": 32, "learning_rate": 0.001, "image_size": 224},
    }],
    "object_detection": [{
        "key": "class-box-prior-v1", "name": "Class box prior",
        "description": "Lightweight detection baseline that learns a representative box per class.",
        "defaults": {"epochs": 1, "batch_size": 16, "learning_rate": 0.001, "image_size": 640},
    }],
}

for task_name, task_models in MODELS.items():
    for model in task_models:
        model.update({"task": task_name, "workspace": "Bundled", "available": True,
                      "config_schema": (AnomalyBaselineConfig if task_name == "anomaly_detection" else BaseModelConfig).model_json_schema()})


def gpu_available():
    override = os.environ.get("TRAINING_GPU_AVAILABLE", "").lower()
    if override in {"1", "true", "yes"}: return True
    if override in {"0", "false", "no"}: return False
    if Path("/dev/nvidia0").exists(): return True
    try:
        return subprocess.run(["nvidia-smi", "-L"], capture_output=True, timeout=2).returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


@app.get("/health")
def health(): return {"status": "ok"}


@app.get("/api/v1/capabilities")
def capabilities():
    gpu = gpu_available()
    return {"cpu": {"available": True}, "gpu": {"available": gpu,
            "reason": "GPU runtime is not exposed to this agent" if not gpu else "GPU runtime detected"},
            "models": MODELS, "workbenches": discover_workbenches(),
            "tensorboard": {"available": bool(TENSORBOARD_URL), "url": TENSORBOARD_URL},
            "capacity": agent_jobs.capacity(), "async_jobs": True, "workspace_root": os.environ.get("TRAINING_WORKSPACES_ROOT", "/workspaces")}


def _classification(coco, root):
    sums, counts = {}, {}
    by_id = {item["id"]: item for item in coco["images"]}
    for record in by_id.values():
        with Image.open(root / record["file_name"]) as image:
            rgb = image.convert("RGB").resize((32, 32))
            feature = [sum(channel) / len(channel) for channel in zip(*list(rgb.get_flattened_data()))]
        for category in record.get("category_ids", []):
            sums.setdefault(str(category), [0.0, 0.0, 0.0])
            sums[str(category)] = [a + b for a, b in zip(sums[str(category)], feature)]
            counts[str(category)] = counts.get(str(category), 0) + 1
    centroids = {key: [value / counts[key] for value in values] for key, values in sums.items()}
    return {"kind": "histogram-centroid-v1", "centroids": centroids}, {"classes_trained": float(len(centroids)), "samples": float(len(by_id))}


def anomaly_feature(path):
    with Image.open(path) as image:
        return [value / 255 for value in ImageStat.Stat(image.convert("RGB").resize((32, 32))).mean]


def anomaly_score(feature, centroid):
    return sum((a - b) ** 2 for a, b in zip(feature, centroid)) ** 0.5


def _anomaly(coco, root, config):
    records = coco["images"]
    if any(record.get("split") not in {"train", "test"} for record in records):
        raise HTTPException(422, "Anomaly datasets require a frozen train/test split on every image")
    features = [(record["split"], anomaly_feature(root / record["file_name"])) for record in records]
    train_features = [feature for split, feature in features if split == "train"]
    if not train_features:
        raise HTTPException(422, "The published anomaly dataset has no training images")
    centroid = [sum(values) / len(train_features) for values in zip(*train_features)]
    train_scores = sorted(anomaly_score(feature, centroid) for feature in train_features)
    import math
    threshold = train_scores[max(0, math.ceil(len(train_scores) * config.threshold_quantile) - 1)]
    test_scores = [anomaly_score(feature, centroid) for split, feature in features if split == "test"]
    metrics = {"train_samples": float(len(train_features)), "test_samples": float(len(test_scores)),
               "train_mean_anomaly_score": sum(train_scores) / len(train_scores), "anomaly_threshold": threshold}
    if test_scores:
        metrics.update(test_mean_anomaly_score=sum(test_scores) / len(test_scores),
                       test_flagged_fraction=sum(score > threshold for score in test_scores) / len(test_scores))
    return {"kind": "colour-distance-anomaly-v1", "feature": "mean RGB / 255 after 32x32 resize",
            "centroid": centroid, "threshold": threshold, "score": "euclidean_distance", "anomaly_rule": "score > threshold"}, metrics


def _detection(coco, root):
    sums, counts = {}, {}
    images = {item["id"]: item for item in coco["images"]}
    for ann in coco.get("annotations", []):
        image = images[ann["image_id"]]; x, y, w, h = ann["bbox"]
        box = [x / image["width"], y / image["height"], w / image["width"], h / image["height"]]
        key = str(ann["category_id"]); sums.setdefault(key, [0.0] * 4)
        sums[key] = [a + b for a, b in zip(sums[key], box)]; counts[key] = counts.get(key, 0) + 1
    priors = {key: [value / counts[key] for value in values] for key, values in sums.items()}
    return {"kind": "class-box-prior-v1", "priors": priors}, {"classes_trained": float(len(priors)), "annotations": float(sum(counts.values()))}


@app.post("/api/v1/train")
def train(manifest: str = Form(...), dataset: UploadFile = File(...)):
    return train_model(manifest, dataset)


def file_digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def workbench_digest(workbench):
    if not workbench or not workbench.get("path"): return None
    root = Path(workbench['path'])
    digest = hashlib.sha256()
    for path in sorted([*root.rglob('*.py'), root / 'ai-workbench.json']):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            with path.open('rb') as stream: digest.update(hashlib.file_digest(stream, 'sha256').digest())
    return digest.hexdigest()


def train_model(manifest, dataset, report=None, binary=False):
    try: config = json.loads(manifest)
    except json.JSONDecodeError as exc: raise HTTPException(422, "Invalid training manifest") from exc
    task = config.get("annotation_type"); model_key = config.get("base_model")
    builtin = model_key in {m["key"] for m in MODELS.get(task, [])}
    workbench = find_workbench(model_key) if isinstance(model_key, str) and model_key.startswith("workspace:") else None
    if not builtin and not workbench: raise HTTPException(422, "Model workbench is unavailable on this compute agent")
    if workbench and workbench["task"] != task: raise HTTPException(422, "Workbench task does not match this project")
    if "gpu" in config.get("devices", []) and not gpu_available(): raise HTTPException(409, "GPU is unavailable on this compute agent")
    try: model_class = load_model(workbench) if workbench else None
    except Exception as exc: raise HTTPException(500, f"Model could not be loaded: {type(exc).__name__}: {exc}") from exc
    config_type = model_class.config_type if model_class else (AnomalyBaselineConfig if task == "anomaly_detection" else BaseModelConfig)
    try: model_config = config_type.model_validate(config.get("config", {}))
    except Exception as exc: raise HTTPException(422, f"Invalid model configuration: {exc}") from exc
    job_id = config.get("job_id", uuid.uuid4().hex)
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job_id):
        raise HTTPException(422, "Invalid job ID")
    run_name = config.get("run_name", job_id)
    if not isinstance(run_name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_name):
        raise HTTPException(422, "Invalid run name")
    effective = model_config
    if report: report(phase="preparing", message="Configuration validated")
    work = Path(tempfile.mkdtemp(prefix="training-"))
    try:
        archive = work / "dataset.zip"
        with archive.open("wb") as stream: shutil.copyfileobj(dataset.file, stream)
        with zipfile.ZipFile(archive) as bundle:
            if any(Path(name).is_absolute() or ".." in Path(name).parts for name in bundle.namelist()):
                raise HTTPException(422, "Unsafe dataset archive")
            bundle.extractall(work / "dataset")
        files = list((work / "dataset" / "annotations").glob("*.json"))
        if len(files) != 1: raise HTTPException(422, "Dataset must contain one COCO annotation file")
        coco = json.loads(files[0].read_text())
        if not model_class and task != 'anomaly_detection':
            fitting = {record['id'] for record in coco['images'] if record.get('split', 'train') == 'train'}
            coco['images'] = [record for record in coco['images'] if record['id'] in fitting]
            coco['annotations'] = [record for record in coco.get('annotations', []) if record['image_id'] in fitting]
        if report: report(phase="training", message=f"Training on {len(coco['images'])} images")
        if model_class:
            output = RUNS_ROOT / run_name
            try: output.mkdir(parents=True, exist_ok=False)
            except FileExistsError as exc: raise HTTPException(409, "Job ID already has a training run") from exc
            effective = model_config.model_copy(update={"dataset_path": archive, "output_path": output})
            model = model_class(effective)
            dataset_version = DatasetVersion(effective.project_id, effective.dataset_version_id,
                config.get("dataset_name", "dataset"), task, archive, coco.get("categories", []))
            result = model.train(TrainingContext(job_id, dataset_version, output,
                config.get("hyperparameters", {}), tuple(config.get("devices", ["cpu"])), report_progress=report))
            artifact_path = result.artifact.path.resolve(); artifact_path.relative_to(output.resolve())
            if not artifact_path.is_file() or artifact_path.stat().st_size > 512 * 1024 * 1024:
                raise HTTPException(422, "Workbench artifact is missing or exceeds 512 MiB")
            artifact = {"filename": artifact_path.name, "media_type": result.artifact.media_type,
                        **({'local_path': str(artifact_path)} if binary else {'content_base64': base64.b64encode(artifact_path.read_bytes()).decode()})}
            # Keep event files for live/history dashboards; the Studio stores the final artifact.
            if not binary: artifact_path.unlink()
            metrics, summary = dict(result.metrics), result.summary
        else:
            payload, metrics = (_anomaly(coco, work / "dataset", model_config) if task == "anomaly_detection" else _classification(coco, work / "dataset") if task == "image_classification"
                                else _detection(coco, work / "dataset"))
            payload.update({"model": model_key, "configuration": model_config.model_dump(mode="json"),
                            "hyperparameters": config.get("hyperparameters", {}), "classes": coco.get("categories", [])})
            artifact = {"filename": "model.json", "media_type": "application/json",
                        "content_base64": base64.b64encode(json.dumps(payload, indent=2).encode()).decode()}
            summary = "Reference model trained successfully"
        if report: report(phase="saving", metrics=metrics, message="Saving trained model")
        return {"status": "succeeded", "metrics": metrics, "artifact": artifact, "summary": summary, "config": effective.model_dump(mode="json"), "provenance": {
            "python": platform.python_version(), "platform": platform.platform(),
            "packages": {name: importlib.metadata.version(name) for name in ('fastapi', 'Pillow', 'ai-infra-interfaces')},
            "dataset_sha256": file_digest(archive),
            "workbench_sha256": workbench_digest(workbench)}}
    except (HTTPException, agent_jobs.Cancelled):
        raise
    except Exception as exc:
        raise HTTPException(500, f"Training failed: {type(exc).__name__}: {exc}") from exc
    finally: shutil.rmtree(work, ignore_errors=True)


def execute_training(manifest, directory, report):
    with (directory / "dataset.zip").open("rb") as stream:
        return train_model(json.dumps(manifest), UploadFile(filename="dataset.zip", file=stream), report, binary=True)


def execute_evaluation(manifest, directory, report):
    from evaluation import evaluate
    return evaluate(manifest, directory, report, find_workbench, load_model)


def request_manifest(manifest):
    try: value = json.loads(manifest)
    except ValueError as error: raise HTTPException(422, "Invalid job manifest") from error
    if not isinstance(value, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(value.get("job_id", ""))):
        raise HTTPException(422, "Invalid job ID")
    return value


@app.post("/api/v1/jobs", status_code=202)
def submit_job(manifest: str = Form(...), dataset: UploadFile = File(...)):
    value = request_manifest(manifest); value["kind"] = "training"
    return agent_jobs.start(jobs_root(), value["job_id"], value, dataset.file, execute_training)


@app.get("/api/v1/jobs/{job_id}")
def job_status(job_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job_id): raise HTTPException(422, "Invalid job ID")
    return agent_jobs.status(jobs_root(), job_id)


@app.get("/api/v1/jobs/{job_id}/result")
def job_result(job_id: str, binary: bool = False):
    job_status(job_id)
    return agent_jobs.result(jobs_root(), job_id, binary=binary)


@app.post("/api/v1/evaluations", status_code=202)
def submit_evaluation(manifest: str = Form(...), dataset: UploadFile = File(...), artifact: UploadFile = File(...)):
    value = request_manifest(manifest); value["kind"] = "evaluation"
    return agent_jobs.start(jobs_root(), value["job_id"], value, dataset.file, execute_evaluation, artifact.file)


@app.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job_status(job_id)
    return agent_jobs.cancel(jobs_root(), job_id)


@app.get('/api/v1/jobs/{job_id}/artifact')
def job_artifact(job_id: str):
    job_status(job_id)
    agent_jobs.result(jobs_root(), job_id, binary=True)
    path = jobs_root() / job_id / 'model.bin'
    if not path.is_file(): raise HTTPException(404, 'Artifact unavailable')
    return FileResponse(path, media_type='application/octet-stream')


@app.post('/api/v1/augmentation-preview')
def augmentation_preview(manifest: str = Form(...), image: UploadFile = File(...)):
    try:
        value = json.loads(manifest)
        if not isinstance(value, dict): raise ValueError('Manifest must be an object')
        with tempfile.TemporaryDirectory(prefix='augmentation-preview-') as temporary:
            root = Path(temporary)
            (root / 'manifest.json').write_text(json.dumps(value))
            with (root / 'image').open('wb') as output:
                shutil.copyfileobj(image.file, output)
            if (root / 'image').stat().st_size > 50 * 1024 * 1024: raise ValueError('Image exceeds 50 MiB')
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('preview.py')), str(root)], capture_output=True, text=True, timeout=60)
            if result.returncode: raise ValueError(result.stderr[-1500:])
            return json.loads(result.stdout)
    except (ValueError, subprocess.SubprocessError) as error:
        raise HTTPException(422, f'Invalid augmentation preview: {error}') from error
