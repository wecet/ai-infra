# Deploying AI Infrastructure

## Profiles and target hosts

Deployment Manager reads the V1 manifest at the repository root. `sources.project_dir` points to the application source; it does not instruct the manager to build it. Service definitions are self-contained and do not import external deployment templates.

| Profile | Intended use |
| --- | --- |
| `dev.env` | Plaintext local development, default Docker host, locally built labeller image |
| `local_server.nolock.env` | Plaintext remote server template; configure SSH alias, registry, and credentials |
| `prod.env.example` | Production template; not an active profile until configured and encrypted as `prod.env` |

All services use `HOST_APP` and one bridge network. Each application publishes its own configurable host port. `<default>` selects Deployment Manager's configured default Docker host; `ssh://ai-infra-local` requires a working SSH configuration and Docker access.

Set `DEPLOYED_CONFIG_PATH` to an absolute, writable path appropriate to your manager installation. Do not mount a source-code directory on the remote host to run the labeller.

## Build and publish the labeller

Create `gpt.env` at the repository root from `gpt.env.example` before deploying. Leave `OPENAI_API_KEY` empty for manual-only labelling, or fill in the key and desired image-capable model for AI assistance. Deployment Manager synchronizes this ignored file and mounts it read-only into the backend; do not include it in the Docker image. See [AI-assisted labelling](../src/labelling/README.md#ai-assisted-labelling) for all settings.

Use a registry and immutable release tag available to your deployment host:

```bash
docker build -t registry.example.com/ai-infra/labelling:v1.0.0 src/labelling
docker login registry.example.com
docker push registry.example.com/ai-infra/labelling:v1.0.0
```

Set `LABELLING_IMAGE` to that exact image in the selected profile. For local Deployment Manager use, build the `ai-infra/labelling:dev` tag directly. A remote host needs a registry image or an explicitly loaded image. Build for the target CPU architecture.

## Apply the deployment

1. Update the explicit metadata in `deployment.yaml` for the client, site, and environment. Manifest metadata does not change with profile selection.
2. Configure the profile's host, images, credentials, ports and volume names. Pin upstream images to tested versions or digests for production; shipped upstream tags preserve the previous stack defaults.
3. For production, configure a SOPS policy with your own recipients, fill `prod.env.example`, and encrypt the result into `profiles/prod.env`. Do not copy another project's recipients or commit plaintext secrets. Deployment Manager treats profiles other than `dev`, `*.dev`, and `*.nolock` as encrypted.
4. Open the repository in Deployment Manager, select the profile, inspect the rendered desired state and reconciliation plan, then deploy. Stop any previous stack first when using the same ports or volumes.
5. Verify the service URLs and labeller health at `http://localhost:8080/api/health` (adjust the host and `LABELLING_PORT` as needed). In the labeller, verify that the repository homepage loads, **Import Project** prompts for a name, and **Dashboard**, **Review**, **History**, and **Settings** open. For a disposable sample, verify that deleting an image creates an archived preview in History and that restoring it creates an **Images Restored** entry. Initialize lakeFS in its UI and save the generated access credentials for `lakectl config`.

Disabling a service with `DISABLED_SERVICES` requires reviewing its dependent services too.
