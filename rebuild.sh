#!/usr/bin/env bash
set -euo pipefail

BRANCH="dev"
REPO="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$REPO/docker-compose.yml"
IMAGE="billsplit-app"

# --pull-base-images makes buildx re-check the registry for a newer base image.
# Off by default: it adds a network round-trip to every rebuild for almost no
# benefit. Pass it manually when you deliberately want a fresh python:3.12-slim.
PULL_BASE=""
for arg in "$@"; do
  case "$arg" in
    --pull-base-images) PULL_BASE="--pull" ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

echo "==> Switching to branch: $BRANCH"
git -C "$REPO" checkout "$BRANCH"

echo "==> Discarding any local changes..."
git -C "$REPO" reset --hard

echo "==> Pulling latest code..."
git -C "$REPO" pull origin "$BRANCH"

# Ensure host-side data subdirs exist before Docker mounts them
echo "==> Creating data directories..."
mkdir -p "$REPO/data/uploads"

COMMIT=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "==> Building image $IMAGE:latest (commit: $COMMIT)..."
# Build directly with buildx so BuildKit is always used. `docker compose build`
# can silently fall back to the legacy builder on this host, which then chokes
# on BuildKit-only Dockerfile features (# syntax=..., RUN --mount=type=cache).
# --load places the result in the local image store so Compose can find it.
# Long-form --tag on purpose: -t has tripped a spurious "unknown shorthand
# flag" error in this exact setup. $PULL_BASE is intentionally unquoted so it
# vanishes when empty and becomes --pull when the opt-in flag is passed.
docker buildx build \
    --tag "$IMAGE:latest" \
    --build-arg GIT_COMMIT="$COMMIT" \
    $PULL_BASE \
    --load \
    "$REPO"

echo "==> Recreating app container..."
# --no-build: never let Compose run its own (possibly non-BuildKit) build; it
# must use the image we just built. Only the app is force-recreated, so the
# database container keeps running. Compose still starts db if it isn't up,
# since app depends_on it.
docker compose -f "$COMPOSE_FILE" up -d --no-build --force-recreate app

echo "==> Done. Containers are running."
docker compose -f "$COMPOSE_FILE" ps
