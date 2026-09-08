# Migration and persistence

The labeller source moved from `labelling/` to `src/labelling/`. Its API, UI, container paths, and database format are unchanged. Nginx and custom hostnames have been removed. Applications publish direct ports configured by `LABELLING_PORT` (8080), `MLFLOW_PORT` (5001), and `LAKEFS_PORT` (8002). The MLflow and lakeFS defaults avoid ports held by the legacy Compose stack during migration. Remove obsolete hosts-file entries if no longer needed.

## Existing installations

1. Record the running containers' volume mounts with `docker inspect mlops-postgres mlops-lakefs mlops-labelling`. Back up data before handing the deployment to a new manager.
2. Copy your existing root `.env` settings into the chosen profile, especially PostgreSQL credentials and `LAKEFS_AUTH_ENCRYPT_SECRET_KEY`. Keep lakeFS CLI access keys in your CLI configuration. The old `.env` is left on disk but is no longer used by the scripts.
3. Set `POSTGRES_VOLUME`, `LAKEFS_VOLUME`, and `LABELLING_VOLUME` to the actual existing Docker volume names. Defaults match the original `ai-infra` Compose project. A different checkout/project name may have created different names. Missing names create empty volumes; they do not migrate data.
4. Preserve any MLflow tracking data from the existing container before removing it. The previous Compose configuration had no MLflow volume or explicit backend/artifact store; this restructuring preserves that behavior. PostgreSQL credentials alone do not configure MLflow to use PostgreSQL.
5. Stop the old stack without deleting volumes, using `docker compose down` before switching configuration, or `./scripts/compose.sh dev down` after updating profiles. Deploy with the chosen runner.
6. Remove the obsolete Nginx container: for Compose use `./scripts/compose.sh dev up -d --build --remove-orphans`; for Deployment Manager review and apply its removal in the reconciliation plan.
7. Verify existing lakeFS repositories and labelling projects, images, annotations, and exports.

## Storage

| Service | Container path | Profile volume setting |
| --- | --- | --- |
| PostgreSQL | `/var/lib/postgresql/data` | `POSTGRES_VOLUME` |
| lakeFS | `/data` | `LAKEFS_VOLUME` |
| Labeller | `/data` | `LABELLING_VOLUME` |

Stop the consuming service before backing up its entire volume. The labeller requires both its SQLite database and uploaded image files. Restore onto the same target host and set the profile to the restored volume name. Moving `HOST_APP` to another machine does not transfer named-volume data.

Never use `down -v` when retaining data: Compose can delete the configured named volumes. Deployment Manager and Compose share the configured physical volume names, even though their network/container naming differs.
