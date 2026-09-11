# Labelling Studio

A React frontend and Python/FastAPI backend for object detection and image classification. SQLite stores project types, classes, boxes, whole-image class labels and completion state; uploaded images live in the same `labelling_data` Docker volume.

## Run with the stack

Open the repository in Deployment Manager, select a profile, review the deployment plan, and deploy it. Then open http://localhost:8080 (or the port configured by `LABELLING_PORT` in your profile). For a remote Docker host, replace `localhost` with its IP address.

## Workflow

1. Create a project, choose **Object detection** or **Image classification**, and add your named classes. Select one project type. Class names must be unique; type and classes are fixed once created. Existing projects remain object detection projects.
2. Use **Import folder** to choose a local directory, including subfolders, or select individual files. The browser uploads copies to the server. JPEG, PNG, WebP, BMP and TIFF are supported, up to 50 MiB and 40 megapixels per image. For multipage TIFFs, only the first frame is imported. Other files in a folder are skipped.
3. For detection, select a class and drag to draw a box; move, resize, reclassify or delete boxes as needed. For classification, click the classes present in the whole image; multiple classes may be selected, and clicking again removes a class. No boxes are drawn.
4. Box and class changes save automatically. Click **Complete & next** when finished. **No objects · complete** or **No classes · complete** records an intentionally empty image; navigation alone leaves an image incomplete. Reopening resumes at the first incomplete image. Changing a completed classification's classes marks it incomplete for review.
5. Open **KPIs & export** to see progress, bounding-box or image-label counts, and distinct image counts for each class. Class representation counts completed images only.
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

Classification exports use the same ZIP layout, but each image record contains `category_ids` referencing the `categories` list. `annotations` is empty; there are no artificial full-image bounding boxes. The JSON `info.annotation_type` identifies the task. Detection exports remain COCO bounding-box datasets.

## AI-Assisted Labelling

Fill in the private repository-root `gpt.env` using `gpt.env.example` as a reference. `OPENAI_API_KEY` and `OPENAI_MODEL` are required. The other fields control the HTTPS API base URL, timeout, output token limit, image detail, optional project/organization headers, and reasoning effort (leave blank for models that do not support it). Use a model supporting image input and Structured Outputs.

Deployment Manager mounts `gpt.env` read-only at `/app/gpt.env`; it is ignored by Git and excluded from images. For a fresh checkout, copy `gpt.env.example` to `gpt.env` before deploying, even if leaving the key blank. Native development finds the repository-root file automatically; `GPT_ENV_FILE` overrides its location. After changing credentials in the deployment checkout, redeploy the labeller to synchronize the mounted file to the target host.

In a detection project, check **AI-Assisted Labelling**. A small blank-image request validates credentials and model support. Missing or rejected credentials show **Invalid Credentials Provided** and leave the checkbox unticked. Quota, network, and unsupported-model errors have separate messages. No key is sent to the browser or stored in SQLite.

While enabled, each newly opened, untouched image is sent to OpenAI once for suggestions using only the project's classes. Calls use the Responses API with structured JSON and `store: false`. Enabling the checkbox and generating suggestions incur API usage. Images are scaled to at most 2048 pixels on their longest side; returned normalized coordinates are mapped back to the original image. Existing annotations, completed images, and concurrent edits are protected from replacement. Suggestions save as incomplete drafts, including empty predictions, and remain editable. Review positioning and classes before clicking **Complete & next**. Assistance is off when reopening a project; disable and re-enable to retry a failed image.

Reference: [OpenAI image input](https://developers.openai.com/api/docs/guides/images-vision) and [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Persistence and deployment

Data lives under `/data` in the container. Restarting or rebuilding preserves the named volume. Back up the entire volume with the service stopped to keep the database and image files consistent. Deleting the named volume deletes this data.

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
