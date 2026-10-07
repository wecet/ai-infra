# AI Infrastructure

A self-hosted Docker Compose stack containing:

- **Labelling Studio** — image classification and object-detection annotation
- **lakeFS** — versioned dataset storage used by published labelling snapshots
- **MLflow** - experiment and artifact tracking
- **Training agent** - CPU/GPU model execution, deployable locally or on a remote host

The labeller supports project ZIP import/export, managed classes, AI-assisted box suggestions, review workflows, immutable versions, lakeFS publishing, dataset lineage, version comparison, dataset quality checks, deletion recovery, comments, train/test exports, and version-bound training jobs. See the [labelling guide](src/labelling/README.md) for the complete workflow.

## Quick start

Docker with the Compose plugin is the only deployment prerequisite.

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
| Labelling Studio | http://localhost:8081 |
| lakeFS | http://localhost:8002 |
| MLflow | http://localhost:5001 |
| Training agent | http://localhost:8090 |

The labeller uses host port `8081` because `8080` was already occupied on the machine where this stack was configured. Change `LABELLING_PORT`, `LAKEFS_PORT`, or `MLFLOW_PORT` in `.env` if a port is unavailable, then recreate the services with `docker compose up -d`.

lakeFS is initialized automatically from the `LAKEFS_*` values in `.env`. Log in with `LAKEFS_ACCESS_KEY_ID` and `LAKEFS_SECRET_ACCESS_KEY`. The `datasets` repository is created automatically the first time a labelling version is pushed. MLflow stores both its SQLite database and artifacts in a named volume. The bundled training agent always supports CPU; its GPU option is disabled unless it detects an exposed GPU runtime.

## Model training

Publish an immutable dataset from the Dashboard, then open the project's **Training** tab. Choose the version, installed base model, hyperparameters, and compute target. For remote compute, run the training-agent image on another machine, expose port `8090`, enter its IP and port, and test the connection before starting the job.

The bundled models are lightweight baseline trainers: a colour-centroid classifier and a class box-prior detector. They exercise the complete job, artifact, and MLflow path without downloading a heavyweight framework. Production PyTorch, TensorFlow, or ONNX packages plug into the public contracts in [`libs/ai_interfaces`](libs/ai_interfaces/README.md).

The project **Lineage** tab traces imports, deletion/restoration events, published versions, lakeFS commits, training runs, registered models, and deployments. The **Compare** tab audits any two published versions, including membership, annotations, classes, deterministic train/test assignment, review status, quality metrics, duplicates, and split leakage.

Install those contracts in another workspace from a release tag:

```bash
pip install "ai-infra-interfaces @ git+https://github.com/wecet/ai-infra.git@v1.0.0#subdirectory=libs/ai_interfaces"
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

Pushing a semantic version tag such as `v1.0.0`, or manually running **Publish labeller release** with a version, publishes a multi-platform labeller image to `ghcr.io/wecet/ai-infra/labelling`. The workflow also creates a GitHub Release containing a Linux AMD64 OCI image archive and the Compose/environment templates. It uses the repository-provided `GITHUB_TOKEN`; no additional publishing secrets are required.

## Persistence and migration

The stack deliberately uses the historic `ai-infra_labelling_data` and `ai-infra_lakefs_data` volume names so an older local installation can retain its data. MLflow now persists in `ai-infra_mlflow_data`.

Before migrating an existing installation, inspect and back up its volumes. Stop the old stack without `-v`, confirm the volume names in `.env`, and then start this Compose stack. Keep `LAKEFS_AUTH_ENCRYPT_SECRET_KEY` and the lakeFS credentials stable for an existing lakeFS volume.

The services are intended for a trusted network: the labeller has no login and MLflow runs with its security middleware disabled. Add a secured reverse proxy or equivalent access control before public exposure.

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
