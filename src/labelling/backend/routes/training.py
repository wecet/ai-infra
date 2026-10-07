"""Version-bound training orchestration for local and remote compute agents."""
import base64
import io
import ipaddress
import json
import os
import re
import threading
import time
import urllib.parse
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from common import DATA, database, get_project
from routes.versions import _version_content, version_detail

router = APIRouter()
LOCAL_AGENT = os.environ.get("TRAINING_AGENT_URL", "http://training-agent:8090").rstrip("/")
MLFLOW_URL = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000").rstrip("/")
MLFLOW_PUBLIC_URL = os.environ.get("MLFLOW_PUBLIC_URL", "http://localhost:5001").rstrip("/")


class ComputeTarget(BaseModel):
    kind: Literal["local", "remote"] = "local"
    cpu: bool = True
    gpu: bool = False
    endpoint: str = ""

    @model_validator(mode="after")
    def valid_target(self):
        if self.kind == "local" and not (self.cpu or self.gpu):
            raise ValueError("Select CPU, GPU, or both")
        if self.kind == "remote" and not self.endpoint.strip():
            raise ValueError("Enter the remote compute agent IP address")
        return self


class JobCreate(BaseModel):
    version_id: str = Field(min_length=1, max_length=64)
    base_model: str = Field(min_length=1, max_length=150)
    hyperparameters: dict = Field(default_factory=dict)
    compute: ComputeTarget = Field(default_factory=ComputeTarget)


def _agent_url(target):
    if target["kind"] == "local": return LOCAL_AGENT
    raw = target["endpoint"].strip()
    if "://" not in raw: raw = "http://" + raw
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.path not in {"", "/"}:
        raise HTTPException(422, "Use an IP address and optional port, for example 192.168.1.20:8090")
    try: ipaddress.ip_address(parsed.hostname or "")
    except ValueError as exc: raise HTTPException(422, "Remote compute target must be an IP address") from exc
    port = parsed.port or 8090
    return f"{parsed.scheme}://{parsed.hostname}:{port}"


def _capabilities(url):
    try:
        response = httpx.get(f"{url}/api/v1/capabilities", timeout=4)
        response.raise_for_status(); return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"Compute agent is unavailable: {exc}") from exc


@router.get("/api/training/capabilities")
def local_capabilities(): return _capabilities(LOCAL_AGENT)


@router.post("/api/training/probe")
def probe(target: ComputeTarget):
    url = _agent_url(target.model_dump())
    return {"endpoint": url, **_capabilities(url)}


@router.get("/api/projects/{project_id}/training/template")
def training_template(project_id: str, version_id: str):
    detail = version_detail(project_id, version_id)
    with database() as db: project = get_project(db, project_id)
    return {"dataset_path": f"labelling://projects/{project_id}/versions/{version_id}",
            "output_path": f"/outputs/{project_id}/{{job_id}}", "mlflow_url": MLFLOW_PUBLIC_URL,
            "project_id": project_id, "dataset_version_id": version_id,
            "class_names": [item["name"] for item in project["classes"]],
            "annotation_type": project["annotation_type"], "dataset_name": detail["name"]}


def _archive(project_id, version_id):
    detail = version_detail(project_id, version_id)
    _, _, objects = _version_content(project_id, version_id, detail)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path, content, _ in objects: bundle.writestr(path, content)
    return detail, buffer.getvalue()


def _mlflow(job, metrics):
    """Best-effort MLflow REST logging; a tracking outage never loses the model artifact."""
    try:
        found = httpx.get(f"{MLFLOW_URL}/api/2.0/mlflow/experiments/get-by-name",
                          params={"experiment_name": "labelling-training"}, timeout=5)
        if found.status_code == 404:
            exp = httpx.post(f"{MLFLOW_URL}/api/2.0/mlflow/experiments/create",
                             json={"name": "labelling-training"}, timeout=5).json()["experiment_id"]
        else: found.raise_for_status(); exp = found.json()["experiment"]["experiment_id"]
        now = int(time.time() * 1000)
        run = httpx.post(f"{MLFLOW_URL}/api/2.0/mlflow/runs/create", json={"experiment_id": exp,
             "start_time": now, "run_name": job["id"], "tags": [{"key": "project_id", "value": job["project_id"]},
             {"key": "dataset_version", "value": job["version_id"]}]}, timeout=5).json()["run"]
        run_id = run["info"]["run_id"]
        httpx.post(f"{MLFLOW_URL}/api/2.0/mlflow/runs/log-batch", json={"run_id": run_id,
            "metrics": [{"key": k, "value": float(v), "timestamp": now, "step": 0} for k, v in metrics.items()],
            "params": [{"key": "base_model", "value": job["base_model"]}], "tags": []}, timeout=5).raise_for_status()
        httpx.post(f"{MLFLOW_URL}/api/2.0/mlflow/runs/update", json={"run_id": run_id,
            "status": "FINISHED", "end_time": int(time.time() * 1000)}, timeout=5).raise_for_status()
        return f"{exp}:{run_id}"
    except Exception:
        return None


def _run(job_id):
    now = datetime.now(timezone.utc).isoformat()
    with database() as db:
        db.execute("UPDATE training_jobs SET status='running',started_at=? WHERE id=?", (now, job_id))
        job = dict(db.execute("SELECT * FROM training_jobs WHERE id=?", (job_id,)).fetchone())
    try:
        target = json.loads(job["compute_target"]); agent = _agent_url(target)
        capabilities = _capabilities(agent)
        if target.get("gpu") and not capabilities["gpu"]["available"]:
            raise RuntimeError(capabilities["gpu"].get("reason") or "GPU unavailable")
        detail, archive = _archive(job["project_id"], job["version_id"])
        hyperparameters = json.loads(job["hyperparameters"])
        model_config = {"dataset_path": "/workspace/dataset.zip", "output_path": f"/workspace/outputs/{job_id}",
                        "mlflow_url": MLFLOW_URL, "project_id": job["project_id"],
                        "dataset_version_id": job["version_id"],
                        "class_names": [item["name"] for item in detail["snapshot"]["project"]["classes"]],
                        "devices": [key for key in ("cpu", "gpu") if target.get(key)], **hyperparameters}
        manifest = {"job_id": job_id, "annotation_type": job["task_type"], "base_model": job["base_model"],
                    "hyperparameters": hyperparameters, "config": model_config,
                    "devices": model_config["devices"], "dataset_name": detail["name"]}
        response = httpx.post(f"{agent}/api/v1/train", data={"manifest": json.dumps(manifest)},
                              files={"dataset": (f"{detail['name']}.zip", archive, "application/zip")}, timeout=3600)
        response.raise_for_status(); result = response.json()
        output = DATA / "training" / job_id; output.mkdir(parents=True, exist_ok=True)
        artifact_data = result["artifact"]
        filename = re.sub(r"[^A-Za-z0-9._-]+", "_", artifact_data.get("filename", "model.bin"))[:150] or "model.bin"
        artifact = output / filename
        artifact.write_bytes(base64.b64decode(artifact_data["content_base64"], validate=True))
        run_id = _mlflow(job, result.get("metrics", {}))
        with database() as db: db.execute("""UPDATE training_jobs SET status='succeeded',metrics=?,artifact_path=?,
            mlflow_run_id=?,completed_at=? WHERE id=?""", (json.dumps(result.get("metrics", {})), str(artifact),
            run_id, datetime.now(timezone.utc).isoformat(), job_id))
    except Exception as exc:
        with database() as db: db.execute("UPDATE training_jobs SET status='failed',error=?,completed_at=? WHERE id=?",
            (str(exc)[:2000], datetime.now(timezone.utc).isoformat(), job_id))


def _job(row):
    item = dict(row); item["hyperparameters"] = json.loads(item["hyperparameters"])
    item["compute_target"] = json.loads(item["compute_target"]); item["metrics"] = json.loads(item["metrics"])
    item["artifact_available"] = bool(item.pop("artifact_path"))
    if item["mlflow_run_id"]:
        experiment_id, run_id = (item["mlflow_run_id"].split(":", 1)
                                 if ":" in item["mlflow_run_id"] else ("0", item["mlflow_run_id"]))
        item["mlflow_url"] = f"{MLFLOW_PUBLIC_URL}/#/experiments/{experiment_id}/runs/{run_id}"
    else:
        item["mlflow_url"] = None
    return item


@router.get("/api/projects/{project_id}/training/jobs")
def jobs(project_id: str):
    with database() as db:
        get_project(db, project_id)
        return [_job(row) for row in db.execute("SELECT * FROM training_jobs WHERE project_id=? ORDER BY created_at DESC", (project_id,))]


@router.post("/api/projects/{project_id}/training/jobs", status_code=202)
def create_job(project_id: str, payload: JobCreate):
    target = payload.compute.model_dump(); agent = _agent_url(target); caps = _capabilities(agent)
    with database() as db:
        project = get_project(db, project_id)
        version = db.execute("SELECT id FROM dataset_versions WHERE id=? AND project_id=?", (payload.version_id, project_id)).fetchone()
        if not version: raise HTTPException(404, "Published version not found")
        installed = {item["key"] for item in caps.get("models", {}).get(project["annotation_type"], [])}
        installed.update(item["key"] for item in caps.get("workbenches", [])
                         if item.get("available") and item.get("task") == project["annotation_type"])
        if payload.base_model not in installed: raise HTTPException(422, "Selected model is not installed on this compute agent")
        if target["gpu"] and not caps["gpu"]["available"]: raise HTTPException(422, caps["gpu"].get("reason", "GPU unavailable"))
        job_id = uuid.uuid4().hex
        db.execute("""INSERT INTO training_jobs (id,project_id,version_id,task_type,base_model,hyperparameters,
            compute_target,status) VALUES (?,?,?,?,?,?,?,'queued')""", (job_id, project_id, payload.version_id,
            project["annotation_type"], payload.base_model, json.dumps(payload.hyperparameters), json.dumps(target)))
        row = db.execute("SELECT * FROM training_jobs WHERE id=?", (job_id,)).fetchone()
    threading.Thread(target=_run, args=(job_id,), daemon=True).start()
    return _job(row)


@router.get("/api/projects/{project_id}/training/jobs/{job_id}/artifact")
def artifact(project_id: str, job_id: str):
    with database() as db: row = db.execute("SELECT artifact_path FROM training_jobs WHERE id=? AND project_id=?", (job_id, project_id)).fetchone()
    if not row or not row["artifact_path"] or not Path(row["artifact_path"]).is_file(): raise HTTPException(404, "Model artifact is unavailable")
    path = Path(row["artifact_path"])
    return FileResponse(path, filename=f"{job_id[:8]}-{path.name}")
