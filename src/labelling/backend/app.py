"""Persistent image annotation API and production React host."""
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import random
import re
import shutil
import sqlite3
import tempfile
import uuid
import warnings
import zipfile
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Literal
from threading import Lock

import ai_labelling

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError
from starlette.background import BackgroundTask

DATA = Path(os.environ.get('LABELLING_DATA_DIR', '/data'))
MAX_UPLOAD = 50 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000
@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title='Labelling API', lifespan=lifespan)


@contextmanager
def database():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATA / 'labelling.sqlite3', timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        with con:
            yield con
    finally:
        con.close()


def init_db():
    with database() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, classes TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS images (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            source_path TEXT NOT NULL, stored_name TEXT NOT NULL, digest TEXT NOT NULL,
            width INTEGER NOT NULL, height INTEGER NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0,
            boxes TEXT NOT NULL DEFAULT '[]', UNIQUE(project_id, source_path));
        CREATE TABLE IF NOT EXISTS import_batches (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            kind TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sample_count INTEGER, details TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS annotation_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id TEXT NOT NULL REFERENCES images(id), revision INTEGER NOT NULL,
            boxes TEXT NOT NULL, labels TEXT NOT NULL, completed INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(image_id, revision));
        CREATE TABLE IF NOT EXISTS project_comments (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            author TEXT NOT NULL, body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        ''')
        # Additive migrations preserve annotations from existing deployments.
        if 'annotation_type' not in {r['name'] for r in db.execute('PRAGMA table_info(projects)')}:
            db.execute("ALTER TABLE projects ADD COLUMN annotation_type TEXT NOT NULL DEFAULT 'object_detection'")
        project_columns = {r['name'] for r in db.execute('PRAGMA table_info(projects)')}
        for column, definition in (
            ('description', "TEXT NOT NULL DEFAULT ''"),
            ('labelling_instructions', "TEXT NOT NULL DEFAULT ''"),
            ('ai_instructions', "TEXT NOT NULL DEFAULT ''"),
            ('export_train_percent', 'INTEGER NOT NULL DEFAULT 80'),
        ):
            if column not in project_columns:
                db.execute(f'ALTER TABLE projects ADD COLUMN {column} {definition}')
        if 'sort_order' not in project_columns:
            db.execute('ALTER TABLE projects ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0')
            for position, project in enumerate(db.execute('SELECT id FROM projects ORDER BY created_at,rowid')):
                db.execute('UPDATE projects SET sort_order=? WHERE id=?', (position, project['id']))
        if 'labels' not in {r['name'] for r in db.execute('PRAGMA table_info(images)')}:
            db.execute("ALTER TABLE images ADD COLUMN labels TEXT NOT NULL DEFAULT '[]'")
        image_columns = {r['name'] for r in db.execute('PRAGMA table_info(images)')}
        had_review_status = 'review_status' in image_columns
        if 'batch_id' not in image_columns:
            db.execute('ALTER TABLE images ADD COLUMN batch_id TEXT')
        if 'perceptual_hash' not in image_columns:
            db.execute("ALTER TABLE images ADD COLUMN perceptual_hash TEXT NOT NULL DEFAULT ''")
        for column, definition in (
            ('review_status', "TEXT NOT NULL DEFAULT 'draft'"),
            ('review_comment', "TEXT NOT NULL DEFAULT ''"),
            ('reviewed_by', "TEXT NOT NULL DEFAULT ''"),
            ('reviewed_at', 'TEXT'),
        ):
            if column not in image_columns:
                db.execute(f'ALTER TABLE images ADD COLUMN {column} {definition}')
        if not had_review_status:
            db.execute("UPDATE images SET review_status='ready_for_review' WHERE completed=1")
        batch_columns = {r['name'] for r in db.execute('PRAGMA table_info(import_batches)')}
        if 'sample_count' not in batch_columns:
            db.execute('ALTER TABLE import_batches ADD COLUMN sample_count INTEGER')
        if 'details' not in batch_columns:
            db.execute("ALTER TABLE import_batches ADD COLUMN details TEXT NOT NULL DEFAULT '[]'")
        db.execute('CREATE INDEX IF NOT EXISTS idx_images_project_batch ON images(project_id,batch_id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_revisions_image ON annotation_revisions(image_id,revision)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_batches_project ON import_batches(project_id)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_comments_project ON project_comments(project_id,created_at)')
        # Existing deployments become version 1 without altering any image data.
        for project in db.execute('SELECT id,created_at FROM projects').fetchall():
            batch = db.execute('SELECT id FROM import_batches WHERE project_id=? ORDER BY rowid LIMIT 1',
                               (project['id'],)).fetchone()
            if batch is None:
                batch_id = uuid.uuid4().hex
                db.execute('INSERT INTO import_batches (id,project_id,kind,created_at) VALUES (?,?,?,?)',
                           (batch_id, project['id'], 'project_created', project['created_at']))
            else:
                batch_id = batch['id']
            db.execute('UPDATE images SET batch_id=? WHERE project_id=? AND batch_id IS NULL',
                       (batch_id, project['id']))


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    classes: list[str] = Field(min_length=1)
    annotation_type: Literal['object_detection', 'image_classification'] = 'object_detection'


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default='', max_length=2000)
    labelling_instructions: str = Field(default='', max_length=4000)
    ai_instructions: str = Field(default='', max_length=4000)
    export_train_percent: int = Field(default=80, ge=0, le=100)


class ProjectMerge(BaseModel):
    source_project_id: str = Field(min_length=1, max_length=64)


class ProjectOrder(BaseModel):
    project_ids: list[str] = Field(min_length=1)


class Box(BaseModel):
    category_id: int = Field(ge=1)
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)
    width: float = Field(gt=0, allow_inf_nan=False)
    height: float = Field(gt=0, allow_inf_nan=False)


class AnnotationSave(BaseModel):
    boxes: list[Box]
    labels: list[int] = Field(default_factory=list)
    completed: bool
    revision: int = Field(ge=0)


class ExportRequest(BaseModel):
    train_percent: int = Field(ge=0, le=100)
    description: str = Field(default='', max_length=1000)
    split: Literal['train', 'test']


class BatchCreate(BaseModel):
    kind: Literal['new_additions'] = 'new_additions'


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ReviewDecision(BaseModel):
    status: Literal['ready_for_review', 'approved', 'rejected']
    comment: str = Field(default='', max_length=2000)


def perceptual_hash(image):
    """Return a compact 64-bit difference hash for near-duplicate grouping."""
    gray = image.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(gray.get_flattened_data())
    bits = [pixels[y * 9 + x] > pixels[y * 9 + x + 1] for y in range(8) for x in range(8)]
    return f'{sum(1 << i for i, bit in enumerate(bits) if bit):016x}'


def hamming(left, right):
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _safe_zip_members(archive):
    members = [item for item in archive.infolist() if not item.is_dir()]
    if len(members) > 20_000 or sum(item.file_size for item in members) > 2 * 1024 * 1024 * 1024:
        raise HTTPException(413, 'Expanded dataset must be at most 2 GiB and 20,000 files')
    if any(PurePosixPath(item.filename).is_absolute() or '..' in PurePosixPath(item.filename).parts
           for item in members):
        raise HTTPException(422, 'Dataset ZIP contains an unsafe path')
    return members


def get_project(db, project_id):
    row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Project not found')
    return dict(row) | {'classes': json.loads(row['classes'])}


def get_image(db, project_id, image_id):
    row = db.execute('SELECT * FROM images WHERE id=? AND project_id=?', (image_id, project_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Image not found')
    return row


def freeze_addition_batches(db, project_id):
    db.execute('''UPDATE import_batches SET sample_count=(
        SELECT COUNT(*) FROM images WHERE images.batch_id=import_batches.id)
        WHERE project_id=? AND kind IN ('project_created','new_additions') AND sample_count IS NULL''',
        (project_id,))


def image_json(row):
    return {key: row[key] for key in ('id', 'source_path', 'width', 'height', 'revision',
                                      'review_status', 'review_comment', 'reviewed_by', 'reviewed_at')} | {
        'completed': bool(row['completed']), 'boxes': json.loads(row['boxes']),
        'labels': json.loads(row['labels'])}


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/projects')
def projects():
    with database() as db:
        rows = db.execute('''SELECT p.id, p.name, p.annotation_type, p.created_at, p.sort_order, COUNT(i.id) AS total,
            COALESCE(SUM(i.completed), 0) AS completed FROM projects p
            LEFT JOIN images i ON i.project_id=p.id GROUP BY p.id ORDER BY p.sort_order, p.created_at, p.id''')
        return [dict(row) for row in rows]


@app.put('/api/projects/order')
def reorder_projects(payload: ProjectOrder):
    if len(payload.project_ids) != len(set(payload.project_ids)):
        raise HTTPException(422, 'Project order contains duplicate IDs')
    with database() as db:
        existing = {row['id'] for row in db.execute('SELECT id FROM projects')}
        if set(payload.project_ids) != existing:
            raise HTTPException(409, 'Project list changed. Refresh before reordering.')
        for position, project_id in enumerate(payload.project_ids):
            db.execute('UPDATE projects SET sort_order=? WHERE id=?', (position, project_id))
    return {'project_ids': payload.project_ids}


@app.post('/api/projects', status_code=201)
def create_project(payload: ProjectCreate):
    name = payload.name.strip()
    classes = [c.strip() for c in payload.classes]
    if not name or any(not c or len(c) > 100 for c in classes):
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
        return get_project(db, project_id)


@app.post('/api/projects/import', status_code=201)
def import_project(name: str = Form(...), file: UploadFile = File(...)):
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
        documents = [json.loads(archive.read(item)) for item in annotation_members]
    except HTTPException:
        raise
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(422, 'Invalid project ZIP or annotation JSON') from exc
    documents = [item for item in documents if isinstance(item, dict) and item.get('categories')]
    if not documents:
        raise HTTPException(422, 'Annotation JSON must contain a categories list')
    first = documents[0]
    classes = [item.get('name', '').strip() for item in first['categories']]
    if any(not item for item in classes):
        raise HTTPException(422, 'Every imported category must have a name')
    class_names = {item.casefold() for item in classes}
    for document in documents[1:]:
        if {item.get('name', '').strip().casefold() for item in document['categories']} != class_names:
            raise HTTPException(422, 'All annotation JSON files must define the same classes')
    types = {item.get('info', {}).get('annotation_type', 'object_detection') for item in documents}
    if not types <= {'object_detection', 'image_classification'} or len(types) != 1:
        raise HTTPException(422, 'All annotation JSON files must use the same supported annotation type')
    project_name = name.strip()
    if not project_name or len(project_name) > 150:
        raise HTTPException(422, 'Enter a project name of 1–150 characters')
    created = create_project(ProjectCreate(name=project_name, classes=classes, annotation_type=types.pop()))
    if not image_members and all(not document.get('images') for document in documents):
        return {'project': created, 'updated': 0, 'images_imported': 0, 'unmatched': []}
    try:
        result = import_annotations(created['id'], UploadFile(filename=file.filename, file=io.BytesIO(raw)))
    except Exception:
        delete_project(created['id'])
        raise
    return {'project': created, **result}


@app.get('/api/projects/{project_id}')
def project(project_id: str):
    with database() as db:
        return get_project(db, project_id)


@app.put('/api/projects/{project_id}')
def update_project(project_id: str, payload: ProjectUpdate):
    values = [payload.name.strip(), payload.description.strip(), payload.labelling_instructions.strip(),
              payload.ai_instructions.strip(), payload.export_train_percent]
    if not values[0]:
        raise HTTPException(422, 'Project name cannot be empty')
    with database() as db:
        get_project(db, project_id)
        db.execute('''UPDATE projects SET name=?,description=?,labelling_instructions=?,ai_instructions=?,
            export_train_percent=? WHERE id=?''', (*values, project_id))
        return get_project(db, project_id)


@app.post('/api/projects/{project_id}/merge')
def merge_project(project_id: str, payload: ProjectMerge):
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
            db.execute('DELETE FROM import_batches WHERE project_id=?', (source_id,))
            db.execute('UPDATE projects SET classes=? WHERE id=?', (json.dumps(root_classes), project_id))
            db.execute('DELETE FROM projects WHERE id=?', (source_id,))
        except Exception:
            for new_path, old_path in reversed(moved_files):
                old_path.parent.mkdir(parents=True, exist_ok=True)
                if new_path.exists():
                    shutil.move(new_path, old_path)
            raise
    shutil.rmtree(DATA / 'images' / source_id, ignore_errors=True)
    shutil.rmtree(DATA / 'deleted' / source_id, ignore_errors=True)
    with database() as db:
        return get_project(db, project_id) | {'images_merged': len(moved_files),
                                              'classes_added': len(root_classes) - len(root['classes'])}


@app.delete('/api/projects/{project_id}')
def delete_project(project_id: str):
    with database() as db:
        get_project(db, project_id)
        db.execute('DELETE FROM annotation_revisions WHERE image_id IN (SELECT id FROM images WHERE project_id=?)',
                   (project_id,))
        db.execute('DELETE FROM project_comments WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM images WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM import_batches WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM projects WHERE id=?', (project_id,))
    shutil.rmtree(DATA / 'images' / project_id, ignore_errors=True)
    shutil.rmtree(DATA / 'deleted' / project_id, ignore_errors=True)
    return {'deleted': project_id}


@app.get('/api/projects/{project_id}/comments')
def project_comments(project_id: str):
    with database() as db:
        get_project(db, project_id)
        return [dict(row) for row in db.execute('''SELECT id,author,body,created_at
            FROM project_comments WHERE project_id=? ORDER BY created_at DESC,rowid DESC''', (project_id,))]


@app.post('/api/projects/{project_id}/comments', status_code=201)
def add_project_comment(project_id: str, payload: CommentCreate, request: Request):
    body = payload.body.strip()
    if not body:
        raise HTTPException(422, 'Comment cannot be empty')
    author = (request.headers.get('x-forwarded-preferred-username') or
              request.headers.get('x-forwarded-user') or 'admin').strip()[:150] or 'admin'
    comment_id = uuid.uuid4().hex
    with database() as db:
        get_project(db, project_id)
        db.execute('INSERT INTO project_comments (id,project_id,author,body) VALUES (?,?,?,?)',
                   (comment_id, project_id, author, body))
        return dict(db.execute('SELECT id,author,body,created_at FROM project_comments WHERE id=?',
                               (comment_id,)).fetchone())


@app.get('/api/projects/{project_id}/images')
def images(project_id: str):
    with database() as db:
        get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY source_path,id', (project_id,))
        return [{k: item[k] for k in ('id', 'source_path', 'width', 'height', 'batch_id',
                                      'review_status', 'review_comment', 'reviewed_by', 'reviewed_at')} |
                {'completed': bool(item['completed'])} for item in rows]


@app.post('/api/projects/{project_id}/batches', status_code=201)
def create_batch(project_id: str, payload: BatchCreate):
    batch_id = uuid.uuid4().hex
    with database() as db:
        get_project(db, project_id)
        freeze_addition_batches(db, project_id)
        db.execute('INSERT INTO import_batches (id,project_id,kind) VALUES (?,?,?)',
                   (batch_id, project_id, payload.kind))
        return dict(db.execute('SELECT * FROM import_batches WHERE id=?', (batch_id,)).fetchone())


@app.get('/api/projects/{project_id}/history')
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


@app.get('/api/projects/{project_id}/batches/{batch_id}/images')
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
                {'completed': bool(row['completed'])} for row in rows]


@app.post('/api/projects/{project_id}/images', status_code=201)
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


@app.get('/api/projects/{project_id}/images/{image_id}')
def image_detail(project_id: str, image_id: str):
    with database() as db:
        return image_json(get_image(db, project_id, image_id))


@app.get('/api/projects/{project_id}/images/{image_id}/file')
def image_file(project_id: str, image_id: str):
    with database() as db:
        row = get_image(db, project_id, image_id)
        return FileResponse(DATA / 'images' / project_id / row['stored_name'], media_type='image/png')


@app.delete('/api/projects/{project_id}/images/{image_id}')
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


@app.get('/api/projects/{project_id}/history/{batch_id}/deleted/{image_id}/file')
def deleted_image_file(project_id: str, batch_id: str, image_id: str):
    with database() as db:
        get_project(db, project_id)
        deleted_snapshot(db, project_id, batch_id, image_id)
    path = DATA / 'deleted' / project_id / batch_id / f'{image_id}.png'
    if not path.is_file():
        raise HTTPException(404, 'Deleted image archive is unavailable')
    return FileResponse(path, media_type='image/png')


@app.post('/api/projects/{project_id}/history/{batch_id}/deleted/{image_id}/restore')
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


@app.put('/api/projects/{project_id}/images/{image_id}')
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


@app.put('/api/projects/{project_id}/images/{image_id}/review')
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


@app.get('/api/projects/{project_id}/images/{image_id}/revisions')
def annotation_history(project_id: str, image_id: str):
    with database() as db:
        get_image(db, project_id, image_id)
        rows = db.execute('''SELECT revision,boxes,labels,completed,created_at
            FROM annotation_revisions WHERE image_id=? ORDER BY revision DESC''', (image_id,)).fetchall()
        return [dict(row) | {'boxes': json.loads(row['boxes']), 'labels': json.loads(row['labels']),
                            'completed': bool(row['completed'])} for row in rows]


def _match_image(rows, filename):
    normalized = filename.replace('\\', '/').lstrip('./')
    candidates = [normalized]
    for prefix in ('train/images/', 'test/images/', 'valid/images/', 'images/'):
        if normalized.startswith(prefix):
            candidates.append(normalized[len(prefix):])
    exact = [row for row in rows if row['source_path'] in candidates or row['stored_name'] in candidates]
    if len(exact) == 1:
        return exact[0]
    basename = PurePosixPath(normalized).name
    matches = [row for row in rows if PurePosixPath(row['source_path']).name == basename]
    if len(matches) == 1:
        return matches[0]
    suffix_matches = [row for row in rows if row['source_path'].endswith(f'/{normalized}')]
    return suffix_matches[0] if len(suffix_matches) == 1 else None


@app.post('/api/projects/{project_id}/annotations/import')
def import_annotations(project_id: str, file: UploadFile = File(...)):
    raw = file.file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, 'Annotation import must be at most 50 MiB')
    archive = None
    documents = []
    yolo_files = []
    images_imported = 0
    try:
        if (file.filename or '').lower().endswith('.json'):
            documents = [(file.filename or 'annotations.json', json.loads(raw))]
        else:
            archive = zipfile.ZipFile(io.BytesIO(raw))
            members = _safe_zip_members(archive)
            documents = [(item.filename, json.loads(archive.read(item))) for item in members
                         if item.filename.lower().endswith('.json')]
            yolo_files = [item.filename for item in members if item.filename.lower().endswith('.txt')
                          and PurePosixPath(item.filename).name.lower() not in {'classes.txt', 'obj.names'}]
            image_members = [item for item in members
                             if PurePosixPath(item.filename).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}]
            if image_members:
                with database() as db:
                    get_project(db, project_id)
                    existing_ids = {row['id'] for row in db.execute('SELECT id FROM images WHERE project_id=?', (project_id,))}
                    first_batch = db.execute('SELECT id FROM import_batches WHERE project_id=? ORDER BY rowid LIMIT 1',
                                             (project_id,)).fetchone()['id']
                batch_id = first_batch if not existing_ids else create_batch(project_id, BatchCreate())['id']
                for item in image_members:
                    uploaded = upload_image(project_id, UploadFile(filename=item.filename,
                                            file=io.BytesIO(archive.read(item))), batch_id)
                    if uploaded['id'] not in existing_ids:
                        images_imported += 1
                        existing_ids.add(uploaded['id'])
    except HTTPException:
        raise
    except (json.JSONDecodeError, zipfile.BadZipFile, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f'Invalid COCO JSON or YOLO ZIP: {exc}') from exc
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=?', (project_id,)).fetchall()
        by_id = {row['id']: row for row in rows}
        updates = {}
        unmatched = []
        try:
            for document_name, document in documents:
                if not isinstance(document, dict) or 'images' not in document:
                    continue
                category_names = {c['id']: c.get('name', '') for c in document.get('categories', [])}
                target_by_name = {c['name'].casefold(): c['id'] for c in project['classes']}
                category_map = {source: target_by_name.get(name.casefold()) for source, name in category_names.items()}
                annotations = {}
                for item in document.get('annotations', []):
                    annotations.setdefault(item.get('image_id'), []).append(item)
                for source_image in document['images']:
                    source_filename = source_image.get('file_name', '')
                    row = _match_image(rows, source_filename)
                    if row is None:
                        row = _match_image(rows, str(PurePosixPath(document_name).parent / source_filename))
                    if row is None:
                        unmatched.append(source_image.get('file_name', 'unknown'))
                        continue
                    labels = []
                    boxes = []
                    if project['annotation_type'] == 'image_classification':
                        source_labels = source_image.get('category_ids', [])
                        labels = [category_map.get(item, item if item in {c['id'] for c in project['classes']} else None)
                                  for item in source_labels]
                        if any(item is None for item in labels):
                            raise HTTPException(422, 'One or more imported classes do not exist in this project')
                    else:
                        for item in annotations.get(source_image.get('id'), []):
                            target_id = category_map.get(item.get('category_id'))
                            bbox = item.get('bbox', [])
                            if target_id is None:
                                source_name = category_names.get(item.get('category_id'), item.get('category_id'))
                                raise HTTPException(422, f'Imported class {source_name!r} does not exist in this project')
                            if target_id and len(bbox) == 4:
                                boxes.append({'category_id': target_id, 'x': bbox[0], 'y': bbox[1],
                                              'width': bbox[2], 'height': bbox[3]})
                    updates[row['id']] = (boxes, labels)
            if not documents and yolo_files:
                if project['annotation_type'] != 'object_detection':
                    raise HTTPException(422, 'YOLO imports are supported for object detection projects')
                for name in yolo_files:
                    image_name = str(PurePosixPath(name).with_suffix(''))
                    image_name = re.sub(r'(^|/)(labels)(/)', r'\1images\3', image_name) + '.png'
                    row = _match_image(rows, image_name)
                    if row is None:
                        stem = PurePosixPath(name).stem
                        matches = [item for item in rows if PurePosixPath(item['source_path']).stem == stem]
                        row = matches[0] if len(matches) == 1 else None
                    if row is None:
                        unmatched.append(name)
                        continue
                    boxes = []
                    for line in archive.read(name).decode('utf-8-sig').splitlines():
                        if not line.strip():
                            continue
                        parts = line.split()
                        if len(parts) != 5:
                            raise HTTPException(422, f'Invalid YOLO annotation in {name}')
                        class_index, cx, cy, width, height = map(float, parts)
                        category_id = int(class_index) + 1
                        width *= row['width']; height *= row['height']
                        boxes.append({'category_id': category_id,
                                      'x': cx * row['width'] - width / 2,
                                      'y': cy * row['height'] - height / 2,
                                      'width': width, 'height': height})
                    updates[row['id']] = (boxes, [])
        except (json.JSONDecodeError, zipfile.BadZipFile, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, f'Invalid COCO JSON or YOLO ZIP: {exc}') from exc
        if not updates:
            raise HTTPException(422, 'No annotations matched images in this project')
        validated = []
        valid_categories = {item['id'] for item in project['classes']}
        for image_id, (boxes, labels) in updates.items():
            row = by_id[image_id]
            try:
                payload = AnnotationSave(boxes=boxes, labels=labels, completed=True, revision=row['revision'])
            except ValidationError as exc:
                raise HTTPException(422, f'Imported annotation is invalid for {row["source_path"]}') from exc
            if any(box.category_id not in valid_categories or
                   box.x + box.width > row['width'] + 0.001 or
                   box.y + box.height > row['height'] + 0.001 for box in payload.boxes):
                raise HTTPException(422, f'Imported annotation is outside {row["source_path"]}')
            validated.append((image_id, payload))
        for image_id, payload in validated:
            # Validate through the ordinary save route while retaining optimistic revisions.
            save_annotations(project_id, image_id, payload)
        return {'updated': len(updates), 'images_imported': images_imported,
                'unmatched': sorted(set(unmatched))[:100]}


@app.get('/api/projects/{project_id}/duplicates')
def duplicate_groups(project_id: str):
    with database() as db:
        get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY source_path,id', (project_id,)).fetchall()
        for row in rows:
            if not row['perceptual_hash']:
                path = DATA / 'images' / project_id / row['stored_name']
                with Image.open(path) as source:
                    value = perceptual_hash(source)
                db.execute('UPDATE images SET perceptual_hash=? WHERE id=?', (value, row['id']))
        rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY source_path,id', (project_id,)).fetchall()
    parent = list(range(len(rows)))
    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item
    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left
    distances = {}
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            distance = hamming(rows[left]['perceptual_hash'], rows[right]['perceptual_hash'])
            if distance <= 6:
                union(left, right)
                distances[(left, right)] = distance
    grouped = {}
    for index, row in enumerate(rows):
        grouped.setdefault(find(index), []).append((index, row))
    result = []
    for items in grouped.values():
        if len(items) < 2:
            continue
        indexes = {index for index, _ in items}
        group_distances = [value for (left, right), value in distances.items()
                           if left in indexes and right in indexes]
        result.append({'id': items[0][1]['id'], 'closest_distance': min(group_distances or [0]),
                       'images': [{k: row[k] for k in ('id', 'source_path', 'width', 'height')} |
                                  {'completed': bool(row['completed'])} for _, row in items]})
    return {'groups': result, 'similar_images': sum(len(group['images']) for group in result)}


@app.get('/api/projects/{project_id}/stats')
def stats(project_id: str):
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT completed,boxes,labels,review_status FROM images WHERE project_id=?',
                          (project_id,)).fetchall()
    extra = {'labels': 0} if project['annotation_type'] == 'image_classification' else {}
    classes = [c | {'boxes': 0, 'images': 0} | extra for c in project['classes']]
    by_id = {c['id']: c for c in classes}
    for row in rows:
        if not row['completed']:
            continue
        represented = set(json.loads(row['labels']))
        for category_id in represented:
            by_id[category_id]['labels'] += 1
        for box in json.loads(row['boxes']):
            by_id[box['category_id']]['boxes'] += 1
            represented.add(box['category_id'])
        for category_id in represented:
            by_id[category_id]['images'] += 1
    completed = sum(row['completed'] for row in rows)
    duplicate_result = duplicate_groups(project_id)
    return {'total': len(rows), 'completed': completed, 'remaining': len(rows) - completed,
            'boxes': sum(c['boxes'] for c in classes),
            'labels': sum(c.get('labels', 0) for c in classes), 'classes': classes,
            'similar_images': duplicate_result['similar_images'],
            'similar_groups': len(duplicate_result['groups']),
            'review': {status: sum(row['review_status'] == status for row in rows)
                       for status in ('draft', 'ready_for_review', 'approved', 'rejected')}}


@app.get('/api/projects/{project_id}/quality')
def quality(project_id: str):
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY id', (project_id,)).fetchall()
    counts = {category['id']: 0 for category in project['classes']}
    missing_labels = small_boxes = invalid_boxes = 0
    for row in rows:
        if not row['completed']:
            continue
        labels, boxes = json.loads(row['labels']), json.loads(row['boxes'])
        if not labels and not boxes:
            missing_labels += 1
        for category_id in labels:
            counts[category_id] = counts.get(category_id, 0) + 1
        for box in boxes:
            counts[box['category_id']] = counts.get(box['category_id'], 0) + 1
            area = box['width'] * box['height']
            if area < row['width'] * row['height'] * 0.001:
                small_boxes += 1
            if (box['x'] < 0 or box['y'] < 0 or box['width'] <= 0 or box['height'] <= 0 or
                    box['x'] + box['width'] > row['width'] + .001 or
                    box['y'] + box['height'] > row['height'] + .001):
                invalid_boxes += 1
    duplicate_result = duplicate_groups(project_id)
    shuffled = [row for row in rows if row['completed']]
    random.Random(42).shuffle(shuffled)
    cut = math.floor(len(shuffled) * project['export_train_percent'] / 100 + .5)
    train_ids = {row['id'] for row in shuffled[:cut]}
    test_ids = {row['id'] for row in shuffled[cut:]}
    cross_split = sum(bool({item['id'] for item in group['images']} & train_ids) and
                      bool({item['id'] for item in group['images']} & test_ids)
                      for group in duplicate_result['groups'])
    issues = []
    def issue(code, title, detail, count, severity='warning'):
        if count:
            issues.append({'code': code, 'title': title, 'detail': detail,
                           'count': count, 'severity': severity})
    issue('missing_labels', 'Completed images without labels',
          'These images are marked complete but contain no class labels or boxes.', missing_labels, 'error')
    issue('invalid_boxes', 'Boxes outside image bounds',
          'Legacy or imported boxes extend outside their source image.', invalid_boxes, 'error')
    issue('small_boxes', 'Unusually small boxes',
          'Boxes cover less than 0.1% of their image and may be accidental.', small_boxes)
    empty_names = [category['name'] for category in project['classes'] if not counts.get(category['id'])]
    issue('empty_classes', 'Classes without annotations',
          'No completed annotations use: ' + ', '.join(empty_names), len(empty_names))
    represented = [value for value in counts.values() if value]
    imbalanced = len(represented) > 1 and max(represented) > min(represented) * 5
    issue('class_imbalance', 'Strong class imbalance',
          'The most common class has more than five times the annotations of the least common represented class.',
          1 if imbalanced else 0)
    issue('similar_images', 'Similar images',
          'Near-duplicate images can overweight scenes during training.', duplicate_result['similar_images'])
    issue('cross_split_duplicates', 'Similar images cross the default split',
          'Related image groups appear in both train and test with the saved export split.', cross_split, 'error')
    return {'issues': issues, 'checks_run': 7, 'cross_split_groups': cross_split}


@app.post('/api/projects/{project_id}/export')
def export_project(project_id: str, payload: ExportRequest):
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? AND completed=1 ORDER BY id', (project_id,)).fetchall()
    if not rows:
        raise HTTPException(422, 'Mark at least one image complete before exporting')
    random.Random(42).shuffle(rows)
    cut = math.floor(len(rows) * payload.train_percent / 100 + 0.5)
    subset = rows[:cut] if payload.split == 'train' else rows[cut:]
    if not subset:
        raise HTTPException(422, f'The {payload.split} split is empty and will not be exported')
    filename = re.sub(r'[^A-Za-z0-9._-]+', '_', project['name']).strip('._-')[:80] or 'project'
    archive_name = f'{filename}_{payload.split}'
    exported_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    fd, temp_path = tempfile.mkstemp(suffix='.zip')
    os.close(fd)
    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('annotations/', b'')
            archive.writestr('images/', b'')
            distribution = {category['id']: {
                'category_id': category['id'], 'name': category['name'],
                'annotations': 0, 'annotated_images': 0,
            } for category in project['classes']}
            for row in subset:
                represented = set(json.loads(row['labels']))
                for category_id in represented:
                    distribution[category_id]['annotations'] += 1
                for box in json.loads(row['boxes']):
                    distribution[box['category_id']]['annotations'] += 1
                    represented.add(box['category_id'])
                for category_id in represented:
                    distribution[category_id]['annotated_images'] += 1
            coco = {'info': {
                        'description': payload.description.strip(),
                        'project_name': project['name'],
                        'annotation_type': project['annotation_type'],
                        'date_created': exported_at,
                        'split': payload.split,
                        'images_annotated': len(subset),
                        'total_images_annotated': len(rows),
                        'class_distribution': list(distribution.values()),
                    }, 'licenses': [], 'images': [],
                    'annotations': [], 'categories': [c | {'supercategory': ''} for c in project['classes']]}
            for row in subset:
                # Sequential IDs avoid precision loss and collisions in COCO consumers.
                image_id = len(coco['images']) + 1
                coco['images'].append({'id': image_id, 'file_name': f"images/{row['stored_name']}",
                    'width': row['width'], 'height': row['height'], 'source_path': row['source_path']})
                archive.write(DATA / 'images' / project_id / row['stored_name'], f"images/{row['stored_name']}")
                if project['annotation_type'] == 'image_classification':
                    coco['images'][-1]['category_ids'] = json.loads(row['labels'])
                for box in json.loads(row['boxes']):
                    coco['annotations'].append({'id': len(coco['annotations']) + 1, 'image_id': image_id,
                        'category_id': box['category_id'], 'bbox': [box['x'], box['y'], box['width'], box['height']],
                        'area': box['width'] * box['height'], 'iscrowd': 0, 'segmentation': []})
            archive.writestr(f'annotations/{archive_name}.json', json.dumps(coco, indent=2))
    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        raise
    return FileResponse(temp_path, media_type='application/zip', filename=f'{archive_name}.zip',
                        background=BackgroundTask(lambda: Path(temp_path).unlink(missing_ok=True)))


ai_lock = Lock()


@app.post('/api/ai/validate')
def validate_ai():
    ai_labelling.validate_credentials()
    return {'valid': True}


class AISuggestRequest(BaseModel):
    revision: int = Field(ge=0)


@app.post('/api/projects/{project_id}/images/{image_id}/ai')
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
        boxes = ai_labelling.detect(image_path, project['classes'], row['width'], row['height'],
                                    project['ai_instructions'])
        # The ordinary save path validates classes, bounds, and the revision again.
        return save_annotations(project_id, image_id, AnnotationSave(
            boxes=boxes, completed=False, revision=payload.revision))
    finally:
        ai_lock.release()


static_dir = Path(os.environ.get('LABELLING_STATIC_DIR', '/app/static'))
if static_dir.is_dir():
    app.mount('/', StaticFiles(directory=static_dir, html=True), name='frontend')
