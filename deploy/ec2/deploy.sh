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

# API runs pip + alembic + uvicorn on start; give it time before health check.
HEALTH_URL="http://127.0.0.1:8000/health"
for attempt in $(seq 1 40); do
  if curl -fsS "$HEALTH_URL"; then
    echo ""
    echo "Health check OK (attempt $attempt)"
    exit 0
  fi
  echo "Waiting for API... ($attempt/40)"
  sleep 3
done
echo "Health check failed after 40 attempts (~2 min)."
exit 1
