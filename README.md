# AI Infrastructure

A self-hosted MLflow, lakeFS, and image labelling stack, with PostgreSQL. Deploy through Deployment Manager or run locally with Docker Compose.

## Repository layout

```text
deployment.yaml             Deployment Manager V1 manifest
profiles/                   Deployment environment settings
services/platform/          One Deployment Manager definition per service
src/labelling/              Labeller Dockerfile, React UI, FastAPI API, tests
docs/                       Deployment, configuration, and migration guides
design/                     Architecture
scripts/compose.sh          Compose wrapper with explicit profile selection
```

## Local start

Install Docker Engine and Compose. The optional Ubuntu `./bootstrap.sh` also installs the MLflow and lakeFS CLI tools.

Review `profiles/dev.env`, then run:

```bash
./start.sh dev
```

Access the services directly:

| Service | Default URL | Profile variable |
| --- | --- | --- |
| Labelling | http://localhost:8080 | `LABELLING_PORT` |
| MLflow | http://localhost:5000 | `MLFLOW_PORT` |
| lakeFS | http://localhost:8001 | `LAKEFS_PORT` |

Change the ports in the selected profile and restart the stack. For a remote Docker host, replace `localhost` with the server IP. No custom domains or hosts-file entries are required.

```bash
./scripts/compose.sh dev ps
./scripts/compose.sh dev logs -f labelling
./scripts/compose.sh dev down
```

Configuration lives in `profiles/`. The scripts explicitly select a profile; the old root `.env` is no longer loaded. Shell environment overrides still follow Compose precedence.

## Deployment Manager

Open this repository as a deployment project and select `dev` or `local_server.nolock`. Configure the target host and image references before deploying. The manager reads `deployment.yaml` and `services/`; application images must already be available to the target Docker host.

- [Deployment and image publishing](docs/deployment.md)
- [Profile variables](docs/configurable-variables.md)
- [Migration and persistence](docs/migration.md)
- [Labelling workflow and development](src/labelling/README.md)
- [Architecture](design/README.md)
- [lakeFS CLI examples](commands.md)

The current stack uses lakeFS local storage. PostgreSQL is retained for compatibility but neither lakeFS nor MLflow currently connects to it. MLflow retains its existing default storage behavior; its container filesystem has no persistent volume. See the migration guide before replacing containers with valuable tracking data.

The services retain their existing trusted-network deployment model: the labeller has no authentication and MLflow runs with security middleware disabled. Production profiles require appropriate network/access controls.

See [LICENSE](LICENSE).
