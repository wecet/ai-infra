"""Saved models and reproducible evaluations of their recorded held-out samples."""
import json
import threading
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException

from common import database, get_project
from routes.training import _agent_url
from services.datasets import _archive
from services.agent_polling import reconnect

router = APIRouter()
_active = set()
_lock = threading.Lock()


def model_row(db, project_id, model_id):
    get_project(db, project_id)
    row = db.execute('''SELECT m.*,j.version_id,j.base_model,j.task_type,j.compute_target,j.artifact_path,
        j.dataset_partition,j.effective_config,j.run_name FROM registered_models m
        JOIN training_jobs j ON j.id=m.training_job_id WHERE m.project_id=? AND m.id=?''',
        (project_id, model_id)).fetchone()
    if not row: raise HTTPException(404, 'Saved model not found')
    return dict(row)


@router.get('/api/projects/{project_id}/models')
def models(project_id: str):
    with database() as db:
        get_project(db, project_id)
        rows = db.execute('''SELECT m.id,m.name,m.model_version,m.training_job_id,m.created_at,j.run_name,
            j.version_id,j.dataset_partition,j.artifact_path FROM registered_models m
            JOIN training_jobs j ON j.id=m.training_job_id WHERE m.project_id=? ORDER BY m.created_at DESC''', (project_id,)).fetchall()
    return [{key: row[key] for key in ('id','name','model_version','training_job_id','created_at','run_name','version_id')} |
        {'held_out_samples': len(json.loads(row['dataset_partition']).get('test', [])),
         'evaluation_available': bool(json.loads(row['dataset_partition']).get('test') and row['artifact_path'] and Path(row['artifact_path']).is_file()),
         'partition_recorded': bool(json.loads(row['dataset_partition']))} for row in rows]


def evaluation_json(row):
    value = dict(row); value['result'] = json.loads(value['result'])
    return value


@router.get('/api/projects/{project_id}/models/{model_id}/evaluation')
def evaluation(project_id: str, model_id: str):
    with database() as db:
        model_row(db, project_id, model_id)
        row = db.execute('SELECT * FROM model_evaluations WHERE model_id=? ORDER BY created_at DESC LIMIT 1', (model_id,)).fetchone()
    return evaluation_json(row) if row else {'status': 'not_started', 'result': {}}


@router.post('/api/projects/{project_id}/models/{model_id}/evaluation', status_code=202)
def evaluate_model(project_id: str, model_id: str):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        model = model_row(db, project_id, model_id)
        partition = json.loads(model['dataset_partition'])
        if not partition: raise HTTPException(422, 'This model predates held-out tracking. Train a new run to evaluate a verified held-out partition.')
        if not partition.get('test'): raise HTTPException(422, 'This run has no held-out images. Configure a nonempty test split and train a new run.')
        if not model['artifact_path'] or not Path(model['artifact_path']).is_file(): raise HTTPException(404, 'Model artifact is unavailable')
        existing = db.execute("SELECT * FROM model_evaluations WHERE model_id=? AND status IN ('queued','running','succeeded') ORDER BY created_at DESC LIMIT 1", (model_id,)).fetchone()
        if existing: return evaluation_json(existing)
        evaluation_id = uuid.uuid4().hex
        db.execute('''INSERT INTO model_evaluations (id,model_id,project_id,version_id,status,agent_job_id)
            VALUES (?,?,?,?,'queued',?)''', (evaluation_id, model_id, project_id, model['version_id'], evaluation_id))
        row = db.execute('SELECT * FROM model_evaluations WHERE id=?', (evaluation_id,)).fetchone()
    start_evaluation(evaluation_id)
    return evaluation_json(row)


def start_evaluation(evaluation_id):
    with _lock:
        if evaluation_id in _active: return
        _active.add(evaluation_id)
    threading.Thread(target=run_evaluation, args=(evaluation_id,), daemon=True).start()


def resume_evaluations():
    with database() as db: ids = [row['id'] for row in db.execute("SELECT id FROM model_evaluations WHERE status IN ('queued','running')")]
    for evaluation_id in ids: start_evaluation(evaluation_id)


def run_evaluation(evaluation_id):
    try:
        with database() as db:
            evaluation = dict(db.execute('SELECT * FROM model_evaluations WHERE id=?', (evaluation_id,)).fetchone())
            model = model_row(db, evaluation['project_id'], evaluation['model_id'])
            db.execute("UPDATE model_evaluations SET status='running' WHERE id=?", (evaluation_id,))
        agent = _agent_url(json.loads(model['compute_target']))
        partition = json.loads(model['dataset_partition'])
        _, archive = _archive(model['project_id'], model['version_id'], partition['test'], stream=True)
        config = json.loads(model['effective_config'])
        manifest = {'job_id': evaluation_id, 'base_model': model['base_model'], 'annotation_type': model['task_type'], 'config': config}
        model_stream = Path(model['artifact_path']).open('rb')
        def waiting(message):
            with database() as db:
                db.execute("UPDATE model_evaluations SET error=? WHERE id=?", (f'Reconnecting: {message}'[:2000], evaluation_id))
        def accepted():
            archive.seek(0); model_stream.seek(0)
            response = httpx.get(f'{agent}/api/v1/jobs/{evaluation_id}', timeout=10)
            if response.status_code == 404:
                response = httpx.post(f'{agent}/api/v1/evaluations', data={'manifest': json.dumps(manifest)},
                    files={'dataset': ('held-out.zip', archive, 'application/zip'),
                           'artifact': ('model.bin', model_stream, 'application/octet-stream')}, timeout=120)
            response.raise_for_status()
        reconnect(accepted, waiting)
        def fetch(suffix=''):
            response = httpx.get(f'{agent}/api/v1/jobs/{evaluation_id}{suffix}', timeout=120 if suffix else 10)
            response.raise_for_status()
            return response.json()
        while True:
            state = reconnect(fetch, waiting)
            with database() as db: db.execute("UPDATE model_evaluations SET error='' WHERE id=?", (evaluation_id,))
            if state['status'] in ('failed', 'cancelled'): raise RuntimeError(state.get('error') or 'Evaluation stopped')
            if state['status'] == 'succeeded':
                result = reconnect(lambda: fetch('/result'), waiting)
                result.update(version_id=model['version_id'], training_job_id=model['training_job_id'], held_out_image_ids=partition['test'])
                with database() as db: db.execute("UPDATE model_evaluations SET status='succeeded',result=?,error='' WHERE id=?", (json.dumps(result), evaluation_id))
                return
            time.sleep(2)
    except Exception as error:
        with database() as db: db.execute("UPDATE model_evaluations SET status='failed',error=? WHERE id=?", (str(error)[:2000], evaluation_id))
    finally:
        for name in ('archive', 'model_stream'):
            stream = locals().get(name)
            if hasattr(stream, 'close'): stream.close()
        with _lock: _active.discard(evaluation_id)


@router.get('/api/projects/{project_id}/model-comparison')
def compare_models(project_id: str, left: str, right: str):
    with database() as db:
        pair = [model_row(db, project_id, model_id) for model_id in (left, right)]
        evaluations = [db.execute("SELECT * FROM model_evaluations WHERE model_id=? AND status='succeeded' ORDER BY created_at DESC,rowid DESC LIMIT 1", (model_id,)).fetchone() for model_id in (left, right)]
    results = [json.loads(row['result']) if row else {} for row in evaluations]
    reasons = []
    if pair[0]['task_type'] != pair[1]['task_type']: reasons.append('Different task types')
    if pair[0]['version_id'] != pair[1]['version_id']: reasons.append('Different dataset versions')
    partitions = [json.loads(model['dataset_partition']).get('test', []) for model in pair]
    if not all(partitions) or set(partitions[0]) != set(partitions[1]): reasons.append('Different or missing held-out membership')
    if not all(results): reasons.append('Both models need a saved evaluation')
    if results[0].get('metric_policy') != results[1].get('metric_policy'): reasons.append('Different evaluation policies')
    configs = [json.loads(model['effective_config']) for model in pair]
    changes = {key: [configs[0].get(key), configs[1].get(key)] for key in configs[0].keys() | configs[1].keys() if configs[0].get(key) != configs[1].get(key)}
    rows = [{row['image_id']: row for row in result.get('predictions', [])} for result in results]
    return {'compatible': not reasons, 'reasons': reasons, 'config_changes': changes,
        'metrics': [result.get('metrics', {}) for result in results],
        'examples': [{'image_id': key, 'left': rows[0][key], 'right': rows[1][key]} for key in rows[0].keys() & rows[1].keys()] if not reasons else []}
