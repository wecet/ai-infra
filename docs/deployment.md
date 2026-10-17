# Docker Compose deployment

Copy `.env.example` to `.env`, replace the development secrets, and start the complete stack:

```bash
docker compose up --build -d
docker compose ps
```

Compose builds the labeller from `src/labelling/Dockerfile`, initializes lakeFS, and starts MLflow. No separately published labeller image is required for a local deployment.

The `lakefs-init` one-shot service creates the lakeFS administrator from `.env` before the server starts. It is safe to keep the same values when restarting an existing installation. The labeller receives the same access key pair and creates its configured repository on the first snapshot publish.

Use `docker compose logs SERVICE` to diagnose startup and `docker compose down` to stop the stack without deleting volumes. Never add `-v` when data must be retained.

For a remote host, copy the repository and a private `.env` to that host and run the same commands there. Studio requires sign-in; complete [first-owner setup](users-and-repository-access.md) and enable secure cookies behind HTTPS. MLflow, TensorBoard and agent endpoints need separate network/access controls.

Training-agent and TensorBoard services are also part of the stack. Persistent agent jobs and event logs live in the training-runs volume. Upgrade Studio and training-agent together for asynchronous training and saved-model evaluation; remote agents must be upgraded independently. Agent execution is independent of browser requests. Restarting a compute agent interrupts in-process trainers and records a recoverable failure rather than resuming weights.

See [Training jobs and evaluation](training-jobs-and-evaluation.md) and the [documentation index](README.md).

MySQL now persists Studio identity/access data in `ai-infra_auth_mysql`. Set both `AUTH_MYSQL_PASSWORD` and `AUTH_MYSQL_ROOT_PASSWORD` before starting Compose. MySQL has no published host port. Upgrade instructions and first-owner setup are in [Users and repository access](users-and-repository-access.md).

## RAM use on local machines

The default stack has explicit per-container memory and memory+swap ceilings. Studio is limited to 512 MiB, MySQL to 512 MiB, lakeFS to 512 MiB, MLflow to 768 MiB, TensorBoard to 384 MiB, and the compute agent (including model workers) to 2 GiB. The combined ceilings are 4.625 GiB; idle usage should be substantially lower. Docker Desktop's VM allocation is shared with other projects and may include filesystem cache, so its host RAM figure can exceed the sum of `docker stats` working sets.

MLflow runs one HTTP worker with its separate GenAI/job-execution consumer pools disabled. Studio uses the compute agent for training. MySQL uses a 64 MiB InnoDB buffer pool, 40 maximum connections and disabled performance-schema instrumentation; increase these values for a larger team. TensorBoard retains bounded in-memory samples and reloads every 15 seconds; the original event files stay on disk.

Model training and evaluation run in fresh subprocesses. Their framework imports, model tensors and allocator caches are released when the worker exits. The API process owns durable job state and progress; cancellation terminates the model process group even when the trainer is silent. The legacy synchronous endpoint uses the same bounded queue and isolated workers. Model discovery is serialized and cached for five minutes to avoid concurrent heavy imports; restart the agent to refresh a newly installed workbench immediately. `TRAINING_WORKBENCH_INSPECTION_TIMEOUT` defaults to 30 seconds per workbench for cold framework imports on Docker Desktop.

For a larger model, set `TRAINING_MEMORY_LIMIT=4g` (or an appropriate budget) in `.env` before recreating the agent. Its limit includes the API, discovery/preview processes, and all concurrent training/evaluation workers. Keep `TRAINING_MAX_CONCURRENT_JOBS=1` on memory-constrained hosts. A memory-limit kill fails the affected job; it cannot make an oversized model fit. `TRAINING_CPU_THREADS` defaults to 2 to bound CPU-library thread pools and their working memory.

All memory ceilings, `MLFLOW_WORKERS`, `MYSQL_BUFFER_POOL_SIZE`, `MYSQL_PERFORMANCE_SCHEMA`, `MYSQL_MAX_CONNECTIONS`, `TRAINING_CPU_THREADS`, `TRAINING_WORKBENCH_CACHE_SECONDS` and `TENSORBOARD_SAMPLES_PER_PLUGIN` are configurable in `.env.example`. The Go runtime's `LAKEFS_GO_MEMORY_LIMIT` is a soft heap target below the lakeFS container's hard ceiling. Memory+swap is capped at the same value as RAM to avoid sustained host swapping.

Apply changes with `docker compose up -d --build` while no training job is active. Check usage with `docker stats --no-stream` and service health with `docker compose ps`. Published-version exports and lakeFS uploads stream image files from disk; they no longer materialize the full dataset in Studio's heap.

Measured on this Docker Desktop stack on 17 October 2026: idle MLflow fell from about 1.76 GiB to 310 MiB, and MySQL from 430 MiB to about 185 MiB. All six services remained healthy and MLflow experiment/metric logging passed. Synthetic PyTorch training and held-out evaluation, legacy synchronous training, and cancellation passed through the deployed agent. The sampled PyTorch workload peaked near 265 MiB while the API process stayed near 48 MiB RSS and did not load PyTorch libraries. These small-demo figures are verification results, not memory estimates for larger models.

The regression run passed 102 tests plus classification/detection training smoke workflows, frontend static checks/build and Compose validation. One isolated-MySQL integration test was skipped; the live identity database connection and tuned MySQL settings were checked separately.
