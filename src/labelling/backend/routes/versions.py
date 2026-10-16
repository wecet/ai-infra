from fastapi import APIRouter
from common import (
    BackgroundTask, DATA, FileResponse, HTTPException, Path, Request, database, datetime, get_project, image_json, json, os, shutil, tempfile, timezone, uuid, zipfile
)
import lakefs_client
from services.partitions import freeze
from services import datasets as dataset_service

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
            raise HTTPException(422, 'Import at least one image before publishing' if project['annotation_type'] == 'anomaly_detection'
                                else 'Complete at least one annotation before publishing')
        number = db.execute('SELECT COALESCE(MAX(version_number),0)+1 FROM dataset_versions WHERE project_id=?',
                            (project_id,)).fetchone()[0]
        name = f'v{number}-{datetime.now(timezone.utc).strftime("%y%m%d")}-ready'
        author = request.state.user['username']
        snapshot = {'project': {key: project[key] for key in ('name', 'annotation_type', 'classes', 'description',
                    'labelling_instructions', 'ai_instructions', 'export_train_percent')},
                    'images': [image_json(row) | {'stored_name': row['stored_name'], 'digest': row['digest']} for row in rows]}
        freeze(snapshot)
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
    return dataset_service.version_detail(project_id, version_id)


_version_content = dataset_service._version_content


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
    username = request.state.user['username']
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
    with database() as db:
        commit_record = uuid.uuid4().hex
        db.execute('''INSERT INTO lakefs_commits
            (id,project_id,version_id,commit_id,repository,branch) VALUES (?,?,?,?,?,?)''',
            (commit_record, project_id, version_id, result.get('commit_id', ''),
             result['repository'], result['branch']))
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
