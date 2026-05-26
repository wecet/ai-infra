#!/usr/bin/env bash

set -euo pipefail

echo "Installing base dependencies..."

sudo apt-get update
sudo apt-get install -y \
  ca-certificates \
  curl \
  wget \
  unzip \
  git \
  gnupg \
  lsb-release \
  python3 \
  python3-pip

echo "Installing Docker..."

if ! command -v docker >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings

  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

  sudo chmod a+r /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

  sudo apt-get update

  sudo apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

  sudo usermod -aG docker "$USER"
fi

echo "Installing AWS CLI..."

if ! command -v aws >/dev/null 2>&1; then
  curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
  unzip -q awscliv2.zip
  sudo ./aws/install
  rm -rf aws awscliv2.zip
fi

echo "Installing uv..."

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"

  if ! grep -q '.local/bin' "$HOME/.bashrc"; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
  fi
fi

echo "Installing Python CLI tools..."

export PATH="$HOME/.local/bin:$PATH"

uv tool install mlflow || uv tool upgrade mlflow

echo "Installing lakeFS + lakectl..."

if ! command -v lakectl >/dev/null 2>&1; then
  LAKEFS_VERSION="1.81.1"

  wget \
    "https://github.com/treeverse/lakeFS/releases/download/v${LAKEFS_VERSION}/lakeFS_${LAKEFS_VERSION}_Linux_x86_64.tar.gz"

  tar -zxvf "lakeFS_${LAKEFS_VERSION}_Linux_x86_64.tar.gz"

  chmod +x lakectl lakefs

  sudo mv lakectl lakefs /usr/bin

  rm -f "lakeFS_${LAKEFS_VERSION}_Linux_x86_64.tar.gz"
fi

echo "Verifying installation..."

docker --version
docker compose version
aws --version
uv --version
mlflow --version || true
lakectl --version || true

echo ""
echo "Bootstrap complete."
echo "Log out and back in, or run: newgrp docker"