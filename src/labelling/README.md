# Labelling Studio

A React frontend and Python/FastAPI backend for persistent bounding-box annotation projects. SQLite stores project definitions, annotation coordinates and completion state; uploaded images are stored alongside it in the `labelling_data` Docker volume.

## Run with the stack

```bash
./start.sh dev
```

Open http://localhost:8080 (or the port configured by `LABELLING_PORT` in your profile). For a remote Docker host, replace `localhost` with its IP address. The service is also built and started by `./start.sh`.

## Workflow

1. Create a project and add as many named classes as you need. Class names must be unique within a project. Classes are fixed once the project is created.
2. Use **Import folder** to choose a local directory, including subfolders, or select individual files. The browser uploads copies to the server. JPEG, PNG, WebP, BMP and TIFF are supported, up to 50 MiB and 40 megapixels per image. For multipage TIFFs, only the first frame is imported. Other files in a folder are skipped.
3. Select a class and drag on the image to draw a box. Drag a box to move it, or select it and drag its bottom-right handle to resize. Use the box list to change its class or delete it. Zoom controls provide finer detail.
4. Each box change saves automatically. Click **Complete & next** when finished. **No objects · complete** records an intentionally empty image; navigation alone leaves an image incomplete. Reopening a project resumes at its first incomplete image. Completed images can also be revisited and edited.
5. Open **KPIs & export** to see total, labelled and remaining images, plus class box counts and distinct image counts. Class representation counts completed images only.
6. Click **Export dataset**, enter a filename, optionally describe the dataset, and adjust either of the linked Train/Test sliders. They always total 100%. Download contains:

   ```text
   chosen-name.zip
   ├── train/
   │   ├── chosen-name.json
   │   └── images/*.png
   └── test/
       ├── chosen-name.json
       └── images/*.png
   ```

7. Use **Delete project** in the project header to permanently remove the project, its annotations, and its uploaded image copies. The browser asks for confirmation first. This action cannot be undone.

Each JSON file is a COCO object-detection dataset with `images`, `annotations` and `categories`. Its `info` object records the optional description, project name, UTC export timestamp, split name, annotated image counts, and per-class annotation/image distribution for that split. Boxes use original normalized image pixels as `[x, y, width, height]`, with `area` and `iscrowd: 0`. Image paths are relative to the JSON file. Export includes completed images only, including completed images without objects. The train count rounds to the nearest whole image; a small dataset or a 0/100 split can leave one split empty. A fixed random seed makes the image allocation repeatable for an unchanged set of completed images. Splits are by image, without class stratification or grouping of related images.

Images are converted to RGB PNG and EXIF orientation is applied during import, so annotation coordinates match both displayed and exported images. Export uses unique filenames and records the original relative path in each image's `source_path`. Original files on your machine are untouched. Reimporting the same relative path with identical contents preserves its annotations; different contents at the same path produce an error. Successfully imported files remain available if other uploads fail, and the folder can be selected again to retry.

## Persistence and deployment

Data lives under `/data` in the container. Restarting or rebuilding preserves the named volume. Back up the entire volume with the service stopped to keep the database and image files consistent. `./scripts/compose.sh dev down -v` deletes this data.

This service has no login or per-user permissions: deploy it on your trusted internal network. Conflicting edits to the same image from different tabs are rejected instead of overwriting newer annotations. A failed save is shown in the UI and blocks navigation until retried or explicitly discarded by reloading the image.

## Local development

Use Python 3.12 and Node.js 24. From the repository root:

```bash
python3 -m venv src/labelling/backend/.venv
src/labelling/backend/.venv/bin/pip install -r src/labelling/backend/requirements.txt
LABELLING_DATA_DIR="$PWD/src/labelling/data" src/labelling/backend/.venv/bin/uvicorn app:app --app-dir src/labelling/backend --host 127.0.0.1 --port 8080
```

In a second terminal:

```bash
cd src/labelling/frontend
npm ci
npm run dev
```

Vite proxies `/api` to the Python service on port 8080. Open the local URL printed by Vite. Production builds serve the compiled React app directly from FastAPI.

## Verification

```bash
src/labelling/backend/.venv/bin/pip install -r src/labelling/backend/requirements-dev.txt
PYTHONPATH=src/labelling/backend src/labelling/backend/.venv/bin/pytest src/labelling/backend/tests -q
cd src/labelling/frontend
npm ci
npm run build
```

API tests cover persisted progress, reimports, project deletion and isolation, concurrent-edit conflicts, invalid coordinates, image orientation, KPI counts, and complete/disjoint COCO exports, including empty splits and negative examples.
