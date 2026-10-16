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

## Offline backup and isolated restore

Run `docker compose stop` and then `python3.11 tools/backup_restore.py backup /absolute/path/new-backup`.
The command refuses running containers and existing backup directories. It archives every configured
named volume, including MySQL identities, Studio images/database/models, lakeFS, MLflow and training logs.
Restart with `docker compose start` after backup. Keep the existing environment and lakeFS keys separately;
the backup intentionally excludes environment secrets. Protect backup files as private application data.

Verify with `python3.11 tools/backup_restore.py verify /absolute/path/new-backup`.
Restore with `python3.11 tools/backup_restore.py restore /absolute/path/new-backup --prefix studio-restore-test`.
Restore validates hashes, safe archive paths, SQLite integrity and live/frozen/model references, then creates
fresh volumes. It refuses existing target volumes. It does not change the active stack or its credentials.
The output maps volume keys to restored names. Use an isolated Compose project with those volume names,
separate ports and the original credentials to perform service health checks before adopting a restore.
Archives reject links, traversal paths and special files before extraction. Restore preserves numeric file ownership for database volumes. Docker backup/restore uses the local Studio image's Python.
