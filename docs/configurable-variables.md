# Configurable variables

Every active profile must supply the variables referenced by `services/`. Deployment Manager resolves `~~ENV:NAME~~` markers in service definitions. Do not put these markers in `deployment.yaml`.

| Variable | Purpose / default |
| --- | --- |
| `HOST_APP` | Deployment Manager Docker host key; `<default>` locally, SSH URL remotely |
| `DEPLOYED_CONFIG_PATH` | Absolute manager-managed configuration directory; required for non-dev profiles |
| `DISABLED_SERVICES` | Manager service filtering; empty enables all services |
| `NETWORK_NAME` | Manager bridge network name; default `ai-infra-network` |
| `MLFLOW_IMAGE` | Tracking image, initially `ghcr.io/mlflow/mlflow:latest` |
| `LAKEFS_IMAGE` | Versioning image, initially `treeverse/lakefs:latest` |
| `LABELLING_IMAGE` | Built/published labeller image; local default `ai-infra/labelling:dev` |
| `LAKEFS_AUTH_ENCRYPT_SECRET_KEY` | lakeFS encryption secret; replace development value and preserve for existing installations |
| `LABELLING_PORT` | Published labeller port, `8080` (container port stays 8080) |
| `MLFLOW_PORT` | Published tracking port, `5001` (container port stays 5000) |
| `LAKEFS_PORT` | Published lakeFS port, `8002` (container port stays 8000) |
| `LAKEFS_VOLUME` | Physical Docker volume name, `ai-infra_lakefs_data` |
| `LABELLING_VOLUME` | Physical Docker volume name, `ai-infra_labelling_data` |
| `LOG_MAX_SIZE` | Manager JSON log rotation size, `10m` |
| `LOG_MAX_FILE` | Manager retained log-file count, `3` |

Access each application at `http://localhost:PORT`, or use the Docker server IP remotely. Use distinct published ports in the range 1–65535.

The labeller's `LABELLING_DATA_DIR=/data`, lakeFS local storage settings, and MLflow command are defined in service YAML. The labeller volume holds SQLite, active images, deleted-image archives, and copied images for immutable published versions. For native development, override `LABELLING_DATA_DIR` with a writable local path. See [the labeller guide](../src/labelling/README.md).

When adding a setting, update every profile/template, the relevant service definition, and this table together. Keep private plaintext credentials out of Git; production profiles should be encrypted with your own SOPS policy.
