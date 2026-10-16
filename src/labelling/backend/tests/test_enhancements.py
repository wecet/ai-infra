"""Regression tests for the complete dataset/run/review enhancement stack."""
import base64
import io
import json
import uuid

import httpx
import pytest
from PIL import Image
import app as service
from test_app import client, project, upload, save


def seed_model(client, monkeypatch, pid):
    for index in range(6):
        image = upload(client, pid, f'{index}.png', (20 + index, 20))
        assert save(client, pid, image, boxes=[]).status_code == 200
    version = client.post(f'/api/projects/{pid}/publish').json()['id']
    monkeypatch.setattr(service.training, '_capabilities', lambda _: {'async_jobs': True, 'models': {'object_detection': [{'key': 'class-box-prior-v1'}]}, 'gpu': {'available': False}})
    monkeypatch.setattr(service.training, 'start_job', lambda _: None)
    job = client.post(f'/api/projects/{pid}/training/jobs', json={'version_id': version, 'base_model': 'class-box-prior-v1'}).json()
    monkeypatch.setattr(service.training, '_mlflow', lambda *args: None)
    service.training._finish(job, {'artifact': {'filename': 'model.json', 'content_base64': base64.b64encode(b'{}').decode()}, 'metrics': {}}, {})
    model = client.get(f'/api/projects/{pid}/models').json()[0]
    row = {'image_id': job['dataset_partition']['test'][0], 'source_path': 'failure.png', 'predictions': [{'class_name': 'Bolt', 'score': .8}], 'ground_truth': [], 'failed': True, 'width': 20, 'height': 20}
    result = {'predictions': [row], 'failure_examples': [row], 'metrics': {'f1': .5}, 'metric_policy': 'same-policy', 'sample_count': 1}
    with service.database() as db:
        db.execute("INSERT INTO model_evaluations(id,model_id,project_id,version_id,status,agent_job_id,result) VALUES (?,?,?,?,'succeeded',?,?)", (uuid.uuid4().hex, model['id'], pid, version, 'agent', json.dumps(result)))
    return job, model, row


def test_preview_rejects_invalid_images_without_mutating_project(client):
    pid = project(client)
    path = f'/api/projects/{pid}/imports/preview'
    assert client.post(path, files={'file': ('bad.png', b'invalid')}).status_code == 422
    raw = io.BytesIO(); Image.new('RGB', (10, 20)).save(raw, 'PNG')
    response = client.post(path, files={'file': ('new.png', raw.getvalue())})
    assert response.status_code == 200 and response.json()['status'] == 'accepted'
    assert response.json()['width'] == 10
    assert client.get(f'/api/projects/{pid}/images').json() == []
    assert client.post(path, files={'file': ('../escape.png', raw.getvalue())}).status_code == 422


def test_readiness_is_task_aware_and_proposes_disjoint_partitions(client):
    pid = project(client)
    assert not client.get(f'/api/projects/{pid}/readiness').json()['can_publish']
    for index in range(6):
        image = upload(client, pid, f'{index}.png', (20 + index, 20))
        save(client, pid, image, boxes=[])
    report = client.get(f'/api/projects/{pid}/readiness')
    assert report.status_code == 200, report.text
    assert sum(report.json()['partitions'].values()) == 6
    assert any(check['code'] == 'unreviewed' for check in report.json()['checks'])
    anomaly = client.post('/api/projects', json={'name': 'Anomaly', 'annotation_type': 'anomaly_detection'}).json()['id']
    upload(client, anomaly)
    assert not any(check['code'] in ('unreviewed', 'incomplete') for check in client.get(f'/api/projects/{anomaly}/readiness').json()['checks'])


def test_failure_queue_is_idempotent_model_scoped_and_preserves_labels(client, monkeypatch):
    pid = project(client)
    job, model, row = seed_model(client, monkeypatch, pid)
    endpoint = f"/api/projects/{pid}/models/{model['id']}/review-tasks"
    before = client.get(f"/api/projects/{pid}/images/{row['image_id']}").json()
    for _ in range(2): assert client.post(endpoint, json={'image_ids': [row['image_id']]}).status_code == 201
    assert client.post(endpoint, json={'image_ids': ['unverified']}).status_code == 422
    tasks = client.get(f'/api/projects/{pid}/review-tasks').json()
    assert len(tasks) == 1 and tasks[0]['created_by'] == 'admin'
    assert before == client.get(f"/api/projects/{pid}/images/{row['image_id']}").json()
    task_path = f"/api/projects/{pid}/review-tasks/{tasks[0]['id']}"
    assert client.put(task_path, json={'status': 'resolved'}).status_code == 422
    assert client.put(task_path, json={'status': 'resolved', 'resolution': 'Correct label verified'}).status_code == 200
    assert client.get(f'/api/projects/{pid}/activity').json()[0]['actor'] == 'admin'
    other = project(client, 'Other')
    assert client.post(endpoint.replace(pid, other), json={'image_ids': [row['image_id']]}).status_code == 404
    assert client.delete(f'/api/projects/{pid}').status_code == 200


def test_comparison_explains_incompatible_holdout(client, monkeypatch):
    pid = project(client)
    job, model, row = seed_model(client, monkeypatch, pid)
    path = f"/api/projects/{pid}/model-comparison?left={model['id']}&right={model['id']}"
    assert client.get(path).json()['compatible']
    with service.database() as db: db.execute("UPDATE training_jobs SET dataset_partition='{}' WHERE id=?", (job['id'],))
    response = client.get(path)
    assert not response.json()['compatible'] and response.json()['examples'] == []


def test_clone_parent_and_delete_guard(client, monkeypatch):
    pid = project(client)
    job, model, row = seed_model(client, monkeypatch, pid)
    path = f'/api/projects/{pid}/training/jobs'
    cloned = client.post(path, json={'version_id': job['version_id'], 'base_model': job['base_model'], 'parent_job_id': job['id']})
    assert cloned.status_code == 202 and cloned.json()['parent_job_id'] == job['id']
    assert client.delete(f'/api/projects/{pid}').status_code == 409
    assert client.post(path, json={'version_id': job['version_id'], 'base_model': job['base_model'], 'parent_job_id': 'missing'}).status_code == 404


def test_training_permanent_agent_errors_finish_instead_of_polling_forever(client, monkeypatch):
    pid = project(client)
    job, model, row = seed_model(client, monkeypatch, pid)
    new = client.post(f'/api/projects/{pid}/training/jobs', json={'version_id': job['version_id'], 'base_model': job['base_model']}).json()
    monkeypatch.setattr(service.training.httpx, 'get', lambda url, **kwargs: httpx.Response(403, request=httpx.Request('GET', url)))
    service.training._run(new['id'])
    jobs = client.get(f'/api/projects/{pid}/training/jobs').json()
    assert next(item for item in jobs if item['id'] == new['id'])['status'] == 'failed'
