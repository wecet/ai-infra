#!/usr/bin/env bash

set -euo pipefail

echo "Starting MLOps platform..."

docker compose pull
docker compose up -d

echo ""
echo "Running containers:"
docker compose ps

echo ""
echo "Access URLs:"
echo "MLflow:   http://mlflow.openiiot.mlops:8088"
echo "lakeFS:   http://lakefs.openiiot.mlops:8088"
echo "Seaweed:  http://seaweed.openiiot.mlops:8088"
echo ""