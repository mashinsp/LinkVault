#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "Deploying LinkVault from: $ROOT_DIR"

# Build sequentially to reduce memory spikes on small EC2 instances.
docker compose build api
docker compose build worker

# Bring up only core services by default (observability is profile-gated).
docker compose up -d --remove-orphans api worker db redis rabbitmq

echo "Core services status:"
docker compose ps

curl -fsS http://localhost:8000/health
