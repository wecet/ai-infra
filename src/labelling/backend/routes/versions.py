from fastapi import APIRouter
from common import *

router = APIRouter()

@router.post('/api/projects/{project_id}/publish', status_code=201)
def publish_version(project_id: str, request: Request):
    version_id = uuid.uuid4().hex
    directory = DATA / 'versions' / project_id / version_id
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY source_path,id', (project_id,)).fetchall()
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
