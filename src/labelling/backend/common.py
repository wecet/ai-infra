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
        CREATE TABLE IF NOT EXISTS dataset_versions (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            version_number INTEGER NOT NULL, name TEXT NOT NULL, author TEXT NOT NULL,
            sample_count INTEGER NOT NULL, snapshot TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id,version_number));
        CREATE TABLE IF NOT EXISTS training_jobs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            version_id TEXT NOT NULL REFERENCES dataset_versions(id), task_type TEXT NOT NULL,
            base_model TEXT NOT NULL, hyperparameters TEXT NOT NULL, compute_target TEXT NOT NULL,
            status TEXT NOT NULL, metrics TEXT NOT NULL DEFAULT '{}', artifact_path TEXT,
            mlflow_run_id TEXT, error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, started_at TEXT, completed_at TEXT);
        CREATE TABLE IF NOT EXISTS lakefs_commits (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            version_id TEXT NOT NULL REFERENCES dataset_versions(id), commit_id TEXT NOT NULL,
            repository TEXT NOT NULL, branch TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS registered_models (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            training_job_id TEXT NOT NULL REFERENCES training_jobs(id), name TEXT NOT NULL,
            model_version INTEGER NOT NULL, mlflow_run_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id,name,model_version));
        CREATE TABLE IF NOT EXISTS model_deployments (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            registered_model_id TEXT NOT NULL REFERENCES registered_models(id), name TEXT NOT NULL,
            environment TEXT NOT NULL, status TEXT NOT NULL, endpoint TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        ''')
        # Additive migrations preserve annotations from existing deployments.
        if 'tensorboard_url' not in {r['name'] for r in db.execute('PRAGMA table_info(training_jobs)')}:
            db.execute("ALTER TABLE training_jobs ADD COLUMN tensorboard_url TEXT NOT NULL DEFAULT ''")
        if 'run_name' not in {r['name'] for r in db.execute('PRAGMA table_info(training_jobs)')}:
            db.execute("ALTER TABLE training_jobs ADD COLUMN run_name TEXT NOT NULL DEFAULT ''")
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
        db.execute('CREATE INDEX IF NOT EXISTS idx_versions_project ON dataset_versions(project_id,version_number)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_training_jobs_project ON training_jobs(project_id,created_at)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_lakefs_commits_project ON lakefs_commits(project_id,created_at)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_registered_models_project ON registered_models(project_id,created_at)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_model_deployments_project ON model_deployments(project_id,created_at)')
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


class BulkReview(BaseModel):
    image_ids: list[str] = Field(min_length=1, max_length=1000)
    status: Literal['approved'] = 'approved'


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(pattern=r'^#[0-9A-Fa-f]{6}$')


class ClassUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(pattern=r'^#[0-9A-Fa-f]{6}$')
    archived: bool = False


class ClassMerge(BaseModel):
    target_category_id: int = Field(ge=1)


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
