"""Version-bound training orchestration for local and remote compute agents."""
import tempfile
import base64
import hashlib
import io
import math
import random
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

from services.agent_polling import reconnect
from common import DATA, database, get_project
from services.datasets import _archive, version_detail

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
    parent_job_id: str | None = Field(default=None, max_length=64)
    version_id: str = Field(min_length=1, max_length=64)
    base_model: str = Field(min_length=1, max_length=150)
    hyperparameters: dict = Field(default_factory=dict)
    compute: ComputeTarget = Field(default_factory=ComputeTarget)

    @model_validator(mode='after')
    def protect_managed_config(self):
        managed = {'dataset_path', 'output_path', 'mlflow_url', 'project_id', 'dataset_version_id', 'class_names', 'devices'}
        if managed.intersection(self.hyperparameters): raise ValueError('Infrastructure configuration is managed by Studio')
        return self


def _agent_url(target):
    if target["kind"] == "local": return LOCAL_AGENT
    raw = target["endpoint"].strip()
    if "://" not in raw: raw = "http://" + raw
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise HTTPException(422, "Use an IP address and optional port, for example 192.168.1.20:8090")
    try: ipaddress.ip_address(parsed.hostname or "")
    except ValueError as exc: raise HTTPException(422, "Remote compute target must be an IP address") from exc
    try: port = parsed.port or 8090
    except ValueError as error: raise HTTPException(422, 'Invalid compute agent port') from error
    host = f'[{parsed.hostname}]' if ':' in parsed.hostname else parsed.hostname
    return f"{parsed.scheme}://{host}:{port}"


def _capabilities(url):
    try:
        response = httpx.get(f"{url}/api/v1/capabilities", timeout=httpx.Timeout(20, connect=4))
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
            "annotation_type": project["annotation_type"], "dataset_name": detail["name"],
            "partitions": {key: len(value) for key, value in partition(detail["snapshot"]).items() if isinstance(value, list)}}


from services.partitions import partition


def _mlflow(job, metrics, config):
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
             "start_time": now, "run_name": job.get("run_name") or job["id"], "tags": [{"key": "project_id", "value": job["project_id"]},
             {"key": "dataset_version", "value": job["version_id"]}]}, timeout=5).json()["run"]
        run_id = run["info"]["run_id"]
        httpx.post(f"{MLFLOW_URL}/api/2.0/mlflow/runs/log-batch", json={"run_id": run_id,
            "metrics": [{"key": k, "value": float(v), "timestamp": now, "step": 0} for k, v in metrics.items()],
            "params": [{"key": "base_model", "value": job["base_model"]}] +
                      [{"key": f"config.{key}", "value": json.dumps(value, ensure_ascii=False)} for key, value in config.items()], "tags": []}, timeout=5).raise_for_status()
        httpx.post(f"{MLFLOW_URL}/api/2.0/mlflow/runs/update", json={"run_id": run_id,
            "status": "FINISHED", "end_time": int(time.time() * 1000)}, timeout=5).raise_for_status()
        return f"{exp}:{run_id}"
    except Exception:
        return None


_running = set()
_running_lock = threading.Lock()


def start_job(job_id):
    with _running_lock:
        if job_id in _running: return
        _running.add(job_id)
    threading.Thread(target=_run, args=(job_id,), daemon=True).start()


def resume_jobs():
    with database() as db:
        ids = [row['id'] for row in db.execute("SELECT id FROM training_jobs WHERE status IN ('queued','running','cancelling')")]
    for job_id in ids:
        with database() as db:
            record = db.execute('SELECT dataset_partition FROM training_jobs WHERE id=?', (job_id,)).fetchone()
            if not json.loads(record['dataset_partition']):
                db.execute("UPDATE training_jobs SET status='failed',phase='interrupted',error=?,completed_at=? WHERE id=?",
                    ('Legacy job interrupted by Studio restart; retry to use durable agent jobs.', datetime.now(timezone.utc).isoformat(), job_id))
                continue
        start_job(job_id)


def _persist_progress(job_id, value):
    with database() as db:
        db.execute("""UPDATE training_jobs SET status=?,phase=?,heartbeat_at=?,logs=?,metrics=?,latest_metric=?,
            started_at=COALESCE(started_at,?),error='' WHERE id=? AND status IN ('queued','running','cancelling')""",
            (value['status'] if value.get('status') in ('queued', 'cancelling') else 'running', value.get('phase', 'training'), value.get('heartbeat_at'), json.dumps(value.get('logs', [])),
             json.dumps(value.get('metrics', {})), json.dumps(value.get('latest_metric') or {}), value.get('started_at'), job_id))


def _finish(job, result, model_config):
    job_id = job['id']
    output = DATA / 'training' / job_id; output.mkdir(parents=True, exist_ok=True)
    artifact_data = result['artifact']
    filename = re.sub(r'[^A-Za-z0-9._-]+', '_', artifact_data.get('filename', 'model.bin'))[:150] or 'model.bin'
    if filename in ('.', '..'): filename = 'model.bin'
    artifact = output / filename
    if '_downloaded_path' in artifact_data:
        Path(artifact_data['_downloaded_path']).replace(artifact)
    else: artifact.write_bytes(base64.b64decode(artifact_data['content_base64'], validate=True))
    config = result.get('config', model_config)
    with database() as db:
        provenance = json.loads(db.execute('SELECT provenance FROM training_jobs WHERE id=?', (job_id,)).fetchone()['provenance'])
        provenance.update(agent=result.get('provenance', {}), effective_config=config)
        db.execute('UPDATE training_jobs SET provenance=? WHERE id=?', (json.dumps(provenance), job_id))
    metrics = result.get('metrics', {})
    key = 'validation_loss' if 'validation_loss' in metrics else next(iter(metrics), None)
    latest = {'name': key, 'value': metrics[key]} if key else {}
    run_id = _mlflow(job, result.get('metrics', {}), config)
    with database() as db:
        completed = datetime.now(timezone.utc).isoformat()
        logs = json.loads(db.execute('SELECT logs FROM training_jobs WHERE id=?', (job_id,)).fetchone()['logs'])
        logs.append({'time': completed, 'message': 'Model saved' if run_id else 'Model saved; MLflow tracking is unavailable'})
        changed = db.execute("""UPDATE training_jobs SET status='succeeded',phase='completed',metrics=?,artifact_path=?,
            mlflow_run_id=?,completed_at=?,effective_config=?,logs=?,latest_metric=?,error='' WHERE id=? AND status!='succeeded'""",
            (json.dumps(result.get('metrics', {})), str(artifact), run_id, completed, json.dumps(config), json.dumps(logs[-200:]), json.dumps(latest), job_id))
        if not changed.rowcount: return
        model_version = db.execute('SELECT COALESCE(MAX(model_version),0)+1 FROM registered_models WHERE project_id=? AND name=?',
                                   (job['project_id'], job['base_model'])).fetchone()[0]
        db.execute("""INSERT INTO registered_models (id,project_id,training_job_id,name,model_version,mlflow_run_id,created_at)
            VALUES (?,?,?,?,?,?,?)""", (uuid.uuid4().hex, job['project_id'], job_id, job['base_model'], model_version, run_id, completed))


class CancelledWork(Exception):
    pass


def _run(job_id):
    with database() as db:
        job = dict(db.execute('SELECT * FROM training_jobs WHERE id=?', (job_id,)).fetchone())
    try:
        target = json.loads(job['compute_target']); agent = _agent_url(target)
        def waiting(message):
            with database() as db: db.execute("UPDATE training_jobs SET phase='reconnecting',error=? WHERE id=?", (f'Waiting for agent: {message}'[:2000], job_id))
        def capability_request():
            try: return _capabilities(agent)
            except HTTPException as error:
                if error.status_code != 502: raise
                raise httpx.ConnectError(str(error.detail)) from error
        caps = reconnect(capability_request, waiting)
        selected = json.loads(job['dataset_partition'])
        detail, archive = _archive(job['project_id'], job['version_id'], selected.get('train', []) + selected.get('validation', []), stream=True)
        hyperparameters = json.loads(job['hyperparameters'])
        model_config = {'dataset_path': '/workspace/dataset.zip', 'output_path': f'/workspace/outputs/{job_id}',
            'mlflow_url': MLFLOW_URL, 'project_id': job['project_id'], 'dataset_version_id': job['version_id'],
            'class_names': [item['name'] for item in detail['snapshot']['project']['classes']],
            'devices': [key for key in ('cpu', 'gpu') if target.get(key)], **hyperparameters}
        provenance = {'snapshot_sha256': hashlib.sha256(json.dumps(detail['snapshot'], sort_keys=True).encode()).hexdigest(),
            'partition': selected, 'config': model_config, 'base_model': job['base_model'], 'split_seed': 42}
        with database() as db: db.execute('UPDATE training_jobs SET provenance=? WHERE id=?', (json.dumps(provenance), job_id))
        manifest = {'job_id': job_id, 'annotation_type': job['task_type'], 'base_model': job['base_model'],
            'run_name': job['run_name'] or job_id, 'hyperparameters': hyperparameters, 'config': model_config,
            'devices': model_config['devices'], 'dataset_name': detail['name']}
        if caps.get('async_jobs'):
            def accepted():
                response = httpx.get(f'{agent}/api/v1/jobs/{job_id}', timeout=10)
                if response.status_code == 404:
                    with database() as db: state = db.execute('SELECT status FROM training_jobs WHERE id=?', (job_id,)).fetchone()['status']
                    if state == 'cancelling': raise CancelledWork()
                    archive.seek(0)
                    response = httpx.post(f'{agent}/api/v1/jobs', data={'manifest': json.dumps(manifest)},
                        files={'dataset': (f"{detail['name']}.zip", archive, 'application/zip')}, timeout=120)
                response.raise_for_status()
            reconnect(accepted, waiting)
            def state_request():
                response = httpx.get(f'{agent}/api/v1/jobs/{job_id}', timeout=10)
                response.raise_for_status()
                value = response.json()
                with database() as db: intent = db.execute('SELECT status FROM training_jobs WHERE id=?', (job_id,)).fetchone()['status']
                if intent == 'cancelling' and value['status'] in ('queued', 'running', 'cancelling'):
                    response = httpx.post(f'{agent}/api/v1/jobs/{job_id}/cancel', timeout=10)
                    response.raise_for_status(); value = response.json()
                return value
            while True:
                value = reconnect(state_request, waiting)
                _persist_progress(job_id, value)
                if value['status'] == 'cancelled': raise CancelledWork()
                if value['status'] == 'failed': raise RuntimeError(value.get('error') or 'Agent job failed')
                if value['status'] == 'succeeded':
                    def result_request():
                        response = httpx.get(f'{agent}/api/v1/jobs/{job_id}/result?binary=true', timeout=120)
                        response.raise_for_status(); result = response.json()
                        if 'content_base64' not in result['artifact']:
                            download = DATA / 'training' / f'{job_id}.download'
                            download.parent.mkdir(parents=True, exist_ok=True)
                            with httpx.stream('GET', f'{agent}/api/v1/jobs/{job_id}/artifact', timeout=120) as incoming:
                                incoming.raise_for_status()
                                with download.open('wb') as output:
                                    for chunk in incoming.iter_bytes(): output.write(chunk)
                            result['artifact']['_downloaded_path'] = str(download)
                        return result
                    result = reconnect(result_request, waiting)
                    break
                time.sleep(2)
        else:
            # Compatibility with agents predating the asynchronous job protocol.
            with database() as db: db.execute("UPDATE training_jobs SET status='running',phase='training',started_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), job_id))
            response = httpx.post(f'{agent}/api/v1/train', data={'manifest': json.dumps(manifest)},
                files={'dataset': (f"{detail['name']}.zip", archive, 'application/zip')}, timeout=3600)
            if response.is_error:
                try: message = response.json().get('detail')
                except ValueError: message = None
                if isinstance(message, str): raise RuntimeError(message)
            response.raise_for_status(); result = response.json()
        _finish(job, result, model_config)
    except CancelledWork:
        with database() as db: db.execute("UPDATE training_jobs SET status='cancelled',phase='cancelled',error='',completed_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), job_id))
    except Exception as error:
        with database() as db: db.execute("UPDATE training_jobs SET status='failed',phase='failed',error=?,completed_at=? WHERE id=?",
            (str(error)[:2000], datetime.now(timezone.utc).isoformat(), job_id))
    finally:
        if 'archive' in locals() and hasattr(archive, 'close'): archive.close()
        with _running_lock: _running.discard(job_id)


def _job(row):
    item = dict(row); item["hyperparameters"] = json.loads(item["hyperparameters"])
    item["compute_target"] = json.loads(item["compute_target"]); item["metrics"] = json.loads(item["metrics"])
    item["logs"] = json.loads(item["logs"]); item["latest_metric"] = json.loads(item["latest_metric"])
    item["dataset_partition"] = json.loads(item["dataset_partition"]); item["effective_config"] = json.loads(item["effective_config"])
    item["provenance"] = json.loads(item["provenance"])
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
        db.execute("BEGIN IMMEDIATE")
        project = get_project(db, project_id)
        version = db.execute("SELECT id,snapshot FROM dataset_versions WHERE id=? AND project_id=?", (payload.version_id, project_id)).fetchone()
        if not version: raise HTTPException(404, "Published version not found")
        if project["annotation_type"] == "anomaly_detection" and not any(
                image.get("split") == "train" for image in json.loads(version["snapshot"])["images"]):
            raise HTTPException(422, "Published anomaly version has no training images. Increase the train split and publish a new version.")
        partitions = partition(json.loads(version["snapshot"]))
        if not partitions["train"]: raise HTTPException(422, "Published dataset has no training images. Increase the train split and publish a new version.")
        installed = {item["key"] for item in caps.get("models", {}).get(project["annotation_type"], [])}
        installed.update(item["key"] for item in caps.get("workbenches", [])
                         if item.get("available") and item.get("task") == project["annotation_type"])
        if payload.base_model not in installed: raise HTTPException(422, "Selected model is not installed on this compute agent")
        if target["gpu"] and not caps["gpu"]["available"]: raise HTTPException(422, caps["gpu"].get("reason", "GPU unavailable"))
        if payload.parent_job_id and not db.execute('SELECT 1 FROM training_jobs WHERE id=? AND project_id=?', (payload.parent_job_id, project_id)).fetchone():
            raise HTTPException(404, 'Parent run not found in this project')
        job_id = uuid.uuid4().hex
        slug = re.sub(r"[^a-z0-9]+", "-", project["name"].lower()).strip("-")[:80] or "project"
        prefix = f"{datetime.now(timezone.utc).strftime('%y%m%d')}-{slug}-v"
        number = db.execute("SELECT COUNT(*)+1 FROM training_jobs WHERE project_id=?", (project_id,)).fetchone()[0]
        run_name = f"{prefix}{number}"
        while db.execute("SELECT 1 FROM training_jobs WHERE run_name=?", (run_name,)).fetchone():
            number += 1
            run_name = f"{prefix}{number}"
        db.execute("""INSERT INTO training_jobs (id,project_id,version_id,task_type,base_model,hyperparameters,
            compute_target,run_name,tensorboard_url,dataset_partition,status) VALUES (?,?,?,?,?,?,?,?,?,?,'queued')""", (job_id, project_id, payload.version_id,
            project["annotation_type"], payload.base_model, json.dumps(payload.hyperparameters), json.dumps(target), run_name, caps.get("tensorboard", {}).get("url", "") if caps.get("tensorboard", {}).get("available") else "", json.dumps(partitions)))
        db.execute('UPDATE training_jobs SET parent_job_id=? WHERE id=?', (payload.parent_job_id, job_id))
        row = db.execute("SELECT * FROM training_jobs WHERE id=?", (job_id,)).fetchone()
    with database() as db:
        db.execute('UPDATE training_jobs SET logs=? WHERE id=?', (json.dumps([{'time': datetime.now(timezone.utc).isoformat(), 'message': 'Queued; training continues independently of this page'}]), job_id))
        row = db.execute('SELECT * FROM training_jobs WHERE id=?', (job_id,)).fetchone()
    start_job(job_id)
    return _job(row)


@router.get("/api/projects/{project_id}/training/jobs/{job_id}/artifact")
def artifact(project_id: str, job_id: str):
    with database() as db: row = db.execute("SELECT artifact_path,run_name FROM training_jobs WHERE id=? AND project_id=?", (job_id, project_id)).fetchone()
    if not row or not row["artifact_path"] or not Path(row["artifact_path"]).is_file(): raise HTTPException(404, "Model artifact is unavailable")
    path = Path(row["artifact_path"])
    return FileResponse(path, filename=f"{row['run_name'] or job_id}-{path.name}")


@router.post('/api/projects/{project_id}/training/jobs/{job_id}/cancel')
def cancel_job(project_id: str, job_id: str):
    with database() as db:
        row = db.execute('SELECT * FROM training_jobs WHERE project_id=? AND id=?', (project_id, job_id)).fetchone()
        if not row: raise HTTPException(404, 'Training job not found')
        if row['status'] not in ('queued', 'running', 'cancelling'): return _job(row)
        agent = _agent_url(json.loads(row['compute_target']))
        # Record cancellation intent before contacting the agent, including before submission.
        db.execute("UPDATE training_jobs SET status='cancelling',phase='cancelling' WHERE id=?", (job_id,))
    try:
        response = httpx.post(f'{agent}/api/v1/jobs/{job_id}/cancel', timeout=10)
        if response.status_code != 404: response.raise_for_status()
    except httpx.HTTPError as error:
        raise HTTPException(502, 'Cancellation requested; agent is unreachable. Retry cancellation.') from error
    return {'id': job_id, 'status': 'cancelling'}


class PreviewRequest(JobCreate):
    seed: int = Field(default=42, ge=0, le=2**31-1)


@router.post('/api/projects/{project_id}/augmentation-preview')
def augmentation_preview(project_id: str, payload: PreviewRequest):
    detail = version_detail(project_id, payload.version_id)
    snapshot = detail['snapshot']
    selected = partition(snapshot)['train']
    image = next((row for row in snapshot['images'] if row['id'] in selected), None)
    if image is None: raise HTTPException(422, 'No training sample available')
    config = {'dataset_path': '/preview/dataset.zip', 'output_path': '/preview',
        'class_names': [c['name'] for c in snapshot['project']['classes']], 'project_id': project_id,
        'dataset_version_id': payload.version_id, **payload.hyperparameters}
    agent = _agent_url(payload.compute.model_dump())
    with (DATA / 'versions' / project_id / payload.version_id / image['stored_name']).open('rb') as stream:
        try:
            response = httpx.post(f'{agent}/api/v1/augmentation-preview', data={'manifest': json.dumps({'base_model': payload.base_model, 'config': config, 'seed': payload.seed, 'boxes': image['boxes']})}, files={'image': ('sample.png', stream, 'image/png')}, timeout=60)
            response.raise_for_status()
        except httpx.HTTPError as error: raise HTTPException(422, f'Preview unavailable on selected agent: {error}') from error
    return response.json() | {'source_path': image['source_path']}
