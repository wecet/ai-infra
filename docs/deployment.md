# Docker Compose deployment

Copy `.env.example` to `.env`, replace the development secrets, and start the complete stack:

```bash
docker compose up --build -d
docker compose ps
```

Compose builds the labeller from `src/labelling/Dockerfile`, initializes lakeFS, and starts MLflow. No separately published labeller image is required for a local deployment.

The `lakefs-init` one-shot service creates the lakeFS administrator from `.env` before the server starts. It is safe to keep the same values when restarting an existing installation. The labeller receives the same access key pair and creates its configured repository on the first snapshot publish.

Use `docker compose logs SERVICE` to diagnose startup and `docker compose down` to stop the stack without deleting volumes. Never add `-v` when data must be retained.

For a remote host, copy the repository and a private `.env` to that host and run the same commands there. The labeller and MLflow have no application authentication, so do not publish their ports to an untrusted network without an authenticated proxy or firewall.

Training-agent and TensorBoard services are also part of the stack. Persistent agent jobs and event logs live in the training-runs volume. Upgrade Studio and training-agent together for asynchronous training and saved-model evaluation; remote agents must be upgraded independently. Agent execution is independent of browser requests. Restarting a compute agent interrupts in-process trainers and records a recoverable failure rather than resuming weights.

See [Training jobs and evaluation](training-jobs-and-evaluation.md) and the [documentation index](README.md).
