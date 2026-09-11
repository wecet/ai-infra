# Labelling Studio

A React frontend and Python/FastAPI backend for object detection and image classification. SQLite stores project settings, classes, annotations, completion and review state, comments, and dataset history. Active images and restorable deleted-image archives live in the same `labelling_data` Docker volume.

## Run with the stack

Open the repository in Deployment Manager, select a profile, review the deployment plan, and deploy it. Then open http://localhost:8080 (or the port configured by `LABELLING_PORT` in your profile). For a remote Docker host, replace `localhost` with its IP address.

## Workflow

1. Create a project, choose **Object detection** or **Image classification**, and add your named classes. Alternatively, use **Import Project** on the homepage to add a complete project ZIP to the repository. The ZIP must use this layout:

   ```text
   project.zip
   ├── annotations/
   │   └── annotations.json
   └── images/
       └── image files
   ```

   After choosing the ZIP, a popup asks for the name that should appear in the repository; the ZIP filename is offered as a starting value and the entered name overrides annotation metadata. The JSON uses the COCO `images`, `annotations`, and `categories` fields. `info.annotation_type` may be `object_detection` or `image_classification`; otherwise object detection is used. Multiple JSON files are accepted when they define the same classes and project type. A project ZIP is limited to 50 MiB compressed, 2 GiB expanded, and 20,000 files. Failed imports are removed rather than leaving a partial project. A malformed import opens a help popup containing the validation error, required folder tree, and expected JSON fields.
   Project cards on the homepage can also be dragged. Drop one onto another project of the same annotation type to preview a merge, then confirm it. The receiving card is the root: it keeps its name and settings while images, annotation revisions, classes, and comments move from the dragged project. Classes with the same case-insensitive name are reused; new classes are appended and annotations are remapped. Conflicting source paths receive a folder prefix based on the source project name. History records one **Projects Merged** entry and Dashboard metrics recalculate from the combined dataset. The dragged source project and its historic deleted-image archives are removed after a successful merge. Dropping between classification and detection projects is rejected without changing either project.
2. Use **Import folder** to choose a local directory, including subfolders, or select individual files. The browser uploads copies to the server. Later uploads are recorded as **New Additions** in dataset history. JPEG, PNG, WebP, BMP and TIFF are supported, up to 50 MiB and 40 megapixels per image. For multipage TIFFs, only the first frame is imported. Other files in a folder are skipped.
3. For detection, select a class and drag to draw a box; move, resize, reclassify or delete boxes as needed. For classification, click the classes present in the whole image; multiple classes may be selected, and clicking again removes a class. No boxes are drawn.
4. Box and class changes save automatically. Click **Complete & next** when finished. **No objects · complete** or **No classes · complete** records an intentionally empty image; navigation alone leaves an image incomplete. Reopening resumes at the first incomplete image. Changing a completed classification's classes marks it incomplete for review.
5. Use brightness and contrast controls without changing the stored image. Zoom from 100–300%, enable **Pan** to drag the zoomed viewport, or enter fullscreen. Keyboard shortcuts are `←`/`→` for navigation, `1`–`9` for classes, `Delete` for the selected box, `Enter` to complete, `Ctrl/Cmd+Z` and `Ctrl/Cmd+Y` for undo/redo, and `+`/`-` for zoom. Up to 50 edits can be undone while the image remains open; every undo and redo is persisted as a new validated revision.
6. Open **Review** for a visual gallery of completed annotations. Completing an annotation marks it **Ready for Review**. Reviewers can approve it or reject it with a required correction reason, and filter the gallery by status. The forwarded authenticated username and timestamp are recorded with the decision. Editing an approved or rejected annotation resets it to **Ready for Review**.
7. Open **History** to see immutable dataset membership versions: project creation, each later image batch, image deletions, and restorations. Each row shows the positive or negative sample change, resulting dataset size, and timestamp. **View images** opens Review filtered to an addition batch. Expanding a deletion shows an archived preview and **Restore image** action; restoration preserves the annotation revision history and review state and creates a positive **Images Restored** entry. Deletions made before archive support retain their source filename but cannot be restored.
8. Open **Dashboard** to see the project description, progress, review counts, bounding-box or image-label counts, and distinct image counts for each class. KPI cards use restrained green accents for completed/approved work, amber for items requiring attention, and neutral styling for totals. Dataset quality checks flag completed images without labels, out-of-bounds and unusually small boxes, unused or strongly imbalanced classes, similar images, and similar groups divided between the saved train/test split. Class representation counts completed images only. The **Similar images** metric groups images whose 64-bit perceptual hashes differ by six bits or fewer; click it to inspect the groups before exporting. Use **Comments** below Class representation for persistent, timestamped project updates displayed newest first. The authenticated username forwarded by the access proxy is shown as the author; direct development access uses `admin`. Comments are stored in the project database and removed with the project.
9. Open **Settings** to edit the project name and description, human labelling instructions, detection-specific AI instructions, and the default train percentage. The description appears on Dashboard, labelling instructions appear above the editor, AI instructions are added to the model request as annotation criteria, and the saved split initializes exports and cross-split quality checks.
10. Click **Export dataset**, optionally describe the dataset, and adjust either of the linked Train/Test sliders. They always total 100%. The browser downloads two project-named archives, and each archive can be passed directly back to **Import Project**:

   ```text
   Project_Name_train.zip          Project_Name_test.zip
   ├── annotations/                ├── annotations/
   │   └── Project_Name_train.json │   └── Project_Name_test.json
   └── images/*.png                └── images/*.png
   ```

11. While viewing any image, use **Delete image from dataset** to archive a faulty sample and remove it from the active dataset after confirmation. The deletion is recorded in History and can be restored there. Use **Delete project** in the project header to permanently remove the project, its annotations, history, comments, active images, and deleted-image archives. Project deletion asks for confirmation and cannot be undone.

Each JSON file is a COCO object-detection dataset with `images`, `annotations` and `categories`. Its `info` object records the optional description, project name, UTC export timestamp, split name, annotated image counts, and per-class annotation/image distribution for that split. Boxes use original normalized image pixels as `[x, y, width, height]`, with `area` and `iscrowd: 0`. Image paths point into the archive's root `images/` folder. Export includes completed images only, including completed images without objects. The train count rounds to the nearest whole image. When a small dataset or a 0/100 split leaves one side empty, that ZIP is skipped and only the non-empty split is downloaded. A fixed random seed makes the image allocation repeatable for an unchanged set of completed images. Splits are by image, without class stratification or grouping of related images.

Images are converted to RGB PNG and EXIF orientation is applied during import, so annotation coordinates match both displayed and exported images. Export uses unique filenames and records the original relative path in each image's `source_path`. Original files on your machine are untouched. Reimporting the same relative path with identical contents preserves its annotations; different contents at the same path produce an error. Successfully imported files remain available if other uploads fail, and the folder can be selected again to retry.

Classification exports use the same ZIP layout, but each image record contains `category_ids` referencing the `categories` list. `annotations` is empty; there are no artificial full-image bounding boxes. The JSON `info.annotation_type` identifies the task. Detection exports remain COCO bounding-box datasets.

## AI-Assisted Labelling

Fill in the private repository-root `gpt.env` using `gpt.env.example` as a reference. `OPENAI_API_KEY` and `OPENAI_MODEL` are required. The other fields control the HTTPS API base URL, timeout, output token limit, image detail, optional project/organization headers, and reasoning effort (leave blank for models that do not support it). Use a model supporting image input and Structured Outputs.

Deployment Manager mounts `gpt.env` read-only at `/app/gpt.env`; it is ignored by Git and excluded from images. For a fresh checkout, copy `gpt.env.example` to `gpt.env` before deploying, even if leaving the key blank. Native development finds the repository-root file automatically; `GPT_ENV_FILE` overrides its location. After changing credentials in the deployment checkout, redeploy the labeller to synchronize the mounted file to the target host.

In a detection project, check **AI-Assisted Labelling**. A small blank-image request validates credentials and model support. Missing or rejected credentials show **Invalid Credentials Provided** and leave the checkbox unticked. Quota, network, and unsupported-model errors have separate messages. No key is sent to the browser or stored in SQLite.

While enabled, each newly opened, untouched image is sent to OpenAI once for suggestions using the project's classes and optional AI instructions from Settings. Calls use the Responses API with structured JSON and `store: false`. Enabling the checkbox and generating suggestions incur API usage. Images are scaled to at most 2048 pixels on their longest side; returned normalized coordinates are mapped back to the original image. Existing annotations, completed images, and concurrent edits are protected from replacement. Suggestions save as incomplete drafts, including empty predictions, and remain editable. Review positioning and classes before clicking **Complete & next**. Assistance is off when reopening a project; disable and re-enable to retry a failed image.

Reference: [OpenAI image input](https://developers.openai.com/api/docs/guides/images-vision) and [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Persistence and deployment

Data lives under `/data` in the container: SQLite records are stored alongside active images in `/data/images` and recoverable deletion archives in `/data/deleted`. Restarting or rebuilding preserves the named volume. Back up the entire volume with the service stopped to keep history records and archived files consistent. Deleting the named volume permanently deletes active and archived data.

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

API tests cover persisted progress, transactional same-type project merging and class remapping, cross-type merge rejection, project settings, review decisions and reset behavior, quality findings, AI instructions, prompted project ZIP imports and rollback, import batches and dataset history, deleted-image previews and restoration with revision recovery, project comments, near-duplicate groups, reimports, project deletion and isolation, concurrent-edit conflicts, invalid coordinates, image orientation, Dashboard counts, paired export/import round trips, skipped empty splits, and negative examples.
