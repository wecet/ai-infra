# Migration and persistence

The labeller source moved from `labelling/` to `src/labelling/`. Its container data path remains `/data`. Startup applies additive SQLite migrations for project types, whole-image labels, import batches, annotation revisions, perceptual hashes, project comments, project settings, and review metadata while retaining existing projects and annotations. Existing completed images enter **Ready for Review**. Nginx and custom hostnames have been removed. Applications publish direct ports configured by `LABELLING_PORT` (8080), `MLFLOW_PORT` (5001), and `LAKEFS_PORT` (8002). The MLflow and lakeFS defaults avoid ports held by the legacy Compose stack during migration. Remove obsolete hosts-file entries if no longer needed.

## Existing installations

1. Record the running containers' volume mounts with `docker inspect mlops-postgres mlops-lakefs mlops-labelling`. Back up data before handing the deployment to a new manager.
2. Copy settings from an older installation's root `.env` into the chosen profile, especially PostgreSQL credentials and `LAKEFS_AUTH_ENCRYPT_SECRET_KEY`. Keep lakeFS CLI access keys in your CLI configuration. This repository no longer uses a root `.env`.
3. Set `POSTGRES_VOLUME`, `LAKEFS_VOLUME`, and `LABELLING_VOLUME` to the actual existing Docker volume names. Defaults match the original `ai-infra` Compose project. A different checkout/project name may have created different names. Missing names create empty volumes; they do not migrate data.
4. Preserve any MLflow tracking data from the existing container before removing it. The previous Compose configuration had no MLflow volume or explicit backend/artifact store; this restructuring preserves that behavior. PostgreSQL credentials alone do not configure MLflow to use PostgreSQL.
5. Stop the old stack from its original checkout without deleting volumes, using `docker compose down`, before switching control to Deployment Manager.
6. Review the Deployment Manager reconciliation plan and apply removal of the obsolete Nginx container.
7. Verify existing lakeFS repositories and labelling projects, images, annotations, History entries, Dashboard comments, Review states, Settings, quality checks, and paired train/test exports. Existing labelling images are assigned to the migrated project's initial **Project Created** history entry. Images deleted after this upgrade are archived and can be previewed and restored from History. Historic deletion entries created before archive support retain their source paths but cannot recover files that were already removed.

## Storage

| Service | Container path | Profile volume setting |
| --- | --- | --- |
| PostgreSQL | `/var/lib/postgresql/data` | `POSTGRES_VOLUME` |
| lakeFS | `/data` | `LAKEFS_VOLUME` |
| Labeller | `/data` | `LABELLING_VOLUME` |

Stop the consuming service before backing up its entire volume. The labeller requires its SQLite database, active images under `/data/images`, and restorable deleted-image archives under `/data/deleted`; the database includes annotations, review state, revision history, dataset history, project settings, and comments. Backing up only SQLite produces deletion records whose archived previews cannot be restored. Restore onto the same target host and set the profile to the restored volume name. Moving `HOST_APP` to another machine does not transfer named-volume data.

Never use `down -v` when retaining data: Compose can delete the configured named volumes. Deployment Manager and Compose share the configured physical volume names, even though their network/container naming differs.
