#!/usr/bin/env bash
set -euo pipefail

BRANCH="main"
REPO="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$REPO/docker-compose.yml"
IMAGE="billsplit-app"

# --pull-base-images makes buildx re-check the registry for a newer base image.
# Off by default: it adds a network round-trip to every rebuild for almost no
# benefit. Pass it manually when you deliberately want a fresh python:3.12-slim.
# --force skips the "nothing changed" check below and rebuilds/recreates anyway.
PULL_BASE=""
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --pull-base-images) PULL_BASE="--pull" ;;
    --force) FORCE=1 ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

echo "==> Fetching latest code..."
git -C "$REPO" fetch origin "$BRANCH"

echo "==> Switching to branch: $BRANCH"
git -C "$REPO" checkout "$BRANCH"

# Reset straight to origin's tip rather than `git pull`, so this always lands
# on the latest commit even if the local branch ever diverges (a stray local
# commit, an interrupted previous run, etc.) instead of merging/failing.
# No `git clean`: data/postgres and data/uploads live inside this repo dir
# (git-ignored but untracked), and clean would delete the live DB/uploads.
echo "==> Discarding any local changes and resetting to origin/$BRANCH..."
git -C "$REPO" reset --hard "origin/$BRANCH"

COMMIT=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo "unknown")

# Compare against what's actually running, not just whether the pull brought
# new commits: a container stuck from a prior failed build, a manual restart,
# or an image built outside this script would otherwise be missed.
CONTAINER_ID=$(docker compose -f "$COMPOSE_FILE" ps -q app 2>/dev/null || true)
RUNNING_COMMIT=""
if [ -n "$CONTAINER_ID" ]; then
  RUNNING_COMMIT=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER_ID" 2>/dev/null | sed -n 's/^GIT_COMMIT=//p')
fi

if [ "$RUNNING_COMMIT" = "$COMMIT" ] && [ "$FORCE" -eq 0 ] && [ -z "$PULL_BASE" ]; then
  echo "==> Running container is already on commit $COMMIT; nothing to rebuild. Pass --force to rebuild anyway."
  exit 0
fi

# Ensure host-side data subdirs exist before Docker mounts them
echo "==> Creating data directories..."
mkdir -p "$REPO/data/uploads"

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
