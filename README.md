# AI Infrastructure (MLOps Platform)

A self-hosted MLOps platform that runs entirely via Docker Compose, providing experiment tracking, data versioning, and S3-compatible object storage behind a single Nginx reverse proxy.

## Table of Contents

- [Introduction](#introduction)
- [Components](#components)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Hosts Setup](#hosts-setup)
- [lakeFS CLI Commands](#lakefs-cli-commands)
- [License](#license)

## Introduction

This project provides a ready-to-run MLOps infrastructure stack. It wires together experiment tracking (MLflow), data lake versioning (lakeFS), S3-compatible storage (SeaweedFS), and a PostgreSQL database — all routed through an Nginx reverse proxy so each service is accessible via a friendly hostname on port `8088`.

## Components

| Service    | Image                          | Purpose                              | Internal Port |
|------------|--------------------------------|--------------------------------------|---------------|
| PostgreSQL | `postgres:16`                  | Metadata database                    | 5432          |
| SeaweedFS  | `chrislusf/seaweedfs:latest`   | S3-compatible distributed storage    | 8333, 8888, 9333 |
| MLflow     | `ghcr.io/mlflow/mlflow:latest` | ML experiment tracking & model registry | 5000       |
| lakeFS     | `treeverse/lakefs:latest`      | Git-like data versioning             | 8000          |
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

# Optional — defaults to 8333 if not set
SEAWEED_S3_PORT=8333
```

### 4. Start the platform

```bash
chmod +x start.sh
./start.sh
```

This pulls all images and starts the stack in detached mode.

## Configuration

Nginx is configured in [nginx/conf.d/mlops.conf](nginx/conf.d/mlops.conf) and routes traffic by `server_name`:

| Hostname                    | Proxied to          |
|-----------------------------|---------------------|
| `mlflow.openiiot.mlops`     | `mlops-mlflow:5000` |
| `lakefs.openiiot.mlops`     | `mlops-lakefs:8000` |
| `seaweed.openiiot.mlops`    | `mlops-seaweedfs:8888` |

## Usage

Once the stack is running, the services are available at:

| Service   | URL                                    |
|-----------|----------------------------------------|
| MLflow    | http://mlflow.openiiot.mlops:8088      |
| lakeFS    | http://lakefs.openiiot.mlops:8088      |
| SeaweedFS | http://seaweed.openiiot.mlops:8088     |

> The hostnames must resolve to your server's IP — see [Hosts Setup](#hosts-setup).

## Hosts Setup

On every machine that needs to access the platform, add the following entries to `/etc/hosts`:

```bash
sudo nano /etc/hosts
```

```
{YOUR_SERVER_IP}  mlflow.openiiot.mlops
{YOUR_SERVER_IP}  lakefs.openiiot.mlops
{YOUR_SERVER_IP}  seaweed.openiiot.mlops
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