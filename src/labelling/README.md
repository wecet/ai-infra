# AI Studio

The Training tab starts jobs only from immutable published versions. It supports the bundled local CPU/GPU compute agent or a remote agent addressed by IP, exposes model hyperparameters, downloads completed artifacts, and links tracked runs to MLflow. GPU selection remains disabled until the selected agent reports a usable runtime.

Model implementations must use the ABCs in [`../../libs/ai_interfaces`](../../libs/ai_interfaces/README.md), keeping classification and object-detection packages compatible with the same job runner.

A React frontend and Python/FastAPI backend for object detection and image classification. SQLite stores project settings, classes, annotations, completion and review state, comments, and dataset history. Active images and restorable deleted-image archives live in the same `labelling_data` Docker volume.

## Run with the stack

From the repository root, run `docker compose up --build -d`, then open http://localhost:8081 (or the host port configured by `LABELLING_PORT` in `.env`).

## Workflow

1. Create a project, choose **Object detection** or **Image classification**, and add your named classes. Alternatively, use **Import Project** on the homepage to add a complete project ZIP to the repository. The ZIP must use this layout:

   ```text
   project.zip
   ├── annotations/
   │   └── annotations.json
   └── images/
       └── image files
   ```

   After choosing the ZIP, a popup asks for the name that should appear in the repository; the ZIP filename is offered as a starting value and the entered name overrides annotation metadata. Each JSON document is validated before a project is created. A document with valid COCO `annotations[].bbox` values becomes an object-detection project; a document without boxes becomes an image-classification project and reads class assignments from `images[].category_ids`. The importer validates category and image references, numeric box shapes and bounds, class definitions, and consistent types across multiple JSON files. Payload content is authoritative when `info.annotation_type` disagrees. A project ZIP is limited to 50 MiB compressed, 2 GiB expanded, and 20,000 files. Failed imports are removed rather than leaving a partial project. A malformed import opens a help popup containing the validation error, required folder tree, and expected JSON fields.
   Homepage cards identify object detection with a box-target symbol and image classification with a grid symbol. Cards can also be dragged: move over the left or right edge of another card and release at the blue insertion line to save a new homepage order. Drop in the centre of another project of the same annotation type to preview a merge; the receiving card uses a slow, subtle growth pulse before confirmation. The receiving card is the root: it keeps its name and settings while images, annotation revisions, classes, and comments move from the dragged project. Classes with the same case-insensitive name are reused; new classes are appended and annotations are remapped. Conflicting source paths receive a folder prefix based on the source project name. History records one **Projects Merged** entry and Dashboard metrics recalculate from the combined dataset. The dragged source project and its historic deleted-image archives are removed after a successful merge. Dropping between classification and detection projects is rejected without changing either project.
2. Use **Import folder** to choose a local directory, including subfolders, or select individual files. The browser uploads copies to the server. Later uploads are recorded as **New Additions** in dataset history. JPEG, PNG, WebP, BMP and TIFF are supported, up to 50 MiB and 40 megapixels per image. For multipage TIFFs, only the first frame is imported. Other files in a folder are skipped.
3. For detection, select a class and drag to draw a box; move, resize, reclassify or delete boxes as needed. For classification, click the classes present in the whole image; multiple classes may be selected, and clicking again removes a class. No boxes are drawn.
4. Box and class changes save automatically. Click **Complete & next** when finished. **No objects · complete** or **No classes · complete** records an intentionally empty image; navigation alone leaves an image incomplete. Reopening resumes at the first incomplete image. Changing a completed classification's classes marks it incomplete for review.
5. Use brightness and contrast controls without changing the stored image. Zoom from 100–300%, enable **Pan** to drag the zoomed viewport, or enter fullscreen. Keyboard shortcuts are `←`/`→` for navigation, `1`–`9` for classes, `Delete` for the selected box, `Enter` to complete, `Ctrl/Cmd+Z` and `Ctrl/Cmd+Y` for undo/redo, and `+`/`-` for zoom. Up to 50 edits can be undone while the image remains open; every undo and redo is persisted as a new validated revision.
6. Open **Review** for completed annotations; drafts and untouched images are excluded. Search by filename and filter by class, review state, or annotation presence. Select images and use **Approve selected** for bulk approval. Reviewers can also approve individually or reject with a required correction reason. The forwarded username and timestamp are recorded. Editing reviewed work resets it to **Ready for Review**.
7. Open **History** to see immutable dataset membership versions: project creation, each later image batch, image deletions, and restorations. Each row shows the positive or negative sample change, resulting dataset size, and timestamp. **View images** opens Review filtered to an addition batch. Expanding a deletion shows an archived preview and **Restore image** action; restoration preserves the annotation revision history and review state and creates a positive **Images Restored** entry. Deletions made before archive support retain their source filename but cannot be restored.
8. Open **Dashboard** to see project progress and quality metrics. **Publish** creates an immutable snapshot named `v{number}-{YYMMDD}-ready`; **Versions** lists snapshots and their frozen images. **Export ZIP** downloads any version as an import-compatible archive built entirely from its frozen images, classes, and annotations. The lakeFS icon uploads those same frozen files to the configured repository and branch, then commits them as `Saving {dataset version name} at {DD-MM-YY} by {Username}`. KPI cards use green for completed/approved work, amber for attention, and neutral styling for totals. Quality checks cover missing labels, invalid or small boxes, class balance, similar images, and split leakage. **Comments** stores timestamped progress updates.
9. Open **Lineage** to trace imports, deleted/restored images, published versions, lakeFS commits, training runs, registered models, and deployments. Select a node to open its history batch, frozen version, lakeFS commit, training job, or MLflow run.
10. Open **Compare** to audit two published versions. It reports added/removed images, annotation and class edits, deterministic train/test membership changes, review-status changes, quality metric deltas, duplicates, and split leakage. Select a changed image for a side-by-side frozen annotation view.
11. Open **Settings** to edit project metadata, instructions, and the default train percentage. Class management supports adding, renaming, recolouring, archiving/restoring, and merging classes. Merges remap current annotations and saved revisions; archived classes remain in historical data but are unavailable for new annotations.
12. Click **Export dataset**, optionally describe the dataset, and adjust either of the linked Train/Test sliders. They always total 100%. The browser downloads two project-named archives, and each archive can be passed directly back to **Import Project**:

   ```text
   Project_Name_train.zip          Project_Name_test.zip
   ├── annotations/                ├── annotations/
   │   └── Project_Name_train.json │   └── Project_Name_test.json
   └── images/*.png                └── images/*.png
   ```

13. While viewing any image, use **Delete image from dataset** to archive a faulty sample and remove it from the active dataset after confirmation. The deletion is recorded in History and can be restored there. Use **Delete project** in the project header to permanently remove the project, its annotations, lineage, history, comments, active images, and deleted-image archives. Project deletion asks for confirmation and cannot be undone.

Each JSON file is a COCO object-detection dataset with `images`, `annotations` and `categories`. Its `info` object records the optional description, project name, UTC export timestamp, split name, annotated image counts, and per-class annotation/image distribution for that split. Boxes use original normalized image pixels as `[x, y, width, height]`, with `area` and `iscrowd: 0`. Image paths point into the archive's root `images/` folder. Export includes completed images only, including completed images without objects. The train count rounds to the nearest whole image. When a small dataset or a 0/100 split leaves one side empty, that ZIP is skipped and only the non-empty split is downloaded. A fixed random seed makes the image allocation repeatable for an unchanged set of completed images. Splits are by image, without class stratification or grouping of related images.

Images are converted to RGB PNG and EXIF orientation is applied during import, so annotation coordinates match both displayed and exported images. Export uses unique filenames and records the original relative path in each image's `source_path`. Original files on your machine are untouched. Reimporting the same relative path with identical contents preserves its annotations; different contents at the same path produce an error. Successfully imported files remain available if other uploads fail, and the folder can be selected again to retry.

Classification exports use the same ZIP layout, but each image record contains `category_ids` referencing the `categories` list. `annotations` is empty; there are no artificial full-image bounding boxes. The JSON `info.annotation_type` identifies the task. Detection exports remain COCO bounding-box datasets.

## AI-Assisted Labelling

Set `OPENAI_API_KEY` and `OPENAI_MODEL` in the private repository-root `.env`. The other `OPENAI_*` fields control the HTTPS API base URL, timeout, output token limit, image detail, optional project/organization headers, and reasoning effort (leave blank for models that do not support it). Use a model supporting image input and Structured Outputs.

Compose passes these values to the backend without baking credentials into the image. `.env` is ignored by Git. After changing a value, run `docker compose up -d labelling` to recreate the service. For native development, export the same variables in the shell; the older `GPT_ENV_FILE` override remains supported for compatibility.

In a detection project, check **AI-Assisted Labelling**. A small blank-image request validates credentials and model support. Missing or rejected credentials show **Invalid Credentials Provided** and leave the checkbox unticked. Quota, network, and unsupported-model errors have separate messages. No key is sent to the browser or stored in SQLite.

While enabled, each newly opened, untouched image is sent to OpenAI once for suggestions using the project's classes and optional AI instructions from Settings. Calls use the Responses API with structured JSON and `store: false`. Enabling the checkbox and generating suggestions incur API usage. Images are scaled to at most 2048 pixels on their longest side; returned normalized coordinates are mapped back to the original image. Existing annotations, completed images, and concurrent edits are protected from replacement. Suggestions save as incomplete drafts, including empty predictions, and remain editable. Review positioning and classes before clicking **Complete & next**. Assistance is off when reopening a project; disable and re-enable to retry a failed image.

Reference: [OpenAI image input](https://developers.openai.com/api/docs/guides/images-vision) and [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Persistence and deployment

Data lives under `/data` in the container: SQLite records are stored alongside active images in `/data/images`, recoverable deletion archives in `/data/deleted`, and immutable snapshot copies in `/data/versions`. Restarting or rebuilding preserves the named volume. Back up the entire volume with the service stopped to keep history, archives, and versions consistent.

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

### Source layout

The backend composition root is `backend/app.py`. Shared database setup, validation models, storage helpers, and image utilities live in `backend/common.py`; API endpoints are grouped under `backend/routes/`, including `comparison.py` and `lineage.py`. `backend/lakefs_client.py` handles authenticated snapshot uploads and commits.

The frontend entry point is `frontend/src/main.jsx`, with the application shell in `App.jsx`. Feature components live under `frontend/src/components/`, including dedicated modules for Dashboard, Editor, History, Review, Settings, and Versions. `style.css` only composes the focused files under `frontend/src/styles/`: base, homepage, workspace, dashboard, and responsive rules.

## Verification

```bash
src/labelling/backend/.venv/bin/pip install -r src/labelling/backend/requirements-dev.txt
PYTHONPATH=src/labelling/backend src/labelling/backend/.venv/bin/pytest src/labelling/backend/tests -q
cd src/labelling/frontend
npm ci
npm run build
```

API tests cover persisted progress, immutable versions, version comparison, end-to-end lineage, class management and revision remapping, bulk review, search/filter metadata, project ordering and merging, review workflows, quality findings, AI instructions, project ZIP imports, dataset history, deletion restoration, comments, duplicate analysis, concurrency, Dashboard counts, and export/import round trips.

### Training failure recovery

If **Start training** cannot submit the configuration, AI Studio opens a closable error popup and keeps the form available. If a queued trainer fails later, polling opens a popup with the trainer's error message and records the failed run in **Training jobs**. Close with **Close** or **Escape**, correct the configuration or dataset, then start a new run. The same failed job is not repeatedly shown during polling; earlier failures stay in the jobs table when you reopen the page.

Annotation selection uses theme-aware surfaces in the editor, review cards and version comparison. Bounding boxes retain their class colors with contrasting outlines, and class names appear on solid dark badges so they remain readable over bright or dark images.

Training job actions include **↓ Download Model**, **↗ View on MLflow**, and **▥ View live metrics** on the run itself. Live metrics opens TensorBoard's Time Series dashboard with an exact run filter, selecting only that run; the button uses the run's enabled callbacks and compute agent dashboard. New training runs are named `YYMMDD-{project-name}-v{version-number}` with a normalized project name and incrementing training version (including retries). Internal job IDs remain unique. MLflow records the validated training configuration, including defaults, augmentations, callbacks, classes, dataset version and devices, as `config.*` parameters. Existing runs retain their historical names/configuration.

### Theme and layout conventions

Light and dark modes share control dimensions and visible keyboard focus outlines. Small accent text uses a separate contrast color from coral button backgrounds. Lineage cards align content to the left and show readable metadata. Within Commits & runs, lakeFS commits use a teal branch icon and edge, while training runs use a coral play icon and edge; UTC timestamps with or without explicit offsets use the same date formatter. Training job metrics expand under **View training metrics**, while model, MLflow, and live-metrics links remain compact on one row.

When reviewing UI changes, check the project list, annotation and Review pages, Dashboard, History, Versions (including previews), Compare, Lineage, Training, and Manage in both themes. Use existing data without altering annotations or publishing extra versions for visual checks. Check populated and empty states where available, and inspect narrow-screen rules separately.

Metric cards share semantic colours in both themes, using muted tones that complement the studio palette. Dataset overview groups total images and annotations in slate, labelled and approved in sage green, and remaining, ready for review, and similar images in amber. Lineage groups batches, versions, and lakeFS commits in slate, and training runs, registered models, and deployments in the studio's coral accent. Numbers, subtle surfaces, and edges share each group's colour; text labels preserve meaning without relying on colour alone.

Lineage arrows connect individual entries using the recorded graph relationships, including training runs to their registered models. Curved connectors also link entries within one column. Hover or keyboard-focus an arrow to see its relationship description. Dashed lakeFS-to-training connections indicate snapshots of the same published dataset version, rather than claiming that training downloaded its data from lakeFS. Connectors resize with their cards and highlight when an attached card is hovered or focused.

### Anomaly detection projects

`annotation_type="anomaly_detection"` accepts an empty or omitted class list and rejects class labels. Imported images are internally marked ready (`completed=true`) for shared publishing/export paths, without annotation review. Annotation edits, class creation, and review decisions are unavailable. Quality checks cover similar images and cross-split leakage, not missing annotations. The frontend starts on Dataset Dashboard and offers Images, History, Versions, Compare, Lineage, Training, and Manage.

Publishing saves each image's train/test assignment into the immutable snapshot. `_version_content` forwards those assignments to version exports, lakeFS, and compute agents. Existing supervised archives and completion requirements are unchanged. Anomaly ZIPs exported by the platform can be imported as new unlabelled projects; republishing a new project computes a new split from its saved settings.

### Project sections

The New Project dialog opens on **Vision**, with object detection, image classification, and unsupervised anomaly detection. **LLM/VLM** and **Language** show **Under Development - Check in Soon**. Those sections hide the creation form and submit button; returning to Vision preserves entered fields.

### Agent-owned jobs and model evaluation

Training jobs now continue independently of browser lifetime and restore phase, elapsed time, heartbeat, latest metrics and recent logs. Saved models open an evaluation dialog on their recorded held-out images, with supervised metrics/failures or unlabelled anomaly scores. See [the complete behavior and recovery limits](../../docs/training-jobs-and-evaluation.md).
