#!/usr/bin/env bash
# Run on the VM from /opt/unpack.   ./deploy.sh            -> deploy the image in .env (UNPACK_IMAGE)
#                                   ./deploy.sh <git-sha>  -> deploy that tag from UNPACK_REGISTRY
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo ".env missing (copy .env.prod.example)"; exit 1; }
[ -f secrets/app.pem ] || echo "warning: secrets/app.pem missing; GitHub App features will be off"
mkdir -p data secrets

if [ $# -ge 1 ]; then
  registry=$(grep -E '^UNPACK_REGISTRY=' .env | cut -d= -f2-)
  export UNPACK_IMAGE="${registry}/server:$1"
fi

compose="docker compose -f docker-compose.prod.yml"
$compose pull migrate api worker
$compose up -d --remove-orphans
$compose ps
sleep 5
curl -fsS http://127.0.0.1:8000/readyz && echo || echo "readyz not ok yet: docker compose -f docker-compose.prod.yml logs api worker"
echo "public: $(grep -E '^UNPACK_BASE_URL=' .env | cut -d= -f2-)/readyz"
