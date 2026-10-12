import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as service


def test_classification_persistence_stats_and_export(client):
    created = client.post('/api/projects', json={
        'name': 'Conditions', 'classes': ['Clean', 'Damaged'], 'annotation_type': 'image_classification'})
    assert created.status_code == 201
    pid = created.json()['id']
    image = upload(client, pid)
    path = f"/api/projects/{pid}/images/{image['id']}"
    for labels in ([3], [1, 1]):
        assert client.put(path, json={'revision': 0, 'completed': True, 'boxes': [], 'labels': labels}).status_code == 422
    assert save(client, pid, image).status_code == 422  # No boxes in classification projects.
    payload = {'revision': 0, 'completed': False, 'boxes': [], 'labels': [1, 2]}
    result = client.put(path, json=payload)
    assert result.status_code == 200
    assert client.get(f'/api/projects/{pid}/stats').json()['labels'] == 0
    payload.update(revision=1, completed=True)
    assert client.put(path, json=payload).status_code == 200
    assert client.put(path, json=payload).status_code == 409
    service.init_db()
    assert client.get(path).json()['labels'] == [1, 2]
    assert upload(client, pid)['labels'] == [1, 2]  # Reimports retain whole-image labels.
    stats = client.get(f'/api/projects/{pid}/stats').json()
    assert stats['labels'] == 2 and stats['boxes'] == 0
    assert [c['images'] for c in stats['classes']] == [1, 1]
    negative = upload(client, pid, 'negative.png')
    assert save(client, pid, negative, boxes=[]).status_code == 200
    archive = client.post(f'/api/projects/{pid}/export', json={'train_percent': 100, 'split': 'train'})
    assert archive.status_code == 200 and 'Conditions_train.zip' in archive.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        data = json.loads(z.read('annotations/Conditions_train.json'))
        assert data['info']['annotation_type'] == 'image_classification'
        assert data['annotations'] == []
        assert sorted(im['category_ids'] for im in data['images']) == [[], [1, 2]]
        assert all(name.startswith(('annotations/', 'images/')) for name in z.namelist())
        assert [c['annotations'] for c in data['info']['class_distribution']] == [1, 1]
    empty = client.post(f'/api/projects/{pid}/export', json={'train_percent': 100, 'split': 'test'})
    assert empty.status_code == 422
    assert 'test split is empty' in empty.json()['detail']


def test_old_database_migration(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setattr(service, 'DATA', tmp_path)
    monkeypatch.setattr(service.common, 'DATA', tmp_path)
    with sqlite3.connect(tmp_path / 'labelling.sqlite3') as db:
        db.executescript('''CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT, classes TEXT, created_at TEXT);
            CREATE TABLE images(id TEXT PRIMARY KEY, project_id TEXT, source_path TEXT, stored_name TEXT,
            digest TEXT, width INTEGER, height INTEGER, completed INTEGER, revision INTEGER, boxes TEXT);
            INSERT INTO projects VALUES ('old', 'Original', '[{"id": 1, "name": "A"}]', '2026-01-01');
            INSERT INTO images VALUES ('image','old','a.png','a.png','hash',100,80,1,7,
            '[{"category_id":1,"x":1,"y":2,"width":10,"height":20}]');''')
    service.init_db()
    service.init_db()
    with service.database() as db:
        assert service.get_project(db, 'old')['annotation_type'] == 'object_detection'
        image = service.image_json(service.get_image(db, 'old', 'image'))
        assert image['revision'] == 7 and image['completed']
        assert image['boxes'][0]['width'] == 10 and image['labels'] == []
        assert image['review_status'] == 'ready_for_review'


def test_ai_saves_draft_once_and_preserves_edits(client, monkeypatch):
    calls = []
    def detect(*args):
        calls.append(args)
        return [{'category_id': 1, 'x': 10, 'y': 5, 'width': 30, 'height': 20}]
    monkeypatch.setattr(service.ai_labelling, 'detect', detect)
    pid = project(client)
    image = upload(client, pid)
    path = f"/api/projects/{pid}/images/{image['id']}/ai"
    result = client.post(path, json={'revision': 0})
    assert result.status_code == 200 and not result.json()['completed']
    assert result.json()['revision'] == 1 and len(result.json()['boxes']) == 1
    assert client.post(path, json={'revision': 1}).status_code == 409
    assert len(calls) == 1
    assert save(client, pid, result.json(), boxes=[]).status_code == 200
    assert client.post(path, json={'revision': 2}).status_code == 409
    # A human edit while the model runs must win.
    second = upload(client, pid, 'second.png')
    def concurrent(*args):
        assert save(client, pid, second).status_code == 200
        return []
    monkeypatch.setattr(service.ai_labelling, 'detect', concurrent)
    assert client.post(f"/api/projects/{pid}/images/{second['id']}/ai", json={'revision': 0}).status_code == 409
    current = client.get(f"/api/projects/{pid}/images/{second['id']}").json()
    assert current['completed'] and len(current['boxes']) == 1


def test_project_settings_review_workflow_and_quality(client):
    pid = project(client)
    settings = client.put(f'/api/projects/{pid}', json={
        'name': 'Updated', 'description': 'Inspect components',
        'labelling_instructions': 'Use tight boxes', 'ai_instructions': 'Ignore reflections',
        'export_train_percent': 50})
    assert settings.status_code == 200
    assert settings.json()['description'] == 'Inspect components'
    assert settings.json()['export_train_percent'] == 50
    image = upload(client, pid)
    completed = save(client, pid, image, boxes=[]).json()
    assert completed['review_status'] == 'ready_for_review'
    rejected = client.put(f"/api/projects/{pid}/images/{image['id']}/review",
                          json={'status': 'rejected', 'comment': ''})
    assert rejected.status_code == 422
    rejected = client.put(f"/api/projects/{pid}/images/{image['id']}/review",
                          headers={'x-forwarded-user': 'reviewer'},
                          json={'status': 'rejected', 'comment': 'Missing the component'})
    assert rejected.status_code == 200
    assert rejected.json()['reviewed_by'] == 'reviewer'
    approved = client.put(f"/api/projects/{pid}/images/{image['id']}/review",
                          json={'status': 'approved'}).json()
    assert approved['review_status'] == 'approved'
    edited = save(client, pid, completed, boxes=[]).json()
    assert edited['review_status'] == 'ready_for_review' and not edited['review_comment']
    quality = client.get(f'/api/projects/{pid}/quality').json()
    assert {issue['code'] for issue in quality['issues']} >= {'missing_labels', 'empty_classes'}
    assert quality['checks_run'] == 7


def test_project_merge_remaps_classes_images_revisions_comments_and_history(client):
    root = client.post('/api/projects', json={'name': 'Root', 'classes': ['Bolt', 'Panel']}).json()
    source = client.post('/api/projects', json={'name': 'Source Set', 'classes': ['Panel', 'Crack']}).json()
    root_image = upload(client, root['id'], 'shared/image.png')
    source_image = upload(client, source['id'], 'shared/image.png')
    saved = save(client, source['id'], source_image, boxes=[
        {'category_id': 2, 'x': 10, 'y': 5, 'width': 30, 'height': 20}]).json()
    assert client.post(f"/api/projects/{source['id']}/comments", json={'body': 'Source progress'}).status_code == 201
    result = client.post(f"/api/projects/{root['id']}/merge",
                         json={'source_project_id': source['id']})
    assert result.status_code == 200, result.text
    assert result.json()['images_merged'] == 1 and result.json()['classes_added'] == 1
    assert [item['name'] for item in result.json()['classes']] == ['Bolt', 'Panel', 'Crack']
    assert client.get(f"/api/projects/{source['id']}").status_code == 404
    images = client.get(f"/api/projects/{root['id']}/images").json()
    assert len(images) == 2
    merged = next(item for item in images if item['id'] == source_image['id'])
    assert merged['source_path'] == 'Source_Set/shared/image.png'
    detail = client.get(f"/api/projects/{root['id']}/images/{merged['id']}").json()
    assert detail['boxes'][0]['category_id'] == 3
    revisions = client.get(f"/api/projects/{root['id']}/images/{merged['id']}/revisions").json()
    assert revisions[0]['boxes'][0]['category_id'] == 3
    assert client.get(f"/api/projects/{root['id']}/images/{merged['id']}/file").status_code == 200
    assert client.get(f"/api/projects/{root['id']}/comments").json()[0]['body'] == 'Source progress'
    history = client.get(f"/api/projects/{root['id']}/history").json()
    assert [(item['kind'], item['sample_delta'], item['total_samples']) for item in history] == [
        ('project_created', 1, 1), ('projects_merged', 1, 2)]
    assert client.get(f"/api/projects/{root['id']}/stats").json()['total'] == 2


def test_project_merge_rejects_different_annotation_types(client):
    detection = project(client)
    classification = client.post('/api/projects', json={'name': 'Classification', 'classes': ['A'],
        'annotation_type': 'image_classification'}).json()['id']
    response = client.post(f'/api/projects/{detection}/merge', json={'source_project_id': classification})
    assert response.status_code == 422
    assert response.json()['detail'] == 'Image Classification and Object Detection projects cannot be merged'
    assert client.get(f'/api/projects/{classification}').status_code == 200


def test_project_card_order_persists_and_rejects_stale_lists(client):
    first = project(client, 'First')
    second = project(client, 'Second')
    third = project(client, 'Third')
    assert [item['id'] for item in client.get('/api/projects').json()] == [first, second, third]
    reordered = client.put('/api/projects/order', json={'project_ids': [third, first, second]})
    assert reordered.status_code == 200
    assert [item['id'] for item in client.get('/api/projects').json()] == [third, first, second]
    service.init_db()
    assert [item['id'] for item in client.get('/api/projects').json()] == [third, first, second]
    assert client.put('/api/projects/order', json={'project_ids': [first, first, second]}).status_code == 422
    assert client.put('/api/projects/order', json={'project_ids': [first, second]}).status_code == 409


def test_class_management_remaps_annotations_and_revisions(client):
    pid = project(client)
    added = client.post(f'/api/projects/{pid}/classes', json={'name': 'Crack', 'color': '#123abc'})
    assert added.status_code == 201 and added.json()['classes'][-1]['id'] == 3
    updated = client.put(f'/api/projects/{pid}/classes/3', json={
        'name': 'Surface crack', 'color': '#abcdef', 'archived': True})
    assert updated.status_code == 200 and updated.json()['classes'][-1]['archived'] is True
    image = upload(client, pid)
    saved = save(client, pid, image, boxes=[
        {'category_id': 3, 'x': 10, 'y': 5, 'width': 30, 'height': 20}])
    assert saved.status_code == 200
    merged = client.post(f'/api/projects/{pid}/classes/3/merge', json={'target_category_id': 1})
    assert merged.status_code == 200
    assert [item['id'] for item in merged.json()['classes']] == [1, 2]
    detail = client.get(f"/api/projects/{pid}/images/{image['id']}").json()
    assert detail['boxes'][0]['category_id'] == 1
    revisions = client.get(f"/api/projects/{pid}/images/{image['id']}/revisions").json()
    assert revisions[0]['boxes'][0]['category_id'] == 1
    assert client.post(f'/api/projects/{pid}/classes', json={'name': 'bolt', 'color': '#123456'}).status_code == 422


def test_publish_is_immutable_and_bulk_review_approves_selection(client, monkeypatch):
    pid = project(client)
    first = upload(client, pid, 'first.png')
    second = upload(client, pid, 'second.png', (90, 70))
    upload(client, pid, 'untouched.png')
    first = save(client, pid, first).json()
    second = save(client, pid, second, boxes=[]).json()
    published = client.post(f'/api/projects/{pid}/publish', headers={'x-forwarded-user': 'publisher'})
    assert published.status_code == 201
    assert published.json()['name'].startswith('v1-') and published.json()['name'].endswith('-ready')
    version_id = published.json()['id']
    assert client.get(f'/api/projects/{pid}/versions').json()[0]['author'] == 'publisher'
    before = client.get(f'/api/projects/{pid}/versions/{version_id}').json()
    assert before['sample_count'] == 2 and before['snapshot']['images'][0]['boxes']
    assert {item['source_path'] for item in before['snapshot']['images']} == {'first.png', 'second.png'}
    assert client.get(f"/api/projects/{pid}/versions/{version_id}/images/{first['id']}/file").status_code == 200

    exported_version = client.get(f'/api/projects/{pid}/versions/{version_id}/export')
    assert exported_version.status_code == 200
    assert f'Inspection_{published.json()["name"]}.zip' in exported_version.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(exported_version.content)) as archive:
        annotation_name = f'annotations/Inspection_{published.json()["name"]}.json'
        frozen = json.loads(archive.read(annotation_name))
        assert frozen['info']['published_version'] == published.json()['name']
        assert len(frozen['images']) == 2 and len(frozen['annotations']) == 1
        assert all(image['file_name'] in archive.namelist() for image in frozen['images'])
    pushed = {}
    def fake_push(objects, message, metadata):
        pushed.update(objects=objects, message=message, metadata=metadata)
        return {'commit_id': 'abc123', 'repository': 'labelling-datasets', 'branch': 'main'}
    monkeypatch.setattr(service.versions.lakefs_client, 'push_snapshot', fake_push)
    lakefs = client.post(f'/api/projects/{pid}/versions/{version_id}/lakefs',
                         headers={'x-forwarded-preferred-username': 'owen'})
    assert lakefs.status_code == 200 and lakefs.json()['commit_id'] == 'abc123'
    assert pushed['message'].startswith(f"Saving {published.json()['name']} at ")
    assert pushed['message'].endswith(' by owen')
    assert [path.split('/')[-2] for path, _, _ in pushed['objects']].count('images') == 2
    assert any(path.endswith('.json') and '/annotations/' in path for path, _, _ in pushed['objects'])
    assert save(client, pid, first, boxes=[]).status_code == 200
    after = client.get(f'/api/projects/{pid}/versions/{version_id}').json()
    assert after['snapshot'] == before['snapshot']
    approved = client.put(f'/api/projects/{pid}/review/bulk', headers={'x-forwarded-user': 'reviewer'},
                          json={'image_ids': [first['id'], second['id']], 'status': 'approved'})
    assert approved.status_code == 200 and approved.json()['updated'] == 2
    rows = client.get(f'/api/projects/{pid}/images').json()
    assert all(item['review_status'] == 'approved' for item in rows if item['id'] in {first['id'], second['id']})
    assert next(item for item in rows if item['source_path'] == 'untouched.png')['review_status'] == 'draft'
    assert all('annotation_count' in item and 'category_ids' in item for item in rows)
    assert client.post(f'/api/projects/{pid}/publish').json()['name'].startswith('v2-')


def test_version_comparison_and_end_to_end_lineage(client, monkeypatch):
    pid = project(client, 'Lineage audit')
    first = upload(client, pid, 'first.png')
    assert save(client, pid, first).status_code == 200
    version_one = client.post(f'/api/projects/{pid}/publish').json()

    current = client.get(f"/api/projects/{pid}/images/{first['id']}").json()
    changed = [{'category_id': 2, 'x': 15, 'y': 10, 'width': 35, 'height': 25}]
    assert save(client, pid, current, boxes=changed).status_code == 200
    assert client.put(f'/api/projects/{pid}/review/bulk', json={
        'image_ids': [first['id']], 'status': 'approved'}).status_code == 200
    second = upload(client, pid, 'second.png', (90, 70))
    assert save(client, pid, second, boxes=[]).status_code == 200
    version_two = client.post(f'/api/projects/{pid}/publish').json()

    compared = client.get(f'/api/projects/{pid}/versions/compare', params={
        'left_id': version_one['id'], 'right_id': version_two['id']})
    assert compared.status_code == 200, compared.text
    payload = compared.json()
    assert payload['images']['added'] == ['second.png']
    assert payload['summary']['annotation_changes'] == 1
    assert payload['summary']['review_changes'] == 1
    assert payload['quality']['right']['samples'] == payload['quality']['left']['samples'] + 1
    assert payload['images']['changed'][0]['left_boxes'] != payload['images']['changed'][0]['right_boxes']
    assert client.get(f'/api/projects/{pid}/versions/compare', params={
        'left_id': version_one['id'], 'right_id': version_one['id']}).status_code == 422

    monkeypatch.setattr(service.versions.lakefs_client, 'push_snapshot', lambda *args: {
        'commit_id': 'lineage123', 'repository': 'datasets', 'branch': 'main'})
    assert client.post(f"/api/projects/{pid}/versions/{version_two['id']}/lakefs").status_code == 200
    now = '2026-10-07 12:00:00'
    with service.database() as db:
        db.execute('''INSERT INTO training_jobs
            (id,project_id,version_id,task_type,base_model,hyperparameters,compute_target,status,
             metrics,artifact_path,mlflow_run_id,error,created_at,completed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            ('job-1', pid, version_two['id'], 'object_detection', 'Detector', '{}', 'local-cpu',
             'completed', '{}', '/tmp/model', '7:run-1', '', now, now))
        db.execute('''INSERT INTO registered_models
            (id,project_id,training_job_id,name,model_version,mlflow_run_id,created_at)
            VALUES (?,?,?,?,?,?,?)''', ('model-1', pid, 'job-1', 'Detector', 1, '7:run-1', now))
        db.execute('''INSERT INTO model_deployments
            (id,project_id,registered_model_id,name,environment,status,endpoint,created_at)
            VALUES (?,?,?,?,?,?,?,?)''',
            ('deployment-1', pid, 'model-1', 'Detector API', 'staging', 'healthy',
             'https://example.test/model', now))

    lineage = client.get(f'/api/projects/{pid}/lineage')
    assert lineage.status_code == 200, lineage.text
    graph = lineage.json()
    assert {'batch', 'version', 'lakefs', 'training', 'model', 'deployment'} <= {
        node['type'] for node in graph['nodes']}
    assert graph['counts'] == {'batches': 1, 'versions': 2, 'lakefs_commits': 1,
                               'training_runs': 1, 'registered_models': 1, 'deployments': 1}
    assert any(edge == {'from': 'training:job-1', 'to': 'model:model-1'} for edge in graph['edges'])
    assert any(edge['from'].startswith('lakefs:') and edge['to'] == 'training:job-1'
               and edge.get('kind') == 'snapshot' for edge in graph['edges'])
    assert {'from': f"version:{version_two['id']}", 'to': 'training:job-1'} in graph['edges']


def test_ai_classification_rejected_and_no_credentials(client, monkeypatch, tmp_path):
    monkeypatch.setenv('GPT_ENV_FILE', str(tmp_path / 'missing.env'))
    result = client.post('/api/ai/validate')
    assert result.status_code == 401
    assert result.json()['detail'] == 'Invalid Credentials Provided'
    pid = client.post('/api/projects', json={'name': 'Classify', 'classes': ['A'],
        'annotation_type': 'image_classification'}).json()['id']
    image = upload(client, pid)
    assert client.post(f"/api/projects/{pid}/images/{image['id']}/ai", json={'revision': 0}).status_code == 422


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'DATA', tmp_path)
    with TestClient(service.app) as client:
        yield client


def project(client, name='Inspection'):
    result = client.post('/api/projects', json={'name': name, 'classes': ['Bolt', 'Panel']})
    assert result.status_code == 201
    return result.json()['id']


def upload(client, pid, filename='folder/a.png', size=(100, 80)):
    data = io.BytesIO()
    Image.new('RGB', size, '#669988').save(data, 'PNG')
    result = client.post(f'/api/projects/{pid}/images', files={'file': (filename, data.getvalue(), 'image/png')})
    assert result.status_code == 201, result.text
    return result.json()


def save(client, pid, image, boxes=None, completed=True):
    return client.put(f"/api/projects/{pid}/images/{image['id']}", json={
        'revision': image['revision'], 'completed': completed,
        'boxes': boxes if boxes is not None else [{'category_id': 1, 'x': 10, 'y': 5, 'width': 30, 'height': 20}]})


def test_persistence_duplicates_and_project_isolation(client):
    pid = project(client)
    other = project(client, 'Other project')
    image = upload(client, pid)
    assert save(client, pid, image).status_code == 200
    duplicate = upload(client, pid)
    assert duplicate['id'] == image['id']
    assert duplicate['completed'] is True
    assert len(client.get(f'/api/projects/{pid}/images').json()) == 1
    assert client.get(f'/api/projects/{other}/images').json() == []
    assert client.get(f"/api/projects/{other}/images/{image['id']}/file").status_code == 404
    service.init_db()  # Startup must preserve existing projects and annotations.
    with TestClient(service.app) as restarted:
        persisted = restarted.get(f"/api/projects/{pid}/images/{image['id']}").json()
        assert persisted['boxes'][0]['width'] == 30
        assert persisted['completed'] is True


def test_validation_and_conflicting_edits(client):
    assert client.post('/api/projects', json={'name': ' ', 'classes': ['A']}).status_code == 422
    assert client.post('/api/projects', json={'name': 'X', 'classes': ['A', 'a']}).status_code == 422
    pid = project(client)
    image = upload(client, pid)
    bad_boxes = [
        {'category_id': 3, 'x': 1, 'y': 1, 'width': 10, 'height': 10},
        {'category_id': 1, 'x': 95, 'y': 1, 'width': 10, 'height': 10},
        {'category_id': 1, 'x': 1, 'y': 1, 'width': 0, 'height': 10},
        {'category_id': 1, 'x': -1, 'y': 1, 'width': 10, 'height': 10},
    ]
    for box in bad_boxes:
        assert save(client, pid, image, [box]).status_code == 422
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: save(client, pid, image).status_code, range(2)))
    assert sorted(results) == [200, 409]
    assert client.post(f'/api/projects/{pid}/images', files={'file': ('bad.png', b'not an image')}).status_code == 422
    assert client.post(f'/api/projects/{pid}/images', files={'file': ('../bad.png', b'no')}).status_code == 422


def test_delete_project_removes_database_records_and_images(client):
    pid = project(client)
    other = project(client, 'Keep this project')
    image = upload(client, pid)
    upload(client, other, 'other.png')
    stored = service.DATA / 'images' / pid / f"{image['id']}.png"
    assert stored.is_file()

    response = client.delete(f'/api/projects/{pid}')

    assert response.status_code == 200
    assert response.json() == {'deleted': pid}
    assert client.get(f'/api/projects/{pid}').status_code == 404
    assert client.get(f'/api/projects/{pid}/images').status_code == 404
    assert not (service.DATA / 'images' / pid).exists()
    assert client.get(f'/api/projects/{other}').status_code == 200
    assert len(client.get(f'/api/projects/{other}/images').json()) == 1
    assert client.delete(f'/api/projects/{pid}').status_code == 404


def test_exif_orientation_is_normalized(client):
    pid = project(client)
    image = Image.new('RGB', (30, 50))
    exif = image.getexif()
    exif[274] = 6
    raw = io.BytesIO()
    image.save(raw, 'JPEG', exif=exif)
    row = client.post(f'/api/projects/{pid}/images', files={'file': ('rotated.jpg', raw.getvalue())}).json()
    assert (row['width'], row['height']) == (50, 30)
    stored = client.get(f"/api/projects/{pid}/images/{row['id']}/file")
    assert Image.open(io.BytesIO(stored.content)).size == (50, 30)


def test_kpis_and_coco_split(client):
    pid = project(client)
    for i in range(6):
        image = upload(client, pid, f'dataset/{i}.png')
        if i < 5:
            assert save(client, pid, image, [] if i == 4 else None).status_code == 200
    stats = client.get(f'/api/projects/{pid}/stats').json()
    assert (stats['total'], stats['completed'], stats['remaining'], stats['boxes']) == (6, 5, 1, 4)
    assert stats['classes'][0] == {'id': 1, 'name': 'Bolt', 'boxes': 4, 'images': 4}
    assert stats['classes'][1]['boxes'] == 0
    exported = {}
    for split in ('train', 'test'):
        response = client.post(f'/api/projects/{pid}/export', json={
            'train_percent': 80, 'description': 'Fastener inspection dataset', 'split': split})
        assert response.status_code == 200
        assert f'Inspection_{split}.zip' in response.headers['content-disposition']
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        coco = json.loads(archive.read(f'annotations/Inspection_{split}.json'))
        exported[split] = (coco, archive.namelist(), response.content)
        expected_images = 4 if split == 'train' else 1
        assert set(archive.namelist()) >= {'annotations/', 'images/', f'annotations/Inspection_{split}.json'}
        assert all(name.startswith(('annotations/', 'images/')) for name in archive.namelist())
        for image in coco['images']:
            assert image['file_name'] in archive.namelist()
        assert coco['info']['description'] == 'Fastener inspection dataset'
        assert coco['info']['project_name'] == 'Inspection'
        assert coco['info']['split'] == split
        assert coco['info']['images_annotated'] == expected_images
        assert coco['info']['total_images_annotated'] == 5
        assert datetime.fromisoformat(coco['info']['date_created'].replace('Z', '+00:00')).tzinfo
        assert [item['name'] for item in coco['info']['class_distribution']] == ['Bolt', 'Panel']
    train, test = exported['train'][0], exported['test'][0]
    round_trip = client.post('/api/projects/import',
                             data={'name': 'Imported Train'},
                             files={'file': ('Inspection_train.zip', exported['train'][2], 'application/zip')})
    assert round_trip.status_code == 201, round_trip.text
    assert round_trip.json()['images_imported'] == 4 and round_trip.json()['updated'] == 4
    with zipfile.ZipFile(io.BytesIO(client.post(f'/api/projects/{pid}/export', json={
            'train_percent': 80, 'description': 'Fastener inspection dataset', 'split': 'train'}).content)) as repeated_archive:
        repeated = json.loads(repeated_archive.read('annotations/Inspection_train.json'))
    assert repeated | {'info': repeated['info'] | {'date_created': train['info']['date_created']}} == train
    combined = {
        name: sum(next(item['annotations'] for item in coco['info']['class_distribution'] if item['name'] == name)
                  for coco in (train, test))
        for name in ('Bolt', 'Panel')
    }
    assert combined == {'Bolt': 4, 'Panel': 0}
    assert (len(train['images']), len(test['images'])) == (4, 1)
    train_names = {i['file_name'] for i in train['images']}
    test_names = {i['file_name'] for i in test['images']}
    assert train_names.isdisjoint(test_names)
    assert len(train['annotations']) + len(test['annotations']) == 4
    for split, coco in [('train', train), ('test', test)]:
        assert coco['categories'][1]['id'] == 2
        image_ids = {i['id'] for i in coco['images']}
        for annotation in coco['annotations']:
            assert annotation['image_id'] in image_ids
            assert annotation['bbox'] == [10, 5, 30, 20]
            assert annotation['area'] == 600
    for percentage, split, expected in [(0, 'test', 5), (100, 'train', 5)]:
        response = client.post(f'/api/projects/{pid}/export', json={'train_percent': percentage, 'split': split})
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert len(json.loads(archive.read(f'annotations/Inspection_{split}.json'))['images']) == expected
    assert client.post(f'/api/projects/{pid}/export', json={'train_percent': 0, 'split': 'train'}).status_code == 422
    assert client.post(f'/api/projects/{pid}/export', json={'train_percent': 100, 'split': 'test'}).status_code == 422


def test_export_requires_completed_images_and_valid_split(client):
    pid = project(client)
    upload(client, pid)
    for payload in ({'train_percent': 80, 'split': 'train'}, {'train_percent': 101, 'split': 'train'},
                    {'train_percent': 80, 'split': 'validation'}):
        assert client.post(f'/api/projects/{pid}/export', json=payload).status_code == 422


def test_upload_size_and_same_name_conflict(client, monkeypatch):
    pid = project(client)
    upload(client, pid)
    raw = io.BytesIO()
    Image.new('RGB', (10, 10)).save(raw, 'PNG')
    assert client.post(f'/api/projects/{pid}/images', files={'file': ('folder/a.png', raw.getvalue())}).status_code == 409
    monkeypatch.setattr(service, 'MAX_UPLOAD', 4)
    monkeypatch.setattr(service.images, 'MAX_UPLOAD', 4)
    assert client.post(f'/api/projects/{pid}/images', files={'file': ('big.png', b'12345')}).status_code == 413


def test_dataset_history_batches_and_revision_history(client):
    pid = project(client)
    first = upload(client, pid, 'initial/a.png')
    batch = client.post(f'/api/projects/{pid}/batches', json={'kind': 'new_additions'})
    assert batch.status_code == 201
    second_data = io.BytesIO()
    Image.new('RGB', (40, 30), '#123456').save(second_data, 'PNG')
    second = client.post(f"/api/projects/{pid}/images?batch_id={batch.json()['id']}",
                         files={'file': ('later/b.png', second_data.getvalue(), 'image/png')})
    assert second.status_code == 201
    history = client.get(f'/api/projects/{pid}/history').json()
    assert [(row['version'], row['kind'], row['samples'], row['total_samples']) for row in history] == [
        (1, 'project_created', 1, 1), (2, 'new_additions', 1, 2)]
    batch_images = client.get(f"/api/projects/{pid}/batches/{batch.json()['id']}/images").json()
    assert [item['source_path'] for item in batch_images] == ['later/b.png']
    assert save(client, pid, first).status_code == 200
    saved = client.get(f"/api/projects/{pid}/images/{first['id']}").json()
    assert save(client, pid, saved, boxes=[]).status_code == 200
    revisions = client.get(f"/api/projects/{pid}/images/{first['id']}/revisions").json()
    assert [row['revision'] for row in revisions] == [2, 1, 0]
    assert revisions[1]['boxes'][0]['category_id'] == 1
    stored = service.DATA / 'images' / pid / f"{first['id']}.png"
    assert stored.is_file()
    deleted = client.delete(f"/api/projects/{pid}/images/{first['id']}")
    assert deleted.status_code == 200 and deleted.json() == {'deleted': first['id']}
    assert not stored.exists()
    assert client.get(f"/api/projects/{pid}/images/{first['id']}").status_code == 404
    service.init_db()
    history = client.get(f'/api/projects/{pid}/history').json()
    assert [(row['kind'], row['sample_delta'], row['total_samples']) for row in history] == [
        ('project_created', 1, 1), ('new_additions', 1, 2), ('images_deleted', -1, 1)]
    deletion = history[-1]
    detail = deletion['details'][0]
    assert {key: detail[key] for key in ('id', 'source_path', 'width', 'height', 'completed', 'restorable')} == {
        'id': first['id'], 'source_path': 'initial/a.png', 'width': 100, 'height': 80,
        'completed': True, 'restorable': True}
    assert client.get(f"/api/projects/{pid}/history/{deletion['id']}/deleted/{first['id']}/file").status_code == 200
    with service.database() as db:
        assert db.execute('SELECT COUNT(*) FROM annotation_revisions WHERE image_id=?',
                          (first['id'],)).fetchone()[0] == 0
    restored = client.post(f"/api/projects/{pid}/history/{deletion['id']}/deleted/{first['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()['revision'] == 2 and restored.json()['boxes'] == []
    assert stored.is_file()
    assert [item['revision'] for item in client.get(
        f"/api/projects/{pid}/images/{first['id']}/revisions").json()] == [2, 1, 0]
    history = client.get(f'/api/projects/{pid}/history').json()
    assert history[-1]['kind'] == 'images_restored' and history[-1]['total_samples'] == 2
    assert history[-2]['details'][0]['restorable'] is False
    assert client.post(f"/api/projects/{pid}/history/{deletion['id']}/deleted/{first['id']}/restore").status_code == 409


def test_coco_and_yolo_annotation_import(client):
    pid = project(client)
    coco_image = upload(client, pid, 'nested/coco.png')
    document = {'images': [{'id': 7, 'file_name': 'images/coco.png'}],
                'categories': [{'id': 9, 'name': 'Bolt'}],
                'annotations': [{'id': 1, 'image_id': 7, 'category_id': 9, 'bbox': [1, 2, 20, 30]}]}
    response = client.post(f'/api/projects/{pid}/annotations/import',
                           files={'file': ('annotations.json', json.dumps(document), 'application/json')})
    assert response.status_code == 200 and response.json()['updated'] == 1
    assert client.get(f"/api/projects/{pid}/images/{coco_image['id']}").json()['boxes'][0] == {
        'category_id': 1, 'x': 1.0, 'y': 2.0, 'width': 20.0, 'height': 30.0}

    yolo_image = upload(client, pid, 'nested/yolo.png')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as zipped:
        zipped.writestr('labels/yolo.txt', '1 0.5 0.5 0.2 0.25\n')
    response = client.post(f'/api/projects/{pid}/annotations/import',
                           files={'file': ('labels.zip', archive.getvalue(), 'application/zip')})
    assert response.status_code == 200
    box = client.get(f"/api/projects/{pid}/images/{yolo_image['id']}").json()['boxes'][0]
    assert box == {'category_id': 2, 'x': 40.0, 'y': 30.0, 'width': 20.0, 'height': 20.0}

    imported_pid = project(client, 'Imported dataset')
    raw_image = io.BytesIO(); Image.new('RGB', (50, 40), '#abcdef').save(raw_image, 'JPEG')
    zipped_dataset = io.BytesIO()
    imported_coco = {'images': [{'id': 1, 'file_name': 'images/new.jpg'}],
                     'categories': [{'id': 1, 'name': 'Panel'}],
                     'annotations': [{'image_id': 1, 'category_id': 1, 'bbox': [5, 5, 10, 10]}]}
    with zipfile.ZipFile(zipped_dataset, 'w') as zipped:
        zipped.writestr('train/images/new.jpg', raw_image.getvalue())
        zipped.writestr('train/annotations.json', json.dumps(imported_coco))
    response = client.post(f'/api/projects/{imported_pid}/annotations/import',
                           files={'file': ('coco.zip', zipped_dataset.getvalue(), 'application/zip')})
    assert response.status_code == 200, response.text
    assert response.json() == {'updated': 1, 'images_imported': 1, 'unmatched': []}
    imported = client.get(f'/api/projects/{imported_pid}/images').json()
    assert len(imported) == 1 and imported[0]['completed'] is True


def test_similar_image_groups_are_reported_in_stats(client):
    pid = project(client)
    upload(client, pid, 'first.png', (100, 80))
    upload(client, pid, 'second.png', (120, 90))
    duplicate_data = client.get(f'/api/projects/{pid}/duplicates').json()
    assert duplicate_data['similar_images'] == 2
    assert len(duplicate_data['groups']) == 1
    assert {item['source_path'] for item in duplicate_data['groups'][0]['images']} == {'first.png', 'second.png'}
    stats = client.get(f'/api/projects/{pid}/stats').json()
    assert stats['similar_images'] == 2 and stats['similar_groups'] == 1


def test_import_project_zip_creates_repository_project_and_rolls_back_errors(client):
    image_data = io.BytesIO()
    Image.new('RGB', (60, 40), '#457890').save(image_data, 'PNG')
    document = {
        'info': {'project_name': 'Imported Inspection', 'annotation_type': 'image_classification'},
        'images': [{'id': 1, 'file_name': 'images/sample.png', 'width': 60, 'height': 40}],
        'categories': [{'id': 5, 'name': 'Bolt'}, {'id': 8, 'name': 'Panel'}],
        'annotations': [{'id': 1, 'image_id': 1, 'category_id': 5, 'bbox': [4, 5, 20, 10]}],
    }
    project_zip = io.BytesIO()
    with zipfile.ZipFile(project_zip, 'w') as archive:
        archive.writestr('annotations/instances.json', json.dumps(document))
        archive.writestr('images/sample.png', image_data.getvalue())
    response = client.post('/api/projects/import',
                           data={'name': 'Chosen Repository Name'},
                           files={'file': ('inspection.zip', project_zip.getvalue(), 'application/zip')})
    assert response.status_code == 201, response.text
    imported = response.json()
    assert imported['project']['name'] == 'Chosen Repository Name'
    assert imported['project']['annotation_type'] == 'object_detection'
    assert [item['name'] for item in imported['project']['classes']] == ['Bolt', 'Panel']
    assert imported['images_imported'] == 1 and imported['updated'] == 1
    pid = imported['project']['id']
    images = client.get(f'/api/projects/{pid}/images').json()
    assert len(images) == 1 and images[0]['completed'] is True
    detail = client.get(f"/api/projects/{pid}/images/{images[0]['id']}").json()
    assert detail['boxes'][0]['category_id'] == 1

    assert client.post('/api/projects/import', data={'name': 'Bad'},
                       files={'file': ('bad.zip', b'not zip')}).status_code == 422
    assert client.post('/api/projects/import', data={'name': '   '},
                       files={'file': ('inspection.zip', project_zip.getvalue())}).status_code == 422
    assert client.post('/api/projects/import', files={'file': ('inspection.zip', project_zip.getvalue())}).status_code == 422
    bad_zip = io.BytesIO()
    document['annotations'][0]['bbox'] = [55, 5, 20, 10]
    with zipfile.ZipFile(bad_zip, 'w') as archive:
        archive.writestr('annotations/instances.json', json.dumps(document))
        archive.writestr('images/sample.png', image_data.getvalue())
    before = len(client.get('/api/projects').json())
    assert client.post('/api/projects/import', data={'name': 'Invalid'},
                       files={'file': ('invalid.zip', bad_zip.getvalue())}).status_code == 422
    assert len(client.get('/api/projects').json()) == before

    classification = {
        'info': {'annotation_type': 'object_detection'},
        'images': [{'id': 1, 'file_name': 'images/sample.png', 'category_ids': [5]}],
        'categories': [{'id': 5, 'name': 'Bolt'}], 'annotations': [],
    }
    classification_zip = io.BytesIO()
    with zipfile.ZipFile(classification_zip, 'w') as archive:
        archive.writestr('annotations/classes.json', json.dumps(classification))
        archive.writestr('images/sample.png', image_data.getvalue())
    classified = client.post('/api/projects/import', data={'name': 'Classification'},
        files={'file': ('classification.zip', classification_zip.getvalue())})
    assert classified.status_code == 201, classified.text
    assert classified.json()['project']['annotation_type'] == 'image_classification'

    malformed = classification | {'annotations': [{'image_id': 1, 'category_id': 5}]}
    malformed_zip = io.BytesIO()
    with zipfile.ZipFile(malformed_zip, 'w') as archive:
        archive.writestr('annotations/bad.json', json.dumps(malformed))
        archive.writestr('images/sample.png', image_data.getvalue())
    before = len(client.get('/api/projects').json())
    invalid = client.post('/api/projects/import', data={'name': 'Malformed'},
        files={'file': ('malformed.zip', malformed_zip.getvalue())})
    assert invalid.status_code == 422 and 'bbox' in invalid.json()['detail']
    assert len(client.get('/api/projects').json()) == before


def test_project_comments_are_persistent_timestamped_and_use_forwarded_user(client):
    pid = project(client)
    assert client.get(f'/api/projects/{pid}/comments').json() == []
    assert client.post(f'/api/projects/{pid}/comments', json={'body': '   '}).status_code == 422
    first = client.post(f'/api/projects/{pid}/comments', json={'body': 'Initial upload complete.'},
                        headers={'x-forwarded-preferred-username': 'owen'})
    assert first.status_code == 201
    assert first.json()['author'] == 'owen'
    assert datetime.fromisoformat(first.json()['created_at'].replace('Z', '+00:00'))
    second = client.post(f'/api/projects/{pid}/comments', json={'body': 'Review started.'})
    assert second.status_code == 201 and second.json()['author'] == 'admin'
    service.init_db()
    comments = client.get(f'/api/projects/{pid}/comments').json()
    assert [item['body'] for item in comments] == ['Review started.', 'Initial upload complete.']
    assert client.delete(f'/api/projects/{pid}').status_code == 200
    assert client.get(f'/api/projects/{pid}/comments').status_code == 404


def test_training_run_name_and_config_tracking(client, monkeypatch):
    import re
    from routes import training
    caps = {'models': {'object_detection': [{'key': 'demo'}]}, 'gpu': {'available': False}}
    monkeypatch.setattr(training, '_capabilities', lambda url: caps)
    from types import SimpleNamespace
    monkeypatch.setattr(training, 'threading', SimpleNamespace(Thread=lambda **kwargs: SimpleNamespace(start=lambda: None)))
    project = client.post('/api/projects', json={'name': 'Test Project', 'classes': ['Object']}).json()
    image = upload(client, project['id'])
    assert save(client, project['id'], image).status_code == 200
    version = client.post(f"/api/projects/{project['id']}/publish").json()
    payload = {'version_id': version['id'], 'base_model': 'demo', 'hyperparameters': {'callbacks': ['tensorboard', 'gradcam']}}
    path = f"/api/projects/{project['id']}/training/jobs"
    first = client.post(path, json=payload).json()
    second = client.post(path, json=payload).json()
    assert re.fullmatch(r'\d{6}-test-project-v1', first['run_name'])
    assert second['run_name'].endswith('-v2')
    calls = []
    def request(url, **kwargs):
        calls.append((url, kwargs))
        if 'get-by-name' in url: return httpx.Response(200, request=httpx.Request('GET', url), json={'experiment': {'experiment_id': '1'}})
        if url.endswith('/create'): return httpx.Response(200, request=httpx.Request('GET', url), json={'run': {'info': {'run_id': 'run'}}})
        return httpx.Response(200, request=httpx.Request('GET', url), json={})
    import httpx
    monkeypatch.setattr(training.httpx, 'get', request)
    monkeypatch.setattr(training.httpx, 'post', request)
    config = {'epochs': 3, 'augmentations': {'blur': 0.2}, 'callbacks': ['tensorboard', 'gradcam'], 'class_names': ['Object']}
    assert training._mlflow(first, {'loss': 1.0}, config) == '1:run'
    logged = next(kwargs['json'] for url, kwargs in calls if url.endswith('/log-batch'))
    assert {item['key']: json.loads(item['value']) for item in logged['params'] if item['key'].startswith('config.')} == {f'config.{key}': value for key, value in config.items()}
    assert next(kwargs['json']['run_name'] for url, kwargs in calls if url.endswith('/create')) == first['run_name']
