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
    archive = client.post(f'/api/projects/{pid}/export', json={'filename': 'classes', 'train_percent': 100})
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        data = json.loads(z.read('train/classes.json'))
        assert data['info']['annotation_type'] == 'image_classification'
        assert data['annotations'] == []
        assert sorted(im['category_ids'] for im in data['images']) == [[], [1, 2]]
        assert json.loads(z.read('test/classes.json'))['images'] == []
        assert [c['annotations'] for c in data['info']['class_distribution']] == [1, 1]


def test_old_database_migration(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setattr(service, 'DATA', tmp_path)
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
    response = client.post(f'/api/projects/{pid}/export', json={
        'filename': 'my-dataset', 'train_percent': 80, 'description': 'Fastener inspection dataset'})
    assert response.status_code == 200
    assert 'my-dataset.zip' in response.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        train = json.loads(archive.read('train/my-dataset.json'))
        test = json.loads(archive.read('test/my-dataset.json'))
        for split, coco, expected_images in [('train', train, 4), ('test', test, 1)]:
            assert coco['info']['description'] == 'Fastener inspection dataset'
            assert coco['info']['project_name'] == 'Inspection'
            assert coco['info']['split'] == split
            assert coco['info']['images_annotated'] == expected_images
            assert coco['info']['total_images_annotated'] == 5
            assert datetime.fromisoformat(coco['info']['date_created'].replace('Z', '+00:00')).tzinfo
            assert [item['name'] for item in coco['info']['class_distribution']] == ['Bolt', 'Panel']
        assert train['info']['date_created'] == test['info']['date_created']
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
            for image in coco['images']:
                assert f"{split}/{image['file_name']}" in archive.namelist()
            for annotation in coco['annotations']:
                assert annotation['image_id'] in image_ids
                assert annotation['bbox'] == [10, 5, 30, 20]
                assert annotation['area'] == 600
    repeat = client.post(f'/api/projects/{pid}/export', json={
        'filename': 'my-dataset', 'train_percent': 80, 'description': 'Fastener inspection dataset'})
    with zipfile.ZipFile(io.BytesIO(repeat.content)) as archive:
        repeated = json.loads(archive.read('train/my-dataset.json'))
        assert repeated | {'info': repeated['info'] | {'date_created': train['info']['date_created']}} == train
    for percentage, expected in [(0, 0), (100, 5)]:
        response = client.post(f'/api/projects/{pid}/export', json={'filename': 'edge', 'train_percent': percentage})
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert len(json.loads(archive.read('train/edge.json'))['images']) == expected


def test_export_requires_completed_images_and_safe_filename(client):
    pid = project(client)
    upload(client, pid)
    for filename, percent in [('empty', 80), ('../unsafe', 80), ('okay', 101)]:
        assert client.post(f'/api/projects/{pid}/export', json={'filename': filename, 'train_percent': percent}).status_code == 422


def test_upload_size_and_same_name_conflict(client, monkeypatch):
    pid = project(client)
    upload(client, pid)
    raw = io.BytesIO()
    Image.new('RGB', (10, 10)).save(raw, 'PNG')
    assert client.post(f'/api/projects/{pid}/images', files={'file': ('folder/a.png', raw.getvalue())}).status_code == 409
    monkeypatch.setattr(service, 'MAX_UPLOAD', 4)
    assert client.post(f'/api/projects/{pid}/images', files={'file': ('big.png', b'12345')}).status_code == 413
