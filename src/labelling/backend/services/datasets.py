"""Immutable dataset lookup and archive construction independent of HTTP routes."""
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path
from fastapi import HTTPException
import common
from common import database

def version_detail(project_id: str, version_id: str):
    with database() as db:
        row = db.execute('SELECT * FROM dataset_versions WHERE id=? AND project_id=?',
                         (version_id, project_id)).fetchone()
        if row is None:
            raise HTTPException(404, 'Published version not found')
        return {key: row[key] for key in ('id', 'version_number', 'name', 'author', 'sample_count', 'created_at')} | {
            'snapshot': json.loads(row['snapshot'])}


def _version_content(project_id, version_id, detail, lazy=False):
    snapshot, project = detail['snapshot'], detail['snapshot']['project']
    safe_project = re.sub(r'[^A-Za-z0-9._-]+', '_', project['name']).strip('._-')[:80] or 'project'
    archive_name = f"{safe_project}_{detail['name']}"
    coco = {'info': {'description': project.get('description', ''), 'project_name': project['name'],
             'annotation_type': project['annotation_type'], 'published_version': detail['name'],
             'date_created': detail['created_at'], 'images_annotated': len(snapshot['images'])},
            'schema_version': snapshot.get('schema_version', 1), 'licenses': [], 'images': [], 'annotations': [],
            'categories': [category | {'supercategory': ''} for category in project['classes']]}
    if project['annotation_type'] == 'anomaly_detection':
        coco['info'].update(train_percent=project['export_train_percent'], split_seed=42,
                            train_samples=sum(item['split'] == 'train' for item in snapshot['images']),
                            test_samples=sum(item['split'] == 'test' for item in snapshot['images']))
    objects = []
    for item in snapshot['images']:
        image_id = len(coco['images']) + 1
        record = {'id': image_id, 'file_name': f"images/{item['stored_name']}",
                  'width': item['width'], 'height': item['height'], 'source_path': item['source_path']}
        if project['annotation_type'] == 'image_classification':
            record['category_ids'] = item['labels']
        if 'split' in item: record['split'] = item['split']
        coco['images'].append(record)
        path = common.DATA / 'versions' / project_id / version_id / item['stored_name']
        if not path.is_file():
            raise HTTPException(404, f'Frozen image {item["source_path"]} is unavailable')
        objects.append((record['file_name'], path if lazy else path.read_bytes(), 'application/octet-stream'))
        for box in item['boxes']:
            coco['annotations'].append({'id': len(coco['annotations']) + 1, 'image_id': image_id,
                'category_id': box['category_id'], 'bbox': [box['x'], box['y'], box['width'], box['height']],
                'area': box['width'] * box['height'], 'iscrowd': 0, 'segmentation': []})
    annotation_path = f'annotations/{archive_name}.json'
    objects.append((annotation_path, json.dumps(coco, indent=2).encode(), 'application/json'))
    return archive_name, coco, objects


def _archive(project_id, version_id, image_ids=None, stream=False):
    detail = version_detail(project_id, version_id)
    _, manifest, objects = _version_content(project_id, version_id, detail, lazy=stream)
    by_name = {f"images/{item['stored_name']}": item for item in detail['snapshot']['images']}
    for record in manifest['images']:
        record['studio_image_id'] = by_name[record['file_name']]['id']
    if image_ids is not None:
        allowed = set(image_ids)
        manifest['images'] = [record for record in manifest['images'] if record['studio_image_id'] in allowed]
        ids = {record['id'] for record in manifest['images']}
        manifest['annotations'] = [item for item in manifest['annotations'] if item['image_id'] in ids]
        files = {record['file_name'] for record in manifest['images']}
        objects = [item for item in objects if item[0] in files or item[0].endswith('.json')]
    manifest['info']['archive_samples'] = len(manifest['images'])
    if manifest['info']['annotation_type'] == 'anomaly_detection':
        manifest['info']['train_samples'] = sum(image.get('split') == 'train' for image in manifest['images'])
        manifest['info']['test_samples'] = sum(image.get('split') == 'test' for image in manifest['images'])
    buffer = tempfile.TemporaryFile() if stream else io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path, content, _ in objects:
            if isinstance(content, Path): bundle.write(content, path)
            else: bundle.writestr(path, json.dumps(manifest).encode() if path.endswith('.json') else content)
    if stream:
        buffer.seek(0)
        return detail, buffer
    return detail, buffer.getvalue()


