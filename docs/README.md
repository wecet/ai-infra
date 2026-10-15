# AI Studio documentation

The guides below describe the current checkout. Published container and interface releases may lag behind it. Roadmap documents are proposals, not shipped functionality or delivery commitments.

## Using and operating the platform

| Guide | Purpose |
| --- | --- |
| [Users and repository access](users-and-repository-access.md) | First-owner setup, MySQL identities, teams, roles and project grants |
| [Platform overview](platform-overview.md) | Current capabilities, data flow, and known limits |
| [Studio workflow](../src/labelling/README.md) | Projects, imports, labelling, anomaly datasets, versions, and training |
| [Training jobs and evaluation](training-jobs-and-evaluation.md) | Background job ownership, progress, recovery and held-out model evaluation |
| [Model interfaces](../libs/ai_interfaces/README.md) | Workbench discovery, Pydantic configuration, training, and inference contracts |
| [Workspace authoring](workspace-authoring.md) | Directory layout and config, model, training and inference examples |
| [PyTorch demos](../tests/README.md) | Classification and detection demos, augmentations, callbacks, and smoke checks |
| [Deployment](deployment.md) | Local stack and remote compute |
| [Environment variables](configurable-variables.md) | Supported configuration groups |
| [Migration and persistence](migration.md) | Volumes, backups, and retained data |
| [lakeFS commands](lakefs-commands.md) | Dataset storage operations |

## Brainstorm and proposed direction

| Document | Purpose |
| --- | --- |
| [Product roadmap](roadmap.md) | Priorities, dependencies, effort estimates, and completion criteria |
| [UI/UX proposals](ui-ux-roadmap.md) | Page-level improvements and an accessibility review plan |
| [Project family expansion](project-families.md) | Proposed Vision, LLM/VLM, and Language workflows and contract evolution |

Start with the roadmap's first three increments. Implement one complete user workflow at a time, then reassess the backlog against real usage.

## Obsidian knowledge graph

Run `python3 tools/export_obsidian.py` from the repository root to export all project documentation into the `AI Studio` folder of your Obsidian vault. Edit the script's `CONFIG` dictionary if your vault path differs. The export includes 16 source guides, linked concept notes and topic maps, with tags and source-revision metadata. Markdown links between guides become Obsidian wikilinks; code links point to the source revision on GitHub.

Start at **AI Studio** in Obsidian. Search `tag:ai-infra`, use Backlinks/Local graph on a concept, or filter Graph view with `path:"AI Studio"`. Repository docs remain authoritative. Refreshes stop if a generated note has personal edits, so keep your commentary in separate linked notes. Existing vault notes and settings are left untouched.
