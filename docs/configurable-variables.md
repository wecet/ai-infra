# Environment variables

Docker Compose loads the repository-root `.env`. The committed `.env.example` documents every supported value.

| Group | Variables |
| --- | --- |
| Images | `LABELLING_IMAGE`, `LAKEFS_IMAGE`, `MLFLOW_IMAGE` |
| Published ports | `LABELLING_PORT`, `LAKEFS_PORT`, `MLFLOW_PORT` |
| Storage | `LABELLING_VOLUME`, `LAKEFS_VOLUME`, `MLFLOW_VOLUME` |
| lakeFS identity | `LAKEFS_USER_NAME`, `LAKEFS_ACCESS_KEY_ID`, `LAKEFS_SECRET_ACCESS_KEY`, `LAKEFS_AUTH_ENCRYPT_SECRET_KEY` |
| lakeFS publishing | `LAKEFS_REPOSITORY`, `LAKEFS_BRANCH`, `LAKEFS_STORAGE_NAMESPACE` |
| AI assistance | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_OUTPUT_TOKENS`, `OPENAI_IMAGE_DETAIL`, `OPENAI_PROJECT`, `OPENAI_ORGANIZATION`, `OPENAI_REASONING_EFFORT` |
| Operations | `COMPOSE_PROJECT_NAME`, `NETWORK_NAME`, `LOG_MAX_SIZE`, `LOG_MAX_FILE` |

Keep `.env` private. Preserve the lakeFS encryption key and credentials when reusing an existing lakeFS volume. Leave `OPENAI_API_KEY` empty when AI assistance is not required.
