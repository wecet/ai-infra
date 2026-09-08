"""Persistent image annotation API and production React host."""
import hashlib
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

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
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
        ''')


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    classes: list[str] = Field(min_length=1)


class Box(BaseModel):
    category_id: int = Field(ge=1)
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)
    width: float = Field(gt=0, allow_inf_nan=False)
    height: float = Field(gt=0, allow_inf_nan=False)


class AnnotationSave(BaseModel):
    boxes: list[Box]
    completed: bool
    revision: int = Field(ge=0)


class ExportRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=100)
    train_percent: int = Field(ge=0, le=100)
    description: str = Field(default='', max_length=1000)


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


def image_json(row):
    return {key: row[key] for key in ('id', 'source_path', 'width', 'height', 'revision')} | {
        'completed': bool(row['completed']), 'boxes': json.loads(row['boxes'])}


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/projects')
def projects():
    with database() as db:
        rows = db.execute('''SELECT p.id, p.name, p.created_at, COUNT(i.id) AS total,
            COALESCE(SUM(i.completed), 0) AS completed FROM projects p
            LEFT JOIN images i ON i.project_id=p.id GROUP BY p.id ORDER BY p.created_at DESC, p.id''')
        return [dict(row) for row in rows]


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
        db.execute('INSERT INTO projects (id,name,classes) VALUES (?,?,?)',
                   (project_id, name, json.dumps(categories)))
        return get_project(db, project_id)


@app.get('/api/projects/{project_id}')
def project(project_id: str):
    with database() as db:
        return get_project(db, project_id)


@app.delete('/api/projects/{project_id}')
def delete_project(project_id: str):
    with database() as db:
        get_project(db, project_id)
        db.execute('DELETE FROM images WHERE project_id=?', (project_id,))
        db.execute('DELETE FROM projects WHERE id=?', (project_id,))
    shutil.rmtree(DATA / 'images' / project_id, ignore_errors=True)
    return {'deleted': project_id}


@app.get('/api/projects/{project_id}/images')
def images(project_id: str):
    with database() as db:
        get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY source_path,id', (project_id,))
        return [{k: item[k] for k in ('id', 'source_path', 'width', 'height', 'completed')} for item in rows]


@app.post('/api/projects/{project_id}/images', status_code=201)
def upload_image(project_id: str, file: UploadFile = File(...)):
    with database() as db:
        get_project(db, project_id)
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
                normalized.save(target, 'PNG')
        with database() as db:
            db.execute('''INSERT INTO images
                (id,project_id,source_path,stored_name,digest,width,height) VALUES (?,?,?,?,?,?,?)''',
                (image_id, project_id, source_path, stored_name, digest, width, height))
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


@app.put('/api/projects/{project_id}/images/{image_id}')
def save_annotations(project_id: str, image_id: str, payload: AnnotationSave):
    with database() as db:
        project = get_project(db, project_id)
        row = get_image(db, project_id, image_id)
        categories = {c['id'] for c in project['classes']}
        for box in payload.boxes:
            if box.category_id not in categories:
                raise HTTPException(422, 'Unknown class')
            if box.x + box.width > row['width'] + 0.001 or box.y + box.height > row['height'] + 0.001:
                raise HTTPException(422, 'Bounding box is outside the image')
        result = db.execute('''UPDATE images SET boxes=?,completed=?,revision=revision+1
            WHERE id=? AND project_id=? AND revision=?''',
            (json.dumps([b.model_dump() for b in payload.boxes]), payload.completed,
             image_id, project_id, payload.revision))
        if result.rowcount != 1:
            raise HTTPException(409, 'This image changed in another tab. Reload before editing again.')
        return image_json(get_image(db, project_id, image_id))


@app.get('/api/projects/{project_id}/stats')
def stats(project_id: str):
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT completed,boxes FROM images WHERE project_id=?', (project_id,)).fetchall()
    classes = [c | {'boxes': 0, 'images': 0} for c in project['classes']]
    by_id = {c['id']: c for c in classes}
    for row in rows:
        if not row['completed']:
            continue
        represented = set()
        for box in json.loads(row['boxes']):
            by_id[box['category_id']]['boxes'] += 1
            represented.add(box['category_id'])
        for category_id in represented:
            by_id[category_id]['images'] += 1
    completed = sum(row['completed'] for row in rows)
    return {'total': len(rows), 'completed': completed, 'remaining': len(rows) - completed,
            'boxes': sum(c['boxes'] for c in classes), 'classes': classes}


@app.post('/api/projects/{project_id}/export')
def export_project(project_id: str, payload: ExportRequest):
    filename = re.sub(r'\.(zip|json)$', '', payload.filename.strip(), flags=re.I)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,95}', filename):
        raise HTTPException(422, 'Use a filename starting with a letter or number, with letters, numbers, dots, underscores or hyphens')
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? AND completed=1 ORDER BY id', (project_id,)).fetchall()
    if not rows:
        raise HTTPException(422, 'Mark at least one image complete before exporting')
    random.Random(42).shuffle(rows)
    cut = math.floor(len(rows) * payload.train_percent / 100 + 0.5)
    exported_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    fd, temp_path = tempfile.mkstemp(suffix='.zip')
    os.close(fd)
    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for split, subset in [('train', rows[:cut]), ('test', rows[cut:])]:
                distribution = {category['id']: {
                    'category_id': category['id'], 'name': category['name'],
                    'annotations': 0, 'annotated_images': 0,
                } for category in project['classes']}
                for row in subset:
                    represented = set()
                    for box in json.loads(row['boxes']):
                        distribution[box['category_id']]['annotations'] += 1
                        represented.add(box['category_id'])
                    for category_id in represented:
                        distribution[category_id]['annotated_images'] += 1
                coco = {'info': {
                            'description': payload.description.strip(),
                            'project_name': project['name'],
                            'date_created': exported_at,
                            'split': split,
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
                    archive.write(DATA / 'images' / project_id / row['stored_name'], f"{split}/images/{row['stored_name']}")
                    for box in json.loads(row['boxes']):
                        coco['annotations'].append({'id': len(coco['annotations']) + 1, 'image_id': image_id,
                            'category_id': box['category_id'], 'bbox': [box['x'], box['y'], box['width'], box['height']],
                            'area': box['width'] * box['height'], 'iscrowd': 0, 'segmentation': []})
                archive.writestr(f'{split}/{filename}.json', json.dumps(coco, indent=2))
    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        raise
    return FileResponse(temp_path, media_type='application/zip', filename=f'{filename}.zip',
                        background=BackgroundTask(lambda: Path(temp_path).unlink(missing_ok=True)))


static_dir = Path(os.environ.get('LABELLING_STATIC_DIR', '/app/static'))
if static_dir.is_dir():
    app.mount('/', StaticFiles(directory=static_dir, html=True), name='frontend')
