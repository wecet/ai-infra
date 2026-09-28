# Migration and persistence

The classic Compose stack uses these default named volumes:

| Service | Volume | Container path |
| --- | --- | --- |
| Labelling Studio | `ai-infra_labelling_data` | `/data` |
| lakeFS | `ai-infra_lakefs_data` | `/data` |
| MLflow | `ai-infra_mlflow_data` | `/mlflow` |

To reuse an existing installation, stop its containers without deleting volumes, set the actual volume names in `.env`, and run `docker compose up --build -d`. Preserve the existing lakeFS encryption key and access credentials. Back up volumes before migration.

The labelling volume must be backed up as a whole: SQLite records reference active images, deleted-image archives, and immutable version snapshots stored alongside the database. Never use `docker compose down -v` when retaining data.
