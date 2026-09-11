"""Labelling API composition root and production React host."""
from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import ai_labelling
import common
from common import *  # Re-export stable helpers used by tests and local tooling.
from routes import datasets, images, projects, versions


@asynccontextmanager
async def lifespan(application):
    # DATA remains an intentionally supported override for isolated tests.
    common.DATA = DATA
    for module in (datasets, images, projects, versions):
        module.DATA = DATA
    init_db()
    yield


app = FastAPI(title='Labelling API', lifespan=lifespan)


@app.get('/api/health')
def health():
    return {'status': 'ok'}


for router in (projects.router, versions.router, images.router, datasets.router):
    app.include_router(router)


static_dir = Path(os.environ.get('LABELLING_STATIC_DIR', '/app/static'))
if static_dir.is_dir():
    app.mount('/', StaticFiles(directory=static_dir, html=True), name='frontend')
