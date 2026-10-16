# Migration and persistence

The classic Compose stack uses these default named volumes:

| Service | Volume | Container path |
| --- | --- | --- |
| AI Studio | `ai-infra_labelling_data` | `/data` |
| lakeFS | `ai-infra_lakefs_data` | `/data` |
| Training agent / TensorBoard | `ai-infra_training_runs` | `/training-runs` |
| MLflow | `ai-infra_mlflow_data` | `/mlflow` |

To reuse an existing installation, stop its containers without deleting volumes, set the actual volume names in `.env`, and run `docker compose up --build -d`. Preserve the existing lakeFS encryption key and access credentials. Back up volumes before migration.

The labelling volume must be backed up as a whole: SQLite records reference active images, deleted-image archives, and immutable version snapshots stored alongside the database. Never use `docker compose down -v` when retaining data.

Back up the training-runs volume as well: it contains agent job manifests, uploaded training/evaluation data, progress logs, result artifacts and TensorBoard events. New SQLite migrations add progress, held-out provenance and evaluation records without rewriting annotations. Studio can reconcile recorded jobs against the upgraded agent; interrupted legacy jobs require a new run.

Identity migration adds the `ai-infra_auth_mysql` volume without rewriting SQLite datasets. Configure private MySQL passwords, upgrade Studio, and complete [first-owner setup](users-and-repository-access.md); existing repositories become owned by that first owner. Back up both identity and dataset stores together.
