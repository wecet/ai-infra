#!/usr/bin/env bash

set -euo pipefail

echo "Starting MLOps platform..."

docker compose pull --ignore-buildable
docker compose up -d --build

echo ""
echo "Running containers:"
docker compose ps

echo ""
echo "Access URLs:"
echo "MLflow:   http://mlflow.openiiot.mlops:8088"
echo "lakeFS:   http://lakefs.openiiot.mlops:8088"
echo "Labelling: http://labelling.openiiot.mlops:8088"
echo ""
