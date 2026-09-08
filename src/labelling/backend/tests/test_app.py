import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as service


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
