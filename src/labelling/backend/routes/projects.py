import auth
from fastapi import APIRouter
from common import (
    ClassCreate, ClassMerge, ClassUpdate, CommentCreate, DATA, File, Form, HTTPException, MAX_UPLOAD, ProjectCreate, ProjectMerge, ProjectOrder, ProjectUpdate, PurePosixPath, Request, UploadFile, _safe_zip_members, database, freeze_addition_batches, get_project, io, json, re, shutil, uuid, zipfile
)
from common import _safe_zip_members
from routes.datasets import import_annotations

router = APIRouter()


from services.import_validation import _validate_import_document

@router.get('/api/projects')
def projects(request: Request):
    access = auth.permission_map(request.state.user)
    with database() as db:
        rows = db.execute('''SELECT p.id, p.name, p.annotation_type, p.created_at, p.sort_order, COUNT(i.id) AS total,
            COALESCE(SUM(i.completed), 0) AS completed FROM projects p
            LEFT JOIN images i ON i.project_id=p.id GROUP BY p.id ORDER BY p.sort_order, p.created_at, p.id''')
        return [dict(row) | access[row["id"]] for row in rows if row["id"] in access]


@router.put('/api/projects/order')
def reorder_projects(payload: ProjectOrder, request: Request):
    if len(payload.project_ids) != len(set(payload.project_ids)):
        raise HTTPException(422, 'Project order contains duplicate IDs')
    with database() as db:
        existing = {row['id'] for row in db.execute('SELECT id FROM projects')} & auth.permission_map(request.state.user).keys()
        if set(payload.project_ids) != existing:
            raise HTTPException(409, 'Project list changed. Refresh before reordering.')
        for position, project_id in enumerate(payload.project_ids):
            db.execute('UPDATE projects SET sort_order=? WHERE id=?', (position, project_id))
    return {'project_ids': payload.project_ids}


@router.post('/api/projects', status_code=201)
def create_project(payload: ProjectCreate, request: Request):
    name = payload.name.strip()
    classes = [c.strip() for c in payload.classes]
    if payload.annotation_type == 'anomaly_detection' and classes:
        raise HTTPException(422, 'Unsupervised anomaly datasets do not use classes')
    if not name or (payload.annotation_type != 'anomaly_detection' and not classes) or any(not c or len(c) > 100 for c in classes):
        raise HTTPException(422, 'Enter a project name and class names of 1–100 characters')
    if len({c.casefold() for c in classes}) != len(classes):
        raise HTTPException(422, 'Class names must be unique')
    categories = [{'id': i + 1, 'name': name} for i, name in enumerate(classes)]
    project_id = uuid.uuid4().hex
    with database() as db:
        sort_order = db.execute('SELECT COALESCE(MAX(sort_order),-1)+1 FROM projects').fetchone()[0]
        db.execute('INSERT INTO projects (id,name,classes,annotation_type,sort_order) VALUES (?,?,?,?,?)',
                   (project_id, name, json.dumps(categories), payload.annotation_type, sort_order))
        db.execute('INSERT INTO import_batches (id,project_id,kind) VALUES (?,?,?)',
                   (uuid.uuid4().hex, project_id, 'project_created'))
        auth.repository_created(project_id, request.state.user)
        return get_project(db, project_id) | auth.require_repository(request.state.user, project_id)


@router.post('/api/projects/import', status_code=201)
def import_project(request: Request, name: str = Form(...), file: UploadFile = File(...)):
    if not (file.filename or '').lower().endswith('.zip'):
        raise HTTPException(422, 'Import Project requires a ZIP file')
    raw = file.file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, 'Project ZIP must be at most 50 MiB')
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        members = _safe_zip_members(archive)
        names = archive.namelist()
        annotation_members = [item for item in members
                              if item.filename.startswith('annotations/') and item.filename.lower().endswith('.json')]
        image_members = [item for item in members if item.filename.startswith('images/') and
                         PurePosixPath(item.filename).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}]
        if not annotation_members or not any(name == 'images/' or name.startswith('images/') for name in names):
            raise HTTPException(422, 'ZIP must contain annotations/*.json and images/*')
        named_documents = [(item.filename, json.loads(archive.read(item))) for item in annotation_members]
    except HTTPException:
        raise
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(422, 'Invalid project ZIP or annotation JSON') from exc
    documents = [item for _, item in named_documents]
    inferred_types = {_validate_import_document(document, filename)
                      for filename, document in named_documents}
    if len(inferred_types) != 1:
        raise HTTPException(422, 'All annotation JSON files must describe the same annotation type')
    first = documents[0]
    classes = [item.get('name', '').strip() for item in first['categories']]
    if any(not item for item in classes):
        raise HTTPException(422, 'Every imported category must have a name')
    class_names = {item.casefold() for item in classes}
    for document in documents[1:]:
        if {item.get('name', '').strip().casefold() for item in document['categories']} != class_names:
            raise HTTPException(422, 'All annotation JSON files must define the same classes')
    annotation_type = inferred_types.pop()
    project_name = name.strip()
    if not project_name or len(project_name) > 150:
        raise HTTPException(422, 'Enter a project name of 1–150 characters')
    created = create_project(ProjectCreate(name=project_name, classes=classes, annotation_type=annotation_type), request)
    if not image_members and all(not document.get('images') for document in documents):
        return {'project': created, 'updated': 0, 'images_imported': 0, 'unmatched': []}
    try:
        result = import_annotations(created['id'], UploadFile(filename=file.filename, file=io.BytesIO(raw)))
    except Exception:
        delete_project(created['id'])
        raise
    return {'project': created, **result}


@router.get('/api/projects/{project_id}')
def project(project_id: str, request: Request):
    with database() as db:
        return get_project(db, project_id) | auth.require_repository(request.state.user, project_id)


@router.put('/api/projects/{project_id}')
def update_project(project_id: str, payload: ProjectUpdate, request: Request):
    values = [payload.name.strip(), payload.description.strip(), payload.labelling_instructions.strip(),
              payload.ai_instructions.strip(), payload.export_train_percent]
    if not values[0]:
        raise HTTPException(422, 'Project name cannot be empty')
    with database() as db:
        get_project(db, project_id)
        db.execute('''UPDATE projects SET name=?,description=?,labelling_instructions=?,ai_instructions=?,
            export_train_percent=? WHERE id=?''', (*values, project_id))
        return get_project(db, project_id) | auth.require_repository(request.state.user, project_id)


def validate_class_name(classes, name, exclude_id=None):
    value = name.strip()
    if not value or any(item['id'] != exclude_id and item['name'].casefold() == value.casefold()
                        for item in classes):
        raise HTTPException(422, 'Class names must be non-empty and unique')
    return value


@router.post('/api/projects/{project_id}/classes', status_code=201)
def add_class(project_id: str, payload: ClassCreate):
    with database() as db:
        project = get_project(db, project_id)
        if project['annotation_type'] == 'anomaly_detection':
            raise HTTPException(422, 'Unsupervised anomaly datasets do not use classes')
        name = validate_class_name(project['classes'], payload.name)
        category_id = max((item['id'] for item in project['classes']), default=0) + 1
        classes = project['classes'] + [{'id': category_id, 'name': name,
                                         'color': payload.color.lower(), 'archived': False}]
        db.execute('UPDATE projects SET classes=? WHERE id=?', (json.dumps(classes), project_id))
        return get_project(db, project_id)


@router.put('/api/projects/{project_id}/classes/{category_id}')
def update_class(project_id: str, category_id: int, payload: ClassUpdate):
    with database() as db:
        project = get_project(db, project_id)
        category = next((item for item in project['classes'] if item['id'] == category_id), None)
        if category is None:
            raise HTTPException(404, 'Class not found')
        name = validate_class_name(project['classes'], payload.name, category_id)
        if payload.archived and sum(not item.get('archived', False) and item['id'] != category_id
                                    for item in project['classes']) == 0:
            raise HTTPException(422, 'A project must retain at least one active class')
        category.update(name=name, color=payload.color.lower(), archived=payload.archived)
        db.execute('UPDATE projects SET classes=? WHERE id=?', (json.dumps(project['classes']), project_id))
        return get_project(db, project_id)


@router.post('/api/projects/{project_id}/classes/{category_id}/merge')
def merge_class(project_id: str, category_id: int, payload: ClassMerge):
    if category_id == payload.target_category_id:
        raise HTTPException(422, 'Choose a different destination class')
    with database() as db:
        project = get_project(db, project_id)
        ids = {item['id'] for item in project['classes']}
        if category_id not in ids or payload.target_category_id not in ids:
            raise HTTPException(404, 'Class not found')
        for table, key in (('images', 'id'), ('annotation_revisions', 'id')):
            rows = db.execute(f'''SELECT {key},boxes,labels FROM {table} WHERE ''' +
                              ('project_id=?' if table == 'images' else
                               'image_id IN (SELECT id FROM images WHERE project_id=?)'), (project_id,)).fetchall()
            for row in rows:
                boxes = json.loads(row['boxes'])
                for box in boxes:
                    if box['category_id'] == category_id:
                        box['category_id'] = payload.target_category_id
                labels = list(dict.fromkeys(payload.target_category_id if item == category_id else item
                                            for item in json.loads(row['labels'])))
                db.execute(f'UPDATE {table} SET boxes=?,labels=? WHERE {key}=?',
                           (json.dumps(boxes), json.dumps(labels), row[key]))
        classes = [item for item in project['classes'] if item['id'] != category_id]
        db.execute('UPDATE projects SET classes=? WHERE id=?', (json.dumps(classes), project_id))
        return get_project(db, project_id)


@router.post('/api/projects/{project_id}/merge')
def merge_project(project_id: str, payload: ProjectMerge, request: Request):
    auth.require_repository(request.state.user, payload.source_project_id, "owner")
    source_id = payload.source_project_id
    if source_id == project_id:
        raise HTTPException(422, 'A project cannot be merged into itself')
    moved_files = []
    with database() as db:
        root = get_project(db, project_id)
        source = get_project(db, source_id)
        if root['annotation_type'] != source['annotation_type']:
            raise HTTPException(422, 'Image Classification and Object Detection projects cannot be merged')
        root_classes = list(root['classes'])
        root_by_name = {item['name'].casefold(): item['id'] for item in root_classes}
        class_map = {}
        for category in source['classes']:
            key = category['name'].casefold()
            if key not in root_by_name:
                next_id = max((item['id'] for item in root_classes), default=0) + 1
                root_classes.append({'id': next_id, 'name': category['name']})
                root_by_name[key] = next_id
            class_map[category['id']] = root_by_name[key]
        source_rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY id', (source_id,)).fetchall()
        existing_paths = {row['source_path'] for row in db.execute(
            'SELECT source_path FROM images WHERE project_id=?', (project_id,)).fetchall()}
        planned = []
        prefix = re.sub(r'[^A-Za-z0-9._-]+', '_', source['name']).strip('._-') or 'merged-project'
        for row in source_rows:
            source_path = row['source_path']
            if source_path in existing_paths:
                source_path = f'{prefix}/{source_path}'
                suffix = 2
                candidate = source_path
                while candidate in existing_paths:
                    candidate = f'{prefix}-{suffix}/{row["source_path"]}'
                    suffix += 1
                source_path = candidate
            existing_paths.add(source_path)
            planned.append((row, source_path))
        root_directory = DATA / 'images' / project_id
        root_directory.mkdir(parents=True, exist_ok=True)
        try:
            for row, _ in planned:
                old_path = DATA / 'images' / source_id / row['stored_name']
                new_path = root_directory / row['stored_name']
                if not old_path.is_file():
                    raise HTTPException(409, f'Missing stored image: {row["source_path"]}')
                if new_path.exists():
                    raise HTTPException(409, 'A stored image identifier conflicts with the root project')
                shutil.move(old_path, new_path)
                moved_files.append((new_path, old_path))
            freeze_addition_batches(db, project_id)
            merge_batch = uuid.uuid4().hex
            details = [{'source_project_id': source_id, 'source_project_name': source['name'],
                        'images': len(source_rows), 'classes_added': len(root_classes) - len(root['classes'])}]
            db.execute('''INSERT INTO import_batches (id,project_id,kind,sample_count,details)
                VALUES (?,?,?,?,?)''', (merge_batch, project_id, 'projects_merged', len(source_rows), json.dumps(details)))
            for row, source_path in planned:
                boxes = json.loads(row['boxes'])
                for box in boxes:
                    box['category_id'] = class_map[box['category_id']]
                labels = [class_map[item] for item in json.loads(row['labels'])]
                db.execute('''UPDATE images SET project_id=?,source_path=?,batch_id=?,boxes=?,labels=? WHERE id=?''',
                           (project_id, source_path, merge_batch, json.dumps(boxes), json.dumps(labels), row['id']))
                revisions = db.execute('SELECT id,boxes,labels FROM annotation_revisions WHERE image_id=?',
                                       (row['id'],)).fetchall()
                for revision in revisions:
                    revision_boxes = json.loads(revision['boxes'])
                    for box in revision_boxes:
                        box['category_id'] = class_map[box['category_id']]
                    revision_labels = [class_map[item] for item in json.loads(revision['labels'])]
                    db.execute('UPDATE annotation_revisions SET boxes=?,labels=? WHERE id=?',
                               (json.dumps(revision_boxes), json.dumps(revision_labels), revision['id']))
            db.execute('UPDATE project_comments SET project_id=? WHERE project_id=?', (project_id, source_id))
            db.execute('DELETE FROM model_deployments WHERE project_id=?', (source_id,))
            db.execute('DELETE FROM review_tasks WHERE project_id=?', (source_id,))
            db.execute('DELETE FROM model_evaluations WHERE project_id=?', (source_id,))
            db.execute('DELETE FROM registered_models WHERE project_id=?', (source_id,))
            db.execute('DELETE FROM training_jobs WHERE project_id=?', (source_id,))
            db.execute('DELETE FROM lakefs_commits WHERE project_id=?', (source_id,))
            db.execute('DELETE FROM dataset_versions WHERE project_id=?', (source_id,))
            db.execute('DELETE FROM import_batches WHERE project_id=?', (source_id,))
            db.execute('UPDATE projects SET classes=? WHERE id=?', (json.dumps(root_classes), project_id))
            db.execute('DELETE FROM projects WHERE id=?', (source_id,))
        except Exception:
            for new_path, old_path in reversed(moved_files):
                old_path.parent.mkdir(parents=True, exist_ok=True)
                if new_path.exists():
                    shutil.move(new_path, old_path)
            raise
    auth.repository_deleted(source_id)
    shutil.rmtree(DATA / 'images' / source_id, ignore_errors=True)
    shutil.rmtree(DATA / 'deleted' / source_id, ignore_errors=True)
    shutil.rmtree(DATA / 'versions' / source_id, ignore_errors=True)
    with database() as db:
        return get_project(db, project_id) | {'images_merged': len(moved_files),
                                              'classes_added': len(root_classes) - len(root['classes'])}


@router.delete('/api/projects/{project_id}')
def delete_project(project_id: str):
    with database() as db:
        get_project(db, project_id)
        if db.execute("SELECT 1 FROM training_jobs WHERE project_id=? AND status IN ('queued','running','cancelling')", (project_id,)).fetchone() or db.execute("SELECT 1 FROM model_evaluations WHERE project_id=? AND status IN ('queued','running')", (project_id,)).fetchone():
            raise HTTPException(409, 'Stop active training and evaluation before deleting this project')
        db.execute('DELETE FROM annotation_revisions WHERE image_id IN (SELECT id FROM images WHERE project_id=?)',
                   (project_id,))
        db.execute('DELETE FROM project_comments WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM model_deployments WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM review_tasks WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM model_evaluations WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM registered_models WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM training_jobs WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM lakefs_commits WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM dataset_versions WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM images WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM import_batches WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM projects WHERE id=?', (project_id,))
    auth.repository_deleted(project_id)
    shutil.rmtree(DATA / 'images' / project_id, ignore_errors=True)
    shutil.rmtree(DATA / 'deleted' / project_id, ignore_errors=True)
    shutil.rmtree(DATA / 'versions' / project_id, ignore_errors=True)
    return {'deleted': project_id}


@router.get('/api/projects/{project_id}/comments')
def project_comments(project_id: str):
    with database() as db:
        get_project(db, project_id)
        return [dict(row) for row in db.execute('''SELECT id,author,body,created_at
            FROM project_comments WHERE project_id=? ORDER BY created_at DESC,rowid DESC''', (project_id,))]


@router.post('/api/projects/{project_id}/comments', status_code=201)
def add_project_comment(project_id: str, payload: CommentCreate, request: Request):
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, 'Comment cannot be empty')
    author = request.state.user['username']
    comment_id = uuid.uuid4().hex
    with database() as db:
        get_project(db, project_id)
        db.execute('INSERT INTO project_comments (id,project_id,author,body) VALUES (?,?,?,?)',
                   (comment_id, project_id, author, body))
        return dict(db.execute('SELECT id,author,body,created_at FROM project_comments WHERE id=?',
                               (comment_id,)).fetchone())


@router.get('/api/projects/{project_id}/activity')
def project_activity(project_id: str, before: int | None = None):
    with database() as db:
        get_project(db, project_id)
        return [dict(row) for row in db.execute('SELECT * FROM project_activity WHERE project_id=? AND id<? ORDER BY id DESC LIMIT 100', (project_id, before if before is not None else 2**63-1))]
