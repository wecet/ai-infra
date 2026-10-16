# AI Infrastructure

A self-hosted Docker Compose stack containing:

- **AI Studio** — dataset annotation, model training and lineage
- **lakeFS** — versioned dataset storage used by published labelling snapshots
- **MLflow** - experiment and artifact tracking
- **Training agent** - CPU/GPU model execution, deployable locally or on a remote host
- **TensorBoard** — live training losses and Grad-CAM images for the PyTorch demos

The labeller supports project ZIP import/export, managed classes, AI-assisted box suggestions, review workflows, immutable versions, lakeFS publishing, dataset lineage, version comparison, dataset quality checks, deletion recovery, comments, train/test exports, and version-bound training jobs. See the [labelling guide](src/labelling/README.md) for the complete workflow.

## Project families and planning

**Vision** includes object detection, image classification and unsupervised anomaly datasets. **LLM/VLM** and **Language** currently display **Under Development - Check in Soon**.

Use the [documentation index](docs/README.md) for current capabilities, operating guides and proposals. The [roadmap](docs/roadmap.md) prioritizes job reliability, reproducible splits, evaluation, and future project families; the [UI/UX plan](docs/ui-ux-roadmap.md) describes usability improvements. Roadmap entries are proposals, not delivery commitments.

## Quick start

Docker with the Compose plugin is the only deployment prerequisite. Set unique `AUTH_MYSQL_PASSWORD` and `AUTH_MYSQL_ROOT_PASSWORD` values in `.env` before starting the stack.

```bash
cp .env.example .env
# Review .env and replace the lakeFS secrets before using this outside local development.
docker compose up --build -d
docker compose ps
```

This checkout already has a local `.env` with development credentials. The file is intentionally ignored by Git; `.env.example` is the committed template.

Open the services at:

| Service | Default URL |
| --- | --- |
| AI Studio | http://localhost:8081 |
| lakeFS | http://localhost:8002 |
| MLflow | http://localhost:5001 |
| Training agent | http://localhost:8090 |
| TensorBoard | http://localhost:6006 |

The labeller uses host port `8081` because `8080` was already occupied on the machine where this stack was configured. Change `LABELLING_PORT`, `LAKEFS_PORT`, or `MLFLOW_PORT` in `.env` if a port is unavailable, then recreate the services with `docker compose up -d`.

lakeFS is initialized automatically from the `LAKEFS_*` values in `.env`. Log in with `LAKEFS_ACCESS_KEY_ID` and `LAKEFS_SECRET_ACCESS_KEY`. The `datasets` repository is created automatically the first time a labelling version is pushed. MLflow stores both its SQLite database and artifacts in a named volume. The bundled training agent always supports CPU; its GPU option is disabled unless it detects an exposed GPU runtime.

## Users and repository access

System owners manage users, roles, teams and password resets from **Users & teams** on the homepage. Projects are private repositories owned by their creator; their Manage page grants Read/Write access to users or teams and supports ownership transfer. See [Users and repository access](docs/users-and-repository-access.md) for setup and migration.

## Model training

Publish an immutable dataset from the Dashboard, then open the project's **Training** tab. Choose the version, installed base model, hyperparameters, and compute target. For remote compute, run the training-agent image on another machine, expose port `8090`, enter its IP and port, and test the connection before starting the job.

The bundled models are lightweight baseline trainers: a colour-centroid classifier, a class box-prior detector and an unsupervised colour-distance anomaly scorer. They exercise the complete job, artifact, and MLflow path without downloading a heavyweight framework. Two discoverable PyTorch demos live in [`tests`](tests/README.md): a multi-label CNN classifier and a Faster R-CNN detector with a tiny backbone. The training-agent image installs their PyTorch dependencies. **View live metrics** opens TensorBoard in a new tab; losses and Grad-CAM visualizations are logged during training and retained in the training-runs volume. Other PyTorch, TensorFlow, or ONNX packages plug into the public contracts in [`libs/ai_interfaces`](libs/ai_interfaces/README.md).

Training configuration fields use their Pydantic defaults and expose `Field(description="...")` through the information button beside each label. Missing descriptions show **No description defined**. Start-request errors and newly failed background runs open a closable error popup; the training page and entered configuration remain available for correction and retry. Trainer exception details are retained in the failed job's result. Close the popup with **Close** or **Escape**; polling does not repeatedly reopen the same failure or replay historical failures when entering the page.

Training is owned by the compute agent rather than the browser. Refreshing or closing Training does not cancel a job; returning restores persisted logs and current phase, elapsed time, heartbeat and metrics in compact cards. Studio can reattach after restart; agent restarts mark interrupted runs for retry. See [Training jobs and evaluation](docs/training-jobs-and-evaluation.md) for recovery limits and the progress callback.

New jobs record a fixed held-out partition and exclude those images from fitting. Click a **saved model** or **View model** to open its evaluation dialog: predictions, task-specific metrics and supervised failure examples are saved against that model and dataset version. Anomaly results show scores and flagged examples without claiming labelled accuracy. Older models without held-out provenance explain why verified evaluation is unavailable.

The project **Lineage** tab traces imports, deletion/restoration events, published versions, lakeFS commits, training runs, registered models, and deployments. The **Compare** tab audits any two published versions, including membership, annotations, classes, deterministic train/test assignment, review status, quality metrics, duplicates, and split leakage.

See [Workspace authoring](docs/workspace-authoring.md) for the directory layout and configuration, model, training and inference skeletons.

Install the current `ai_interfaces` contracts in another workspace from their package release tag:

```bash
pip install "ai-infra-interfaces @ git+https://github.com/wecet/ai-infra.git@ai-interfaces-v0.3.0#subdirectory=libs/ai_interfaces"
```

## Configuration

All runtime settings are in `.env`:

- Image tags, published ports, Docker network, log rotation, and named-volume names
- lakeFS encryption, login credentials, repository, branch, and local namespace
- Optional OpenAI Responses API settings for AI-assisted labelling

Leave `OPENAI_API_KEY` empty to use manual labelling only. Do not commit `.env`. Replace all sample secrets before exposing the services to another machine.

## Common commands

```bash
docker compose up --build -d       # build and start everything
docker compose ps                  # check service health
docker compose logs -f             # follow all logs
docker compose down                # stop containers, preserve data
docker compose pull                # refresh upstream lakeFS/MLflow images
```

Do not use `docker compose down -v` unless you intend to delete all labelling, lakeFS, and MLflow data.

## Releases and GitHub Packages

The current platform release is `v1.2.0`. Pull its multi-platform runtime packages with:

```bash
docker pull ghcr.io/wecet/ai-infra/labelling:v1.2.0
docker pull ghcr.io/wecet/ai-infra/training-agent:v1.2.0
```

Pushing a semantic version tag, or manually running **Publish platform release**, publishes both images for AMD64 and ARM64. The workflow creates a GitHub Release containing offline Linux AMD64 OCI archives plus Compose and environment templates already configured for the published images. It uses the repository-provided `GITHUB_TOKEN`; no additional publishing secrets are required.

The independently versioned Python model-contract package is currently `ai-interfaces-v0.3.0`; its GitHub Release contains the wheel and source distribution.

## Persistence and migration

The stack deliberately uses the historic `ai-infra_labelling_data` and `ai-infra_lakefs_data` volume names so an older local installation can retain its data. MLflow now persists in `ai-infra_mlflow_data`.

Before migrating an existing installation, inspect and back up its volumes. Stop the old stack without `-v`, confirm the volume names in `.env`, and then start this Compose stack. Keep `LAKEFS_AUTH_ENCRYPT_SECRET_KEY` and the lakeFS credentials stable for an existing lakeFS volume.

AI Studio now requires sign-in and enforces MySQL-backed users, teams and repository permissions. Complete [first-owner setup](docs/users-and-repository-access.md) after upgrading. MLflow, TensorBoard, lakeFS and compute-agent endpoints remain separate services; restrict their direct access and use HTTPS for shared deployments.

## Verification

```bash
docker compose config --quiet
curl --fail http://localhost:8081/api/health
curl --fail http://localhost:8002/_health
curl --fail http://localhost:5001/health
curl --fail http://localhost:8090/health
```

Backend and frontend development instructions are in [src/labelling/README.md](src/labelling/README.md).

See [LICENSE](LICENSE).

## Unsupervised anomaly datasets

Choose **Anomaly detection (unsupervised)** when creating a project. Import a folder or image files; there are no classes, annotation completion steps, AI labelling, or annotation reviews. Use **Dataset → Images** to inspect or remove samples (History supports restoration).

Set **Default train split (%)** in Manage, then publish from Dashboard. Publishing freezes the image files and their deterministic train/test assignments (seed 42) so later settings or imports cannot alter that version. The version ZIP and lakeFS snapshot retain each image's `split` (`train` or `test`) in their JSON manifest. The manifest keeps the existing `annotations/*.json` and `images/` archive layout for compatibility, with empty categories and annotations. Live split exports remain available; they use the selected ratio, while published exports retain the frozen split. Empty exports are skipped.

Train a published version using the bundled **Colour distance anomaly baseline**, or an installed `anomaly_detection` workbench. The baseline fits mean RGB features and a score threshold using only training images, then reports held-out anomaly scores and the flagged fraction. Its downloadable JSON artifact contains the centroid, threshold, feature recipe, and configuration. This is a pipeline demo, not a production anomaly detector. With unlabelled test data, the metrics do not claim detection accuracy. Prepare representative normal training data for normality-based models. A zero-sized training partition cannot be trained.

Anomaly jobs use the existing local/remote compute, MLflow tracking, artifact download, model registration, and lineage flows. Custom implementations can use `AnomalyDetectionModel` and `AnomalyModelConfig` from `ai_interfaces` (empty `class_names`). Use the published `ai-interfaces-v0.3.0` contracts or install this checkout with `pip install -e libs/ai_interfaces`. They must respect the frozen `split` on each manifest image; held-out test samples must not enter fitting or threshold calibration.

Run the complete development verification with `tests/.venv/bin/python tools/verify.py` after installing the Python dependencies in tests/requirements.txt and backend/requirements-dev.txt. Set `AUTH_TEST_SETTINGS` to an isolated MySQL database configuration to include identity integration tests; CI supplies one.

## Workflow enhancements in this checkout

New publications freeze supervised fitting/validation/test membership. Training supports capacity-limited agents, cooperative cancellation, parent-linked cloning, reproducibility records and compatible saved-model comparison. Evaluation retains full examples with pagination and filters; anomaly thresholds can be explored without changing saved metrics. Send supervised failures into an assignable review queue and publish a new dataset after corrections.

Use Explore for metadata and duplicate filters, Dashboard for readiness and annotation import mappings, and the image picker for selective import previews with failed-file retry. Training can preview an installed workbench's augmentations with a seed and transformed boxes. Lineage supports search, collapsed stages and ancestry selection; Activity attributes project mutations to users.

See [the enhancement branch stack](docs/enhancement-stack.md), [training details](docs/training-jobs-and-evaluation.md), and [backup/restore](docs/migration.md). These source features are not a new published platform release.
