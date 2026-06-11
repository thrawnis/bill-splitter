#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

git checkout dev
git reset --hard
git pull origin dev

mkdir -p data/uploads data/postgres

export GIT_COMMIT=$(git rev-parse --short HEAD)

docker compose build --build-arg GIT_COMMIT="$GIT_COMMIT"
docker compose down
docker compose up -d

echo ""
docker compose ps
