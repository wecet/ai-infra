"""Portable compute agent. Deploy this same container on CPU or GPU hosts."""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image
from ai_interfaces import BaseModelConfig, DatasetVersion, TrainingContext
from workbenches import discover_workbenches, find_workbench, load_model

RUNS_ROOT = Path(os.environ.get("TRAINING_RUNS_ROOT", "/tmp/training-runs"))
TENSORBOARD_URL = os.environ.get("TENSORBOARD_PUBLIC_URL", "")

app = FastAPI(title="ai-infra compute agent")

MODELS = {
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
                      "config_schema": BaseModelConfig.model_json_schema()})


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
            "workspace_root": os.environ.get("TRAINING_WORKSPACES_ROOT", "/workspaces")}


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
    try: config = json.loads(manifest)
    except json.JSONDecodeError as exc: raise HTTPException(422, "Invalid training manifest") from exc
    task = config.get("annotation_type"); model_key = config.get("base_model")
    builtin = model_key in {m["key"] for m in MODELS.get(task, [])}
    workbench = find_workbench(model_key) if isinstance(model_key, str) and model_key.startswith("workspace:") else None
    if not builtin and not workbench: raise HTTPException(422, "Model workbench is unavailable on this compute agent")
    if workbench and workbench["task"] != task: raise HTTPException(422, "Workbench task does not match this project")
    if "gpu" in config.get("devices", []) and not gpu_available(): raise HTTPException(409, "GPU is unavailable on this compute agent")
    model_class = load_model(workbench) if workbench else None
    config_type = model_class.config_type if model_class else BaseModelConfig
    try: model_config = config_type.model_validate(config.get("config", {}))
    except Exception as exc: raise HTTPException(422, f"Invalid model configuration: {exc}") from exc
    job_id = config.get("job_id", uuid.uuid4().hex)
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job_id):
        raise HTTPException(422, "Invalid job ID")
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
        if model_class:
            output = RUNS_ROOT / job_id
            try: output.mkdir(parents=True, exist_ok=False)
            except FileExistsError as exc: raise HTTPException(409, "Job ID already has a training run") from exc
            effective = model_config.model_copy(update={"dataset_path": archive, "output_path": output})
            model = model_class(effective)
            dataset_version = DatasetVersion(effective.project_id, effective.dataset_version_id,
                config.get("dataset_name", "dataset"), task, archive, coco.get("categories", []))
            result = model.train(TrainingContext(job_id, dataset_version, output,
                config.get("hyperparameters", {}), tuple(config.get("devices", ["cpu"]))))
            artifact_path = result.artifact.path.resolve(); artifact_path.relative_to(output.resolve())
            if not artifact_path.is_file() or artifact_path.stat().st_size > 512 * 1024 * 1024:
                raise HTTPException(422, "Workbench artifact is missing or exceeds 512 MiB")
            artifact = {"filename": artifact_path.name, "media_type": result.artifact.media_type,
                        "content_base64": base64.b64encode(artifact_path.read_bytes()).decode()}
            # Keep event files for live/history dashboards; the Studio stores the final artifact.
            artifact_path.unlink()
            metrics, summary = dict(result.metrics), result.summary
        else:
            payload, metrics = (_classification(coco, work / "dataset") if task == "image_classification"
                                else _detection(coco, work / "dataset"))
            payload.update({"model": model_key, "configuration": model_config.model_dump(mode="json"),
                            "hyperparameters": config.get("hyperparameters", {}), "classes": coco.get("categories", [])})
            artifact = {"filename": "model.json", "media_type": "application/json",
                        "content_base64": base64.b64encode(json.dumps(payload, indent=2).encode()).decode()}
            summary = "Reference model trained successfully"
        return {"status": "succeeded", "metrics": metrics, "artifact": artifact, "summary": summary}
    finally: shutil.rmtree(work, ignore_errors=True)
