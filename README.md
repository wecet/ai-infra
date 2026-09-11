# AI Infrastructure

A self-hosted MLflow, lakeFS, and image labelling stack, with PostgreSQL, deployed through Deployment Manager.

The labeller supports object detection, multi-label image classification, optional AI-generated box suggestions, importable project ZIPs, drag-to-merge projects, auditable image additions, restorable deletions, approval-based annotation review, automated dataset quality checks, project settings, near-duplicate analysis, and timestamped project comments. Its Dashboard displays the project description and exports separate import-compatible train and test archives, skipping empty splits. Configure the ignored `gpt.env` for AI assistance; a blank API key keeps manual labelling available. See the [labelling guide](src/labelling/README.md).

## Repository layout

```text
deployment.yaml             Deployment Manager V1 manifest
profiles/                   Deployment environment settings
services/ai-infra/          One Deployment Manager definition per service
src/labelling/              Labeller Dockerfile, React UI, FastAPI API, tests
docs/                       Deployment, configuration, and migration guides
```

## Deployment

Open this repository in Deployment Manager and select the appropriate profile. Use `dev` for the manager's default local Docker host, or `local_server.nolock` for the configured remote host. Review the rendered desired state and reconciliation plan, then deploy.

Access the deployed services directly:

| Service | Default URL | Profile variable |
| --- | --- | --- |
| Labelling | http://localhost:8080 | `LABELLING_PORT` |
| MLflow | http://localhost:5001 | `MLFLOW_PORT` |
| lakeFS | http://localhost:8002 | `LAKEFS_PORT` |

Change the ports in the selected profile and redeploy. For a remote Docker host, replace `localhost` with the server IP. The manager reads `deployment.yaml`, `profiles/`, and `services/`; application images must already be available to the target Docker host.

- [Deployment and image publishing](docs/deployment.md)
- [Profile variables](docs/configurable-variables.md)
- [Migration and persistence](docs/migration.md)
- [Labelling workflow and development](src/labelling/README.md)
- [lakeFS CLI examples](docs/lakefs-commands.md)

The current stack uses lakeFS local storage. PostgreSQL is retained for compatibility but neither lakeFS nor MLflow currently connects to it. MLflow retains its existing default storage behavior; its container filesystem has no persistent volume. See the migration guide before replacing containers with valuable tracking data.

The services retain their existing trusted-network deployment model: the labeller has no authentication and MLflow runs with security middleware disabled. Production profiles require appropriate network/access controls.

See [LICENSE](LICENSE).
