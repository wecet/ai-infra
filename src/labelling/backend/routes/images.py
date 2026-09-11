from fastapi import APIRouter
from common import *

router = APIRouter()

@router.get('/api/projects/{project_id}/images')
def images(project_id: str):
    with database() as db:
        get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY source_path,id', (project_id,))
        return [{k: item[k] for k in ('id', 'source_path', 'width', 'height', 'batch_id',
                                      'review_status', 'review_comment', 'reviewed_by', 'reviewed_at')} |
                {'completed': bool(item['completed']),
                 'annotation_count': len(json.loads(item['boxes'])) + len(json.loads(item['labels'])),
                 'category_ids': sorted(set(json.loads(item['labels'])) |
                                        {box['category_id'] for box in json.loads(item['boxes'])})}
                for item in rows]


@router.post('/api/projects/{project_id}/batches', status_code=201)
def create_batch(project_id: str, payload: BatchCreate):
    batch_id = uuid.uuid4().hex
    with database() as db:
        get_project(db, project_id)
        freeze_addition_batches(db, project_id)
        db.execute('INSERT INTO import_batches (id,project_id,kind) VALUES (?,?,?)',
                   (batch_id, project_id, payload.kind))
        return dict(db.execute('SELECT * FROM import_batches WHERE id=?', (batch_id,)).fetchone())


@router.get('/api/projects/{project_id}/history')
def project_history(project_id: str):
    with database() as db:
        get_project(db, project_id)
        rows = db.execute('''SELECT b.id,b.kind,b.created_at,b.details,
            COALESCE(b.sample_count,COUNT(i.id)) AS samples
            FROM import_batches b LEFT JOIN images i ON i.batch_id=b.id
            WHERE b.project_id=? GROUP BY b.id ORDER BY b.rowid''', (project_id,)).fetchall()
        total = 0
        history = []
        for number, row in enumerate(rows, 1):
            delta = -row['samples'] if row['kind'] == 'images_deleted' else row['samples']
            total += delta
            details = json.loads(row['details'])
            if row['kind'] == 'images_deleted':
                for item in details:
                    item['restorable'] = bool(item.get('snapshot') and
                        (DATA / 'deleted' / project_id / row['id'] / f"{item['id']}.png").is_file())
            history.append({key: row[key] for key in ('id', 'kind', 'created_at', 'samples')} |
                           {'version': number, 'sample_delta': delta, 'total_samples': total,
                            'details': details})
        return history


@router.get('/api/projects/{project_id}/batches/{batch_id}/images')
def batch_images(project_id: str, batch_id: str):
    with database() as db:
        get_project(db, project_id)
        if db.execute('SELECT 1 FROM import_batches WHERE id=? AND project_id=?',
                      (batch_id, project_id)).fetchone() is None:
            raise HTTPException(404, 'History entry not found')
        rows = db.execute('SELECT * FROM images WHERE project_id=? AND batch_id=? ORDER BY source_path,id',
                          (project_id, batch_id)).fetchall()
        return [{k: row[k] for k in ('id', 'source_path', 'width', 'height', 'batch_id',
                                     'review_status', 'review_comment', 'reviewed_by', 'reviewed_at')} |
                {'completed': bool(row['completed']),
                 'annotation_count': len(json.loads(row['boxes'])) + len(json.loads(row['labels'])),
                 'category_ids': sorted(set(json.loads(row['labels'])) |
                                        {box['category_id'] for box in json.loads(row['boxes'])})}
                for row in rows]


@router.post('/api/projects/{project_id}/images', status_code=201)
def upload_image(project_id: str, file: UploadFile = File(...), batch_id: str | None = None):
    with database() as db:
        get_project(db, project_id)
        if batch_id is None:
            batch = db.execute('SELECT id FROM import_batches WHERE project_id=? ORDER BY rowid LIMIT 1',
                               (project_id,)).fetchone()
            batch_id = batch['id']
        elif db.execute('SELECT 1 FROM import_batches WHERE id=? AND project_id=?',
                        (batch_id, project_id)).fetchone() is None:
            raise HTTPException(422, 'Unknown import batch')
    source_path = (file.filename or 'image').replace('\\', '/')
    path = PurePosixPath(source_path)
    if path.is_absolute() or '..' in path.parts or len(source_path) > 1000:
        raise HTTPException(422, 'Invalid image path')
    raw = file.file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, 'Each image must be at most 50 MiB')
    digest = hashlib.sha256(raw).hexdigest()
    with database() as db:
        existing = db.execute('SELECT * FROM images WHERE project_id=? AND source_path=?',
                              (project_id, source_path)).fetchone()
        if existing:
            if existing['digest'] != digest:
                raise HTTPException(409, f'{source_path} already exists with different contents')
            return image_json(existing)
    image_id = uuid.uuid4().hex
    directory = DATA / 'images' / project_id
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f'{image_id}.png'
    target = directory / stored_name
    try:
        import io
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as original:
                if original.format not in {'JPEG', 'PNG', 'WEBP', 'BMP', 'TIFF'}:
                    raise HTTPException(422, 'Supported formats: JPEG, PNG, WebP, BMP and TIFF')
                normalized = ImageOps.exif_transpose(original).convert('RGB')
                width, height = normalized.size
                image_hash = perceptual_hash(normalized)
                normalized.save(target, 'PNG')
        with database() as db:
            db.execute('''INSERT INTO images
                (id,project_id,source_path,stored_name,digest,width,height,batch_id,perceptual_hash)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (image_id, project_id, source_path, stored_name, digest, width, height, batch_id, image_hash))
            db.execute('''INSERT INTO annotation_revisions
                (image_id,revision,boxes,labels,completed) VALUES (?,0,'[]','[]',0)''', (image_id,))
            return image_json(get_image(db, project_id, image_id))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        target.unlink(missing_ok=True)
        raise HTTPException(422, 'Invalid image or image exceeds the 40 megapixel limit')
    except sqlite3.IntegrityError:
        target.unlink(missing_ok=True)
        raise HTTPException(409, 'Image was uploaded concurrently; retry the import')
    except Exception:
        target.unlink(missing_ok=True)
        raise


@router.get('/api/projects/{project_id}/images/{image_id}')
def image_detail(project_id: str, image_id: str):
    with database() as db:
        return image_json(get_image(db, project_id, image_id))


@router.get('/api/projects/{project_id}/images/{image_id}/file')
def image_file(project_id: str, image_id: str):
    with database() as db:
        row = get_image(db, project_id, image_id)
        return FileResponse(DATA / 'images' / project_id / row['stored_name'], media_type='image/png')


@router.delete('/api/projects/{project_id}/images/{image_id}')
def delete_image(project_id: str, image_id: str):
    deletion_id = uuid.uuid4().hex
    with database() as db:
        row = get_image(db, project_id, image_id)
        freeze_addition_batches(db, project_id)
        revisions = [dict(item) for item in db.execute(
            'SELECT revision,boxes,labels,completed,created_at FROM annotation_revisions WHERE image_id=?',
            (image_id,)).fetchall()]
        details = [{'id': row['id'], 'source_path': row['source_path'],
                    'width': row['width'], 'height': row['height'],
                    'completed': bool(row['completed']), 'snapshot': dict(row), 'revisions': revisions}]
        archive = DATA / 'deleted' / project_id / deletion_id
        archive.mkdir(parents=True, exist_ok=True)
        source = DATA / 'images' / project_id / row['stored_name']
        if not source.is_file():
            raise HTTPException(409, 'The stored image file is missing and cannot be archived')
        shutil.move(source, archive / f'{image_id}.png')
        db.execute('''INSERT INTO import_batches
            (id,project_id,kind,sample_count,details) VALUES (?,?,?,?,?)''',
            (deletion_id, project_id, 'images_deleted', 1, json.dumps(details)))
        db.execute('DELETE FROM annotation_revisions WHERE image_id=?', (image_id,))
        db.execute('DELETE FROM images WHERE id=? AND project_id=?', (image_id, project_id))
    return {'deleted': image_id}


def deleted_snapshot(db, project_id, batch_id, image_id):
    row = db.execute("SELECT details FROM import_batches WHERE id=? AND project_id=? AND kind='images_deleted'",
                     (batch_id, project_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Deletion history entry not found')
    item = next((item for item in json.loads(row['details']) if item.get('id') == image_id), None)
    if item is None or not item.get('snapshot'):
        raise HTTPException(404, 'This historic deletion cannot be restored')
    return item


@router.get('/api/projects/{project_id}/history/{batch_id}/deleted/{image_id}/file')
def deleted_image_file(project_id: str, batch_id: str, image_id: str):
    with database() as db:
        get_project(db, project_id)
        deleted_snapshot(db, project_id, batch_id, image_id)
    path = DATA / 'deleted' / project_id / batch_id / f'{image_id}.png'
    if not path.is_file():
        raise HTTPException(404, 'Deleted image archive is unavailable')
    return FileResponse(path, media_type='image/png')


@router.post('/api/projects/{project_id}/history/{batch_id}/deleted/{image_id}/restore')
def restore_image(project_id: str, batch_id: str, image_id: str):
    archived = DATA / 'deleted' / project_id / batch_id / f'{image_id}.png'
    with database() as db:
        get_project(db, project_id)
        item = deleted_snapshot(db, project_id, batch_id, image_id)
        snapshot = item['snapshot']
        if not archived.is_file():
            raise HTTPException(409, 'This image has already been restored or its archive is unavailable')
        if db.execute('SELECT 1 FROM images WHERE project_id=? AND source_path=?',
                      (project_id, snapshot['source_path'])).fetchone():
            raise HTTPException(409, 'An image with this source path already exists')
        restore_batch = uuid.uuid4().hex
        db.execute('''INSERT INTO import_batches (id,project_id,kind,sample_count,details)
            VALUES (?,?,?,1,?)''', (restore_batch, project_id, 'images_restored',
            json.dumps([{'id': image_id, 'source_path': snapshot['source_path']}])) )
        snapshot['batch_id'] = restore_batch
        columns = list(snapshot)
        db.execute(f"INSERT INTO images ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                   tuple(snapshot[column] for column in columns))
        for revision in item.get('revisions', []):
            db.execute('''INSERT INTO annotation_revisions
                (image_id,revision,boxes,labels,completed,created_at) VALUES (?,?,?,?,?,?)''',
                (image_id, revision['revision'], revision['boxes'], revision['labels'],
                 revision['completed'], revision['created_at']))
        destination = DATA / 'images' / project_id / snapshot['stored_name']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(archived, destination)
        return image_json(get_image(db, project_id, image_id))


@router.put('/api/projects/{project_id}/images/{image_id}')
def save_annotations(project_id: str, image_id: str, payload: AnnotationSave):
    with database() as db:
        project = get_project(db, project_id)
        row = get_image(db, project_id, image_id)
        categories = {c['id'] for c in project['classes']}
        classification = project['annotation_type'] == 'image_classification'
        if classification and payload.boxes:
            raise HTTPException(422, 'Classification projects use image classes, not bounding boxes')
        if not classification and payload.labels:
            raise HTTPException(422, 'Detection projects use bounding boxes')
        if len(set(payload.labels)) != len(payload.labels) or not set(payload.labels) <= categories:
            raise HTTPException(422, 'Unknown or duplicate image class')
        for box in payload.boxes:
            if box.category_id not in categories:
                raise HTTPException(422, 'Unknown class')
            if box.x + box.width > row['width'] + 0.001 or box.y + box.height > row['height'] + 0.001:
                raise HTTPException(422, 'Bounding box is outside the image')
        review_status = 'ready_for_review' if payload.completed else 'draft'
        result = db.execute('''UPDATE images SET boxes=?,labels=?,completed=?,revision=revision+1,
            review_status=?,review_comment='',reviewed_by='',reviewed_at=NULL
            WHERE id=? AND project_id=? AND revision=?''',
            (json.dumps([b.model_dump() for b in payload.boxes]), json.dumps(payload.labels), payload.completed,
             review_status,
             image_id, project_id, payload.revision))
        if result.rowcount != 1:
            raise HTTPException(409, 'This image changed in another tab. Reload before editing again.')
        saved = get_image(db, project_id, image_id)
        db.execute('''INSERT OR REPLACE INTO annotation_revisions
            (image_id,revision,boxes,labels,completed) VALUES (?,?,?,?,?)''',
            (image_id, saved['revision'], saved['boxes'], saved['labels'], saved['completed']))
        return image_json(saved)


@router.put('/api/projects/{project_id}/images/{image_id}/review')
def review_annotation(project_id: str, image_id: str, payload: ReviewDecision, request: Request):
    comment = payload.comment.strip()
    if payload.status == 'rejected' and not comment:
        raise HTTPException(422, 'Add a reason when rejecting an annotation')
    reviewer = (request.headers.get('x-forwarded-preferred-username') or
                request.headers.get('x-forwarded-user') or 'admin').strip()[:150] or 'admin'
    with database() as db:
        row = get_image(db, project_id, image_id)
        if not row['completed']:
            raise HTTPException(422, 'Complete the annotation before reviewing it')
        reviewed_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        db.execute('''UPDATE images SET review_status=?,review_comment=?,reviewed_by=?,reviewed_at=?
            WHERE id=? AND project_id=?''',
            (payload.status, comment, reviewer, reviewed_at, image_id, project_id))
        return image_json(get_image(db, project_id, image_id))


@router.put('/api/projects/{project_id}/review/bulk')
def bulk_review(project_id: str, payload: BulkReview, request: Request):
    image_ids = list(dict.fromkeys(payload.image_ids))
    reviewer = (request.headers.get('x-forwarded-preferred-username') or
                request.headers.get('x-forwarded-user') or 'admin').strip()[:150] or 'admin'
    with database() as db:
        get_project(db, project_id)
        placeholders = ','.join('?' for _ in image_ids)
        rows = db.execute(f'SELECT id,completed FROM images WHERE project_id=? AND id IN ({placeholders})',
                          (project_id, *image_ids)).fetchall()
        if len(rows) != len(image_ids):
            raise HTTPException(404, 'One or more selected images no longer exist')
        if any(not row['completed'] for row in rows):
            raise HTTPException(422, 'Only completed annotations can be approved')
        reviewed_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        db.execute(f'''UPDATE images SET review_status='approved',review_comment='',reviewed_by=?,reviewed_at=?
            WHERE project_id=? AND id IN ({placeholders})''',
                   (reviewer, reviewed_at, project_id, *image_ids))
        return {'updated': len(image_ids), 'image_ids': image_ids, 'reviewed_by': reviewer,
                'reviewed_at': reviewed_at}


@router.get('/api/projects/{project_id}/images/{image_id}/revisions')
def annotation_history(project_id: str, image_id: str):
    with database() as db:
        get_image(db, project_id, image_id)
        rows = db.execute('''SELECT revision,boxes,labels,completed,created_at
            FROM annotation_revisions WHERE image_id=? ORDER BY revision DESC''', (image_id,)).fetchall()
        return [dict(row) | {'boxes': json.loads(row['boxes']), 'labels': json.loads(row['labels']),
                            'completed': bool(row['completed'])} for row in rows]


ai_lock = Lock()


@router.post('/api/ai/validate')
def validate_ai():
    ai_labelling.validate_credentials()
    return {'valid': True}


class AISuggestRequest(BaseModel):
    revision: int = Field(ge=0)


@router.post('/api/projects/{project_id}/images/{image_id}/ai')
def suggest_annotations(project_id: str, image_id: str, payload: AISuggestRequest):
    if not ai_lock.acquire(blocking=False):
        raise HTTPException(409, 'AI assistance is busy. Try again shortly.')
    try:
        with database() as db:
            project = get_project(db, project_id)
            row = get_image(db, project_id, image_id)
            if project['annotation_type'] != 'object_detection':
                raise HTTPException(422, 'AI assistance is available for object detection projects only')
            if row['revision'] != payload.revision:
                raise HTTPException(409, 'This image changed. Reload before requesting AI assistance.')
            if row['revision'] or row['completed'] or json.loads(row['boxes']):
                raise HTTPException(409, 'AI assistance only runs on unannotated images')
            image_path = DATA / 'images' / project_id / row['stored_name']
        active_classes = [item for item in project['classes'] if not item.get('archived', False)]
        boxes = ai_labelling.detect(image_path, active_classes, row['width'], row['height'],
                                    project['ai_instructions'])
        # The ordinary save path validates classes, bounds, and the revision again.
        return save_annotations(project_id, image_id, AnnotationSave(
            boxes=boxes, completed=False, revision=payload.revision))
    finally:
        ai_lock.release()
