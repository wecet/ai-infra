# Configurable variables

Every active profile must supply the variables referenced by `services/`. Deployment Manager uses `~~ENV:NAME~~`; Compose uses `${NAME}`. Do not put Deployment Manager markers in `deployment.yaml`.

| Variable | Purpose / default |
| --- | --- |
| `HOST_APP` | Deployment Manager Docker host key; `<default>` locally, SSH URL remotely |
| `DEPLOYED_CONFIG_PATH` | Absolute manager-managed configuration directory; required for non-dev profiles |
| `DISABLED_SERVICES` | Manager service filtering; empty enables all services; does not affect Compose |
| `NETWORK_NAME` | Manager bridge network name; default `ai-infra-network`; Compose uses its own default network |
| `POSTGRES_IMAGE` | PostgreSQL image, initially `postgres:16` |
| `MLFLOW_IMAGE` | Tracking image, initially `ghcr.io/mlflow/mlflow:latest` |
| `LAKEFS_IMAGE` | Versioning image, initially `treeverse/lakefs:latest` |
| `LABELLING_IMAGE` | Built/published labeller image; local default `ai-infra/labelling:dev` |
| `POSTGRES_USER` | Initial database username, `mlops` |
| `POSTGRES_PASSWORD` | Initial database password; replace development value |
| `POSTGRES_DB` | Initial database name, `mlops` |
| `LAKEFS_AUTH_ENCRYPT_SECRET_KEY` | lakeFS encryption secret; replace development value and preserve for existing installations |
| `LABELLING_PORT` | Published labeller port, `8080` (container port stays 8080) |
| `MLFLOW_PORT` | Published tracking port, `5000` |
| `LAKEFS_PORT` | Published lakeFS port, `8001` (container port stays 8000) |
| `POSTGRES_VOLUME` | Physical Docker volume name, `ai-infra_postgres_data` |
| `LAKEFS_VOLUME` | Physical Docker volume name, `ai-infra_lakefs_data` |
| `LABELLING_VOLUME` | Physical Docker volume name, `ai-infra_labelling_data` |
| `LOG_MAX_SIZE` | Manager JSON log rotation size, `10m` |
| `LOG_MAX_FILE` | Manager retained log-file count, `3` |

Access each application at `http://localhost:PORT`, or use the Docker server IP remotely. Use distinct published ports in the range 1–65535. PostgreSQL initialization variables only initialize an empty database volume; changing the profile does not update existing database users/passwords.

The labeller's `LABELLING_DATA_DIR=/data`, lakeFS local storage settings, and MLflow command are defined in service YAML. For native labeller development, override `LABELLING_DATA_DIR` with a writable local path. See [the labeller guide](../src/labelling/README.md).

When adding a setting, update every profile/template, service definition, Compose configuration where applicable, and this table together. Keep private plaintext credentials out of Git; production profiles should be encrypted with your own SOPS policy.
