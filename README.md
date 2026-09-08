# AI Infrastructure (MLOps Platform)

A self-hosted MLOps platform that runs entirely via Docker Compose, providing experiment tracking, data versioning, and image labelling behind a single Nginx reverse proxy.

## Table of Contents

- [Introduction](#introduction)
- [Components](#components)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Image labelling](#image-labelling)
- [Hosts Setup](#hosts-setup)
- [lakeFS CLI Commands](#lakefs-cli-commands)
- [License](#license)

## Introduction

This project provides a ready-to-run MLOps infrastructure stack. It wires together experiment tracking (MLflow), data lake versioning (lakeFS), image labelling (React and Python), and a PostgreSQL database — all routed through an Nginx reverse proxy so each service is accessible via a friendly hostname on port `8088`.

## Components

| Service    | Image                          | Purpose                              | Internal Port |
|------------|--------------------------------|--------------------------------------|---------------|
| PostgreSQL | `postgres:16`                  | Metadata database                    | 5432          |
| MLflow     | `ghcr.io/mlflow/mlflow:latest` | ML experiment tracking & model registry | 5000       |
| lakeFS     | `treeverse/lakefs:latest`      | Git-like data versioning             | 8000          |
| Labelling Studio | Built from `./labelling` | Bounding-box annotation, KPIs & COCO export | 8080 |
| Nginx      | `nginx:alpine`                 | Reverse proxy (routes by hostname)   | 8088 → 80    |

## Prerequisites

Before running this project you will need:

- A Linux machine (Ubuntu recommended)
- `git` to clone the repository
- `sudo` / root access for the bootstrap script

All other dependencies (Docker, AWS CLI, `uv`, `mlflow` CLI, `lakectl`) are installed by the bootstrap script.

## Installation

### 1. Clone the repository

```bash
git clone <repo-url> ai-infra
cd ai-infra
```

### 2. Run the bootstrap script

This installs Docker, the AWS CLI, `uv`, the `mlflow` CLI tool, and `lakectl`:

```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

> **Note:** After bootstrap completes, start a new shell session (or run `newgrp docker`) so the Docker group membership takes effect.

### 3. Create the environment file

Create a `.env` file in the project root with the following variables:

```env
POSTGRES_USER=mlops
POSTGRES_PASSWORD=your_postgres_password
POSTGRES_DB=mlops

LAKEFS_AUTH_ENCRYPT_SECRET_KEY=your_secret_key
```

### 4. Start the platform

```bash
chmod +x start.sh
./start.sh
```

This pulls upstream images, builds Labelling Studio, and starts the stack in detached mode.

## Configuration

Nginx is configured in [nginx/conf.d/mlops.conf](nginx/conf.d/mlops.conf) and routes traffic by `server_name`:

| Hostname                    | Proxied to          |
|-----------------------------|---------------------|
| `mlflow.openiiot.mlops`     | `mlops-mlflow:5000` |
| `lakefs.openiiot.mlops`     | `mlops-lakefs:8000` |
| `labelling.openiiot.mlops` | `mlops-labelling:8080` |

## Usage

Once the stack is running, the services are available at:

| Service   | URL                                    |
|-----------|----------------------------------------|
| MLflow    | http://mlflow.openiiot.mlops:8088      |
| lakeFS    | http://lakefs.openiiot.mlops:8088      |
| Labelling Studio | http://labelling.openiiot.mlops:8088 |

> The hostnames must resolve to your server's IP — see [Hosts Setup](#hosts-setup).

When using <b>lakeFS</b> for the first time; you will be promted to create an account. Upon successful account creation, you will be met by a dashboard showing your 'Access Key' under `LAKEFS_ACCESS_KEY_ID` and 'Secret Key' under `LAKEFS_SECRET_ACCESS_KEY`. These credentials are required to use the `lakectl` CLI tool, so make sure to save them in your `.env` file. Following this, you can create a repository and branch to start versioning your data. For more details on using lakeFS, see the [Commands for lakeFS](#commands-for-lakefs) section below.

lakeFS is also available directly on port `8001` (override with `LAKEFS_PORT` in `.env`). Its internal port remains `8000`. All hostname URLs above require port `8088`.

## Image labelling

Open Labelling Studio to create projects with named classes, import image folders from your computer, and draw bounding boxes. Progress and images persist in the `labelling_data` volume. The KPI page shows completion and class representation, and exports a named ZIP containing train/test COCO JSON files and images using linked split sliders. See the [Labelling Studio guide](labelling/README.md) for the workflow, export layout, and local development.

## Hosts Setup

On every machine that needs to access the platform, add the following entries to `/etc/hosts`:

```bash
sudo nano /etc/hosts
```

```
{YOUR_SERVER_IP}  mlflow.openiiot.mlops
{YOUR_SERVER_IP}  lakefs.openiiot.mlops
{YOUR_SERVER_IP}  labelling.openiiot.mlops
```

Replace `{YOUR_SERVER_IP}` with the actual IP address of your server.

## lakeFS CLI Commands

### Configure lakectl

```bash
lakectl config
```

Enter the credentials you set in your `.env` file when prompted.

### Download data from lakeFS

```bash
lakectl fs download lakefs://{REPOSITORY}/{BRANCH}/ ./{FOLDER} --recursive
```

Example:

```bash
lakectl fs download lakefs://quickstart/main/ ./images --recursive
```

### Upload data to lakeFS

```bash
lakectl fs upload ./{FOLDER} lakefs://{REPOSITORY}/{BRANCH}/ --recursive
```

Example:

```bash
lakectl fs upload lakefs://quickstart/main/samples --source samples --recursive
```

Then commit:

```bash
lakectl commit lakefs://{REPOSITORY}/{BRANCH}/ -m "Commit message"
```

Example:

```bash
lakectl commit lakefs://quickstart/main -m "uploading samples"
```

## License

This software is licensed under a License Agreement. See the [LICENSE](LICENSE) file for details.