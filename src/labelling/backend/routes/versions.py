from fastapi import APIRouter
from common import *
import lakefs_client

router = APIRouter()

@router.post('/api/projects/{project_id}/publish', status_code=201)
def publish_version(project_id: str, request: Request):
    version_id = uuid.uuid4().hex
    directory = DATA / 'versions' / project_id / version_id
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('''SELECT * FROM images WHERE project_id=? AND completed=1
            ORDER BY source_path,id''', (project_id,)).fetchall()
        if not rows:
            raise HTTPException(422, 'Complete at least one annotation before publishing')
        number = db.execute('SELECT COALESCE(MAX(version_number),0)+1 FROM dataset_versions WHERE project_id=?',
                            (project_id,)).fetchone()[0]
        name = f'v{number}-{datetime.now(timezone.utc).strftime("%y%m%d")}-ready'
        author = (request.headers.get('x-forwarded-preferred-username') or
                  request.headers.get('x-forwarded-user') or 'admin').strip()[:150] or 'admin'
        snapshot = {'project': {key: project[key] for key in ('name', 'annotation_type', 'classes', 'description',
                    'labelling_instructions', 'ai_instructions', 'export_train_percent')},
                    'images': [image_json(row) | {'stored_name': row['stored_name']} for row in rows]}
        try:
            directory.mkdir(parents=True)
            for row in rows:
                shutil.copy2(DATA / 'images' / project_id / row['stored_name'], directory / row['stored_name'])
            db.execute('''INSERT INTO dataset_versions
                (id,project_id,version_number,name,author,sample_count,snapshot) VALUES (?,?,?,?,?,?,?)''',
                (version_id, project_id, number, name, author, len(rows), json.dumps(snapshot)))
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        return {'id': version_id, 'version_number': number, 'name': name, 'author': author,
                'sample_count': len(rows), 'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}


@router.get('/api/projects/{project_id}/versions')
def versions(project_id: str):
    with database() as db:
        get_project(db, project_id)
        return [dict(row) for row in db.execute('''SELECT id,version_number,name,author,sample_count,created_at
            FROM dataset_versions WHERE project_id=? ORDER BY version_number DESC''', (project_id,))]


@router.get('/api/projects/{project_id}/versions/{version_id}')
def version_detail(project_id: str, version_id: str):
    with database() as db:
        row = db.execute('SELECT * FROM dataset_versions WHERE id=? AND project_id=?',
                         (version_id, project_id)).fetchone()
        if row is None:
            raise HTTPException(404, 'Published version not found')
        return {key: row[key] for key in ('id', 'version_number', 'name', 'author', 'sample_count', 'created_at')} | {
            'snapshot': json.loads(row['snapshot'])}


def _version_content(project_id, version_id, detail):
    snapshot, project = detail['snapshot'], detail['snapshot']['project']
    safe_project = re.sub(r'[^A-Za-z0-9._-]+', '_', project['name']).strip('._-')[:80] or 'project'
    archive_name = f"{safe_project}_{detail['name']}"
    coco = {'info': {'description': project.get('description', ''), 'project_name': project['name'],
             'annotation_type': project['annotation_type'], 'published_version': detail['name'],
             'date_created': detail['created_at'], 'images_annotated': len(snapshot['images'])},
            'licenses': [], 'images': [], 'annotations': [],
            'categories': [category | {'supercategory': ''} for category in project['classes']]}
    objects = []
    for item in snapshot['images']:
        image_id = len(coco['images']) + 1
        record = {'id': image_id, 'file_name': f"images/{item['stored_name']}",
                  'width': item['width'], 'height': item['height'], 'source_path': item['source_path']}
        if project['annotation_type'] == 'image_classification':
            record['category_ids'] = item['labels']
        coco['images'].append(record)
        path = DATA / 'versions' / project_id / version_id / item['stored_name']
        if not path.is_file():
            raise HTTPException(404, f'Frozen image {item["source_path"]} is unavailable')
        objects.append((record['file_name'], path.read_bytes(), 'application/octet-stream'))
        for box in item['boxes']:
            coco['annotations'].append({'id': len(coco['annotations']) + 1, 'image_id': image_id,
                'category_id': box['category_id'], 'bbox': [box['x'], box['y'], box['width'], box['height']],
                'area': box['width'] * box['height'], 'iscrowd': 0, 'segmentation': []})
    annotation_path = f'annotations/{archive_name}.json'
    objects.append((annotation_path, json.dumps(coco, indent=2).encode(), 'application/json'))
    return archive_name, coco, objects


@router.get('/api/projects/{project_id}/versions/{version_id}/export')
def export_version(project_id: str, version_id: str):
    detail = version_detail(project_id, version_id)
    archive_name, _, objects = _version_content(project_id, version_id, detail)
    fd, temp_path = tempfile.mkstemp(suffix='.zip')
    os.close(fd)
    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('annotations/', b'')
            archive.writestr('images/', b'')
            for path, content, _ in objects:
                archive.writestr(path, content)
    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        raise
    return FileResponse(temp_path, media_type='application/zip', filename=f'{archive_name}.zip',
                        background=BackgroundTask(lambda: Path(temp_path).unlink(missing_ok=True)))


@router.post('/api/projects/{project_id}/versions/{version_id}/lakefs')
def push_version_to_lakefs(project_id: str, version_id: str, request: Request):
    detail = version_detail(project_id, version_id)
    archive_name, _, objects = _version_content(project_id, version_id, detail)
    username = (request.headers.get('x-forwarded-preferred-username') or
                request.headers.get('x-forwarded-user') or 'admin').strip()[:150] or 'admin'
    date = datetime.now(timezone.utc).strftime('%d-%m-%y')
    message = f"Saving {detail['name']} at {date} by {username}"
    prefix = f'{archive_name}/'
    try:
        result = lakefs_client.push_snapshot(
            [(prefix + path, content, content_type) for path, content, content_type in objects],
            message, {'dataset_version': detail['name'], 'project': detail['snapshot']['project']['name'],
                      'published_by': detail['author'], 'pushed_by': username})
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc
    return result | {'message': message, 'path': prefix}


@router.get('/api/projects/{project_id}/versions/{version_id}/images/{image_id}/file')
def version_image_file(project_id: str, version_id: str, image_id: str):
    detail = version_detail(project_id, version_id)
    image = next((item for item in detail['snapshot']['images'] if item['id'] == image_id), None)
    if image is None:
        raise HTTPException(404, 'Version image not found')
    path = DATA / 'versions' / project_id / version_id / image['stored_name']
    if not path.is_file():
        raise HTTPException(404, 'Version image file is unavailable')
    return FileResponse(path, media_type='image/png')
