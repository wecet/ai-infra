"""Labelling API composition root and production React host."""
from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import pymysql

import ai_labelling
import common
import auth
from common import DATA, init_db, database, get_project, get_image, image_json
from routes import comparison, datasets, images, lineage, projects, training, versions, models


@asynccontextmanager
async def lifespan(application):
    # DATA remains an intentionally supported override for isolated tests.
    common.DATA = DATA
    for module in (comparison, datasets, images, lineage, projects, training, versions, models):
        module.DATA = DATA
    init_db()
    auth.init_auth()
    training.resume_jobs()
    models.resume_evaluations()
    yield


app = FastAPI(title='Labelling API', lifespan=lifespan)


@app.middleware('http')
async def private_api_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Vary'] = 'Cookie'
    return response


@app.exception_handler(pymysql.MySQLError)
async def identity_unavailable(request, error):
    return JSONResponse(status_code=503, content={'detail': 'The user database is unavailable. Try again shortly.'})


@app.get('/api/health')
def health():
    return {'status': 'ok'}


for router in (projects.router, comparison.router, versions.router, images.router, datasets.router,
               training.router, lineage.router, models.router):
    app.include_router(router, dependencies=[Depends(auth.authorize)])
app.include_router(auth.router)


static_dir = Path(os.environ.get('LABELLING_STATIC_DIR', '/app/static'))
if static_dir.is_dir():
    app.mount('/', StaticFiles(directory=static_dir, html=True), name='frontend')
