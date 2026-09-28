# lakeFS commands

lakeFS is available at `http://localhost:8002` by default. Use the access key and secret from `.env`.

Configure `lakectl` interactively:

```bash
lakectl config
```

Download or upload data and commit it:

```bash
lakectl fs download lakefs://datasets/main/ ./images --recursive
lakectl fs upload lakefs://datasets/main/samples --source samples --recursive
lakectl commit lakefs://datasets/main -m "Upload samples"
```

The Labelling Studio creates the configured repository automatically when its first immutable version is pushed to lakeFS.
