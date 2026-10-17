# Environment variables

Docker Compose loads the repository-root `.env`. The committed `.env.example` documents every supported value.

| Group | Variables |
| --- | --- |
| Images | `LABELLING_IMAGE`, `LAKEFS_IMAGE`, `MLFLOW_IMAGE`, `TRAINING_AGENT_IMAGE` |
| Published ports | `LABELLING_PORT`, `LAKEFS_PORT`, `MLFLOW_PORT`, `TRAINING_AGENT_PORT`, `TENSORBOARD_PORT` |
| Storage | `LABELLING_VOLUME`, `LAKEFS_VOLUME`, `MLFLOW_VOLUME`, `TRAINING_RUNS_VOLUME` |
| lakeFS identity | `LAKEFS_USER_NAME`, `LAKEFS_ACCESS_KEY_ID`, `LAKEFS_SECRET_ACCESS_KEY`, `LAKEFS_AUTH_ENCRYPT_SECRET_KEY` |
| lakeFS publishing | `LAKEFS_REPOSITORY`, `LAKEFS_BRANCH`, `LAKEFS_STORAGE_NAMESPACE` |
| AI assistance | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_OUTPUT_TOKENS`, `OPENAI_IMAGE_DETAIL`, `OPENAI_PROJECT`, `OPENAI_ORGANIZATION`, `OPENAI_REASONING_EFFORT` |
| Compute / model discovery | `TRAINING_GPU_AVAILABLE`, `TRAINING_WORKSPACES_PATH` |
| Memory budgets | `LABELLING_MEMORY_LIMIT`, `MYSQL_MEMORY_LIMIT`, `TRAINING_MEMORY_LIMIT`, `TENSORBOARD_MEMORY_LIMIT`, `LAKEFS_MEMORY_LIMIT`, `LAKEFS_GO_MEMORY_LIMIT`, `MLFLOW_MEMORY_LIMIT` |
| Memory tuning | `MLFLOW_WORKERS`, `MYSQL_BUFFER_POOL_SIZE`, `MYSQL_PERFORMANCE_SCHEMA`, `MYSQL_MAX_CONNECTIONS`, `TRAINING_CPU_THREADS`, `TRAINING_WORKBENCH_CACHE_SECONDS`, `TRAINING_WORKBENCH_INSPECTION_TIMEOUT`, `TRAINING_CAPABILITIES_TIMEOUT`, `TENSORBOARD_SAMPLES_PER_PLUGIN` |
| Operations | `COMPOSE_PROJECT_NAME`, `NETWORK_NAME`, `LOG_MAX_SIZE`, `LOG_MAX_FILE` |

Keep `.env` private. Preserve the lakeFS encryption key and credentials when reusing an existing lakeFS volume. Leave `OPENAI_API_KEY` empty when AI assistance is not required.

Compute-agent runtime paths (`TRAINING_WORKSPACES_ROOT`, `TRAINING_RUNS_ROOT`) and service URLs are passed by Compose. Standalone/remote agents can set `TENSORBOARD_PUBLIC_URL` to their reachable dashboard URL. Persistent job files use `TRAINING_RUNS_ROOT/.jobs`; keep that storage across agent recreation.

## Users and repository permissions

`AUTH_MYSQL_DATABASE`, `AUTH_MYSQL_USER`, `AUTH_MYSQL_PASSWORD`, `AUTH_MYSQL_ROOT_PASSWORD`, `AUTH_MYSQL_VOLUME` and `AUTH_COOKIE_SECURE` configure the new MySQL identity service. Password values are required; use unique random values. Native backends also accept `AUTH_MYSQL_HOST` and `AUTH_MYSQL_PORT`. See [Users and repository access](users-and-repository-access.md) for defaults, secure cookies and initialization.
