#!/bin/bash
set -euo pipefail

mkdir -p /app/data/uploads
chown app:app /app/data /app/data/uploads

gosu app python -m app.migrate

exec gosu app uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
