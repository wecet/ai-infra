# Architecture

```mermaid
flowchart LR
    Browser -->|HTTP 5000| MLflow
    Browser -->|HTTP 8001| lakeFS
    Browser -->|HTTP 8080| Labeller[React + FastAPI labeller]
    lakeFS --> LakeData[(lakeFS local volume)]
    Labeller --> LabelData[(SQLite + images volume)]
    PostgreSQL --> PGData[(PostgreSQL volume)]
```

All containers share one Docker host and network. The labeller, MLflow, and lakeFS publish configurable direct host ports. PostgreSQL remains available for future database integration; neither application is currently configured to consume it. Labeller assets are compiled into its container image.
